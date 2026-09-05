"""
telegram_notifier.py
--------------------
Sends formatted Telegram alerts (Entry, Exit, Watchlist, Status) and
listens for bot commands (/watch, /unwatch, /watchlist, /status, /hourly)
to manage the system remotely.
"""

import threading
import asyncio
import io
from typing import List, Dict, Optional
from telegram import Update, InputFile
from telegram.ext import Application, CommandHandler, ContextTypes

import yfinance as yf
import matplotlib.pyplot as plt

from watchlist_manager import WatchlistManager
from config_manager import ConfigManager
from market_health import MarketHealthChecker
from portfolio_manager import PortfolioManager

class TelegramNotifier:
    """Handles sending notifications and running the Telegram bot."""

    def __init__(self, config: ConfigManager, watchlist: WatchlistManager, portfolio: PortfolioManager = None):
        self.config = config
        self.watchlist = watchlist
        self.portfolio = portfolio
        self.bot_token = config.telegram_bot_token
        self.chat_id = config.telegram_chat_id
        
        self.is_configured = bool(self.bot_token and self.chat_id)
        
        # We need a separate event loop for the bot if running in background
        self._bot_thread = None
        self._bot_app = None

    # Telegram API limit is 4096 characters per message
    MAX_MSG_LEN = 4096

    async def _send_message_async(self, text: str):
        if not self.is_configured:
            print("[warn] Telegram not configured. Skipping message.")
            return
            
        import telegram
        bot = telegram.Bot(token=self.bot_token)

        # Split long messages into chunks that fit the Telegram limit
        chunks = self._split_message(text)
        for chunk in chunks:
            try:
                await bot.send_message(chat_id=self.chat_id, text=chunk, parse_mode='HTML')
            except Exception as e:
                print(f"[error] Failed to send Telegram message: {e}")

    def _split_message(self, text: str) -> list:
        """Splits a message into chunks of MAX_MSG_LEN or fewer characters,
        breaking at newline boundaries so we never cut mid-line."""
        if len(text) <= self.MAX_MSG_LEN:
            return [text]

        chunks = []
        while text:
            if len(text) <= self.MAX_MSG_LEN:
                chunks.append(text)
                break
            # Find the last newline within the limit
            split_at = text.rfind('\n', 0, self.MAX_MSG_LEN)
            if split_at == -1:
                # No newline found; hard-cut at the limit
                split_at = self.MAX_MSG_LEN
            chunks.append(text[:split_at])
            text = text[split_at:].lstrip('\n')
        return chunks

    def send_message(self, text: str):
        """Sends a message synchronously (auto-splits if too long)."""
        if not self.is_configured:
            return
        asyncio.run(self._send_message_async(text))

    def _format_stock_entry(self, data: dict, sentiment: dict, ai_summary: dict) -> str:
        """Formats a single stock for the Entry/Exit lists."""
        sym = data.get("symbol", "UNKNOWN")
        price = data.get("price", 0)
        slope = data.get("slope", 0)
        rsi = data.get("rsi", 0)
        adx = data.get("adx", 0)
        sl = data.get("stop_loss", 0)
        
        tv_signal = sentiment.get("technical", {}).get("recommendation", "UNKNOWN")
        ai_text = ai_summary.get("ai_summary", "No AI summary.")
        news = ai_summary.get("raw_news", [])
        
        msg = f"<b>{sym}</b> | ₹{price:.2f} | Slope: {slope:.3f}\n"
        msg += f"RSI: {rsi} | ADX: {adx} | SL: ₹{sl:.2f}\n"
        msg += f"TV Signal: {tv_signal}\n"
        msg += f"<i>AI: {ai_text}</i>\n"
        if news:
            msg += "Recent News:\n"
            for n in news:
                msg += f"• {n}\n"
        msg += "\n"
        return msg

    # How many stocks to include per Telegram message to stay under the
    # 4096-char limit comfortably (each stock block is ~300-500 chars).
    STOCKS_PER_MSG = 8

    def send_scan_results(self, entry_list: List[Dict], exit_list: List[Dict], market_health: Dict):
        """Sends a short summary of the scan results with a link to the HTML dashboard."""
        
        header = market_health.get("status_text", "MARKET HEALTH: UNKNOWN")
        
        if not entry_list and not exit_list:
            self.send_message(f"{header}\n\nScan complete. No actionable signals found.")
            return

        msg = f"🚨 <b>NSE Scan Complete!</b>\n\n"
        msg += f"{header}\n\n"
        msg += f"🟢 {len(entry_list)} Entry Candidates\n"
        msg += f"🔴 {len(exit_list)} Caution / Exits\n\n"
        
        # We can hardcode the repo URL since it's hosted via GitHub Pages for the user.
        # Format is typically: https://<username>.github.io/<repo>/
        # Alternatively we can grab it from config, but for simplicity:
        dashboard_url = "https://imSRAQ.github.io/Stock_screener/stocks_monitoring_and_notifying/docs/"
        
        msg += f"👉 <b>View Full AI Dashboard:</b>\n{dashboard_url}"
        
        self.send_message(msg)

    def send_trailing_stop_alerts(self, alerts: List[Dict]):
        """Sends alerts for hit or updated trailing stops."""
        if not alerts:
            return
            
        msg = "<b>🚨 PORTFOLIO ALERTS</b>\n\n"
        for alert in alerts:
            sym = alert["symbol"]
            if alert["type"] == "STOP_HIT":
                pnl = alert["pnl"]
                emoji = "🟢" if pnl >= 0 else "🔴"
                msg += f"💥 <b>STOP HIT: {sym}</b> at ₹{alert['price']:.2f}\n"
                msg += f"Profit/Loss: {emoji} ₹{pnl:.2f}\n\n"
            elif alert["type"] == "STOP_UPDATED":
                msg += f"🛡️ <b>STOP RAISED: {sym}</b>\n"
                msg += f"Stock reached ₹{alert['highest_price']:.2f}.\n"
                msg += f"New SL: ₹{alert['new_sl']:.2f} (was ₹{alert['old_sl']:.2f})\n\n"
                
        self.send_message(msg)

    def send_weekly_new_entries(self, new_entries: List[Dict], market_health: Dict):
        """Sends the weekly diff of new entries."""
        if not new_entries:
            return
            
        header = market_health.get("status_text", "MARKET HEALTH: UNKNOWN")
        msg = f"{header}\n\n<b>🆕 NEW ENTRIES THIS WEEK</b>\n\n"
        
        for item in new_entries:
            msg += self._format_stock_entry(item["data"], item["sentiment"], item["ai"])
            
        self.send_message(msg)

    # ------------------------------------------------------------------
    # Bot Command Handlers
    # ------------------------------------------------------------------

    async def _cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        welcome_msg = (
            "🤖 <b>NSE Stock Monitor Bot is running!</b>\n\n"
            "Here are the available commands:\n\n"
            "<b>Watchlist Management:</b>\n"
            "/watch SYMBOL — Add a stock to special watchlist\n"
            "/unwatch SYMBOL — Remove a stock\n"
            "/watchlist — View your watchlist\n\n"
            "<b>Portfolio Management:</b>\n"
            "/entry [SYMBOL] [PRICE] [QTY] [SL] — Add to portfolio\n"
            "/exit [SYMBOL] — Remove from portfolio\n"
            "/portfolio — View current holdings & P&L\n\n"
            "<b>Interactive Analysis:</b>\n"
            "/chart [SYMBOL] — Get a technical chart with MAs\n\n"
            "<b>Examples:</b>\n"
            "/watch RELIANCE\n"
            "/entry RELIANCE 2500 10 2400\n"
            "/chart INFY\n\n"
            "<b>System Controls:</b>\n"
            "/status — View market health & config\n"
            "/hourly on|off — Toggle hourly scans\n\n"
            "<b>🎮 Virtual Auto-Trader:</b>\n"
            "/vportfolio — View virtual holdings\n"
            "/vhistory — View recent virtual trades\n"
            "/vreset — Reset virtual balance to ₹500,000\n\n"
            "/help — Show this menu again"
        )
        await update.message.reply_text(welcome_msg, parse_mode='HTML')

    async def _cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await self._cmd_start(update, context)

    async def _cmd_watch(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not context.args:
            await update.message.reply_text("Usage: /watch SYMBOL")
            return
        symbol = context.args[0]
        if self.watchlist.add(symbol):
            await update.message.reply_text(f"Added {symbol.upper()} to Special Watchlist.")
        else:
            await update.message.reply_text(f"{symbol.upper()} is already in the watchlist.")

    async def _cmd_unwatch(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not context.args:
            await update.message.reply_text("Usage: /unwatch SYMBOL")
            return
        symbol = context.args[0]
        if self.watchlist.remove(symbol):
            await update.message.reply_text(f"Removed {symbol.upper()} from Special Watchlist.")
        else:
            await update.message.reply_text(f"{symbol.upper()} is not in the watchlist.")

    async def _cmd_watchlist(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        items = self.watchlist.get_all()
        if not items:
            await update.message.reply_text("Special Watchlist is empty.")
        else:
            await update.message.reply_text("Special Watchlist:\n" + "\n".join(items))

    async def _cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        mh = MarketHealthChecker().check()
        status = mh.get("status_text", "UNKNOWN")
        hourly = "ON" if self.config.hourly_enabled else "OFF"
        await update.message.reply_text(f"System Status:\n{status}\nHourly Scans: {hourly}")

    async def _cmd_hourly(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not context.args or context.args[0].lower() not in ["on", "off"]:
            await update.message.reply_text("Usage: /hourly [on|off]")
            return
            
        state = context.args[0].lower() == "on"
        self.config.hourly_enabled = state
        self.config.save()
        await update.message.reply_text(f"Hourly refreshes turned {'ON' if state else 'OFF'}.")

    async def _cmd_entry(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.portfolio:
            await update.message.reply_text("Portfolio manager is not initialized.")
            return
            
        if len(context.args) < 3:
            await update.message.reply_text("Usage: /entry SYMBOL PRICE QUANTITY [STOP_LOSS]")
            return
            
        try:
            symbol = context.args[0]
            price = float(context.args[1])
            qty = int(context.args[2])
            
            # If SL not provided, default to 5% below entry
            sl = float(context.args[3]) if len(context.args) > 3 else price * 0.95
            
            res = self.portfolio.add_position(symbol, price, qty, sl)
            await update.message.reply_text(res)
        except ValueError:
            await update.message.reply_text("Error: Price, Quantity, and Stop Loss must be numbers.")

    async def _cmd_exit(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.portfolio:
            return
            
        if not context.args:
            await update.message.reply_text("Usage: /exit SYMBOL")
            return
            
        symbol = context.args[0]
        res = self.portfolio.remove_position(symbol)
        await update.message.reply_text(res)

    async def _cmd_portfolio(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.portfolio:
            return
            
        positions = self.portfolio.get_portfolio()
        if not positions:
            await update.message.reply_text("💼 Portfolio is currently empty.")
            return
            
        msg = "<b>💼 VIRTUAL PORTFOLIO</b>\n\n"
        for sym, data in positions.items():
            entry = data['entry_price']
            qty = data['quantity']
            tsl = data['trailing_sl']
            high = data['highest_price']
            
            msg += f"<b>{sym}</b> (Qty: {qty})\n"
            msg += f"Entry: ₹{entry:.2f} | High: ₹{high:.2f}\n"
            msg += f"Trailing SL: ₹{tsl:.2f}\n\n"
            
        await update.message.reply_text(msg, parse_mode='HTML')

    async def _cmd_chart(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Generates a technical chart for a given symbol."""
        if not context.args:
            await update.message.reply_text("Please provide a symbol. Example: /chart RELIANCE")
            return
            
        raw_symbol = context.args[0].upper()
        # Assume NSE for Indian stocks
        symbol = raw_symbol + ".NS" if not raw_symbol.endswith(".NS") else raw_symbol
        
        loading_msg = await update.message.reply_text(f"📊 Fetching data and generating chart for {raw_symbol}...")
        
        try:
            # Run in executor to not block async loop
            def generate_chart():
                data = yf.download(symbol, period="6mo", progress=False)
                if data.empty:
                    return None
                    
                # Setup dark theme
                plt.style.use('dark_background')
                fig, ax = plt.subplots(figsize=(10, 6))
                
                # Plot price
                if isinstance(data.columns, pd.MultiIndex):
                    close = data['Close'][symbol]
                else:
                    close = data['Close']
                    
                ax.plot(close.index, close, label='Close', color='#3b82f6', linewidth=1.5)
                
                # Calculate and plot SMAs
                sma50 = close.rolling(window=50).mean()
                sma200 = close.rolling(window=200).mean()
                ax.plot(sma50.index, sma50, label='50 SMA', color='#10b981', linewidth=1.2, linestyle='--')
                ax.plot(sma200.index, sma200, label='200 SMA', color='#ef4444', linewidth=1.2, linestyle='--')
                
                # Formatting
                ax.set_title(f"{raw_symbol} - 6 Month Technical Chart", color='white', pad=15)
                ax.grid(True, color='#334155', linestyle='-', alpha=0.5)
                ax.legend(facecolor='#1e293b', edgecolor='#334155')
                
                # Save to buffer
                buf = io.BytesIO()
                fig.savefig(buf, format='png', bbox_inches='tight', dpi=150, facecolor='#0f172a')
                buf.seek(0)
                plt.close(fig)
                return buf
                
            import pandas as pd
            loop = asyncio.get_event_loop()
            buf = await loop.run_in_executor(None, generate_chart)
            
            if not buf:
                await loading_msg.edit_text(f"❌ Could not fetch data for {raw_symbol}. Check symbol.")
                return
                
            await update.message.reply_photo(photo=InputFile(buf, filename=f"{raw_symbol}_chart.png"))
            await loading_msg.delete()
            
        except Exception as e:
            await loading_msg.edit_text(f"❌ Error generating chart: {str(e)}")

    async def _cmd_vportfolio(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        from paper_trader import PaperTrader
        pt = PaperTrader()
        positions = pt.get_portfolio()
        cash = pt.get_cash()
        
        msg = f"<b>🎮 VIRTUAL PORTFOLIO</b>\nCash Balance: ₹{cash:,.2f}\n\n"
        if not positions:
            msg += "No active virtual positions."
        else:
            for sym, data in positions.items():
                entry = data['entry_price']
                qty = data['quantity']
                tsl = data['trailing_sl']
                tgt = data['target_price']
                partial = " (50% Sold)" if data.get('partial_taken') else ""
                
                msg += f"<b>{sym}</b>{partial}\n"
                msg += f"Qty: {qty} | Entry: ₹{entry:.2f}\n"
                msg += f"SL: ₹{tsl:.2f} | Tgt: ₹{tgt:.2f}\n\n"
                
        await update.message.reply_text(msg, parse_mode='HTML')

    async def _cmd_vhistory(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        from paper_trader import PaperTrader
        pt = PaperTrader()
        history = pt.state.get("trade_history", [])
        
        if not history:
            await update.message.reply_text("No virtual trades executed yet.")
            return
            
        msg = "<b>📜 RECENT VIRTUAL TRADES</b>\n\n"
        for t in history[-10:]: # Show last 10
            emoji = "🟢" if t.get("pnl", 0) > 0 else "🔴"
            msg += f"<b>{t['symbol']}</b> - {t['type']}\n"
            msg += f"Exit: ₹{t['exit_price']:.2f} | PnL: {emoji} ₹{t.get('pnl',0):.2f}\n"
            msg += f"<i>{t['date']}</i>\n\n"
            
        await update.message.reply_text(msg, parse_mode='HTML')

    async def _cmd_vreset(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        from paper_trader import PaperTrader
        pt = PaperTrader()
        pt.state = {
            "cash_balance": 500000.0,
            "positions": {},
            "trade_history": []
        }
        pt.save()
        await update.message.reply_text("✅ Virtual Portfolio has been reset to ₹500,000.")

    def _run_bot_loop(self):
        """Runs the bot polling in a separate thread."""
        try:
            # Create a new event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            self._bot_app = Application.builder().token(self.bot_token).build()
            
            # ── Uptrend strategy commands (unchanged) ─────────────────────────────
            self._bot_app.add_handler(CommandHandler("start",      self._cmd_start))
            self._bot_app.add_handler(CommandHandler("help",       self._cmd_help))
            self._bot_app.add_handler(CommandHandler("watch",      self._cmd_watch))
            self._bot_app.add_handler(CommandHandler("unwatch",    self._cmd_unwatch))
            self._bot_app.add_handler(CommandHandler("watchlist",  self._cmd_watchlist))
            self._bot_app.add_handler(CommandHandler("status",     self._cmd_status))
            self._bot_app.add_handler(CommandHandler("hourly",     self._cmd_hourly))
            self._bot_app.add_handler(CommandHandler("entry",      self._cmd_entry))
            self._bot_app.add_handler(CommandHandler("exit",       self._cmd_exit))
            self._bot_app.add_handler(CommandHandler("portfolio",  self._cmd_portfolio))
            self._bot_app.add_handler(CommandHandler("chart",      self._cmd_chart))
            self._bot_app.add_handler(CommandHandler("vportfolio", self._cmd_vportfolio))
            self._bot_app.add_handler(CommandHandler("vhistory",   self._cmd_vhistory))
            self._bot_app.add_handler(CommandHandler("vreset",     self._cmd_vreset))

            # ── RSI Reversal strategy commands (/rev* prefix) ─────────────────────
            # Handlers live in Multi Timeframe RSI Reversal/rev_handlers.py
            # This is the ONLY change needed to integrate the reversal strategy.
            try:
                import sys, os
                _rev_path = os.path.join(
                    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "Multi Timeframe RSI Reversal"
                )
                if _rev_path not in sys.path:
                    sys.path.insert(0, _rev_path)
                import rev_handlers as rev
                self._bot_app.add_handler(CommandHandler("revhelp",      rev.cmd_help))
                self._bot_app.add_handler(CommandHandler("revstatus",    rev.cmd_status))
                self._bot_app.add_handler(CommandHandler("revscan",      rev.cmd_scan))
                self._bot_app.add_handler(CommandHandler("revchart",     rev.cmd_chart))
                self._bot_app.add_handler(CommandHandler("revsize",      rev.cmd_size))
                self._bot_app.add_handler(CommandHandler("revblackout",  rev.cmd_blackout))
                self._bot_app.add_handler(CommandHandler("revportfolio", rev.cmd_portfolio))
                self._bot_app.add_handler(CommandHandler("revhistory",   rev.cmd_history))
                self._bot_app.add_handler(CommandHandler("revreset",     rev.cmd_reset))
                self._bot_app.add_handler(CommandHandler("revtoggle",    rev.cmd_toggle))
                print("[info] RSI Reversal /rev* commands registered on shared bot.")
            except Exception as rev_exc:
                print(f"[warn] Could not load reversal handlers: {rev_exc}")
                print("[warn] RSI Reversal /rev* commands will not be available.")

            self._bot_app.run_polling(drop_pending_updates=True)
        except Exception as e:
            print(f"[error] Telegram bot listener stopped: {e}")

    def start_bot_listener(self):
        """Starts the bot listener in a background thread."""
        if not self.is_configured:
            print("[warn] Cannot start bot listener: telegram config missing.")
            return
            
        if self._bot_thread is None or not self._bot_thread.is_alive():
            self._bot_thread = threading.Thread(target=self._run_bot_loop, daemon=True)
            self._bot_thread.start()
            print("[info] Telegram bot listener started.")
