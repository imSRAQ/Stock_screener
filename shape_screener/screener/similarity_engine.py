"""
similarity_engine.py
Core logic: normalize price series and score candidates by shape-similarity
to a reference stock's recent candlestick/price pattern.

Also computes technical strength indicators (RSI, SMA, MACD, ADX) from
the close-price array — no extra network calls needed.

This module has NO network dependency and is fully unit-testable offline.
"""

import numpy as np
import pandas as pd

def normalize_series(prices: np.ndarray) -> np.ndarray:
    """
    Z-score normalize a price series so shape comparison
    is scale invariant.

    MODIFIED:
    - Missing values are replaced with previous values.
    - Leading NaNs are replaced with first valid value.
    """

    prices = np.asarray(prices, dtype=float)

    # ============================================================
    # MODIFICATION START
    # Forward-fill NaN values using previous close.
    # ============================================================
    if np.isnan(prices).any():
        prices = pd.Series(prices).ffill().bfill().to_numpy()
    # ============================================================
    # MODIFICATION END
    # ============================================================

    mean = prices.mean()
    std = prices.std()

    if std == 0:
        return np.zeros_like(prices)

    return (prices - mean) / std
# def normalize_series(prices: np.ndarray) -> np.ndarray:
#     """
#     Z-score normalize a price series so shape comparison is scale-invariant.
#     A stock at ₹50 and one at ₹5000 with the same % movement pattern
#     will normalize to the same shape.
#     """
#     prices = np.asarray(prices, dtype=float)
#     mean = prices.mean()
#     std = prices.std()
#     if std == 0:
#         return np.zeros_like(prices)
#     return (prices - mean) / std


def dtw_distance(seq_a: np.ndarray, seq_b: np.ndarray, window: int = None) -> float:
    """
    Dynamic Time Warping distance between two normalized sequences.
    Lower = more similar shape. Tolerates slight time-shifts/stretches,
    which matters for candlestick pattern matching (patterns rarely
    line up to the exact same day count).

    window: optional Sakoe-Chiba band width to limit warping (speeds up
    computation and avoids degenerate matches on longer series).
    """
    n, m = len(seq_a), len(seq_b)
    if window is None:
        window = max(n, m)

    cost = np.full((n + 1, m + 1), np.inf)
    cost[0, 0] = 0.0

    for i in range(1, n + 1):
        j_start = max(1, i - window)
        j_end = min(m, i + window)
        for j in range(j_start, j_end + 1):
            dist = abs(seq_a[i - 1] - seq_b[j - 1])
            cost[i, j] = dist + min(
                cost[i - 1, j],      # insertion
                cost[i, j - 1],      # deletion
                cost[i - 1, j - 1],  # match
            )
    return cost[n, m]


def trend_slope(prices: np.ndarray) -> float:
    """
    Linear regression slope of the price series, normalized by mean price,
    so it's comparable across stocks of different price levels.
    Positive = uptrend. Returned as approx. fractional change per day.
    """
    prices = np.asarray(prices, dtype=float)
    x = np.arange(len(prices))
    slope, intercept = np.polyfit(x, prices, 1)
    mean_price = prices.mean()
    if mean_price == 0:
        return 0.0
    return slope / mean_price


def pct_return(prices: np.ndarray) -> float:
    """Total % return over the window."""
    prices = np.asarray(prices, dtype=float)
    if prices[0] == 0:
        return 0.0
    return (prices[-1] - prices[0]) / prices[0] * 100


# ---------------------------------------------------------------------------
# Technical indicators  ***NEW***
# All computed from the close-price array we already have — zero extra
# network calls. Pure-numpy for speed.
# ---------------------------------------------------------------------------

def compute_rsi(prices: np.ndarray, period: int = 14) -> float:
    """
    Relative Strength Index (Wilder's smoothing).
    Returns the latest RSI value (0–100).
    > 70 = overbought, < 30 = oversold, 50–65 = healthy uptrend.
    Returns None if not enough data.
    """
    prices = np.asarray(prices, dtype=float)
    if len(prices) < period + 1:
        return None
    deltas = np.diff(prices)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)

    # Wilder's smoothed average (exponential)
    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])

    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)


def compute_sma(prices: np.ndarray, period: int) -> float:
    """
    Simple Moving Average — latest value.
    Returns None if not enough data.
    """
    prices = np.asarray(prices, dtype=float)
    if len(prices) < period:
        return None
    return float(np.mean(prices[-period:]))


def _compute_ema(prices: np.ndarray, period: int) -> np.ndarray:
    """
    Exponential Moving Average — returns the full EMA array.
    Used internally by MACD.
    """
    prices = np.asarray(prices, dtype=float)
    ema = np.empty_like(prices)
    ema[0] = prices[0]
    k = 2.0 / (period + 1)
    for i in range(1, len(prices)):
        ema[i] = prices[i] * k + ema[i - 1] * (1 - k)
    return ema


def compute_macd(prices: np.ndarray) -> dict:
    """
    MACD (12, 26, 9) — returns latest macd line value, signal line value,
    histogram value, and whether the crossover is bullish.
    Returns dict with None values if not enough data.
    """
    prices = np.asarray(prices, dtype=float)
    if len(prices) < 35:  # need at least 26 + 9 for meaningful MACD
        return {"macd": None, "signal": None, "histogram": None, "macd_bullish": None}

    ema12 = _compute_ema(prices, 12)
    ema26 = _compute_ema(prices, 26)
    macd_line = ema12 - ema26
    signal_line = _compute_ema(macd_line, 9)

    latest_macd = float(macd_line[-1])
    latest_signal = float(signal_line[-1])
    histogram = latest_macd - latest_signal

    return {
        "macd": round(latest_macd, 4),
        "signal": round(latest_signal, 4),
        "histogram": round(histogram, 4),
        "macd_bullish": bool(latest_macd > latest_signal),
    }


def compute_adx(prices: np.ndarray, period: int = 14) -> float:
    """
    Simplified ADX from close prices only (we don't have high/low).
    Uses absolute close-to-close moves as a proxy for directional movement.
    > 25 = strong trend, > 50 = very strong trend.
    Returns None if not enough data.
    """
    prices = np.asarray(prices, dtype=float)
    if len(prices) < period * 2 + 1:
        return None

    deltas = np.diff(prices)
    plus_dm = np.where(deltas > 0, deltas, 0.0)
    minus_dm = np.where(deltas < 0, -deltas, 0.0)
    tr = np.abs(deltas)  # simplified true range from closes

    # Wilder's smoothing
    atr = np.mean(tr[:period])
    plus_di_sum = np.mean(plus_dm[:period])
    minus_di_sum = np.mean(minus_dm[:period])

    dx_values = []
    for i in range(period, len(deltas)):
        atr = (atr * (period - 1) + tr[i]) / period
        plus_di_sum = (plus_di_sum * (period - 1) + plus_dm[i]) / period
        minus_di_sum = (minus_di_sum * (period - 1) + minus_dm[i]) / period

        if atr == 0:
            continue
        plus_di = 100 * plus_di_sum / atr
        minus_di = 100 * minus_di_sum / atr
        di_sum = plus_di + minus_di
        if di_sum == 0:
            continue
        dx = 100 * abs(plus_di - minus_di) / di_sum
        dx_values.append(dx)

    if len(dx_values) < period:
        return None

    # Smooth DX to get ADX
    adx = np.mean(dx_values[:period])
    for i in range(period, len(dx_values)):
        adx = (adx * (period - 1) + dx_values[i]) / period

    return round(float(adx), 2)


def compute_technical_score(prices: np.ndarray) -> dict:
    """
    Compute all technical indicators and a composite tech_score (0–100).

    Returns a dict with individual indicators plus the composite score.
    Higher tech_score = stronger technical setup for an uptrend trade.

    Scoring weights:
      RSI in sweet spot (40–70):  20%
      Price > SMA 50:            20%
      Price > SMA 200:           20%
      MACD bullish crossover:    20%
      ADX > 25 (strong trend):   20%
    """
    prices = np.asarray(prices, dtype=float)
    result = {
        "rsi": None,
        "sma_50": None,
        "sma_200": None,
        "above_sma_50": None,
        "above_sma_200": None,
        "macd": None,
        "macd_signal": None,
        "macd_histogram": None,
        "macd_bullish": None,
        "adx": None,
        "tech_score": None,
    }

    if len(prices) < 15:
        return result

    current_price = float(prices[-1])

    # ── Individual indicators ────────────────────────────────────────
    rsi = compute_rsi(prices)
    sma_50 = compute_sma(prices, 50)
    sma_200 = compute_sma(prices, 200)
    macd_data = compute_macd(prices)
    adx = compute_adx(prices)

    above_50 = (current_price > sma_50) if sma_50 is not None else None
    above_200 = (current_price > sma_200) if sma_200 is not None else None

    result.update({
        "rsi": rsi,
        "sma_50": round(sma_50, 2) if sma_50 is not None else None,
        "sma_200": round(sma_200, 2) if sma_200 is not None else None,
        "above_sma_50": above_50,
        "above_sma_200": above_200,
        "macd": macd_data["macd"],
        "macd_signal": macd_data["signal"],
        "macd_histogram": macd_data["histogram"],
        "macd_bullish": macd_data["macd_bullish"],
        "adx": adx,
    })

    # ── Composite tech_score (0–100) ────────────────────────────────
    components = []
    weights = []

    # RSI sweet spot: best at 50-65, good at 40-70, poor outside
    if rsi is not None:
        if 50 <= rsi <= 65:
            components.append(100)
        elif 40 <= rsi < 50:
            components.append(60 + (rsi - 40) * 4)  # 60→100
        elif 65 < rsi <= 70:
            components.append(100 - (rsi - 65) * 10)  # 100→50
        elif 30 <= rsi < 40:
            components.append(30 + (rsi - 30) * 3)  # 30→60
        elif 70 < rsi <= 80:
            components.append(max(0, 50 - (rsi - 70) * 5))  # 50→0
        else:
            components.append(0)
        weights.append(20)

    # Price > SMA 50
    if above_50 is not None:
        components.append(100 if above_50 else 0)
        weights.append(20)

    # Price > SMA 200
    if above_200 is not None:
        components.append(100 if above_200 else 0)
        weights.append(20)

    # MACD bullish
    if macd_data["macd_bullish"] is not None:
        components.append(100 if macd_data["macd_bullish"] else 0)
        weights.append(20)

    # ADX trend strength: 0 at ADX=0, 100 at ADX≥50
    if adx is not None:
        adx_score = min(100, adx * 2)  # 50 ADX → 100 score
        components.append(adx_score)
        weights.append(20)

    if weights:
        total_weight = sum(weights)
        tech_score = sum(c * w for c, w in zip(components, weights)) / total_weight
        result["tech_score"] = round(tech_score, 1)

    return result


def score_candidate(
    reference_close: np.ndarray,
    candidate_close: np.ndarray,
    min_slope: float = 0.0,
) -> dict:
    """
    Compare one candidate's price shape against the reference.
    Returns a dict with similarity score (0-100, higher=more similar),
    raw DTW distance, trend slope, whether it passes the uptrend filter,
    and all technical indicators with composite tech_score.

    min_slope: minimum normalized daily slope required to count as
    "uptrend" (0.0 = any positive slope; raise it to demand a stronger trend).
    """
    cand_norm = normalize_series(candidate_close)

    if reference_close is not None and len(reference_close) > 0:
        ref_norm = normalize_series(reference_close)
        # Forward-fill missing values before DTW comparison.
        reference_close = (
            pd.Series(reference_close)
            .ffill()
            .bfill()
            .to_numpy(dtype=float)
        )

    candidate_close = (
        pd.Series(candidate_close)
        .ffill()
        .bfill()
        .to_numpy(dtype=float)
    )

    if reference_close is not None and len(reference_close) > 0:
        ref_norm = (
            pd.Series(reference_close)
            .pct_change()
            .fillna(0)
            .add(1)
            .cumprod()
            .to_numpy(dtype=float)
        )
        # Align lengths
        if len(cand_norm) != len(ref_norm):
            x_old = np.linspace(0, 1, len(cand_norm))
            x_new = np.linspace(0, 1, len(ref_norm))
            cand_norm = np.interp(x_new, x_old, cand_norm)

        distance = dtw_distance(ref_norm, cand_norm, window=max(5, len(ref_norm) // 3))
        norm_distance = distance / len(ref_norm)
        similarity = 100 / (1 + norm_distance)
    else:
        distance = 0.0
        similarity = 0.0

    slope = trend_slope(candidate_close)
    ret = pct_return(candidate_close)

    # ── Technical indicators (computed from close data we already have) ──
    tech = compute_technical_score(candidate_close)

    result = {
        "similarity_score": round(float(similarity), 2),
        "dtw_distance": round(float(distance), 4),
        "trend_slope": round(float(slope), 6),
        "pct_return": round(float(ret), 2),
        "is_uptrend": bool(slope > min_slope),
    }
    result.update(tech)  # merge all technical fields
    return result


def rank_candidates(
    reference_close: np.ndarray,
    candidates: dict,  # {ticker: close_array}
    min_slope: float = 0.0,
    uptrend_only: bool = True,
) -> pd.DataFrame:
    """
    Score every candidate against the reference and return a ranked DataFrame,
    sorted by similarity_score descending. Filters to uptrend-only by default.
    Now includes technical indicator columns.
    """
    rows = []
    for ticker, closes in candidates.items():
        closes = np.asarray(closes, dtype=float)
        if len(closes) < 5:
            continue  # too little data to compare meaningfully
        try:
            result = score_candidate(reference_close, closes, min_slope=min_slope)
        except Exception as e:
            continue
        result["ticker"] = ticker
        rows.append(result)

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    if uptrend_only:
        df = df[df["is_uptrend"]]

    if reference_close is None or len(reference_close) == 0:
        # If no reference shape is provided, sort by tech_score first
        if "tech_score" in df.columns:
            df = df.sort_values("tech_score", ascending=False).reset_index(drop=True)
        else:
            df = df.sort_values("trend_slope", ascending=False).reset_index(drop=True)
    else:
        df = df.sort_values("similarity_score", ascending=False).reset_index(drop=True)

    # Include all columns — similarity + technical indicators
    base_cols = ["ticker", "similarity_score", "pct_return", "trend_slope",
                 "dtw_distance", "is_uptrend"]
    tech_cols = ["rsi", "sma_50", "sma_200", "above_sma_50", "above_sma_200",
                 "macd", "macd_signal", "macd_histogram", "macd_bullish",
                 "adx", "tech_score"]
    all_cols = base_cols + [c for c in tech_cols if c in df.columns]
    return df[all_cols]
