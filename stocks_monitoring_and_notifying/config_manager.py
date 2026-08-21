"""
config_manager.py
-----------------
Loads and validates the application configuration from config.json
or environment variables (for GitHub Actions deployment).
"""

import os
import json


# Default configuration values
DEFAULTS = {
    "schedule": {
        "full_scan_time_ist": "08:00",
        "hourly_enabled": True,
        "hourly_start_ist": "09:00",
        "hourly_end_ist": "16:00",
        "top_n_for_hourly": 50,
    },
    "filters": {
        "sma_short": 50,
        "sma_long": 200,
        "rsi_min": 40,
        "rsi_max": 65,
        "adx_min": 25,
        "volume_ratio_min": 1.0,
        "atr_stop_loss_multiplier": 1.5,
        "lookback_days": 90,
    },
    "portfolio": {
        "trailing_stop_activation_pct": 5.0,
        "trailing_stop_distance_atr": 1.5
    }
}


class ConfigManager:
    """Loads, validates and provides access to application configuration.

    Configuration is read from a JSON file on disk.  When running inside
    GitHub Actions the three secret values (telegram_bot_token,
    telegram_chat_id, gemini_api_key) can also come from environment
    variables which take precedence over the file.
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
        """Load configuration from disk and merge with defaults."""
        if os.path.exists(self.config_path):
            with open(self.config_path, "r", encoding="utf-8") as fh:
                self._data = json.load(fh)
        else:
            self._data = {}

        # Merge defaults for any missing sections
        for section, defaults in DEFAULTS.items():
            if section not in self._data:
                self._data[section] = dict(defaults)
            else:
                for key, value in defaults.items():
                    self._data[section].setdefault(key, value)

        # Environment variable overrides (for GitHub Actions)
        env_token = os.environ.get("TELEGRAM_BOT_TOKEN")
        env_chat = os.environ.get("TELEGRAM_CHAT_ID")
        env_gemini = os.environ.get("GEMINI_API_KEY")
        env_groq = os.environ.get("GROQ_API_KEY")
        env_openai = os.environ.get("OPENAI_API_KEY")
        env_anthropic = os.environ.get("ANTHROPIC_API_KEY")

        if env_token:
            self._data["telegram_bot_token"] = env_token
        if env_chat:
            self._data["telegram_chat_id"] = env_chat
        if env_gemini:
            self._data["gemini_api_key"] = env_gemini
        if env_groq:
            self._data["groq_api_key"] = env_groq
        if env_openai:
            self._data["openai_api_key"] = env_openai
        if env_anthropic:
            self._data["anthropic_api_key"] = env_anthropic

        return self._data

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate(self, require_secrets: bool = True) -> list[str]:
        """Return a list of human-readable error strings.

        When *require_secrets* is True (the default for headless / scheduler
        mode) the three API keys must be present.  Set to False for GUI-only
        mode where the keys are optional.
        """
        errors: list[str] = []

        if require_secrets:
            if not self.telegram_bot_token:
                errors.append(
                    "Missing 'telegram_bot_token'. Set it in config.json or "
                    "as the TELEGRAM_BOT_TOKEN environment variable."
                )
            if not self.telegram_chat_id:
                errors.append(
                    "Missing 'telegram_chat_id'. Set it in config.json or "
                    "as the TELEGRAM_CHAT_ID environment variable."
                )
            if not self.gemini_api_key:
                errors.append(
                    "Missing 'gemini_api_key'. Set it in config.json or "
                    "as the GEMINI_API_KEY environment variable."
                )
        return errors

    # ------------------------------------------------------------------
    # Save (for GUI toggling hourly_enabled, etc.)
    # ------------------------------------------------------------------

    def save(self) -> None:
        """Persist current configuration back to disk."""
        with open(self.config_path, "w", encoding="utf-8") as fh:
            json.dump(self._data, fh, indent=4)

    # ------------------------------------------------------------------
    # Convenience accessors
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

    # Schedule accessors
    @property
    def schedule(self) -> dict:
        return self._data.get("schedule", DEFAULTS["schedule"])

    # Filter accessors
    @property
    def filters(self) -> dict:
        return self._data.get("filters", DEFAULTS["filters"])

    @property
    def hourly_enabled(self) -> bool:
        return self.schedule.get("hourly_enabled", True)

    @hourly_enabled.setter
    def hourly_enabled(self, value: bool):
        self._data.setdefault("schedule", {})["hourly_enabled"] = value

    @property
    def top_n_for_hourly(self) -> int:
        return self.schedule.get("top_n_for_hourly", 50)

    # Advanced accessors
    @property
    def advanced(self) -> dict:
        return self._data.get("advanced", DEFAULTS.get("advanced", {}))

    # Portfolio accessors
    @property
    def portfolio(self) -> dict:
        return self._data.get("portfolio", DEFAULTS["portfolio"])

    @property
    def config(self) -> dict:
        """Return the entire configuration dictionary.
        This mirrors the historical attribute that callers (e.g., tests) expect.
        """
        return self._data
