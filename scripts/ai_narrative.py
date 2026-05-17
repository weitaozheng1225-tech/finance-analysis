"""调用 Claude 为周报生成叙事性深度解读，写回 data/weekly_snapshot.json。

需要环境变量 ANTHROPIC_API_KEY。如果未设置，静默跳过 —— 周报会照常出，
只是不含 AI 叙事段落。

设计要点：
- 模型：claude-opus-4-7（最深度分析能力）
- 自适应思考：让模型决定推理深度，不需调 budget_tokens
- effort: high —— 智能敏感型任务的最低推荐档位
- Prompt 缓存：把 5 份框架文档（01-05.md）作为缓存的系统前缀；ttl=5m，
  适配开发期反复测试与一次性周报触发的混合场景。生产周报一周一次时，
  缓存基本会过期，1.25x 写入成本是可接受的小溢价。
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEEKLY = ROOT / "data" / "weekly_snapshot.json"

# 五份框架文档作为推理依据
FRAMEWORK_DOCS = [
    ROOT / "01_scenario_analysis.md",
    ROOT / "02_observation_indicators.md",
    ROOT / "03_us_default_deep_dive.md",
    ROOT / "04_japan_carry_unwind.md",
    ROOT / "05_uk_gilt_ldi_risk.md",
]

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s")
log = logging.getLogger("ai")


SYSTEM_PREAMBLE = """你是一位资深宏观研究分析师，专注于全球主权债券市场与系统性金融风险。

任务：为每周一份的"全球长债危机监测"报告撰写**叙事性深度解读段落**（中文）。

读者画像：有经验的投资者，已经看过本周的所有指标数据与情景概率表。
他们需要的不是数据复述，而是**带判断力的解读 + 可操作的下周观察重点**。

写作约束：

1. **全中文写作**，专业但简练。避免对仗工整的废话与无信息量的形容词。

2. **结构固定**：四段，每段以 `<h4>` 标题开头：
   - `<h4>本周关键变化</h4>` —— 最重要的 2-3 项变化及其含义
   - `<h4>市场所处状态判断</h4>` —— 当前落在哪个情景（A/B/C/D/E），为何，
     哪条传导通道（通道 1-6）在激活
   - `<h4>下周 1-2 周观察重点</h4>` —— 3 个具体的临界值与触发器
   - `<h4>行动建议</h4>` —— 2-3 条对仓位的可执行建议

3. **必须引用具体指标值**：每个论断都要带数字。不要说"波动率上升"，
   要说"MOVE 从 X 升至 Y（z=+1.2）"。

4. **必须对标参考框架**：使用"情景 A-E"、"通道 1-6"等术语，与
   `01_scenario_analysis.md` 等文档保持一致。

5. **输出格式**：纯 HTML 片段，只使用 `<h4>`、`<p>`、`<ul>`、`<li>`、
   `<b>`、`<i>` 标签。不要 `<html>`/`<body>` 包裹，不要 markdown 语法，
   不要代码块。直接输出可嵌入到现有 HTML 文档中的片段。

6. **绝不编造数据**：所有引用的数字必须来自给定的快照。如某指标值为
   None 或 "—"（数据缺失），不要在分析中使用该指标。

7. **总字数控制在 600-900 字**之间。

下面是分析所依据的参考框架文档（5 份 .md，依序拼接）："""


def _load_framework_context() -> str:
    parts: list[str] = []
    for p in FRAMEWORK_DOCS:
        if p.exists():
            parts.append(f"\n\n===== {p.name} =====\n\n{p.read_text()}")
        else:
            log.warning("framework doc missing: %s", p.name)
    return "".join(parts)


def _fmt(v) -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:.4f}"
    return str(v)


def _snapshot_summary(snap: dict) -> str:
    """把 weekly snapshot 压成 Claude 输入用的 markdown 摘要。"""
    lines = [
        f"# 本周快照（截至 {snap['as_of']}）\n",
        f"- 综合压力指数：**{snap['today_stress']}/12**（等级：{snap['today_band']}）",
        f"- 过去 14 个交易日压力分序列：{[h['stress'] for h in snap.get('stress_history', [])]}",
        "",
        "## 当前异常",
    ]
    if snap.get("anomalies"):
        for a in snap["anomalies"]:
            lines.append(f"- {a}")
    else:
        lines.append("- 无")

    lines += ["", "## 压力指数构成"]
    for c in snap.get("components", []):
        lines.append(
            f"- {c['name']}：值={_fmt(c.get('value'))}，"
            f"得分 {c['points']}/2（阈值 {c['detail']}）"
        )

    lines += ["", "## 涨幅最大（5 日）"]
    for ind in snap.get("top_movers_up", [])[:5]:
        lines.append(
            f"- {ind['label']}（{ind.get('group','')}）："
            f"最新 {_fmt(ind.get('latest_value'))} {ind.get('unit','')}，"
            f"1日Δ={_fmt(ind.get('change_1d'))}，5日Δ={_fmt(ind.get('change_5d'))}，"
            f"20日Δ={_fmt(ind.get('change_20d'))}，z(60d)={_fmt(ind.get('z_60d'))}，"
            f"状态={ind.get('threshold_state')}"
        )

    lines += ["", "## 跌幅最大（5 日）"]
    for ind in snap.get("top_movers_down", [])[:5]:
        lines.append(
            f"- {ind['label']}（{ind.get('group','')}）："
            f"最新 {_fmt(ind.get('latest_value'))} {ind.get('unit','')}，"
            f"1日Δ={_fmt(ind.get('change_1d'))}，5日Δ={_fmt(ind.get('change_5d'))}，"
            f"20日Δ={_fmt(ind.get('change_20d'))}，z(60d)={_fmt(ind.get('z_60d'))}，"
            f"状态={ind.get('threshold_state')}"
        )

    lines += ["", "## 情景概率（本周已调整）"]
    for s in snap.get("scenarios", []):
        lines.append(f"- {s['name']}：{s['low']}%-{s['high']}%")
    if snap.get("scenario_notes"):
        lines += ["", "## 本周触发的概率调整理由"]
        for n in snap["scenario_notes"]:
            lines.append(f"- {n}")

    lines += ["", "## 全指标快照（按 group 排列）"]
    by_group: dict[str, list] = {}
    for ind in snap.get("indicators", []):
        by_group.setdefault(ind.get("group") or "其它", []).append(ind)
    for group, items in by_group.items():
        lines.append(f"\n### {group}")
        for ind in items:
            lines.append(
                f"- {ind['label']}：最新 {_fmt(ind.get('latest_value'))} {ind.get('unit','')}，"
                f"1日Δ={_fmt(ind.get('change_1d'))}，5日Δ={_fmt(ind.get('change_5d'))}，"
                f"20日Δ={_fmt(ind.get('change_20d'))}，z={_fmt(ind.get('z_60d'))}，"
                f"状态={ind.get('threshold_state')}"
            )

    lines += [
        "",
        "---",
        "",
        "请按上面定义的四段结构，针对**本周这份快照**撰写中文叙事性深度解读 HTML 片段。",
    ]
    return "\n".join(lines)


def generate_narrative(snap: dict) -> str | None:
    try:
        import anthropic
    except ImportError:
        log.warning("anthropic SDK 未安装，跳过 AI narrative")
        return None

    api_key = (os.getenv("ANTHROPIC_API_KEY") or "").strip()
    if not api_key:
        log.info("ANTHROPIC_API_KEY 未设置，跳过 AI narrative")
        return None

    client = anthropic.Anthropic(api_key=api_key)
    framework = _load_framework_context()
    if not framework:
        log.warning("框架文档全部缺失，跳过 AI narrative")
        return None

    user_msg = _snapshot_summary(snap)

    try:
        response = client.messages.create(
            model="claude-opus-4-7",
            max_tokens=4096,
            thinking={"type": "adaptive"},
            output_config={"effort": "high"},
            system=[
                {"type": "text", "text": SYSTEM_PREAMBLE},
                {
                    "type": "text",
                    "text": framework,
                    "cache_control": {"type": "ephemeral", "ttl": "5m"},
                },
            ],
            messages=[{"role": "user", "content": user_msg}],
        )
    except anthropic.APIStatusError as e:
        log.error("Claude API 状态错误 (%s): %s", e.status_code, e.message)
        return None
    except Exception as e:
        log.error("Claude API 调用失败: %s", e)
        return None

    # 拿出 text 块（过滤 thinking 块）
    narrative = "\n".join(b.text for b in response.content if b.type == "text").strip()

    if response.stop_reason == "refusal":
        log.error("Claude 拒绝生成 (refusal): %s", response.stop_details)
        return None

    usage = response.usage
    log.info(
        "AI narrative 生成完成: %d 字符；token usage: "
        "input=%d, cache_creation=%d, cache_read=%d, output=%d",
        len(narrative),
        usage.input_tokens,
        getattr(usage, "cache_creation_input_tokens", 0) or 0,
        getattr(usage, "cache_read_input_tokens", 0) or 0,
        usage.output_tokens,
    )
    return narrative


def main() -> int:
    if not WEEKLY.exists():
        log.error("weekly_snapshot.json 不存在 —— 先运行 weekly_report.py")
        return 1
    snap = json.loads(WEEKLY.read_text())
    narrative = generate_narrative(snap)
    if narrative:
        snap["ai_narrative"] = narrative
        WEEKLY.write_text(
            json.dumps(snap, indent=2, default=str, ensure_ascii=False)
        )
        log.info("已写入 weekly_snapshot.json 的 ai_narrative 字段")
    else:
        log.info("无 AI narrative 写入；PDF 将不包含该段落")
    return 0


if __name__ == "__main__":
    sys.exit(main())
