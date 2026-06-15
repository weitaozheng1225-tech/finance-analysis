# 全球长债利率压力与金融危机监测

> 分析日期基准：2026-05
> 关注主线：日本 / 美国 / 英国长端利率突破近期新高，向系统性金融风险传导的路径、阈值、概率

## 仓库结构

```
finance-analysis/
├── README.md                        本文件
├── 01_scenario_analysis.md          危机推演：四档情景 + 复合压力指数定义
├── 02_observation_indicators.md     观察指标库：阈值 + 数据源 + 频率
├── 03_us_default_deep_dive.md       美债违约专题
├── 04_japan_carry_unwind.md         日本因素专题
├── 05_uk_gilt_ldi_risk.md           英国因素专题
│
├── scripts/                         每日数据流水线 (Python)
│   ├── requirements.txt
│   ├── config.py                    指标 / 阈值 / 压力指数定义
│   ├── fetch_daily.py               从公开 API 抓取所有指标
│   ├── analyze.py                   压力指数 + 异常检测
│   ├── report.py                    生成 Markdown 报告
│   └── notify.py                    邮件 + Webhook 告警
│
├── .github/workflows/
│   └── daily-monitor.yml            每日 06:30 UTC 自动跑
│
├── .claude/agents/
│   └── bond-crisis-monitor.md       Claude 子代理：深度推演 + 网络研究
│
├── data/
│   ├── timeseries/                  per-indicator CSV (自动生长)
│   ├── latest_snapshot.json         今日聚合 + 压力指数
│   └── last_fetch.txt               抓取摘要
│
└── reports/
    ├── daily/YYYY-MM-DD.md          每日机器生成报告
    ├── daily/latest.md              软链接到最新一份
    └── deep/YYYY-MM-DD.md           子代理生成的深度推演
```

---

## 发送逻辑（用户只收两类邮件）

```
  每日两次 (07:00 UTC 亚收 / 22:00 UTC 美收)
  ┌────────────────────────────────────────────────────────┐
  │ 事件监测: fetch → analyze → 事件检测                     │
  │   • 数值触发器: 单日事件级异动 (USDJPY±2%, JGB+15bp,     │
  │     MOVE+20, KRE-5%, 黄金±3%, 压力指数日跳≥3 …)          │
  │   • AI 新闻扫描: 联网按事件分类(A-F)排查过去 ~18h         │
  │   ⇒ 任一命中 → Opus 4.7 结合当下环境做后果分析            │
  │   ⇒ 仅在检测到事件时发"⚠即时事件警报"邮件(否则静默)       │
  └────────────────────────────────────────────────────────┘

  每周六 21:00 北京 (13:00 UTC)
  ┌────────────────────────────────────────────────────────┐
  │ 周深度报告: 14 日趋势 + Top movers + 情景概率 + AI 叙事   │
  │   ⇒ 始终发送 (这是常规接收的唯一定期报告)                 │
  └────────────────────────────────────────────────────────┘

  按需 (在 Claude Code 调 bond-crisis-monitor subagent)
  ┌────────────────────────────────────────────────────────┐
  │ 深度推演: 读 snapshot + web research + 情景推演           │
  └────────────────────────────────────────────────────────┘
```

> 设计要点：**不再有常规每日邮件**。日常跑只更新数据(供周报积累历史)，
> 只有当天发生对全球债市有实质性影响的事件时才发即时警报。
> 事件分类清单(穷举)见 `scripts/config.py` 的 `EVENT_TAXONOMY`；
> 数值触发阈值见 `EVENT_TRIGGERS`。

---

## 数据源（全部免费公开）

| 来源 | 用途 | 是否需要 key |
|------|------|--------------|
| FRED (St. Louis Fed) | UST 收益率、SOFR/IORB、TGA、RRP、信用利差、FX | ✅ 免费 key |
| Yahoo Finance (yfinance) | VIX、MOVE、Gold、TLT、KRE、DXY、Nikkei、FTSE | ❌ |
| CoinGecko | BTC | ❌ |
| 日本财务省 MoF (CSV) | JGB 各期限收益率 | ❌ |
| Bank of England (XLSX) | UK 名义 Gilt 收益率曲线 | ❌ |

---

## 一次性配置（在 GitHub 仓库 Settings → Secrets/Variables）

### Secrets（必须）
| 名称 | 说明 | 获取 |
|------|------|------|
| `FRED_API_KEY` | FRED 免费 API key | https://fredaccount.stlouisfed.org/apikeys |

### Secrets（按需配置告警渠道）
| 名称 | 说明 |
|------|------|
| `SMTP_HOST` | 例：smtp.gmail.com / smtp.qq.com |
| `SMTP_PORT` | 通常 587 |
| `SMTP_USER` | 邮箱账号 |
| `SMTP_PASS` | 邮箱密码或应用专用密码 |
| `EMAIL_FROM` | 发件人 |
| `EMAIL_TO` | 收件人，多个用逗号分隔 |
| `WEBHOOK_URL` | Slack/Discord/飞书/钉钉 incoming webhook |

### Secrets（可选：周报 AI 叙事段落）
| 名称 | 说明 |
|------|------|
| `ANTHROPIC_API_KEY` | 申请：https://console.anthropic.com/settings/keys。配置后：(1) 周报 PDF 含 Opus 4.7 中文叙事段落；(2) 事件监测每次跑会做 AI 联网新闻扫描，检测到事件时生成后果分析。未配置则跳过 AI——周报照常出，事件监测退化为纯数值触发。AI 成本：周报约 $0.05-0.10/次；事件扫描约 $0.05-0.15/次 × 每日 2 次。|

### Variables（可选）
| 名称 | 默认 | 说明 |
|------|------|------|
| `EVENT_SCAN_MODEL` | `claude-opus-4-7` | 事件新闻扫描模型。可设 `claude-sonnet-4-6` 降本约 40%。|
| `EVENT_ANALYSIS_MODEL` | `claude-opus-4-7` | 事件后果分析模型。|
| `ALERT_MIN_BAND` | `warn` | （已弃用）旧的每日压力告警阈值；现日报改为事件驱动，此变量不再影响发送。|

---

## 本地一次性手动跑（验证流水线）

```bash
cd scripts
pip install -r requirements.txt
export FRED_API_KEY=xxxxxxxxxxxxxxxxx
python fetch_daily.py      # 第一次会慢一些，下载 3 年历史
python analyze.py
python report.py
cat ../reports/daily/latest.md
```

---

## 调用 Claude 子代理做深度推演

在本仓库目录下打开 Claude Code，对它说：

```
用 bond-crisis-monitor subagent 分析今天的报告
```

它会：
1. 读 `data/latest_snapshot.json` 和 `reports/daily/latest.md`
2. 对 top-3 异常用 WebSearch / WebFetch 找当天新闻
3. 对照 01-05 号框架文档判断当前所处的情景与传导通道
4. 生成 `reports/deep/YYYY-MM-DD.md`，结构：当前定位 / 危机概率推演 / 下一步可能结果

---

## 核心论点（执行摘要）

1. **三国长端同步上行的本质不是周期问题，而是"主权信用 + 期限溢价 + 边际买家"的结构性重定价**。
2. **最高概率的危机形态不是美债违约**，而是 *流动性事件*（类似 2019/9 回购、2020/3 美债"dash for cash"、2022/9 英国 LDI）。
3. **美债技术性违约（X-date 失误）概率显著高于实质性违约**，前者 ~5%，后者 < 1%。
4. **最先发出系统性信号的不是收益率本身**，而是 MOVE、SOFR-IORB、跨境基差、拍卖尾差、一级交易商持仓。
5. **日本因素是被低估的全球流动性变量**：JGB 30Y/40Y 收益率每上行 25bp，对应日本机构数千亿美元级别的潜在回流压力。
