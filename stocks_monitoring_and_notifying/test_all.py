"""
Comprehensive Test Suite for NSE Stock Screener
Tests every module individually and in combination.
"""

import sys
import os
import json
import traceback
import tempfile
import shutil

# Set working directory to project
os.chdir(os.path.dirname(__file__))

PASS = 0
FAIL = 0
ERRORS = []

def test(name, func):
    global PASS, FAIL, ERRORS
    try:
        func()
        PASS += 1
        print(f"  [PASS] {name}")
    except Exception as e:
        FAIL += 1
        err_msg = f"  [FAIL] {name}: {e}"
        ERRORS.append(err_msg)
        print(err_msg)
        traceback.print_exc()

# =========================================================================
# 1. CONFIG MANAGER
# =========================================================================
print("\n" + "=" * 60)
print("TEST MODULE: config_manager.py")
print("=" * 60)

def test_config_load():
    from config_manager import ConfigManager
    c = ConfigManager()
    assert c.config_path is not None
    assert c._data is not None

def test_config_defaults():
    from config_manager import ConfigManager
    tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w")
    tmp.write("{}")
    tmp.close()
    c = ConfigManager(config_path=tmp.name)
    assert c.filters.get("rsi_min") is not None, "Defaults not merged"
    assert c.filters.get("sma_short") == 50
    assert c.hourly_enabled == True
    os.unlink(tmp.name)

def test_config_save_and_reload():
    from config_manager import ConfigManager
    tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w")
    tmp.write("{}")
    tmp.close()
    c = ConfigManager(config_path=tmp.name)
    c._data["telegram_bot_token"] = "test_token_123"
    c.save()
    c2 = ConfigManager(config_path=tmp.name)
    assert c2.telegram_bot_token == "test_token_123"
    os.unlink(tmp.name)

def test_config_properties():
    from config_manager import ConfigManager
    c = ConfigManager()
    _ = c.telegram_bot_token
    _ = c.telegram_chat_id
    _ = c.gemini_api_key
    _ = c.groq_api_key
    _ = c.openai_api_key
    _ = c.anthropic_api_key
    _ = c.schedule
    _ = c.filters
    _ = c.hourly_enabled
    _ = c.top_n_for_hourly
    _ = c.advanced
    _ = c.portfolio
    _ = c.config

def test_config_validate():
    from config_manager import ConfigManager
    tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w")
    tmp.write("{}")
    tmp.close()
    c = ConfigManager(config_path=tmp.name)
    errors = c.validate(require_secrets=True)
    assert len(errors) > 0, "Empty config should fail validation"
    errors2 = c.validate(require_secrets=False)
    assert len(errors2) == 0
    os.unlink(tmp.name)

test("Load config", test_config_load)
test("Default merging", test_config_defaults)
test("Save + reload", test_config_save_and_reload)
test("All properties accessible", test_config_properties)
test("Validation logic", test_config_validate)

# =========================================================================
# 2. WATCHLIST MANAGER
# =========================================================================
print("\n" + "=" * 60)
print("TEST MODULE: watchlist_manager.py")
print("=" * 60)

def test_watchlist_add_remove():
    from watchlist_manager import WatchlistManager
    # WatchlistManager expects {"symbols": [...]} format
    tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w")
    json.dump({"symbols": []}, tmp)
    tmp.close()
    wl = WatchlistManager(filepath=tmp.name)
    assert wl.add("RELIANCE") == True
    assert wl.add("RELIANCE") == False  # Duplicate
    assert "RELIANCE.NS" in wl.get_all()
    assert wl.remove("RELIANCE") == True
    assert wl.remove("RELIANCE") == False
    os.unlink(tmp.name)

def test_watchlist_persistence():
    from watchlist_manager import WatchlistManager
    tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w")
    json.dump({"symbols": []}, tmp)
    tmp.close()
    wl = WatchlistManager(filepath=tmp.name)
    wl.add("INFY")
    wl2 = WatchlistManager(filepath=tmp.name)
    assert "INFY.NS" in wl2.get_all()
    os.unlink(tmp.name)

test("Add/remove symbols", test_watchlist_add_remove)
test("Persistence across instances", test_watchlist_persistence)

# =========================================================================
# 3. PORTFOLIO MANAGER
# =========================================================================
print("\n" + "=" * 60)
print("TEST MODULE: portfolio_manager.py")
print("=" * 60)

def test_portfolio_add_remove():
    from portfolio_manager import PortfolioManager
    tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w")
    tmp.write("{}")
    tmp.close()
    pm = PortfolioManager(filepath=tmp.name)
    result = pm.add_position("RELIANCE", 2500.0, 10, 2400.0)
    assert "Added" in result
    assert "RELIANCE" in pm.portfolio
    result2 = pm.add_position("RELIANCE", 2500.0, 10, 2400.0)
    assert "already" in result2
    result3 = pm.remove_position("RELIANCE")
    assert "Closed" in result3
    result4 = pm.remove_position("RELIANCE")
    assert "not found" in result4
    os.unlink(tmp.name)

def test_portfolio_trailing_stop():
    from portfolio_manager import PortfolioManager
    tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w")
    tmp.write("{}")
    tmp.close()
    pm = PortfolioManager(filepath=tmp.name)
    pm.add_position("TEST", 100.0, 10, 90.0)
    
    config = {"trailing_stop_activation_pct": 5.0, "trailing_stop_distance_atr": 1.5}
    
    # Price goes up 10% -> activate trailing stop
    alerts = pm.check_trailing_stops({"TEST": {"price": 110.0, "atr": 3.0}}, config)
    assert pm.portfolio["TEST"]["trailing_sl"] == 105.5, f"Expected 105.5, got {pm.portfolio['TEST']['trailing_sl']}"
    
    # Price drops but above SL -> no exit
    alerts2 = pm.check_trailing_stops({"TEST": {"price": 106.0, "atr": 3.0}}, config)
    assert "TEST" in pm.portfolio
    
    # Price drops below SL -> exit
    alerts3 = pm.check_trailing_stops({"TEST": {"price": 104.0, "atr": 3.0}}, config)
    assert "TEST" not in pm.portfolio, "Should have been removed on stop hit"
    assert any(a["type"] == "STOP_HIT" for a in alerts3)
    os.unlink(tmp.name)

def test_portfolio_empty_portfolio():
    from portfolio_manager import PortfolioManager
    tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w")
    tmp.write("{}")
    tmp.close()
    pm = PortfolioManager(filepath=tmp.name)
    alerts = pm.check_trailing_stops({}, {})
    assert alerts == []
    os.unlink(tmp.name)

def test_portfolio_missing_symbol_in_prices():
    from portfolio_manager import PortfolioManager
    tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w")
    tmp.write("{}")
    tmp.close()
    pm = PortfolioManager(filepath=tmp.name)
    pm.add_position("GHOST", 100, 5, 90)
    alerts = pm.check_trailing_stops({"OTHER": {"price": 50, "atr": 2}}, {})
    assert alerts == [], "Missing symbol should be silently skipped"
    assert "GHOST" in pm.portfolio
    os.unlink(tmp.name)

test("Add/remove positions", test_portfolio_add_remove)
test("Trailing stop logic", test_portfolio_trailing_stop)
test("Empty portfolio handling", test_portfolio_empty_portfolio)
test("Missing symbol in current_prices", test_portfolio_missing_symbol_in_prices)

# =========================================================================
# 4. HISTORY MANAGER
# =========================================================================
print("\n" + "=" * 60)
print("TEST MODULE: history_manager.py")
print("=" * 60)

def test_history_record_and_load():
    from history_manager import HistoryManager
    hm = HistoryManager()
    assert isinstance(hm.history, list)

def test_history_duplicate_prevention():
    from history_manager import HistoryManager
    hm = HistoryManager()
    original_len = len(hm.history)
    test_entry = [{"data": {"symbol": "__TEST_SYMBOL__", "price": 100, "stop_loss": 90}, "ai": {"ai_summary": "test"}, "sentiment": {"technical": {"recommendation": "BUY"}}}]
    hm.record_entries(test_entry)
    len_after_first = len(hm.history)
    hm.record_entries(test_entry)
    len_after_second = len(hm.history)
    assert len_after_second == len_after_first, "Duplicate prevention failed"
    # Cleanup
    hm.history = [h for h in hm.history if h["symbol"] != "__TEST_SYMBOL__"]
    hm._save_history()

def test_history_empty_analytics():
    from history_manager import HistoryManager
    hm = HistoryManager()
    orig = hm.history
    hm.history = []
    analytics = hm.calculate_analytics()
    assert analytics["total_trades"] == 0
    assert analytics["win_rate"] == 0.0
    hm.history = orig

test("Load history", test_history_record_and_load)
test("Duplicate prevention", test_history_duplicate_prevention)
test("Empty history analytics", test_history_empty_analytics)

# =========================================================================
# 5. MARKET HEALTH
# =========================================================================
print("\n" + "=" * 60)
print("TEST MODULE: market_health.py")
print("=" * 60)

def test_market_health_import():
    from market_health import MarketHealthChecker
    mhc = MarketHealthChecker()
    assert hasattr(mhc, "check")

test("Import MarketHealthChecker", test_market_health_import)

# =========================================================================
# 6. SECTOR ANALYSIS
# =========================================================================
print("\n" + "=" * 60)
print("TEST MODULE: sector_analysis.py")
print("=" * 60)

def test_sector_analysis_import():
    from sector_analysis import SectorAnalyzer
    sa = SectorAnalyzer()
    assert hasattr(sa, "rank_sectors")
    assert hasattr(sa, "get_sector")

def test_sector_get_sector():
    from sector_analysis import SectorAnalyzer
    sa = SectorAnalyzer()
    sec = sa.get_sector("RELIANCE")
    assert isinstance(sec, str)

test("Import SectorAnalyzer", test_sector_analysis_import)
test("Get sector for symbol", test_sector_get_sector)

# =========================================================================
# 7. DASHBOARD GENERATOR
# =========================================================================
print("\n" + "=" * 60)
print("TEST MODULE: dashboard_generator.py")
print("=" * 60)

def test_dashboard_import():
    from dashboard_generator import DashboardGenerator
    dg = DashboardGenerator()
    assert hasattr(dg, "generate")

def test_dashboard_generate_empty():
    from dashboard_generator import DashboardGenerator
    dg = DashboardGenerator()
    path = dg.generate([], [], {"status_text": "TEST", "nifty_close": 0, "nifty_sma": 0},
                       analytics={"total_trades": 0, "win_rate": 0, "avg_profit_pct": 0, "active_history": []},
                       portfolio={})
    assert os.path.exists(path), "Dashboard HTML not created"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "TEST" in content or "NSE" in content

def test_dashboard_generate_with_sector_badges():
    from dashboard_generator import DashboardGenerator
    dg = DashboardGenerator()
    entry = [{"data": {"symbol": "TESTSTOCK", "price": 100, "rsi": 55, "adx": 30, "stop_loss": 90, "slope": 0.5, "sector": "Technology", "sector_boost": True}, "ai": {"ai_summary": "Test summary"}, "sentiment": {"technical": {"recommendation": "BUY"}}}]
    exit_item = [{"data": {"symbol": "EXITSTOCK", "price": 50, "rsi": 75, "adx": 15, "stop_loss": 45, "slope": -0.1, "sector": "Unknown", "sector_boost": False}, "ai": {"ai_summary": "Exit test"}, "sentiment": {"technical": {"recommendation": "SELL"}}}]
    path = dg.generate(entry, exit_item, {"status_text": "BULLISH", "nifty_close": 24000, "nifty_sma": 23500},
                       analytics={"total_trades": 0, "win_rate": 0, "avg_profit_pct": 0, "active_history": []},
                       portfolio={})
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "TESTSTOCK" in content
    assert "HOT SECTOR" in content, "HOT SECTOR badge missing for sector_boost=True"
    assert "EXITSTOCK" in content

def test_dashboard_missing_sector_field():
    """Dashboard should handle stocks without sector data gracefully."""
    from dashboard_generator import DashboardGenerator
    dg = DashboardGenerator()
    entry = [{"data": {"symbol": "NOSECTOR", "price": 100, "rsi": 55, "adx": 30, "stop_loss": 90, "slope": 0.5}, "ai": {"ai_summary": "Test"}, "sentiment": {"technical": {"recommendation": "BUY"}}}]
    path = dg.generate(entry, [], {"status_text": "TEST", "nifty_close": 0, "nifty_sma": 0},
                       analytics={"total_trades": 0, "win_rate": 0, "avg_profit_pct": 0, "active_history": []},
                       portfolio={})
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "NOSECTOR" in content, "Stock without sector field should still render"

test("Import DashboardGenerator", test_dashboard_import)
test("Generate empty dashboard", test_dashboard_generate_empty)
test("Generate with sector badges", test_dashboard_generate_with_sector_badges)
test("Dashboard handles missing sector", test_dashboard_missing_sector_field)

# =========================================================================
# 8. TELEGRAM NOTIFIER (non-network tests)
# =========================================================================
print("\n" + "=" * 60)
print("TEST MODULE: telegram_notifier.py (non-network)")
print("=" * 60)

def test_telegram_import():
    from telegram_notifier import TelegramNotifier
    from config_manager import ConfigManager
    from watchlist_manager import WatchlistManager
    from portfolio_manager import PortfolioManager
    c = ConfigManager()
    w = WatchlistManager()
    p = PortfolioManager()
    tn = TelegramNotifier(c, w, p)
    assert hasattr(tn, "send_message")
    assert hasattr(tn, "send_scan_results")
    assert hasattr(tn, "_cmd_chart")
    assert hasattr(tn, "_cmd_portfolio")
    assert hasattr(tn, "_cmd_entry")
    assert hasattr(tn, "_cmd_exit")

def test_telegram_not_configured():
    from telegram_notifier import TelegramNotifier
    from config_manager import ConfigManager
    from watchlist_manager import WatchlistManager
    tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w")
    tmp.write("{}")
    tmp.close()
    c = ConfigManager(config_path=tmp.name)
    w = WatchlistManager()
    tn = TelegramNotifier(c, w)
    assert tn.is_configured == False
    os.unlink(tmp.name)

test("Import and construct TelegramNotifier", test_telegram_import)
test("Unconfigured bot detection", test_telegram_not_configured)

# =========================================================================
# 9. TECHNICAL INDICATORS
# =========================================================================
print("\n" + "=" * 60)
print("TEST MODULE: technical_indicators.py")
print("=" * 60)

def test_indicators_import():
    from technical_indicators import TechnicalIndicators
    assert hasattr(TechnicalIndicators, "compute_rsi")
    assert hasattr(TechnicalIndicators, "compute_adx")
    assert hasattr(TechnicalIndicators, "compute_atr")
    assert hasattr(TechnicalIndicators, "compute_volume_ratio")

def test_indicators_rsi():
    import numpy as np
    from technical_indicators import TechnicalIndicators
    # Steadily rising prices -> high RSI
    data = np.arange(100, 200, dtype=float)
    rsi = TechnicalIndicators.compute_rsi(data, 14)
    assert rsi > 90, f"Steadily rising RSI should be near 100, got {rsi}"

def test_indicators_rsi_insufficient_data():
    import numpy as np
    from technical_indicators import TechnicalIndicators
    data = np.array([1.0, 2.0, 3.0])
    rsi = TechnicalIndicators.compute_rsi(data, 14)
    assert np.isnan(rsi), "Insufficient data should return NaN"

test("Import TechnicalIndicators", test_indicators_import)
test("RSI calculation", test_indicators_rsi)
test("RSI with insufficient data", test_indicators_rsi_insufficient_data)

# =========================================================================
# 10. UPTREND ANALYZER
# =========================================================================
print("\n" + "=" * 60)
print("TEST MODULE: uptrend_analyzer.py")
print("=" * 60)

def test_uptrend_import():
    from uptrend_analyzer import UptrendAnalyzer
    ua = UptrendAnalyzer()
    assert hasattr(ua, "filter_and_rank")

test("Import UptrendAnalyzer", test_uptrend_import)

# =========================================================================
# 11. DATA FETCHER
# =========================================================================
print("\n" + "=" * 60)
print("TEST MODULE: data_fetcher.py")
print("=" * 60)

def test_data_fetcher_import():
    from data_fetcher import DataFetcher
    df = DataFetcher()
    assert hasattr(df, "fetch_all_universe")

test("Import DataFetcher", test_data_fetcher_import)

# =========================================================================
# 12. SCHEDULER
# =========================================================================
print("\n" + "=" * 60)
print("TEST MODULE: scheduler.py")
print("=" * 60)

def test_scheduler_import():
    from scheduler import Scheduler
    ss = Scheduler()
    assert hasattr(ss, "run_full")
    assert hasattr(ss, "run_hourly")
    assert hasattr(ss, "run_weekly")

test("Import Scheduler", test_scheduler_import)

# =========================================================================
# 13. CROSS-MODULE INTEGRATION
# =========================================================================
print("\n" + "=" * 60)
print("TEST: Cross-Module Integration")
print("=" * 60)

def test_config_to_scheduler():
    from config_manager import ConfigManager
    from scheduler import Scheduler
    c = ConfigManager()
    ss = Scheduler()
    _ = c.filters
    _ = c.schedule
    _ = c.advanced
    _ = c.portfolio
    _ = c.top_n_for_hourly

def test_portfolio_to_telegram():
    from config_manager import ConfigManager
    from watchlist_manager import WatchlistManager
    from portfolio_manager import PortfolioManager
    from telegram_notifier import TelegramNotifier
    c = ConfigManager()
    w = WatchlistManager()
    p = PortfolioManager()
    tn = TelegramNotifier(c, w, p)
    assert tn.portfolio is not None
    assert isinstance(tn.portfolio.get_portfolio(), dict)

def test_history_to_dashboard():
    from dashboard_generator import DashboardGenerator
    dg = DashboardGenerator()
    analytics = {
        "total_trades": 5,
        "win_rate": 60.0,
        "avg_profit_pct": 2.5,
        "active_history": [
            {"symbol": "TEST", "date": "2026-08-25", "entry_price": 100, "current_price": 105, "pnl_pct": 5.0, "ai_summary": "Good", "tv_signal": "BUY", "stop_loss": 90}
        ]
    }
    path = dg.generate([], [], {"status_text": "TEST", "nifty_close": 0, "nifty_sma": 0},
                       analytics=analytics, portfolio={})
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "60" in content, "Win rate not rendered"

test("Config -> Scheduler integration", test_config_to_scheduler)
test("Portfolio -> Telegram integration", test_portfolio_to_telegram)
test("History -> Dashboard integration", test_history_to_dashboard)

# =========================================================================
# 14. EDGE CASES
# =========================================================================
print("\n" + "=" * 60)
print("TEST: Edge Cases")
print("=" * 60)

def test_portfolio_zero_price():
    from portfolio_manager import PortfolioManager
    tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w")
    tmp.write("{}")
    tmp.close()
    pm = PortfolioManager(filepath=tmp.name)
    pm.add_position("ZERO", 100, 5, 90)
    alerts = pm.check_trailing_stops({"ZERO": {"price": 0, "atr": 2}}, {})
    assert "ZERO" in pm.portfolio, "Zero price should not trigger exit"
    os.unlink(tmp.name)

def test_portfolio_sl_never_decreases():
    from portfolio_manager import PortfolioManager
    tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w")
    tmp.write("{}")
    tmp.close()
    pm = PortfolioManager(filepath=tmp.name)
    pm.add_position("SL_TEST", 100, 10, 90)
    config = {"trailing_stop_activation_pct": 5.0, "trailing_stop_distance_atr": 1.5}
    # Price rises to 112 -> SL = 112 - 4.5 = 107.5
    pm.check_trailing_stops({"SL_TEST": {"price": 112, "atr": 3}}, config)
    sl_after_first = pm.portfolio["SL_TEST"]["trailing_sl"]
    # Price drops to 108 but SL should not decrease
    pm.check_trailing_stops({"SL_TEST": {"price": 108, "atr": 3}}, config)
    sl_after_second = pm.portfolio["SL_TEST"]["trailing_sl"]
    assert sl_after_second >= sl_after_first, f"SL decreased from {sl_after_first} to {sl_after_second}!"
    os.unlink(tmp.name)

def test_config_missing_file():
    from config_manager import ConfigManager
    c = ConfigManager(config_path="/nonexistent/path/config.json")
    assert c.filters is not None, "Should use defaults for missing file"

test("Portfolio with zero price", test_portfolio_zero_price)
test("Trailing SL never decreases", test_portfolio_sl_never_decreases)
test("Config with missing file", test_config_missing_file)

# =========================================================================
# SUMMARY
# =========================================================================
print("\n" + "=" * 60)
print(f"RESULTS:  {PASS} PASSED  |  {FAIL} FAILED")
print("=" * 60)
if ERRORS:
    print("\nFailed tests:")
    for e in ERRORS:
        print(e)
    sys.exit(1)
else:
    print("\n ALL TESTS PASSED! Project is solid.")
    sys.exit(0)
