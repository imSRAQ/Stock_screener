# 📈 Multi-Timeframe RSI Reversal Screener

> **Strategy**: RSI Reversal MWD (Monthly 60+ · Weekly 60+ · Daily 35–45)  
> **Platform**: NSE | **Deployment**: Render.com + GitHub Pages  
> **Bot**: Shared Telegram bot — reversal commands use `/rev` prefix

---

## Table of Contents
- [What This Does](#what-this-does)
- [Strategy Rules](#strategy-rules)
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Setup Guide](#setup-guide)
- [Telegram Commands](#telegram-commands)
- [Dashboard](#dashboard)
- [Paper Trader](#paper-trader)
- [Blackout Calendar](#blackout-calendar)
- [Position Sizing](#position-sizing)
- [Deployment](#deployment)

---

## What This Does

This system scans the entire NSE universe every weekday at **19:00 IST** (after market close) for stocks that satisfy a 3-timeframe RSI setup — Monthly strength, Weekly momentum, and Daily pullback — combined with a bullish reversal candlestick pattern.

**Key outputs:**
1. **Telegram alert** with confirmed entries and watchlist setups
2. **GitHub Pages dashboard** with per-stock charts, entry/SL/target levels, and a live position sizing calculator
3. **Virtual paper trading** — automatically enters confirmed breakouts and manages exits

---

## Strategy Rules

### Rule 1 — Multi-Timeframe RSI Filter
| Timeframe | RSI(14) Condition | Default |
|---|---|---|
| Monthly | ≥ threshold (strong uptrend) | 60 |
| Weekly  | ≥ threshold (momentum)       | 60 |
| Daily   | In pullback band (reversal zone) | 35–45 |

### Rule 2 — Signal Candle Detection
Any of the following detected within `lookback_days` (default 400) of the scan:

| Pattern | What it signals |
|---|---|
| Morning Star | 3-bar reversal — strongest |
| Bullish Engulfing | Full reversal |
| Piercing Pattern | Partial recovery above midpoint |
| Bullish Harami | Inside reversal |
| Hammer | Long lower shadow — buying pressure |
| Doji | Indecision at support |

Each pattern returns a human-readable explanation shown on the dashboard card.

### Rule 3 — Entry Tag
| Tag | Condition |
|---|---|
| `confirmed_entry` | Most recent close > signal candle high (breakout confirmed) |
| `early_entry` | Signal candle found, price not yet broken above candle high |

> **Paper trader only executes `confirmed_entry` — never `early_entry`.**

### Rule 4 — Stop Loss
Configured via `sl_mode` in `config.json`:
- `signal_candle_low` (default) — SL = low of the signal candle
- `swing_low` — SL = lowest low of the last N bars before signal

### Rule 5 — Targets
- **1R Target** — `entry + reward_multiple × risk_per_share` (partial exit: 50% of shares)
- **RSI-60 Target** — binary search projection of the price where daily RSI(14) returns to 60 (full exit)

---

## Architecture

```
stocks_monitoring_and_notifying/
├── bot_worker.py          ← Uptrend scan (08:00 IST) + Telegram polling loop
│                             + Reversal scan (19:00 IST) via Option A
│                             + Reversal /rev* commands via rev_handlers import
└── telegram_notifier.py  ← Registers all handlers (uptrend + reversal)

Multi Timeframe RSI Reversal/
├── config_manager.py       ← Reversal-specific config + env var overrides
├── data_fetcher.py         ← Bhavcopy primary → yfinance fallback + D/W/M resampling
├── reversal_analyzer.py    ← Rules 1–5 (RSI + candle + entry/SL/target)
├── event_blackout_filter.py← Blackout calendar gate
├── position_sizer.py       ← Pure sizing math (used by trader + dashboard JS)
├── paper_trader.py         ← Virtual paper trader (confirmed_entry only)
├── ai_summarizer.py        ← Gemini/Groq/OpenAI/Anthropic cascade
├── dashboard_generator.py  ← Static HTML: 4 tabs + charts + sizing panel
├── rev_handlers.py         ← /rev* Telegram command handlers
├── scheduler.py            ← Full pipeline orchestrator
└── bot_worker.py           ← APScheduler only (fallback if running standalone)
```

**Bot integration**: The existing `telegram_notifier.py` polling loop imports `rev_handlers` and registers `/rev*` commands alongside the uptrend commands. No second bot instance — one polling loop, two strategy namespaces.

---

## Project Structure

```
Multi Timeframe RSI Reversal/
├── config.json.example         ← Copy to config.json and fill in your keys
├── config.json                 ← Gitignored — real secrets
├── blackout_calendar.json      ← Auto-created on first /revblackout use
├── virtual_portfolio.json      ← Auto-created on first scan (reversal paper trader)
├── universe_snapshot.json      ← Auto-created after each scan
└── docs/
    ├── index.html              ← GitHub Pages dashboard (main)
    └── scan/
        └── YYYY-MM-DD.html     ← Archived per-day scan pages
```

---

## Setup Guide

### 1. Install Dependencies

This project shares the `requirements.txt` with the existing `stocks_monitoring_and_notifying` system. Ensure these are present:

```
python-telegram-bot>=20.0
apscheduler>=3.10
pytz
requests
numpy
yfinance
matplotlib
google-generativeai
openai
anthropic
holidays
```

### 2. Create `config.json`

```bash
cd "Multi Timeframe RSI Reversal"
cp config.json.example config.json
```

Edit `config.json`:
```json
{
  "telegram_bot_token": "<same token as existing system>",
  "telegram_chat_id": "<your chat ID>",
  "gemini_api_key": "<your key>",
  "schedule": {
    "full_scan_time_ist": "19:00"
  },
  "filters": {
    "rsi_monthly_min": 60,
    "rsi_weekly_min": 60,
    "rsi_daily_band": [35, 45]
  },
  "risk": {
    "default_capital": 500000,
    "risk_pct_default": 1.0
  }
}
```

> ℹ️ On Render.com, set secrets as **environment variables** instead — `config.json` is only needed for local runs.

### 3. Test the Scan Locally

```bash
cd "Multi Timeframe RSI Reversal"
python scheduler.py --full
```

Expected output:
```
[info] Universe: 2150 symbols with D/W/M data.
[info] Reversal filter: 12 candidates found.
[info] Dashboard written → .../docs/index.html
[info] Full scan complete: 5 confirmed, 7 watchlist.
```

### 4. Test the Position Sizer

```bash
python position_sizer.py
# Enter: entry=2500, sl=2450, capital=500000, risk=1, rr=1.5
```

### 5. Test Telegram Commands

Start the existing `stocks_monitoring_and_notifying/bot_worker.py` — reversal commands are now registered:
```
/revhelp      → shows all reversal commands
/revstatus    → shows "No scan run yet" (expected on first run)
/revportfolio → shows empty virtual portfolio
```

---

## Telegram Commands

| Command | Description |
|---|---|
| **Scanning** | |
| `/revscan` | Trigger full reversal scan on-demand |
| `/revstatus` | Last scan summary + portfolio snapshot |
| `/revchart RELIANCE` | Candlestick + RSI chart with signal candle overlay |
| **Position Sizing** | |
| `/revsize RELIANCE 500000 1` | Calc position size (symbol, capital, risk%) |
| **Virtual Portfolio** | |
| `/revportfolio` | Open positions + unrealised P&L |
| `/revhistory` | Last 10 closed virtual trades |
| `/revreset` | Reset virtual balance to `default_capital` |
| `/revtoggle on\|off` | Enable/disable auto paper trading |
| **Blackout Calendar** | |
| `/revblackout LIST` | Show all blackout dates |
| `/revblackout ADD RELIANCE 2026-10-15` | Add blackout for one symbol |
| `/revblackout ADD GLOBAL 2026-11-07` | Add global blackout (all symbols) |
| `/revblackout REMOVE RELIANCE 2026-10-15` | Remove blackout |
| **Help** | |
| `/revhelp` | Show all reversal commands |

> All commands use `/rev` prefix. **Uptrend commands (`/scan`, `/vportfolio`, etc.) are completely unchanged.**

---

## Dashboard

**URL**: `https://<your-github-username>.github.io/<repo>/Multi%20Timeframe%20RSI%20Reversal/docs/`

**4 Tabs:**

| Tab | Contents |
|---|---|
| ✅ Confirmed | `confirmed_entry` stocks (breakout confirmed) |
| 👀 Watchlist | `early_entry` stocks (signal found, awaiting breakout) |
| 🚫 Blacked Out | Stocks excluded from alerts due to upcoming events |
| 💼 Portfolio | Virtual positions, equity curve, closed trade history |

**Per-stock card (expandable):**
- RSI badges (M/W/D)
- Signal candle pattern + date + plain-English reason
- Entry · SL · 1R Target · RSI-60 Target · Risk/Share levels
- **Live position sizing calculator** (editable capital/risk fields, instant recalc)

---

## Paper Trader

| Feature | Detail |
|---|---|
| **Trigger** | Only `confirmed_entry` (Rule 3 breakout confirmed at close) |
| **`early_entry` stocks** | Never auto-executed — watchlist only |
| **Partial exit** | 50% of shares sold at 1R target; SL moved to entry |
| **Full exit** | RSI-60 target price hit OR trailing SL hit |
| **Trailing SL** | `min(last N lows)` updated every `trailing_bar_count` bars (if enabled) |
| **Sizing** | Delegates to `position_sizer.compute()` — same formula as dashboard |
| **State file** | `virtual_portfolio.json` (separate from uptrend's) |
| **Max positions** | Configurable via `risk.max_positions` |

---

## Blackout Calendar

Prevents alerts and virtual trades on event dates (e.g. earnings, result day, ex-dividend).

**Format** (`blackout_calendar.json`):
```json
{
    "RELIANCE": ["2026-10-15", "2026-01-20"],
    "GLOBAL":   ["2026-11-07"]
}
```

`GLOBAL` blocks all symbols on that date (e.g. RBI policy day, Union Budget).

---

## Position Sizing

The sizing formula is a single source of truth in `position_sizer.py`:

```
risk_per_share = entry - sl
risk_amount    = capital × (risk_pct / 100)
qty            = floor(risk_amount / risk_per_share)
capital_req    = qty × entry
target_1r      = entry + reward_multiple × risk_per_share
```

Used by: `paper_trader.py` (Python) and the dashboard calculator (JavaScript mirror).

---

## Deployment

### Render.com (existing service — Option A)

The reversal scan is added as a second APScheduler job inside your existing `stocks_monitoring_and_notifying/bot_worker.py`. No new Render service needed.

**Environment variables** (same service, same dashboard):
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `GEMINI_API_KEY`
- `GITHUB_TOKEN`

### GitHub Pages (Dashboard)

1. Go to your repo → **Settings → Pages**
2. Source: **Deploy from a branch** → `main` → `/` (root)
3. Dashboard URL: `https://<username>.github.io/<repo>/Multi%20Timeframe%20RSI%20Reversal/docs/`

---

## Notes

- **`nse_symbols.txt`** — shared from `../stocks_monitoring_and_notifying/nse_symbols.txt`. Add/remove symbols there; both strategies pick up changes automatically.
- **RSI-60 target** is computed via binary search (50 iterations) — precision < 0.001₹. Falls back to 2R if the calculation produces an unrealistic result.
- **AI summaries** are generated in batches of 5 to stay within Gemini free tier (15 stocks/day × 3 API calls). Falls back to Groq → OpenAI → Anthropic if Gemini fails.
- **Trailing SL** is disabled by default. Enable it via `filters.trailing_enabled: true` in `config.json`.

---

*Built as part of the `imSRAQ/Stock_screener` project.*
