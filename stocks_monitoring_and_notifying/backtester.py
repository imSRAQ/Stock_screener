"""
backtester.py
==============
Utility to back‑test the up‑trend pipeline (including multi‑timeframe
alignment, volume‑profile stop‑loss and fundamental filter) against
historical daily data.

Usage (run from the repository root)::

    python backtester.py --symbols AAPL MSFT --start 2022-01-01 --end 2023-01-01

The script:
1. Loads the list of symbols (either from the CLI or from a file).
2. Pulls daily OHLCV data for the full period using ``yfinance``.
3. Walks through each trading day, calling ``UptrendAnalyzer`` with the
   data available *up to* that day (so the strategy never looks ahead).
4. When a stock passes the filter it is entered into a virtual portfolio
   (``PortfolioManager``).  The portfolio is updated each day with the
   trailing‑stop logic (ATR or Volume‑Profile based).
5. At the end it prints a concise performance report:
   - Total profit / loss
   - Win‑rate
   - Max draw‑down
   - Number of trades

The module is deliberately self‑contained – it does **not** rely on any
GitHub‑Actions or live‑bot components, making it safe to run locally.
"""

import argparse
import datetime as dt
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

# Local imports – adjust the import path if this script is executed
# from the repo root.
sys.path.append(str(Path(__file__).parent))
from uptrend_analyzer import UptrendAnalyzer
from portfolio_manager import PortfolioManager
from config_manager import ConfigManager
from fundamental_filter import FundamentalFilter
from volume_profile import VolumeProfiler


def download_symbol_data(symbol: str, start: dt.date, end: dt.date) -> pd.DataFrame:
    """Download daily OHLCV data for *symbol* between *start* and *end*.

    Returns a pandas ``DataFrame`` with a DatetimeIndex and the columns
    ``['Open','High','Low','Close','Volume']``.
    """
    ticker = yf.Ticker(symbol if symbol.endswith('.NS') else f"{symbol}.NS")
    df = ticker.history(start=start, end=end, interval="1d", auto_adjust=False)
    if df.empty:
        print(f"[warn] No data returned for {symbol}, skipping...")
        return pd.DataFrame()
    # Ensure required columns exist
    df = df[['Open', 'High', 'Low', 'Close', 'Volume']].copy()
    df.dropna(inplace=True)
    return df


def backtest(symbols, start_date, end_date, config: ConfigManager):
    # Initialise helpers according to the current configuration
    analyzer = UptrendAnalyzer(
        sma_short=config.filters["sma_short"],
        sma_long=config.filters["sma_long"],
        rsi_min=config.filters["rsi_min"],
        rsi_max=config.filters["rsi_max"],
        adx_min=config.filters["adx_min"],
        volume_ratio_min=config.filters["volume_ratio_min"],
        atr_multiplier=config.filters["atr_stop_loss_multiplier"],
        multi_timeframe=config.advanced.get("multi_timeframe_alignment", True),
        use_volume_profile_stop=config.advanced.get("use_volume_profile_stop", True),
    )
    portfolio = PortfolioManager()
    fundamental = FundamentalFilter()
    # Cache for fundamentals – will be refreshed weekly as per the filter
    fund_cache = {}

    symbol_hist = {}
    for sym in symbols:
        df = download_symbol_data(sym, start_date, end_date)
        if not df.empty:
            symbol_hist[sym] = df

    # Build a sorted list of all unique trading days across symbols
    all_days = sorted({d for df in symbol_hist.values() for d in df.index})

    # Main walk‑forward loop
    for current_day in all_days:
        # Prepare a temporary universe limited to data up to *current_day*
        universe = {}
        for sym, df in symbol_hist.items():
            # Select rows up to current_day (inclusive)
            hist_up_to = df[df.index <= current_day]
            if hist_up_to.empty:
                continue
            # Convert to numpy arrays for the analyzer
            universe[sym] = {
                "close": hist_up_to["Close"].values,
                "high": hist_up_to["High"].values,
                "low": hist_up_to["Low"].values,
                "volume": hist_up_to["Volume"].values,
            }
        if not universe:
            continue

        # Run the up‑trend pipeline for *today* (using all data available up‑to today)
        candidates = analyzer.filter_and_rank(universe)

        # === ENTRY LOGIC ===
        for cand in candidates[: config.filters.get("top_n_for_hourly", 50)]:
            sym = cand["symbol"]
            # Fundamental gate – only evaluate once per week to avoid excessive API calls
            if config.advanced.get("fundamental_check_enabled", True):
                week_key = f"{sym}_{current_day.isocalendar().year}_{current_day.isocalendar().week}"
                if week_key not in fund_cache:
                    fund_cache[week_key] = fundamental.check(
                        sym,
                        min_revenue_growth=config.advanced.get("min_revenue_growth", 0.05),
                        max_debt_equity=config.advanced.get("max_debt_equity", 1.5),
                    )
                if not fund_cache[week_key]["fundamental_ok"]:
                    continue

            # Open position if we don't already hold it
            if sym not in portfolio.get_portfolio():
                entry_price = cand["price"]
                qty = 1  # For back‑test we use 1 lot; can be scaled later
                init_sl = cand["stop_loss"]
                portfolio.add_position(sym, entry_price, qty, init_sl)

        # === STOP‑LOSS / TRAILING LOGIC ===
        day_prices = {}
        for sym, df in symbol_hist.items():
            if current_day in df.index:
                row = df.loc[current_day]
                recent = df.loc[:current_day].tail(14)
                atr = analyzer.ti.compute_atr(
                    recent["High"].values,
                    recent["Low"].values,
                    recent["Close"].values,
                )
                day_prices[sym] = {"price": float(row["Close"]), "atr": float(atr)}
        alerts = portfolio.check_trailing_stops(day_prices, config.advanced)
        _ = alerts

    # ==== PERFORMANCE SUMMARY ====
    final_portfolio = portfolio.get_portfolio()
    pnl_total = 0.0
    win = loss = 0
    for sym, pos in final_portfolio.items():
        last_price = symbol_hist[sym]["Close"].iloc[-1]
        pnl = (last_price - pos["entry_price"]) * pos["quantity"]
        pnl_total += pnl
        if pnl >= 0:
            win += 1
        else:
            loss += 1

    trade_count = win + loss
    win_rate = (win / trade_count * 100) if trade_count else 0.0
    cum = []
    cash = 0.0
    for sym, pos in final_portfolio.items():
        cash += (pos["trailing_sl"] - pos["entry_price"]) * pos["quantity"]
        cum.append(cash)
    max_dd = 0.0
    if cum:
        peak = cum[0]
        for v in cum:
            if v > peak:
                peak = v
            dd = peak - v
            if dd > max_dd:
                max_dd = dd

    print("\n=== BACK-TEST SUMMARY ===")
    print(f"Period            : {start_date} -> {end_date}")
    print(f"Symbols examined  : {len(symbols)}")
    print(f"Total trades      : {trade_count}")
    print(f"Win rate          : {win_rate:.2f}%")
    print(f"Total P&L         : Rs{pnl_total:,.2f}")
    print(f"Max draw-down     : Rs{max_dd:,.2f}")


def parse_args():
    parser = argparse.ArgumentParser(description="Back‑test the NSE up‑trend pipeline")
    parser.add_argument(
        "--symbols",
        nargs="+",
        required=False,
        help="List of ticker symbols (without .NS). Use a file if many symbols.",
    )
    parser.add_argument(
        "--symbol_file",
        type=Path,
        required=False,
        help="Path to a plain‑text file with one symbol per line.",
    )
    parser.add_argument("--start", type=lambda s: dt.datetime.strptime(s, "%Y-%m-%d").date(), required=True)
    parser.add_argument("--end", type=lambda s: dt.datetime.strptime(s, "%Y-%m-%d").date(), required=True)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    if not args.symbols and not args.symbol_file:
        sys.exit("Provide either --symbols or --symbol_file")
    symbols = args.symbols or []
    if args.symbol_file:
        symbols.extend([line.strip() for line in args.symbol_file.read_text().splitlines() if line.strip()])
    if not symbols:
        sys.exit("No symbols supplied")

    cfg = ConfigManager()
    backtest(symbols, args.start, args.end, cfg)
