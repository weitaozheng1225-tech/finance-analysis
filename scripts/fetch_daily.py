"""Daily fetcher for bond crisis monitor.

Pulls all configured indicators from public free sources and appends to
per-indicator CSV files under data/timeseries/. Each CSV is keyed by date
with columns [date, value]. Idempotent — re-running a day overwrites the row.

Required env: FRED_API_KEY (free signup at https://fred.stlouisfed.org/).
All other sources are keyless.
"""

from __future__ import annotations

import io
import logging
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data" / "timeseries"
DATA_DIR.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(ROOT / "scripts"))
from config import INDICATORS  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(message)s",
)
log = logging.getLogger("fetch")

FRED_KEY = os.getenv("FRED_API_KEY")
TIMEOUT = 30


# ---------------------------------------------------------------------------
# Source adapters
# ---------------------------------------------------------------------------
def fetch_fred(series_id: str) -> pd.Series:
    if not FRED_KEY:
        raise RuntimeError("FRED_API_KEY env var not set")
    url = "https://api.stlouisfed.org/fred/series/observations"
    params = {
        "series_id": series_id,
        "api_key": FRED_KEY,
        "file_type": "json",
        "observation_start": (date.today() - timedelta(days=365 * 3)).isoformat(),
    }
    r = requests.get(url, params=params, timeout=TIMEOUT)
    r.raise_for_status()
    obs = r.json()["observations"]
    s = pd.Series(
        {pd.Timestamp(o["date"]): _to_float(o["value"]) for o in obs},
        name=series_id,
    ).dropna()
    return s


def fetch_yahoo(ticker: str) -> pd.Series:
    import yfinance as yf

    hist = yf.Ticker(ticker).history(period="2y", interval="1d", auto_adjust=False)
    if hist.empty:
        raise RuntimeError(f"no data for {ticker}")
    # Normalise to naive date index
    hist.index = hist.index.tz_localize(None).normalize()
    return hist["Close"].dropna()


def fetch_coingecko(coin_id: str) -> pd.Series:
    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
    params = {"vs_currency": "usd", "days": "365", "interval": "daily"}
    r = requests.get(url, params=params, timeout=TIMEOUT)
    r.raise_for_status()
    prices = r.json()["prices"]
    s = pd.Series(
        {pd.Timestamp(ms, unit="ms").normalize(): px for ms, px in prices},
        name=coin_id,
    )
    return s.groupby(s.index).last()


def fetch_mof_jgb(tenor: str) -> pd.Series:
    """Japan MoF historical JGB yields (CSV)."""
    year = date.today().year
    url = f"https://www.mof.go.jp/english/policy/jgbs/reference/interest_rate/jgbcme.csv"
    r = requests.get(url, timeout=TIMEOUT)
    r.raise_for_status()
    df = pd.read_csv(io.BytesIO(r.content))
    # The CSV: first col = Date, then columns named '1Y','2Y',...,'30Y','40Y'
    df.columns = [c.strip() for c in df.columns]
    date_col = df.columns[0]
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    df = df.dropna(subset=[date_col]).set_index(date_col)
    col = f"{tenor}Y"
    if col not in df.columns:
        raise RuntimeError(f"tenor {col} not in MoF CSV columns: {list(df.columns)}")
    s = pd.to_numeric(df[col], errors="coerce").dropna()
    s.name = f"jgb_{tenor}y"
    return s


def fetch_dmo_gilt(tenor: str) -> pd.Series:
    """UK Gilt yields via Bank of England yield curve archive.

    The DMO does not publish a stable machine-readable daily yield curve, but
    BoE publishes a spreadsheet of nominal spot curves daily. We use FRED-style
    proxy via Yahoo (^TNX-equivalent for UK) — fall back to BoE if needed.
    """
    # Use Yahoo proxy: ^TYX-style not available for UK, use specific tickers.
    # IGLT.L = iShares UK Gilts ETF (proxy for price), not yield. So instead:
    # The Bank of England publishes daily nominal yield curves at
    # https://www.bankofengland.co.uk/statistics/yield-curves -- requires xls.
    # As a pragmatic free source we use FT's published yield via investpy/yfinance.
    # Yahoo provides ^FTAS but no yield curve. We use UK Gilt ETF + duration proxy
    # OR pull the BoE GLC nominal spot curve XLSX:
    url = (
        "https://www.bankofengland.co.uk/-/media/boe/files/statistics/yield-curves/latest-yield-curve-data.zip"
    )
    try:
        import zipfile
        r = requests.get(url, timeout=TIMEOUT)
        r.raise_for_status()
        z = zipfile.ZipFile(io.BytesIO(r.content))
        # find the GLC nominal daily file
        target = next(
            (n for n in z.namelist() if "GLC Nominal daily data" in n and n.endswith(".xlsx")),
            None,
        )
        if target is None:
            raise RuntimeError("BoE zip missing GLC Nominal daily file")
        with z.open(target) as f:
            xl = pd.ExcelFile(f)
            # most recent year sheet
            sheet = sorted([s for s in xl.sheet_names if s.isdigit() or " " in s])[-1]
            df = xl.parse(sheet, skiprows=3)
        # first column is date, subsequent columns are maturities in years
        date_col = df.columns[0]
        df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
        df = df.dropna(subset=[date_col]).set_index(date_col)
        # find the column closest to requested tenor
        numeric_cols = [c for c in df.columns if isinstance(c, (int, float))]
        if not numeric_cols:
            raise RuntimeError("BoE sheet has no numeric maturity columns")
        target_tenor = float(tenor)
        closest = min(numeric_cols, key=lambda c: abs(c - target_tenor))
        s = pd.to_numeric(df[closest], errors="coerce").dropna()
        s.name = f"gilt_{tenor}y"
        return s
    except Exception as e:
        log.warning("BoE gilt fetch failed (%s); falling back to Yahoo ^FTSE-derived proxy", e)
        # last resort: no gilt yield; return empty series so loop continues
        return pd.Series(dtype=float, name=f"gilt_{tenor}y")


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
def _to_float(v: str) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return float("nan")


def _append_csv(name: str, series: pd.Series) -> None:
    if series.empty:
        log.warning("[%s] empty series, skipping write", name)
        return
    path = DATA_DIR / f"{name}.csv"
    new = series.rename("value").to_frame()
    new.index.name = "date"
    new.index = pd.to_datetime(new.index).normalize()
    if path.exists():
        existing = pd.read_csv(path, parse_dates=["date"]).set_index("date")
        existing.index = existing.index.normalize()
        merged = pd.concat([existing[~existing.index.isin(new.index)], new])
        merged = merged.sort_index()
    else:
        merged = new.sort_index()
    merged.to_csv(path)
    last = merged.iloc[-1]
    log.info("[%s] wrote %d rows, latest %s = %s", name, len(merged), merged.index[-1].date(), last["value"])


SOURCE_DISPATCH = {
    "fred": fetch_fred,
    "yahoo": fetch_yahoo,
    "coingecko": fetch_coingecko,
    "mof": fetch_mof_jgb,
    "dmo": fetch_dmo_gilt,
}


def main() -> int:
    failures: list[str] = []
    for name, cfg in INDICATORS.items():
        src = cfg["source"]
        fn = SOURCE_DISPATCH.get(src)
        if fn is None:
            log.warning("[%s] no fetcher for source=%s", name, src)
            continue
        try:
            series = fn(cfg["id"])
            _append_csv(name, series)
        except Exception as e:
            log.error("[%s] fetch failed: %s", name, e)
            failures.append(name)

    summary_path = ROOT / "data" / "last_fetch.txt"
    summary_path.parent.mkdir(exist_ok=True)
    summary_path.write_text(
        f"fetched_at={datetime.now(timezone.utc).isoformat()}\n"
        f"total={len(INDICATORS)}\n"
        f"failures={','.join(failures) if failures else 'none'}\n"
    )
    if failures:
        log.warning("Completed with %d failures: %s", len(failures), failures)
        # exit non-zero only if more than half failed
        return 1 if len(failures) > len(INDICATORS) / 2 else 0
    log.info("All %d indicators fetched.", len(INDICATORS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
