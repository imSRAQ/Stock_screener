# Institutional-Grade NSE Stock Screener & Auto-Trader 🚀

An end-to-end quantitative trading system for Indian Equities (NSE). It automatically scrapes data, filters for institutional uptrends, applies a smart pullback strategy, sizes risk dynamically, takes partial profits, hosts an AI dashboard, and communicates via a 24/7 Telegram bot.

## 🌟 Key Features

1. **6-Layer Quantitative Filter**
   - Trend (SMA 50 > 200)
   - Institutional Volume confirmation
   - Momentum (RSI sweet-spot)
   - Trend Strength (ADX > 25)
   - Multi-timeframe alignment (Weekly trend)
   - Sector momentum boost (Top 3 hot sectors get 1.2x rank boost)

2. **Automated Paper Trading Engine (`paper_trader.py`)**
   - **Auto-Buys** when a stock hits a high Composite Buy Score during a pullback.
   - **Strict 1% Risk Sizing:** Calculates position sizes so you never risk more than 1% of your account per trade.
   - **1.5x R:R Target:** Automatically sells 50% when the target is hit to lock in profit.
   - **Trailing Stops:** Trails the remaining 50% using ATR to capture maximum upside.

3. **Google Gemini AI Summarizer**
   - Processes technicals, fundamentals, and recent news.
   - Writes a human-readable action plan for every top candidate.

4. **Dynamic AI Dashboard (GitHub Pages)**
   - Automatically builds a stunning static HTML dashboard every hour.
   - Sorts candidates by a proprietary "Composite Buy Score".
   - View at: `https://<your-username>.github.io/Stock_screener/stocks_monitoring_and_notifying/docs/`

5. **24/7 Telegram Bot (Render.com + UptimeRobot)**
   - Fully interactive remote control via Telegram.
   - `/vportfolio` to view virtual trades.
   - `/chart SYMBOL` to generate technical charts on the fly.
   - Instantly notifies you of virtual executions (`🎮 VIRTUAL BUY`, `🎯 TARGET HIT`).

6. **Fully Serverless (GitHub Actions)**
   - No local server required.
   - Scheduled hourly scans (9 AM - 4 PM IST) and full daily scans (8 AM IST).
   - Graceful failover to `yfinance` if NSE blocks cloud IPs.

---

## 🏗️ Architecture

- `scheduler.py`: The brain that orchestrates the hourly/daily scans.
- `uptrend_analyzer.py` & `sector_analysis.py`: The core quant filters.
- `paper_trader.py`: The virtual algorithmic trading execution engine.
- `dashboard_generator.py`: HTML generator for the GitHub Pages frontend.
- `bot_worker.py`: Standalone Telegram listener hosted on Render.com.

---

## 🚀 Setup Instructions

### 1. Local Setup
```bash
git clone https://github.com/imSRAQ/Stock_screener.git
cd Stock_screener
python -m venv .venv
.venv\Scripts\activate  # Windows
pip install -r requirements.txt
```

### 2. Configuration (`config.json`)
Create `stocks_monitoring_and_notifying/config.json` (This file is git-ignored for safety):
```json
{
  "telegram_bot_token": "YOUR_TOKEN",
  "telegram_chat_id": "YOUR_CHAT_ID",
  "gemini_api_key": "YOUR_GEMINI_KEY",
  "schedule": {
    "hourly_enabled": true
  },
  "filters": {
    "sma_short": 50,
    "sma_long": 200,
    "rsi_min": 40,
    "rsi_max": 65,
    "adx_min": 25,
    "atr_stop_loss_multiplier": 1.5
  }
}
```

### 3. Telegram Bot 24/7 Hosting (Render.com)
1. Create a **Free Web Service** on Render.com pointing to this repo.
2. Build command: `pip install -r requirements.txt`
3. Start command: `python stocks_monitoring_and_notifying/bot_worker.py`
4. Add Environment Variables: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `GEMINI_API_KEY`, `GITHUB_TOKEN` (Personal Access Token).
5. Set up a free ping on UptimeRobot for the Render URL to prevent sleeping.

### 4. GitHub Actions (Cloud Automation)
Add `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, and `GEMINI_API_KEY` to your repository's **Secrets** (Settings > Secrets and variables > Actions). The `.github/workflows/hourly_scan.yml` will handle the rest!

---

## 📚 Detailed Documentation
For a deep dive into the math, logic, and inner workings of every module, please read:
[`stocks_monitoring_and_notifying/walkthrough.md`](stocks_monitoring_and_notifying/walkthrough.md)
