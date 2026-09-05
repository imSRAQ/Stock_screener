"""
event_blackout_filter.py
------------------------
Applies a user-maintained event blackout calendar to screener candidates.

Any symbol whose scan date falls on a blackout date is tagged `blacked_out=True`
and excluded from Telegram alerts (still visible in the dashboard, greyed out).

Blackout calendar format (blackout_calendar.json):
{
    "RELIANCE": ["2026-10-15", "2026-01-20"],
    "GLOBAL":   ["2026-11-07"]
}

"GLOBAL" dates block ALL symbols on that date (e.g. RBI policy day, Budget day).

Strategy: Multi-Timeframe RSI Reversal
"""

import os
import json
from datetime import datetime


_HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CALENDAR_PATH = os.path.join(_HERE, "blackout_calendar.json")


class EventBlackoutFilter:
    """Loads, queries, and manages the blackout calendar."""

    def __init__(self, calendar_path: str = None):
        self.path = calendar_path or DEFAULT_CALENDAR_PATH
        self._calendar: dict[str, list[str]] = {}
        self._load()

    # ------------------------------------------------------------------
    # Load / Save
    # ------------------------------------------------------------------

    def _load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as fh:
                    self._calendar = json.load(fh)
            except Exception as exc:
                print(f"[warn] Failed to load blackout calendar: {exc}")
                self._calendar = {}
        else:
            self._calendar = {}

    def save(self):
        """Persist current calendar to disk."""
        try:
            with open(self.path, "w", encoding="utf-8") as fh:
                json.dump(self._calendar, fh, indent=4)
        except Exception as exc:
            print(f"[warn] Failed to save blackout calendar: {exc}")

    # ------------------------------------------------------------------
    # Mutations (used by /revblackout Telegram command)
    # ------------------------------------------------------------------

    def add(self, symbol: str, date_str: str) -> str:
        """Add a blackout date for a symbol (or GLOBAL).

        Returns a human-readable confirmation string.
        """
        sym = symbol.upper().strip()
        # Validate date format
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            return f"❌ Invalid date format: '{date_str}'. Use YYYY-MM-DD."

        dates = self._calendar.setdefault(sym, [])
        if date_str in dates:
            return f"ℹ️ {sym} already has blackout on {date_str}."
        dates.append(date_str)
        dates.sort()
        self.save()
        return f"✅ Added blackout for {sym} on {date_str}."

    def remove(self, symbol: str, date_str: str) -> str:
        """Remove a blackout date for a symbol (or GLOBAL).

        Returns a human-readable confirmation string.
        """
        sym = symbol.upper().strip()
        dates = self._calendar.get(sym, [])
        if date_str not in dates:
            return f"ℹ️ No blackout for {sym} on {date_str}."
        dates.remove(date_str)
        if not dates:
            del self._calendar[sym]
        self.save()
        return f"✅ Removed blackout for {sym} on {date_str}."

    def list_all(self) -> str:
        """Return a formatted string of all active blackout dates."""
        if not self._calendar:
            return "📅 No blackout dates configured."
        lines = ["📅 <b>Blackout Calendar</b>"]
        for sym, dates in sorted(self._calendar.items()):
            lines.append(f"  <b>{sym}</b>: {', '.join(sorted(dates))}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Apply filter
    # ------------------------------------------------------------------

    def apply(self, candidates: list[dict], scan_date: str = None) -> list[dict]:
        """Mark candidates with blacked_out=True where applicable.

        Parameters
        ----------
        candidates : list[dict]
            Output from ReversalAnalyzer.screen() — each dict has 'symbol'.
        scan_date : str, optional
            Date string in "YYYY-MM-DD" format. Defaults to today.

        Returns
        -------
        list[dict]
            Same list with `blacked_out` field updated in-place.
        """
        if scan_date is None:
            scan_date = datetime.now().strftime("%Y-%m-%d")

        global_dates = self._calendar.get("GLOBAL", [])
        is_global_blackout = scan_date in global_dates

        for candidate in candidates:
            if is_global_blackout:
                candidate["blacked_out"] = True
                candidate["blackout_reason"] = f"Global blackout on {scan_date}"
                continue

            sym = candidate.get("symbol", "")
            sym_dates = self._calendar.get(sym, [])
            if scan_date in sym_dates:
                candidate["blacked_out"] = True
                candidate["blackout_reason"] = f"Symbol blackout on {scan_date}"
            else:
                candidate.setdefault("blacked_out", False)
                candidate.setdefault("blackout_reason", "")

        return candidates

    def is_blacked_out(self, symbol: str, scan_date: str = None) -> bool:
        """Quick check for a single symbol (used by paper_trader)."""
        if scan_date is None:
            scan_date = datetime.now().strftime("%Y-%m-%d")
        global_dates = self._calendar.get("GLOBAL", [])
        if scan_date in global_dates:
            return True
        return scan_date in self._calendar.get(symbol.upper(), [])
