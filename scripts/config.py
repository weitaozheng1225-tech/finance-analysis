"""指标定义、阈值、注释与压力指数评分规则。

每个指标条目包含：
  source:    数据源 {"fred", "yahoo", "stooq", "coingecko", "mof"}
  id:        数据源对应的标识符
  unit:      展示单位
  label:     表格中的简短标签（中文）
  group:     PDF 报告中的分组名（中文）
  notes:     全称 + 经济学意义，用于 PDF 末页释义
  warn / crisis / direction: 状态阈值
  stress:    压力指数贡献映射

复合压力指数 (0-12) 算法见 01_scenario_analysis.md §5。
"""

from __future__ import annotations

INDICATORS: dict[str, dict] = {
    # ============================ 美国国债 ============================
    "us_2y": {
        "source": "fred", "id": "DGS2", "unit": "%",
        "label": "美国 2Y 国债",
        "group": "美国国债",
        "notes": (
            "美国 2 年期国债收益率。反映市场对未来 2 年联邦基金利率路径的预期，"
            "是收益率曲线前端的锚，与曲线形状（陡峭/平坦/倒挂）密切相关。"
        ),
    },
    "us_10y": {
        "source": "fred", "id": "DGS10", "unit": "%",
        "label": "美国 10Y 国债",
        "group": "美国国债",
        "notes": (
            "美国 10 年期国债收益率。全球无风险利率基准，是美国房贷、企业信用债"
            "以及跨境利率市场的定价之锚。"
        ),
    },
    "us_30y": {
        "source": "fred", "id": "DGS30", "unit": "%",
        "label": "美国 30Y 国债",
        "group": "美国国债",
        "notes": (
            "美国 30 年期长期国债收益率（长债）。对通胀预期、财政可持续性以及"
            "长久期需求（保险、养老金、海外储备管理者）最为敏感。"
        ),
    },
    "us_10y_term_premium": {
        "source": "fred", "id": "THREEFYTP10", "unit": "%",
        "label": "美国 10Y 期限溢价 (ACM)",
        "group": "美国国债",
        "warn": 0.5, "crisis": 1.0, "direction": "above",
        "stress": {"low": 0.5, "high": 1.0},
        "notes": (
            "NY Fed 发布的 ACM (Adrian-Crump-Moench) 模型 10Y 期限溢价。指投资者"
            "持有长久期所要求的、短端利率路径无法解释的额外补偿。该值上行通常"
            "意味着主权久期被重定价 —— 多由财政担忧或海外需求弱化驱动。"
        ),
    },
    # ======================== 资金面与流动性 ========================
    "sofr": {
        "source": "fred", "id": "SOFR", "unit": "%",
        "label": "SOFR 隔夜担保融资利率",
        "group": "资金面与流动性",
        "notes": (
            "Secured Overnight Financing Rate，LIBOR 退役后的美元基准利率，反映"
            "美债担保隔夜回购的真实成本。相对 IORB 飙升时（如 2019 年 9 月回购"
            "事件）即美元资金紧张信号。"
        ),
    },
    "iorb": {
        "source": "fred", "id": "IORB", "unit": "%",
        "label": "IORB 准备金利息",
        "group": "资金面与流动性",
        "notes": (
            "Interest on Reserve Balances，美联储对商业银行准备金支付的利率，是"
            "联邦基金利率走廊的事实下限，也是 SOFR 的参照基准。"
        ),
    },
    "rrp_usage": {
        "source": "fred", "id": "RRPONTSYD", "unit": "$B",
        "label": "隔夜逆回购规模 (ON RRP)",
        "group": "资金面与流动性",
        "notes": (
            "货币市场基金当私募市场收益率不具吸引力时将现金存入美联储 RRP。"
            "RRP 余额回落意味着资金回流私募回购与短端国债；RRP 膨胀则代表"
            "市场流动性过剩、无处可投。"
        ),
    },
    "tga_balance": {
        "source": "fred", "id": "WTREGEN", "unit": "$M",
        "label": "美国财政部一般账户 (TGA)",
        "group": "资金面与流动性",
        "notes": (
            "美国财政部在美联储的一般账户余额（即财政部支票账户）。账户耗用"
            "向银行体系注入流动性；账户补充（如债务上限协议达成后）则抽走流动性。"
            "是 X-date 风险窗口的关键变量。"
        ),
    },
    "fed_balance_sheet": {
        "source": "fred", "id": "WALCL", "unit": "$M",
        "label": "美联储总资产 (H.4.1)",
        "group": "资金面与流动性",
        "notes": (
            "美联储每周 H.4.1 资产负债表合计。直接刻画 QE 扩表与 QT 缩表节奏，"
            "是央行流动性供给的最综合单一指标。"
        ),
    },
    # ============================ 美国信用 ============================
    "ig_oas": {
        "source": "fred", "id": "BAMLC0A0CM", "unit": "%",
        "label": "美国 IG 企业债利差 (OAS)",
        "group": "美国信用",
        "warn": 1.30, "crisis": 1.80, "direction": "above",
        "notes": (
            "ICE BofA 美国投资级企业债指数相对美债的期权调整利差 (OAS)。代表"
            "投资级信用风险加流动性补偿，利差走阔提示违约预期上升或银行资产"
            "负债表恶化。"
        ),
    },
    "hy_oas": {
        "source": "fred", "id": "BAMLH0A0HYM2", "unit": "%",
        "label": "美国 HY 企业债利差 (OAS)",
        "group": "美国信用",
        "warn": 4.50, "crisis": 7.00, "direction": "above",
        "notes": (
            "ICE BofA 美国高收益企业债 OAS。企业信用市场的恐慌温度计，高收益"
            "利差通常领先股票回撤数日至数周，是杠杆系统压力最干净的读数。"
        ),
    },
    # ============================== 外汇 ==============================
    "usdjpy": {
        "source": "fred", "id": "DEXJPUS", "unit": "JPY",
        "label": "美元/日元",
        "group": "外汇",
        "notes": (
            "USD/JPY 即期汇率。反映 Fed-BOJ 政策利差及日元套息交易的温度。"
            "若快速回落（日元升值）即套息平仓信号，往往领先全球避险情绪"
            "（如 2024 年 8 月日股闪崩前）。"
        ),
    },
    "gbpusd": {
        "source": "fred", "id": "DEXUSUK", "unit": "USD",
        "label": "英镑/美元",
        "group": "外汇",
        "notes": (
            "GBP/USD 即期汇率。英国财政与政治信誉的重要标尺。LDI 式压力"
            "（如 2022 年 9 月）通常先在此显现，因海外持债人抛售英国国债"
            "并将本金兑回本币。"
        ),
    },
    "dxy": {
        "source": "yahoo", "id": "DX-Y.NYB", "unit": "idx",
        "label": "DXY 美元指数",
        "group": "外汇",
        "notes": (
            "ICE 美元指数。美元相对一篮子主要货币的贸易加权汇率。DXY 上行"
            "意味着全球美元流动性收紧，对新兴市场与大宗商品板块构成压力。"
        ),
    },
    # ============================ 波动率指数 ============================
    "vix": {
        "source": "yahoo", "id": "^VIX", "unit": "idx",
        "label": "VIX 股票波动率",
        "group": "波动率指数",
        "warn": 25, "crisis": 40, "direction": "above",
        "notes": (
            "CBOE 波动率指数。标普 500 期权未来 30 天隐含波动率，即股票恐慌"
            "指数。持续高于 25 = 风险升温；冲高 40+ 通常对应宏观冲击事件。"
        ),
    },
    "move": {
        "source": "yahoo", "id": "^MOVE", "unit": "idx",
        "label": "MOVE 国债波动率",
        "group": "波动率指数",
        "warn": 140, "crisis": 170, "direction": "above",
        "stress": {"low": 100, "high": 140},
        "notes": (
            "Merrill Option Volatility Estimate (MOVE)。美债市场版的 VIX，对"
            "2/5/10/30Y 国债期权隐含波动率加权。是利率市场最重要的单一压力"
            "指标 —— 几乎所有美国固收市场失序事件（2022 LDI、2023 SVB、"
            "基差交易解除）之前 MOVE 都会先飙升。"
        ),
    },
    # ============================ 股票市场 ============================
    "kre": {
        "source": "yahoo", "id": "KRE", "unit": "USD",
        "label": "KRE 美国区域银行 ETF",
        "group": "股票市场",
        "notes": (
            "SPDR S&P 区域银行 ETF。美国地区银行压力最直接的读数 —— 这类机构"
            "持有最大规模的 HTM 美债未实现亏损，对久期冲击最敏感（SVB 模板）。"
        ),
    },
    "nikkei": {
        "source": "yahoo", "id": "^N225", "unit": "idx",
        "label": "日经 225",
        "group": "股票市场",
        "notes": (
            "Nikkei 225 指数。东京市场价格加权蓝筹指数，出口型权重高使其对"
            "USD/JPY 与全球增长高度敏感。急跌通常提示套息交易解除已开始"
            "（如 2024-08-05 单日 -12%）。"
        ),
    },
    "topix_banks": {
        "source": "yahoo", "id": "1615.T", "unit": "JPY",
        "label": "TOPIX 银行 ETF (1615.T)",
        "group": "股票市场",
        "notes": (
            "TOPIX 银行业 ETF。日本银行股反映 JGB 端的资本压力：净息差扩大"
            "（正面）与 HTM 账户未实现亏损（负面）的合成。监测日本银行体系"
            "如何消化长端收益率上行的实时仪表。"
        ),
    },
    "ftse100": {
        "source": "yahoo", "id": "^FTSE", "unit": "idx",
        "label": "富时 100",
        "group": "股票市场",
        "notes": (
            "FTSE 100 指数。英国大盘，权重以全球商品、金融、医药为主，相比"
            "FTSE 250 较少反映英国本土压力。"
        ),
    },
    # ======================== 避险与另类资产 ========================
    "gold": {
        "source": "yahoo", "id": "GC=F", "unit": "USD/oz",
        "label": "黄金 (CME 主力)",
        "group": "避险与另类资产",
        "notes": (
            "COMEX 黄金主力月份期货。对主权信用、通胀、货币贬值的经典对冲。"
            "在实际利率稳定的背景下仍上涨，是主权风险被结构性重定价的清晰信号。"
        ),
    },
    "btc": {
        "source": "coingecko", "id": "bitcoin", "unit": "USD",
        "label": "比特币",
        "group": "避险与另类资产",
        "notes": (
            "比特币现货 (USD)。另类价值储存工具，相关性体制不稳定：有时跟随"
            "风险资产，有时跟随黄金。在传统避险资产也承压时，可作为尾部对冲"
            "信号观察。"
        ),
    },
    # =========================== 长债 ETF 代理 ===========================
    "tlt": {
        "source": "yahoo", "id": "TLT", "unit": "USD",
        "label": "TLT 美国 20+Y 国债 ETF",
        "group": "长债 ETF 代理",
        "notes": (
            "iShares 20+ 年美国国债 ETF。长久期美债总回报的代理。TLT 下跌"
            "= 长端收益率上行；大幅回撤可确认长债的结构性重定价。"
        ),
    },
    "uk_gilt_etf": {
        "source": "yahoo", "id": "IGLT.L", "unit": "GBp",
        "label": "IGLT.L 英国国债 ETF",
        "group": "长债 ETF 代理",
        "notes": (
            "iShares Core UK Gilts UCITS ETF。当直接的英国国债收益率数据源"
            "不可用时，用价格作为英国国债压力代理。ETF 久期约 14 年，价格"
            "每跌 1% 大致对应曲线上行 7-8bp。本压力指数中代替 UK 30Y。"
        ),
    },
    # ============================ 日本国债 ============================
    "jgb_10y": {
        "source": "mof", "id": "10", "unit": "%",
        "label": "日本 10Y 国债",
        "group": "日本国债",
        "warn": 1.75, "crisis": 2.25, "direction": "above",
        "notes": (
            "Japan 10Y JGB 收益率。长期是 BOJ YCC 政策的目标利率。上行预示"
            "货币政策正常化、JGB 需求侵蚀，以及随着日本机构回流而带来的"
            "全球流动性收紧。"
        ),
    },
    "jgb_30y": {
        "source": "mof", "id": "30", "unit": "%",
        "label": "日本 30Y 国债",
        "group": "日本国债",
        "warn": 2.50, "crisis": 3.00, "direction": "above",
        "notes": (
            "Japan 30Y JGB 收益率。对 BOJ 购债节奏与寿险 ALM 需求高度敏感。"
            "全球非美主权利率最重要的单一信号 —— 25bp 的变动对应日本机构"
            "持有的数千亿美元级别资产的潜在重新配置压力。"
        ),
    },
    "jgb_40y": {
        "source": "mof", "id": "40", "unit": "%",
        "label": "日本 40Y 国债",
        "group": "日本国债",
        "warn": 2.75, "crisis": 3.25, "direction": "above",
        "notes": (
            "Japan 40Y JGB 收益率。日本国债发行的最长期限，流动性最低、"
            "波动性最大，常领先整条 JGB 曲线。3% 以上的水平历史罕见，会"
            "明显压力薄弱的养老金 / 寿险需求。"
        ),
    },
    # ========================== 外汇与套息 ==========================
    "us_3m_tbill": {
        "source": "fred", "id": "DGS3MO", "unit": "%",
        "label": "美国 3M 国债利率",
        "group": "外汇与套息",
        "notes": (
            "美国 3 个月期国债到期收益率 (CMT)。USD 端短期无风险利率，"
            "也是 USD/JPY 锁汇成本（CIP 隐含）的核心分量。"
        ),
    },
    "jp_3m_tbill": {
        "source": "fred", "id": "IR3TIB01JPM156N", "unit": "%",
        "label": "日本 3M 银行间利率（月频）",
        "group": "外汇与套息",
        "notes": (
            "日本 3 个月银行间拆借利率（IR3TIB01JPM156N）。FRED 仅提供"
            "月频，本系统按月更新并前向填充到日频供派生指标使用。"
            "由 BOJ 政策利率直接驱动；BOJ 加息时该值同步上行，"
            "降低 USD/JPY 锁汇成本。"
        ),
    },
    "jpy_usd_hedge_cost": {
        "source": "derived", "id": "jpy_usd_hedge_cost", "unit": "%",
        "label": "USD/JPY 3M 锁汇成本（CIP 隐含）",
        "group": "外汇与套息",
        "warn": 4.0, "crisis": 5.0, "direction": "above",
        "notes": (
            "通过覆盖性利率平价 (CIP) 隐含的 3 个月 USD/JPY 锁汇成本，"
            "= 美 3M T-Bill 利率 − 日 3M 银行间利率。日本投资者持有 USD"
            "资产并用 3M 远期对冲汇率风险，每年需付出此比例的费用。"
            "判断：> 4% = 锁汇后美债吸引力大幅下降；> 5% = 结构性回流"
            "压力显著。"
            "注意：真实锁汇成本还含 30-80bp 的 USD/JPY 跨货币基差点 "
            "(xccy basis)，为付费数据；CIP 隐含值已捕捉 90%+ 的信号。"
        ),
    },
    "hedged_us_jgb_carry": {
        "source": "derived", "id": "hedged_us_jgb_carry", "unit": "%",
        "label": "锁汇后美 10Y − JGB 10Y 套息差",
        "group": "外汇与套息",
        "warn": -1.0, "crisis": -2.5, "direction": "below",
        "notes": (
            "日本投资者用 3M 远期全额锁汇 USD/JPY 后，持有美 10Y 国债"
            "相对持有 JGB 10Y 的实际超额收益。"
            "计算公式：(美 10Y − 锁汇成本) − JGB 10Y "
            "= 美 10Y − (美 3M − 日 3M) − JGB 10Y。"
            "为负 = 锁汇后美债 carry 低于 JGB，日本机构有结构性回流"
            "动机；深度为负（< −2.5%）= 寿险 / 大行已开始系统性减持美债。"
            "对应 04_japan_carry_unwind.md 通道 1（寿险回流）最直接的"
            "量化触发信号，也是 USDJPY 即期下行的领先指标。"
        ),
    },
}

# PDF 报告中分组的展示顺序
GROUP_ORDER = [
    "美国国债",
    "资金面与流动性",
    "美国信用",
    "外汇",
    "波动率指数",
    "股票市场",
    "避险与另类资产",
    "长债 ETF 代理",
    "日本国债",
    "外汇与套息",
]

# 复合压力指数构成 —— 详见 01_scenario_analysis.md §5
STRESS_COMPONENTS = [
    {"name": "MOVE 国债波动率", "indicator": "move", "low": 100, "high": 140, "direction": "above"},
    {"name": "美国 10Y 期限溢价", "indicator": "us_10y_term_premium", "low": 0.5, "high": 1.0, "direction": "above"},
    {"name": "SOFR - IORB 利差", "derived": "sofr_iorb_spread", "low": 0.05, "high": 0.10, "direction": "above"},
    {"name": "日本 30Y JGB 收益率", "indicator": "jgb_30y", "low": 2.5, "high": 3.0, "direction": "above"},
    {"name": "英国 Gilt ETF 5 日回报", "derived": "uk_gilt_etf_5d_return", "low": -0.025, "high": -0.045, "direction": "below"},
    {"name": "KRE 1 个月回报", "derived": "kre_1m_return", "low": -0.05, "high": -0.10, "direction": "below"},
]

# 异常检测 —— 滚动窗口与 z 分阈值
ROLLING_WINDOW_DAYS = 60
ANOMALY_Z_WARN = 2.0
ANOMALY_Z_CRISIS = 3.0

# 压力指数告警阈值（满分 12）
STRESS_ALERT_WARN = 4
STRESS_ALERT_CRISIS = 7
