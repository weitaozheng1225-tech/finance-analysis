"""Render the snapshot JSON to a Wall Street-style PDF using WeasyPrint.

Usage:
    python scripts/pdf.py                  # daily report → reports/daily/YYYY-MM-DD.pdf
    python scripts/pdf.py weekly           # weekly report → reports/weekly/YYYY-MM-DD.pdf
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SNAPSHOT = DATA / "latest_snapshot.json"
WEEKLY = DATA / "weekly_snapshot.json"
DAILY_OUT = ROOT / "reports" / "daily"
WEEKLY_OUT = ROOT / "reports" / "weekly"
EVENT_OUT = ROOT / "reports" / "events"

sys.path.insert(0, str(ROOT / "scripts"))
from config import GROUP_ORDER  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s")
log = logging.getLogger("pdf")


# ---------------------------------------------------------------------------
# Wall Street palette
# ---------------------------------------------------------------------------
CSS = """
@page {
  size: A4;
  margin: 18mm 16mm 22mm 16mm;
  @bottom-left {
    content: "全球长债危机监测 · 内部研究";
    font-family: 'Noto Serif CJK SC', 'Source Han Serif CN', 'DejaVu Serif', Georgia, serif;
    font-size: 8pt;
    color: #8B8B8B;
  }
  @bottom-right {
    content: "第 " counter(page) " / " counter(pages) " 页";
    font-family: 'Noto Serif CJK SC', 'Source Han Serif CN', 'DejaVu Serif', Georgia, serif;
    font-size: 8pt;
    color: #8B8B8B;
  }
}

* { box-sizing: border-box; }

body {
  font-family: 'Noto Sans CJK SC', 'Source Han Sans CN', 'DejaVu Sans', Helvetica, Arial, sans-serif;
  font-size: 9.5pt;
  color: #2C2C2C;
  line-height: 1.4;
  background: #FFFFFF;
}

/* ---------------- Header banner ---------------- */
.cover {
  background: #0F1E3D;
  color: #FFFFFF;
  padding: 14mm 12mm 12mm 12mm;
  margin: -18mm -16mm 8mm -16mm;
  border-bottom: 3pt solid #C9A961;
}
.cover .brand {
  font-family: 'Noto Serif CJK SC', 'Source Han Serif CN', 'DejaVu Serif', Georgia, serif;
  font-size: 9pt;
  letter-spacing: 0.3em;
  text-transform: uppercase;
  color: #C9A961;
  margin-bottom: 3mm;
}
.cover h1 {
  font-family: 'Noto Serif CJK SC', 'Source Han Serif CN', 'DejaVu Serif', Georgia, serif;
  font-size: 22pt;
  font-weight: normal;
  margin: 0 0 2mm 0;
}
.cover .subtitle {
  font-size: 10pt;
  color: #D6D2C8;
  margin: 0;
}
.cover .date {
  font-size: 10pt;
  color: #C9A961;
  margin-top: 4mm;
  letter-spacing: 0.05em;
}

/* ---------------- Section headings ---------------- */
h2 {
  font-family: 'Noto Serif CJK SC', 'Source Han Serif CN', 'DejaVu Serif', Georgia, serif;
  font-size: 11pt;
  font-weight: bold;
  color: #0F1E3D;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  border-bottom: 1pt solid #C9A961;
  padding-bottom: 2mm;
  margin: 9mm 0 4mm 0;
}
h3 {
  font-family: 'Noto Serif CJK SC', 'Source Han Serif CN', 'DejaVu Serif', Georgia, serif;
  font-size: 10pt;
  font-weight: bold;
  color: #0F1E3D;
  margin: 6mm 0 2mm 0;
  letter-spacing: 0.04em;
}

/* ---------------- Stress meter ---------------- */
.stress-block {
  background: #FAF8F3;
  padding: 6mm 8mm;
  border-left: 4pt solid #C9A961;
  margin-bottom: 4mm;
}
.stress-number {
  font-family: 'Noto Serif CJK SC', 'Source Han Serif CN', 'DejaVu Serif', Georgia, serif;
  font-size: 32pt;
  font-weight: bold;
  color: #0F1E3D;
  line-height: 1;
}
.stress-suffix {
  font-size: 14pt;
  color: #8B8B8B;
}
.stress-band {
  display: inline-block;
  padding: 1mm 4mm;
  border-radius: 2pt;
  font-size: 10pt;
  font-weight: bold;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  margin-left: 6mm;
  vertical-align: middle;
}
.band-ok      { background: #1F5C3D; color: #FFFFFF; }
.band-watch   { background: #C9A961; color: #0F1E3D; }
.band-warn    { background: #C97B1F; color: #FFFFFF; }
.band-crisis  { background: #9C2A2A; color: #FFFFFF; }

.meter {
  margin-top: 4mm;
  width: 100%;
  height: 6mm;
  background: #E8E5DE;
  border-radius: 1mm;
  position: relative;
  overflow: hidden;
}
.meter-fill {
  height: 100%;
  background: linear-gradient(to right, #1F5C3D 0%, #C9A961 33%, #C97B1F 58%, #9C2A2A 100%);
}
.meter-scale {
  display: flex;
  justify-content: space-between;
  font-size: 7pt;
  color: #8B8B8B;
  margin-top: 1mm;
  letter-spacing: 0.05em;
}

/* ---------------- Alerts ---------------- */
.alert {
  padding: 2mm 4mm;
  margin: 1.5mm 0;
  border-left: 3pt solid #9C2A2A;
  background: #FCEFEF;
  font-size: 9pt;
}
.alert.warn   { border-color: #C97B1F; background: #FDF4E8; }
.alert.crisis { border-color: #9C2A2A; background: #FCEFEF; }
.alert .label { font-weight: bold; color: #0F1E3D; }
.alert .body  { color: #2C2C2C; }
.no-alerts {
  font-style: italic;
  color: #1F5C3D;
  padding: 2mm 0;
}

/* ---------------- Tables ---------------- */
table {
  width: 100%;
  border-collapse: collapse;
  font-size: 8.5pt;
  margin: 2mm 0 4mm 0;
}
th {
  background: #0F1E3D;
  color: #FFFFFF;
  font-weight: bold;
  font-size: 8pt;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  text-align: left;
  padding: 1.5mm 2mm;
}
th.num { text-align: right; }
td {
  padding: 1.2mm 2mm;
  border-bottom: 0.5pt solid #E8E5DE;
  vertical-align: top;
}
td.num { text-align: right; font-variant-numeric: tabular-nums; }
td.center { text-align: center; }
tr:nth-child(even) td { background: #FAF8F3; }

.tag {
  display: inline-block;
  padding: 0.3mm 1.5mm;
  border-radius: 1pt;
  font-size: 7pt;
  font-weight: bold;
  letter-spacing: 0.05em;
}
.tag-ok      { background: #E8F0EA; color: #1F5C3D; }
.tag-warn    { background: #FDF4E8; color: #C97B1F; }
.tag-crisis  { background: #FCEFEF; color: #9C2A2A; }

.delta-up   { color: #9C2A2A; }
.delta-down { color: #1F5C3D; }
.delta-flat { color: #8B8B8B; }

/* ---------------- Glossary ---------------- */
.glossary-item {
  margin: 2.5mm 0;
  padding-left: 4mm;
  border-left: 2pt solid #E8E5DE;
}
.glossary-item .term {
  font-weight: bold;
  color: #0F1E3D;
  font-size: 9pt;
}
.glossary-item .meta {
  color: #8B8B8B;
  font-size: 7.5pt;
  letter-spacing: 0.05em;
}
.glossary-item .desc {
  margin-top: 1mm;
  font-size: 8.5pt;
  color: #2C2C2C;
  line-height: 1.5;
}

/* ---------------- Misc ---------------- */
.footer-note {
  margin-top: 8mm;
  padding-top: 3mm;
  border-top: 0.5pt solid #E8E5DE;
  font-size: 7.5pt;
  color: #8B8B8B;
  line-height: 1.5;
}
.page-break { page-break-before: always; }
"""


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------
BAND_CLASS = {"ok": "band-ok", "watch": "band-watch", "warn": "band-warn", "crisis": "band-crisis"}
BAND_NAME = {"ok": "正常", "watch": "观察", "warn": "警戒", "crisis": "危机"}
STATE_CLASS = {"ok": "tag-ok", "warn": "tag-warn", "crisis": "tag-crisis"}
STATE_TAG = {"ok": "—", "warn": "警戒", "crisis": "危机"}


def fmt_value(v, unit: str = "", digits: int = 3) -> str:
    if v is None:
        return "—"
    if unit == "%":
        return f"{v:.3f}%"
    if unit in {"USD/oz", "USD"}:
        return f"${v:,.2f}"
    if unit == "GBp":
        return f"{v:,.2f}"
    if unit == "JPY":
        return f"¥{v:,.2f}"
    if unit == "$B":
        return f"${v:,.1f}B"
    if unit == "$M":
        return f"${v:,.0f}M"
    if unit == "idx":
        return f"{v:,.2f}"
    return f"{v:,.{digits}f}"


def fmt_delta_level(v) -> str:
    if v is None:
        return "—"
    sign = "+" if v >= 0 else ""
    return f"{sign}{v:.3f}"


def fmt_delta_pct(v) -> str:
    if v is None:
        return "—"
    sign = "+" if v >= 0 else ""
    return f"{sign}{v * 100:.2f}%"


def delta_class(v) -> str:
    if v is None or v == 0:
        return "delta-flat"
    return "delta-up" if v > 0 else "delta-down"


def fmt_change(v, unit: str) -> tuple[str, str]:
    """Returns (text, css_class) for a delta value."""
    if unit in {"%", "bp"}:
        return fmt_delta_level(v), delta_class(v)
    return fmt_delta_pct(v), delta_class(v)


def fmt_z(v) -> str:
    if v is None:
        return "—"
    return f"{v:+.2f}"


def state_tag(state: str) -> str:
    return f'<span class="tag {STATE_CLASS.get(state, "tag-ok")}">{STATE_TAG.get(state, "OK")}</span>'


def band_pill(band: str) -> str:
    return f'<span class="stress-band {BAND_CLASS.get(band, "band-ok")}">{BAND_NAME.get(band, band)}</span>'


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------
def render_daily(snap: dict) -> str:
    band = snap["stress_band"]
    stress = snap["composite_stress"]
    meter_pct = min(100, max(0, int(stress / 12 * 100)))

    # Alerts section
    if snap["anomalies"]:
        alerts_html = "".join(
            f'<div class="alert {"crisis" if "危机" in a else "warn"}">'
            f'<span class="label">▸</span> <span class="body">{a}</span>'
            f"</div>"
            for a in snap["anomalies"]
        )
    else:
        alerts_html = '<div class="no-alerts">今日无阈值越界或异常波动。</div>'

    # Stress components table
    comp_rows = "".join(
        f"<tr><td>{c['name']}</td><td class='num'>{fmt_value(c['value'], '', 3)}</td>"
        f"<td class='num'>{c['detail']}</td>"
        f"<td class='center'><b>{c['points']}</b></td></tr>"
        for c in snap["components"]
    )

    # Indicator tables — grouped
    indicators_by_group: dict[str, list] = {}
    for ind in snap["indicators"]:
        indicators_by_group.setdefault(ind.get("group") or "Other", []).append(ind)

    group_html_parts: list[str] = []
    for group in GROUP_ORDER + [g for g in indicators_by_group if g not in GROUP_ORDER]:
        if group not in indicators_by_group:
            continue
        rows = []
        for ind in indicators_by_group[group]:
            unit = ind.get("unit", "")
            c1, c1c = fmt_change(ind["change_1d"], unit)
            c5, c5c = fmt_change(ind["change_5d"], unit)
            c20, c20c = fmt_change(ind["change_20d"], unit)
            rows.append(
                f"<tr><td>{ind['label']}</td>"
                f"<td class='num'>{fmt_value(ind['latest_value'], unit)}</td>"
                f"<td class='center' style='font-size:7.5pt;color:#8B8B8B'>{ind['latest_date'] or '—'}</td>"
                f"<td class='num {c1c}'>{c1}</td>"
                f"<td class='num {c5c}'>{c5}</td>"
                f"<td class='num {c20c}'>{c20}</td>"
                f"<td class='num'>{fmt_z(ind['z_60d'])}</td>"
                f"<td class='center'>{state_tag(ind['threshold_state'])}</td></tr>"
            )
        group_html_parts.append(
            f"<h3>{group}</h3>"
            f"<table><thead><tr>"
            f"<th>指标</th><th class='num'>最新</th>"
            f"<th class='center'>日期</th>"
            f"<th class='num'>1 日Δ</th><th class='num'>5 日Δ</th><th class='num'>20 日Δ</th>"
            f"<th class='num'>z (60 日)</th><th class='center'>状态</th>"
            f"</tr></thead><tbody>"
            f"{''.join(rows)}</tbody></table>"
        )

    # Glossary
    glossary_parts: list[str] = []
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
                f"<div class='meta'>标识 {ind['name']} · 单位 {ind.get('unit', '—')}</div>"
                f"<div class='desc'>{ind['notes']}</div>"
                f"</div>"
            )

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>全球长债危机监测 — 每日报告 {snap['as_of']}</title>
<style>{CSS}</style>
</head>
<body>

<div class="cover">
  <div class="brand">BOND CRISIS MONITOR · 全球长债危机监测</div>
  <h1>每日风险报告</h1>
  <p class="subtitle">日本 / 美国 / 英国 长端收益率压力监测</p>
  <p class="date">数据截至 {snap['as_of']}</p>
</div>

<h2>执行摘要</h2>
<div class="stress-block">
  <div>
    <span class="stress-number">{stress}</span><span class="stress-suffix"> / 12</span>
    {band_pill(band)}
  </div>
  <div class="meter"><div class="meter-fill" style="width:{meter_pct}%"></div></div>
  <div class="meter-scale">
    <span>0 正常</span><span>4 警戒</span><span>7 危机</span><span>12 极值</span>
  </div>
</div>

<h2>告警与异常</h2>
{alerts_html}

<h2>压力指数构成</h2>
<table>
  <thead><tr>
    <th>分量</th><th class='num'>当前值</th><th class='num'>阈值（low / high）</th>
    <th class='center'>得分</th>
  </tr></thead>
  <tbody>{comp_rows}</tbody>
</table>

<div class="page-break"></div>
<h2>指标快照</h2>
{''.join(group_html_parts)}

<div class="page-break"></div>
<h2>指标释义与经济学意义</h2>
{''.join(glossary_parts)}

<div class="footer-note">
  缩写说明：<b>OAS</b> = 期权调整利差；<b>SOFR</b> = 隔夜担保融资利率；
  <b>IORB</b> = 准备金利息；<b>RRP</b> = 隔夜逆回购工具；
  <b>ACM</b> = Adrian-Crump-Moench 期限溢价模型；<b>JGB</b> = 日本国债；
  <b>LDI</b> = 负债驱动投资；<b>MOVE</b> = 美林期权波动率估计；
  <b>VIX</b> = CBOE 波动率指数；<b>TLT</b> = iShares 20+Y 美国国债 ETF；
  <b>KRE</b> = SPDR S&amp;P 区域银行 ETF；<b>DXY</b> = 美元指数。
  收益率与 OAS 以百分比水平展示（4.470 即 4.470%）；
  对于收益率/利差，"Δ" 列为水平差；对于价格/指数，"Δ" 列为百分比。
  复合压力指数算法详见 <code>01_scenario_analysis.md §5</code>。
</div>

</body>
</html>
"""


def render_event_html(status: dict) -> str:
    """即时事件警报 PDF。红色封面 + 触发信号表 + AI 后果分析。"""
    triggers = status.get("triggers", [])
    news = status.get("news", {}) or {}
    band = status.get("stress_band", "ok")
    stress = status.get("composite_stress", 0)

    if triggers:
        trig_rows = "".join(
            f"<tr><td>{t.get('category','')}</td><td>{t.get('desc','')}</td>"
            f"<td>{t.get('indicator','')}</td>"
            f"<td class='num'>{fmt_value(t.get('latest_value'))}</td>"
            f"<td class='num'>{fmt_value(t.get('change_1d'))}</td></tr>"
            for t in triggers
        )
        trig_block = (
            "<h2>数值触发信号</h2><table><thead><tr>"
            "<th>类别</th><th>触发条件</th><th>指标</th>"
            "<th class='num'>当前值</th><th class='num'>单日Δ</th>"
            "</tr></thead><tbody>" + trig_rows + "</tbody></table>"
        )
    else:
        trig_block = "<h2>数值触发信号</h2><div class='no-alerts'>无数值触发；事件来自新闻扫描。</div>"

    news_events = news.get("events", [])
    if news_events:
        items = "".join(
            f"<div class='glossary-item'><div class='term'>[{e.get('category','')}] "
            f"{e.get('headline','')}</div><div class='desc'>{e.get('summary','')}</div>"
            + (
                "<div class='meta'>来源：" + " · ".join(
                    f"<a href='{u}'>{u}</a>" for u in e.get("sources", [])
                ) + "</div>" if e.get("sources") else ""
            )
            + "</div>"
            for e in news_events
        )
        news_block = "<h2>新闻扫描发现</h2>" + items
    else:
        news_block = "<h2>新闻扫描发现</h2><div class='no-alerts'>新闻扫描未发现重大事件（事件由数值触发）。</div>"

    if status.get("ai_narrative"):
        analysis_block = (
            "<div class='page-break'></div><h2>AI 后果分析</h2>"
            f"<div style='font-size:9.5pt;line-height:1.6;'>{status['ai_narrative']}</div>"
        )
    else:
        analysis_block = (
            "<div class='page-break'></div><h2>AI 后果分析</h2>"
            "<div class='no-alerts'>未生成 AI 分析（未配置 ANTHROPIC_API_KEY 或调用失败）。"
            "请结合上方触发信号与新闻自行研判。</div>"
        )

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8">
<title>全球长债危机监测 — 即时事件警报 {status.get('as_of','')}</title>
<style>{CSS}
.cover {{ background:#9C2A2A; }}
.cover .brand {{ color:#F4D6D6; }}
.cover .date {{ color:#F4D6D6; }}
</style></head>
<body>
<div class="cover">
  <div class="brand">BOND CRISIS MONITOR · 即时事件警报</div>
  <h1>⚠ 实质性事件警报</h1>
  <p class="subtitle">检测到对全球债券市场可能有实质性影响的事件</p>
  <p class="date">数据截至 {status.get('as_of','')} · 检测时间 {status.get('checked_at','')[:16]} UTC</p>
</div>

<h2>当前压力定位</h2>
<div class="stress-block">
  <div><span class="stress-number">{stress}</span><span class="stress-suffix"> / 12</span>
  {band_pill(band)}</div>
</div>

{trig_block}
{news_block}
{analysis_block}

<div class="footer-note">
  本警报由数值触发器（单日事件级异动）与 AI 联网新闻扫描共同判定，
  后果分析由 Claude Opus 4.7 结合参考框架与当下市场快照生成，仅供研究参考，
  不构成投资建议。完整方法见 <code>01_scenario_analysis.md</code>。
</div>
</body></html>
"""


def render_pdf(html: str, out_path: Path) -> None:
    from weasyprint import HTML  # imported lazily so unit tests don't need libs
    out_path.parent.mkdir(parents=True, exist_ok=True)
    HTML(string=html, base_url=str(ROOT)).write_pdf(str(out_path))
    log.info("Wrote %s (%d KB)", out_path, out_path.stat().st_size // 1024)


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "daily"
    if mode == "daily":
        snap = json.loads(SNAPSHOT.read_text())
        html = render_daily(snap)
        out = DAILY_OUT / f"{snap['as_of']}.pdf"
        render_pdf(html, out)
        (DAILY_OUT / "latest.pdf").write_bytes(out.read_bytes())
        return 0
    elif mode == "weekly":
        if not WEEKLY.exists():
            log.error("weekly_snapshot.json missing — run weekly_report.py first")
            return 1
        snap = json.loads(WEEKLY.read_text())
        # Re-use the daily template for now; weekly_report.py extends it later
        from weekly_report import render_weekly_html
        html = render_weekly_html(snap)
        out = WEEKLY_OUT / f"{snap['as_of']}.pdf"
        render_pdf(html, out)
        (WEEKLY_OUT / "latest.pdf").write_bytes(out.read_bytes())
        return 0
    elif mode == "event":
        status_path = DATA / "event_status.json"
        if not status_path.exists():
            log.error("event_status.json missing — run event_monitor.py first")
            return 1
        status = json.loads(status_path.read_text())
        if not status.get("detected"):
            log.info("event not detected — no event PDF generated")
            return 0
        EVENT_OUT.mkdir(parents=True, exist_ok=True)
        html = render_event_html(status)
        stamp = (status.get("checked_at") or status.get("as_of") or "event")[:16].replace(":", "")
        out = EVENT_OUT / f"{stamp}.pdf"
        render_pdf(html, out)
        (EVENT_OUT / "latest.pdf").write_bytes(out.read_bytes())
        return 0
    else:
        log.error("Unknown mode: %s (use 'daily' | 'weekly' | 'event')", mode)
        return 2


if __name__ == "__main__":
    sys.exit(main())
