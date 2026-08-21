# NSE Candlestick Shape Screener

Finds Indian (NSE) stocks whose recent daily price/candle **shape** resembles
a reference stock's uptrend pattern — for shortlisting candidates, not for
trading signals.

## What's included

| File | Purpose |
|---|---|
| `screener/stock_similarity_screener.py` | Main script — run this on your own machine |
| `screener/nse_screener_gui.py` | Desktop GUI for the screener (run this instead of the CLI script if you prefer a graphical interface) |
| `screener/data_sources.py` | Pluggable data backends (yfinance + NSE Bhavcopy) and market-cap lookup |
| `screener/similarity_engine.py` | Core matching logic (DTW shape comparison) |
| `screener/nifty500_tickers.py` | Default candidate universe (see caveat below) |
| `templates/dashboard.html` | Visual screener — open in any browser, load the JSON output |
| `templates/interactive_dashboard.html` | Advanced interactive dashboard |
| `output/sample_output.json` | Synthetic example (includes market cap) so the dashboard works before you run anything |

## Setup (one time)

```bash
pip install -r requirements.txt
```

No API key needed for either backend below.

## Choosing a data source — ***NEW: now two options***

| | `--source yfinance` (default) | `--source nse` (new) |
|---|---|---|
| What it is | Unofficial Yahoo Finance wrapper | NSE's own official daily Bhavcopy archive |
| Access pattern | One request per ticker | One file per trading day, covers all stocks at once |
| Best for | Quick runs, smaller watchlists | Large universes (e.g. full Nifty 500), wanting the primary official source |
| Known risk | Can silently rate-limit or return gaps at scale | Server can reject scripted requests without browser-like headers (handled, but NSE could change this) |

Both produce the exact same output format, so you can switch freely:

```bash
python -m screener.stock_similarity_screener --reference RELIANCE --source yfinance
python -m screener.stock_similarity_screener --reference RELIANCE --source nse
```

I also looked at **Alpha Vantage** as a third option but ruled it out for this
use case — its free tier caps out at 25 requests/day, which isn't enough to
scan a broad universe like Nifty 500 even once.

The `--source nse` backend caches each day's downloaded Bhavcopy file in
`~/.nse_screener_cache/` so re-running the script (e.g. daily) doesn't
re-download historical days you've already fetched — only the newest
trading day needs fetching each time.

## Running it

**Option 1: Using the Desktop GUI (Recommended)**
```bash
python -m screener.nse_screener_gui
```
This opens a graphical interface where you can set your reference stock, lookback window, data source, and other parameters, and then view the results directly.

**Option 2: Using the Command Line**
```bash
# Basic: find stocks shaped like RELIANCE's last 60 days (uses yfinance by default)
python -m screener.stock_similarity_screener --reference RELIANCE

# Same, but using NSE's own official data instead of Yahoo Finance
python -m screener.stock_similarity_screener --reference RELIANCE --source nse

# Custom lookback window and stricter uptrend requirement
python -m screener.stock_similarity_screener --reference TCS --lookback 30 --min-slope 0.0015

# Use your own watchlist instead of the bundled Nifty 500 snapshot
python -m screener.stock_similarity_screener --reference INFY --tickers-file data/my_watchlist.csv

# Also fetch market capitalization for the reference + shortlisted matches
python -m screener.stock_similarity_screener --reference RELIANCE --with-market-cap
```

This writes `output/screener_output.json`. Open `templates/dashboard.html` in your browser
and click **Load JSON output** to view the ranked results visually — each
row shows a mini overlay of the candidate's shape against your reference
pattern, plus market cap if you used `--with-market-cap`.

Re-run the script whenever you want fresh results (daily, weekly — your
choice). For true daily automation, schedule it with cron / Task Scheduler
to run after market close and just open the dashboard each morning.

## Market capitalization (opt-in via `--with-market-cap`)

- Fetched as a **current snapshot**, separately from the historical OHLC
  data, and only for the reference stock + the shortlisted matches (not
  the full scanned universe) — so it adds only a handful of extra requests,
  not hundreds.
- Sourced from yfinance's `.info` dict, or NSE's quote-equity API when
  `--source nse` is active. If yfinance comes up empty for a ticker, the
  script automatically tries the NSE source as a fallback.
- Displayed in the dashboard in Indian crore/lakh notation (e.g. "₹19.80L Cr"
  for a company worth roughly ₹19.8 lakh crore), since that's the
  conventional way this figure is read for NSE stocks.
- Off by default because it's an extra round of network calls; turn it on
  with `--with-market-cap` when you want it. Tickers where neither source
  has a figure show as "n/a" in the dashboard rather than erroring out.

## How "similarity" is calculated

1. Each stock's closing-price series is **z-score normalized** (so price
   level doesn't matter — a ₹50 stock and a ₹5,000 stock with the same %
   movement pattern score identically).
2. **Dynamic Time Warping (DTW)** measures shape distance between the
   normalized reference and each candidate, tolerating small time-shifts.
3. Distance is converted to a **0–100 similarity score**.
4. A **linear-regression trend slope** filters out anything not actually
   trending upward — by default any positive slope passes; raise
   `--min-slope` to demand a steeper trend.

## Things you should know before relying on this

- **This is shape-matching, not prediction.** A high similarity score means
  "this chart's recent path looks like that chart's recent path." It says
  nothing about why, whether it'll continue, volume quality, fundamentals,
  or news risk. Treat the output as a first-pass filter for your own
  further research — not a buy signal.
- **The bundled Nifty 500 ticker list is a best-effort reconstruction**, not
  a verified live feed from NSE. It may contain stale, delisted, or
  misspelled symbols. For serious use, download a current list from
  [niftyindices.com](https://www.niftyindices.com) and pass it via
  `--tickers-file`.
- **Neither data backend is bulletproof.** yfinance is an unofficial Yahoo
  wrapper that can rate-limit or silently return incomplete data. NSE's own
  archive is official but actively guards against scripted access and has
  changed its file format/URL before (most recently mid-2024) — if NSE
  changes it again, `--source nse` will need a corresponding update in
  `data_sources.py`. Spot-check a few tickers manually (e.g. on NSE's own
  site) if a result looks surprising, regardless of which source you use.
- **Market cap figures can lag the live exchange** by however long the
  underlying API takes to refresh its snapshot — treat it as
  "approximately current," not tick-by-tick accurate.
- **Nothing here runs automatically in the background.** Both pieces
  (script and dashboard) only act when you run/open them — there's no
  always-on "agent" watching the market for you. If you want that, you'd
  need to schedule the script on a server or machine that stays on.
