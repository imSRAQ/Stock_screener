"""
fundamental_filter.py
---------------------
Applies a fundamental quality gate to uptrend candidates.
Checks EPS, revenue growth, and debt-to-equity using yfinance.
Results are cached weekly to avoid redundant API calls.
"""

import os
import json
import time
from datetime import datetime, timedelta

try:
    import yfinance as yf
except ImportError:
    yf = None


class FundamentalFilter:
    """Checks fundamental health of stocks and caches results weekly."""

    def __init__(self):
        self.cache_file = os.path.join(
            os.path.dirname(__file__), "fundamental_cache.json"
        )
        self.cache: dict = {}
        self.cache_max_age_days = 7  # Refresh fundamentals weekly
        self._load_cache()

    # ------------------------------------------------------------------
    # Cache management
    # ------------------------------------------------------------------

    def _load_cache(self):
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    self.cache = json.load(f)
            except Exception:
                self.cache = {}

    def _save_cache(self):
        try:
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, indent=2)
        except Exception as e:
            print(f"[warn] Failed to save fundamental cache: {e}")

    def _is_stale(self, symbol: str) -> bool:
        """Check if a cached entry is older than cache_max_age_days."""
        if symbol not in self.cache:
            return True
        cached_date = self.cache[symbol].get("fetched_at", "")
        if not cached_date:
            return True
        try:
            fetched = datetime.fromisoformat(cached_date)
            return datetime.now() - fetched > timedelta(days=self.cache_max_age_days)
        except Exception:
            return True

    # ------------------------------------------------------------------
    # Data fetching
    # ------------------------------------------------------------------

    def _fetch_fundamentals(self, symbol: str) -> dict:
        """Fetch fundamental data from yfinance for a single stock."""
        if yf is None:
            return {"status": "UNKNOWN", "reason": "yfinance not installed"}

        yf_symbol = symbol if symbol.endswith(".NS") else f"{symbol}.NS"
        try:
            ticker = yf.Ticker(yf_symbol)
            info = ticker.info

            eps = info.get("trailingEps", None)
            revenue_growth = info.get("revenueGrowth", None)
            debt_equity = info.get("debtToEquity", None)
            market_cap = info.get("marketCap", None)
            sector = info.get("sector", "Unknown")

            return {
                "eps": eps,
                "revenue_growth": revenue_growth,
                "debt_to_equity": debt_equity,
                "market_cap": market_cap,
                "sector": sector,
                "fetched_at": datetime.now().isoformat(),
                "status": "OK",
            }
        except Exception as e:
            return {
                "status": "ERROR",
                "reason": str(e),
                "fetched_at": datetime.now().isoformat(),
            }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check(
        self,
        symbol: str,
        min_revenue_growth: float = 0.05,
        max_debt_equity: float = 1.5,
    ) -> dict:
        """Check the fundamental quality of a stock.

        Returns
        -------
        dict
            {
                "symbol": str,
                "fundamental_ok": bool,   # True = passes all checks
                "flags": list[str],       # Human-readable risk flags
                "data": dict,             # Raw fundamental data
            }
        """
        # Refresh cache if stale
        if self._is_stale(symbol):
            data = self._fetch_fundamentals(symbol)
            self.cache[symbol] = data
            self._save_cache()
            # Small delay to be kind to yfinance
            time.sleep(0.3)
        else:
            data = self.cache[symbol]

        if data.get("status") != "OK":
            return {
                "symbol": symbol,
                "fundamental_ok": True,  # Don't block on errors
                "flags": [f"⚠️ Fundamental data unavailable: {data.get('reason', 'unknown')}"],
                "data": data,
            }

        flags = []
        passes = True

        # Check EPS
        eps = data.get("eps")
        if eps is not None and eps <= 0:
            flags.append(f"🔴 Negative EPS ({eps})")
            passes = False

        # Check revenue growth
        rg = data.get("revenue_growth")
        if rg is not None and rg < min_revenue_growth:
            flags.append(f"🟡 Low Revenue Growth ({rg:.1%} < {min_revenue_growth:.0%})")
            passes = False

        # Check debt-to-equity
        de = data.get("debt_to_equity")
        if de is not None and de > max_debt_equity * 100:
            # yfinance returns D/E as a percentage (e.g. 150 for 1.5x)
            flags.append(f"🟡 High Debt/Equity ({de/100:.1f}x > {max_debt_equity:.1f}x)")
            passes = False

        if not flags:
            flags.append("✅ Fundamentals look healthy")

        return {
            "symbol": symbol,
            "fundamental_ok": passes,
            "flags": flags,
            "data": data,
        }

    def check_batch(
        self,
        symbols: list[str],
        min_revenue_growth: float = 0.05,
        max_debt_equity: float = 1.5,
    ) -> dict[str, dict]:
        """Check fundamentals for a list of symbols.

        Returns
        -------
        dict
            Mapping of symbol → check result.
        """
        results = {}
        for sym in symbols:
            results[sym] = self.check(sym, min_revenue_growth, max_debt_equity)
        return results
