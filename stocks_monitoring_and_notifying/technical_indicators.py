"""
technical_indicators.py
-----------------------
Pure calculation utilities for technical indicators used by the
uptrend analyzer.  All functions accept numpy arrays and return
scalar float values (the most recent indicator reading).
"""

import numpy as np


class TechnicalIndicators:
    """Stateless collection of technical-indicator calculations."""

    # ------------------------------------------------------------------
    # RSI  (Relative Strength Index)
    # ------------------------------------------------------------------

    @staticmethod
    def compute_rsi(closes: np.ndarray, period: int = 14) -> float:
        """Calculate the most recent RSI value.

        Parameters
        ----------
        closes : np.ndarray
            Array of close prices (oldest → newest).
        period : int
            Look-back window (default 14).

        Returns
        -------
        float
            RSI value between 0 and 100, or NaN if insufficient data.
        """
        if len(closes) < period + 1:
            return np.nan

        deltas = np.diff(closes)
        gains = np.where(deltas > 0, deltas, 0.0)
        losses = np.where(deltas < 0, -deltas, 0.0)

        # Wilder's smoothed moving average (exponential, alpha = 1/period)
        avg_gain = np.mean(gains[:period])
        avg_loss = np.mean(losses[:period])

        for i in range(period, len(gains)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period

        if avg_loss == 0:
            return 100.0

        rs = avg_gain / avg_loss
        return float(100.0 - (100.0 / (1.0 + rs)))

    # ------------------------------------------------------------------
    # ADX  (Average Directional Index)
    # ------------------------------------------------------------------

    @staticmethod
    def compute_adx(
        high: np.ndarray,
        low: np.ndarray,
        close: np.ndarray,
        period: int = 14,
    ) -> float:
        """Calculate the most recent ADX value.

        Parameters
        ----------
        high, low, close : np.ndarray
            OHLC arrays (oldest → newest), must be same length.
        period : int
            Look-back window (default 14).

        Returns
        -------
        float
            ADX value (0–100), or NaN if insufficient data.
        """
        n = len(high)
        if n < 2 * period + 1:
            return np.nan

        # True Range
        tr = np.maximum(
            high[1:] - low[1:],
            np.maximum(
                np.abs(high[1:] - close[:-1]),
                np.abs(low[1:] - close[:-1]),
            ),
        )

        # Directional Movement
        up_move = high[1:] - high[:-1]
        down_move = low[:-1] - low[1:]
        plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
        minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

        # Wilder smoothing helper
        def _wilder_smooth(arr: np.ndarray, p: int) -> np.ndarray:
            smoothed = np.empty(len(arr) - p + 1)
            smoothed[0] = np.sum(arr[:p])
            for i in range(1, len(smoothed)):
                smoothed[i] = smoothed[i - 1] - smoothed[i - 1] / p + arr[p + i - 1]
            return smoothed

        atr = _wilder_smooth(tr, period)
        plus_di = 100.0 * _wilder_smooth(plus_dm, period) / (atr + 1e-10)
        minus_di = 100.0 * _wilder_smooth(minus_dm, period) / (atr + 1e-10)

        dx = 100.0 * np.abs(plus_di - minus_di) / (plus_di + minus_di + 1e-10)

        # ADX = Wilder-smoothed DX
        if len(dx) < period:
            return np.nan

        adx_arr = _wilder_smooth(dx, period) / period  # normalize
        return float(adx_arr[-1])

    # ------------------------------------------------------------------
    # ATR  (Average True Range)
    # ------------------------------------------------------------------

    @staticmethod
    def compute_atr(
        high: np.ndarray,
        low: np.ndarray,
        close: np.ndarray,
        period: int = 14,
    ) -> float:
        """Calculate the most recent ATR value.

        Parameters
        ----------
        high, low, close : np.ndarray
            OHLC arrays (oldest → newest).
        period : int
            Look-back window (default 14).

        Returns
        -------
        float
            ATR value, or NaN if insufficient data.
        """
        if len(high) < period + 1:
            return np.nan

        tr = np.maximum(
            high[1:] - low[1:],
            np.maximum(
                np.abs(high[1:] - close[:-1]),
                np.abs(low[1:] - close[:-1]),
            ),
        )

        # Wilder's smoothed ATR
        atr_val = np.mean(tr[:period])
        for i in range(period, len(tr)):
            atr_val = (atr_val * (period - 1) + tr[i]) / period

        return float(atr_val)

    # ------------------------------------------------------------------
    # Volume Ratio
    # ------------------------------------------------------------------

    @staticmethod
    def compute_volume_ratio(volume: np.ndarray, period: int = 20) -> float:
        """Return ratio of latest volume to the `period`-day average.

        A value > 1.0 means today's volume is above the recent average,
        confirming the price move.

        Returns
        -------
        float
            Volume ratio, or NaN if insufficient data.
        """
        if len(volume) < period + 1:
            return np.nan

        avg_vol = np.mean(volume[-period - 1 : -1])  # exclude today
        if avg_vol == 0:
            return np.nan

        return float(volume[-1] / avg_vol)
