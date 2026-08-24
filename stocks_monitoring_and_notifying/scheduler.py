"""
scheduler.py
------------
Headless execution script designed to be run via GitHub Actions.
Supports three modes:
  --full   : Daily 8 AM fetch + scan. Saves universe_snapshot.json.
  --weekly : Monday 8 AM comparison against previous week's snapshot.
  --hourly : Top N refresh running 9 AM - 4 PM.
"""

import os
import sys
import json
import argparse
from datetime import datetime
import shutil
import time

try:
    import holidays
except ImportError:
    holidays = None

from config_manager import ConfigManager
from watchlist_manager import WatchlistManager
from telegram_notifier import TelegramNotifier
from data_fetcher import DataFetcher
from uptrend_analyzer import UptrendAnalyzer
from market_health import MarketHealthChecker
from sentiment_analyzer import SentimentAnalyzer
from ai_summarizer import AISummarizer
from sector_analysis import SectorAnalyzer
from portfolio_manager import PortfolioManager
from fundamental_filter import FundamentalFilter


class Scheduler:
    def __init__(self):
        self.config = ConfigManager()
        # Require secrets for headless mode
        errors = self.config.validate(require_secrets=True)
        if errors:
            for err in errors:
                print(f"[error] {err}")
            sys.exit(1)
            
        self.watchlist_mgr = WatchlistManager()
        self.portfolio = PortfolioManager()
        self.notifier = TelegramNotifier(self.config, self.watchlist_mgr, self.portfolio)
        self.sector_analyzer = SectorAnalyzer()
        
        self.snapshot_file = os.path.join(os.path.dirname(__file__), "universe_snapshot.json")
        self.prev_snapshot_file = os.path.join(os.path.dirname(__file__), "universe_snapshot_prev.json")
        self.cache_data_file = os.path.join(os.path.dirname(__file__), "latest_universe_data.json")

    def _is_holiday(self) -> bool:
        """Check if today is an NSE holiday or weekend."""
        today = datetime.now()
        if today.weekday() >= 5:
            return True
            
        if holidays is not None:
            # Check against Indian public holidays (closest approx without custom NSE calendar)
            in_holidays = holidays.India(years=today.year)
            if today.date() in in_holidays:
                return True
                
        return False

    def _save_snapshot(self, results: list):
        """Saves current scan results, rotating the old one to prev."""
        if os.path.exists(self.snapshot_file):
            shutil.copy(self.snapshot_file, self.prev_snapshot_file)
            
        with open(self.snapshot_file, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)

    def _load_snapshot(self, filepath: str) -> list:
        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        return []

    # Max stocks to generate AI summaries for (free tier = 20 req/day,
    # batch size = 5 stocks/req, so 15 stocks = 3 API calls).
    MAX_AI_STOCKS = 15

    def _run_sentiment_and_notify(self, results: list, market_health: dict, is_weekly=False):
        """Runs the sentiment + AI pipeline and sends Telegram messages."""
        if not results:
            print("[info] No results to process.")
            if is_weekly:
                self.notifier.send_weekly_new_entries([], market_health)
            else:
                self.notifier.send_scan_results([], [], market_health)
            return

        print(f"[info] Analyzing sentiment for {len(results)} stocks...")
        
        symbols = [r["symbol"] for r in results]
        
        sentiment_analyzer = SentimentAnalyzer()
        sentiments = sentiment_analyzer.analyze_batch(symbols)
        
        ai_summarizer = AISummarizer(
            gemini_api_key=self.config.gemini_api_key,
            groq_api_key=self.config.groq_api_key,
            openai_api_key=self.config.openai_api_key,
            anthropic_api_key=self.config.anthropic_api_key
        )
        
        # Prepare items for batch AI (limit to MAX_AI_STOCKS to conserve quota)
        ai_candidates = []
        for item in results[:self.MAX_AI_STOCKS]:
            sym = item["symbol"]
            sentiment = sentiments.get(sym, {})
            ai_candidates.append({"data": item, "sentiment": sentiment})

        # Batch AI call (uses ~3 API requests for 15 stocks)
        print(f"[info] Generating AI summaries for top {len(ai_candidates)} stocks (batch mode)...")
        ai_results = ai_summarizer.generate_batch_summaries(ai_candidates)

        final_entries = []
        final_exits = []
        
        for item in results:
            sym = item["symbol"]
            sentiment = sentiments.get(sym, {})
            
            # Use AI summary if available, otherwise use a short template
            if sym in ai_results:
                ai_text = ai_results[sym]
            else:
                ai_text = (
                    f"Technical setup: RSI {item.get('rsi', 0):.1f}, "
                    f"ADX {item.get('adx', 0):.1f}, "
                    f"Slope {item.get('slope', 0):.3f}. "
                    f"Stop-loss at Rs {item.get('stop_loss', 0):.2f}."
                )
            
            ai = {"ai_summary": ai_text, "raw_news": sentiment.get("news", [])}
            
            payload = {
                "data": item,
                "sentiment": sentiment,
                "ai": ai
            }
            
            tv_rec = sentiment.get("technical", {}).get("recommendation", "")
            
            # Simple sorting logic: 
            if "BUY" in tv_rec:
                final_entries.append(payload)
            else:
                final_exits.append(payload)

        # --- NEW DASHBOARD GENERATOR ---
        from dashboard_generator import DashboardGenerator
        # Since docs is now inside stocks_monitoring_and_notifying, we point to "docs"
        dashboard_gen = DashboardGenerator(docs_dir="docs")
        dashboard_gen.generate(final_entries, final_exits, market_health)
        
        if is_weekly:
            self.notifier.send_weekly_new_entries(final_entries, market_health)
        else:
            self.notifier.send_scan_results(final_entries, final_exits, market_health)

    def run_full(self):
        """Executes the full daily scan."""
        if self._is_holiday():
            print("[info] Today is a holiday. Skipping full scan.")
            return

        print("[info] Starting full daily scan...")
        
        market_health = MarketHealthChecker().check()
        print(market_health["status_text"])
        
        filters = self.config.filters
        lookback = filters.get("lookback_days", 90)
        fetch_days = max(lookback, filters.get("sma_long", 200)) + 20
        
        fetcher = DataFetcher()
        universe_data = fetcher.fetch_all_universe(period_days=fetch_days)
        
        # Save universe data for hourly runs (we convert numpy arrays to lists)
        cache_data = {}
        for sym, d in universe_data.items():
            cache_data[sym] = {k: v.tolist() for k, v in d.items()}
        with open(self.cache_data_file, "w") as f:
            json.dump(cache_data, f)
            
        advanced = self.config.advanced
        analyzer = UptrendAnalyzer(
            sma_short=filters.get("sma_short", 50),
            sma_long=filters.get("sma_long", 200),
            rsi_min=filters.get("rsi_min", 40.0),
            rsi_max=filters.get("rsi_max", 65.0),
            adx_min=filters.get("adx_min", 25.0),
            volume_ratio_min=filters.get("volume_ratio_min", 1.0),
            atr_multiplier=filters.get("atr_stop_loss_multiplier", 1.5),
            multi_timeframe=advanced.get("multi_timeframe_alignment", True),
            use_volume_profile_stop=advanced.get("use_volume_profile_stop", True)
        )
        
        results = analyzer.filter_and_rank(universe_data, lookback_days=lookback)
        
        # Phase 4: Sector Strength
        sector_data = self.sector_analyzer.rank_sectors(results)
        top_sectors = sector_data["top_sectors"]
        print(f"[info] Top 3 strongest sectors today: {', '.join(top_sectors)}")
        
        # Apply 1.2x slope boost to stocks in top sectors
        for r in results:
            sec = self.sector_analyzer.get_sector(r["symbol"])
            if sec in top_sectors:
                r["slope"] *= 1.2
                r["sector_boost"] = True
            else:
                r["sector_boost"] = False
                
        # Re-sort after boost
        results.sort(key=lambda x: x["slope"], reverse=True)
        
        self._save_snapshot(results)
        
        print(f"[info] Full scan complete. Found {len(results)} uptrend candidates.")
        
        # Apply fundamental gate before taking top N
        advanced = self.config.advanced
        if advanced.get("fundamental_check_enabled", True):
            print("[info] Running fundamental quality check on top candidates...")
            fundamental = FundamentalFilter()
            filtered_results = []
            for r in results:
                if len(filtered_results) >= self.config.top_n_for_hourly:
                    break
                check = fundamental.check(
                    r["symbol"],
                    min_revenue_growth=advanced.get("min_revenue_growth", 0.05),
                    max_debt_equity=advanced.get("max_debt_equity", 1.5)
                )
                if check["fundamental_ok"]:
                    filtered_results.append(r)
            results = filtered_results
        
        # Limit the number of stocks processed for sentiment/AI to avoid hitting rate limits
        top_n = min(len(results), self.config.top_n_for_hourly)
        top_results = results[:top_n]
        
        # Check Trailing Stops for Portfolio
        current_prices = {r["symbol"]: {"price": r["price"], "atr": r["atr"]} for r in results}
        alerts = self.portfolio.check_trailing_stops(current_prices, self.config.portfolio)
        self.notifier.send_trailing_stop_alerts(alerts)
        
        self._run_sentiment_and_notify(top_results, market_health)

    def run_weekly(self):
        """Finds newly entered stocks compared to last week."""
        print("[info] Running weekly diff...")
        market_health = MarketHealthChecker().check()
        
        current = self._load_snapshot(self.snapshot_file)
        prev = self._load_snapshot(self.prev_snapshot_file)
        
        prev_symbols = {item["symbol"] for item in prev}
        
        new_entries = [item for item in current if item["symbol"] not in prev_symbols]
        print(f"[info] Found {len(new_entries)} new entries this week.")
        
        # Take top N of new entries
        top_n = min(len(new_entries), self.config.top_n_for_hourly)
        top_new_entries = new_entries[:top_n]
        
        self._run_sentiment_and_notify(top_new_entries, market_health, is_weekly=True)

    def run_hourly(self):
        """Runs a fast refresh using cached data."""
        if not self.config.hourly_enabled:
            print("[info] Hourly scans are disabled in config.")
            return
            
        if self._is_holiday():
            print("[info] Today is a holiday. Skipping hourly scan.")
            return

        print("[info] Running hourly refresh...")
        market_health = MarketHealthChecker().check()
        
        if not os.path.exists(self.cache_data_file):
            print("[warn] No cache found. Run --full first.")
            return
            
        with open(self.cache_data_file, "r") as f:
            raw_cache = json.load(f)
            
        # Convert lists back to numpy arrays
        import numpy as np
        universe_data = {}
        for sym, d in raw_cache.items():
            universe_data[sym] = {k: np.array(v) for k, v in d.items()}
            
        filters = self.config.filters
        lookback = filters.get("lookback_days", 90)
        
        advanced = self.config.advanced
        analyzer = UptrendAnalyzer(
            sma_short=filters.get("sma_short", 50),
            sma_long=filters.get("sma_long", 200),
            rsi_min=filters.get("rsi_min", 40.0),
            rsi_max=filters.get("rsi_max", 65.0),
            adx_min=filters.get("adx_min", 25.0),
            volume_ratio_min=filters.get("volume_ratio_min", 1.0),
            atr_multiplier=filters.get("atr_stop_loss_multiplier", 1.5),
            multi_timeframe=advanced.get("multi_timeframe_alignment", True),
            use_volume_profile_stop=advanced.get("use_volume_profile_stop", True)
        )
        
        results = analyzer.filter_and_rank(universe_data, lookback_days=lookback)
        
        # Apply sector boost if available in cache
        for r in results:
            sec = self.sector_analyzer.get_sector(r["symbol"])
            # We don't recalculate top sectors hourly, but we can still boost if we know it from daily
            # For simplicity hourly we just rank by raw slope, or apply boost if we saved top sectors.
            # To keep it simple, we won't boost hourly, we'll just take raw slope.
            pass
        
        top_n = min(len(results), self.config.top_n_for_hourly)
        top_results = results[:top_n]
        
        # Check Trailing Stops
        current_prices = {r["symbol"]: {"price": r["price"], "atr": r["atr"]} for r in results}
        alerts = self.portfolio.check_trailing_stops(current_prices, self.config.portfolio)
        self.notifier.send_trailing_stop_alerts(alerts)
        
        self._run_sentiment_and_notify(top_results, market_health)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Headless Scheduler for NSE Uptrend Scanner")
    parser.add_argument("--full", action="store_true", help="Run full daily scan.")
    parser.add_argument("--weekly", action="store_true", help="Run weekly diff (new entries).")
    parser.add_argument("--hourly", action="store_true", help="Run hourly refresh.")
    
    args = parser.parse_args()
    
    scheduler = Scheduler()
    
    if args.full:
        scheduler.run_full()
    if args.weekly:
        scheduler.run_weekly()
    if args.hourly:
        scheduler.run_hourly()
    
    if not (args.full or args.weekly or args.hourly):
        parser.print_help()
