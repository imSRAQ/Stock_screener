"""
uptrend_analyzer.py
-------------------
Applies a 6-layer filter pipeline to the full NSE universe and ranks
the surviving stocks by the aggressiveness of their uptrend.

Filter Pipeline (applied in order):
    1. SMA Filter       : Close > SMA_short > SMA_long
    2. Volume Filter    : Current volume > 20-day average volume
    3. RSI Filter       : RSI(14) between rsi_min and rsi_max
    4. ADX Filter       : ADX(14) > adx_min
    5. Multi-Timeframe  : Weekly Close > Weekly 50-SMA (optional)
    6. Slope Ranking    : Linear regression slope over lookback_days

Stop-loss is computed using the smarter of ATR or Volume Profile POC.
"""

import numpy as np
from technical_indicators import TechnicalIndicators
from volume_profile import VolumeProfiler


class UptrendAnalyzer:
    """Filters and ranks stocks using a multi-indicator uptrend scan."""

    def __init__(
        self,
        sma_short: int = 50,
        sma_long: int = 200,
        rsi_min: float = 40.0,
        rsi_max: float = 65.0,
        adx_min: float = 25.0,
        volume_ratio_min: float = 1.0,
        atr_multiplier: float = 1.5,
        multi_timeframe: bool = True,
        use_volume_profile_stop: bool = True,
    ):
        self.sma_short = sma_short
        self.sma_long = sma_long
        self.rsi_min = rsi_min
        self.rsi_max = rsi_max
        self.adx_min = adx_min
        self.volume_ratio_min = volume_ratio_min
        self.atr_multiplier = atr_multiplier
        self.multi_timeframe = multi_timeframe
        self.use_volume_profile_stop = use_volume_profile_stop
        self.ti = TechnicalIndicators()
        self.vp = VolumeProfiler()

    # ------------------------------------------------------------------
    # SMA helper
    # ------------------------------------------------------------------

    @staticmethod
    def _sma(prices: np.ndarray, window: int) -> float | None:
        """Simple moving average of the last *window* values."""
        if len(prices) < window:
            return None
        return float(np.mean(prices[-window:]))

    # ------------------------------------------------------------------
    # Slope (linear regression)
    # ------------------------------------------------------------------

    @staticmethod
    def _slope(prices: np.ndarray, window: int) -> float:
        """Normalised linear-regression slope over the last *window* days.

        Normalising by (mean, std) makes slopes comparable across
        stocks with very different price levels.
        """
        if len(prices) < window:
            return 0.0

        y = prices[-window:]
        std = np.std(y)
        if std == 0:
            return 0.0

        y_norm = (y - np.mean(y)) / std
        x = np.arange(len(y_norm))
        slope, _ = np.polyfit(x, y_norm, 1)
        return float(slope)

    # ------------------------------------------------------------------
    # Weekly resampling for multi-timeframe analysis
    # ------------------------------------------------------------------

    @staticmethod
    def _resample_to_weekly(closes: np.ndarray) -> np.ndarray:
        """Resample daily closes to approximate weekly closes.

        Takes every 5th value as a weekly close.  This is a lightweight
        approximation that avoids needing pandas or date alignment.
        """
        if len(closes) < 10:
            return closes
        # Take every 5th element (end of each trading week)
        weekly = closes[::5]
        # Make sure the very last daily close is included
        if len(closes) % 5 != 0:
            weekly = np.append(weekly, closes[-1])
        return weekly

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def filter_and_rank(
        self,
        universe_data: dict,
        lookback_days: int = 90,
    ) -> list[dict]:
        """Apply the 6-layer filter and return ranked results.

        Parameters
        ----------
        universe_data : dict
            ``{ 'SYMBOL': { 'close': np.array, 'high': np.array,
            'low': np.array, 'volume': np.array } }``
        lookback_days : int
            Window for slope calculation (default 90).

        Returns
        -------
        list[dict]
            Sorted by slope (most aggressive first).  Each dict
            contains: symbol, price, sma_50, sma_200, slope, rsi,
            adx, atr, volume_ratio, stop_loss, stop_method, poc_price.
        """
        results: list[dict] = []

        for symbol, data in universe_data.items():
            # Support both old format (np.array of closes) and new
            # OHLCV dict format
            if isinstance(data, dict):
                closes = data["close"]
                highs = data.get("high", closes)
                lows = data.get("low", closes)
                volumes = data.get("volume", np.zeros_like(closes))
            else:
                # Backwards compatibility: plain array of close prices
                closes = data
                highs = closes
                lows = closes
                volumes = np.zeros_like(closes)

            if len(closes) < self.sma_long:
                continue

            current_price = float(closes[-1])

            # ── Layer 1: SMA filter ──────────────────────────────────
            sma_short_val = self._sma(closes, self.sma_short)
            sma_long_val = self._sma(closes, self.sma_long)
            if sma_short_val is None or sma_long_val is None:
                continue
            if not (current_price > sma_short_val > sma_long_val):
                continue

            # ── Layer 2: Volume confirmation ─────────────────────────
            volume_ratio = self.ti.compute_volume_ratio(volumes)
            if np.isnan(volume_ratio):
                volume_ratio = 0.0
            # Only filter on volume when we have real volume data
            if np.any(volumes > 0) and volume_ratio < self.volume_ratio_min:
                continue

            # ── Layer 3: RSI zone filter ─────────────────────────────
            rsi = self.ti.compute_rsi(closes)
            if np.isnan(rsi):
                rsi = 50.0  # neutral default
            if not (self.rsi_min <= rsi <= self.rsi_max):
                continue

            # ── Layer 4: ADX trend-strength filter ───────────────────
            adx = self.ti.compute_adx(highs, lows, closes)
            if np.isnan(adx):
                adx = 0.0
            if adx < self.adx_min:
                continue

            # ── Layer 5: Multi-Timeframe Alignment ───────────────────
            if self.multi_timeframe:
                weekly_closes = self._resample_to_weekly(closes)
                weekly_sma50 = self._sma(weekly_closes, 10)  # ~50 daily ≈ 10 weekly
                if weekly_sma50 is not None:
                    weekly_price = float(weekly_closes[-1])
                    if weekly_price < weekly_sma50:
                        continue  # Weekly trend is not bullish

            # ── Layer 6: Slope ranking ───────────────────────────────
            slope = self._slope(closes, lookback_days)

            # ── Smart stop-loss (ATR vs Volume Profile) ──────────────
            atr = self.ti.compute_atr(highs, lows, closes)
            if np.isnan(atr):
                atr = 0.0

            stop_method = "ATR"
            poc_price = 0.0

            if self.use_volume_profile_stop and np.any(volumes > 0):
                sl_data = self.vp.compute_smart_stop_loss(
                    highs, lows, closes, volumes,
                    atr=atr,
                    atr_multiplier=self.atr_multiplier,
                    lookback=lookback_days,
                )
                stop_loss = sl_data["stop_loss"]
                stop_method = sl_data["method"]
                poc_price = sl_data["poc_price"]
            else:
                stop_loss = current_price - (self.atr_multiplier * atr)

            results.append({
                "symbol": symbol,
                "price": current_price,
                "sma_50": sma_short_val,
                "sma_200": sma_long_val,
                "slope": slope,
                "rsi": round(rsi, 1),
                "adx": round(adx, 1),
                "atr": round(atr, 2),
                "volume_ratio": round(volume_ratio, 2),
                "stop_loss": round(stop_loss, 2),
                "stop_method": stop_method,
                "poc_price": round(poc_price, 2),
            })

        # Sort by slope descending (most aggressive uptrend first)
        results.sort(key=lambda x: x["slope"], reverse=True)
        return results

