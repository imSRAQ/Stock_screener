import os
from datetime import datetime

class DashboardGenerator:
    """Generates a static HTML dashboard from the latest scan results and history."""

    def __init__(self, docs_dir: str = "docs"):
        self.docs_dir = docs_dir
        if not os.path.exists(self.docs_dir):
            os.makedirs(self.docs_dir)

    def generate(self, entries: list, exits: list, market_health: dict, analytics: dict = None, portfolio: dict = None) -> str:
        """Generates the index.html file."""
        html_path = os.path.join(self.docs_dir, "index.html")

        if analytics is None:
            analytics = {"total_trades": 0, "win_rate": 0.0, "avg_profit_pct": 0.0, "active_history": []}
        if portfolio is None:
            portfolio = {}

        # Prepare cards HTML
        entry_cards_html = self._generate_cards(entries, is_entry=True)
        exit_cards_html = self._generate_cards(exits, is_entry=False)
        history_cards_html = self._generate_history_cards(analytics.get('active_history', []))
        portfolio_cards_html = self._generate_portfolio_cards(portfolio)
        
        market_status = market_health.get('status', 'UNKNOWN')
        nifty_price = market_health.get('nifty_price', 0)
        sma = market_health.get('nifty_50_sma', 0)

        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>NSE Stock Screener Dashboard</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap" rel="stylesheet">
    <style>
        body {{ font-family: 'Inter', sans-serif; background-color: #0f172a; color: #e2e8f0; overflow-y: scroll; }}
        .glass {{ background: rgba(30, 41, 59, 0.7); backdrop-filter: blur(12px); border: 1px solid rgba(255, 255, 255, 0.1); }}
        .card-hover {{ transition: transform 0.2s, box-shadow 0.2s; }}
        .card-hover:hover {{ transform: translateY(-5px); box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.5); }}
    </style>
</head>
<body class="min-h-screen p-4 md:p-8 pb-20">

    <div class="max-w-7xl mx-auto">
        <!-- Header & Market Health -->
        <header class="glass rounded-2xl p-6 mb-6 flex flex-col md:flex-row justify-between items-center shadow-lg">
            <div>
                <h1 class="text-3xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-blue-400 to-emerald-400">NSE Automated Screener</h1>
                <p class="text-slate-400 mt-1">Last Updated: {datetime.now().strftime('%Y-%m-%d %H:%M IST')}</p>
            </div>
            <div class="mt-4 md:mt-0 text-center md:text-right">
                <div class="text-sm text-slate-400 uppercase tracking-wider font-semibold">Market Health</div>
                <div class="text-2xl font-bold {'text-emerald-400' if 'BULLISH' in market_status else 'text-red-400'}">{market_status}</div>
                <div class="text-sm text-slate-300">Nifty: {nifty_price:,.2f} | 50-SMA: {sma:,.2f}</div>
            </div>
        </header>
        
        <!-- Paper Trading Analytics Banner -->
        <div class="glass rounded-xl p-5 mb-8 flex justify-around items-center text-center border-l-4 border-l-blue-500 shadow-md">
            <div>
                <div class="text-xs text-slate-400 uppercase font-semibold">Total AI Picks</div>
                <div class="text-2xl font-bold text-white mt-1">{analytics['total_trades']}</div>
            </div>
            <div class="w-px h-10 bg-slate-700"></div>
            <div>
                <div class="text-xs text-slate-400 uppercase font-semibold">Historical Win Rate</div>
                <div class="text-2xl font-bold text-emerald-400 mt-1">{analytics['win_rate']:.1f}%</div>
            </div>
            <div class="w-px h-10 bg-slate-700"></div>
            <div>
                <div class="text-xs text-slate-400 uppercase font-semibold">Average P&L</div>
                <div class="text-2xl font-bold {'text-emerald-400' if analytics['avg_profit_pct'] >= 0 else 'text-red-400'} mt-1">{analytics['avg_profit_pct']:.2f}%</div>
            </div>
        </div>

        <!-- Controls -->
        <div class="flex flex-col md:flex-row justify-between items-center mb-6 gap-4">
            <h2 class="text-2xl font-semibold">Actionable Candidates</h2>
            <div class="flex gap-2 items-center bg-slate-800 p-1 rounded-lg">
                <span class="px-3 text-sm text-slate-400">Sort by:</span>
                <select id="sortSelect" class="bg-slate-700 text-white text-sm rounded px-3 py-2 outline-none cursor-pointer border border-slate-600 focus:border-blue-500 transition-colors" onchange="sortCards()">
                    <option value="adx_desc">Trend Strength (ADX High to Low)</option>
                    <option value="rsi_desc">Momentum (RSI High to Low)</option>
                    <option value="rsi_asc">Momentum (RSI Low to High)</option>
                    <option value="price_desc">Price (High to Low)</option>
                    <option value="price_asc">Price (Low to High)</option>
                    <option value="pnl_desc">P&L (High to Low)</option>
                    <option value="date_desc">Date (Newest to Oldest)</option>
                </select>
            </div>
        </div>

        <!-- Tabs -->
        <div class="flex overflow-x-auto border-b border-slate-700 mb-6 pb-1 custom-scrollbar">
            <button id="tab-entries" class="px-5 py-3 whitespace-nowrap font-semibold text-emerald-400 border-b-2 border-emerald-400 transition-colors" onclick="switchTab('entries')">Entry Candidates ({len(entries)})</button>
            <button id="tab-exits" class="px-5 py-3 whitespace-nowrap font-semibold text-slate-400 border-b-2 border-transparent hover:text-red-400 transition-colors" onclick="switchTab('exits')">Caution / Exits ({len(exits)})</button>
            <button id="tab-portfolio" class="px-5 py-3 whitespace-nowrap font-semibold text-slate-400 border-b-2 border-transparent hover:text-blue-400 transition-colors" onclick="switchTab('portfolio')">Active Portfolio ({len(portfolio)})</button>
            <button id="tab-history" class="px-5 py-3 whitespace-nowrap font-semibold text-slate-400 border-b-2 border-transparent hover:text-purple-400 transition-colors" onclick="switchTab('history')">AI Pick History ({len(analytics.get('active_history', []))})</button>
        </div>

        <!-- Grid Containers -->
        <div id="grid-entries" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {entry_cards_html}
        </div>
        
        <div id="grid-exits" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 hidden">
            {exit_cards_html}
        </div>
        
        <div id="grid-portfolio" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 hidden">
            {portfolio_cards_html}
        </div>
        
        <div id="grid-history" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 hidden">
            {history_cards_html}
        </div>
        
    </div>

    <style>
        .custom-scrollbar::-webkit-scrollbar {{ height: 6px; }}
        .custom-scrollbar::-webkit-scrollbar-track {{ background: #1e293b; border-radius: 4px; }}
        .custom-scrollbar::-webkit-scrollbar-thumb {{ background: #475569; border-radius: 4px; }}
    </style>

    <script>
        function switchTab(tab) {{
            const tabs = ['entries', 'exits', 'portfolio', 'history'];
            
            tabs.forEach(t => {{
                document.getElementById('grid-' + t).classList.add('hidden');
                
                let btn = document.getElementById('tab-' + t);
                btn.className = "px-5 py-3 whitespace-nowrap font-semibold text-slate-400 border-b-2 border-transparent transition-colors";
                
                if (t === 'entries') btn.classList.add('hover:text-emerald-400');
                if (t === 'exits') btn.classList.add('hover:text-red-400');
                if (t === 'portfolio') btn.classList.add('hover:text-blue-400');
                if (t === 'history') btn.classList.add('hover:text-purple-400');
            }});
            
            document.getElementById('grid-' + tab).classList.remove('hidden');
            
            let activeBtn = document.getElementById('tab-' + tab);
            activeBtn.className = "px-5 py-3 whitespace-nowrap font-semibold transition-colors border-b-2";
            
            if (tab === 'entries') activeBtn.classList.add('text-emerald-400', 'border-emerald-400');
            if (tab === 'exits') activeBtn.classList.add('text-red-400', 'border-red-400');
            if (tab === 'portfolio') activeBtn.classList.add('text-blue-400', 'border-blue-400');
            if (tab === 'history') activeBtn.classList.add('text-purple-400', 'border-purple-400');
            
            sortCards(); 
        }}

        function sortCards() {{
            const select = document.getElementById('sortSelect').value;
            const [key, direction] = select.split('_');
            
            const tabs = ['entries', 'exits', 'history']; // Portfolio is generally unsorted or sorted by date
            
            tabs.forEach(tab => {{
                const grid = document.getElementById('grid-' + tab);
                if (!grid) return;
                
                const cards = Array.from(grid.getElementsByClassName('stock-card'));
                
                cards.sort((a, b) => {{
                    let valA = parseFloat(a.getAttribute('data-' + key)) || 0;
                    let valB = parseFloat(b.getAttribute('data-' + key)) || 0;
                    
                    if (direction === 'desc') return valB - valA;
                    return valA - valB;
                }});
                
                cards.forEach(card => grid.appendChild(card));
            }});
        }}
        
        sortCards();
    </script>
</body>
</html>"""

        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        
        return html_path

    def _generate_cards(self, items: list, is_entry: bool) -> str:
        if not items:
            return f"""<div class="col-span-full glass rounded-xl p-8 text-center text-slate-400">
                <p>No candidates found matching criteria in this scan.</p>
            </div>"""

        html = ""
        badge_color = "bg-emerald-500/20 text-emerald-400 border-emerald-500/30" if is_entry else "bg-red-500/20 text-red-400 border-red-500/30"
        status_text = "BUY SETUP" if is_entry else "CAUTION / EXIT"

        for item in items:
            d = item['data']
            sym = d.get('symbol', 'UNKNOWN')
            price = d.get('price', 0)
            rsi = d.get('rsi', 0)
            adx = d.get('adx', 0)
            sl = d.get('stop_loss', 0)
            slope = d.get('slope', 0)
            
            ai_text = item.get('ai', {}).get('ai_summary', 'No summary available.')
            tv_rec = item.get('sentiment', {}).get('technical', {}).get('recommendation', 'UNKNOWN')
            
            sector = d.get('sector', 'Unknown')
            sector_boost = d.get('sector_boost', False)
            sector_badge = f'<span class="px-2 py-1 text-xs font-bold rounded border bg-orange-500/20 text-orange-400 border-orange-500/30 shadow-[0_0_10px_rgba(249,115,22,0.3)] ml-2" title="{sector}">🔥 HOT SECTOR</span>' if sector_boost else ''

            html += f"""
            <div class="stock-card glass rounded-xl p-5 flex flex-col card-hover border-t-4 {'border-t-emerald-500' if is_entry else 'border-t-red-500'}" 
                 data-rsi="{rsi}" data-adx="{adx}" data-price="{price}" data-slope="{slope}" data-pnl="0" data-date="0">
                <div class="flex justify-between items-start mb-3">
                    <div>
                        <h3 class="text-xl font-bold text-white tracking-wide">{sym}{sector_badge}</h3>
                        <div class="text-slate-300 font-mono text-lg mt-1">₹{price:,.2f}</div>
                    </div>
                    <span class="px-2 py-1 text-xs font-bold rounded border {badge_color}">{status_text}</span>
                </div>
                
                <div class="grid grid-cols-2 gap-3 mb-4 text-sm bg-slate-800/50 p-3 rounded-lg border border-slate-700">
                    <div><span class="text-slate-400 block text-xs uppercase">RSI (14)</span><span class="font-semibold text-white">{rsi:.1f}</span></div>
                    <div><span class="text-slate-400 block text-xs uppercase">ADX (14)</span><span class="font-semibold text-white">{adx:.1f}</span></div>
                    <div><span class="text-slate-400 block text-xs uppercase">Stop Loss</span><span class="font-semibold text-orange-400">₹{sl:,.2f}</span></div>
                    <div><span class="text-slate-400 block text-xs uppercase">TV Signal</span><span class="font-semibold text-blue-400">{tv_rec}</span></div>
                </div>
                
                <div class="flex-grow">
                    <p class="text-slate-300 text-sm leading-relaxed border-l-2 border-slate-600 pl-3 italic">
                        "{ai_text}"
                    </p>
                </div>
                
                <div class="mt-4 pt-4 border-t border-slate-700/50 flex justify-between items-center text-xs text-slate-500 font-mono">
                    <span>Slope: {slope:.3f}</span>
                    <a href="https://in.tradingview.com/chart/?symbol=NSE:{sym}" target="_blank" class="text-blue-400 hover:text-blue-300 transition-colors flex items-center gap-1">
                        View Chart ↗
                    </a>
                </div>
            </div>
            """
        return html

    def _generate_history_cards(self, history: list) -> str:
        if not history:
            return f"""<div class="col-span-full glass rounded-xl p-8 text-center text-slate-400">
                <p>No historical recommendations found yet.</p>
            </div>"""

        html = ""
        for idx, item in enumerate(history):
            sym = item.get('symbol', 'UNKNOWN')
            date_str = item.get('date', 'Unknown')
            entry = item.get('entry_price', 0)
            current = item.get('current_price', 0)
            pnl_pct = item.get('pnl_pct', 0)
            ai_text = item.get('ai_summary', '')
            
            pnl_color = "text-emerald-400" if pnl_pct >= 0 else "text-red-400"
            border_color = "border-t-purple-500"
            
            # Simple timestamp for sorting
            ts = 0
            if date_str != 'Unknown':
                try: ts = datetime.strptime(date_str, "%Y-%m-%d").timestamp()
                except: pass

            html += f"""
            <div class="stock-card glass rounded-xl p-5 flex flex-col card-hover border-t-4 {border_color}" 
                 data-pnl="{pnl_pct}" data-date="{ts}" data-price="{current}" data-rsi="0" data-adx="0">
                <div class="flex justify-between items-start mb-3">
                    <div>
                        <h3 class="text-xl font-bold text-white tracking-wide">{sym}</h3>
                        <div class="text-slate-400 text-xs mt-1">Recommended: {date_str}</div>
                    </div>
                    <div class="text-right">
                        <div class="text-xs text-slate-400 uppercase">P&L</div>
                        <div class="font-bold text-lg {pnl_color}">{pnl_pct:+.1f}%</div>
                    </div>
                </div>
                
                <div class="grid grid-cols-2 gap-3 mb-4 text-sm bg-slate-800/50 p-3 rounded-lg border border-slate-700">
                    <div><span class="text-slate-400 block text-xs uppercase">Entry Price</span><span class="font-semibold text-white">₹{entry:,.2f}</span></div>
                    <div><span class="text-slate-400 block text-xs uppercase">Current Price</span><span class="font-semibold text-white">₹{current:,.2f}</span></div>
                </div>
                
                <div class="flex-grow">
                    <p class="text-slate-400 text-xs leading-relaxed border-l-2 border-slate-700 pl-3 italic line-clamp-3" title="{ai_text}">
                        "{ai_text}"
                    </p>
                </div>
                
                <div class="mt-4 pt-4 border-t border-slate-700/50 flex justify-end items-center text-xs">
                    <a href="https://in.tradingview.com/chart/?symbol=NSE:{sym}" target="_blank" class="text-blue-400 hover:text-blue-300 transition-colors flex items-center gap-1">
                        View Chart ↗
                    </a>
                </div>
            </div>
            """
        return html

    def _generate_portfolio_cards(self, portfolio: dict) -> str:
        if not portfolio:
            return f"""<div class="col-span-full glass rounded-xl p-8 text-center text-slate-400">
                <p>Your portfolio is currently empty.</p>
            </div>"""

        html = ""
        for sym, data in portfolio.items():
            entry = data.get('entry_price', 0)
            qty = data.get('quantity', 0)
            sl = data.get('stop_loss', 0)
            
            html += f"""
            <div class="glass rounded-xl p-5 flex flex-col border-t-4 border-t-blue-500">
                <div class="flex justify-between items-start mb-3">
                    <div>
                        <h3 class="text-xl font-bold text-white tracking-wide">{sym}</h3>
                        <div class="text-slate-300 font-mono text-lg mt-1">{qty} Shares</div>
                    </div>
                    <span class="px-2 py-1 text-xs font-bold rounded border bg-blue-500/20 text-blue-400 border-blue-500/30">HOLDING</span>
                </div>
                
                <div class="grid grid-cols-2 gap-3 mb-2 text-sm bg-slate-800/50 p-3 rounded-lg border border-slate-700">
                    <div><span class="text-slate-400 block text-xs uppercase">Avg Price</span><span class="font-semibold text-white">₹{entry:,.2f}</span></div>
                    <div><span class="text-slate-400 block text-xs uppercase">Stop Loss</span><span class="font-semibold text-orange-400">₹{sl:,.2f}</span></div>
                </div>
                
                <div class="mt-4 pt-4 border-t border-slate-700/50 flex justify-end items-center text-xs">
                    <a href="https://in.tradingview.com/chart/?symbol=NSE:{sym}" target="_blank" class="text-blue-400 hover:text-blue-300 transition-colors flex items-center gap-1">
                        View Chart ↗
                    </a>
                </div>
            </div>
            """
        return html
