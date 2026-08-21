"""
ai_summarizer.py
----------------
Generates concise entry/exit reasoning using various AI APIs.
Implements a cascading fallback: Gemini -> Groq -> OpenAI -> Anthropic.

Optimized for free tiers by batching multiple stocks into a single API call.
"""

import google.generativeai as genai
import time
import re
from typing import Dict, List, Optional
from openai import OpenAI
from anthropic import Anthropic


class AISummarizer:
    """Uses various AI APIs to summarize stock sentiment and provide reasoning.
    
    Supports both single-stock and batch summarization. Batch mode is
    strongly recommended to stay within free-tier quotas.
    """

    # How many stocks to pack into one AI request
    BATCH_SIZE = 5

    def __init__(self, gemini_api_key: str = "", groq_api_key: str = "", openai_api_key: str = "", anthropic_api_key: str = ""):
        self.gemini_key = gemini_api_key
        self.groq_key = groq_api_key
        self.openai_key = openai_api_key
        self.anthropic_key = anthropic_api_key

        if self.gemini_key:
            genai.configure(api_key=self.gemini_key)
        self.gemini_model = genai.GenerativeModel("gemini-3.6-flash")

        self.is_configured = any([self.gemini_key, self.groq_key, self.openai_key, self.anthropic_key])

    # ------------------------------------------------------------------
    # Batch summarization (recommended)
    # ------------------------------------------------------------------

    def generate_batch_summaries(self, stocks_with_sentiment: List[dict]) -> dict:
        """Generates AI summaries for multiple stocks in batched API calls."""
        if not self.is_configured:
            return {
                item["data"].get("symbol", "?"): "AI unavailable (no API keys configured)."
                for item in stocks_with_sentiment
            }

        results = {}

        # Process in batches
        for i in range(0, len(stocks_with_sentiment), self.BATCH_SIZE):
            batch = stocks_with_sentiment[i : i + self.BATCH_SIZE]
            batch_results = self._call_batch(batch)
            results.update(batch_results)

        return results

    def _build_prompt(self, batch: List[dict]) -> str:
        prompt_parts = [
            "You are an expert Indian stock market analyst.",
            "For EACH of the following stocks, write a VERY CONCISE 2-sentence",
            "actionable summary (Entry reasoning if bullish, Caution reasoning if",
            "there are red flags). Keep it plain text, no markdown.\n",
        ]

        for idx, item in enumerate(batch, 1):
            d = item["data"]
            s = item.get("sentiment", {})
            tv = s.get("technical", {}).get("recommendation", "UNKNOWN")
            prompt_parts.append(
                f"Stock {idx}: {d.get('symbol','?')} | Price: {d.get('price',0)} | "
                f"SL: {d.get('stop_loss',0)} | RSI: {d.get('rsi',0)} | "
                f"ADX: {d.get('adx',0)} | Volume Ratio: {d.get('volume_ratio',0)} | "
                f"TV Signal: {tv}"
            )

        prompt_parts.append(
            "\nRespond with exactly one summary per stock, each on its own line,"
            " prefixed with the stock symbol and a colon. Example:\n"
            "RELIANCE: Strong bullish entry backed by momentum...\n"
            "TCS: Caution, RSI is elevated and volume is weak..."
        )

        return "\n".join(prompt_parts)

    def _call_batch(self, batch: List[dict]) -> dict:
        """Sends a single API request covering multiple stocks using a fallback chain."""
        prompt = self._build_prompt(batch)

        # 1. Try Gemini
        if self.gemini_key:
            try:
                time.sleep(3)  # basic rate-limit politeness
                response = self.gemini_model.generate_content(prompt)
                return self._parse_batch_response(response.text.strip(), batch)
            except Exception as e:
                print(f"[warn] Gemini failed: {e}. Falling back...")

        # 2. Try Groq
        if self.groq_key:
            try:
                client = OpenAI(api_key=self.groq_key, base_url="https://api.groq.com/openai/v1")
                response = client.chat.completions.create(
                    model="groq/compound",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3
                )
                return self._parse_batch_response(response.choices[0].message.content.strip(), batch)
            except Exception as e:
                print(f"[warn] Groq failed: {e}. Falling back...")

        # 3. Try OpenAI (GPT-4o-mini)
        if self.openai_key:
            try:
                client = OpenAI(api_key=self.openai_key)
                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3
                )
                return self._parse_batch_response(response.choices[0].message.content.strip(), batch)
            except Exception as e:
                print(f"[warn] OpenAI failed: {e}. Falling back...")

        # 4. Try Anthropic (Claude 3 Haiku)
        if self.anthropic_key:
            try:
                client = Anthropic(api_key=self.anthropic_key)
                response = client.messages.create(
                    model="claude-3-haiku-20240307",
                    max_tokens=1024,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3
                )
                return self._parse_batch_response(response.content[0].text.strip(), batch)
            except Exception as e:
                print(f"[warn] Anthropic failed: {e}. Falling back...")

        # 5. Final fallback if all fail
        return {
            item["data"].get("symbol", "?"): "AI summary unavailable (all providers failed or exhausted rate limits)."
            for item in batch
        }

    def _parse_batch_response(self, text: str, batch: List[dict]) -> dict:
        """Parses the multi-stock response into a dict of symbol -> summary."""
        symbols = [item["data"].get("symbol", "?") for item in batch]
        results = {}

        # Try to match "SYMBOL: summary text" lines
        for sym in symbols:
            pattern = re.compile(rf"^{re.escape(sym)}\s*:\s*(.+)", re.MULTILINE | re.IGNORECASE)
            match = pattern.search(text)
            if match:
                results[sym] = match.group(1).strip()
            else:
                results[sym] = "Summary available (see batch block)."

        # If regex missed something, try to ensure every symbol has something
        for sym in symbols:
            if sym not in results:
                results[sym] = "Could not parse AI response."

        return results

    # ------------------------------------------------------------------
    # Single-stock summarization (legacy)
    # ------------------------------------------------------------------

    def generate_summary(self, stock_data: dict, sentiment_report: dict) -> dict:
        """Legacy single-stock method. Wraps the batch method for convenience."""
        batch = [{"data": stock_data, "sentiment": sentiment_report}]
        results = self.generate_batch_summaries(batch)
        sym = stock_data.get("symbol", "?")
        return {
            "ai_summary": results.get(sym, "AI error."),
            "raw_news": sentiment_report.get("news", [])
        }
