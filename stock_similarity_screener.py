#!/usr/bin/env python3
"""
stock_similarity_screener.py

Fetches daily OHLC data for a reference NSE stock and a candidate universe,
then ranks candidates by how similar their recent price/candle SHAPE is to
the reference stock's pattern, filtering to uptrend-only matches.

*** MODIFIED: now supports TWO data backends via --source, not just yfinance ***
  --source yfinance  (default, original behavior) - unofficial Yahoo Finance
  --source nse       (NEW) - NSE's own official daily Bhavcopy archive

REQUIREMENTS (install once):
    pip install yfinance pandas numpy requests
    (requests is needed for the new --source nse option; yfinance only
    needed if you plan to use --source yfinance)

USAGE:
    python stock_similarity_screener.py --reference RELIANCE --lookback 60

    # *** NEW: use NSE's own official data instead of Yahoo Finance ***
    python stock_similarity_screener.py --reference RELIANCE --source nse

    # Use your own candidate list instead of the built-in Nifty 500 snapshot:
    python stock_similarity_screener.py --reference RELIANCE --tickers-file my_list.csv

    # Tune the uptrend strictness and output location:
    python stock_similarity_screener.py --reference TCS --lookback 30 --min-slope 0.001 --out results.json

    # *** NEW: include market capitalization for the reference + shortlisted matches ***
    python stock_similarity_screener.py --reference RELIANCE --with-market-cap

OUTPUT:
    Writes a JSON file (default: screener_output.json) containing the ranked
    results plus the reference stock's own OHLC series, in the exact shape
    the companion dashboard artifact expects. Open the dashboard and load
    this file to view results visually.

IMPORTANT CAVEATS (read before trusting the output):
  - yfinance is an unofficial wrapper around Yahoo Finance endpoints. It can
    break, rate-limit, or return incomplete data without warning. Always
    sanity-check a few tickers manually if results look odd.
  - *** NEW: --source nse caveat *** NSE's archive is the official primary
    source, but (a) its server can block scripted requests without
    browser-like headers [handled in data_sources.py, but NSE can change
    this anytime], and (b) it downloads one file per trading day covering
    ALL stocks, so a large --lookback window means more files to fetch on
    first run (subsequent runs reuse a local cache, see data_sources.py).
  - The bundled Nifty 500 ticker list (nifty500_tickers.py) is a
    best-effort snapshot and may contain stale/incorrect symbols. For
    serious use, replace it with a verified current list from
    niftyindices.com.
  - DTW shape-similarity is a STARTING FILTER for further analysis, not a
    trading signal. It tells you "this chart looks like that chart" --
    it says nothing about fundamentals, volume quality, news, or whether
    the pattern will continue. Always do your own due diligence.
  - *** NEW: --with-market-cap caveat *** Market cap is fetched as a
    CURRENT snapshot (today's value), not historical, and is only fetched
    for the reference + shortlisted matches (not the full scanned
    universe) to keep the run fast. Figures come from yfinance's `.info`
    or NSE's quote API depending on --source, and either can occasionally
    be stale, missing, or briefly out of sync with the live exchange.
"""

import argparse
import json
import sys
import time
from datetime import datetime

import numpy as np
import pandas as pd

from similarity_engine import rank_candidates
from nifty500_tickers import get_tickers
# *** pluggable multi-source fetchers (yfinance + NSE Bhavcopy) ***
# *** NEW: fetch_market_caps for the --with-market-cap option ***
# from data_sources import fetch_reference_ohlc, fetch_universe_ohlc, fetch_fundamentals,fetch_market_caps
from data_sources import fetch_reference_ohlc, fetch_universe_ohlc, fetch_fundamentals


def load_candidate_tickers(args) -> list:
    if args.tickers_file:
        df = pd.read_csv(args.tickers_file)
        col = df.columns[0]
        symbols = df[col].astype(str).str.strip().tolist()
        return [s if s.endswith(".NS") else f"{s}.NS" for s in symbols]
    return get_tickers()


def main():
    parser = argparse.ArgumentParser(description="Candlestick shape-similarity stock screener (NSE)")
    parser.add_argument("--reference", default=None, help="Optional reference NSE symbol, e.g. RELIANCE (no .NS needed). If omitted, finds all uptrending stocks.")
    # *** NEW: --source flag to choose the data backend ***
    parser.add_argument("--source", default="yfinance", choices=["yfinance", "nse"],
                         help="Data backend: 'yfinance' (default, unofficial Yahoo wrapper) "
                              "or 'nse' (NSE's own official Bhavcopy archive)")
    parser.add_argument("--lookback", type=int, default=60, help="Lookback window in trading days (default: 60)")
    parser.add_argument("--min-slope", type=float, default=0.0,
                         help="Minimum normalized daily trend slope to count as uptrend (default: 0.0, i.e. any positive slope)")
    parser.add_argument("--tickers-file", default=None,
                         help="Optional CSV with one ticker per row (first column), to override the built-in Nifty 500 snapshot")
    parser.add_argument("--top-n", type=int, default=50, help="How many top matches to keep (default: 30)")
    parser.add_argument("--out", default="screener_output.json", help="Output JSON path")
    parser.add_argument("--delay", type=float, default=0.3,
                         help="Seconds to sleep between requests to avoid rate-limiting (default: 0.3)")
    # *** NEW: opt-in fundamentals enrichment (adds one extra request per
    # shortlisted ticker, so it's off by default to keep runs fast) ***
    parser.add_argument("--with-fundamentals", "--with-market-cap", dest="with_fundamentals", action="store_true",
                         help="Fetch fundamental metrics (P/E, ROE, D/E, etc.) for the top matches. Off by default.")
    args = parser.parse_args()

    ref_ticker = args.reference if (args.reference and args.reference.endswith(".NS")) else (f"{args.reference}.NS" if args.reference else None)

    ref_close, ref_dates = None, []
    if ref_ticker:
        print(f"Fetching reference stock: {ref_ticker} ({args.lookback} days) via '{args.source}'...")
        ref_close, ref_dates = fetch_reference_ohlc(ref_ticker, args.lookback, source=args.source)
        if ref_close is None:
            print(f"ERROR: could not fetch data for reference '{ref_ticker}' using source '{args.source}'. "
                  f"Check the symbol, or try --source yfinance / --source nse instead.", file=sys.stderr)
            sys.exit(1)
        print(f"  Got {len(ref_close)} days of data.")
    else:
        print("No reference stock provided. Finding all uptrending stocks...")

    candidate_tickers = load_candidate_tickers(args)
    # Don't compare the reference against itself
    candidate_tickers = [t for t in candidate_tickers if t != ref_ticker]
    print(f"Scanning {len(candidate_tickers)} candidate stocks via '{args.source}'. "
          f"This may take a while...")

    # *** MODIFIED: now routes through fetch_universe_ohlc(..., source=args.source)
    # instead of a hand-rolled per-ticker loop. Both backends return the same
    # (dict, failed_list) shape so the rest of this function is unchanged. ***
    candidates_data, failed = fetch_universe_ohlc(
        candidate_tickers, args.lookback, source=args.source, delay=args.delay
    )

    print(f"Successfully fetched {len(candidates_data)} / {len(candidate_tickers)} candidates "
          f"({len(failed)} failed/skipped).")

    print("Ranking candidates by shape similarity...")
    ranked = rank_candidates(ref_close, candidates_data, min_slope=args.min_slope, uptrend_only=True)

    if ranked.empty:
        print("No uptrend matches found. Try lowering --min-slope or increasing --lookback.")
    else:
        ranked = ranked.head(args.top_n)
        print(f"\nTop {len(ranked)} matches:")
        print(ranked.to_string(index=False))

    # *** NEW: opt-in fundamentals enrichment ***
    # Only fetched for the reference + shortlisted tickers
    fundamentals = {}
    if args.with_fundamentals:
        tickers_needing_fund = [ref_ticker] + (ranked["ticker"].tolist() if not ranked.empty else [])
        print(f"\nFetching fundamentals for {len(tickers_needing_fund)} tickers...")
        fundamentals = fetch_fundamentals(tickers_needing_fund, source=args.source, delay=args.delay)

        # Add fundamental metrics to each ranked stock
        if not ranked.empty:
            ranked["market_cap"]     = ranked["ticker"].apply(lambda x: fundamentals.get(x, {}).get("market_cap"))
            ranked["current_price"]  = ranked["ticker"].apply(lambda x: fundamentals.get(x, {}).get("current_price"))
            ranked["roe"]            = ranked["ticker"].apply(lambda x: fundamentals.get(x, {}).get("roe"))
            ranked["quick_ratio"]    = ranked["ticker"].apply(lambda x: fundamentals.get(x, {}).get("quick_ratio"))
            # NEW fields
            ranked["pe_ratio"]       = ranked["ticker"].apply(lambda x: fundamentals.get(x, {}).get("pe_ratio"))
            ranked["eps"]            = ranked["ticker"].apply(lambda x: fundamentals.get(x, {}).get("eps"))
            ranked["pb_ratio"]       = ranked["ticker"].apply(lambda x: fundamentals.get(x, {}).get("pb_ratio"))
            ranked["debt_to_equity"] = ranked["ticker"].apply(lambda x: fundamentals.get(x, {}).get("debt_to_equity"))
            ranked["profit_margin"]  = ranked["ticker"].apply(lambda x: fundamentals.get(x, {}).get("profit_margin"))
            ranked["revenue_growth"] = ranked["ticker"].apply(lambda x: fundamentals.get(x, {}).get("revenue_growth"))
            ranked["free_cash_flow"] = ranked["ticker"].apply(lambda x: fundamentals.get(x, {}).get("free_cash_flow"))
            ranked["dividend_yield"] = ranked["ticker"].apply(lambda x: fundamentals.get(x, {}).get("dividend_yield"))
            ranked["fund_score"]     = ranked["ticker"].apply(lambda x: fundamentals.get(x, {}).get("fund_score"))

        missing = [t for t in tickers_needing_fund if t not in fundamentals]
        if missing:
            print(f"  [note] fundamentals not found for {len(missing)} ticker(s): {', '.join(missing)}")

    # Build output payload for the dashboard
    output = {
        "generated_at": datetime.now().isoformat(),
        "reference": {
            "ticker": ref_ticker,
            "lookback_days": args.lookback,
            "close": ref_close.round(2).tolist(),
            "dates": ref_dates,

            # Fundamental data
            "market_cap":    fundamentals.get(ref_ticker, {}).get("market_cap"),
            "current_price": fundamentals.get(ref_ticker, {}).get("current_price"),
            "roe":           fundamentals.get(ref_ticker, {}).get("roe"),
            "quick_ratio":   fundamentals.get(ref_ticker, {}).get("quick_ratio"),
            "pe_ratio":      fundamentals.get(ref_ticker, {}).get("pe_ratio"),
            "fund_score":    fundamentals.get(ref_ticker, {}).get("fund_score"),
        },
        "params": {
            "min_slope": args.min_slope,
            "top_n": args.top_n,
            "source": args.source,
        },
        "results": ranked.to_dict(orient="records") if not ranked.empty else [],
        "candidates_close": {
            t: candidates_data[t].round(2).tolist()
            for t in ranked["ticker"].tolist()
        } if not ranked.empty else {},
        # *** NEW: per-candidate market caps in rupees. A ticker missing
        # from this dict simply has no cap data available; the dashboard
        # shows "n/a" for those rather than treating it as an error. ***
        # "market_caps": {t: market_caps[t] for t in market_caps if t != ref_ticker},
        "fundamentals": {
            t: fundamentals[t]
            for t in fundamentals
            if t != ref_ticker
        },
        "failed_count": len(failed),
        "scanned_count": len(candidate_tickers),
    }

    with open(args.out, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nResults written to {args.out}")
    print("Load this file into the companion dashboard artifact to view it visually.")


if __name__ == "__main__":
    main()
