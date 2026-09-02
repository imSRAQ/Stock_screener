import os
import json
import math
from datetime import datetime
import subprocess

class PaperTrader:
    def __init__(self, filepath=None):
        if filepath is None:
            self.filepath = os.path.join(os.path.dirname(__file__), "virtual_portfolio.json")
        else:
            self.filepath = filepath
            
        self.state = {
            "cash_balance": 500000.0,
            "positions": {},
            "trade_history": []
        }
        self.load()
        
        self.TOTAL_CAPITAL = 500000.0  # Initial capital reference
        self.RISK_PCT = 0.01  # 1% risk
        self.TARGET_RR = 1.5  # 1:1.5 Risk-Reward

    def load(self):
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    self.state = json.load(f)
            except Exception as e:
                print(f"[warn] Failed to load virtual portfolio: {e}")

    def save(self):
        try:
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(self.state, f, indent=4)
            self._git_sync()
        except Exception as e:
            print(f"[warn] Failed to save virtual portfolio: {e}")

    def _git_sync(self):
        try:
            repo_dir = os.path.dirname(os.path.dirname(self.filepath))
            subprocess.run(["git", "add", "-f", self.filepath], cwd=repo_dir, check=True, capture_output=True)
            commit_res = subprocess.run(["git", "commit", "-m", "Auto-sync virtual_portfolio.json"], cwd=repo_dir, capture_output=True)
            if commit_res.returncode == 0:
                subprocess.run(["git", "push"], cwd=repo_dir, check=True, capture_output=True)
        except Exception as e:
            pass

    def get_portfolio(self):
        return self.state["positions"]
        
    def get_cash(self):
        return self.state["cash_balance"]

    def _calculate_buy_score(self, item):
        d = item.get('data', item)
        tv_rec = item.get('sentiment', {}).get('technical', {}).get('recommendation', 'UNKNOWN')
        rsi = d.get('rsi', 0)
        adx = d.get('adx', 0)
        slope = d.get('slope', 0)
        sector_boost = d.get('sector_boost', False)

        tv_weight = {"STRONG_BUY": 40, "BUY": 25, "BUY_WEAK": 12, "NEUTRAL": 0}.get(tv_rec, 0)
        adx_score = min(float(adx), 50) * 0.6
        rsi_score = max(0.0, 20.0 - abs(float(rsi) - 55.0) * 0.8)
        slope_score = min(float(slope) * 200, 20)
        sector_score = 10 if sector_boost else 0
        return tv_weight + adx_score + rsi_score + slope_score + sector_score

    def execute_trades(self, entry_candidates, exit_candidates, current_prices, notifier):
        alerts = []
        portfolio_updated = False
        
        # --- 1. Process Exits & Trailing Stops ---
        exit_symbols = {item['data']['symbol'] if 'data' in item else item['symbol'] for item in exit_candidates}
        
        for symbol in list(self.state["positions"].keys()):
            pos = self.state["positions"][symbol]
            market_data = current_prices.get(symbol, {})
            current_price = market_data.get("price", 0)
            if current_price == 0:
                continue

            # Check SL
            if current_price <= pos["trailing_sl"]:
                pnl = (current_price - pos["entry_price"]) * pos["quantity"]
                self.state["cash_balance"] += (current_price * pos["quantity"])
                
                self.state["trade_history"].append({
                    "symbol": symbol,
                    "type": "SELL (SL Hit)",
                    "exit_price": current_price,
                    "pnl": pnl,
                    "date": datetime.now().strftime("%Y-%m-%d %H:%M")
                })
                del self.state["positions"][symbol]
                portfolio_updated = True
                
                emoji = "🟢" if pnl > 0 else "🔴"
                alerts.append(f"💥 <b>VIRTUAL STOP HIT: {symbol}</b>\nSold remaining shares at ₹{current_price:.2f}.\nPnL: {emoji} ₹{pnl:.2f}")
                continue

            # Check Target (1.5x) for 50% partial exit
            if not pos.get("partial_taken", False) and current_price >= pos["target_price"]:
                half_qty = pos["quantity"] // 2
                if half_qty > 0:
                    pnl = (current_price - pos["entry_price"]) * half_qty
                    self.state["cash_balance"] += (current_price * half_qty)
                    pos["quantity"] -= half_qty
                    pos["partial_taken"] = True
                    # Trail stop to entry for the rest
                    pos["trailing_sl"] = max(pos["trailing_sl"], pos["entry_price"])
                    
                    self.state["trade_history"].append({
                        "symbol": symbol,
                        "type": "SELL (Target Hit - 50%)",
                        "exit_price": current_price,
                        "pnl": pnl,
                        "date": datetime.now().strftime("%Y-%m-%d %H:%M")
                    })
                    portfolio_updated = True
                    alerts.append(f"🎯 <b>VIRTUAL TARGET HIT: {symbol}</b>\nSold 50% ({half_qty} shares) at ₹{current_price:.2f} for +₹{pnl:.2f}.\nSL for rest moved to Entry (₹{pos['trailing_sl']:.2f}).")
                
            # Check System Exit Signal
            if symbol in exit_symbols:
                pnl = (current_price - pos["entry_price"]) * pos["quantity"]
                self.state["cash_balance"] += (current_price * pos["quantity"])
                
                self.state["trade_history"].append({
                    "symbol": symbol,
                    "type": "SELL (AI Caution)",
                    "exit_price": current_price,
                    "pnl": pnl,
                    "date": datetime.now().strftime("%Y-%m-%d %H:%M")
                })
                del self.state["positions"][symbol]
                portfolio_updated = True
                emoji = "🟢" if pnl > 0 else "🔴"
                alerts.append(f"⚠️ <b>VIRTUAL AI CAUTION: {symbol}</b>\nAuto-sold position at ₹{current_price:.2f}.\nPnL: {emoji} ₹{pnl:.2f}")
                continue

            # Standard Trailing Stop (ATR based)
            if current_price > pos["highest_price"]:
                pos["highest_price"] = current_price
                atr = market_data.get("atr", 0)
                if atr > 0:
                    new_sl = current_price - (1.5 * atr)
                    if new_sl > pos["trailing_sl"]:
                        old_sl = pos["trailing_sl"]
                        pos["trailing_sl"] = round(new_sl, 2)
                        alerts.append(f"🛡️ <b>VIRTUAL SL RAISED: {symbol}</b>\nNew SL: ₹{pos['trailing_sl']:.2f} (was ₹{old_sl:.2f})")
                        portfolio_updated = True
                        
        # --- 2. Process Entries ---
        active_positions = len(self.state["positions"])
        max_positions = 5
        
        # Sort candidates by buy score
        scored_candidates = []
        for item in entry_candidates:
            score = self._calculate_buy_score(item)
            scored_candidates.append((score, item))
        
        scored_candidates.sort(key=lambda x: x[0], reverse=True)
        
        for score, item in scored_candidates:
            if active_positions >= max_positions:
                break
                
            d = item.get('data', item)
            symbol = d.get('symbol')
            if symbol in self.state["positions"]:
                continue
                
            rsi = d.get('rsi', 0)
            price = d.get('price', 0)
            sl = d.get('stop_loss', 0)
            
            # Pullback criteria: RSI between 40 and 55, Score > 60
            if 40 <= rsi <= 55 and score >= 60 and price > 0 and sl > 0 and price > sl:
                risk_per_share = price - sl
                total_risk_amount = self.TOTAL_CAPITAL * self.RISK_PCT # 1% risk
                
                qty = math.floor(total_risk_amount / risk_per_share)
                cost = qty * price
                
                if qty > 0 and self.state["cash_balance"] >= cost:
                    target_price = price + (risk_per_share * self.TARGET_RR)
                    
                    self.state["positions"][symbol] = {
                        "entry_price": price,
                        "quantity": qty,
                        "initial_sl": sl,
                        "trailing_sl": sl,
                        "highest_price": price,
                        "target_price": target_price,
                        "partial_taken": False
                    }
                    self.state["cash_balance"] -= cost
                    active_positions += 1
                    portfolio_updated = True
                    
                    alerts.append(f"🎮 <b>VIRTUAL BUY: {symbol} (Pullback)</b>\nBought {qty} shares at ₹{price:.2f}.\nRisk: 1% (₹{total_risk_amount:.2f})\nTarget (1.5x): ₹{target_price:.2f}\nSL: ₹{sl:.2f}")

        if portfolio_updated:
            self.save()
            
        if alerts and notifier:
            msg = "<b>🤖 AUTO-TRADER EXECUTION</b>\n\n" + "\n\n".join(alerts)
            notifier.send_message(msg)
