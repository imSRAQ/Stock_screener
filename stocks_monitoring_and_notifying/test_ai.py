"""
test_ai.py
----------
Quick diagnostic script to:
  1. List all available Gemini models for your API key
  2. Pick the best one automatically
  3. Test it with a dummy stock summary

Run from the repo root:
    python test_ai.py
"""

import sys
import os
import io

# Force UTF-8 output on Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# Make sure the project folder is on the path
sys.path.insert(0, os.path.dirname(__file__))

import google.generativeai as genai
from stocks_monitoring_and_notifying.config_manager import ConfigManager


def main():
    # -- Step 1: Load API key --
    cfg = ConfigManager()
    api_key = cfg.gemini_api_key

    if not api_key:
        print("[FAIL] No gemini_api_key found in config.json or environment.")
        print("       Add it to stocks_monitoring_and_notifying/config.json")
        return

    genai.configure(api_key=api_key)
    print("[OK] API key loaded successfully.\n")

    # -- Step 2: List all available models --
    print("=" * 60)
    print("  AVAILABLE GEMINI MODELS (for generateContent)")
    print("=" * 60)

    available_models = []
    try:
        for m in genai.list_models():
            if "generateContent" in (m.supported_generation_methods or []):
                available_models.append(m.name)
                print(f"  [+] {m.name}")
    except Exception as e:
        print(f"[FAIL] Could not list models: {e}")
        return

    if not available_models:
        print("  [!] No models support generateContent for your API key.")
        return

    print(f"\n  Total: {len(available_models)} model(s)\n")

    # -- Step 3: Pick the best model --
    # Preference order (newest to oldest)
    preferred = [
        "models/gemini-3.6-flash",
        "models/gemini-3.5-flash",
        "models/gemini-3.1-flash-lite",
        "models/gemini-2.5-flash",
        "models/gemini-2.0-flash",
    ]

    chosen = None
    for pref in preferred:
        if pref in available_models:
            chosen = pref
            break

    if chosen is None:
        # Just pick the first available one
        chosen = available_models[0]

    print(f">>> Selected model: {chosen}\n")

    # -- Step 4: Test a quick generation --
    print("=" * 60)
    print("  TESTING AI SUMMARY")
    print("=" * 60)

    model = genai.GenerativeModel(chosen)

    dummy_prompt = """
    You are an expert stock market analyst. Analyze the following data for NSE stock RELIANCE.

    Current Price: 2500.0
    Stop Loss Level: 2400.0
    Trend Slope: 0.045
    RSI(14): 48.5
    ADX(14): 37.2
    Volume Ratio: 1.3

    TradingView Technical Signal: BUY

    Latest News Headlines:
    - No recent news available.

    Based on this data, provide a VERY CONCISE, actionable reasoning summary.
    - If the setup is bullish (good entry), write 2-3 sentences of Entry reasoning, mentioning the stop-loss level.
    - If there are red flags (bearish news, overbought RSI, weak TV signal), write 1-2 sentences of Exit/caution reasoning.
    Do not use markdown formatting like bolding in the output. Keep it plain text.
    """

    try:
        response = model.generate_content(dummy_prompt)
        summary = response.text.strip()
        print(f"\n  {summary}\n")
        print("=" * 60)
        print("[OK] AI summarizer is working!")

        # Extract just the model short name (e.g. "gemini-2.5-flash")
        short_name = chosen.replace("models/", "")
        print(f"")
        print(f"  >>> UPDATE ai_summarizer.py with this model name:")
        print(f"      self.model = genai.GenerativeModel(\"{short_name}\")")
        print(f"")
        print("=" * 60)
    except Exception as e:
        print(f"\n[FAIL] Generation failed: {e}")
        print("       Try a different model from the list above.")


if __name__ == "__main__":
    main()
