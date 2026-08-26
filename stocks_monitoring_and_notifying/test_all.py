"""
test_all.py
-----------
Comprehensive test suite for the NSE Stock Screener project.
Tests every module individually and in combination.
Covers: edge cases, empty data, invalid inputs, integration paths.

Run with:
    python test_all.py
"""

import os
import sys
import json
import shutil
import tempfile
import traceback
import numpy as np

# ── Ensure project root is on the Python path ──────────────────────────
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)


# ═══════════════════════════════════════════════════════════════════════
#  Test infrastructure
# ═══════════════════════════════════════════════════════════════════════

_passed = 0
_failed = 0
_errors = []


def _run(name, fn):
    """Run a single test function, catching and recording failures."""
    global _passed, _failed
    try:
        fn()
        _passed += 1
        print(f"  ✅  {name}")
    except AssertionError as e:
        _failed += 1
        msg = f"  ❌  {name}  →  {e}"
        print(msg)
        _errors.append(msg)
    except Exception as e:
        _failed += 1
        msg = f"  💥  {name}  →  {type(e).__name__}: {e}"
        print(msg)
        _errors.append(msg)
        traceback.print_exc()


# ═══════════════════════════════════════════════════════════════════════
#  1.  ConfigManager
# ═══════════════════════════════════════════════════════════════════════

def test_config_manager():
    from config_manager import ConfigManager

    print("\n── ConfigManager ──")

    # 1a. Load from a non-existent path -> should use defaults
    def t_defaults():
        cfg = ConfigManager(config_path="__nonexistent__.json")
        assert cfg.filters is not None
        assert cfg.filters["rsi_min"] == 40
        assert cfg.filters["sma_long"] == 200
        assert cfg.hourly_enabled is True
        assert cfg.telegram_bot_token == ""
    _run("defaults on missing file", t_defaults)

    # 1b. Save and reload round-trip
    def t_save_reload():
        tmp = os.path.join(tempfile.gettempdir(), "test_config_rt.json")
        try:
            cfg = ConfigManager(config_path=tmp)
            cfg._data["telegram_bot_token"] = "TEST_TOKEN"
            cfg.save()

            cfg2 = ConfigManager(config_path=tmp)
            assert cfg2.telegram_bot_token == "TEST_TOKEN"
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)
    _run("save / reload round-trip", t_save_reload)

    # 1c. Env-var overrides
    def t_env_override():
        os.environ["TELEGRAM_BOT_TOKEN"] = "FROM_ENV"
        try:
            cfg = ConfigManager(config_path="__nonexistent__.json")
            assert cfg.telegram_bot_token == "FROM_ENV"
        finally:
            del os.environ["TELEGRAM_BOT_TOKEN"]
    _run("env-var override", t_env_override)

    # 1d. Validation
    def t_validation():
        cfg = ConfigManager(config_path="__nonexistent__.json")
        errors = cfg.validate(require_secrets=True)
        assert len(errors) >= 2  # at least token + chat_id missing
    _run("validation catches missing secrets", t_validation)

    # 1e. hourly_enabled setter
    def t_hourly_setter():
        cfg = ConfigManager(config_path="__nonexistent__.json")
        cfg.hourly_enabled = False
        assert cfg.hourly_enabled is False
        cfg.hourly_enabled = True
        assert cfg.hourly_enabled is True
    _run("hourly_enabled setter", t_hourly_setter)

    # 1f. filters property returns dict not copy (mutations propagate)
    def t_filters_mutable():
        cfg = ConfigManager(config_path="__nonexistent__.json")
        cfg.filters["rsi_min"] = 99
        assert cfg.filters["rsi_min"] == 99
    _run("filters property is mutable reference", t_filters_mutable)

    # 1g. .config property
    def t_config_property():
        cfg = ConfigManager(config_path="__nonexistent__.json")
        d = cfg.config
        assert isinstance(d, dict)
        assert "filters" in d
    _run(".config property returns full dict", t_config_property)


# ═══════════════════════════════════════════════════════════════════════
#  2.  TechnicalIndicators
# ═══════════════════════════════════════════════════════════════════════

def test_technical_indicators():
    from technical_indicators import TechnicalIndicators

    ti = TechnicalIndicators()
    print("\n── TechnicalIndicators ──")

    # 2a. RSI basic
    def t_rsi_basic():
        prices = np.array([44, 44.3, 44.1, 43.6, 44.3, 44.8, 45.1, 45.4,
                           45.1, 45.3, 44.5, 44.2, 44.7, 44.4, 44.8, 45.2])
        rsi = ti.compute_rsi(prices)
        assert 0 <= rsi <= 100, f"RSI out of range: {rsi}"
    _run("RSI basic range", t_rsi_basic)

    # 2b. RSI insufficient data
    def t_rsi_short():
        rsi = ti.compute_rsi(np.array([1.0, 2.0]))
        assert np.isnan(rsi)
    _run("RSI returns NaN for short data", t_rsi_short)

    # 2c. RSI monotonic up -> near 100
    def t_rsi_monotonic_up():
        prices = np.arange(1, 50, dtype=float)
        rsi = ti.compute_rsi(prices)
        assert rsi > 90, f"RSI should be near 100 for monotonic up, got {rsi}"
    _run("RSI near 100 for monotonic up", t_rsi_monotonic_up)

    # 2d. RSI constant prices -> 0 div guard
    def t_rsi_flat():
        prices = np.full(30, 100.0)
        rsi = ti.compute_rsi(prices)
        assert rsi == 100.0  # avg_loss == 0 => rsi = 100
    _run("RSI flat prices (no division by zero)", t_rsi_flat)

    # 2e. ADX basic
    def t_adx_basic():
        np.random.seed(42)
        n = 100
        high = np.cumsum(np.random.uniform(0, 2, n)) + 100
        low = high - np.random.uniform(1, 3, n)
        close = (high + low) / 2
        adx = ti.compute_adx(high, low, close)
        assert not np.isnan(adx), "ADX should not be NaN with 100 bars"
        assert adx >= 0, f"ADX should be non-negative, got {adx}"
    _run("ADX basic computation", t_adx_basic)

    # 2f. ADX insufficient data
    def t_adx_short():
        adx = ti.compute_adx(np.array([1.0]), np.array([0.5]), np.array([0.8]))
        assert np.isnan(adx)
    _run("ADX returns NaN for short data", t_adx_short)

    # 2g. ATR basic
    def t_atr_basic():
        np.random.seed(42)
        n = 30
        high = np.arange(n, dtype=float) + 100
        low = high - 5
        close = high - 2
        atr = ti.compute_atr(high, low, close)
        assert not np.isnan(atr)
        assert atr > 0
    _run("ATR basic computation", t_atr_basic)

    # 2h. ATR insufficient data
    def t_atr_short():
        atr = ti.compute_atr(np.array([10.0]), np.array([8.0]), np.array([9.0]))
        assert np.isnan(atr)
    _run("ATR returns NaN for short data", t_atr_short)

    # 2i. Volume ratio
    def t_vol_ratio():
        vol = np.ones(30) * 1000
        vol[-1] = 2000  # today is 2x avg
        ratio = ti.compute_volume_ratio(vol)
        assert abs(ratio - 2.0) < 0.01
    _run("volume ratio 2x", t_vol_ratio)

    # 2j. Volume ratio zero avg
    def t_vol_ratio_zero():
        vol = np.zeros(30)
        ratio = ti.compute_volume_ratio(vol)
        assert np.isnan(ratio)
    _run("volume ratio NaN on zero volume", t_vol_ratio_zero)


# ═══════════════════════════════════════════════════════════════════════
#  3.  VolumeProfiler
# ═══════════════════════════════════════════════════════════════════════

def test_volume_profiler():
    from volume_profile import VolumeProfiler

    vp = VolumeProfiler()
    print("\n── VolumeProfiler ──")

    # 3a. Normal profile
    def t_profile_basic():
        np.random.seed(42)
        n = 100
        close = np.cumsum(np.random.normal(0, 1, n)) + 100
        high = close + np.abs(np.random.normal(0, 0.5, n))
        low = close - np.abs(np.random.normal(0, 0.5, n))
        volume = np.random.uniform(100000, 500000, n)
        result = vp.compute_profile(high, low, close, volume)
        assert "poc_price" in result
        assert result["poc_volume"] > 0
        assert result["value_area_low"] <= result["poc_price"] <= result["value_area_high"]
    _run("basic profile computation", t_profile_basic)

    # 3b. Insufficient data fallback
    def t_profile_short():
        result = vp.compute_profile(
            np.array([10.0, 11.0]),
            np.array([9.0, 10.0]),
            np.array([9.5, 10.5]),
            np.array([1000, 2000]),
        )
        assert result["profile"] == []  # empty profile indicates fallback
    _run("profile fallback on short data", t_profile_short)

    # 3c. Smart stop loss
    def t_smart_sl():
        np.random.seed(42)
        n = 100
        close = np.cumsum(np.random.normal(0, 1, n)) + 100
        high = close + 1
        low = close - 1
        volume = np.ones(n) * 100000
        result = vp.compute_smart_stop_loss(high, low, close, volume, atr=2.0)
        assert "stop_loss" in result
        assert result["method"] in ("ATR", "VOLUME_PROFILE")
        assert result["stop_loss"] < float(close[-1])
    _run("smart stop loss < current price", t_smart_sl)


# ═══════════════════════════════════════════════════════════════════════
#  4.  UptrendAnalyzer
# ═══════════════════════════════════════════════════════════════════════

def test_uptrend_analyzer():
    from uptrend_analyzer import UptrendAnalyzer

    print("\n── UptrendAnalyzer ──")

    # 4a. Perfect uptrend stock should pass
    def t_perfect_uptrend():
        analyzer = UptrendAnalyzer(
            sma_short=50, sma_long=200,
            rsi_min=0, rsi_max=100,  # fully open RSI window
            adx_min=0,  # disable ADX gate
            volume_ratio_min=0,  # disable volume gate
            multi_timeframe=False,
            use_volume_profile_stop=False,
        )
        np.random.seed(123)
        n = 250
        # Strong uptrend with some noise
        close = np.linspace(50, 150, n) + np.random.normal(0, 0.5, n)
        high = close + 1
        low = close - 1
        volume = np.ones(n) * 100000
        universe = {"TEST": {"close": close, "high": high, "low": low, "volume": volume}}
        results = analyzer.filter_and_rank(universe)
        assert len(results) >= 1, "Perfect uptrend should pass all filters"
        assert results[0]["symbol"] == "TEST"
        assert results[0]["slope"] > 0
    _run("perfect uptrend passes filters", t_perfect_uptrend)

    # 4b. Downtrend stock should fail SMA filter
    def t_downtrend_fails():
        analyzer = UptrendAnalyzer(multi_timeframe=False, use_volume_profile_stop=False)
        n = 250
        close = np.linspace(150, 50, n)  # downtrend
        high = close + 1
        low = close - 1
        volume = np.ones(n) * 100000
        universe = {"DOWN": {"close": close, "high": high, "low": low, "volume": volume}}
        results = analyzer.filter_and_rank(universe)
        assert len(results) == 0, "Downtrend should not pass SMA filter"
    _run("downtrend fails SMA filter", t_downtrend_fails)

    # 4c. Empty universe
    def t_empty_universe():
        analyzer = UptrendAnalyzer()
        results = analyzer.filter_and_rank({})
        assert results == []
    _run("empty universe returns empty list", t_empty_universe)

    # 4d. Short data filtered out
    def t_short_data():
        analyzer = UptrendAnalyzer()
        universe = {"SHORT": {"close": np.array([100.0, 101.0]),
                              "high": np.array([101.0, 102.0]),
                              "low": np.array([99.0, 100.0]),
                              "volume": np.array([1000, 1000])}}
        results = analyzer.filter_and_rank(universe)
        assert len(results) == 0
    _run("short data (< sma_long) is filtered", t_short_data)

    # 4e. Backwards compatibility with plain arrays
    def t_plain_array():
        analyzer = UptrendAnalyzer(
            sma_short=5, sma_long=10,
            rsi_min=0, rsi_max=100,
            adx_min=0, volume_ratio_min=0,
            multi_timeframe=False, use_volume_profile_stop=False,
        )
        close = np.linspace(50, 100, 30)
        universe = {"PLAIN": close}
        results = analyzer.filter_and_rank(universe, lookback_days=10)
        # Should not crash
        assert isinstance(results, list)
    _run("plain ndarray backwards compatibility", t_plain_array)

    # 4f. Slope is 0 for flat prices
    def t_slope_flat():
        close = np.full(100, 100.0)
        slope = UptrendAnalyzer._slope(close, 90)
        assert slope == 0.0
    _run("slope is 0 for flat prices", t_slope_flat)


# ═══════════════════════════════════════════════════════════════════════
#  5.  WatchlistManager
# ═══════════════════════════════════════════════════════════════════════

def test_watchlist_manager():
    from watchlist_manager import WatchlistManager

    print("\n── WatchlistManager ──")
    tmp = os.path.join(tempfile.gettempdir(), "test_watchlist.json")

    def cleanup():
        if os.path.exists(tmp):
            os.remove(tmp)

    # 5a. Add and retrieve
    def t_add():
        cleanup()
        wm = WatchlistManager(filepath=tmp)
        assert wm.add("RELIANCE")
        items = wm.get_all()
        assert "RELIANCE.NS" in items
    _run("add symbol", t_add)

    # 5b. Duplicate add returns False
    def t_dup():
        cleanup()
        wm = WatchlistManager(filepath=tmp)
        wm.add("INFY")
        assert wm.add("INFY") is False
    _run("duplicate add returns False", t_dup)

    # 5c. Remove
    def t_remove():
        cleanup()
        wm = WatchlistManager(filepath=tmp)
        wm.add("TCS")
        assert wm.remove("TCS")
        assert "TCS.NS" not in wm.get_all()
    _run("remove symbol", t_remove)

    # 5d. Remove non-existent
    def t_remove_missing():
        cleanup()
        wm = WatchlistManager(filepath=tmp)
        assert wm.remove("NOPE") is False
    _run("remove non-existent returns False", t_remove_missing)

    # 5e. Persistence
    def t_persist():
        cleanup()
        wm1 = WatchlistManager(filepath=tmp)
        wm1.add("HDFC")
        wm2 = WatchlistManager(filepath=tmp)
        assert "HDFC.NS" in wm2.get_all()
    _run("persistence across loads", t_persist)

    cleanup()


# ═══════════════════════════════════════════════════════════════════════
#  6.  PortfolioManager
# ═══════════════════════════════════════════════════════════════════════

def test_portfolio_manager():
    from portfolio_manager import PortfolioManager

    print("\n── PortfolioManager ──")
    tmp = os.path.join(tempfile.gettempdir(), "test_portfolio.json")

    def cleanup():
        if os.path.exists(tmp):
            os.remove(tmp)

    # 6a. Add position
    def t_add():
        cleanup()
        pm = PortfolioManager(filepath=tmp)
        result = pm.add_position("RELIANCE", 2500, 10, 2400)
        assert "✅" in result
        assert "RELIANCE" in pm.portfolio
        assert pm.portfolio["RELIANCE"]["entry_price"] == 2500
    _run("add position", t_add)

    # 6b. Duplicate add
    def t_dup():
        cleanup()
        pm = PortfolioManager(filepath=tmp)
        pm.add_position("INFY", 1500, 5, 1400)
        result = pm.add_position("INFY", 1600, 3, 1500)
        assert "already" in result
    _run("duplicate add blocked", t_dup)

    # 6c. Remove position
    def t_remove():
        cleanup()
        pm = PortfolioManager(filepath=tmp)
        pm.add_position("TCS", 3500, 2, 3400)
        result = pm.remove_position("TCS")
        assert "✅" in result
        assert "TCS" not in pm.portfolio
    _run("remove position", t_remove)

    # 6d. Remove non-existent
    def t_remove_missing():
        cleanup()
        pm = PortfolioManager(filepath=tmp)
        result = pm.remove_position("NOPE")
        assert "❌" in result
    _run("remove non-existent", t_remove_missing)

    # 6e. Trailing stop NOT HIT (price above SL)
    def t_trail_no_hit():
        cleanup()
        pm = PortfolioManager(filepath=tmp)
        pm.add_position("X", 100, 10, 90)
        alerts = pm.check_trailing_stops(
            {"X": {"price": 105, "atr": 5}},
            {"trailing_stop_activation_pct": 5.0, "trailing_stop_distance_atr": 1.5}
        )
        stop_hits = [a for a in alerts if a["type"] == "STOP_HIT"]
        assert len(stop_hits) == 0
    _run("trailing stop not hit when price above SL", t_trail_no_hit)

    # 6f. Trailing stop HIT
    def t_trail_hit():
        cleanup()
        pm = PortfolioManager(filepath=tmp)
        pm.add_position("Y", 100, 10, 95)
        alerts = pm.check_trailing_stops(
            {"Y": {"price": 90, "atr": 5}},
            {"trailing_stop_activation_pct": 5.0, "trailing_stop_distance_atr": 1.5}
        )
        stop_hits = [a for a in alerts if a["type"] == "STOP_HIT"]
        assert len(stop_hits) == 1
        assert stop_hits[0]["pnl"] == (90 - 100) * 10  # -100
        assert "Y" not in pm.portfolio
    _run("trailing stop hit removes position", t_trail_hit)

    # 6g. Trailing stop UPDATES upward
    def t_trail_update():
        cleanup()
        pm = PortfolioManager(filepath=tmp)
        pm.add_position("Z", 100, 10, 90)
        # Simulate price rising to 120 (20% above entry, well past 5% activation)
        pm.portfolio["Z"]["highest_price"] = 120
        alerts = pm.check_trailing_stops(
            {"Z": {"price": 120, "atr": 5}},
            {"trailing_stop_activation_pct": 5.0, "trailing_stop_distance_atr": 1.5}
        )
        updates = [a for a in alerts if a["type"] == "STOP_UPDATED"]
        assert len(updates) == 1
        assert pm.portfolio["Z"]["trailing_sl"] > 90  # moved up from initial
    _run("trailing stop updates upward", t_trail_update)

    # 6h. Missing symbol in current_prices is skipped
    def t_missing_symbol():
        cleanup()
        pm = PortfolioManager(filepath=tmp)
        pm.add_position("A", 100, 1, 90)
        alerts = pm.check_trailing_stops(
            {},  # no data for A
            {"trailing_stop_activation_pct": 5.0, "trailing_stop_distance_atr": 1.5}
        )
        assert len(alerts) == 0
        assert "A" in pm.portfolio  # position still there
    _run("missing symbol in prices is skipped", t_missing_symbol)

    # 6i. Zero price is skipped
    def t_zero_price():
        cleanup()
        pm = PortfolioManager(filepath=tmp)
        pm.add_position("B", 100, 1, 90)
        alerts = pm.check_trailing_stops(
            {"B": {"price": 0, "atr": 5}},
            {"trailing_stop_activation_pct": 5.0, "trailing_stop_distance_atr": 1.5}
        )
        assert len(alerts) == 0
    _run("zero price is skipped", t_zero_price)

    # 6j. Persistence
    def t_persist():
        cleanup()
        pm1 = PortfolioManager(filepath=tmp)
        pm1.add_position("P", 200, 5, 180)
        pm2 = PortfolioManager(filepath=tmp)
        assert "P" in pm2.portfolio
    _run("portfolio persists across loads", t_persist)

    cleanup()


# ═══════════════════════════════════════════════════════════════════════
#  7.  MarketHealthChecker
# ═══════════════════════════════════════════════════════════════════════

def test_market_health():
    from market_health import MarketHealthChecker

    print("\n── MarketHealthChecker ──")

    # 7a. Fallback method
    def t_fallback():
        result = MarketHealthChecker._fallback("test reason")
        assert result["is_bullish"] is True
        assert "test reason" in result["status_text"]
    _run("fallback returns bullish with reason", t_fallback)

    # 7b. Check returns required keys
    def t_check_keys():
        mh = MarketHealthChecker()
        result = mh.check()
        required = {"is_bullish", "nifty_close", "nifty_sma50", "status_emoji", "status_text"}
        assert required <= set(result.keys()), f"Missing keys: {required - set(result.keys())}"
    _run("check() returns all required keys", t_check_keys)


# ═══════════════════════════════════════════════════════════════════════
#  8.  HistoryManager
# ═══════════════════════════════════════════════════════════════════════

def test_history_manager():
    from history_manager import HistoryManager

    print("\n── HistoryManager ──")

    # Monkey-patch the filepath for testing
    def make_hm():
        hm = HistoryManager()
        hm.filepath = os.path.join(tempfile.gettempdir(), "test_history.json")
        hm.history = []
        return hm

    # 8a. Record entries
    def t_record():
        hm = make_hm()
        entries = [
            {"data": {"symbol": "INFY", "price": 1500, "stop_loss": 1400},
             "ai": {"ai_summary": "bullish"},
             "sentiment": {"technical": {"recommendation": "BUY"}}},
        ]
        hm.record_entries(entries)
        assert len(hm.history) == 1
        assert hm.history[0]["symbol"] == "INFY"
    _run("record entries", t_record)

    # 8b. Deduplication on same day
    def t_dedup():
        hm = make_hm()
        entries = [
            {"data": {"symbol": "INFY", "price": 1500, "stop_loss": 1400},
             "ai": {"ai_summary": "bullish"},
             "sentiment": {"technical": {"recommendation": "BUY"}}},
        ]
        hm.record_entries(entries)
        hm.record_entries(entries)  # same day
        assert len(hm.history) == 1
    _run("deduplication on same day", t_dedup)

    # 8c. Calculate analytics with empty history
    def t_analytics_empty():
        hm = make_hm()
        result = hm.calculate_analytics()
        assert result["total_trades"] == 0
        assert result["win_rate"] == 0.0
    _run("analytics on empty history", t_analytics_empty)

    # Cleanup
    tmp = os.path.join(tempfile.gettempdir(), "test_history.json")
    if os.path.exists(tmp):
        os.remove(tmp)


# ═══════════════════════════════════════════════════════════════════════
#  9.  SectorAnalyzer
# ═══════════════════════════════════════════════════════════════════════

def test_sector_analyzer():
    from sector_analysis import SectorAnalyzer

    print("\n── SectorAnalyzer ──")

    # 9a. rank_sectors with mock data
    def t_rank():
        sa = SectorAnalyzer()
        # Pre-populate cache so no yfinance calls needed
        sa.sector_map = {
            "A": "IT",
            "B": "IT",
            "C": "Auto",
            "D": "Pharma",
        }
        results = [
            {"symbol": "A", "slope": 0.5},
            {"symbol": "B", "slope": 0.4},
            {"symbol": "C", "slope": 0.3},
            {"symbol": "D", "slope": 0.1},
        ]
        data = sa.rank_sectors(results)
        assert "top_sectors" in data
        assert len(data["top_sectors"]) <= 3
        # IT should be top since it has most stocks and highest avg slope
        assert data["top_sectors"][0] == "IT"
    _run("sector ranking", t_rank)

    # 9b. get_sector from cache
    def t_cache():
        sa = SectorAnalyzer()
        sa.sector_map = {"RELIANCE": "Energy"}
        assert sa.get_sector("RELIANCE") == "Energy"
    _run("get_sector from cache", t_cache)

    # 9c. Empty results
    def t_empty():
        sa = SectorAnalyzer()
        data = sa.rank_sectors([])
        assert data["top_sectors"] == []
    _run("empty results -> empty ranking", t_empty)


# ═══════════════════════════════════════════════════════════════════════
# 10. DashboardGenerator
# ═══════════════════════════════════════════════════════════════════════

def test_dashboard_generator():
    from dashboard_generator import DashboardGenerator

    print("\n── DashboardGenerator ──")

    # 10a. Generate with empty data
    def t_empty():
        tmp_dir = os.path.join(tempfile.gettempdir(), "test_dashboard")
        os.makedirs(tmp_dir, exist_ok=True)
        dg = DashboardGenerator(docs_dir=tmp_dir)
        path = dg.generate(
            entries=[], exits=[],
            market_health={"status": "BULLISH", "nifty_price": 24000, "nifty_50_sma": 23500, "is_bullish": True},
            analytics={"total_trades": 0, "win_rate": 0, "avg_profit_pct": 0},
            portfolio={}
        )
        assert os.path.exists(path)
        with open(path, "r", encoding="utf-8") as f:
            html = f.read()
        assert "NSE" in html
        shutil.rmtree(tmp_dir)
    _run("generate with empty data", t_empty)

    # 10b. Generate with sample entries
    def t_entries():
        tmp_dir = os.path.join(tempfile.gettempdir(), "test_dashboard2")
        os.makedirs(tmp_dir, exist_ok=True)
        dg = DashboardGenerator(docs_dir=tmp_dir)
        entries = [{
            "data": {"symbol": "INFY", "price": 1500, "rsi": 55, "adx": 30,
                     "stop_loss": 1400, "slope": 0.5, "sector": "IT", "sector_boost": True},
            "ai": {"ai_summary": "Bullish setup"},
            "sentiment": {"technical": {"recommendation": "BUY"}}
        }]
        path = dg.generate(
            entries=entries, exits=[],
            market_health={"status": "BULLISH", "nifty_price": 24000, "nifty_50_sma": 23500, "is_bullish": True},
            analytics={"total_trades": 1, "win_rate": 100, "avg_profit_pct": 5.0},
            portfolio={}
        )
        with open(path, "r", encoding="utf-8") as f:
            html = f.read()
        assert "INFY" in html
        assert "HOT SECTOR" in html
        shutil.rmtree(tmp_dir)
    _run("generate with entries (HOT SECTOR badge)", t_entries)


# ═══════════════════════════════════════════════════════════════════════
# 11. TelegramNotifier (unit tests, no real API calls)
# ═══════════════════════════════════════════════════════════════════════

def test_telegram_notifier():
    from telegram_notifier import TelegramNotifier
    from config_manager import ConfigManager
    from watchlist_manager import WatchlistManager
    from portfolio_manager import PortfolioManager

    print("\n── TelegramNotifier ──")

    # 11a. Not configured when tokens missing
    def t_not_configured():
        cfg = ConfigManager(config_path="__nonexistent__.json")
        wm = WatchlistManager(filepath=os.path.join(tempfile.gettempdir(), "tw.json"))
        pm = PortfolioManager(filepath=os.path.join(tempfile.gettempdir(), "tp.json"))
        tn = TelegramNotifier(cfg, wm, pm)
        assert tn.is_configured is False
    _run("not configured when tokens missing", t_not_configured)

    # 11b. Message splitting
    def t_split():
        cfg = ConfigManager(config_path="__nonexistent__.json")
        wm = WatchlistManager(filepath=os.path.join(tempfile.gettempdir(), "tw2.json"))
        tn = TelegramNotifier(cfg, wm)
        # Create a message larger than 4096 chars
        long_msg = "Line\n" * 1500
        chunks = tn._split_message(long_msg)
        assert len(chunks) > 1
        for chunk in chunks:
            assert len(chunk) <= TelegramNotifier.MAX_MSG_LEN
    _run("message splitting respects 4096 limit", t_split)

    # 11c. send_message does NOT crash when not configured
    def t_send_noop():
        cfg = ConfigManager(config_path="__nonexistent__.json")
        wm = WatchlistManager(filepath=os.path.join(tempfile.gettempdir(), "tw3.json"))
        tn = TelegramNotifier(cfg, wm)
        tn.send_message("test")  # should silently do nothing
    _run("send_message is no-op when not configured", t_send_noop)

    # Cleanup temp watchlist files
    for f in ["tw.json", "tw2.json", "tw3.json", "tp.json"]:
        p = os.path.join(tempfile.gettempdir(), f)
        if os.path.exists(p):
            os.remove(p)


# ═══════════════════════════════════════════════════════════════════════
# 12. Integration: Full pipeline (ConfigManager + UptrendAnalyzer + Dashboard)
# ═══════════════════════════════════════════════════════════════════════

def test_integration_pipeline():
    from config_manager import ConfigManager
    from uptrend_analyzer import UptrendAnalyzer
    from dashboard_generator import DashboardGenerator
    from history_manager import HistoryManager

    print("\n── Integration Pipeline ──")

    # 12a. Config -> Analyzer -> Dashboard end-to-end
    def t_full_pipeline():
        cfg = ConfigManager(config_path="__nonexistent__.json")

        analyzer = UptrendAnalyzer(
            sma_short=50,
            sma_long=200,
            rsi_min=0, rsi_max=100,  # fully open
            adx_min=0,
            volume_ratio_min=0,
            multi_timeframe=False,
            use_volume_profile_stop=False,
        )

        np.random.seed(456)
        n = 250
        close = np.linspace(50, 150, n) + np.random.normal(0, 0.3, n)
        high = close + 1
        low = close - 1
        volume = np.ones(n) * 100000

        universe = {"TESTSTOCK": {"close": close, "high": high, "low": low, "volume": volume}}
        results = analyzer.filter_and_rank(universe)

        # Build dashboard payload
        entry_list = []
        for r in results:
            entry_list.append({
                "data": {**r, "sector": "Test", "sector_boost": False},
                "ai": {"ai_summary": "Test summary"},
                "sentiment": {"technical": {"recommendation": "BUY"}}
            })

        tmp_dir = os.path.join(tempfile.gettempdir(), "test_integration")
        os.makedirs(tmp_dir, exist_ok=True)
        dg = DashboardGenerator(docs_dir=tmp_dir)
        path = dg.generate(
            entries=entry_list, exits=[],
            market_health={"status": "BULLISH", "nifty_price": 24000, "nifty_50_sma": 23500, "is_bullish": True},
            analytics={"total_trades": 0, "win_rate": 0, "avg_profit_pct": 0},
            portfolio={}
        )
        assert os.path.exists(path)
        with open(path, "r", encoding="utf-8") as f:
            html = f.read()
        assert "TESTSTOCK" in html

        shutil.rmtree(tmp_dir)
    _run("Config → Analyzer → Dashboard end-to-end", t_full_pipeline)

    # 12b. Portfolio + Trailing stops integration
    def t_portfolio_integration():
        from portfolio_manager import PortfolioManager
        tmp = os.path.join(tempfile.gettempdir(), "test_port_int.json")
        pm = PortfolioManager(filepath=tmp)
        pm.add_position("STOCK1", 100, 10, 90)
        pm.add_position("STOCK2", 200, 5, 180)

        # Simulate: STOCK1 hit stop, STOCK2 going up
        alerts = pm.check_trailing_stops(
            {
                "STOCK1": {"price": 85, "atr": 5},
                "STOCK2": {"price": 220, "atr": 10},
            },
            {"trailing_stop_activation_pct": 5.0, "trailing_stop_distance_atr": 1.5}
        )

        # STOCK1 should be stopped out
        hits = [a for a in alerts if a["type"] == "STOP_HIT"]
        assert len(hits) == 1
        assert hits[0]["symbol"] == "STOCK1"
        assert "STOCK1" not in pm.portfolio

        # STOCK2 should have updated trailing stop
        updates = [a for a in alerts if a["type"] == "STOP_UPDATED"]
        assert len(updates) == 1
        assert pm.portfolio["STOCK2"]["trailing_sl"] > 180

        if os.path.exists(tmp):
            os.remove(tmp)
    _run("portfolio multi-stock trailing stops", t_portfolio_integration)

    # 12c. HistoryManager + DashboardGenerator
    def t_history_dashboard():
        hm = HistoryManager()
        hm.filepath = os.path.join(tempfile.gettempdir(), "test_hist_dash.json")
        hm.history = []

        entries = [
            {"data": {"symbol": "A", "price": 100, "stop_loss": 90},
             "ai": {"ai_summary": "OK"},
             "sentiment": {"technical": {"recommendation": "BUY"}}},
        ]
        hm.record_entries(entries)
        assert len(hm.history) == 1

        # Verify it persists
        hm2 = HistoryManager()
        hm2.filepath = hm.filepath
        hm2._load_history()
        assert len(hm2.history) == 1

        if os.path.exists(hm.filepath):
            os.remove(hm.filepath)
    _run("history record + reload", t_history_dashboard)


# ═══════════════════════════════════════════════════════════════════════
# 13. FundamentalFilter (cache logic only, no live API)
# ═══════════════════════════════════════════════════════════════════════

def test_fundamental_filter():
    from fundamental_filter import FundamentalFilter

    print("\n── FundamentalFilter ──")

    # 13a. Healthy stock passes
    def t_healthy():
        ff = FundamentalFilter()
        ff.cache = {
            "HEALTHY": {
                "eps": 50,
                "revenue_growth": 0.15,
                "debt_to_equity": 80,  # yfinance returns as percentage
                "market_cap": 1e12,
                "sector": "IT",
                "fetched_at": "2026-08-26T00:00:00",
                "status": "OK",
            }
        }
        result = ff.check("HEALTHY")
        assert result["fundamental_ok"] is True
        assert "✅" in result["flags"][0]
    _run("healthy stock passes all checks", t_healthy)

    # 13b. Negative EPS fails
    def t_neg_eps():
        ff = FundamentalFilter()
        ff.cache = {
            "BADEPS": {
                "eps": -5,
                "revenue_growth": 0.2,
                "debt_to_equity": 50,
                "fetched_at": "2026-08-26T00:00:00",
                "status": "OK",
            }
        }
        result = ff.check("BADEPS")
        assert result["fundamental_ok"] is False
        assert any("Negative EPS" in f for f in result["flags"])
    _run("negative EPS fails", t_neg_eps)

    # 13c. High debt fails
    def t_high_debt():
        ff = FundamentalFilter()
        ff.cache = {
            "DEBT": {
                "eps": 10,
                "revenue_growth": 0.1,
                "debt_to_equity": 300,  # 3.0x as percentage
                "fetched_at": "2026-08-26T00:00:00",
                "status": "OK",
            }
        }
        result = ff.check("DEBT", max_debt_equity=1.5)
        assert result["fundamental_ok"] is False
        assert any("Debt" in f for f in result["flags"])
    _run("high debt fails", t_high_debt)

    # 13d. Error status lets stock pass (don't block on API errors)
    def t_error_passes():
        ff = FundamentalFilter()
        ff.cache = {
            "ERR": {
                "status": "ERROR",
                "reason": "rate limit",
                "fetched_at": "2026-08-26T00:00:00",
            }
        }
        result = ff.check("ERR")
        assert result["fundamental_ok"] is True
    _run("API error doesn't block stock", t_error_passes)


# ═══════════════════════════════════════════════════════════════════════
# 14. Edge cases & stress tests
# ═══════════════════════════════════════════════════════════════════════

def test_edge_cases():
    print("\n── Edge Cases & Stress Tests ──")

    # 14a. Large universe doesn't crash
    def t_large_universe():
        from uptrend_analyzer import UptrendAnalyzer
        analyzer = UptrendAnalyzer(
            adx_min=0, volume_ratio_min=0,
            multi_timeframe=False, use_volume_profile_stop=False,
            rsi_min=0, rsi_max=100,
        )
        universe = {}
        for i in range(100):
            n = 250
            close = np.linspace(50, 150, n) + np.random.normal(0, 0.5, n)
            universe[f"STOCK{i}"] = {
                "close": close, "high": close + 1,
                "low": close - 1, "volume": np.ones(n) * 100000
            }
        results = analyzer.filter_and_rank(universe)
        assert isinstance(results, list)
    _run("100-stock universe doesn't crash", t_large_universe)

    # 14b. NaN in price data
    def t_nan_prices():
        from technical_indicators import TechnicalIndicators
        ti = TechnicalIndicators()
        prices = np.array([1.0, 2.0, np.nan, 4.0, 5.0] * 10)
        rsi = ti.compute_rsi(prices)
        # Should return NaN or a number (not crash)
        assert isinstance(rsi, (float, np.floating))
    _run("NaN in prices doesn't crash RSI", t_nan_prices)

    # 14c. Extremely small array
    def t_tiny_array():
        from technical_indicators import TechnicalIndicators
        ti = TechnicalIndicators()
        assert np.isnan(ti.compute_rsi(np.array([])))
        assert np.isnan(ti.compute_atr(np.array([]), np.array([]), np.array([])))
    _run("empty array returns NaN", t_tiny_array)

    # 14d. JSON file corruption recovery
    def t_corrupted_json():
        from watchlist_manager import WatchlistManager
        tmp = os.path.join(tempfile.gettempdir(), "corrupted.json")
        with open(tmp, "w") as f:
            f.write("{invalid json!!!")
        wm = WatchlistManager(filepath=tmp)
        assert wm.get_all() == []  # graceful recovery
        os.remove(tmp)
    _run("corrupted JSON recovery", t_corrupted_json)

    # 14e. Portfolio with no config keys
    def t_portfolio_no_config():
        from portfolio_manager import PortfolioManager
        tmp = os.path.join(tempfile.gettempdir(), "tp_edge.json")
        pm = PortfolioManager(filepath=tmp)
        pm.add_position("X", 100, 1, 90)
        # Pass empty config dict
        alerts = pm.check_trailing_stops(
            {"X": {"price": 105, "atr": 5}},
            {}  # empty config -> should use defaults
        )
        assert isinstance(alerts, list)
        if os.path.exists(tmp):
            os.remove(tmp)
    _run("portfolio with empty config dict", t_portfolio_no_config)


# ═══════════════════════════════════════════════════════════════════════
#  Run all tests
# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 60)
    print("  NSE Stock Screener — Comprehensive Test Suite")
    print("=" * 60)

    test_config_manager()
    test_technical_indicators()
    test_volume_profiler()
    test_uptrend_analyzer()
    test_watchlist_manager()
    test_portfolio_manager()
    test_market_health()
    test_history_manager()
    test_sector_analyzer()
    test_dashboard_generator()
    test_telegram_notifier()
    test_integration_pipeline()
    test_fundamental_filter()
    test_edge_cases()

    print("\n" + "=" * 60)
    print(f"  RESULTS:  ✅ {_passed} passed   ❌ {_failed} failed")
    print("=" * 60)

    if _errors:
        print("\n  Failures:")
        for e in _errors:
            print(f"    {e}")
        sys.exit(1)
    else:
        print("\n  🎉 ALL TESTS PASSED — Project is rock solid!")
        sys.exit(0)
