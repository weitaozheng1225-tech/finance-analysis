"""Indicator definitions, thresholds, annotations, and stress-index scoring rules.

Each indicator entry:
  source:    one of {"fred", "yahoo", "stooq", "coingecko", "mof"}
  id:        provider-specific identifier
  unit:      display unit
  label:     short label shown in tables
  group:     category for grouping in PDF reports
  notes:     full name + economic meaning, shown in PDF glossary
  warn/crisis/direction: optional thresholds for status flagging
  stress:    optional dict mapping value -> 0/1/2 contribution to composite index

Composite stress index (0-12) follows 01_scenario_analysis.md §5.
"""

from __future__ import annotations

INDICATORS: dict[str, dict] = {
    # =========================== US Treasuries ===========================
    "us_2y": {
        "source": "fred", "id": "DGS2", "unit": "%",
        "label": "US 2Y Treasury",
        "group": "US Treasuries",
        "notes": (
            "US 2-Year Treasury yield. Reflects market expectations of the Fed funds rate "
            "over the next 2 years; the front-end anchor and a key driver of curve shape."
        ),
    },
    "us_10y": {
        "source": "fred", "id": "DGS10", "unit": "%",
        "label": "US 10Y Treasury",
        "group": "US Treasuries",
        "notes": (
            "US 10-Year Treasury yield. The global risk-free benchmark; anchors mortgages, "
            "corporate borrowing costs, and cross-border rate markets."
        ),
    },
    "us_30y": {
        "source": "fred", "id": "DGS30", "unit": "%",
        "label": "US 30Y Treasury",
        "group": "US Treasuries",
        "notes": (
            "US 30-Year Treasury bond yield (the long bond). Most sensitive to inflation "
            "expectations, fiscal sustainability concerns, and structural demand from "
            "long-duration buyers (insurers, pensions, foreign reserve managers)."
        ),
    },
    "us_10y_term_premium": {
        "source": "fred", "id": "THREEFYTP10", "unit": "%",
        "label": "US 10Y term premium (ACM)",
        "group": "US Treasuries",
        "warn": 0.5, "crisis": 1.0, "direction": "above",
        "stress": {"low": 0.5, "high": 1.0},
        "notes": (
            "Adrian-Crump-Moench (ACM) model term premium on the 10Y, published by NY Fed. "
            "The compensation investors demand for holding long-duration risk beyond what "
            "expected short-rate paths can justify. Rising values indicate structural "
            "repricing of sovereign duration — often driven by fiscal concerns or "
            "weakening foreign demand."
        ),
    },
    # ========================= Funding & Liquidity =========================
    "sofr": {
        "source": "fred", "id": "SOFR", "unit": "%",
        "label": "SOFR",
        "group": "Funding & Liquidity",
        "notes": (
            "Secured Overnight Financing Rate. The post-LIBOR USD benchmark; reflects the "
            "true cost of overnight Treasury repo. Spikes (relative to IORB) flag dollar "
            "funding stress, as in the September 2019 repo blowup."
        ),
    },
    "iorb": {
        "source": "fred", "id": "IORB", "unit": "%",
        "label": "IORB",
        "group": "Funding & Liquidity",
        "notes": (
            "Interest on Reserve Balances. Rate the Fed pays banks on excess reserves; "
            "the de facto floor of the fed funds corridor and benchmark for SOFR."
        ),
    },
    "rrp_usage": {
        "source": "fred", "id": "RRPONTSYD", "unit": "$B",
        "label": "ON RRP usage",
        "group": "Funding & Liquidity",
        "notes": (
            "Overnight Reverse Repo Program take-up. Money-market funds park cash with "
            "the Fed when private-market yields are unattractive. A draining RRP signals "
            "cash flowing back into private repo and T-Bills; a swelling RRP signals "
            "excess liquidity with nowhere to go."
        ),
    },
    "tga_balance": {
        "source": "fred", "id": "WTREGEN", "unit": "$M",
        "label": "Treasury TGA balance",
        "group": "Funding & Liquidity",
        "notes": (
            "Treasury General Account balance at the Fed. The US Treasury's checking "
            "account. Drawdowns inject liquidity into the banking system; refills (e.g. "
            "post debt-ceiling deals) drain it. Key variable around X-date risk windows."
        ),
    },
    "fed_balance_sheet": {
        "source": "fred", "id": "WALCL", "unit": "$M",
        "label": "Fed total assets (H.4.1)",
        "group": "Funding & Liquidity",
        "notes": (
            "Total assets on the Fed's weekly H.4.1 balance sheet. Tracks QE expansion "
            "and QT runoff; the broadest single gauge of central bank liquidity supply."
        ),
    },
    # ============================= US Credit ===============================
    "ig_oas": {
        "source": "fred", "id": "BAMLC0A0CM", "unit": "%",
        "label": "US IG corporate OAS",
        "group": "US Credit",
        "warn": 1.30, "crisis": 1.80, "direction": "above",
        "notes": (
            "ICE BofA US Investment-Grade Corporate Index option-adjusted spread over "
            "Treasuries. The compensation for IG credit + liquidity risk. Widening signals "
            "rising default expectations and/or deteriorating bank balance sheets."
        ),
    },
    "hy_oas": {
        "source": "fred", "id": "BAMLH0A0HYM2", "unit": "%",
        "label": "US HY corporate OAS",
        "group": "US Credit",
        "warn": 4.50, "crisis": 7.00, "direction": "above",
        "notes": (
            "ICE BofA US High-Yield Corporate Index OAS. The 'risk gauge' of corporate "
            "credit. HY spreads typically lead equity drawdowns by days to weeks and are "
            "the cleanest read on leverage-system stress."
        ),
    },
    # ================================ FX ===================================
    "usdjpy": {
        "source": "fred", "id": "DEXJPUS", "unit": "JPY",
        "label": "USD/JPY",
        "group": "FX",
        "notes": (
            "USD/JPY spot. Captures the Fed-BOJ policy gap and the temperature of yen "
            "carry-trade positioning. A sharp drop (yen strength) signals carry-unwind "
            "and tends to precede global risk-off (e.g. Aug 2024)."
        ),
    },
    "gbpusd": {
        "source": "fred", "id": "DEXUSUK", "unit": "USD",
        "label": "GBP/USD",
        "group": "FX",
        "notes": (
            "GBP/USD spot. Key gauge of UK fiscal/political credibility; LDI-style stress "
            "(Sep 2022) typically shows here first as foreign holders dump gilts and "
            "convert proceeds back to home currency."
        ),
    },
    "dxy": {
        "source": "yahoo", "id": "DX-Y.NYB", "unit": "idx",
        "label": "DXY US Dollar Index",
        "group": "FX",
        "notes": (
            "ICE US Dollar Index. Trade-weighted USD vs a basket of major currencies. "
            "A rising DXY tightens global dollar liquidity and pressures EM/commodity "
            "complexes."
        ),
    },
    # ============================ Volatility ===============================
    "vix": {
        "source": "yahoo", "id": "^VIX", "unit": "idx",
        "label": "VIX (equity vol)",
        "group": "Volatility",
        "warn": 25, "crisis": 40, "direction": "above",
        "notes": (
            "CBOE Volatility Index. 30-day implied vol on S&P 500 options — the 'equity "
            "fear gauge'. Sustained levels above 25 = elevated risk; spikes above 40 "
            "historically coincide with macro shocks."
        ),
    },
    "move": {
        "source": "yahoo", "id": "^MOVE", "unit": "idx",
        "label": "MOVE (Treasury vol)",
        "group": "Volatility",
        "warn": 140, "crisis": 170, "direction": "above",
        "stress": {"low": 100, "high": 140},
        "notes": (
            "Merrill Option Volatility Estimate. The Treasury-market equivalent of VIX: "
            "implied vol weighted across 2/5/10/30Y options. The single most important "
            "rates-market stress gauge — spikes in MOVE precede most US fixed-income "
            "dislocations (LDI 2022, SVB 2023, basis-trade unwinds)."
        ),
    },
    # ============================== Equities ==============================
    "kre": {
        "source": "yahoo", "id": "KRE", "unit": "USD",
        "label": "KRE (regional banks)",
        "group": "Equities",
        "notes": (
            "SPDR S&P Regional Banking ETF. Most direct read on US regional bank stress "
            "— this cohort holds the largest unrealised losses on HTM Treasuries and is "
            "most exposed to a duration shock (SVB-style risk)."
        ),
    },
    "nikkei": {
        "source": "yahoo", "id": "^N225", "unit": "idx",
        "label": "Nikkei 225",
        "group": "Equities",
        "notes": (
            "Nikkei 225 Index. Tokyo's price-weighted blue-chip index; export-heavy "
            "composition makes it highly sensitive to USD/JPY and global growth. Sharp "
            "drops often signal carry-unwind underway (e.g. -12% on 5 Aug 2024)."
        ),
    },
    "topix_banks": {
        "source": "yahoo", "id": "1615.T", "unit": "JPY",
        "label": "TOPIX Banks (1615.T)",
        "group": "Equities",
        "notes": (
            "TOPIX Banks sector ETF. Japanese bank stocks reflect JGB capital pressure "
            "via NIM expansion (positive) and HTM unrealised losses (negative); a useful "
            "barometer of how Japanese banks are processing rising long-end yields."
        ),
    },
    "ftse100": {
        "source": "yahoo", "id": "^FTSE", "unit": "idx",
        "label": "FTSE 100",
        "group": "Equities",
        "notes": (
            "FTSE 100 Index. UK blue chips dominated by global commodity, financial, "
            "and pharma names; less reflective of UK domestic stress than FTSE 250."
        ),
    },
    # ====================== Safe Haven / Alternative ======================
    "gold": {
        "source": "yahoo", "id": "GC=F", "unit": "USD/oz",
        "label": "Gold (CME front)",
        "group": "Safe Haven / Alt",
        "notes": (
            "Gold front-month futures (COMEX). Classic hedge against sovereign credit "
            "risk, inflation, and currency debasement. Rising despite stable real rates "
            "is a clean signal of structural sovereign-risk repricing."
        ),
    },
    "btc": {
        "source": "coingecko", "id": "bitcoin", "unit": "USD",
        "label": "Bitcoin",
        "group": "Safe Haven / Alt",
        "notes": (
            "Bitcoin spot (USD). Alternative store-of-value; correlation regime shifts "
            "— at times tracks risk assets, at times tracks gold. Useful as a tail-hedge "
            "indicator when traditional safe havens are also under stress."
        ),
    },
    # ============================= Long Bonds =============================
    "tlt": {
        "source": "yahoo", "id": "TLT", "unit": "USD",
        "label": "TLT (US 20+Y bonds)",
        "group": "Long Bonds",
        "notes": (
            "iShares 20+ Year Treasury Bond ETF. Proxy for long-duration Treasury total "
            "return. Falling TLT = long-end yields rising; large drawdowns confirm "
            "structural repricing in the long bond."
        ),
    },
    "uk_gilt_etf": {
        "source": "yahoo", "id": "IGLT.L", "unit": "GBp",
        "label": "IGLT.L (UK gilts ETF)",
        "group": "Long Bonds",
        "notes": (
            "iShares Core UK Gilts UCITS ETF. Price-based UK gilt stress proxy used when "
            "direct gilt-yield feeds are unavailable. ETF duration is ~14 years, so each "
            "1% price drop corresponds to roughly a 7-8 bp yield rise across the curve. "
            "Used in lieu of UK 30Y yield in the composite stress index."
        ),
    },
    # ============================ Japan Yields ============================
    "jgb_10y": {
        "source": "mof", "id": "10", "unit": "%",
        "label": "JGB 10Y",
        "group": "Japan Yields",
        "warn": 1.75, "crisis": 2.25, "direction": "above",
        "notes": (
            "Japan 10-Year Government Bond yield. Long the BOJ's YCC target — rising "
            "values signal monetary normalisation, JGB demand erosion, and broader "
            "global liquidity tightening as Japanese institutions repatriate."
        ),
    },
    "jgb_30y": {
        "source": "mof", "id": "30", "unit": "%",
        "label": "JGB 30Y",
        "group": "Japan Yields",
        "warn": 2.50, "crisis": 3.00, "direction": "above",
        "notes": (
            "Japan 30-Year JGB yield. Highly sensitive to BOJ purchase pace and life-"
            "insurance ALM demand. The single most important non-US sovereign-rate "
            "signal: a 25 bp move here translates into hundreds of billions of USD of "
            "potential reallocation flow globally."
        ),
    },
    "jgb_40y": {
        "source": "mof", "id": "40", "unit": "%",
        "label": "JGB 40Y",
        "group": "Japan Yields",
        "warn": 2.75, "crisis": 3.25, "direction": "above",
        "notes": (
            "Japan 40-Year JGB yield. The longest tenor JGB issued; lowest liquidity, "
            "most volatile, often leads the JGB curve. Levels above 3% are historically "
            "rare and stress thin pension/insurance demand."
        ),
    },
}

# Display order of groups in PDF reports
GROUP_ORDER = [
    "US Treasuries",
    "Funding & Liquidity",
    "US Credit",
    "FX",
    "Volatility",
    "Equities",
    "Safe Haven / Alt",
    "Long Bonds",
    "Japan Yields",
]

# Composite stress index spec — see 01_scenario_analysis.md §5
STRESS_COMPONENTS = [
    {"name": "MOVE (Treasury vol)", "indicator": "move", "low": 100, "high": 140, "direction": "above"},
    {"name": "US 10Y term premium", "indicator": "us_10y_term_premium", "low": 0.5, "high": 1.0, "direction": "above"},
    {"name": "SOFR-IORB spread", "derived": "sofr_iorb_spread", "low": 0.05, "high": 0.10, "direction": "above"},
    {"name": "JGB 30Y yield", "indicator": "jgb_30y", "low": 2.5, "high": 3.0, "direction": "above"},
    {"name": "UK Gilt ETF 5d return", "derived": "uk_gilt_etf_5d_return", "low": -0.025, "high": -0.045, "direction": "below"},
    {"name": "KRE 1m return", "derived": "kre_1m_return", "low": -0.05, "high": -0.10, "direction": "below"},
]

# Anomaly detection — rolling z-score window and threshold
ROLLING_WINDOW_DAYS = 60
ANOMALY_Z_WARN = 2.0
ANOMALY_Z_CRISIS = 3.0

# Stress-index alert thresholds (out of 12)
STRESS_ALERT_WARN = 4
STRESS_ALERT_CRISIS = 7
