"""Generate the daily Markdown report from the snapshot JSON."""

from __future__ import annotations

import json
import logging
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT = ROOT / "data" / "latest_snapshot.json"
REPORTS = ROOT / "reports" / "daily"
REPORTS.mkdir(parents=True, exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s")
log = logging.getLogger("report")

BAND_BADGE = {
    "ok": "🟢 NORMAL",
    "watch": "🟡 WATCH",
    "warn": "🟠 WARN",
    "crisis": "🔴 CRISIS",
}
STATE_BADGE = {"ok": "·", "warn": "⚠", "crisis": "🔴"}


def _fmt(v, digits=3):
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:.{digits}f}"
    return str(v)


def _fmt_pct(v):
    if v is None:
        return "—"
    return f"{v * 100:+.2f}%"


def _fmt_level(v):
    if v is None:
        return "—"
    return f"{v:+.3f}"


def render(snap: dict) -> str:
    lines: list[str] = []
    band = snap["stress_band"]
    lines.append(f"# 全球长债危机监测 · {snap['as_of']}")
    lines.append("")
    lines.append(f"## 综合压力指数: **{snap['composite_stress']} / 12** — {BAND_BADGE.get(band, band)}")
    lines.append("")

    # Anomalies first — the actionable bit
    if snap["anomalies"]:
        lines.append("## 🚨 异常 / 阈值告警")
        lines.append("")
        for a in snap["anomalies"]:
            lines.append(f"- {a}")
        lines.append("")
    else:
        lines.append("## ✅ 无异常或阈值越界")
        lines.append("")

    # Stress component breakdown
    lines.append("## 压力指数构成")
    lines.append("")
    lines.append("| 维度 | 当前值 | 阈值 (low/high) | 得分 |")
    lines.append("| --- | --- | --- | --- |")
    for c in snap["components"]:
        lines.append(f"| {c['name']} | {_fmt(c['value'])} | {c['detail']} | **{c['points']}** |")
    lines.append("")

    # Full indicator table
    lines.append("## 指标快照")
    lines.append("")
    lines.append("| 指标 | 最新 | 日期 | 1d Δ | 5d Δ | 20d Δ | z (60d) | 状态 |")
    lines.append("| --- | ---: | --- | ---: | ---: | ---: | ---: | :---: |")
    for ind in snap["indicators"]:
        # Heuristic: yields/spreads use level deltas, prices use pct
        # The analyze step already chose the correct delta type per unit.
        c1 = _fmt_level(ind["change_1d"]) if abs(ind["change_1d"] or 0) < 1.5 else _fmt_pct(ind["change_1d"])
        c5 = _fmt_level(ind["change_5d"]) if abs(ind["change_5d"] or 0) < 1.5 else _fmt_pct(ind["change_5d"])
        c20 = _fmt_level(ind["change_20d"]) if abs(ind["change_20d"] or 0) < 1.5 else _fmt_pct(ind["change_20d"])
        z = "—" if ind["z_60d"] is None else f"{ind['z_60d']:+.2f}"
        st = STATE_BADGE.get(ind["threshold_state"], "·")
        lines.append(
            f"| {ind['label']} | {_fmt(ind['latest_value'])} | {ind['latest_date'] or '—'} | "
            f"{c1} | {c5} | {c20} | {z} | {st} |"
        )
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("> 字段说明：yields/spreads 显示**水平差**(unit-level)；价格/指数显示**百分比**。")
    lines.append("> 阈值与压力指数定义见 `01_scenario_analysis.md` §5 与 `02_observation_indicators.md`。")
    lines.append("> 若需要深入分析或推演下一步影响，在 Claude Code 中调用 `bond-crisis-monitor` subagent。")
    return "\n".join(lines)


def main() -> int:
    snap = json.loads(SNAPSHOT.read_text())
    md = render(snap)
    today = snap["as_of"]
    out = REPORTS / f"{today}.md"
    out.write_text(md)
    # Also write to a stable "latest.md" for easy linking
    (REPORTS / "latest.md").write_text(md)
    log.info("Wrote %s (%d bytes)", out, len(md))
    return 0


if __name__ == "__main__":
    sys.exit(main())
