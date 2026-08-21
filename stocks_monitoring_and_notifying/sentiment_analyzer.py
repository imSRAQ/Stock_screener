"""
sentiment_analyzer.py
---------------------
Analyzes the market sentiment for a given list of stocks using a dual-thread approach:
1. Technical Sentiment (tradingview-ta): Fetches RECOMMENDATION.
2. News Sentiment (yfinance): Fetches the latest news headlines.
"""

import threading
import yfinance as yf
from tradingview_ta import TA_Handler, Interval, Exchange

class SentimentAnalyzer:
    """Fetches technical and news sentiment for stocks in parallel."""

    def __init__(self):
        pass

    def _fetch_technical_sentiment(self, symbol: str, result_dict: dict):
        """Fetches TradingView technical recommendation."""
        # Convert NSE symbol to TradingView format
        tv_symbol = symbol
        if tv_symbol.endswith(".NS"):
            tv_symbol = tv_symbol[:-3]

        try:
            handler = TA_Handler(
                symbol=tv_symbol,
                screener="india",
                exchange="NSE",
                interval=Interval.INTERVAL_1_DAY
            )
            analysis = handler.get_analysis()
            result_dict["technical"] = {
                "recommendation": analysis.summary.get("RECOMMENDATION", "UNKNOWN"),
                "buy": analysis.summary.get("BUY", 0),
                "sell": analysis.summary.get("SELL", 0),
                "neutral": analysis.summary.get("NEUTRAL", 0)
            }
        except Exception as e:
            result_dict["technical"] = {"error": str(e), "recommendation": "UNKNOWN"}

    def _fetch_news_sentiment(self, symbol: str, result_dict: dict):
        """Fetches latest news headlines from Yahoo Finance."""
        yf_symbol = symbol if symbol.endswith(".NS") else f"{symbol}.NS"
        try:
            ticker = yf.Ticker(yf_symbol)
            news = ticker.news
            headlines = []
            if news:
                # Extract top 3 headlines
                for item in news[:3]:
                    title = item.get("title", "")
                    if title:
                        headlines.append(title)
            result_dict["news"] = headlines
        except Exception as e:
            result_dict["news"] = []
            result_dict["news_error"] = str(e)

    def analyze(self, symbol: str) -> dict:
        """Analyzes sentiment for a single stock using threads.
        
        Returns:
            dict containing "technical" and "news" data.
        """
        result = {}
        
        t1 = threading.Thread(target=self._fetch_technical_sentiment, args=(symbol, result))
        t2 = threading.Thread(target=self._fetch_news_sentiment, args=(symbol, result))
        
        t1.start()
        t2.start()
        
        t1.join()
        t2.join()
        
        return result

    def analyze_batch(self, symbols: list[str]) -> dict:
        """Analyzes sentiment for a list of stocks.
        
        Returns:
            dict mapping symbols to their sentiment reports.
        """
        batch_results = {}
        threads = []
        
        def worker(sym):
            batch_results[sym] = self.analyze(sym)

        for symbol in symbols:
            t = threading.Thread(target=worker, args=(symbol,))
            threads.append(t)
            t.start()
            
        for t in threads:
            t.join()
            
        return batch_results
