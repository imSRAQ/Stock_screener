"""
data_sources.py  ***NEW FILE — added to support multiple data backends***

Two free data backends for NSE daily OHLC, selectable via --source:

  1. "yfinance"  (original/default) - unofficial Yahoo Finance wrapper,
     queried per-ticker. Easy, but unofficial and rate-limit-prone at scale.

  2. "nse"       (new) - NSE's own official daily Bhavcopy (UDiFF) archive.
     This is the exchange's primary published data, not a third-party
     wrapper. The tradeoff: Bhavcopy is published ONE FILE PER TRADING DAY
     covering ALL stocks, not one call per ticker. So building an N-day
     history means downloading N daily archive files and stitching them
     together — slower to assemble but does not depend on Yahoo at all.

Both backends expose the same function signature so the rest of the
codebase doesn't need to know which one is active:

    fetch_universe_ohlc(tickers, period_days, source="yfinance") -> dict[str, np.ndarray]
    fetch_reference_ohlc(ticker, period_days, source="yfinance") -> (np.ndarray, list[str dates])

IMPORTANT CAVEATS:
  - NSE's archive server commonly rejects bare/scripted requests with a 403
    unless real browser-like headers are sent and a session/cookie is
    established first. This module does that (see _nse_session()), but NSE
    can still change its anti-bot behavior at any time without notice.
  - The Bhavcopy URL format below (UDiFF, .csv.zip) is current as of mid-2026
    per NSE circular 62424 (June 2024), replacing the older bhavcopy.csv
    format that was discontinued July 8, 2024. If NSE changes this again,
    this function will need updating — it WILL break silently otherwise,
    so errors are raised loudly rather than swallowed.
  - This pulls one ZIP per calendar day in your lookback window across
    ALL ~2000 listed securities, then filters down to the tickers you
    asked for. That's a few MB per file - fine for a 30-90 day lookback,
    slow for very long windows. A local on-disk cache avoids re-downloading
    a date you've already fetched in a previous run.
"""

import io
import os
import sys
import time
import zipfile
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Shared cache directory so repeated runs (e.g. daily use) don't re-download
# the same historical Bhavcopy files every time.
# ---------------------------------------------------------------------------
CACHE_DIR = os.path.join(os.path.expanduser("~"), ".nse_screener_cache")


def _ensure_cache_dir():
    os.makedirs(CACHE_DIR, exist_ok=True)


# ---------------------------------------------------------------------------
# BACKEND 1: yfinance (original behavior, unchanged from the first version)
# ---------------------------------------------------------------------------

def _fetch_yfinance(ticker: str, period_days: int, retries: int = 2):
    try:
        import yfinance as yf
    except ImportError:
        print("ERROR: yfinance not installed. Run: pip install yfinance", file=sys.stderr)
        sys.exit(1)

    calendar_days = int(period_days * 1.6) + 10

    for attempt in range(retries + 1):
        try:
            df = yf.Ticker(ticker).history(period=f"{calendar_days}d", interval="1d")
            if df is None or df.empty:
                return None
            df = df.tail(period_days)
            if len(df) < max(5, period_days * 0.5):
                return None
            # closes = df["Close"].to_numpy()
            # dates = [d.strftime("%Y-%m-%d") for d in df.index]
            # return closes, dates
            
            # ============================================================
            # MODIFICATION START
            # Handle missing close values by carrying forward
            # the previous trading day's close (forward-fill).
            # ============================================================

            missing_before = df["Close"].isna().sum()
            
            df["Close"] = (
                pd.to_numeric(df["Close"], errors="coerce")
                .ffill()      # use previous day's close
                .bfill()      # safety fallback if first row is NaN
            )

            if missing_before > 0:
                print(
                    f"[info] {ticker}: replaced "
                    f"{missing_before} missing close value(s) "
                    f"using previous trading day close."
                )

            # If any NaNs still remain, discard the ticker
            if df["Close"].isna().any():
                return None

            closes = df["Close"].to_numpy(dtype=float)
            dates = [d.strftime("%Y-%m-%d") for d in df.index]

            # ============================================================
            # MODIFICATION END
            # ============================================================

            return closes, dates
        except Exception as e:
            if attempt < retries:
                time.sleep(1.5)
                continue
            print(f"  [warn] yfinance failed for {ticker}: {e}", file=sys.stderr)
            return None


# ---------------------------------------------------------------------------
# BACKEND 2: NSE official Bhavcopy archive  ***NEW***
# ---------------------------------------------------------------------------

_NSE_SESSION = None  # module-level cache of the warmed-up session


def _nse_session():
    """
    NSE's archive server blocks bare scripted requests. The standard
    workaround is to use a real browser User-Agent and first visit the
    homepage so the session picks up the cookies NSE expects on
    subsequent archive requests. Cached at module level so we only do
    this handshake once per script run, not once per file.
    """
    global _NSE_SESSION
    if _NSE_SESSION is not None:
        return _NSE_SESSION

    import requests
    session = requests.Session()
    session.headers.update({
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Connection": "keep-alive",
    })
    try:
        # Warm-up request to the homepage to establish session cookies
        # before requesting the archive endpoint.
        session.get("https://www.nseindia.com", timeout=10)
    except Exception as e:
        print(f"  [warn] NSE session warm-up failed ({e}); archive requests may be blocked.",
              file=sys.stderr)
    _NSE_SESSION = session
    return session


def _bhavcopy_url(date: datetime) -> str:
    """
    Current (as of mid-2026) UDiFF Common Bhavcopy Final URL format.
    See NSE Circular No. 62424 (June 12, 2024) - this replaced the older
    plain-CSV bhavcopy URL, which NSE discontinued July 8, 2024.
    """
    ds = date.strftime("%Y%m%d")
    return f"https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{ds}_F_0000.csv.zip"


def _fetch_bhavcopy_day(date: datetime, retries: int = 2) -> pd.DataFrame:
    """
    Download and parse one day's Bhavcopy. Returns a DataFrame indexed by
    SYMBOL with at least a CLOSE column, or None if that date has no data
    (weekend/holiday) or the download failed.
    Caches the raw CSV on disk so re-running the script doesn't re-fetch
    days you already have.
    """
    _ensure_cache_dir()
    cache_path = os.path.join(CACHE_DIR, f"bhavcopy_{date.strftime('%Y%m%d')}.csv")

    if os.path.exists(cache_path):
        try:
            return pd.read_csv(cache_path)
        except Exception:
            pass  # fall through and re-fetch if cached file is corrupt

    session = _nse_session()
    url = _bhavcopy_url(date)

    for attempt in range(retries + 1):
        try:
            resp = session.get(url, timeout=20)
            if resp.status_code == 404:
                return None  # market holiday/weekend - no file published
            resp.raise_for_status()
            with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
                csv_name = zf.namelist()[0]
                with zf.open(csv_name) as f:
                    df = pd.read_csv(f)
            df.to_csv(cache_path, index=False)  # cache for next run
            return df
        except Exception as e:
            if attempt < retries:
                time.sleep(1.5)
                continue
            print(f"  [warn] Bhavcopy fetch failed for {date.strftime('%Y-%m-%d')}: {e}",
                  file=sys.stderr)
            return None


def _fetch_nse_universe(tickers: list, period_days: int) -> dict:
    """
    Builds an N-day close-price history for every requested ticker by
    downloading one Bhavcopy file per trading day and pivoting.
    This single pass covers ALL requested tickers at once (unlike
    yfinance, which needs one call per ticker), which is the main
    efficiency advantage of this backend for large candidate universes.
    """
    symbols = {t.replace(".NS", "") for t in tickers}
    calendar_days_needed = int(period_days * 1.6) + 10

    records = {}  # symbol -> list of (date_str, close)
    today = datetime.now()
    days_collected = 0
    days_checked = 0
    max_days_to_check = calendar_days_needed + 15  # safety margin for holidays

    print(f"  Downloading NSE Bhavcopy archives (this fetches ALL stocks per "
          f"day, cached locally at {CACHE_DIR})...")

    while days_collected < period_days and days_checked < max_days_to_check:
        day = today - timedelta(days=days_checked + 1)  # start from yesterday
        days_checked += 1
        if day.weekday() >= 5:  # skip Sat/Sun outright, saves a request
            continue

        df = _fetch_bhavcopy_day(day)
        if df is None:
            continue  # holiday or fetch failure for this day

        # UDiFF columns are typically upper-case; normalize defensively
        df.columns = [c.strip().upper() for c in df.columns]
        if "SYMBOL" not in df.columns or "CLOSE_PRICE" not in df.columns:
            # Column name fallback - UDiFF sometimes labels it CLOSE_PRICE,
            # older formats used CLOSE. Try both before giving up on the file.
            close_col = "CLOSE" if "CLOSE" in df.columns else None
        else:
            close_col = "CLOSE_PRICE"

        if close_col is None or "SYMBOL" not in df.columns:
            print(f"  [warn] unexpected Bhavcopy column format on "
                  f"{day.strftime('%Y-%m-%d')}, skipping this file.", file=sys.stderr)
            continue

        day_str = day.strftime("%Y-%m-%d")
        subset = df[df["SYMBOL"].isin(symbols)][["SYMBOL", close_col]]
        for _, row in subset.iterrows():
            records.setdefault(row["SYMBOL"], []).append((day_str, float(row[close_col])))

        days_collected += 1
        if days_collected % 15 == 0:
            print(f"  ...{days_collected}/{period_days} trading days collected")

    # Reassemble into {ticker: close_array}, sorted oldest -> newest
    result = {}
    for symbol, points in records.items():
        points.sort(key=lambda p: p[0])
        closes = np.array([p[1] for p in points], dtype=float)
        if len(closes) >= max(5, period_days * 0.5):
            ticker_key = symbol if symbol.endswith(".NS") else f"{symbol}.NS"
            result[ticker_key] = closes
    return result


# ---------------------------------------------------------------------------
# Public unified interface
# ---------------------------------------------------------------------------

def fetch_reference_ohlc(ticker: str, period_days: int, source: str = "yfinance"):
    """Returns (close_array, date_strings) for a single reference ticker."""
    if source == "yfinance":
        out = _fetch_yfinance(ticker, period_days)
        return out if out else (None, None)
    elif source == "nse":
        universe = _fetch_nse_universe([ticker], period_days)
        symbol = ticker if ticker.endswith(".NS") else f"{ticker}.NS"
        if symbol not in universe:
            return None, None
        closes = universe[symbol]
        # Bhavcopy backend doesn't track exact trading-day strings per
        # close as cleanly as yfinance's DataFrame index; approximate with
        # a generic sequential label since the dashboard only needs *a*
        # date axis, not perfectly reconstructed calendar dates.
        dates = [f"day_{i+1}" for i in range(len(closes))]
        return closes, dates
    else:
        raise ValueError(f"Unknown source '{source}'. Use 'yfinance' or 'nse'.")


def fetch_universe_ohlc(tickers: list, period_days: int, source: str = "yfinance", delay: float = 0.3):
    """
    Returns {ticker: close_array} for every ticker that returned usable data.
    For yfinance, fetches one ticker at a time (with --delay pacing).
    For nse, fetches the whole universe in one pass over daily archives.
    """
    if source == "yfinance":
        candidates_data = {}
        failed = []
        for i, ticker in enumerate(tickers, 1):
            if i % 25 == 0:
                print(f"  ...{i}/{len(tickers)} processed")
            out = _fetch_yfinance(ticker, period_days)
            if out is None:
                failed.append(ticker)
                continue
            closes, _dates = out
            candidates_data[ticker] = closes
            time.sleep(delay)
        return candidates_data, failed

    elif source == "nse":
        candidates_data = _fetch_nse_universe(tickers, period_days)
        failed = [t for t in tickers if t not in candidates_data]
        return candidates_data, failed

    else:
        raise ValueError(f"Unknown source '{source}'. Use 'yfinance' or 'nse'.")


# ---------------------------------------------------------------------------
# *** NEW: Market capitalization lookup ***
#
# Market cap is a CURRENT snapshot value, not a historical series, so it's
# fetched separately from the OHLC history above (one lookup per ticker,
# not per day). Two backends, same idea as OHLC:
#
#   "yfinance" - ticker.info["marketCap"], in raw rupees.
#   "nse"      - NSE's own quote-equity API, which reports market cap in
#                rupees CRORES (1 crore = 10,000,000) natively - converted
#                to plain rupees here so both backends return the same unit.
# ---------------------------------------------------------------------------

# def _fetch_market_cap_yfinance(ticker: str, retries: int = 1):
#     try:
#         import yfinance as yf
#     except ImportError:
#         return None
#     for attempt in range(retries + 1):
#         try:
#             info = yf.Ticker(ticker).get_info()
#             cap = info.get("marketCap")
#             return float(cap) if cap else None
#         except Exception:
#             if attempt < retries:
#                 time.sleep(1.0)
#                 continue
#             return None

def compute_fundamental_score(fund: dict) -> float:
    """
    Compute a composite fundamental strength score (0–100) from a
    fundamentals dict. Higher = financially healthier company.

    Scoring weights:
      P/E < 25 (reasonable valuation):  15%
      ROE > 15%:                        15%
      Debt/Equity < 1.0:                15%
      Profit Margin > 10%:              15%
      Revenue Growth > 0%:              15%
      EPS > 0 (profitable):             10%
      Free Cash Flow > 0:               15%

    Missing values score 50 (neutral) — not penalized, not rewarded.
    """
    components = []
    weights = []
    NEUTRAL = 50

    # P/E: best < 15, good < 25, poor > 40
    pe = fund.get("pe_ratio")
    if pe is not None and pe > 0:
        if pe <= 15:
            components.append(100)
        elif pe <= 25:
            components.append(100 - (pe - 15) * 4)  # 100→60
        elif pe <= 40:
            components.append(max(0, 60 - (pe - 25) * 4))  # 60→0
        else:
            components.append(0)
    else:
        components.append(NEUTRAL)
    weights.append(15)

    # ROE: scaled, best > 20%
    roe = fund.get("roe")
    if roe is not None:
        roe_pct = roe * 100 if abs(roe) < 1 else roe  # handle both 0.15 and 15.0
        components.append(min(100, max(0, roe_pct * 5)))  # 20% → 100
    else:
        components.append(NEUTRAL)
    weights.append(15)

    # Debt/Equity: best < 0.5, good < 1.0, poor > 2.0
    de = fund.get("debt_to_equity")
    if de is not None:
        de_val = de / 100 if de > 10 else de  # yfinance returns as %, normalize
        if de_val <= 0.5:
            components.append(100)
        elif de_val <= 1.0:
            components.append(100 - (de_val - 0.5) * 80)  # 100→60
        elif de_val <= 2.0:
            components.append(max(0, 60 - (de_val - 1.0) * 60))  # 60→0
        else:
            components.append(0)
    else:
        components.append(NEUTRAL)
    weights.append(15)

    # Profit Margin: scaled 0–100
    margin = fund.get("profit_margin")
    if margin is not None:
        margin_pct = margin * 100 if abs(margin) < 1 else margin
        components.append(min(100, max(0, margin_pct * 4)))  # 25% → 100
    else:
        components.append(NEUTRAL)
    weights.append(15)

    # Revenue Growth: positive = good
    rev_growth = fund.get("revenue_growth")
    if rev_growth is not None:
        growth_pct = rev_growth * 100 if abs(rev_growth) < 5 else rev_growth
        components.append(min(100, max(0, 50 + growth_pct * 2)))  # 0%→50, 25%→100
    else:
        components.append(NEUTRAL)
    weights.append(15)

    # EPS: positive = profitable
    eps = fund.get("eps")
    if eps is not None:
        components.append(100 if eps > 0 else 0)
    else:
        components.append(NEUTRAL)
    weights.append(10)

    # Free Cash Flow: positive = good
    fcf = fund.get("free_cash_flow")
    if fcf is not None:
        components.append(100 if fcf > 0 else 20)
    else:
        components.append(NEUTRAL)
    weights.append(15)

    total_weight = sum(weights)
    score = sum(c * w for c, w in zip(components, weights)) / total_weight
    return round(score, 1)


def fetch_fundamentals(tickers, source="yfinance", delay=0.0):
    """
    Fetch fundamental metrics for tickers.

    Returns a dict keyed by ticker with comprehensive fundamental data
    plus a composite fund_score (0–100).

    Metrics fetched:
      - market_cap, current_price (existing)
      - roe, quick_ratio (existing)
      - pe_ratio, eps, pb_ratio, debt_to_equity (NEW)
      - profit_margin, revenue_growth, free_cash_flow, dividend_yield (NEW)
      - fund_score (NEW — composite 0–100)
    """

    _empty = {
        "market_cap": None, "current_price": None,
        "roe": None, "quick_ratio": None,
        "pe_ratio": None, "eps": None, "pb_ratio": None,
        "debt_to_equity": None, "profit_margin": None,
        "revenue_growth": None, "free_cash_flow": None,
        "dividend_yield": None, "fund_score": None,
    }

    results = {}

    # Always use yfinance for fundamental metrics (NSE API doesn't provide most of these easily)
    try:
        import yfinance as yf
    except ImportError:
        return {t: dict(_empty) for t in tickers}

    import time
    import concurrent.futures

    def _fetch_one_fund(ticker):
        if delay > 0:
            time.sleep(delay / 2.0)
        try:
            info = yf.Ticker(ticker).info

            fund = {
                # Existing metrics
                "market_cap": info.get("marketCap"),
                "current_price": (
                    info.get("currentPrice")
                    or info.get("regularMarketPrice")
                ),
                "roe": info.get("returnOnEquity"),
                "quick_ratio": info.get("quickRatio"),

                # NEW: valuation
                "pe_ratio": info.get("trailingPE"),
                "eps": info.get("trailingEps"),
                "pb_ratio": info.get("priceToBook"),

                # NEW: financial health
                "debt_to_equity": info.get("debtToEquity"),
                "profit_margin": info.get("profitMargins"),
                "revenue_growth": info.get("revenueGrowth"),
                "free_cash_flow": info.get("freeCashflow"),

                # NEW: income
                "dividend_yield": info.get("dividendYield"),
            }

            # Compute composite fundamental score
            fund["fund_score"] = compute_fundamental_score(fund)
            return ticker, fund

        except Exception as e:
            print(f"[warn] fundamentals fetch failed for {ticker}: {e}")
            return ticker, dict(_empty)

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        for ticker, fund in executor.map(_fetch_one_fund, tickers):
            results[ticker] = fund

    return results

def _fetch_market_cap_nse(ticker: str, retries: int = 1):
    """
    NSE's quote-equity endpoint returns market cap under
    priceInfo -> "totalMarketCap" or similar, expressed in CRORES.
    NSE's exact JSON shape has shifted before, so this looks in a couple of
    plausible spots and converts crores -> rupees; if NSE changes the
    schema again this returns None rather than fail loudly, since it's a
    secondary enrichment field, not the core OHLC data.
    """
    try:
        import requests
    except ImportError:
        return None

    symbol = ticker.replace(".NS", "")
    session = _nse_session()
    url = f"https://www.nseindia.com/api/quote-equity?symbol={symbol}"

    for attempt in range(retries + 1):
        try:
            resp = session.get(url, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            price_info = data.get("priceInfo", {})
            cap_crores = (
                price_info.get("totalMarketCap")
                or data.get("securityInfo", {}).get("totalMarketCap")
            )
            if cap_crores:
                return float(cap_crores) * 1e7  # crores -> rupees
            return None
        except Exception:
            if attempt < retries:
                time.sleep(1.0)
                continue
            return None


def fetch_market_caps(tickers: list, source: str = "yfinance", delay: float = 0.3) -> dict:
    """
    Returns {ticker: market_cap_in_rupees} for every ticker where a market
    cap could be found. Omits the key entirely for tickers where neither
    backend has the figure - the dashboard treats a missing market cap as
    "n/a" rather than erroring.

    This is intentionally a best-effort enrichment pass, separate from the
    core similarity ranking: if it fails entirely, the screener still
    works, you just won't see market cap in the dashboard.
    """
    caps = {}
    # fetch_fn = _fetch_market_cap_yfinance if source == "yfinance" else _fetch_market_cap_nse
    fetch_fn = fetch_fundamentals if source == "yfinance" else _fetch_market_cap_nse
    for i, ticker in enumerate(tickers, 1):
        if i % 25 == 0:
            print(f"  ...market cap {i}/{len(tickers)} processed")
        cap = fetch_fn(ticker)
        if cap is None and source == "yfinance":
            # cross-check fallback: try NSE if Yahoo didn't have it
            cap = _fetch_market_cap_nse(ticker)
        if cap is not None:
            caps[ticker] = cap
        time.sleep(delay)
    return caps
