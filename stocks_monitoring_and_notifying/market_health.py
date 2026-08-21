"""
market_health.py
----------------
Checks the overall market health by analyzing the Nifty 50 index.
When Nifty 50 is below its 50-day SMA, the market is considered
bearish and all entry signals should be suppressed.
"""

import numpy as np

try:
    import yfinance as yf
except ImportError:
    yf = None


class MarketHealthChecker:
    """Determines whether the broad Indian market is healthy for new entries.

    Uses the Nifty 50 index (^NSEI on Yahoo Finance) as the benchmark.
    """

    NIFTY_TICKER = "^NSEI"
    SMA_PERIOD = 50

    def __init__(self):
        self._nifty_close: float | None = None
        self._nifty_sma50: float | None = None
        self._is_bullish: bool | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check(self) -> dict:
        """Fetch Nifty 50 data and determine market health.

        Returns
        -------
        dict
            {
                "is_bullish": bool,
                "nifty_close": float,
                "nifty_sma50": float,
                "status_emoji": str,    # "🟢" or "🔴"
                "status_text": str,
            }
        """
        if yf is None:
            # yfinance not installed — assume bullish to avoid blocking
            return self._fallback("yfinance not installed — defaulting to bullish")

        try:
            ticker = yf.Ticker(self.NIFTY_TICKER)
            hist = ticker.history(period="6mo")

            if hist.empty or len(hist) < self.SMA_PERIOD:
                return self._fallback("Insufficient Nifty 50 data")

            closes = hist["Close"].values
            self._nifty_close = float(closes[-1])
            self._nifty_sma50 = float(np.mean(closes[-self.SMA_PERIOD :]))
            self._is_bullish = self._nifty_close > self._nifty_sma50

            if self._is_bullish:
                return {
                    "is_bullish": True,
                    "nifty_close": self._nifty_close,
                    "nifty_sma50": self._nifty_sma50,
                    "status_emoji": "🟢",
                    "status_text": (
                        f"MARKET HEALTH: BULLISH — Nifty 50 "
                        f"({self._nifty_close:,.0f}) above 50-SMA "
                        f"({self._nifty_sma50:,.0f})"
                    ),
                }
            else:
                return {
                    "is_bullish": False,
                    "nifty_close": self._nifty_close,
                    "nifty_sma50": self._nifty_sma50,
                    "status_emoji": "🔴",
                    "status_text": (
                        f"MARKET HEALTH: BEARISH — Nifty 50 "
                        f"({self._nifty_close:,.0f}) below 50-SMA "
                        f"({self._nifty_sma50:,.0f}). "
                        f"No new entries recommended."
                    ),
                }

        except Exception as exc:
            return self._fallback(f"Error fetching Nifty 50: {exc}")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _fallback(reason: str) -> dict:
        """Return a neutral/bullish result when data is unavailable."""
        return {
            "is_bullish": True,
            "nifty_close": None,
            "nifty_sma50": None,
            "status_emoji": "⚪",
            "status_text": f"MARKET HEALTH: UNKNOWN — {reason}",
        }
