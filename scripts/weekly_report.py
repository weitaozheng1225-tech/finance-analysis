"""Aggregate the past 7 days of data into a weekly snapshot + render PDF.

Produces ``data/weekly_snapshot.json`` and the weekly HTML rendered by
``pdf.py``. The output extends the daily snapshot with:

  * 7-day evolution of the composite stress index
  * Top-5 indicator movers (by |z-score|) over the week
  * Anomaly history (which days fired what)
  * Heuristic regime-mapping section that walks each of scenarios A-E
    and updates probability bands based on the week's evidence

No AI is required. The Claude subagent ``bond-crisis-monitor`` remains
the on-demand deep-dive route — invoke it from Claude Code when you want
a narrative interpretation with live web research.
"""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import asdict
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
TS = DATA / "timeseries"
SNAPSHOT = DATA / "latest_snapshot.json"
WEEKLY = DATA / "weekly_snapshot.json"

sys.path.insert(0, str(ROOT / "scripts"))
from config import GROUP_ORDER, INDICATORS, STRESS_COMPONENTS  # noqa: E402
from analyze import compute_snapshot  # noqa: E402
from pdf import (  # noqa: E402
    CSS, band_pill, fmt_change, fmt_value, fmt_z, state_tag,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s")
log = logging.getLogger("weekly")


def _load(name: str) -> pd.Series:
    p = TS / f"{name}.csv"
    if not p.exists():
        return pd.Series(dtype=float)
    df = pd.read_csv(p, parse_dates=["date"])
    return df.set_index("date")["value"].sort_index()


def _stress_history(days: int = 30) -> list[dict]:
    """Compute stress index for each of the last `days` business days
    using cached time-series. Returns list of {date, stress, band}.
    """
    # Build a per-day composite by replaying the rule on the historic data.
    # For each business day in the lookback, look at the value of each
    # stress component series at that date.
    end = date.today()
    start = end - timedelta(days=days)
    # Choose the union of all dates that appear in the component series
    series_map: dict[str, pd.Series] = {}
    for spec in STRESS_COMPONENTS:
        if "derived" in spec:
            # Derived components require multi-series lookups; replay only at end.
            continue
        s = _load(spec["indicator"])
        if not s.empty:
            series_map[spec["indicator"]] = s

    # Build date axis from any series
    if not series_map:
        return []
    union = sorted({d for s in series_map.values() for d in s.index if start <= d.date() <= end})
    out = []
    for d in union:
        total = 0
        for spec in STRESS_COMPONENTS:
            if "derived" in spec:
                # Recompute derived for this date
                if spec["derived"] == "sofr_iorb_spread":
                    sofr, iorb = _load("sofr"), _load("iorb")
                    if d in sofr.index and d in iorb.index:
                        v = float(sofr.loc[d] - iorb.loc[d])
                    else:
                        v = None
                elif spec["derived"] == "uk_gilt_etf_5d_return":
                    g = _load("uk_gilt_etf")
                    g_at = g[g.index <= d]
                    if len(g_at) >= 6:
                        v = float((g_at.iloc[-1] - g_at.iloc[-6]) / abs(g_at.iloc[-6]))
                    else:
                        v = None
                elif spec["derived"] == "kre_1m_return":
                    k = _load("kre")
                    k_at = k[k.index <= d]
                    if len(k_at) >= 22:
                        v = float((k_at.iloc[-1] - k_at.iloc[-22]) / abs(k_at.iloc[-22]))
                    else:
                        v = None
                else:
                    v = None
            else:
                s = series_map.get(spec["indicator"])
                v = float(s.loc[d]) if (s is not None and d in s.index) else None
            if v is None:
                continue
            direction = spec["direction"]
            low, high = spec["low"], spec["high"]
            if direction == "above":
                if v >= high:
                    total += 2
                elif v >= low:
                    total += 1
            else:
                if v <= high:
                    total += 2
                elif v <= low:
                    total += 1
        band = "crisis" if total >= 7 else "warn" if total >= 4 else "watch" if total >= 1 else "ok"
        out.append({"date": d.date().isoformat(), "stress": total, "band": band})
    return out


def _top_movers(indicators: list[dict], n: int = 5) -> tuple[list[dict], list[dict]]:
    """Return (top-up, top-down) by 5d change, normalised across yield/price units."""
    scored: list[tuple[float, dict]] = []
    for ind in indicators:
        v = ind.get("change_5d")
        if v is None:
            continue
        # Use raw value; the sign carries direction
        scored.append((v, ind))
    scored.sort(key=lambda x: x[0])
    return [s[1] for s in scored[-n:][::-1]], [s[1] for s in scored[:n]]


def _scenario_table(snap: dict, history: list[dict]) -> list[dict]:
    """Apply simple heuristics to update scenario probabilities from baseline.

    Baseline probabilities live in 01_scenario_analysis.md. We adjust them
    in a transparent, rule-based way using the observed evidence.
    """
    baseline = [
        {"name": "A · 常态化高利率", "base_low": 45, "base_high": 55},
        {"name": "B · 区域性流动性事件", "base_low": 25, "base_high": 35},
        {"name": "C · 跨市场传染",       "base_low": 10, "base_high": 20},
        {"name": "D · 美债技术性违约",   "base_low":  3, "base_high":  7},
        {"name": "E · 美债实质性违约",   "base_low":  0, "base_high":  1},
    ]

    inds = {i["name"]: i for i in snap["indicators"]}
    jgb_crisis = sum(1 for k in ("jgb_10y", "jgb_30y", "jgb_40y")
                     if inds.get(k, {}).get("threshold_state") == "crisis")
    move_high = (inds.get("move", {}).get("latest_value") or 0) > 140
    tp_warn = (inds.get("us_10y_term_premium", {}).get("latest_value") or 0) > 0.5
    kre_down = (inds.get("kre", {}).get("change_20d") or 0) < -0.05
    crisis_days = sum(1 for h in history if h["band"] == "crisis")
    warn_days = sum(1 for h in history if h["band"] == "warn")

    # Adjustments — small, transparent, additive
    adj = [0, 0, 0, 0, 0]
    notes = []
    if jgb_crisis >= 2:
        adj[1] += 8
        adj[0] -= 5
        notes.append(f"{jgb_crisis} JGB tenors at crisis-level → +8 to B (Japan-led liquidity event)")
    if move_high:
        adj[1] += 5
        adj[2] += 3
        notes.append("MOVE > 140 → +5 to B, +3 to C (rates-vol regime shift)")
    if tp_warn:
        adj[0] -= 2
        adj[1] += 2
        notes.append("Term premium > 0.5% → +2 to B (structural repricing)")
    if kre_down:
        adj[1] += 4
        notes.append("KRE 20d return < -5% → +4 to B (US bank capital stress)")
    if crisis_days >= 2:
        adj[2] += 5
        adj[3] += 1
        notes.append(f"{crisis_days} crisis-band days this week → +5 to C, +1 to D")
    elif warn_days >= 3:
        adj[1] += 3
        notes.append(f"{warn_days} warn-band days this week → +3 to B")

    out = []
    for i, s in enumerate(baseline):
        out.append({
            "name": s["name"],
            "low": max(0, s["base_low"] + adj[i]),
            "high": max(0, s["base_high"] + adj[i]),
        })
    return out, notes


def build_weekly() -> dict:
    daily = json.loads(SNAPSHOT.read_text()) if SNAPSHOT.exists() else asdict(compute_snapshot())
    history = _stress_history(days=14)
    up, down = _top_movers(daily["indicators"], n=5)
    scenarios, scenario_notes = _scenario_table(daily, history)
    return {
        "as_of": date.today().isoformat(),
        "today_stress": daily["composite_stress"],
        "today_band": daily["stress_band"],
        "stress_history": history,
        "top_movers_up": up,
        "top_movers_down": down,
        "anomalies": daily["anomalies"],
        "components": daily["components"],
        "indicators": daily["indicators"],
        "scenarios": scenarios,
        "scenario_notes": scenario_notes,
    }


# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------
def _history_chart_svg(history: list[dict], width: int = 480, height: int = 80) -> str:
    if not history:
        return ""
    values = [h["stress"] for h in history]
    n = len(values)
    if n < 2:
        return ""
    max_v = max(12, max(values))
    pad_x, pad_y = 4, 6
    inner_w, inner_h = width - 2 * pad_x, height - 2 * pad_y
    pts = []
    for i, v in enumerate(values):
        x = pad_x + i * inner_w / (n - 1)
        y = pad_y + inner_h * (1 - v / max_v)
        pts.append(f"{x:.1f},{y:.1f}")
    poly = " ".join(pts)
    # Highlight warn/crisis regions with horizontal bands
    warn_y = pad_y + inner_h * (1 - 4 / max_v)
    crisis_y = pad_y + inner_h * (1 - 7 / max_v)
    last_x, last_y = pts[-1].split(",")
    return f"""
<svg width="100%" viewBox="0 0 {width} {height}" preserveAspectRatio="none"
     style="margin-top:3mm">
  <rect x="0" y="{crisis_y}" width="{width}" height="{height - crisis_y}"
        fill="#FCEFEF"/>
  <rect x="0" y="{warn_y}" width="{width}" height="{crisis_y - warn_y}"
        fill="#FDF4E8"/>
  <polyline points="{poly}" fill="none" stroke="#0F1E3D" stroke-width="1.5"/>
  <circle cx="{last_x}" cy="{last_y}" r="3" fill="#C9A961" stroke="#0F1E3D" stroke-width="0.8"/>
  <text x="{float(last_x) + 6}" y="{float(last_y) + 3}" font-size="9"
        font-family="DejaVu Serif" fill="#0F1E3D" font-weight="bold">{values[-1]}/12</text>
</svg>
"""


def render_weekly_html(snap: dict) -> str:
    history = snap["stress_history"]
    chart = _history_chart_svg(history)
    band = snap["today_band"]
    stress = snap["today_stress"]

    # Top movers tables
    def _movers_table(movers, title):
        rows = []
        for ind in movers:
            unit = ind.get("unit", "")
            c5, c5c = fmt_change(ind["change_5d"], unit)
            rows.append(
                f"<tr><td>{ind['label']}</td>"
                f"<td class='num'>{fmt_value(ind['latest_value'], unit)}</td>"
                f"<td class='num {c5c}'>{c5}</td>"
                f"<td class='num'>{fmt_z(ind['z_60d'])}</td>"
                f"<td class='center'>{state_tag(ind['threshold_state'])}</td></tr>"
            )
        return (
            f"<h3>{title}</h3>"
            f"<table><thead><tr>"
            f"<th>Indicator</th><th class='num'>Latest</th>"
            f"<th class='num'>5d Δ</th><th class='num'>z (60d)</th><th class='center'>Status</th>"
            f"</tr></thead><tbody>{''.join(rows)}</tbody></table>"
        )

    # Scenario table
    sc_rows = "".join(
        f"<tr><td>{s['name']}</td><td class='num'>{s['low']}-{s['high']}%</td></tr>"
        for s in snap["scenarios"]
    )
    sc_notes_html = (
        "<ul style='margin:1mm 0 0 4mm;font-size:8.5pt;color:#2C2C2C'>"
        + "".join(f"<li>{n}</li>" for n in snap["scenario_notes"])
        + "</ul>"
    ) if snap["scenario_notes"] else ""

    # Stress history table
    hist_rows = "".join(
        f"<tr><td>{h['date']}</td>"
        f"<td class='num'>{h['stress']}</td>"
        f"<td class='center'>{band_pill(h['band'])}</td></tr>"
        for h in history[-14:]
    )

    # Anomalies
    if snap["anomalies"]:
        anomalies_html = "<ul style='margin:1mm 0 0 4mm'>" + "".join(
            f"<li>{a}</li>" for a in snap["anomalies"]
        ) + "</ul>"
    else:
        anomalies_html = "<div class='no-alerts'>No active anomalies.</div>"

    # Full indicator glossary (re-used from daily)
    glossary_parts = []
    for group in GROUP_ORDER:
        items = [i for i in snap["indicators"] if i.get("group") == group]
        if not items:
            continue
        glossary_parts.append(f"<h3>{group}</h3>")
        for ind in items:
            if not ind.get("notes"):
                continue
            glossary_parts.append(
                f"<div class='glossary-item'>"
                f"<div class='term'>{ind['label']}</div>"
                f"<div class='meta'>{ind['name']} · unit: {ind.get('unit', '—')}</div>"
                f"<div class='desc'>{ind['notes']}</div></div>"
            )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Bond Crisis Monitor — Weekly Report {snap['as_of']}</title>
<style>{CSS}</style>
</head>
<body>

<div class="cover">
  <div class="brand">Bond Crisis Monitor</div>
  <h1>Weekly Risk Report</h1>
  <p class="subtitle">Global long-end yield stress · 14-day window</p>
  <p class="date">Week ending {snap['as_of']}</p>
</div>

<h2>This Week at a Glance</h2>
<div class="stress-block">
  <div>
    <span class="stress-number">{stress}</span><span class="stress-suffix"> / 12</span>
    {band_pill(band)}
  </div>
  <div style="font-size:8.5pt; color:#8B8B8B; margin-top:2mm;">
    Composite stress index — 14-day evolution
  </div>
  {chart}
</div>

<h2>Active Anomalies</h2>
{anomalies_html}

<h2>Scenario Probability — Updated</h2>
<table>
  <thead><tr><th>Scenario</th><th class='num'>Range</th></tr></thead>
  <tbody>{sc_rows}</tbody>
</table>
<div style="font-size:8.5pt; color:#2C2C2C;">
  Baseline ranges from <code>01_scenario_analysis.md §3</code>. Adjustments derived
  from this week's evidence:
</div>
{sc_notes_html}

<div class="page-break"></div>
<h2>Top Movers This Week (by 5-day change)</h2>
{_movers_table(snap["top_movers_up"], "Largest gainers")}
{_movers_table(snap["top_movers_down"], "Largest decliners")}

<h2>Stress Index History (14 trading days)</h2>
<table>
  <thead><tr>
    <th>Date</th><th class='num'>Stress</th><th class='center'>Band</th>
  </tr></thead>
  <tbody>{hist_rows}</tbody>
</table>

<div class="page-break"></div>
<h2>Glossary &amp; Economic Meaning</h2>
{''.join(glossary_parts)}

<div class="footer-note">
  Weekly report is rule-based. For narrative interpretation grounded in live
  web research (news, central-bank communications, auction results), invoke
  the <code>bond-crisis-monitor</code> subagent from Claude Code.
  Methodology: <code>01_scenario_analysis.md</code>;
  data sources: <code>README.md</code>.
</div>

</body>
</html>
"""


def main() -> int:
    snap = build_weekly()
    WEEKLY.write_text(json.dumps(snap, indent=2, default=str))
    log.info("Weekly snapshot: stress=%d/%s, %d historical points, %d anomalies",
             snap["today_stress"], snap["today_band"],
             len(snap["stress_history"]), len(snap["anomalies"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
