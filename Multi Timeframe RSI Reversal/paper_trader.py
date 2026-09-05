"""
paper_trader.py
---------------
Reversal-strategy virtual paper trader.

COMPLETELY SEPARATE from stocks_monitoring_and_notifying/paper_trader.py.
  - Own state file : Multi Timeframe RSI Reversal/virtual_portfolio.json
  - Own commands   : /revportfolio, /revhistory, /revreset, /revtoggle
  - Own trigger    : ONLY confirmed_entry (Rule 3 closed breakout)
  - Own exit logic : Bar-count trailing SL + RSI-60 target + 1R partial exit

Key differences from the uptrend paper trader:
  | Uptrend                     | This (Reversal)                              |
  |-----------------------------|----------------------------------------------|
  | score >= 60 AND RSI 40–55   | tag == "confirmed_entry" ONLY                |
  | watchlist names executed    | early_entry NEVER auto-executed              |
  | ATR × 1.5 trailing stop     | min(last N lows) every trailing_bar_cnt bars |
  | "AI Caution" exit           | RSI-60 target price OR trailing stop hit     |
  | sizing duplicated inline    | delegates to position_sizer.compute()        |

Strategy: Multi-Timeframe RSI Reversal
"""

import os
import json
import math
from datetime import datetime
from typing import Optional

import position_sizer as ps


_HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PORTFOLIO_PATH = os.path.join(_HERE, "virtual_portfolio.json")


class PaperTrader:
    """Manages a virtual portfolio for the RSI Reversal strategy."""

    def __init__(self, config=None, filepath: str = None):
        self.filepath  = filepath or DEFAULT_PORTFOLIO_PATH
        self._config   = config  # ConfigManager instance (may be None in tests)

        # Read config values (with safe fallbacks)
        if config is not None:
            self._capital         = float(config.default_capital)
            self._risk_pct        = float(config.risk_pct)
            self._reward_multiple = float(config.reward_multiple)
            self._max_positions   = int(config.max_positions)
            self._trailing_enabled = bool(config.filters.get("trailing_enabled", False))
            self._trailing_bar_cnt = int(config.filters.get("trailing_bar_count", 5))
            self._partial_exit_pct = float(config.risk.get("partial_exit_pct", 50)) / 100.0
        else:
            self._capital         = 500_000.0
            self._risk_pct        = 1.0
            self._reward_multiple = 1.5
            self._max_positions   = 5
            self._trailing_enabled = False
            self._trailing_bar_cnt = 5
            self._partial_exit_pct = 0.5

        self._state: dict = {}
        self._load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self):
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r", encoding="utf-8") as fh:
                    self._state = json.load(fh)
            except Exception as exc:
                print(f"[warn] Failed to load reversal virtual portfolio: {exc}")
                self._state = {}

        # Ensure required top-level keys exist
        self._state.setdefault("cash_balance",    self._capital)
        self._state.setdefault("starting_balance", self._capital)
        self._state.setdefault("positions",        {})
        self._state.setdefault("trade_history",    [])

    def _save(self):
        try:
            with open(self.filepath, "w", encoding="utf-8") as fh:
                json.dump(self._state, fh, indent=4)
        except Exception as exc:
            print(f"[warn] Failed to save reversal virtual portfolio: {exc}")

    # ------------------------------------------------------------------
    # Public read accessors
    # ------------------------------------------------------------------

    @property
    def cash(self) -> float:
        return float(self._state.get("cash_balance", self._capital))

    @property
    def positions(self) -> dict:
        return self._state.get("positions", {})

    @property
    def trade_history(self) -> list:
        return self._state.get("trade_history", [])

    def portfolio_value(self, current_prices: dict) -> float:
        """Total portfolio value = cash + mark-to-market open positions."""
        val = self.cash
        for sym, pos in self.positions.items():
            price = current_prices.get(sym, {}).get("price", pos["entry_price"])
            val  += price * pos["quantity"]
        return val

    def get_unrealised_pnl(self, current_prices: dict) -> dict:
        """Return per-symbol unrealised P&L dict."""
        result = {}
        for sym, pos in self.positions.items():
            price = current_prices.get(sym, {}).get("price", pos["entry_price"])
            pnl   = (price - pos["entry_price"]) * pos["quantity"]
            result[sym] = {"price": price, "unrealised_pnl": round(pnl, 2)}
        return result

    def reset(self, starting_balance: float = None) -> str:
        """Reset to a fresh virtual portfolio."""
        bal = starting_balance or self._capital
        self._state = {
            "cash_balance":    bal,
            "starting_balance": bal,
            "positions":       {},
            "trade_history":   [],
        }
        self._save()
        return f"✅ Reversal virtual portfolio reset to ₹{bal:,.2f}."

    # ------------------------------------------------------------------
    # Core execution engine
    # ------------------------------------------------------------------

    def execute_trades(
        self,
        confirmed_candidates: list[dict],
        current_prices: dict,
        blackout_filter=None,
        notifier_send=None,
        daily_data: dict = None,
    ) -> list[str]:
        """Run the full paper-trading cycle for one scan run.

        Parameters
        ----------
        confirmed_candidates : list[dict]
            Candidates from ReversalAnalyzer with tag == "confirmed_entry"
            (caller is responsible for pre-filtering to confirmed only).
        current_prices : dict
            ``{"SYMBOL": {"price": float, "lows": np.ndarray}}``
            lows = recent daily low array (used for bar-count trailing SL).
        blackout_filter : EventBlackoutFilter, optional
            If provided, blacked-out symbols are skipped at execution time.
        notifier_send : callable, optional
            Called with a Telegram-formatted HTML string for each alert.
        daily_data : dict, optional
            Full daily OHLCV per symbol — used for trailing SL updates.

        Returns
        -------
        list[str]
            List of HTML-formatted alert strings (sent to Telegram if
            notifier_send is provided).
        """
        alerts: list[str] = []
        updated = False
        today   = datetime.now().strftime("%Y-%m-%d")

        # ── 1. Process open positions: exits & trailing SL ──────────────────
        for sym in list(self.positions.keys()):
            pos   = self.positions[sym]
            mdata = current_prices.get(sym, {})
            price = float(mdata.get("price", 0))
            if price <= 0:
                continue

            # --- Check trailing SL hit ---
            if price <= pos["sl"]:
                pnl = (price - pos["entry_price"]) * pos["quantity"]
                self._state["cash_balance"] += price * pos["quantity"]
                self._record_trade(sym, "SELL (SL Hit)", price, pnl)
                del self._state["positions"][sym]
                updated = True
                emoji = "🟢" if pnl >= 0 else "🔴"
                alerts.append(
                    f"💥 <b>REV STOP HIT: {sym}</b>\n"
                    f"Sold {pos['quantity']} shares at ₹{price:.2f}\n"
                    f"PnL: {emoji} ₹{pnl:+.2f}"
                )
                continue

            # --- 1R Partial exit (50% of shares at 1R target) ---
            if not pos.get("partial_taken") and price >= pos["target_1r"]:
                qty_sell = math.floor(pos["quantity"] * self._partial_exit_pct)
                if qty_sell > 0:
                    pnl = (price - pos["entry_price"]) * qty_sell
                    self._state["cash_balance"] += price * qty_sell
                    pos["quantity"]      -= qty_sell
                    pos["partial_taken"]  = True
                    # Shift SL to entry (lock in breakeven for remaining shares)
                    pos["sl"] = max(pos["sl"], pos["entry_price"])
                    self._record_trade(sym, f"SELL (1R Partial {int(self._partial_exit_pct*100)}%)", price, pnl)
                    updated = True
                    alerts.append(
                        f"🎯 <b>REV 1R HIT: {sym}</b>\n"
                        f"Sold {qty_sell} shares at ₹{price:.2f} (+₹{pnl:.2f})\n"
                        f"SL for remaining {pos['quantity']} shares → ₹{pos['sl']:.2f} (entry)"
                    )

            # --- RSI-60 full target exit ---
            if price >= pos.get("target_rsi60", float("inf")) and pos["quantity"] > 0:
                pnl = (price - pos["entry_price"]) * pos["quantity"]
                self._state["cash_balance"] += price * pos["quantity"]
                self._record_trade(sym, "SELL (RSI-60 Target)", price, pnl)
                del self._state["positions"][sym]
                updated = True
                alerts.append(
                    f"🏆 <b>REV RSI-60 TARGET: {sym}</b>\n"
                    f"Sold remaining {pos['quantity']} shares at ₹{price:.2f}\n"
                    f"PnL: 🟢 ₹{pnl:+.2f}"
                )
                continue

            # --- Bar-count trailing SL update ---
            if self._trailing_enabled and daily_data and sym in daily_data:
                pos["bars_since_last_trail"] = pos.get("bars_since_last_trail", 0) + 1
                if pos["bars_since_last_trail"] >= self._trailing_bar_cnt:
                    lows = daily_data[sym].get("daily", {}).get("low", [])
                    if len(lows) >= self._trailing_bar_cnt:
                        new_sl = float(min(lows[-self._trailing_bar_cnt:]))
                        if new_sl > pos["sl"] and new_sl < price:
                            old_sl = pos["sl"]
                            pos["sl"] = round(new_sl, 2)
                            pos["bars_since_last_trail"] = 0
                            updated = True
                            alerts.append(
                                f"🛡️ <b>REV SL RAISED: {sym}</b>\n"
                                f"New SL ₹{pos['sl']:.2f} (was ₹{old_sl:.2f})"
                            )

        # ── 2. Process entries (confirmed_entry only) ────────────────────────
        active = len(self.positions)

        for candidate in confirmed_candidates:
            if active >= self._max_positions:
                break

            sym = candidate.get("symbol", "")
            if sym in self.positions:
                continue  # already holding

            # Skip blacked-out symbols
            if blackout_filter and blackout_filter.is_blacked_out(sym, today):
                continue

            # Gate: ONLY confirmed_entry
            if candidate.get("tag") != "confirmed_entry":
                continue

            entry  = float(candidate["entry"])
            sl     = float(candidate["sl"])
            t1r    = float(candidate.get("target_1r",   entry + 1.5 * (entry - sl)))
            trsi60 = float(candidate.get("target_rsi60", entry + 2.0 * (entry - sl)))

            # Compute position size
            sizing = ps.compute(
                entry           = entry,
                sl              = sl,
                capital         = self._capital,
                risk_pct        = self._risk_pct,
                reward_multiple = self._reward_multiple,
                target_rsi60    = trsi60,
            )
            qty  = sizing["qty"]
            cost = qty * entry

            if qty <= 0 or cost > self._state["cash_balance"]:
                continue  # insufficient funds

            # Execute virtual buy
            self._state["cash_balance"] -= cost
            self._state["positions"][sym] = {
                "entry_price":         entry,
                "quantity":            qty,
                "entry_date":          today,
                "signal_candle_date":  candidate.get("signal_candle_date", today),
                "signal_candle_pattern": candidate.get("signal_candle_pattern", ""),
                "sl":                  sl,
                "initial_sl":          sl,
                "target_1r":           t1r,
                "target_rsi60":        trsi60,
                "partial_taken":       False,
                "bars_since_last_trail": 0,
                "highest_price":       entry,
            }
            active  += 1
            updated  = True
            risk_amt = sizing["risk_amount"]
            alerts.append(
                f"🎮 <b>REV BUY: {sym}</b>\n"
                f"Bought {qty} shares @ ₹{entry:.2f}\n"
                f"Pattern: {candidate.get('signal_candle_pattern','')}\n"
                f"Risk: 1% (₹{risk_amt:.2f}) | SL: ₹{sl:.2f}\n"
                f"1R target: ₹{t1r:.2f} | RSI-60 target: ₹{trsi60:.2f}"
            )

        # ── 3. Save & notify ─────────────────────────────────────────────────
        if updated:
            self._save()

        if alerts and notifier_send:
            header = "<b>🤖 RSI REVERSAL AUTO-TRADER</b>\n\n"
            notifier_send(header + "\n\n".join(alerts))

        return alerts

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _record_trade(self, symbol: str, trade_type: str, exit_price: float, pnl: float):
        self._state["trade_history"].append({
            "symbol":     symbol,
            "type":       trade_type,
            "exit_price": round(exit_price, 2),
            "pnl":        round(pnl, 2),
            "date":       datetime.now().strftime("%Y-%m-%d %H:%M"),
        })

    # ------------------------------------------------------------------
    # Telegram-friendly formatters
    # ------------------------------------------------------------------

    def format_portfolio(self, current_prices: dict = None) -> str:
        """Return HTML summary of open positions for /revportfolio."""
        cp = current_prices or {}
        positions = self.positions
        cash      = self.cash

        if not positions:
            return (
                f"💼 <b>RSI Reversal Virtual Portfolio</b>\n\n"
                f"No open positions.\n"
                f"Cash: ₹{cash:,.2f}"
            )

        lines = [f"💼 <b>RSI Reversal Virtual Portfolio</b>\n"]
        total_unrealised = 0.0

        for sym, pos in positions.items():
            price  = cp.get(sym, {}).get("price", pos["entry_price"])
            pnl    = (price - pos["entry_price"]) * pos["quantity"]
            total_unrealised += pnl
            emoji  = "🟢" if pnl >= 0 else "🔴"
            lines.append(
                f"  <b>{sym}</b> {pos.get('signal_candle_pattern','')}\n"
                f"  Entry ₹{pos['entry_price']:.2f} | CMP ₹{price:.2f} | "
                f"Qty {pos['quantity']}\n"
                f"  SL ₹{pos['sl']:.2f} | 1R ₹{pos['target_1r']:.2f}\n"
                f"  P&L: {emoji} ₹{pnl:+.2f}"
            )

        pnl_emoji = "🟢" if total_unrealised >= 0 else "🔴"
        lines.append(
            f"\nCash: ₹{cash:,.2f}\n"
            f"Unrealised P&L: {pnl_emoji} ₹{total_unrealised:+.2f}"
        )
        return "\n".join(lines)

    def format_history(self, n: int = 10) -> str:
        """Return HTML of last n closed trades for /revhistory."""
        history = self.trade_history[-n:][::-1]  # newest first
        if not history:
            return "📋 <b>RSI Reversal Trade History</b>\n\nNo closed trades yet."

        lines = [f"📋 <b>RSI Reversal Trade History (last {len(history)})</b>\n"]
        for t in history:
            emoji = "🟢" if t["pnl"] >= 0 else "🔴"
            lines.append(
                f"  {emoji} <b>{t['symbol']}</b> — {t['type']}\n"
                f"  Exit ₹{t['exit_price']:.2f} | PnL ₹{t['pnl']:+.2f} | {t['date']}"
            )
        return "\n".join(lines)
