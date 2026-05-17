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

## 三层架构

```
                ┌──────────────────────────────────────┐
                │  Layer 1: 数据流水线 (GitHub Actions)  │
                │  每日 06:30 UTC, fetch → analyze →    │
                │  report → notify (email/webhook)     │
                └──────────────────────────────────────┘
                                  │
                                  ▼
                ┌──────────────────────────────────────┐
                │  Layer 2: 告警 (邮件 / Webhook)        │
                │  压力指数 ≥ 4 或单指标进入 warn/crisis  │
                │  即触发                                │
                └──────────────────────────────────────┘
                                  │
                                  ▼
                ┌──────────────────────────────────────┐
                │  Layer 3: 深度推演 (Claude subagent)   │
                │  收到告警后用 bond-crisis-monitor      │
                │  子代理做 web research + 情景推演      │
                └──────────────────────────────────────┘
```

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

### Variables（可选）
| 名称 | 默认 | 说明 |
|------|------|------|
| `ALERT_MIN_BAND` | `warn` | `watch` / `warn` / `crisis` — 触发告警的最低压力级别 |

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
