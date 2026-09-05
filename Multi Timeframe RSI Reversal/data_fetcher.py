"""
data_fetcher.py
---------------
Downloads Daily OHLCV for the full NSE universe (Bhavcopy primary,
yfinance fallback) and resamples to Weekly and Monthly bars for
multi-timeframe RSI calculation.

Strategy: Multi-Timeframe RSI Reversal
"""

import os
import io
import time
import zipfile
import requests
import numpy as np
from datetime import datetime, timedelta


# ── Cache dir ─────────────────────────────────────────────────────────────────
CACHE_DIR = os.path.join(os.path.expanduser("~"), ".reversal_screener_cache")

# ── Shared symbol list from the existing uptrend system ───────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
NSE_SYMBOLS_FILE = os.path.join(
    _HERE, "..", "stocks_monitoring_and_notifying", "nse_symbols.txt"
)


class DataFetcher:
    """Fetches and resamples NSE OHLCV data for the reversal strategy universe."""

    def __init__(self):
        self.session = None
        os.makedirs(CACHE_DIR, exist_ok=True)

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    def _init_session(self):
        if self.session is None:
            self.session = requests.Session()
            self.session.headers.update({
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Connection": "keep-alive",
            })
            try:
                self.session.get("https://www.nseindia.com", timeout=10)
            except Exception as exc:
                print(f"[warn] NSE session warm-up failed: {exc}")

    # ------------------------------------------------------------------
    # Bhavcopy helpers (same as existing system)
    # ------------------------------------------------------------------

    @staticmethod
    def _bhavcopy_url(date: datetime) -> str:
        ds = date.strftime("%Y%m%d")
        return (
            f"https://nsearchives.nseindia.com/content/cm/"
            f"BhavCopy_NSE_CM_0_0_0_{ds}_F_0000.csv.zip"
        )

    def _fetch_bhavcopy_day(self, date: datetime, retries: int = 2):
        """Download (or load cached) one day of Bhavcopy data.

        Returns list of dicts with keys: symbol, open, high, low, close, volume.
        Returns None on weekends / holidays / network errors.
        """
        import csv

        cache_path = os.path.join(CACHE_DIR, f"bhavcopy_{date.strftime('%Y%m%d')}.csv")
        raw_text = None

        if os.path.exists(cache_path):
            try:
                with open(cache_path, "r", encoding="utf-8") as fh:
                    raw_text = fh.read()
            except Exception:
                raw_text = None

        if raw_text is None:
            self._init_session()
            url = self._bhavcopy_url(date)
            for attempt in range(retries + 1):
                try:
                    resp = self.session.get(url, timeout=20)
                    if resp.status_code == 404:
                        return None
                    resp.raise_for_status()
                    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
                        raw_text = zf.read(zf.namelist()[0]).decode("utf-8")
                    with open(cache_path, "w", encoding="utf-8") as fh:
                        fh.write(raw_text)
                    break
                except Exception as exc:
                    if attempt < retries:
                        time.sleep(1.5)
                        continue
                    print(f"[warn] Bhavcopy fetch failed for {date.strftime('%Y-%m-%d')}: {exc}")
                    return None

        if raw_text is None:
            return None

        reader = csv.DictReader(io.StringIO(raw_text))
        headers = [h.strip().upper() for h in (reader.fieldnames or [])]
        reader.fieldnames = headers

        if "TCKRSYMB" in headers:
            sym_col, open_col, high_col, low_col, close_col = (
                "TCKRSYMB", "OPNPRIC", "HGHPRIC", "LWPRIC", "CLSPRIC"
            )
            vol_col    = "TTLTRDQTY"
            series_col = "SCTYSRS"
        else:
            sym_col   = "SYMBOL"
            open_col  = "OPEN"  if "OPEN"  in headers else "OPEN_PRICE"
            high_col  = "HIGH"  if "HIGH"  in headers else "HIGH_PRICE"
            low_col   = "LOW"   if "LOW"   in headers else "LOW_PRICE"
            close_col = "CLOSE" if "CLOSE" in headers else "CLOSE_PRICE"
            vol_col   = "TOTTRDQTY" if "TOTTRDQTY" in headers else "TTL_TRD_QNTY"
            series_col = "SERIES"

        equity_series = {"EQ", "BE", "SM", "ST"}
        rows = []
        for row in reader:
            if series_col in row and row[series_col].strip() not in equity_series:
                continue
            try:
                rows.append({
                    "symbol": row[sym_col].strip(),
                    "open":   float(row.get(open_col,  0) or 0),
                    "high":   float(row.get(high_col,  0) or 0),
                    "low":    float(row.get(low_col,   0) or 0),
                    "close":  float(row[close_col]),
                    "volume": float(row.get(vol_col,   0) or 0),
                })
            except (ValueError, KeyError):
                continue

        return rows

    # ------------------------------------------------------------------
    # Resampling helpers
    # ------------------------------------------------------------------

    @staticmethod
    def resample_to_weekly(daily: dict) -> dict:
        """Group daily OHLCV into weekly bars (week = Mon–Fri, Friday close).

        Parameters
        ----------
        daily : dict  with keys 'dates','open','high','low','close','volume'
                      all numpy arrays of the same length, sorted oldest→newest.

        Returns
        -------
        dict  with same keys, resampled to weekly bars.
        """
        dates   = daily["dates"]
        opens   = daily["open"]
        highs   = daily["high"]
        lows    = daily["low"]
        closes  = daily["close"]
        volumes = daily["volume"]

        # Group by ISO week number (year-week)
        from datetime import date as _date
        week_keys = []
        for d in dates:
            dt = datetime.strptime(d, "%Y-%m-%d")
            iso = dt.isocalendar()          # (year, week, weekday)
            week_keys.append((iso[0], iso[1]))

        w_dates, w_open, w_high, w_low, w_close, w_vol = [], [], [], [], [], []
        i = 0
        while i < len(week_keys):
            key = week_keys[i]
            # Collect all days in this week
            j = i
            while j < len(week_keys) and week_keys[j] == key:
                j += 1
            # Aggregate
            w_dates.append(dates[j - 1])        # Friday (last day of week)
            w_open.append(opens[i])             # Monday open
            w_high.append(float(np.max(highs[i:j])))
            w_low.append(float(np.min(lows[i:j])))
            w_close.append(closes[j - 1])       # Friday close
            w_vol.append(float(np.sum(volumes[i:j])))
            i = j

        return {
            "dates":  np.array(w_dates),
            "open":   np.array(w_open,   dtype=float),
            "high":   np.array(w_high,   dtype=float),
            "low":    np.array(w_low,    dtype=float),
            "close":  np.array(w_close,  dtype=float),
            "volume": np.array(w_vol,    dtype=float),
        }

    @staticmethod
    def resample_to_monthly(daily: dict) -> dict:
        """Group daily OHLCV into monthly bars (last trading day of each month).

        Parameters / Returns — same structure as resample_to_weekly().
        """
        dates   = daily["dates"]
        opens   = daily["open"]
        highs   = daily["high"]
        lows    = daily["low"]
        closes  = daily["close"]
        volumes = daily["volume"]

        # Group by year-month
        month_keys = []
        for d in dates:
            dt = datetime.strptime(d, "%Y-%m-%d")
            month_keys.append((dt.year, dt.month))

        m_dates, m_open, m_high, m_low, m_close, m_vol = [], [], [], [], [], []
        i = 0
        while i < len(month_keys):
            key = month_keys[i]
            j = i
            while j < len(month_keys) and month_keys[j] == key:
                j += 1
            m_dates.append(dates[j - 1])
            m_open.append(opens[i])
            m_high.append(float(np.max(highs[i:j])))
            m_low.append(float(np.min(lows[i:j])))
            m_close.append(closes[j - 1])
            m_vol.append(float(np.sum(volumes[i:j])))
            i = j

        return {
            "dates":  np.array(m_dates),
            "open":   np.array(m_open,   dtype=float),
            "high":   np.array(m_high,   dtype=float),
            "low":    np.array(m_low,    dtype=float),
            "close":  np.array(m_close,  dtype=float),
            "volume": np.array(m_vol,    dtype=float),
        }

    # ------------------------------------------------------------------
    # yfinance fallback
    # ------------------------------------------------------------------

    def _fetch_yfinance_fallback(self, period_days: int, progress_callback=None, symbols=None) -> dict:
        """Fallback to Yahoo Finance if Bhavcopy is blocked or returns 0 symbols."""
        try:
            import yfinance as yf
        except ImportError:
            print("[error] yfinance not installed. Cannot use fallback.")
            return {}

        symbols_file = NSE_SYMBOLS_FILE
        if not os.path.exists(symbols_file):
            # Try local copy as last resort
            local = os.path.join(_HERE, "nse_symbols.txt")
            if os.path.exists(local):
                symbols_file = local
            else:
                print("[error] nse_symbols.txt not found. Cannot use fallback.")
                return {}

        if symbols is not None:
            base_symbols = symbols
        else:
            with open(symbols_file, "r", encoding="utf-8") as f:
                base_symbols = [line.strip() for line in f if line.strip()]

        if not base_symbols:
            return {}

        yf_symbols  = [f"{s}.NS" for s in base_symbols]
        period_str  = "2y" if period_days > 250 else "1y"

        print(f"[info] Falling back to yfinance for {len(yf_symbols)} stocks (period={period_str})...")

        data = yf.download(
            yf_symbols, period=period_str,
            group_by="ticker", threads=True, progress=False
        )

        result = {}
        min_required = int(period_days * 0.8)

        for i, (base_sym, yf_sym) in enumerate(zip(base_symbols, yf_symbols)):
            try:
                df = data[yf_sym].dropna(how="all") if len(yf_symbols) > 1 else data.dropna(how="all")
            except (KeyError, TypeError):
                continue

            if len(df) < min_required:
                continue

            df = df.tail(period_days)
            date_strs = [d.strftime("%Y-%m-%d") for d in df.index]

            result[base_sym] = {
                "dates":  np.array(date_strs),
                "open":   df["Open"].to_numpy(dtype=float),
                "high":   df["High"].to_numpy(dtype=float),
                "low":    df["Low"].to_numpy(dtype=float),
                "close":  df["Close"].to_numpy(dtype=float),
                "volume": df["Volume"].to_numpy(dtype=float),
            }

            if progress_callback and i % 500 == 0:
                progress_callback(i, len(base_symbols))

        print(f"[info] yfinance fallback complete: {len(result)} symbols acquired.")
        return result

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fetch_all_universe(
        self,
        period_days: int = 420,
        progress_callback=None,
        symbols: list = None,
    ) -> dict:
        """Download Bhavcopies and aggregate OHLCV for all (or specified) symbols.

        Parameters
        ----------
        period_days : int
            Number of *trading* days of daily history to fetch.
            Default 420 gives ~20 months — enough for Monthly RSI(14).
        progress_callback : callable, optional
            Called as ``callback(current_day, total_days)`` during fetch.
        symbols : list[str], optional
            If provided, only return data for these symbols (useful for
            intraday / hourly re-checks of watchlist names).

        Returns
        -------
        dict
            ``{
                "SYMBOL": {
                    "daily":   {"dates": np.array, "open": …, "high": …,
                                "low": …, "close": …, "volume": …},
                    "weekly":  {same keys, resampled},
                    "monthly": {same keys, resampled}
                }
            }``
        """
        records: dict[str, list] = {}
        today = datetime.now()
        days_collected = 0
        days_checked   = 0
        calendar_days_needed = int(period_days * 1.6) + 15

        while days_collected < period_days and days_checked < calendar_days_needed:
            day = today - timedelta(days=days_checked + 1)
            days_checked += 1

            if day.weekday() >= 5:
                continue

            rows = self._fetch_bhavcopy_day(day)
            if rows is None:
                continue

            day_str = day.strftime("%Y-%m-%d")
            for entry in rows:
                if symbols and entry["symbol"] not in symbols:
                    continue
                records.setdefault(entry["symbol"], []).append((
                    day_str,
                    entry["open"], entry["high"],
                    entry["low"],  entry["close"],
                    entry["volume"],
                ))

            days_collected += 1
            if progress_callback:
                progress_callback(days_collected, period_days)

        # Build daily arrays (sorted oldest → newest)
        min_required = int(period_days * 0.8)
        daily_universe: dict[str, dict] = {}

        for sym, pts in records.items():
            if len(pts) < min_required:
                continue
            pts.sort(key=lambda p: p[0])
            daily_universe[sym] = {
                "dates":  np.array([p[0] for p in pts]),
                "open":   np.array([p[1] for p in pts], dtype=float),
                "high":   np.array([p[2] for p in pts], dtype=float),
                "low":    np.array([p[3] for p in pts], dtype=float),
                "close":  np.array([p[4] for p in pts], dtype=float),
                "volume": np.array([p[5] for p in pts], dtype=float),
            }

        if not daily_universe:
            print("[warn] Bhavcopy yielded 0 results - falling back to yfinance (may be slow)...")
            daily_universe = self._fetch_yfinance_fallback(period_days, progress_callback, symbols=symbols)

        # Resample to weekly and monthly
        result: dict[str, dict] = {}
        for sym, daily in daily_universe.items():
            weekly  = self.resample_to_weekly(daily)
            monthly = self.resample_to_monthly(daily)
            # Need at least 14 monthly bars for RSI(14)
            if len(monthly["close"]) < 14:
                continue
            result[sym] = {
                "daily":   daily,
                "weekly":  weekly,
                "monthly": monthly,
            }

        print(f"[info] Universe ready: {len(result)} symbols with D/W/M bars.")
        return result
