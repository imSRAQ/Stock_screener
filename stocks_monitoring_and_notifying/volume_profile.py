"""
volume_profile.py
-----------------
Calculates the Volume Profile and Point of Control (POC) for stocks.
The POC is the price level where the most volume was traded over a
given lookback period — it represents institutional accumulation zones.
"""

import numpy as np


class VolumeProfiler:
    """Calculates Volume Profile and Point of Control (POC) for a stock."""

    def __init__(self, num_bins: int = 50):
        """
        Parameters
        ----------
        num_bins : int
            Number of price bins to divide the range into.
            More bins = finer granularity. 50 is a good default.
        """
        self.num_bins = num_bins

    def compute_profile(
        self,
        high: np.ndarray,
        low: np.ndarray,
        close: np.ndarray,
        volume: np.ndarray,
        lookback: int = 90,
    ) -> dict:
        """Compute the volume profile and POC for a stock.

        For each day, volume is distributed evenly across the price
        range [low, high].  The profile bins accumulate this volume
        and the bin with the highest total is the POC.

        Parameters
        ----------
        high, low, close, volume : np.ndarray
            OHLCV arrays (oldest → newest).
        lookback : int
            Number of recent trading days to analyze.

        Returns
        -------
        dict
            {
                "poc_price": float,       # Point of Control price
                "poc_volume": float,      # Volume at POC
                "value_area_high": float, # Upper boundary of 70% volume
                "value_area_low": float,  # Lower boundary of 70% volume
                "support_level": float,   # Suggested stop-loss level (just below POC)
                "profile": list[dict],    # Full profile for visualization
            }
        """
        # Use only the last `lookback` days
        n = min(lookback, len(high))
        h = high[-n:]
        l = low[-n:]
        c = close[-n:]
        v = volume[-n:]

        if n < 10:
            return self._empty_result(close[-1] if len(close) > 0 else 0)

        # Determine the price range
        price_min = float(np.min(l))
        price_max = float(np.max(h))

        if price_max <= price_min:
            return self._empty_result(float(c[-1]))

        # Create bins
        bin_edges = np.linspace(price_min, price_max, self.num_bins + 1)
        bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2
        bin_volumes = np.zeros(self.num_bins)

        # Distribute each day's volume across the bins it spans
        for i in range(n):
            day_low = l[i]
            day_high = h[i]
            day_vol = v[i]

            if day_vol <= 0 or day_high <= day_low:
                continue

            # Find which bins this day's range covers
            low_bin = np.searchsorted(bin_edges, day_low, side="right") - 1
            high_bin = np.searchsorted(bin_edges, day_high, side="left")

            low_bin = max(0, low_bin)
            high_bin = min(self.num_bins - 1, high_bin)

            num_covered = high_bin - low_bin + 1
            if num_covered > 0:
                vol_per_bin = day_vol / num_covered
                bin_volumes[low_bin : high_bin + 1] += vol_per_bin

        # Find POC (bin with highest volume)
        poc_idx = int(np.argmax(bin_volumes))
        poc_price = float(bin_centers[poc_idx])
        poc_volume = float(bin_volumes[poc_idx])

        # Calculate Value Area (70% of total volume, centered on POC)
        total_volume = np.sum(bin_volumes)
        target_volume = total_volume * 0.70

        # Expand outward from POC until we capture 70%
        va_low_idx = poc_idx
        va_high_idx = poc_idx
        accumulated = bin_volumes[poc_idx]

        while accumulated < target_volume and (va_low_idx > 0 or va_high_idx < self.num_bins - 1):
            # Check which side to expand
            expand_low = bin_volumes[va_low_idx - 1] if va_low_idx > 0 else 0
            expand_high = bin_volumes[va_high_idx + 1] if va_high_idx < self.num_bins - 1 else 0

            if expand_low >= expand_high and va_low_idx > 0:
                va_low_idx -= 1
                accumulated += bin_volumes[va_low_idx]
            elif va_high_idx < self.num_bins - 1:
                va_high_idx += 1
                accumulated += bin_volumes[va_high_idx]
            else:
                break

        value_area_low = float(bin_edges[va_low_idx])
        value_area_high = float(bin_edges[va_high_idx + 1])

        # Support level: just below POC (use the lower edge of the POC bin)
        support_level = float(bin_edges[poc_idx])

        # Build profile list for potential visualization
        profile = []
        for i in range(self.num_bins):
            profile.append({
                "price": round(float(bin_centers[i]), 2),
                "volume": round(float(bin_volumes[i]), 0),
            })

        return {
            "poc_price": round(poc_price, 2),
            "poc_volume": round(poc_volume, 0),
            "value_area_high": round(value_area_high, 2),
            "value_area_low": round(value_area_low, 2),
            "support_level": round(support_level, 2),
            "profile": profile,
        }

    @staticmethod
    def _empty_result(current_price: float) -> dict:
        """Fallback when insufficient data is available."""
        return {
            "poc_price": current_price,
            "poc_volume": 0,
            "value_area_high": current_price,
            "value_area_low": current_price,
            "support_level": current_price * 0.95,
            "profile": [],
        }

    def compute_smart_stop_loss(
        self,
        high: np.ndarray,
        low: np.ndarray,
        close: np.ndarray,
        volume: np.ndarray,
        atr: float,
        atr_multiplier: float = 1.5,
        lookback: int = 90,
    ) -> dict:
        """Compute a smart stop-loss that uses both ATR and Volume Profile.

        The stop-loss is placed at the higher of:
        - ATR-based stop: price - (atr_multiplier × ATR)
        - Volume Profile support: just below the POC

        This ensures the stop-loss respects institutional support levels.

        Returns
        -------
        dict
            {
                "stop_loss": float,
                "method": str,          # "ATR" or "VOLUME_PROFILE"
                "poc_price": float,
                "atr_stop": float,
                "vp_stop": float,
            }
        """
        current_price = float(close[-1]) if len(close) > 0 else 0
        atr_stop = current_price - (atr_multiplier * atr)

        profile = self.compute_profile(high, low, close, volume, lookback)
        vp_stop = profile["support_level"]

        # Use the HIGHER stop-loss (the more conservative one)
        # This keeps us closer to strong support
        if vp_stop > atr_stop and vp_stop < current_price:
            return {
                "stop_loss": round(vp_stop, 2),
                "method": "VOLUME_PROFILE",
                "poc_price": profile["poc_price"],
                "atr_stop": round(atr_stop, 2),
                "vp_stop": round(vp_stop, 2),
            }
        else:
            return {
                "stop_loss": round(atr_stop, 2),
                "method": "ATR",
                "poc_price": profile["poc_price"],
                "atr_stop": round(atr_stop, 2),
                "vp_stop": round(vp_stop, 2),
            }
