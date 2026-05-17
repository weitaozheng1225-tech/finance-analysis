# 全球长债危机监测 · 2026-05-17

## 综合压力指数: **3 / 12** — 🟡 WATCH

## 🚨 异常 / 阈值告警

- SOFR: z=-2.60 (WARN)
- iShares 20+Y Treasury ETF: z=-2.19 (WARN)
- US 10Y ACM term premium: level=0.700 crosses WARN threshold
- Japan 10Y JGB yield: level=2.628 crosses CRISIS threshold
- Japan 30Y JGB yield: level=3.852 crosses CRISIS threshold
- Japan 40Y JGB yield: level=3.868 crosses CRISIS threshold

## 压力指数构成

| 维度 | 当前值 | 阈值 (low/high) | 得分 |
| --- | --- | --- | --- |
| MOVE | 79.870 | low=100, high=140, direction=above | **0** |
| US 10Y term premium | 0.700 | low=0.5, high=1.0, direction=above | **1** |
| SOFR-IORB | -0.090 | low=0.05, high=0.1, direction=above | **0** |
| JGB 30Y | 3.852 | low=2.5, high=3.0, direction=above | **2** |
| Gilt 30Y weekly change | — | low=0.3, high=0.5, direction=above | **0** |
| KRE 1m return | -0.027 | low=-0.05, high=-0.1, direction=below | **0** |

## 指标快照

| 指标 | 最新 | 日期 | 1d Δ | 5d Δ | 20d Δ | z (60d) | 状态 |
| --- | ---: | --- | ---: | ---: | ---: | ---: | :---: |
| US 2Y Treasury yield | 4.000 | 2026-05-14 | +0.020 | +0.080 | +0.220 | +1.52 | · |
| US 10Y Treasury yield | 4.470 | 2026-05-14 | +0.010 | +0.060 | +0.150 | +1.47 | · |
| US 30Y Treasury yield | 5.020 | 2026-05-14 | -0.010 | +0.050 | +0.090 | +1.45 | · |
| US 10Y ACM term premium | 0.700 | 2026-05-08 | -0.009 | -0.004 | +0.048 | +1.10 | ⚠ |
| SOFR | 3.560 | 2026-05-14 | -0.030 | -0.040 | -0.110 | -2.60 | · |
| IORB | 3.650 | 2026-05-18 | +0.000 | +0.000 | +0.000 | — | · |
| ON RRP usage | 0.647 | 2026-05-15 | -0.682 | -0.178 | +372.26% | -0.31 | · |
| Treasury General Account balance | 838584.000 | 2026-05-13 | -0.045 | +0.121 | +0.002 | +0.65 | · |
| Fed total assets (H.4.1) | 6728502.000 | 2026-05-13 | +0.003 | +0.005 | +0.022 | +1.58 | · |
| US IG corporate OAS | 0.760 | 2026-05-14 | +0.000 | -0.030 | -0.050 | -1.68 | · |
| US HY corporate OAS | 2.760 | 2026-05-14 | -0.060 | -0.030 | -0.100 | -1.34 | · |
| USD/JPY | 156.640 | 2026-05-08 | +0.001 | -0.001 | -0.016 | -0.79 | · |
| GBP/USD | 1.363 | 2026-05-08 | +0.001 | +0.000 | +0.012 | +1.54 | · |
| VIX equity vol index | 18.430 | 2026-05-15 | +0.068 | +0.072 | +0.054 | -0.78 | · |
| MOVE Treasury vol index | 79.870 | 2026-05-15 | +0.147 | +0.188 | +0.216 | +0.12 | · |
| Gold spot (CME front) | 4561.900 | 2026-05-15 | -0.025 | -0.034 | -0.061 | -0.98 | · |
| iShares 20+Y Treasury ETF | 83.660 | 2026-05-15 | -0.015 | -0.028 | -0.039 | -2.19 | · |
| Regional Banks ETF (KRE) | 66.970 | 2026-05-15 | -0.011 | -0.041 | -0.048 | -0.14 | · |
| DXY US Dollar Index | 99.270 | 2026-05-15 | +0.004 | +0.015 | +0.012 | +0.56 | · |
| Nikkei 225 | 61409.289 | 2026-05-15 | -0.020 | -0.021 | +0.087 | +1.42 | · |
| TOPIX Banks ETF (proxy) | 639.700 | 2026-05-15 | -0.000 | +0.027 | +0.024 | +1.01 | · |
| FTSE 100 | 10195.400 | 2026-05-15 | -0.017 | -0.004 | -0.037 | -0.86 | · |
| Bitcoin (USD) | 78103.032 | 2026-05-17 | -0.012 | -0.044 | -0.007 | +0.78 | · |
| Japan 10Y JGB yield | 2.628 | 2026-05-14 | +0.041 | +0.143 | — | — | 🔴 |
| Japan 30Y JGB yield | 3.852 | 2026-05-14 | +0.069 | +0.138 | — | — | 🔴 |
| Japan 40Y JGB yield | 3.868 | 2026-05-14 | +0.062 | +0.121 | — | — | 🔴 |
| UK 10Y Gilt yield | — | — | — | — | — | — | · |
| UK 30Y Gilt yield | — | — | — | — | — | — | · |
| iShares UK Gilts ETF (IGLT.L) — gilt price proxy | 9.627 | 2026-05-15 | -0.011 | -0.018 | -0.018 | -1.62 | · |

---

> 字段说明：yields/spreads 显示**水平差**(unit-level)；价格/指数显示**百分比**。
> 阈值与压力指数定义见 `01_scenario_analysis.md` §5 与 `02_observation_indicators.md`。
> 若需要深入分析或推演下一步影响，在 Claude Code 中调用 `bond-crisis-monitor` subagent。