"""
data_fetcher.py
---------------
Downloads and caches NSE Bhavcopy data for the entire stock universe.
Returns OHLCV data (Open, High, Low, Close, Volume) for each symbol.
"""

import os
import io
import time
import zipfile
import requests
import numpy as np
from datetime import datetime, timedelta


CACHE_DIR = os.path.join(os.path.expanduser("~"), ".nse_screener_cache")


class DataFetcher:
    """Fetches NSE Bhavcopy OHLCV data for the entire equity universe."""

    def __init__(self):
        self.session = None
        os.makedirs(CACHE_DIR, exist_ok=True)

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    def _init_session(self):
        """Create an HTTP session with NSE-compatible headers."""
        if self.session is None:
            self.session = requests.Session()
            self.session.headers.update({
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": (
                    "text/html,application/xhtml+xml,"
                    "application/xml;q=0.9,*/*;q=0.8"
                ),
                "Connection": "keep-alive",
            })
            try:
                self.session.get("https://www.nseindia.com", timeout=10)
            except Exception as exc:
                print(f"[warn] NSE session warm-up failed: {exc}")

    # ------------------------------------------------------------------
    # Bhavcopy helpers
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

        Returns a list of dicts with keys: symbol, open, high, low, close,
        volume.  Returns None on weekends / holidays / errors.
        """
        import csv

        cache_path = os.path.join(
            CACHE_DIR, f"bhavcopy_{date.strftime('%Y%m%d')}.csv"
        )

        raw_text = None

        # Try cache first
        if os.path.exists(cache_path):
            try:
                with open(cache_path, "r", encoding="utf-8") as fh:
                    raw_text = fh.read()
            except Exception:
                raw_text = None  # corrupted cache – re-download

        # Download if not cached
        if raw_text is None:
            self._init_session()
            url = self._bhavcopy_url(date)
            for attempt in range(retries + 1):
                try:
                    resp = self.session.get(url, timeout=20)
                    if resp.status_code == 404:
                        return None  # weekend or holiday
                    resp.raise_for_status()
                    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
                        csv_name = zf.namelist()[0]
                        raw_text = zf.read(csv_name).decode("utf-8")
                    # Save to cache
                    with open(cache_path, "w", encoding="utf-8") as fh:
                        fh.write(raw_text)
                    break
                except Exception as exc:
                    if attempt < retries:
                        time.sleep(1.5)
                        continue
                    print(
                        f"[warn] Bhavcopy fetch failed for "
                        f"{date.strftime('%Y-%m-%d')}: {exc}"
                    )
                    return None

        if raw_text is None:
            return None

        # Parse CSV
        reader = csv.DictReader(io.StringIO(raw_text))
        headers = [h.strip().upper() for h in reader.fieldnames or []]
        reader.fieldnames = headers

        # Detect column names (newer UDiFF vs older format)
        if "TCKRSYMB" in headers:
            sym_col, open_col, high_col, low_col, close_col = (
                "TCKRSYMB", "OPNPRIC", "HGHPRIC", "LWPRIC", "CLSPRIC"
            )
            vol_col = "TTLTRDQTY"
            series_col = "SCTYSRS"
        else:
            sym_col = "SYMBOL"
            open_col = "OPEN" if "OPEN" in headers else "OPEN_PRICE"
            high_col = "HIGH" if "HIGH" in headers else "HIGH_PRICE"
            low_col = "LOW" if "LOW" in headers else "LOW_PRICE"
            close_col = "CLOSE" if "CLOSE" in headers else "CLOSE_PRICE"
            vol_col = "TOTTRDQTY" if "TOTTRDQTY" in headers else "TTL_TRD_QNTY"
            series_col = "SERIES"

        required = [sym_col, close_col]
        if not all(c in headers for c in required):
            return None

        equity_series = {"EQ", "BE", "SM", "ST"}
        rows = []
        for row in reader:
            # Filter to equity series only
            if series_col in row and row[series_col].strip() not in equity_series:
                continue
            try:
                entry = {
                    "symbol": row[sym_col].strip(),
                    "open": float(row.get(open_col, 0) or 0),
                    "high": float(row.get(high_col, 0) or 0),
                    "low": float(row.get(low_col, 0) or 0),
                    "close": float(row[close_col]),
                    "volume": float(row.get(vol_col, 0) or 0),
                }
                rows.append(entry)
            except (ValueError, KeyError):
                continue

        return rows

    def _fetch_yfinance_fallback(self, period_days: int, progress_callback=None) -> dict:
        """Fallback to Yahoo Finance if NSE Bhavcopy is blocked."""
        try:
            import yfinance as yf
        except ImportError:
            print("[error] yfinance not installed. Cannot use fallback.")
            return {}

        symbols_file = os.path.join(os.path.dirname(__file__), "nse_symbols.txt")
        if not os.path.exists(symbols_file):
            print("[error] nse_symbols.txt not found. Cannot use fallback.")
            return {}

        with open(symbols_file, "r", encoding="utf-8") as f:
            base_symbols = [line.strip() for line in f if line.strip()]
        
        if not base_symbols:
            return {}
            
        yf_symbols = [f"{s}.NS" for s in base_symbols]
        period_str = "1y" if period_days <= 250 else "2y"
        
        print(f"[info] Falling back to yfinance for {len(yf_symbols)} stocks (period={period_str})...")
        print(f"[info] This takes a few minutes, please wait.")
        
        # Download all symbols in one go using threads
        data = yf.download(yf_symbols, period=period_str, group_by="ticker", threads=True, progress=False)
        
        result = {}
        min_required = int(period_days * 0.8)
        
        for i, (base_sym, yf_sym) in enumerate(zip(base_symbols, yf_symbols)):
            if len(yf_symbols) == 1:
                df = data.dropna(how="all")
            else:
                if yf_sym not in data:
                    continue
                df = data[yf_sym].dropna(how="all")
                
            if len(df) < min_required:
                continue
                
            # Keep only the last 'period_days' rows if we got more
            df = df.tail(period_days)
                
            result[base_sym] = {
                "open": df["Open"].to_numpy(dtype=float),
                "high": df["High"].to_numpy(dtype=float),
                "low": df["Low"].to_numpy(dtype=float),
                "close": df["Close"].to_numpy(dtype=float),
                "volume": df["Volume"].to_numpy(dtype=float),
            }
            
            if progress_callback and i % 500 == 0:
                progress_callback(i, len(base_symbols))
                
        print(f"[info] Fallback complete. Acquired data for {len(result)} stocks.")
        return result

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fetch_all_universe(
        self,
        period_days: int,
        progress_callback=None,
    ) -> dict:
        """Download Bhavcopies and aggregate OHLCV data for ALL symbols.

        Parameters
        ----------
        period_days : int
            Number of *trading* days of history to fetch.
        progress_callback : callable, optional
            Called as ``callback(current_day, total_days)`` during fetch.

        Returns
        -------
        dict
            ``{ 'SYMBOL': { 'close': np.array, 'high': np.array,
            'low': np.array, 'open': np.array, 'volume': np.array } }``

            Only symbols with at least 80% of the requested days are
            included.
        """
        records: dict[str, list] = {}
        today = datetime.now()
        days_collected = 0
        days_checked = 0
        calendar_days_needed = int(period_days * 1.6) + 15

        while days_collected < period_days and days_checked < calendar_days_needed:
            day = today - timedelta(days=days_checked + 1)
            days_checked += 1

            if day.weekday() >= 5:  # skip weekends
                continue

            rows = self._fetch_bhavcopy_day(day)
            if rows is None:
                continue

            day_str = day.strftime("%Y-%m-%d")
            for entry in rows:
                records.setdefault(entry["symbol"], []).append(
                    (
                        day_str,
                        entry["open"],
                        entry["high"],
                        entry["low"],
                        entry["close"],
                        entry["volume"],
                    )
                )

            days_collected += 1
            if progress_callback:
                progress_callback(days_collected, period_days)

        # Aggregate into numpy arrays (sorted oldest → newest)
        result = {}
        min_required = int(period_days * 0.8)

        for symbol, points in records.items():
            if len(points) < min_required:
                continue

            points.sort(key=lambda p: p[0])  # sort by date
            result[symbol] = {
                "open": np.array([p[1] for p in points], dtype=float),
                "high": np.array([p[2] for p in points], dtype=float),
                "low": np.array([p[3] for p in points], dtype=float),
                "close": np.array([p[4] for p in points], dtype=float),
                "volume": np.array([p[5] for p in points], dtype=float),
            }

        if not result:
            print("[warn] Bhavcopy yielded 0 results (possibly blocked). Falling back to yfinance...")
            return self._fetch_yfinance_fallback(period_days, progress_callback)

        return result
