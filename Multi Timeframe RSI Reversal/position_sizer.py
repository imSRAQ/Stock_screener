"""
position_sizer.py
-----------------
Pure, side-effect-free position sizing calculations for the
Multi-Timeframe RSI Reversal strategy.

This module is intentionally self-contained so that:
  1. paper_trader.py delegates sizing math here (no duplication)
  2. The dashboard's live JS calculator mirrors the same formula
  3. Unit tests can verify math without any I/O

Strategy: Multi-Timeframe RSI Reversal
"""

import math


def compute(
    entry: float,
    sl: float,
    capital: float,
    risk_pct: float,
    reward_multiple: float = 1.5,
    target_rsi60: float = None,
) -> dict:
    """Compute the full position sizing table for one trade setup.

    Parameters
    ----------
    entry : float
        Breakout entry price (signal candle high).
    sl : float
        Stop-loss price.
    capital : float
        Total available capital in ₹.
    risk_pct : float
        Risk percentage per trade (e.g. 1.0 = 1%).
    reward_multiple : float
        Risk-to-reward multiple for partial exit level (default 1.5).
    target_rsi60 : float, optional
        RSI-60 projected price (1st full target). If None, defaults to
        the 2R level (entry + 2× risk_per_share).

    Returns
    -------
    dict with keys:
        entry, sl, risk_per_share, risk_amount, qty,
        capital_required, target_1r, target_rsi60,
        potential_loss, potential_gain_1r, potential_gain_rsi60,
        risk_reward_1r, warning
    """
    risk_per_share = entry - sl
    risk_amount    = capital * (risk_pct / 100.0)

    warnings = []

    if risk_per_share <= 0:
        warnings.append("⚠️ Risk per share ≤ 0 — SL must be below entry price.")
        return {
            "entry": entry, "sl": sl,
            "risk_per_share": risk_per_share,
            "risk_amount": 0, "qty": 0,
            "capital_required": 0,
            "target_1r": entry, "target_rsi60": entry,
            "potential_loss": 0, "potential_gain_1r": 0, "potential_gain_rsi60": 0,
            "risk_reward_1r": 0,
            "warning": " ".join(warnings),
        }

    qty              = math.floor(risk_amount / risk_per_share)
    capital_required = qty * entry
    target_1r        = entry + reward_multiple * risk_per_share

    if target_rsi60 is None or target_rsi60 <= entry:
        target_rsi60 = entry + 2.0 * risk_per_share  # safe fallback

    potential_loss        = qty * risk_per_share
    potential_gain_1r     = qty * reward_multiple * risk_per_share
    potential_gain_rsi60  = qty * (target_rsi60 - entry)
    risk_reward_1r        = reward_multiple  # always = config multiple

    if capital_required > capital:
        warnings.append(
            f"⚠️ Capital required (₹{capital_required:,.0f}) exceeds "
            f"available capital (₹{capital:,.0f})."
        )

    if qty == 0:
        warnings.append(
            "⚠️ Position size is 0 shares — risk per share too large relative to "
            "risk amount. Consider widening capital or tightening SL."
        )

    return {
        "entry":               round(entry, 2),
        "sl":                  round(sl, 2),
        "risk_per_share":      round(risk_per_share, 2),
        "risk_amount":         round(risk_amount, 2),
        "qty":                 qty,
        "capital_required":    round(capital_required, 2),
        "target_1r":           round(target_1r, 2),
        "target_rsi60":        round(target_rsi60, 2),
        "potential_loss":      round(potential_loss, 2),
        "potential_gain_1r":   round(potential_gain_1r, 2),
        "potential_gain_rsi60": round(potential_gain_rsi60, 2),
        "risk_reward_1r":      round(risk_reward_1r, 2),
        "warning":             " | ".join(warnings) if warnings else "",
    }


def compute_for_candidate(candidate: dict, capital: float, risk_pct: float,
                           reward_multiple: float = 1.5) -> dict:
    """Convenience wrapper — feeds a ReversalAnalyzer candidate dict directly."""
    return compute(
        entry           = candidate["entry"],
        sl              = candidate["sl"],
        capital         = capital,
        risk_pct        = risk_pct,
        reward_multiple = reward_multiple,
        target_rsi60    = candidate.get("target_rsi60"),
    )


# ── CLI quick-calculator (standalone test) ────────────────────────────────────
if __name__ == "__main__":
    import sys
    print("=" * 55)
    print("  RSI Reversal — Position Sizer (Quick Calculator)")
    print("=" * 55)

    try:
        entry   = float(input("Entry price  (₹): "))
        sl      = float(input("Stop loss    (₹): "))
        capital = float(input("Capital      (₹): "))
        risk    = float(input("Risk %        [1]: ") or "1")
        rr      = float(input("RR multiple [1.5]: ") or "1.5")
    except (ValueError, KeyboardInterrupt):
        sys.exit(0)

    result = compute(entry, sl, capital, risk, rr)
    print()
    print(f"  Risk per share      : ₹{result['risk_per_share']:>10,.2f}")
    print(f"  Risk amount         : ₹{result['risk_amount']:>10,.2f}")
    print(f"  Position size       : {result['qty']:>10} shares")
    print(f"  Capital required    : ₹{result['capital_required']:>10,.2f}")
    print(f"  1R target ({rr}x)    : ₹{result['target_1r']:>10,.2f}")
    print(f"  Potential loss      : ₹{result['potential_loss']:>10,.2f}")
    print(f"  Potential gain @1R  : ₹{result['potential_gain_1r']:>10,.2f}")
    if result["warning"]:
        print(f"\n  {result['warning']}")
    print()
