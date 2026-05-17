"""Indicator definitions, thresholds, and stress-index scoring rules.

Each indicator entry:
  source:   one of {"fred", "yahoo", "treasury", "nyfed", "mof", "dmo", "coingecko"}
  id:       provider-specific identifier
  unit:     display unit
  warn:     warning threshold
  crisis:   crisis threshold
  direction:"above" -> larger is worse; "below" -> smaller is worse
  stress:   optional dict mapping value -> 0/1/2 contribution to composite index

Composite stress index (0-12) follows 01_scenario_analysis.md section 5.
"""

from __future__ import annotations

INDICATORS: dict[str, dict] = {
    # ---- Tier A: leading / daily ----
    "us_2y": {
        "source": "fred", "id": "DGS2", "unit": "%",
        "label": "US 2Y Treasury yield",
    },
    "us_10y": {
        "source": "fred", "id": "DGS10", "unit": "%",
        "label": "US 10Y Treasury yield",
    },
    "us_30y": {
        "source": "fred", "id": "DGS30", "unit": "%",
        "label": "US 30Y Treasury yield",
    },
    "us_10y_term_premium": {
        "source": "fred", "id": "THREEFYTP10", "unit": "%",
        "label": "US 10Y ACM term premium",
        "warn": 0.5, "crisis": 1.0, "direction": "above",
        "stress": {"low": 0.5, "high": 1.0},
    },
    "sofr": {
        "source": "fred", "id": "SOFR", "unit": "%",
        "label": "SOFR",
    },
    "iorb": {
        "source": "fred", "id": "IORB", "unit": "%",
        "label": "IORB",
    },
    "rrp_usage": {
        "source": "fred", "id": "RRPONTSYD", "unit": "$B",
        "label": "ON RRP usage",
    },
    "tga_balance": {
        "source": "fred", "id": "WTREGEN", "unit": "$B",
        "label": "Treasury General Account balance",
    },
    "fed_balance_sheet": {
        "source": "fred", "id": "WALCL", "unit": "$M",
        "label": "Fed total assets (H.4.1)",
    },
    "ig_oas": {
        "source": "fred", "id": "BAMLC0A0CM", "unit": "bp",
        "label": "US IG corporate OAS",
        "warn": 1.30, "crisis": 1.80, "direction": "above",
    },
    "hy_oas": {
        "source": "fred", "id": "BAMLH0A0HYM2", "unit": "bp",
        "label": "US HY corporate OAS",
        "warn": 4.50, "crisis": 7.00, "direction": "above",
    },
    "usdjpy": {
        "source": "fred", "id": "DEXJPUS", "unit": "JPY",
        "label": "USD/JPY",
    },
    "gbpusd": {
        "source": "fred", "id": "DEXUSUK", "unit": "USD",
        "label": "GBP/USD",
    },
    # ---- Tier B: market-implied / equity ----
    "vix": {
        "source": "yahoo", "id": "^VIX", "unit": "idx",
        "label": "VIX equity vol index",
        "warn": 25, "crisis": 40, "direction": "above",
    },
    "move": {
        "source": "yahoo", "id": "^MOVE", "unit": "idx",
        "label": "MOVE Treasury vol index",
        "warn": 140, "crisis": 170, "direction": "above",
        "stress": {"low": 100, "high": 140},
    },
    "gold": {
        "source": "yahoo", "id": "GC=F", "unit": "USD/oz",
        "label": "Gold spot (CME front)",
    },
    "tlt": {
        "source": "yahoo", "id": "TLT", "unit": "USD",
        "label": "iShares 20+Y Treasury ETF",
    },
    "kre": {
        "source": "yahoo", "id": "KRE", "unit": "USD",
        "label": "Regional Banks ETF (KRE)",
        # tracked as 1m return; threshold applied in analyze.py
    },
    "dxy": {
        "source": "yahoo", "id": "DX-Y.NYB", "unit": "idx",
        "label": "DXY US Dollar Index",
    },
    "nikkei": {
        "source": "yahoo", "id": "^N225", "unit": "idx",
        "label": "Nikkei 225",
    },
    "topix_banks": {
        "source": "yahoo", "id": "1615.T", "unit": "JPY",
        "label": "TOPIX Banks ETF (proxy)",
    },
    "ftse100": {
        "source": "yahoo", "id": "^FTSE", "unit": "idx",
        "label": "FTSE 100",
    },
    # ---- Tier C: crypto / alt store-of-value ----
    "btc": {
        "source": "coingecko", "id": "bitcoin", "unit": "USD",
        "label": "Bitcoin (USD)",
    },
    # ---- Tier D: sovereign-specific (Japan / UK gilts) ----
    "jgb_10y": {
        "source": "mof", "id": "10", "unit": "%",
        "label": "Japan 10Y JGB yield",
        "warn": 1.75, "crisis": 2.25, "direction": "above",
    },
    "jgb_30y": {
        "source": "mof", "id": "30", "unit": "%",
        "label": "Japan 30Y JGB yield",
        "warn": 2.50, "crisis": 3.00, "direction": "above",
    },
    "jgb_40y": {
        "source": "mof", "id": "40", "unit": "%",
        "label": "Japan 40Y JGB yield",
        "warn": 2.75, "crisis": 3.25, "direction": "above",
    },
    # UK gilt yields: Stooq's free CSV blocks GitHub Actions IP ranges (apikey required).
    # We use the iShares UK Gilts ETF as a price-based stress proxy instead;
    # IGLT.L has duration ~14y so a ~4% price drop ≈ a 30bp yield rise.
    "uk_gilt_etf": {
        "source": "yahoo", "id": "IGLT.L", "unit": "GBp",
        "label": "iShares UK Gilts ETF (IGLT.L) — gilt price proxy",
    },
}

# Composite stress index spec — see 01_scenario_analysis.md §5
STRESS_COMPONENTS = [
    {"name": "MOVE", "indicator": "move", "low": 100, "high": 140, "direction": "above"},
    {"name": "US 10Y term premium", "indicator": "us_10y_term_premium", "low": 0.5, "high": 1.0, "direction": "above"},
    {"name": "SOFR-IORB", "derived": "sofr_iorb_spread", "low": 0.05, "high": 0.10, "direction": "above"},
    {"name": "JGB 30Y", "indicator": "jgb_30y", "low": 2.5, "high": 3.0, "direction": "above"},
    # UK Gilt ETF 5d return (IGLT.L; duration ~14, so -4% ≈ +30bp yield):
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
