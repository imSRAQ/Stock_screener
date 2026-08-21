"""
ai_summarizer.py
----------------
Generates concise entry/exit reasoning using the Google Gemini Flash API.
It processes technical and news sentiment data to provide actionable insights.
"""

# import google.generativeai as genai
import google.generativeai as genai

# Some versions of the library expose configure(), others require passing the key
# directly to the model.  We attempt configure() first; if it does not exist we
# simply skip it – the model constructor will still work when the key is
# supplied later via `genai.GenerativeModel(..., api_key=…)`.
try:
    genai.configure  # attribute check
except AttributeError:
    # Newer google-genai package does not have configure; we'll handle the key
    # later when creating the model.
    pass

import time
from typing import Dict, Optional

class AISummarizer:
    """Uses Gemini API to summarize stock sentiment and provide reasoning."""

    def __init__(self, api_key: str):
        if api_key:
            genai.configure(api_key=api_key)
        # Use gemini-3.6-flash (confirmed available via test_ai.py)
        self.model = genai.GenerativeModel("gemini-3.6-flash")
        self.is_configured = bool(api_key)

    def generate_summary(self, stock_data: dict, sentiment_report: dict) -> dict:
        """Generates AI reasoning for a given stock.

        Args:
            stock_data: dict with price, stop_loss, rsi, adx, slope, etc.
            sentiment_report: dict with 'technical' and 'news' keys.

        Returns:
            dict containing:
            - 'ai_summary': The generated text.
            - 'raw_news': List of news headlines.
        """
        raw_news = sentiment_report.get("news", [])
        
        if not self.is_configured:
            return {
                "ai_summary": "AI summary unavailable (Gemini API key not configured).",
                "raw_news": raw_news
            }

        symbol = stock_data.get("symbol", "UNKNOWN")
        price = stock_data.get("price", 0)
        stop_loss = stock_data.get("stop_loss", 0)
        
        technical = sentiment_report.get("technical", {})
        recommendation = technical.get("recommendation", "UNKNOWN")
        
        news_text = "\n- ".join(raw_news) if raw_news else "No recent news available."

        prompt = f"""
        You are an expert stock market analyst. Analyze the following data for NSE stock {symbol}.

        Current Price: {price}
        Stop Loss Level: {stop_loss}
        Trend Slope: {stock_data.get('slope', 0)}
        RSI(14): {stock_data.get('rsi', 0)}
        ADX(14): {stock_data.get('adx', 0)}
        Volume Ratio: {stock_data.get('volume_ratio', 0)}
        
        TradingView Technical Signal: {recommendation}

        Latest News Headlines:
        - {news_text}

        Based on this data, provide a VERY CONCISE, actionable reasoning summary.
        - If the setup is bullish (good entry), write 2-3 sentences of Entry reasoning, mentioning the stop-loss level.
        - If there are red flags (bearish news, overbought RSI, weak TV signal), write 1-2 sentences of Exit/caution reasoning.
        Do not use markdown formatting like bolding in the output. Keep it plain text.
        """

        try:
            # Add a small delay to respect free tier rate limits (15 req/min)
            time.sleep(2) 
            response = self.model.generate_content(prompt)
            summary = response.text.strip()
        except Exception as e:
            summary = f"Error generating summary: {str(e)}"

        return {
            "ai_summary": summary,
            "raw_news": raw_news
        }
