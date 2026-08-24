"""
portfolio_manager.py
--------------------
Manages the virtual portfolio, tracking entry prices, quantities,
and calculating trailing stop losses based on price movements.
"""

import os
import json
import subprocess
from typing import Dict, List

class PortfolioManager:
    """Manages virtual portfolio and trailing stops."""

    def __init__(self, filepath: str = None):
        if filepath is None:
            self.filepath = os.path.join(os.path.dirname(__file__), "portfolio.json")
        else:
            self.filepath = filepath
            
        # Default structure
        # { "RELIANCE": {"entry_price": 2500, "quantity": 10, "initial_sl": 2400, "trailing_sl": 2400, "highest_price": 2500} }
        self.portfolio: Dict[str, dict] = {}
        self.load()

    def load(self):
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    self.portfolio = json.load(f)
            except Exception as e:
                print(f"[warn] Failed to load portfolio: {e}")
                self.portfolio = {}

    def save(self):
        try:
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(self.portfolio, f, indent=4)
            self._git_sync()
        except Exception as e:
            print(f"[warn] Failed to save portfolio: {e}")

    def _git_sync(self):
        """Attempts to commit and push changes to git."""
        try:
            repo_dir = os.path.dirname(os.path.dirname(self.filepath))
            subprocess.run(["git", "add", "-f", self.filepath], cwd=repo_dir, check=True, capture_output=True)
            commit_res = subprocess.run(["git", "commit", "-m", "Auto-sync portfolio.json"], cwd=repo_dir, capture_output=True)
            if commit_res.returncode == 0:
                subprocess.run(["git", "push"], cwd=repo_dir, check=True, capture_output=True)
        except Exception as e:
            print(f"[warn] Git sync failed for portfolio: {e}")

    def add_position(self, symbol: str, entry_price: float, quantity: int, initial_sl: float) -> str:
        symbol = symbol.upper().strip()
        if symbol in self.portfolio:
            return f"{symbol} is already in the portfolio. Use /exit first to close it."
            
        self.portfolio[symbol] = {
            "entry_price": entry_price,
            "quantity": quantity,
            "initial_sl": initial_sl,
            "trailing_sl": initial_sl,
            "highest_price": entry_price
        }
        self.save()
        return f"✅ Added {symbol} at ₹{entry_price} (Qty: {quantity}). Initial SL: ₹{initial_sl}."

    def remove_position(self, symbol: str) -> str:
        symbol = symbol.upper().strip()
        if symbol in self.portfolio:
            del self.portfolio[symbol]
            self.save()
            return f"✅ Closed position for {symbol}."
        return f"❌ {symbol} not found in portfolio."

    def get_portfolio(self) -> Dict[str, dict]:
        return self.portfolio

    def check_trailing_stops(self, current_prices: Dict[str, dict], config: dict) -> List[dict]:
        """
        Evaluates current prices against trailing stops.
        Updates trailing stops if prices have moved favorably.
        Returns a list of alerts (either updates or exits).
        
        current_prices: { "RELIANCE": {"price": 2600, "atr": 45} }
        config: Portfolio config from ConfigManager.
        """
        alerts = []
        activation_pct = config.get("trailing_stop_activation_pct", 5.0) / 100.0
        distance_atr = config.get("trailing_stop_distance_atr", 1.5)
        
        portfolio_updated = False

        # Need to iterate over a list of keys since we might delete elements on exit
        for symbol in list(self.portfolio.keys()):
            pos = self.portfolio[symbol]
            
            if symbol not in current_prices:
                continue
                
            market_data = current_prices[symbol]
            current_price = market_data.get("price", 0)
            atr = market_data.get("atr", 0)
            
            if current_price == 0:
                continue

            # Update highest price seen
            if current_price > pos["highest_price"]:
                pos["highest_price"] = current_price
                portfolio_updated = True

            entry = pos["entry_price"]
            highest = pos["highest_price"]
            
            # Check if stop loss is hit
            if current_price <= pos["trailing_sl"]:
                profit_loss = (current_price - entry) * pos["quantity"]
                alerts.append({
                    "type": "STOP_HIT",
                    "symbol": symbol,
                    "price": current_price,
                    "stop_loss": pos["trailing_sl"],
                    "pnl": profit_loss
                })
                # Remove from portfolio automatically
                del self.portfolio[symbol]
                portfolio_updated = True
                continue

            # Check if we should activate/update trailing stop
            # Condition: Stock must have moved up by `activation_pct` from entry
            if (highest - entry) / entry >= activation_pct:
                new_sl = highest - (distance_atr * atr)
                
                # We only move the trailing stop UP, never down.
                if new_sl > pos["trailing_sl"]:
                    old_sl = pos["trailing_sl"]
                    pos["trailing_sl"] = round(new_sl, 2)
                    portfolio_updated = True
                    
                    alerts.append({
                        "type": "STOP_UPDATED",
                        "symbol": symbol,
                        "old_sl": old_sl,
                        "new_sl": pos["trailing_sl"],
                        "highest_price": highest
                    })

        if portfolio_updated:
            self.save()
            
        return alerts
