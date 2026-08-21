"""
sector_analysis.py
------------------
Caches sector information for stocks and determines sector strength.
To avoid 5000+ API calls, it only fetches sector info for stocks that 
survive the initial filters, caching them in symbol_to_sector.json.
"""

import os
import json
import yfinance as yf
from collections import defaultdict


class SectorAnalyzer:
    """Ranks market sectors based on the momentum of their top stocks."""

    def __init__(self):
        self.cache_file = os.path.join(os.path.dirname(__file__), "symbol_to_sector.json")
        self.sector_map = {}
        self.load_cache()

    def load_cache(self):
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    self.sector_map = json.load(f)
            except Exception as e:
                print(f"[warn] Failed to load sector cache: {e}")
                self.sector_map = {}

    def save_cache(self):
        try:
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(self.sector_map, f, indent=4)
        except Exception as e:
            print(f"[warn] Failed to save sector cache: {e}")

    def get_sector(self, symbol: str) -> str:
        """Get sector for a symbol, fetching from yfinance if not cached."""
        if symbol in self.sector_map:
            return self.sector_map[symbol]

        yf_symbol = symbol if symbol.endswith(".NS") else f"{symbol}.NS"
        try:
            ticker = yf.Ticker(yf_symbol)
            info = ticker.info
            sector = info.get("sector", "Unknown")
            self.sector_map[symbol] = sector
            return sector
        except Exception as e:
            # If error (e.g. rate limit), return Unknown but don't cache it
            print(f"[debug] Failed to fetch sector for {symbol}: {e}")
            return "Unknown"

    def rank_sectors(self, filtered_results: list[dict]) -> dict:
        """
        Ranks sectors based on the stocks that passed the uptrend filters.
        Returns a dictionary mapping sector name to its strength score.
        """
        print("[info] Calculating sector strength...")
        
        sector_scores = defaultdict(list)
        
        cache_updated = False
        for item in filtered_results:
            symbol = item["symbol"]
            slope = item["slope"]
            
            if symbol not in self.sector_map:
                sector = self.get_sector(symbol)
                if sector != "Unknown":
                    self.sector_map[symbol] = sector
                    cache_updated = True
            else:
                sector = self.sector_map[symbol]
                
            if sector != "Unknown":
                sector_scores[sector].append(slope)

        if cache_updated:
            self.save_cache()

        # Calculate average slope per sector. 
        # Add a small bonus for sectors that have MORE stocks breaking out.
        sector_ranking = {}
        for sector, slopes in sector_scores.items():
            avg_slope = sum(slopes) / len(slopes)
            count_bonus = len(slopes) * 0.05  # Arbitrary weight for breadth
            sector_ranking[sector] = avg_slope + count_bonus

        # Sort sectors by highest score
        sorted_sectors = dict(sorted(sector_ranking.items(), key=lambda item: item[1], reverse=True))
        
        # Keep top 3 as the "Strongest Sectors"
        top_sectors = list(sorted_sectors.keys())[:3]
        
        return {
            "rankings": sorted_sectors,
            "top_sectors": top_sectors
        }
