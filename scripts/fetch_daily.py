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
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/csv,application/json,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
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
    """Japan MoF historical JGB yields.

    The CSV is Shift-JIS encoded. Row 0 is a unit annotation like ``,,,,(Unit : %)``;
    row 1 holds the real header ``Date,1Y,2Y,...,30Y,40Y``. We must skip row 0.
    """
    url = "https://www.mof.go.jp/english/policy/jgbs/reference/interest_rate/jgbcme.csv"
    r = SESSION.get(url, timeout=TIMEOUT)
    r.raise_for_status()
    text: str | None = None
    for enc in ("shift_jis", "cp932", "utf-8"):
        try:
            text = r.content.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise RuntimeError("Failed to decode MoF CSV with any known encoding")
    df = pd.read_csv(io.StringIO(text), header=1)
    df.columns = [str(c).strip() for c in df.columns]
    date_col = df.columns[0]
    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    df = df.dropna(subset=[date_col]).set_index(date_col)
    # Some years use Japanese tenor names (e.g. "1年"); normalise.
    col_candidates = [f"{tenor}Y", f"{tenor}年", tenor]
    col = next((c for c in col_candidates if c in df.columns), None)
    if col is None:
        raise RuntimeError(
            f"tenor {tenor} not in MoF CSV columns: {list(df.columns)}"
        )
    s = pd.to_numeric(df[col], errors="coerce").dropna()
    s.name = f"jgb_{tenor}y"
    return s


def fetch_stooq(ticker: str) -> pd.Series:
    """Stooq daily history CSV.

    Standard bond yield ticker pattern is ``Nyy{country}y.b`` (e.g.
    ``10yusy.b`` for US 10Y, ``10ydey.b`` for Germany 10Y, ``10yuky.b``
    for UK 10Y). We try the given ticker and a couple of common
    alternate forms. Stooq's free CSV endpoint may rate-limit by IP
    and return an HTML page mentioning "apikey" — we detect that and
    raise a clear error so the failure is diagnosable.
    """
    import re

    candidates: list[str] = [ticker]
    m = re.match(r"^(\d+)y?([a-z]{2,3})y?\.b$", ticker)
    if m:
        n, country = m.groups()
        for alt in (f"{n}y{country}y.b", f"{n}{country}y.b", f"{n}{country}.b"):
            if alt not in candidates:
                candidates.append(alt)

    last_err: str | None = None
    for cand in candidates:
        try:
            r = SESSION.get(f"https://stooq.com/q/d/l/?s={cand}&i=d", timeout=TIMEOUT)
            r.raise_for_status()
            body = r.text.strip()
            body_lower = body.lower()
            if not body:
                last_err = f"empty response for {cand}"
                continue
            if body_lower.startswith("<") or "<html" in body_lower[:200]:
                snippet = body[:200].replace("\n", " ")
                last_err = f"HTML (not CSV) response for {cand}: '{snippet}'"
                continue
            if "apikey" in body_lower[:200] or "get_apikey" in body_lower:
                last_err = f"stooq apikey-required for {cand} (free CSV likely rate-limited)"
                continue
            if body_lower.startswith("no data"):
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


def fetch_fiscal_auction(spec: str) -> pd.Series:
    """Treasury Fiscal Data API — Treasury Auctions dataset.

    spec format: ``"<security_term>|<field_name>"``
    Example: ``"30-Year|bid_to_cover_ratio"``.

    Returns one row per auction (sparse — typically monthly for 30Y bonds),
    indexed by auction_date. Defensive: empty/malformed rows are skipped,
    and the function raises a clear error if no usable data is returned so
    the orchestrator records a single named failure rather than poisoning
    the entire pipeline.
    """
    term, field = spec.split("|", 1)
    url = (
        "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/"
        "v1/accounting/od/auctions_query"
    )
    params = {
        "filter": f"security_term:eq:{term}",
        "fields": f"auction_date,{field}",
        "sort": "-auction_date",
        "page[size]": "200",
    }
    r = SESSION.get(url, params=params, timeout=TIMEOUT)
    r.raise_for_status()
    payload = r.json()
    rows = payload.get("data", [])
    if not rows:
        raise RuntimeError(f"fiscal API returned no rows for term={term}")
    parsed: list[tuple[pd.Timestamp, float]] = []
    for row in rows:
        d = row.get("auction_date")
        v = row.get(field)
        if not d or v in (None, "", "null", "NULL"):
            continue
        try:
            parsed.append((pd.Timestamp(d), float(v)))
        except (ValueError, TypeError):
            continue
    if not parsed:
        raise RuntimeError(
            f"fiscal API: no usable rows for term={term} field={field} "
            f"(received {len(rows)} raw rows)"
        )
    parsed.sort()
    idx, vals = zip(*parsed)
    # Deduplicate by date (keep the latest write per date)
    s = pd.Series(vals, index=pd.DatetimeIndex(idx))
    s = s.groupby(s.index).last()
    s.name = f"fiscal_{term}_{field}"
    return s


SOURCE_DISPATCH = {
    "fred": fetch_fred,
    "yahoo": fetch_yahoo,
    "coingecko": fetch_coingecko,
    "mof": fetch_mof_jgb,
    "stooq": fetch_stooq,
    "fiscal": fetch_fiscal_auction,
}


# ---------------------------------------------------------------------------
# Derived indicators — computed from base series after the main fetch loop
# ---------------------------------------------------------------------------
def _load_csv(name: str) -> pd.Series:
    p = DATA_DIR / f"{name}.csv"
    if not p.exists():
        return pd.Series(dtype=float)
    df = pd.read_csv(p, parse_dates=["date"])
    return df.set_index("date")["value"].sort_index()


def _compute_jpy_usd_hedge_cost() -> pd.Series:
    us3 = _load_csv("us_3m_tbill")
    jp3 = _load_csv("jp_3m_tbill")
    if us3.empty or jp3.empty:
        raise RuntimeError("missing inputs: us_3m_tbill or jp_3m_tbill")
    jp3_ff = jp3.reindex(us3.index, method="ffill")
    s = (us3 - jp3_ff).dropna()
    s.name = "jpy_usd_hedge_cost"
    return s


def _compute_hedged_us_jgb_carry() -> pd.Series:
    us10 = _load_csv("us_10y")
    us3 = _load_csv("us_3m_tbill")
    jp3 = _load_csv("jp_3m_tbill")
    jgb10 = _load_csv("jgb_10y")
    missing = [n for n, s in zip(
        ["us_10y", "us_3m_tbill", "jp_3m_tbill", "jgb_10y"],
        [us10, us3, jp3, jgb10],
    ) if s.empty]
    if missing:
        raise RuntimeError(f"missing inputs: {missing}")
    idx = us10.index
    us3_a = us3.reindex(idx, method="ffill")
    jp3_a = jp3.reindex(idx, method="ffill")
    jgb10_a = jgb10.reindex(idx, method="ffill")
    hedge = us3_a - jp3_a
    s = (us10 - hedge - jgb10_a).dropna()
    s.name = "hedged_us_jgb_carry"
    return s


def _compute_spread(short: str, long: str, out_name: str) -> pd.Series:
    a = _load_csv(long)
    b = _load_csv(short)
    if a.empty or b.empty:
        raise RuntimeError(f"missing inputs: {long} / {short}")
    common = a.index.intersection(b.index)
    if len(common) == 0:
        raise RuntimeError(f"no overlapping dates: {long} / {short}")
    s = (a.loc[common] - b.loc[common]).dropna()
    s.name = out_name
    return s


def _compute_us_2s10s() -> pd.Series:
    return _compute_spread("us_2y", "us_10y", "us_2s10s")


def _compute_us_10s30s() -> pd.Series:
    return _compute_spread("us_10y", "us_30y", "us_10s30s")


def _compute_jgb_10s30s() -> pd.Series:
    return _compute_spread("jgb_10y", "jgb_30y", "jgb_10s30s")


def _compute_move_3y_percentile() -> pd.Series:
    m = _load_csv("move")
    if m.empty:
        raise RuntimeError("missing input: move")
    if len(m) < 250:
        raise RuntimeError(f"insufficient MOVE history ({len(m)} rows, need ≥250)")
    # Rolling 750-day window (~3 years of trading days) percentile rank
    # of the current value. pandas' rolling.rank(pct=True) gives the
    # per-window rank of each value as a fraction; multiply by 100 for %ile.
    s = (m.rolling(window=750, min_periods=250).rank(pct=True) * 100).dropna()
    s.name = "move_3y_percentile"
    return s


DERIVED_DISPATCH = {
    "jpy_usd_hedge_cost": _compute_jpy_usd_hedge_cost,
    "hedged_us_jgb_carry": _compute_hedged_us_jgb_carry,
    "us_2s10s": _compute_us_2s10s,
    "us_10s30s": _compute_us_10s30s,
    "jgb_10s30s": _compute_jgb_10s30s,
    "move_3y_percentile": _compute_move_3y_percentile,
}


def main() -> int:
    failures: list[str] = []
    # Pass 1 — fetch all base (non-derived) indicators
    for name, cfg in INDICATORS.items():
        src = cfg["source"]
        if src == "derived":
            continue
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

    # Pass 2 — compute derived indicators from CSVs written in pass 1
    for name, cfg in INDICATORS.items():
        if cfg["source"] != "derived":
            continue
        fn = DERIVED_DISPATCH.get(name)
        if fn is None:
            log.warning("[%s] no derived computation registered", name)
            failures.append(name)
            continue
        try:
            series = fn()
            _append_csv(name, series)
        except Exception as e:
            log.error("[%s] derived computation failed: %s", name, e)
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
