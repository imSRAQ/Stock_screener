import os
import json
from datetime import datetime
from typing import List, Dict

class HistoryManager:
    """Manages the historical record of AI recommendations and calculates paper trading analytics."""

    def __init__(self):
        self.filepath = os.path.join(os.path.dirname(__file__), "historical_recommendations.json")
        self.history: List[dict] = []
        self._load_history()

    def _load_history(self):
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r") as f:
                    self.history = json.load(f)
            except Exception as e:
                print(f"[warn] Failed to load history: {e}")
                self.history = []

    def _save_history(self):
        try:
            with open(self.filepath, "w") as f:
                json.dump(self.history, f, indent=4)
        except Exception as e:
            print(f"[warn] Failed to save history: {e}")

    def record_entries(self, entries: List[Dict]):
        """Records new entry signals into the history log."""
        today = datetime.now().strftime("%Y-%m-%d")
        
        # Check if we already recorded these symbols today to prevent duplicates on hourly runs
        existing_today = {h['symbol'] for h in self.history if h['date'] == today}
        
        added = False
        for item in entries:
            sym = item['data'].get('symbol')
            if not sym or sym in existing_today:
                continue
                
            self.history.append({
                "symbol": sym,
                "date": today,
                "entry_price": item['data'].get('price', 0),
                "stop_loss": item['data'].get('stop_loss', 0),
                "ai_summary": item.get('ai', {}).get('ai_summary', ''),
                "tv_signal": item.get('sentiment', {}).get('technical', {}).get('recommendation', 'UNKNOWN')
            })
            added = True
            
        if added:
            self._save_history()

    def calculate_analytics(self) -> dict:
        """Calculates win rate and average P&L based on current market prices."""
        if not self.history:
            return {
                "total_trades": 0,
                "win_rate": 0.0,
                "avg_profit_pct": 0.0,
                "active_history": []
            }
            
        import yfinance as yf
        
        # Collect symbols
        symbols = list({h['symbol'] + ".NS" for h in self.history})
        
        current_prices = {}
        if symbols:
            try:
                data = yf.download(symbols, period="1d", group_by="ticker", threads=True, progress=False)
                for sym in symbols:
                    base_sym = sym.replace(".NS", "")
                    if len(symbols) == 1:
                        # yfinance returns a flat dataframe for a single ticker
                        price = data['Close'].iloc[-1] if not data.empty and 'Close' in data else 0
                    else:
                        price = data[sym]['Close'].iloc[-1] if sym in data and not data[sym].empty else 0
                    if not type(price) in (float, int) and hasattr(price, "item"):
                        price = price.item()
                    current_prices[base_sym] = float(price) if price else 0.0
            except Exception as e:
                print(f"[warn] Failed to fetch current prices for history: {e}")
            
        wins = 0
        total_pnl_pct = 0.0
        active_history = []
        
        for h in self.history:
            sym = h['symbol']
            entry = h['entry_price']
            
            # Use fetched current price, else fallback to entry
            current = current_prices.get(sym, entry)
            if current == 0:
                current = entry
                
            pnl_pct = ((current - entry) / entry) * 100 if entry > 0 else 0
            
            # Simple assumption: If currently in profit, it's a "win"
            if pnl_pct > 0:
                wins += 1
                
            total_pnl_pct += pnl_pct
            
            # Create a rich history object for the dashboard
            active_history.append({
                **h,
                "current_price": current,
                "pnl_pct": pnl_pct
            })
            
        win_rate = (wins / len(self.history)) * 100
        avg_profit = total_pnl_pct / len(self.history)
        
        # Sort by date descending
        active_history.sort(key=lambda x: x['date'], reverse=True)
        
        return {
            "total_trades": len(self.history),
            "win_rate": win_rate,
            "avg_profit_pct": avg_profit,
            "active_history": active_history
        }
