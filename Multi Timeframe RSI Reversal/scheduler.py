"""
scheduler.py
------------
Orchestrates the full Multi-Timeframe RSI Reversal scan pipeline.

Run modes:
  python scheduler.py --full    : Full daily scan (run after market close)
  python scheduler.py --hourly  : Re-check watchlist breakouts during market hours

Pipeline (--full):
  1. Load Config
  2. Fetch Universe (Daily + Weekly + Monthly OHLCV)
  3. Apply Reversal Filter (Rules 1–5)
  4. Blackout Check
  5. Position Sizing (server-side defaults)
  6. Virtual Execution (if auto_paper_trade_enabled)
  7. AI Summary (top N candidates)
  8. Dashboard Generation
  9. Save snapshot
  10. Telegram Notification

Strategy: Multi-Timeframe RSI Reversal
"""

import os
import sys
import json
import argparse
import shutil
from datetime import datetime

# ── Ensure module folder is on path ───────────────────────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from config_manager        import ConfigManager
from data_fetcher          import DataFetcher
from reversal_analyzer     import ReversalAnalyzer
from event_blackout_filter import EventBlackoutFilter
from position_sizer        import compute_for_candidate
from paper_trader          import PaperTrader
from ai_summarizer         import AISummarizer
from dashboard_generator   import DashboardGenerator

try:
    import holidays as _holidays
except ImportError:
    _holidays = None


class Scheduler:
    """Orchestrates the reversal strategy pipeline."""

    MAX_AI_STOCKS = 15   # Free Gemini tier: ~3 API calls (5 stocks/call)

    def __init__(self):
        self.config   = ConfigManager()
        errors = self.config.validate(require_secrets=True)
        if errors:
            for err in errors:
                print(f"[error] {err}")
            sys.exit(1)

        self.snapshot_path = os.path.join(_HERE, "universe_snapshot.json")
        self.prev_path     = os.path.join(_HERE, "universe_snapshot_prev.json")

    # ------------------------------------------------------------------
    # Holiday check
    # ------------------------------------------------------------------

    def _is_holiday(self) -> bool:
        today = datetime.now()
        if today.weekday() >= 5:
            return True
        if _holidays:
            in_hols = _holidays.India(years=today.year)
            if today.date() in in_hols:
                return True
        return False

    # ------------------------------------------------------------------
    # Snapshot helpers
    # ------------------------------------------------------------------

    def _save_snapshot(self, candidates: list):
        if os.path.exists(self.snapshot_path):
            shutil.copy(self.snapshot_path, self.prev_path)
        with open(self.snapshot_path, "w", encoding="utf-8") as fh:
            json.dump(candidates, fh, indent=2)

    def _load_snapshot(self, path: str) -> list:
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                return json.load(fh)
        return []

    # ------------------------------------------------------------------
    # Notification helper (uses rev_handlers.send_alert — no polling)
    # ------------------------------------------------------------------

    def _notify(self, text: str):
        try:
            from rev_handlers import send_alert
            send_alert(
                token   = self.config.telegram_bot_token,
                chat_id = self.config.telegram_chat_id,
                text    = text,
            )
        except Exception as exc:
            print(f"[warn] Telegram notify failed: {exc}")

    # ------------------------------------------------------------------
    # Full scan
    # ------------------------------------------------------------------

    def run_full(self):
        if self._is_holiday():
            print("[info] Today is a holiday. Skipping reversal scan.")
            return

        scan_date = datetime.now().strftime("%Y-%m-%d")
        print(f"[info] Starting full RSI Reversal scan - {scan_date}")

        # ── Step 1: Load config ────────────────────────────────────────
        filters = self.config.filters
        risk    = self.config.risk

        # ── Step 2: Fetch universe ─────────────────────────────────────
        lookback = int(filters.get("lookback_days", 400))
        fetcher  = DataFetcher()
        universe = fetcher.fetch_all_universe(period_days=lookback)
        print(f"[info] Universe: {len(universe)} symbols with D/W/M data.")

        # ── Step 3: Apply reversal filter (Rules 1–5) ──────────────────
        analyzer   = ReversalAnalyzer(filters, risk)
        candidates = analyzer.screen(universe)
        print(f"[info] Reversal filter: {len(candidates)} candidates found.")

        # ── Step 4: Blackout check ─────────────────────────────────────
        bf         = EventBlackoutFilter()
        candidates = bf.apply(candidates, scan_date)

        # ── Step 5: Position sizing (server-side defaults) ─────────────
        capital  = self.config.default_capital
        risk_pct = self.config.risk_pct
        rr       = self.config.reward_multiple
        for c in candidates:
            sizing = compute_for_candidate(c, capital, risk_pct, rr)
            c.update({
                "sizing_qty":          sizing["qty"],
                "sizing_capital_req":  sizing["capital_required"],
                "sizing_potential_loss": sizing["potential_loss"],
                "sizing_potential_gain": sizing["potential_gain_1r"],
            })

        # Tag each candidate with scan_date for dashboard archiving
        for c in candidates:
            c["scan_date"] = scan_date

        # ── Step 6: Virtual paper trading ─────────────────────────────
        confirmed_only = [c for c in candidates
                          if c.get("tag") == "confirmed_entry" and not c.get("blacked_out")]

        if self.config.auto_paper_trade_enabled:
            trader = PaperTrader(config=self.config)
            # Build minimal current_prices dict from universe data
            current_prices = {}
            for c in candidates:
                sym = c["symbol"]
                d   = universe.get(sym, {}).get("daily", {})
                cl  = d.get("close", [])
                lo  = d.get("low", [])
                if len(cl) > 0:
                    current_prices[sym] = {
                        "price": float(cl[-1]),
                        "lows":  lo,
                    }
            alerts = trader.execute_trades(
                confirmed_candidates = confirmed_only,
                current_prices       = current_prices,
                blackout_filter      = bf,
                daily_data           = universe,
            )
            if alerts:
                print(f"[info] Paper trader: {len(alerts)} virtual trade alerts.")

        # ── Step 7: AI summaries (top N non-blacked-out) ───────────────
        ai_targets = [c for c in candidates if not c.get("blacked_out")][:self.MAX_AI_STOCKS]
        if ai_targets:
            summarizer = AISummarizer(
                gemini_api_key    = self.config.gemini_api_key,
                groq_api_key      = self.config.groq_api_key,
                openai_api_key    = self.config.openai_api_key,
                anthropic_api_key = self.config.anthropic_api_key,
            )
            summaries = summarizer.generate_batch_summaries(ai_targets)
            for c in candidates:
                c["ai_summary"] = summaries.get(c["symbol"], "")

        # ── Step 8: Save snapshot ──────────────────────────────────────
        self._save_snapshot(candidates)

        # ── Step 9: Dashboard generation ──────────────────────────────
        conf_list    = [c for c in candidates if c.get("tag") == "confirmed_entry" and not c.get("blacked_out")]
        watch_list   = [c for c in candidates if c.get("tag") == "early_entry"     and not c.get("blacked_out")]
        blacked_list = [c for c in candidates if c.get("blacked_out")]

        trader_state = {}
        pt_path = os.path.join(_HERE, "virtual_portfolio.json")
        if os.path.exists(pt_path):
            with open(pt_path) as fh:
                trader_state = json.load(fh)

        gen = DashboardGenerator()
        gen.generate(conf_list, watch_list, blacked_list, trader_state, scan_date)

        # ── Step 10: Telegram notification ────────────────────────────
        conf_names  = ", ".join(c["symbol"] for c in conf_list[:5])
        watch_names = ", ".join(c["symbol"] for c in watch_list[:5])

        msg = (
            f"📈 <b>RSI Reversal Scan Complete — {scan_date}</b>\n\n"
            f"✅ <b>Confirmed Entries ({len(conf_list)})</b>\n"
            f"{conf_names or 'None'}\n\n"
            f"👀 <b>Watchlist ({len(watch_list)})</b>\n"
            f"{watch_names or 'None'}\n\n"
            f"🚫 Blacked Out: {len(blacked_list)}\n\n"
            f"💼 Virtual Portfolio: {len(trader_state.get('positions', {}))} open | "
            f"₹{trader_state.get('cash_balance', 0):,.0f} cash\n\n"
            f"📊 Dashboard → check GitHub Pages"
        )
        self._notify(msg)
        print(f"[info] Full scan complete: {len(conf_list)} confirmed, {len(watch_list)} watchlist.")

    # ------------------------------------------------------------------
    # Hourly scan (breakout re-check for watchlist names)
    # ------------------------------------------------------------------

    def run_hourly(self):
        if not self.config.hourly_enabled:
            print("[info] Hourly scan disabled in config.")
            return
        if self._is_holiday():
            print("[info] Today is a holiday. Skipping hourly reversal scan.")
            return

        prev = self._load_snapshot(self.snapshot_path)
        watchlist_syms = [
            c["symbol"] for c in prev
            if c.get("tag") == "early_entry" and not c.get("blacked_out")
        ]

        if not watchlist_syms:
            print("[info] No watchlist names to re-check.")
            return

        top_n = self.config.top_n_for_hourly
        syms_to_check = watchlist_syms[:top_n]
        print(f"[info] Hourly: re-checking {len(syms_to_check)} watchlist names for breakout.")

        fetcher  = DataFetcher()
        universe = fetcher.fetch_all_universe(period_days=30, symbols=syms_to_check)

        filters   = self.config.filters
        risk      = self.config.risk
        analyzer  = ReversalAnalyzer(filters, risk)
        new_cands = analyzer.screen(universe)

        newly_confirmed = [c for c in new_cands if c.get("tag") == "confirmed_entry"]
        if not newly_confirmed:
            print("[info] Hourly: no new breakouts confirmed.")
            return

        bf = EventBlackoutFilter()
        newly_confirmed = bf.apply(newly_confirmed)
        newly_confirmed = [c for c in newly_confirmed if not c.get("blacked_out")]

        if newly_confirmed:
            names = ", ".join(c["symbol"] for c in newly_confirmed)
            msg   = (
                f"🚨 <b>RSI Reversal — NEW BREAKOUT(s) CONFIRMED</b>\n\n"
                f"{names}\n\n"
                f"Rule 3 breakout confirmed on intraday check.\n"
                f"Run /revscan for full details."
            )
            self._notify(msg)
            print(f"[info] Hourly: {len(newly_confirmed)} new breakouts → Telegram notified.")


# ── CLI entry point ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RSI Reversal Strategy Scheduler")
    parser.add_argument("--full",   action="store_true", help="Run full daily scan.")
    parser.add_argument("--hourly", action="store_true", help="Run hourly breakout re-check.")
    args = parser.parse_args()

    sched = Scheduler()

    if args.full:
        sched.run_full()
    if args.hourly:
        sched.run_hourly()
    if not (args.full or args.hourly):
        parser.print_help()
