"""Compute composite stress index and detect anomalies from per-indicator CSVs."""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data" / "timeseries"
OUT_DIR = ROOT / "data"
sys.path.insert(0, str(ROOT / "scripts"))
from config import (  # noqa: E402
    ANOMALY_Z_CRISIS,
    ANOMALY_Z_WARN,
    DEFAULT_MAX_STALENESS_DAYS,
    INDICATORS,
    ROLLING_WINDOW_DAYS,
    STALENESS_OVERRIDES,
    STRESS_ALERT_CRISIS,
    STRESS_ALERT_WARN,
    STRESS_COMPONENTS,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s")
log = logging.getLogger("analyze")


@dataclass
class IndicatorReading:
    name: str
    label: str
    latest_value: float | None
    latest_date: str | None
    change_1d: float | None
    change_5d: float | None
    change_20d: float | None
    z_60d: float | None
    threshold_state: str  # "ok" | "warn" | "crisis"
    group: str = ""
    unit: str = ""
    notes: str = ""
    staleness_days: int | None = None
    is_stale: bool = False


@dataclass
class StressComponent:
    name: str
    value: float | None
    points: int  # 0, 1, or 2
    detail: str


@dataclass
class DailySnapshot:
    as_of: str
    composite_stress: int
    stress_band: str  # "ok" | "watch" | "warn" | "crisis"
    components: list[StressComponent]
    indicators: list[IndicatorReading]
    anomalies: list[str]


def _load_series(name: str) -> pd.Series:
    p = DATA_DIR / f"{name}.csv"
    if not p.exists():
        return pd.Series(dtype=float)
    df = pd.read_csv(p, parse_dates=["date"])
    return df.set_index("date")["value"].sort_index()


def _pct_change(s: pd.Series, n: int) -> float | None:
    if len(s) <= n:
        return None
    prev = s.iloc[-(n + 1)]
    if prev == 0 or pd.isna(prev):
        return None
    return float((s.iloc[-1] - prev) / abs(prev))


def _level_change(s: pd.Series, n: int) -> float | None:
    if len(s) <= n:
        return None
    return float(s.iloc[-1] - s.iloc[-(n + 1)])


def _z_score(s: pd.Series, window: int = ROLLING_WINDOW_DAYS) -> float | None:
    if len(s) < window:
        return None
    tail = s.iloc[-window:]
    sigma = tail.std()
    if sigma == 0 or pd.isna(sigma):
        return None
    return float((s.iloc[-1] - tail.mean()) / sigma)


def _threshold_state(name: str, value: float | None) -> str:
    cfg = INDICATORS.get(name, {})
    if value is None or "warn" not in cfg or "crisis" not in cfg:
        return "ok"
    direction = cfg.get("direction", "above")
    warn, crisis = cfg["warn"], cfg["crisis"]
    if direction == "above":
        if value >= crisis:
            return "crisis"
        if value >= warn:
            return "warn"
    else:
        if value <= crisis:
            return "crisis"
        if value <= warn:
            return "warn"
    return "ok"


def _staleness_budget(name: str) -> int:
    cfg = INDICATORS.get(name, {})
    if "max_staleness_days" in cfg:
        return int(cfg["max_staleness_days"])
    if name in STALENESS_OVERRIDES:
        return int(STALENESS_OVERRIDES[name])
    return DEFAULT_MAX_STALENESS_DAYS


def _read_indicator(name: str) -> IndicatorReading:
    cfg = INDICATORS[name]
    s = _load_series(name)
    group = cfg.get("group", "")
    unit = cfg.get("unit", "")
    notes = cfg.get("notes", "")
    if s.empty:
        return IndicatorReading(
            name=name, label=cfg["label"],
            latest_value=None, latest_date=None,
            change_1d=None, change_5d=None, change_20d=None,
            z_60d=None, threshold_state="ok",
            group=group, unit=unit, notes=notes + " (no data this run)",
            staleness_days=None, is_stale=True,
        )
    val = float(s.iloc[-1])
    # Use level changes for yields and spreads (units: %, bp); pct for prices/indices.
    if unit in {"%", "bp"}:
        c1, c5, c20 = _level_change(s, 1), _level_change(s, 5), _level_change(s, 20)
    else:
        c1, c5, c20 = _pct_change(s, 1), _pct_change(s, 5), _pct_change(s, 20)
    latest_dt = s.index[-1].date()
    staleness = (date.today() - latest_dt).days
    is_stale = staleness > _staleness_budget(name)
    return IndicatorReading(
        name=name, label=cfg["label"],
        latest_value=val,
        latest_date=latest_dt.isoformat(),
        change_1d=c1, change_5d=c5, change_20d=c20,
        z_60d=_z_score(s),
        threshold_state=_threshold_state(name, val),
        group=group, unit=unit, notes=notes,
        staleness_days=staleness, is_stale=is_stale,
    )


# ---------------------------------------------------------------------------
# Derived series used by stress components
# ---------------------------------------------------------------------------
def _derived_value(name: str) -> float | None:
    if name == "sofr_iorb_spread":
        sofr, iorb = _load_series("sofr"), _load_series("iorb")
        common = sofr.index.intersection(iorb.index)
        if common.empty:
            return None
        return float(sofr.loc[common[-1]] - iorb.loc[common[-1]])
    if name == "gilt_30y_5d_change":
        g = _load_series("gilt_30y")
        return _level_change(g, 5)
    if name == "uk_gilt_etf_5d_return":
        return _pct_change(_load_series("uk_gilt_etf"), 5)
    if name == "kre_1m_return":
        return _pct_change(_load_series("kre"), 21)
    return None


def _component_points(value: float | None, low: float, high: float, direction: str) -> int:
    if value is None:
        return 0
    if direction == "above":
        if value >= high:
            return 2
        if value >= low:
            return 1
        return 0
    # direction == "below" -> more negative is worse
    if value <= high:
        return 2
    if value <= low:
        return 1
    return 0


def compute_snapshot() -> DailySnapshot:
    indicators = [_read_indicator(n) for n in INDICATORS]
    state_zh = {"warn": "警戒", "crisis": "危机"}
    anomalies = [
        f"{ind.label}：z={ind.z_60d:+.2f}"
        f"（{'危机' if abs(ind.z_60d) >= ANOMALY_Z_CRISIS else '警戒'}）"
        for ind in indicators
        if ind.z_60d is not None and abs(ind.z_60d) >= ANOMALY_Z_WARN
    ]
    for ind in indicators:
        if ind.threshold_state in {"warn", "crisis"}:
            anomalies.append(
                f"{ind.label}：当前 {ind.latest_value:.3f} 越过"
                f"{state_zh[ind.threshold_state]}阈值"
            )

    # 数据新鲜度告警 —— 让任何静默失效的数据源显形
    for ind in indicators:
        if not ind.is_stale:
            continue
        if ind.latest_date is None:
            anomalies.append(f"⚠ 数据缺失：{ind.label} 本次运行无任何数据")
        else:
            anomalies.append(
                f"⚠ 数据陈旧：{ind.label} 最新数据为 {ind.latest_date}"
                f"（距今 {ind.staleness_days} 天，超过预算）"
            )

    components: list[StressComponent] = []
    total_points = 0
    for spec in STRESS_COMPONENTS:
        if "derived" in spec:
            v = _derived_value(spec["derived"])
        else:
            s = _load_series(spec["indicator"])
            v = float(s.iloc[-1]) if not s.empty else None
        pts = _component_points(v, spec["low"], spec["high"], spec["direction"])
        total_points += pts
        components.append(
            StressComponent(
                name=spec["name"], value=v, points=pts,
                detail=f"low={spec['low']}, high={spec['high']}, direction={spec['direction']}",
            )
        )

    if total_points >= STRESS_ALERT_CRISIS:
        band = "crisis"
    elif total_points >= STRESS_ALERT_WARN:
        band = "warn"
    elif total_points >= 1:
        band = "watch"
    else:
        band = "ok"

    return DailySnapshot(
        as_of=date.today().isoformat(),
        composite_stress=total_points,
        stress_band=band,
        components=components,
        indicators=indicators,
        anomalies=anomalies,
    )


def main() -> int:
    snap = compute_snapshot()
    out = OUT_DIR / "latest_snapshot.json"
    out.write_text(json.dumps(asdict(snap), indent=2, default=str))
    log.info(
        "Snapshot: stress=%d/12 band=%s, %d anomalies",
        snap.composite_stress, snap.stress_band, len(snap.anomalies),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
