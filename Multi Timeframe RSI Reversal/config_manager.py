"""
config_manager.py
-----------------
Loads and validates the application configuration from config.json
or environment variables (for Render.com / GitHub Actions deployment).

Strategy: Multi-Timeframe RSI Reversal (RSI MWD 60-60-40)
"""

import os
import json


# ── Reversal-specific defaults ────────────────────────────────────────────────
DEFAULTS = {
    "schedule": {
        "full_scan_time_ist": "19:00",
        "hourly_enabled": False,
        "hourly_start_ist": "09:15",
        "hourly_end_ist": "15:30",
        "top_n_for_hourly": 50,
    },
    "filters": {
        "rsi_monthly_min": 60,
        "rsi_weekly_min": 60,
        "rsi_daily_band": [35, 45],
        "sl_mode": "signal_candle_low",   # "signal_candle_low" | "swing_low"
        "trailing_enabled": False,
        "trailing_bar_count": 5,
        "lookback_days": 400,
    },
    "risk": {
        "default_capital": 500000,
        "risk_pct_default": 1.0,
        "reward_multiple": 1.5,
        "auto_paper_trade_enabled": True,
        "partial_exit_pct": 50,
        "max_positions": 5,
    },
}


class ConfigManager:
    """Loads, validates and provides typed access to the reversal strategy config.

    Priority (highest → lowest):
      1. Environment variables (TELEGRAM_BOT_TOKEN, etc.)
      2. config.json on disk
      3. Built-in DEFAULTS
    """

    def __init__(self, config_path: str = None):
        if config_path is None:
            config_path = os.path.join(os.path.dirname(__file__), "config.json")
        self.config_path = config_path
        self._data: dict = {}
        self.load()

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def load(self) -> dict:
        """Load configuration from disk and deep-merge with defaults."""
        if os.path.exists(self.config_path):
            with open(self.config_path, "r", encoding="utf-8") as fh:
                self._data = json.load(fh)
        else:
            self._data = {}

        # Deep-merge defaults for any missing sections / keys
        for section, defaults in DEFAULTS.items():
            if section not in self._data:
                self._data[section] = dict(defaults)
            else:
                for key, value in defaults.items():
                    self._data[section].setdefault(key, value)

        # Environment variable overrides (Render.com / GitHub Actions)
        env_map = {
            "TELEGRAM_BOT_TOKEN": "telegram_bot_token",
            "TELEGRAM_CHAT_ID":   "telegram_chat_id",
            "GEMINI_API_KEY":     "gemini_api_key",
            "GROQ_API_KEY":       "groq_api_key",
            "OPENAI_API_KEY":     "openai_api_key",
            "ANTHROPIC_API_KEY":  "anthropic_api_key",
        }
        for env_key, cfg_key in env_map.items():
            val = os.environ.get(env_key)
            if val:
                self._data[cfg_key] = val

        return self._data

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate(self, require_secrets: bool = True) -> list[str]:
        """Return a list of human-readable error strings.

        When *require_secrets* is True the three core API keys must be
        present. Set to False for dry-run / testing without credentials.
        """
        errors: list[str] = []
        if require_secrets:
            if not self.telegram_bot_token:
                errors.append(
                    "Missing 'telegram_bot_token'. Set it in config.json "
                    "or as the TELEGRAM_BOT_TOKEN environment variable."
                )
            if not self.telegram_chat_id:
                errors.append(
                    "Missing 'telegram_chat_id'. Set it in config.json "
                    "or as the TELEGRAM_CHAT_ID environment variable."
                )
            if not self.gemini_api_key:
                errors.append(
                    "Missing 'gemini_api_key'. Set it in config.json "
                    "or as the GEMINI_API_KEY environment variable."
                )
        return errors

    # ------------------------------------------------------------------
    # Persist (for runtime toggles, e.g. /revtoggle)
    # ------------------------------------------------------------------

    def save(self) -> None:
        """Persist current in-memory config back to disk."""
        with open(self.config_path, "w", encoding="utf-8") as fh:
            json.dump(self._data, fh, indent=4)

    # ------------------------------------------------------------------
    # Convenience accessors — secrets
    # ------------------------------------------------------------------

    @property
    def telegram_bot_token(self) -> str:
        return self._data.get("telegram_bot_token", "")

    @property
    def telegram_chat_id(self) -> str:
        return str(self._data.get("telegram_chat_id", ""))

    @property
    def gemini_api_key(self) -> str:
        return self._data.get("gemini_api_key", "")

    @property
    def groq_api_key(self) -> str:
        return self._data.get("groq_api_key", "")

    @property
    def openai_api_key(self) -> str:
        return self._data.get("openai_api_key", "")

    @property
    def anthropic_api_key(self) -> str:
        return self._data.get("anthropic_api_key", "")

    # ------------------------------------------------------------------
    # Convenience accessors — strategy sections
    # ------------------------------------------------------------------

    @property
    def schedule(self) -> dict:
        return self._data.get("schedule", DEFAULTS["schedule"])

    @property
    def filters(self) -> dict:
        return self._data.get("filters", DEFAULTS["filters"])

    @property
    def risk(self) -> dict:
        return self._data.get("risk", DEFAULTS["risk"])

    # Shortcut helpers used across modules
    @property
    def hourly_enabled(self) -> bool:
        return self.schedule.get("hourly_enabled", False)

    @hourly_enabled.setter
    def hourly_enabled(self, value: bool):
        self._data.setdefault("schedule", {})["hourly_enabled"] = value

    @property
    def auto_paper_trade_enabled(self) -> bool:
        return self.risk.get("auto_paper_trade_enabled", True)

    @auto_paper_trade_enabled.setter
    def auto_paper_trade_enabled(self, value: bool):
        self._data.setdefault("risk", {})["auto_paper_trade_enabled"] = value
        self.save()

    @property
    def default_capital(self) -> float:
        return float(self.risk.get("default_capital", 500000))

    @property
    def risk_pct(self) -> float:
        return float(self.risk.get("risk_pct_default", 1.0))

    @property
    def reward_multiple(self) -> float:
        return float(self.risk.get("reward_multiple", 1.5))

    @property
    def max_positions(self) -> int:
        return int(self.risk.get("max_positions", 5))

    @property
    def top_n_for_hourly(self) -> int:
        return int(self.schedule.get("top_n_for_hourly", 50))

    @property
    def config(self) -> dict:
        """Return the raw config dict (for callers that need full access)."""
        return self._data
