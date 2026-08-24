import os
import json
from datetime import datetime

class DashboardGenerator:
    """Generates a static HTML dashboard from the latest scan results."""

    def __init__(self, docs_dir: str = "../docs"):
        self.docs_dir = docs_dir
        if not os.path.exists(self.docs_dir):
            os.makedirs(self.docs_dir)

    def generate(self, entries: list, exits: list, market_health: dict) -> str:
        """Generates the index.html file."""
        html_path = os.path.join(self.docs_dir, "index.html")

        # Prepare cards HTML
        entry_cards_html = self._generate_cards(entries, is_entry=True)
        exit_cards_html = self._generate_cards(exits, is_entry=False)
        
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
        body {{ font-family: 'Inter', sans-serif; background-color: #0f172a; color: #e2e8f0; }}
        .glass {{ background: rgba(30, 41, 59, 0.7); backdrop-filter: blur(12px); border: 1px solid rgba(255, 255, 255, 0.1); }}
        .card-hover {{ transition: transform 0.2s, box-shadow 0.2s; }}
        .card-hover:hover {{ transform: translateY(-5px); box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.5); }}
    </style>
</head>
<body class="min-h-screen p-4 md:p-8">

    <div class="max-w-7xl mx-auto">
        <!-- Header & Market Health -->
        <header class="glass rounded-2xl p-6 mb-8 flex flex-col md:flex-row justify-between items-center shadow-lg">
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
                </select>
            </div>
        </div>

        <!-- Tabs -->
        <div class="flex border-b border-slate-700 mb-6">
            <button id="tab-entries" class="px-6 py-3 font-semibold text-emerald-400 border-b-2 border-emerald-400 transition-colors" onclick="switchTab('entries')">Entry Candidates ({len(entries)})</button>
            <button id="tab-exits" class="px-6 py-3 font-semibold text-slate-400 border-b-2 border-transparent hover:text-red-400 transition-colors" onclick="switchTab('exits')">Caution / Exits ({len(exits)})</button>
        </div>

        <!-- Grid Container -->
        <div id="grid-entries" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {entry_cards_html}
        </div>
        
        <div id="grid-exits" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 hidden">
            {exit_cards_html}
        </div>
        
    </div>

    <script>
        function switchTab(tab) {{
            document.getElementById('grid-entries').classList.add('hidden');
            document.getElementById('grid-exits').classList.add('hidden');
            
            document.getElementById('tab-entries').className = "px-6 py-3 font-semibold text-slate-400 border-b-2 border-transparent hover:text-emerald-400 transition-colors";
            document.getElementById('tab-exits').className = "px-6 py-3 font-semibold text-slate-400 border-b-2 border-transparent hover:text-red-400 transition-colors";
            
            document.getElementById('grid-' + tab).classList.remove('hidden');
            if(tab === 'entries') {{
                document.getElementById('tab-entries').className = "px-6 py-3 font-semibold text-emerald-400 border-b-2 border-emerald-400 transition-colors";
            }} else {{
                document.getElementById('tab-exits').className = "px-6 py-3 font-semibold text-red-400 border-b-2 border-red-400 transition-colors";
            }}
            sortCards(); // re-sort visible grid
        }}

        function sortCards() {{
            const select = document.getElementById('sortSelect').value;
            const [key, direction] = select.split('_');
            
            ['entries', 'exits'].forEach(tab => {{
                const grid = document.getElementById('grid-' + tab);
                const cards = Array.from(grid.getElementsByClassName('stock-card'));
                
                cards.sort((a, b) => {{
                    let valA = parseFloat(a.getAttribute('data-' + key));
                    let valB = parseFloat(b.getAttribute('data-' + key));
                    
                    if (direction === 'desc') return valB - valA;
                    return valA - valB;
                }});
                
                cards.forEach(card => grid.appendChild(card));
            }});
        }}
        
        // Initial sort
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

            html += f"""
            <div class="stock-card glass rounded-xl p-5 flex flex-col card-hover border-t-4 {'border-t-emerald-500' if is_entry else 'border-t-red-500'}" 
                 data-rsi="{rsi}" data-adx="{adx}" data-price="{price}" data-slope="{slope}">
                <div class="flex justify-between items-start mb-3">
                    <div>
                        <h3 class="text-xl font-bold text-white tracking-wide">{sym}</h3>
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
