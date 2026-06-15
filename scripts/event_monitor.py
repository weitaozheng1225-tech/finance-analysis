"""即时事件检测与后果分析。

每次运行（每日两次：亚收 ~07:00 UTC、美收 ~22:00 UTC）执行：

  1. 数值触发器：从 latest_snapshot.json 读各指标单日异动，对照 config
     的 EVENT_TRIGGERS / EVENT_STRESS_JUMP，找出"事件规模"的异动。
  2. AI 新闻扫描（兜底）：调用 Claude + 联网搜索，按 EVENT_TAXONOMY 主动
     排查过去约 18 小时是否发生实质性全球债市事件。
  3. 若数值或新闻任一判定发生事件 → 调用 Opus 4.7 结合当下经济金融环境
     做深度后果分析，写入 data/event_status.json（含可嵌入 PDF 的 HTML）。

无 ANTHROPIC_API_KEY 时优雅降级：跳过 AI，仅凭数值触发器判定，警报正文
列出原始触发项（不含 AI 后果分析）。无事件时写 detected=false，下游不发邮件。

环境变量：
  ANTHROPIC_API_KEY  必需（缺失则跳过所有 AI 步骤）
  EVENT_SCAN_MODEL   新闻扫描模型，默认 claude-opus-4-7（可设 claude-sonnet-4-6 降本）
  EVENT_ANALYSIS_MODEL 深度分析模型，默认 claude-opus-4-7
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SNAPSHOT = DATA / "latest_snapshot.json"
STRESS_LOG = DATA / "stress_log.csv"
EVENT_STATUS = DATA / "event_status.json"

FRAMEWORK_DOCS = [
    ROOT / "01_scenario_analysis.md",
    ROOT / "03_us_default_deep_dive.md",
    ROOT / "04_japan_carry_unwind.md",
    ROOT / "05_uk_gilt_ldi_risk.md",
]

sys.path.insert(0, str(ROOT / "scripts"))
from config import EVENT_STRESS_JUMP, EVENT_TAXONOMY, EVENT_TRIGGERS, INDICATORS  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s")
log = logging.getLogger("event")

SCAN_MODEL = os.getenv("EVENT_SCAN_MODEL", "claude-opus-4-7")
ANALYSIS_MODEL = os.getenv("EVENT_ANALYSIS_MODEL", "claude-opus-4-7")


# ---------------------------------------------------------------------------
# 1. 数值触发器
# ---------------------------------------------------------------------------
def _indicator_map(snap: dict) -> dict[str, dict]:
    return {i["name"]: i for i in snap.get("indicators", [])}


def numeric_triggers(snap: dict) -> list[dict]:
    inds = _indicator_map(snap)
    fired: list[dict] = []
    for t in EVENT_TRIGGERS:
        ind = inds.get(t["indicator"])
        if not ind:
            continue
        chg = ind.get("change_1d")
        if chg is None:
            continue
        thr, direction = t["threshold"], t["direction"]
        hit = (
            (direction == "abs" and abs(chg) >= abs(thr))
            or (direction == "up" and chg >= thr)
            or (direction == "down" and chg <= thr)
        )
        if hit:
            fired.append({
                "category": t["category"],
                "desc": t["desc"],
                "indicator": ind["label"],
                "change_1d": chg,
                "latest_value": ind.get("latest_value"),
            })
    # 复合压力指数单日跳升
    jump = _stress_jump()
    if jump is not None and jump >= EVENT_STRESS_JUMP:
        fired.append({
            "category": "综合", "desc": f"复合压力指数单日跳升 {jump}（≥{EVENT_STRESS_JUMP}）",
            "indicator": "复合压力指数", "change_1d": jump,
            "latest_value": snap.get("composite_stress"),
        })
    return fired


def _stress_jump() -> int | None:
    if not STRESS_LOG.exists():
        return None
    rows = [r for r in STRESS_LOG.read_text().splitlines()[1:] if "," in r]
    if len(rows) < 2:
        return None
    try:
        prev = int(rows[-2].split(",")[1])
        cur = int(rows[-1].split(",")[1])
        return cur - prev
    except (ValueError, IndexError):
        return None


# ---------------------------------------------------------------------------
# 2. AI 新闻扫描
# ---------------------------------------------------------------------------
def _client():
    try:
        import anthropic
    except ImportError:
        log.warning("anthropic SDK 未安装，跳过 AI")
        return None
    key = (os.getenv("ANTHROPIC_API_KEY") or "").strip()
    if not key:
        log.info("ANTHROPIC_API_KEY 未设置，跳过 AI")
        return None
    return anthropic.Anthropic(api_key=key)


def _extract_json(text: str) -> dict | None:
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def ai_news_scan(client) -> dict:
    """返回 {found: bool, events: [{category, headline, summary, sources}]}。失败返回 found=False。"""
    if client is None:
        return {"found": False, "events": [], "skipped": True}
    prompt = (
        "你是全球债券市场监测分析师。请联网搜索过去约 18 小时内是否发生了"
        "下列任一类别的、对全球债券市场有实质性影响的事件：\n\n"
        f"{EVENT_TAXONOMY}\n\n"
        "只报告**确实发生**的重大事件（不要把例行数据、分析师观点、传闻当事件）。"
        "用 JSON 回答，格式：\n"
        '{"found": true/false, "events": [{"category":"A-F 中的类别",'
        '"headline":"一句话标题","summary":"2-3 句关键事实","sources":["url1","url2"]}]}\n'
        "若无重大事件，返回 {\"found\": false, \"events\": []}。只输出 JSON。"
    )
    try:
        resp = client.messages.create(
            model=SCAN_MODEL,
            max_tokens=2048,
            output_config={"effort": "low"},
            tools=[{"type": "web_search_20260209", "name": "web_search"}],
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as e:
        log.error("AI 新闻扫描失败: %s", e)
        return {"found": False, "events": [], "error": str(e)}
    text = "\n".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
    parsed = _extract_json(text)
    if not parsed:
        log.warning("AI 新闻扫描未返回可解析 JSON")
        return {"found": False, "events": []}
    parsed.setdefault("found", False)
    parsed.setdefault("events", [])
    log.info("AI 新闻扫描: found=%s, %d 事件", parsed["found"], len(parsed["events"]))
    return parsed


# ---------------------------------------------------------------------------
# 3. 深度后果分析
# ---------------------------------------------------------------------------
def _framework_context() -> str:
    parts = []
    for p in FRAMEWORK_DOCS:
        if p.exists():
            parts.append(f"\n\n===== {p.name} =====\n\n{p.read_text()}")
    return "".join(parts)


def _snapshot_brief(snap: dict) -> str:
    lines = [
        f"数据截至 {snap.get('as_of')}，复合压力指数 {snap.get('composite_stress')}/12"
        f"（{snap.get('stress_band')}）。关键指标：",
    ]
    for i in snap.get("indicators", []):
        v, u = i.get("latest_value"), i.get("unit", "")
        if v is None:
            continue
        lines.append(
            f"- {i['label']}: {v}{u}（1日Δ {i.get('change_1d')}, z {i.get('z_60d')}, "
            f"状态 {i.get('threshold_state')}）"
        )
    return "\n".join(lines)


def deep_analysis(client, snap: dict, triggers: list[dict], news: dict) -> str | None:
    if client is None:
        return None
    trig_txt = "\n".join(
        f"- [{t['category']}] {t['desc']}：{t['indicator']} 当前 {t['latest_value']}, 单日Δ {t['change_1d']}"
        for t in triggers
    ) or "（无数值触发，事件来自新闻扫描）"
    news_txt = json.dumps(news.get("events", []), ensure_ascii=False, indent=2)
    system = (
        "你是资深宏观与固定收益策略师，为一位有经验的投资者撰写**即时事件警报**（中文）。"
        "任务：基于下方触发信号、新闻事件、最新市场快照与参考框架，分析该事件可能引发的"
        "金融后果。要求：判断有据、引用具体数字、对标参考框架中的情景(A-E)与传导通道(1-6)、"
        "给出概率与时间窗口、给出可执行应对。\n\n"
        "输出为纯 HTML 片段，仅用 <h4><p><ul><li><b><i> 标签，按以下四节：\n"
        "<h4>事件认定</h4>（发生了什么、属哪一类、确信度）\n"
        "<h4>传导链路与受影响市场</h4>\n"
        "<h4>情景概率与时间窗口</h4>\n"
        "<h4>应对建议</h4>\n"
        "总字数 500-800 字。绝不编造数据。\n\n参考框架：" + _framework_context()
    )
    user = (
        f"## 数值触发信号\n{trig_txt}\n\n"
        f"## AI 新闻扫描发现\n{news_txt}\n\n"
        f"## 最新市场快照\n{_snapshot_brief(snap)}\n\n"
        "请输出事件警报 HTML 片段。"
    )
    try:
        resp = client.messages.create(
            model=ANALYSIS_MODEL,
            max_tokens=4096,
            thinking={"type": "adaptive"},
            output_config={"effort": "high"},
            system=[
                {"type": "text", "text": system,
                 "cache_control": {"type": "ephemeral", "ttl": "5m"}},
            ],
            messages=[{"role": "user", "content": user}],
        )
    except Exception as e:
        log.error("深度后果分析失败: %s", e)
        return None
    html = "\n".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip()
    u = resp.usage
    log.info(
        "深度分析完成: %d 字符 (in=%d cache_r=%d out=%d)",
        len(html), u.input_tokens,
        getattr(u, "cache_read_input_tokens", 0) or 0, u.output_tokens,
    )
    return html or None


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
def main() -> int:
    if not SNAPSHOT.exists():
        log.error("latest_snapshot.json 不存在，先运行 analyze.py")
        return 1
    snap = json.loads(SNAPSHOT.read_text())

    triggers = numeric_triggers(snap)
    log.info("数值触发器命中 %d 项", len(triggers))

    client = _client()
    news = ai_news_scan(client)

    detected = bool(triggers) or bool(news.get("found"))
    narrative = None
    if detected:
        log.warning("⚠ 检测到实质性事件 — 触发深度分析")
        narrative = deep_analysis(client, snap, triggers, news)
    else:
        log.info("未检测到实质性事件，本次不发警报")

    status = {
        "as_of": snap.get("as_of"),
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "detected": detected,
        "triggers": triggers,
        "news": news,
        "ai_narrative": narrative,
        "composite_stress": snap.get("composite_stress"),
        "stress_band": snap.get("stress_band"),
    }
    EVENT_STATUS.write_text(json.dumps(status, indent=2, default=str, ensure_ascii=False))
    log.info("已写入 event_status.json (detected=%s)", detected)
    return 0


if __name__ == "__main__":
    sys.exit(main())
