"""
ai_summarizer.py
----------------
Generates concise "why it qualified" summaries for reversal strategy candidates.

Cascade: Gemini → Groq → OpenAI → Anthropic (same pattern as existing system).
Batch mode packs multiple stocks into one API call to stay within free-tier quotas.

Strategy: Multi-Timeframe RSI Reversal
"""

import time
import re
from typing import Dict, List, Optional


class AISummarizer:
    """Uses AI APIs to explain why a stock qualifies for the RSI Reversal strategy."""

    BATCH_SIZE = 5   # Stocks per API call — 5 stocks × 3 calls = 15 stocks/day on free tier

    def __init__(
        self,
        gemini_api_key: str = "",
        groq_api_key: str = "",
        openai_api_key: str = "",
        anthropic_api_key: str = "",
    ):
        self.gemini_key    = gemini_api_key
        self.groq_key      = groq_api_key
        self.openai_key    = openai_api_key
        self.anthropic_key = anthropic_api_key
        self.is_configured = any([gemini_api_key, groq_api_key, openai_api_key, anthropic_api_key])

        if self.gemini_key:
            try:
                import google.generativeai as genai
                genai.configure(api_key=self.gemini_key)
                self._gemini_model = genai.GenerativeModel("gemini-2.0-flash")
            except Exception:
                self._gemini_model = None
        else:
            self._gemini_model = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_batch_summaries(self, candidates: list[dict]) -> dict[str, str]:
        """Generate AI summaries for multiple candidates.

        Parameters
        ----------
        candidates : list[dict]
            List of reversal analyzer output dicts (each has symbol, rsi_*, etc.)

        Returns
        -------
        dict mapping symbol → summary_string
        """
        if not self.is_configured:
            return {
                c["symbol"]: "AI unavailable (no API keys configured)."
                for c in candidates
            }

        results: dict[str, str] = {}

        for i in range(0, len(candidates), self.BATCH_SIZE):
            batch = candidates[i: i + self.BATCH_SIZE]
            batch_results = self._call_batch(batch)
            results.update(batch_results)
            if i + self.BATCH_SIZE < len(candidates):
                time.sleep(2)   # respect rate limits

        return results

    def generate_single(self, candidate: dict) -> str:
        """Generate a summary for a single candidate (used by /revchart command)."""
        results = self.generate_batch_summaries([candidate])
        return results.get(candidate["symbol"], self._fallback_summary(candidate))

    # ------------------------------------------------------------------
    # Batch prompt construction
    # ------------------------------------------------------------------

    def _build_batch_prompt(self, candidates: list[dict]) -> str:
        lines = [
            "You are a concise technical analyst. For each stock below, write exactly 2 sentences "
            "explaining why it qualifies for the Multi-Timeframe RSI Reversal strategy. "
            "Focus on the RSI readings, signal candle, and setup quality. "
            "Be specific — mention the RSI values and pattern name. "
            "Use plain English, no bullet points.\n\n"
            "Format your response as:\n"
            "SYMBOL: <2-sentence explanation>\n\n"
            "Stocks to analyse:\n"
        ]
        for c in candidates:
            lines.append(
                f"- {c['symbol']}: Monthly RSI={c.get('rsi_monthly', '?')}, "
                f"Weekly RSI={c.get('rsi_weekly', '?')}, "
                f"Daily RSI={c.get('rsi_daily', '?')} (pullback zone), "
                f"Signal candle: {c.get('signal_candle_pattern', '?')} on {c.get('signal_candle_date', '?')}, "
                f"Reason: {c.get('signal_candle_reason', '?')}, "
                f"Entry above ₹{c.get('entry', '?')}, SL ₹{c.get('sl', '?')}, "
                f"Tag: {c.get('tag', '?')}."
            )
        return "\n".join(lines)

    def _parse_batch_response(self, response_text: str, candidates: list[dict]) -> dict[str, str]:
        """Extract SYMBOL: summary pairs from the AI response."""
        results = {}
        for candidate in candidates:
            sym = candidate["symbol"]
            # Search for "SYMBOL: text" pattern
            pattern = rf"(?:^|\n){re.escape(sym)}\s*:\s*(.+?)(?=\n[A-Z&]+\s*:|$)"
            match   = re.search(pattern, response_text, re.DOTALL | re.IGNORECASE)
            if match:
                results[sym] = match.group(1).strip().replace("\n", " ")
            else:
                results[sym] = self._fallback_summary(candidate)
        return results

    @staticmethod
    def _fallback_summary(candidate: dict) -> str:
        return (
            f"RSI Reversal setup: Monthly RSI {candidate.get('rsi_monthly', '?')}, "
            f"Weekly RSI {candidate.get('rsi_weekly', '?')}, "
            f"Daily RSI {candidate.get('rsi_daily', '?')} in pullback zone. "
            f"{candidate.get('signal_candle_pattern', 'Signal candle')} on "
            f"{candidate.get('signal_candle_date', '?')} — "
            f"entry above ₹{candidate.get('entry', '?')}, SL ₹{candidate.get('sl', '?')}."
        )

    # ------------------------------------------------------------------
    # API callers (cascade)
    # ------------------------------------------------------------------

    def _call_batch(self, candidates: list[dict]) -> dict[str, str]:
        prompt = self._build_batch_prompt(candidates)
        text   = None

        # 1. Gemini
        if self._gemini_model:
            try:
                response = self._gemini_model.generate_content(prompt)
                text     = response.text
            except Exception as exc:
                print(f"[warn] Gemini failed: {exc}")

        # 2. Groq
        if text is None and self.groq_key:
            try:
                from openai import OpenAI
                client   = OpenAI(api_key=self.groq_key, base_url="https://api.groq.com/openai/v1")
                response = client.chat.completions.create(
                    model    = "llama3-8b-8192",
                    messages = [{"role": "user", "content": prompt}],
                )
                text = response.choices[0].message.content
            except Exception as exc:
                print(f"[warn] Groq failed: {exc}")

        # 3. OpenAI
        if text is None and self.openai_key:
            try:
                from openai import OpenAI
                client   = OpenAI(api_key=self.openai_key)
                response = client.chat.completions.create(
                    model    = "gpt-4o-mini",
                    messages = [{"role": "user", "content": prompt}],
                )
                text = response.choices[0].message.content
            except Exception as exc:
                print(f"[warn] OpenAI failed: {exc}")

        # 4. Anthropic
        if text is None and self.anthropic_key:
            try:
                from anthropic import Anthropic
                client   = Anthropic(api_key=self.anthropic_key)
                response = client.messages.create(
                    model      = "claude-haiku-20240307",
                    max_tokens = 512,
                    messages   = [{"role": "user", "content": prompt}],
                )
                text = response.content[0].text
            except Exception as exc:
                print(f"[warn] Anthropic failed: {exc}")

        if text:
            return self._parse_batch_response(text, candidates)

        # All APIs failed — return fallback summaries
        return {c["symbol"]: self._fallback_summary(c) for c in candidates}
