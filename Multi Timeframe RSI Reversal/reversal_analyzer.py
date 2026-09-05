"""
reversal_analyzer.py
--------------------
Implements the Multi-Timeframe RSI Reversal Strategy (Rules 1–5).

Every symbol in the NSE universe passes through:
  Rule 1 — MTF RSI filter   : Monthly > 60, Weekly > 60, Daily 35–45
  Rule 2 — Signal candle     : Hammer / Doji / Engulfing / Harami /
                               Piercing / Morning Star (explainable OHLC functions)
  Rule 3 — Entry tag         : confirmed_entry (close > signal high) or
                               early_entry (signal found, no breakout yet)
  Rule 4 — Stop loss         : signal_candle_low or swing_low (config toggle)
  Rule 5 — Targets           : RSI-60 projected price + 1R partial level

Strategy: Multi-Timeframe RSI Reversal
"""

import math
import numpy as np
from typing import Optional


# ══════════════════════════════════════════════════════════════════════════════
# RSI helpers
# ══════════════════════════════════════════════════════════════════════════════

def _rsi(closes: np.ndarray, period: int = 14) -> float:
    """Wilder's smoothed RSI.  Returns NaN if not enough data."""
    if len(closes) < period + 1:
        return float("nan")

    deltas = np.diff(closes.astype(float))
    gains  = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)

    # Seed with simple average of first `period` bars
    avg_gain = float(np.mean(gains[:period]))
    avg_loss = float(np.mean(losses[:period]))

    # Wilder smoothing over the rest
    for g, l in zip(gains[period:], losses[period:]):
        avg_gain = (avg_gain * (period - 1) + g) / period
        avg_loss = (avg_loss * (period - 1) + l) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def _rsi_series(closes: np.ndarray, period: int = 14) -> np.ndarray:
    """Return full RSI array (same length as closes, NaN for first `period` bars)."""
    out = np.full(len(closes), float("nan"))
    if len(closes) < period + 1:
        return out

    deltas = np.diff(closes.astype(float))
    gains  = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)

    avg_gain = float(np.mean(gains[:period]))
    avg_loss = float(np.mean(losses[:period]))

    def _to_rsi(ag, al):
        if al == 0:
            return 100.0
        return 100.0 - 100.0 / (1.0 + ag / al)

    out[period] = _to_rsi(avg_gain, avg_loss)
    for i, (g, l) in enumerate(zip(gains[period:], losses[period:]), start=period + 1):
        avg_gain = (avg_gain * (period - 1) + g) / period
        avg_loss = (avg_loss * (period - 1) + l) / period
        out[i] = _to_rsi(avg_gain, avg_loss)

    return out


# ══════════════════════════════════════════════════════════════════════════════
# Signal candle pattern functions
# Each returns (qualified: bool, reason: str)
# ══════════════════════════════════════════════════════════════════════════════

def _range(o, h, l, c) -> float:
    return h - l if h != l else 1e-9

def _body(o, c) -> float:
    return abs(c - o)

def is_hammer(o: float, h: float, l: float, c: float) -> tuple[bool, str]:
    """Bullish hammer: small body in upper portion, long lower shadow."""
    rng = _range(o, h, l, c)
    body = _body(o, c)
    upper_shadow = h - max(o, c)
    lower_shadow = min(o, c) - l

    if body > 0.35 * rng:
        return False, "body too large for hammer"
    if lower_shadow < 2.0 * body:
        return False, "lower shadow < 2× body"
    if upper_shadow > 0.1 * rng:
        return False, "upper shadow too large"
    return True, f"Hammer: body={body:.2f}, lower_shadow={lower_shadow:.2f}"

def is_doji(o: float, h: float, l: float, c: float) -> tuple[bool, str]:
    """Doji: near-equal open and close."""
    rng = _range(o, h, l, c)
    body = _body(o, c)
    if body <= 0.10 * rng:
        return True, f"Doji: body={body:.2f} ≤ 10% of range={rng:.2f}"
    return False, "body too large for doji"

def is_bullish_engulfing(
    prev_o: float, prev_c: float, o: float, c: float
) -> tuple[bool, str]:
    """Bullish engulfing: prior bar bearish, current bar fully engulfs it bullishly."""
    if prev_c >= prev_o:
        return False, "prior candle not bearish"
    if c <= o:
        return False, "current candle not bullish"
    if o >= prev_c:
        return False, "current open above prior close"
    if c <= prev_o:
        return False, "current close below prior open"
    return True, f"Bullish Engulfing: prev body {prev_o:.2f}→{prev_c:.2f}, curr {o:.2f}→{c:.2f}"

def is_bullish_harami(
    prev_o: float, prev_c: float, o: float, c: float
) -> tuple[bool, str]:
    """Bullish harami: prior bar bearish, current body inside prior body, closes higher."""
    if prev_c >= prev_o:
        return False, "prior candle not bearish"
    prev_body_top = max(prev_o, prev_c)
    prev_body_bot = min(prev_o, prev_c)
    curr_top = max(o, c)
    curr_bot = min(o, c)
    if curr_bot < prev_body_bot or curr_top > prev_body_top:
        return False, "current body not inside prior body"
    if c <= o:
        return False, "current candle not bullish"
    return True, f"Bullish Harami: current body inside prior bearish body"

def is_piercing(
    prev_o: float, prev_l: float, prev_c: float, o: float, c: float
) -> tuple[bool, str]:
    """Piercing pattern: opens below prior low, closes above midpoint of prior bearish body."""
    if prev_c >= prev_o:
        return False, "prior candle not bearish"
    if o > prev_l:
        return False, "current open not below prior low"
    midpoint = (prev_o + prev_c) / 2.0
    if c <= midpoint:
        return False, "current close does not pierce above prior midpoint"
    if c >= prev_o:
        return False, "full engulf (not piercing — use engulfing rule)"
    return True, f"Piercing: opened at {o:.2f} (below prior low {prev_l:.2f}), closed at {c:.2f} > mid {midpoint:.2f}"

def is_morning_star(
    o0: float, c0: float,  # bar -2 (big bearish)
    o1: float, c1: float,  # bar -1 (small body / star)
    o2: float, c2: float,  # bar  0 (big bullish)
) -> tuple[bool, str]:
    """Morning star: 3-bar pattern — big bear, small/doji gap, big bull."""
    # Bar -2 must be bearish with meaningful body
    body0 = _body(o0, c0)
    if c0 >= o0 or body0 < 0.01 * o0:
        return False, "bar-2 not a meaningful bearish bar"
    # Bar -1 star: small body
    body1 = _body(o1, c1)
    if body1 >= 0.5 * body0:
        return False, "star body too large (>= 50% of prior bearish body)"
    # Bar 0 must be bullish and close above midpoint of bar -2
    if c2 <= o2:
        return False, "bar 0 not bullish"
    midpoint0 = (o0 + c0) / 2.0
    if c2 < midpoint0:
        return False, f"bar 0 close {c2:.2f} does not recover above midpoint {midpoint0:.2f}"
    return True, f"Morning Star: bearish {o0:.2f}→{c0:.2f}, star {o1:.2f}→{c1:.2f}, bullish {o2:.2f}→{c2:.2f}"


# ══════════════════════════════════════════════════════════════════════════════
# RSI-60 price projection
# ══════════════════════════════════════════════════════════════════════════════

def _project_rsi60_price(closes: np.ndarray, period: int = 14) -> Optional[float]:
    """Estimate the price at which RSI(14) would reach 60.

    Uses binary search: given recent close history, what hypothetical next
    close would push RSI to exactly 60?

    Returns None if the calculation is not feasible.
    """
    if len(closes) < period + 2:
        return None

    current_price = float(closes[-1])

    # Binary search between current price and 3× current price
    lo, hi = current_price, current_price * 3.0
    target_rsi = 60.0

    for _ in range(50):  # 50 iterations ≈ precision < 0.001
        mid = (lo + hi) / 2.0
        test_closes = np.append(closes, mid)
        rsi_val = _rsi(test_closes, period)
        if math.isnan(rsi_val):
            return None
        if rsi_val < target_rsi:
            lo = mid
        else:
            hi = mid

    projected = (lo + hi) / 2.0
    # Sanity: must be at least 1% above current price
    return projected if projected > current_price * 1.01 else None


# ══════════════════════════════════════════════════════════════════════════════
# Main analyzer class
# ══════════════════════════════════════════════════════════════════════════════

class ReversalAnalyzer:
    """Screens the NSE universe for Multi-Timeframe RSI Reversal setups.

    Usage
    -----
    analyzer = ReversalAnalyzer(config.filters, config.risk)
    candidates = analyzer.screen(universe_data)
    # candidates is a list of dicts sorted by rsi_daily ascending
    # (deepest pullback first — most actionable)
    """

    def __init__(self, filters: dict, risk: dict):
        self.rsi_monthly_min  = float(filters.get("rsi_monthly_min", 60))
        self.rsi_weekly_min   = float(filters.get("rsi_weekly_min",  60))
        self.rsi_daily_lo     = float(filters.get("rsi_daily_band", [35, 45])[0])
        self.rsi_daily_hi     = float(filters.get("rsi_daily_band", [35, 45])[1])
        self.sl_mode          = filters.get("sl_mode", "signal_candle_low")
        self.trailing_enabled = bool(filters.get("trailing_enabled", False))
        self.trailing_bar_cnt = int(filters.get("trailing_bar_count", 5))
        self.lookback_days    = int(filters.get("lookback_days", 400))
        self.reward_multiple  = float(risk.get("reward_multiple", 1.5))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def screen(self, universe_data: dict) -> list[dict]:
        """Apply Rules 1–5 to every symbol and return tagged candidates.

        Parameters
        ----------
        universe_data : dict
            Output of DataFetcher.fetch_all_universe():
            ``{"SYMBOL": {"daily": {...}, "weekly": {...}, "monthly": {...}}}``

        Returns
        -------
        list[dict]
            Candidates tagged `confirmed_entry` or `early_entry`.
            Sorted: confirmed_entry first, then by rsi_daily ascending
            (deepest pullback = most actionable setup first).
        """
        candidates = []

        for symbol, data in universe_data.items():
            result = self._analyze_symbol(symbol, data)
            if result is not None:
                candidates.append(result)

        # Sort: confirmed first, then by daily RSI ascending (deepest pullback)
        candidates.sort(
            key=lambda x: (0 if x["tag"] == "confirmed_entry" else 1, x["rsi_daily"])
        )
        return candidates

    # ------------------------------------------------------------------
    # Per-symbol analysis
    # ------------------------------------------------------------------

    def _analyze_symbol(self, symbol: str, data: dict) -> Optional[dict]:
        daily   = data.get("daily",   {})
        weekly  = data.get("weekly",  {})
        monthly = data.get("monthly", {})

        d_closes = daily.get("close",   np.array([]))
        w_closes = weekly.get("close",  np.array([]))
        m_closes = monthly.get("close", np.array([]))

        if len(d_closes) < 30 or len(w_closes) < 14 or len(m_closes) < 14:
            return None

        # ── Rule 1: Multi-Timeframe RSI filter ────────────────────────
        rsi_m = _rsi(m_closes, 14)
        rsi_w = _rsi(w_closes, 14)
        rsi_d = _rsi(d_closes, 14)

        if math.isnan(rsi_m) or math.isnan(rsi_w) or math.isnan(rsi_d):
            return None
        if rsi_m < self.rsi_monthly_min:
            return None
        if rsi_w < self.rsi_weekly_min:
            return None
        if not (self.rsi_daily_lo <= rsi_d <= self.rsi_daily_hi):
            return None

        # ── Rule 2: Signal candle detection ───────────────────────────
        d_opens  = daily.get("open",  d_closes)
        d_highs  = daily.get("high",  d_closes)
        d_lows   = daily.get("low",   d_closes)

        # Scan the most recent `lookback_days` bars for a signal candle
        lookback = min(self.lookback_days, len(d_closes) - 3)
        candle_idx, candle_pattern, candle_reason = self._find_signal_candle(
            d_opens, d_highs, d_lows, d_closes, lookback
        )

        if candle_idx is None:
            return None  # No qualifying signal candle found

        signal_date  = daily.get("dates", np.array([]))[candle_idx] if len(daily.get("dates", [])) > candle_idx else "unknown"
        signal_high  = float(d_highs[candle_idx])
        signal_low   = float(d_lows[candle_idx])
        current_price = float(d_closes[-1])

        # ── Rule 3: Entry tag ─────────────────────────────────────────
        # confirmed_entry: most recent close (after signal candle) > signal high
        tag = "early_entry"
        if len(d_closes) > candle_idx + 1:
            # Check if any close AFTER the signal candle broke out
            post_signal_closes = d_closes[candle_idx + 1:]
            if len(post_signal_closes) > 0 and float(post_signal_closes[-1]) > signal_high:
                tag = "confirmed_entry"

        entry = signal_high  # breakout level = signal candle high

        # ── Rule 4: Stop loss ─────────────────────────────────────────
        if self.sl_mode == "swing_low":
            # Lowest low of recent swing (last trailing_bar_count bars before signal)
            start = max(0, candle_idx - self.trailing_bar_cnt)
            sl = float(np.min(d_lows[start: candle_idx + 1]))
        else:
            # Default: low of the signal candle
            sl = signal_low

        if sl >= entry:
            return None   # Degenerate setup — skip

        risk_per_share = entry - sl

        # ── Rule 5: Targets ───────────────────────────────────────────
        target_1r    = round(entry + self.reward_multiple * risk_per_share, 2)
        target_rsi60 = _project_rsi60_price(d_closes, period=14)
        if target_rsi60 is None:
            target_rsi60 = target_1r  # fallback: use 1R level

        return {
            "symbol":                symbol,
            "tag":                   tag,
            "price":                 round(current_price, 2),
            "signal_candle_idx":     candle_idx,
            "signal_candle_date":    str(signal_date),
            "signal_candle_pattern": candle_pattern,
            "signal_candle_reason":  candle_reason,
            "entry":                 round(entry, 2),
            "sl":                    round(sl, 2),
            "risk_per_share":        round(risk_per_share, 2),
            "target_rsi60":          round(target_rsi60, 2),
            "target_1r":             target_1r,
            "rsi_daily":             round(rsi_d, 1),
            "rsi_weekly":            round(rsi_w, 1),
            "rsi_monthly":           round(rsi_m, 1),
            "blacked_out":           False,   # populated later by EventBlackoutFilter
        }

    # ------------------------------------------------------------------
    # Signal candle finder
    # ------------------------------------------------------------------

    def _find_signal_candle(
        self,
        opens: np.ndarray,
        highs: np.ndarray,
        lows: np.ndarray,
        closes: np.ndarray,
        lookback: int,
    ) -> tuple[Optional[int], str, str]:
        """Scan recent bars (newest first) for the most recent signal candle.

        Returns (index_into_array, pattern_name, reason_string) or
                (None, "", "") if no qualifying candle found.

        Priority order: Morning Star > Bullish Engulfing > Piercing >
                        Bullish Harami > Hammer > Doji
        (more decisive reversal patterns ranked first)
        """
        n = len(closes)
        # Search newest → oldest (skip last bar = current incomplete candle if desired)
        for i in range(n - 2, max(n - lookback - 2, 1), -1):
            o, h, l, c = opens[i], highs[i], lows[i], closes[i]

            # Morning Star needs 3 bars
            if i >= 2:
                qualified, reason = is_morning_star(
                    opens[i - 2], closes[i - 2],
                    opens[i - 1], closes[i - 1],
                    o, c
                )
                if qualified:
                    return i, "Morning Star", reason

            # Two-bar patterns
            if i >= 1:
                po, pc = opens[i - 1], closes[i - 1]
                pl     = lows[i - 1]

                qualified, reason = is_bullish_engulfing(po, pc, o, c)
                if qualified:
                    return i, "Bullish Engulfing", reason

                qualified, reason = is_piercing(po, pl, pc, o, c)
                if qualified:
                    return i, "Piercing Pattern", reason

                qualified, reason = is_bullish_harami(po, pc, o, c)
                if qualified:
                    return i, "Bullish Harami", reason

            # Single-bar patterns
            qualified, reason = is_hammer(o, h, l, c)
            if qualified:
                return i, "Hammer", reason

            qualified, reason = is_doji(o, h, l, c)
            if qualified:
                return i, "Doji", reason

        return None, "", ""
