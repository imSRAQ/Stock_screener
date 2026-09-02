# stocks_monitoring_and_notifying 🧠

This directory contains the entire Python backend and algorithmic logic for the Stock Screener and Auto-Trader system.

## 📁 Core Modules

| Module | Purpose |
|---|---|
| `scheduler.py` | The main orchestrator. Handles `--full`, `--hourly`, and `--weekly` scans. Calls all other modules in order. |
| `data_fetcher.py` | Connects to NSE to fetch daily OHLCV data. Automatically falls back to `yfinance` if cloud IPs are blocked. |
| `uptrend_analyzer.py` | The math engine. Runs the 6-layer technical filter (SMA, RSI, ADX, Slope) to find institutional pullbacks. |
| `sector_analysis.py` | Identifies the top 3 strongest sectors and applies a momentum multiplier to stocks in those sectors. |
| `ai_summarizer.py` | Connects to Google Gemini API to write a structured, human-readable summary of the trade setup. |
| `dashboard_generator.py` | Generates the static HTML dashboard (`index.html`) using raw JSON snapshots from the scans. |
| `paper_trader.py` | The Algorithmic Auto-Trader. Manages 1% risk-sizing, partial target exits, and trailing stops. |
| `telegram_notifier.py` | Formats scan results and virtual trade executions into beautiful Telegram messages. |
| `bot_worker.py` | A lightweight keep-alive web server and Telegram listener. Deploys to Render.com for 24/7 commands. |
| `config_manager.py` | Loads `config.json` safely. Never commit `config.json`. |

## 💾 State & Databases (Auto-Generated)

These JSON files act as the system's database. They are updated dynamically by GitHub Actions:

- `virtual_portfolio.json`: Tracks the virtual cash balance and active paper trades.
- `portfolio.json`: Tracks manual real-world trades (not touched by Auto-Trader).
- `fundamental_cache.json`: Caches Yahoo Finance fundamental data for 7 days to speed up scans.
- `universe_snapshot.json` / `hourly_snapshot.json`: Raw data dumps used by the HTML Dashboard.

## 🛠️ Local Development

To run the pipeline locally (ensure you are in the project root `Stock_screener/`):

```bash
# Run a full daily scan
python stocks_monitoring_and_notifying/scheduler.py --full

# Run the hourly intraday refresh
python stocks_monitoring_and_notifying/scheduler.py --hourly
```

## 🔐 Security Warning
Never commit `config.json` to this directory. Always rely on GitHub Secrets (`TELEGRAM_BOT_TOKEN`, `GEMINI_API_KEY`) when running in the cloud.
