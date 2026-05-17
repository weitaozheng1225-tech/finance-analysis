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

FRED_KEY = (os.getenv("FRED_API_KEY") or "").strip()
TIMEOUT = 30

# Many providers (BoE, MoF, stooq) reject the default python-requests UA.
SESSION = requests.Session()
SESSION.headers.update(
    {
        "User-Agent": (
            "Mozilla/5.0 (compatible; bond-crisis-monitor/1.0; "
            "+https://github.com/weitaozheng1225-tech/finance-analysis)"
        ),
        "Accept": "*/*",
    }
)


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
    r = SESSION.get(url, params=params, timeout=TIMEOUT)
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
    r = SESSION.get(url, params=params, timeout=TIMEOUT)
    r.raise_for_status()
    prices = r.json()["prices"]
    s = pd.Series(
        {pd.Timestamp(ms, unit="ms").normalize(): px for ms, px in prices},
        name=coin_id,
    )
    return s.groupby(s.index).last()


def fetch_mof_jgb(tenor: str) -> pd.Series:
    """Japan MoF historical JGB yields (CSV, Shift-JIS encoded)."""
    url = "https://www.mof.go.jp/english/policy/jgbs/reference/interest_rate/jgbcme.csv"
    r = SESSION.get(url, timeout=TIMEOUT)
    r.raise_for_status()
    # MoF publishes the CSV in Shift-JIS / CP932 (Japanese legacy encoding).
    text: str | None = None
    for enc in ("shift_jis", "cp932", "utf-8"):
        try:
            text = r.content.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise RuntimeError("Failed to decode MoF CSV with any known encoding")
    df = pd.read_csv(io.StringIO(text))
    df.columns = [str(c).strip() for c in df.columns]
    date_col = df.columns[0]
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    df = df.dropna(subset=[date_col]).set_index(date_col)
    col = f"{tenor}Y"
    if col not in df.columns:
        raise RuntimeError(f"tenor {col} not in MoF CSV columns: {list(df.columns)}")
    s = pd.to_numeric(df[col], errors="coerce").dropna()
    s.name = f"jgb_{tenor}y"
    return s


def fetch_stooq(ticker: str) -> pd.Series:
    """Stooq daily history CSV.

    Stooq's bond yield ticker convention is inconsistent: UK 10Y is
    ``10uky.b`` (no 'y' between tenor and country) while US 30Y is
    ``30yusy.b`` (with 'y'). Try the provided form and, if Stooq returns
    "no data", fall back to the alternate form automatically.
    """
    import re

    candidates: list[str] = [ticker]
    m = re.match(r"^(\d+)([a-z]{2,3})y?\.b$", ticker)
    if m:
        n, country = m.groups()
        for alt in (f"{n}{country}y.b", f"{n}y{country}y.b", f"{n}{country}.b"):
            if alt not in candidates:
                candidates.append(alt)

    last_err: str | None = None
    for cand in candidates:
        try:
            r = SESSION.get(f"https://stooq.com/q/d/l/?s={cand}&i=d", timeout=TIMEOUT)
            r.raise_for_status()
            body = r.text.strip()
            if not body or body.lower().startswith("no data"):
                last_err = f"no data for {cand}"
                continue
            df = pd.read_csv(io.StringIO(body))
            if "Date" not in df.columns or "Close" not in df.columns:
                last_err = f"unexpected CSV for {cand}: cols={list(df.columns)}"
                continue
            df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
            df = df.dropna(subset=["Date"]).set_index("Date").sort_index()
            s = pd.to_numeric(df["Close"], errors="coerce").dropna()
            s.name = cand
            if cand != ticker:
                log.info("stooq fallback ticker %s worked (original %s failed)", cand, ticker)
            return s
        except Exception as e:
            last_err = str(e)
            continue
    raise RuntimeError(f"stooq: all ticker candidates failed for {ticker} -> {candidates}: {last_err}")


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
    "stooq": fetch_stooq,
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
