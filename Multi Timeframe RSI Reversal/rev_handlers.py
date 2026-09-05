"""
rev_handlers.py
---------------
Telegram command handlers for the Multi-Timeframe RSI Reversal strategy.

All commands use the /rev prefix to avoid colliding with the uptrend system:
  /revhelp, /revstatus, /revscan, /revchart, /revsize,
  /revblackout, /revportfolio, /revhistory, /revreset, /revtoggle

This module is imported by stocks_monitoring_and_notifying/bot_worker.py
and its handlers are registered on the SHARED Telegram Application instance.
It does NOT run a polling loop — the existing bot_worker owns the single loop.

It also exposes send_alert() for use by the reversal bot_worker.py to send
scheduled scan notifications without a polling loop.

Strategy: Multi-Timeframe RSI Reversal
"""

import os
import sys
import asyncio
import io
from typing import Optional

from telegram import Update, InputFile
from telegram.ext import ContextTypes

# ── Ensure this module's folder is on sys.path ─────────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from config_manager        import ConfigManager
from paper_trader          import PaperTrader
from event_blackout_filter import EventBlackoutFilter
from position_sizer        import compute as _size_compute


# ── Singleton objects (lazy-loaded, shared across all handler calls) ──────────
_config:   Optional[ConfigManager]       = None
_trader:   Optional[PaperTrader]         = None
_blackout: Optional[EventBlackoutFilter] = None


def _get_config() -> ConfigManager:
    global _config
    if _config is None:
        _config = ConfigManager()
    return _config

def _get_trader() -> PaperTrader:
    global _trader
    if _trader is None:
        _trader = PaperTrader(config=_get_config())
    return _trader

def _get_blackout() -> EventBlackoutFilter:
    global _blackout
    if _blackout is None:
        _blackout = EventBlackoutFilter()
    return _blackout


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _reply(update: Update, text: str):
    """Send an HTML-formatted reply, splitting if needed."""
    MAX = 4096
    while text:
        if len(text) <= MAX:
            await update.message.reply_text(text, parse_mode="HTML")
            break
        split_at = text.rfind("\n", 0, MAX)
        if split_at == -1:
            split_at = MAX
        await update.message.reply_text(text[:split_at], parse_mode="HTML")
        text = text[split_at:].lstrip("\n")


def send_alert(token: str, chat_id: str, text: str):
    """Fire-and-forget Telegram send (no polling loop required).

    Used by reversal bot_worker.py to send scheduled scan notifications.
    """
    import telegram
    async def _send(msg_text: str):
        bot    = telegram.Bot(token=token)
        MAX    = 4096
        chunks = []
        while msg_text:
            if len(msg_text) <= MAX:
                chunks.append(msg_text)
                break
            split_at = msg_text.rfind("\n", 0, MAX)
            if split_at == -1:
                split_at = MAX
            chunks.append(msg_text[:split_at])
            msg_text = msg_text[split_at:].lstrip("\n")
        for chunk in chunks:
            try:
                await bot.send_message(chat_id=chat_id, text=chunk, parse_mode="HTML")
            except Exception as exc:
                print(f"[warn] send_alert failed: {exc}")

    try:
        asyncio.run(_send(text))
    except RuntimeError:
        # Already inside an event loop (e.g. during bot_worker polling)
        loop = asyncio.get_event_loop()
        loop.create_task(_send(text))


# ══════════════════════════════════════════════════════════════════════════════
# Command handlers  (all async, match python-telegram-bot v20+ signature)
# ══════════════════════════════════════════════════════════════════════════════

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /revhelp — show all reversal strategy commands."""
    text = (
        "📈 <b>RSI Reversal Strategy — Commands</b>\n\n"
        "<b>📊 Scanning</b>\n"
        "/revscan — Trigger a full reversal scan now\n"
        "/revstatus — Last scan summary &amp; virtual portfolio snapshot\n"
        "/revchart SYMBOL — Candlestick + RSI chart with signal candle overlay\n\n"
        "<b>📐 Position Sizing</b>\n"
        "/revsize SYMBOL CAPITAL RISK% — Quick position size calc\n"
        "  Example: <code>/revsize RELIANCE 500000 1</code>\n\n"
        "<b>🚫 Blackout Calendar</b>\n"
        "/revblackout LIST — Show all active blackout dates\n"
        "/revblackout ADD SYMBOL YYYY-MM-DD — Add blackout\n"
        "/revblackout REMOVE SYMBOL YYYY-MM-DD — Remove blackout\n"
        "  (Use GLOBAL as symbol to block all stocks on that date)\n\n"
        "<b>💼 Virtual Portfolio</b>\n"
        "/revportfolio — Open positions &amp; unrealised P&amp;L\n"
        "/revhistory — Last 10 closed trades\n"
        "/revreset — Reset virtual portfolio to default capital\n"
        "/revtoggle on|off — Enable/disable auto paper trading\n\n"
        "ℹ️ Virtual portfolio is <b>separate</b> from the uptrend strategy portfolio."
    )
    await _reply(update, text)


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /revstatus — last scan summary + portfolio snapshot."""
    cfg     = _get_config()
    trader  = _get_trader()

    # Read last scan snapshot if available
    snap_path = os.path.join(_HERE, "universe_snapshot.json")
    if os.path.exists(snap_path):
        import json
        with open(snap_path, "r") as fh:
            snap = json.load(fh)
        conf   = [c for c in snap if c.get("tag") == "confirmed_entry" and not c.get("blacked_out")]
        watch  = [c for c in snap if c.get("tag") == "early_entry"     and not c.get("blacked_out")]
        blacked = [c for c in snap if c.get("blacked_out")]
        scan_date = snap[0].get("scan_date", "unknown") if snap else "unknown"
    else:
        conf, watch, blacked = [], [], []
        scan_date = "No scan run yet"

    port     = trader.positions
    cash     = trader.cash
    auto_on  = cfg.auto_paper_trade_enabled

    text = (
        f"📈 <b>RSI Reversal — System Status</b>\n\n"
        f"🗓️ Last scan: {scan_date}\n"
        f"✅ Confirmed entries: <b>{len(conf)}</b>\n"
        f"👀 Watchlist setups:  <b>{len(watch)}</b>\n"
        f"🚫 Blacked out:       <b>{len(blacked)}</b>\n\n"
        f"💼 Open positions:   <b>{len(port)}</b>\n"
        f"💰 Cash balance:     <b>₹{cash:,.2f}</b>\n"
        f"🤖 Auto paper trade: <b>{'ON ✅' if auto_on else 'OFF 🔴'}</b>\n\n"
        f"🕐 Full scan scheduled: {cfg.schedule.get('full_scan_time_ist','19:00')} IST (Mon–Fri)"
    )
    await _reply(update, text)


async def cmd_scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /revscan — trigger an on-demand full scan."""
    await _reply(update, "⏳ <b>RSI Reversal scan started…</b>\nThis may take a few minutes. I'll notify you when done.")
    try:
        from scheduler import Scheduler
        sched = Scheduler()
        sched.run_full()
        await _reply(update, "✅ <b>Reversal scan complete!</b> Check the dashboard or use /revstatus.")
    except Exception as exc:
        await _reply(update, f"❌ <b>Scan failed:</b> {exc}")


async def cmd_chart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /revchart SYMBOL — send candlestick + RSI chart."""
    args = context.args
    if not args:
        await _reply(update, "Usage: <code>/revchart RELIANCE</code>")
        return

    symbol = args[0].upper().strip()
    await _reply(update, f"📊 Fetching chart for <b>{symbol}</b>…")

    try:
        import yfinance as yf
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches
        import numpy as np

        df = yf.download(f"{symbol}.NS", period="6mo", interval="1d", progress=False)
        if df.empty:
            await _reply(update, f"❌ No data found for {symbol}.")
            return

        closes = df["Close"].to_numpy(dtype=float)
        opens  = df["Open"].to_numpy(dtype=float)
        highs  = df["High"].to_numpy(dtype=float)
        lows   = df["Low"].to_numpy(dtype=float)
        dates  = [str(d)[:10] for d in df.index]

        # Compute RSI
        from reversal_analyzer import _rsi_series
        rsi_vals = _rsi_series(closes, 14)

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), gridspec_kw={"height_ratios": [3, 1]})
        fig.patch.set_facecolor("#0e1929")
        for ax in (ax1, ax2):
            ax.set_facecolor("#0e1929")
            ax.tick_params(colors="#64748b")
            ax.spines["bottom"].set_color("#1e293b")
            ax.spines["left"].set_color("#1e293b")
            ax.spines["top"].set_visible(False)
            ax.spines["right"].set_visible(False)

        # Candlestick
        x = range(len(dates))
        for i, xi in enumerate(x):
            color = "#10b981" if closes[i] >= opens[i] else "#ef4444"
            ax1.plot([xi, xi], [lows[i], highs[i]], color=color, linewidth=0.8)
            ax1.bar(xi, abs(closes[i] - opens[i]), 0.6, min(opens[i], closes[i]), color=color, alpha=0.9)

        # RSI chart
        rsi_x = [i for i, v in enumerate(rsi_vals) if not np.isnan(v)]
        rsi_y = [rsi_vals[i] for i in rsi_x]
        ax2.plot(rsi_x, rsi_y, color="#3b82f6", linewidth=1.5)
        ax2.axhline(60, color="#10b981", linewidth=0.8, linestyle="--", alpha=0.7)
        ax2.axhline(40, color="#f59e0b", linewidth=0.8, linestyle="--", alpha=0.7)
        ax2.fill_between(rsi_x, rsi_y, 40, where=[v < 40 for v in rsi_y], alpha=0.15, color="#f59e0b")
        ax2.set_ylim(0, 100)
        ax2.set_ylabel("RSI(14)", color="#64748b", fontsize=8)

        ax1.set_title(f"{symbol} — RSI Reversal Setup", color="#e2e8f0", fontsize=13, fontweight="bold")
        ax1.set_xticks([])

        # Label last few x-axis dates
        step  = max(1, len(dates) // 6)
        ticks = list(range(0, len(dates), step))
        ax2.set_xticks(ticks)
        ax2.set_xticklabels([dates[i] for i in ticks], fontsize=7, rotation=30, color="#64748b")

        plt.tight_layout()
        buf = io.BytesIO()
        plt.savefig(buf, format="png", dpi=130, bbox_inches="tight", facecolor="#0e1929")
        buf.seek(0)
        plt.close(fig)

        await update.message.reply_photo(
            photo   = InputFile(buf, filename=f"{symbol}_chart.png"),
            caption = f"📊 {symbol} — 6-month candlestick + RSI(14)"
        )

    except Exception as exc:
        await _reply(update, f"❌ Chart failed for {symbol}: {exc}")


async def cmd_size(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /revsize SYMBOL CAPITAL RISK% — quick position size calc."""
    args = context.args
    if len(args) < 3:
        await _reply(update, "Usage: <code>/revsize RELIANCE 500000 1</code>")
        return

    symbol  = args[0].upper()
    try:
        capital  = float(args[1])
        risk_pct = float(args[2])
    except ValueError:
        await _reply(update, "❌ Invalid capital or risk% — use numbers.")
        return

    # Try to get entry/SL from last scan snapshot
    snap_path = os.path.join(_HERE, "universe_snapshot.json")
    entry = sl = None
    if os.path.exists(snap_path):
        import json
        with open(snap_path) as fh:
            snap = json.load(fh)
        for c in snap:
            if c.get("symbol") == symbol:
                entry = c.get("entry")
                sl    = c.get("sl")
                break

    if entry is None or sl is None:
        await _reply(update, f"ℹ️ {symbol} not found in last scan. Using price from Yahoo Finance…")
        try:
            import yfinance as yf
            ticker = yf.Ticker(f"{symbol}.NS")
            hist   = ticker.history(period="5d")
            if hist.empty:
                await _reply(update, f"❌ Could not fetch price for {symbol}.")
                return
            entry = float(hist["High"].iloc[-1])
            sl    = float(hist["Low"].iloc[-5:].min())
        except Exception as exc:
            await _reply(update, f"❌ Failed to fetch data: {exc}")
            return

    cfg    = _get_config()
    result = _size_compute(entry, sl, capital, risk_pct, cfg.reward_multiple)

    warn = f"\n⚠️ {result['warning']}" if result["warning"] else ""
    text = (
        f"📐 <b>Position Sizing — {symbol}</b>\n\n"
        f"Entry:            ₹{result['entry']:,.2f}\n"
        f"Stop Loss:        ₹{result['sl']:,.2f}\n"
        f"Risk / Share:     ₹{result['risk_per_share']:,.2f}\n"
        f"Risk Amount:      ₹{result['risk_amount']:,.2f} ({risk_pct}% of ₹{capital:,.0f})\n"
        f"Shares to Buy:    <b>{result['qty']}</b>\n"
        f"Capital Required: ₹{result['capital_required']:,.2f}\n"
        f"1R Target ({cfg.reward_multiple}×): ₹{result['target_1r']:,.2f}\n"
        f"Potential Loss:   ₹{result['potential_loss']:,.2f}\n"
        f"Gain @ 1R:        ₹{result['potential_gain_1r']:,.2f}"
        f"{warn}"
    )
    await _reply(update, text)


async def cmd_blackout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /revblackout LIST | ADD SYMBOL DATE | REMOVE SYMBOL DATE."""
    bf   = _get_blackout()
    args = context.args

    if not args or args[0].upper() == "LIST":
        await _reply(update, bf.list_all())
        return

    action = args[0].upper()
    if action in ("ADD", "REMOVE"):
        if len(args) < 3:
            await _reply(update, f"Usage: /revblackout {action} SYMBOL YYYY-MM-DD")
            return
        sym    = args[1].upper()
        date   = args[2]
        if action == "ADD":
            await _reply(update, bf.add(sym, date))
        else:
            await _reply(update, bf.remove(sym, date))
    else:
        await _reply(update, "Usage: /revblackout LIST | ADD SYMBOL DATE | REMOVE SYMBOL DATE")


async def cmd_portfolio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /revportfolio — show open positions with unrealised P&L."""
    trader = _get_trader()
    await _reply(update, trader.format_portfolio())


async def cmd_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /revhistory — show last 10 closed trades."""
    trader = _get_trader()
    await _reply(update, trader.format_history(10))


async def cmd_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /revreset — reset virtual portfolio to default capital."""
    cfg    = _get_config()
    trader = _get_trader()
    msg    = trader.reset(cfg.default_capital)
    await _reply(update, msg)


async def cmd_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /revtoggle on|off — enable/disable auto paper trading."""
    args = context.args
    if not args or args[0].lower() not in ("on", "off"):
        await _reply(update, "Usage: <code>/revtoggle on</code> or <code>/revtoggle off</code>")
        return

    cfg     = _get_config()
    enabled = args[0].lower() == "on"
    cfg.auto_paper_trade_enabled = enabled   # saves to config.json automatically
    status  = "✅ ON" if enabled else "🔴 OFF"
    await _reply(update, f"🤖 RSI Reversal auto paper trading is now <b>{status}</b>.")
