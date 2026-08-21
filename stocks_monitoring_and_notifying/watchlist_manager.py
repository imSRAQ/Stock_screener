"""
watchlist_manager.py
--------------------
Manages the special watchlist by persisting it to watchlist.json.
Automatically syncs changes to git so GitHub Actions has the latest list.
"""

import os
import json
import subprocess

class WatchlistManager:
    """Manages a persistent watchlist of stock symbols with git auto-sync."""

    def __init__(self, filepath: str = None):
        if filepath is None:
            self.filepath = os.path.join(os.path.dirname(__file__), "watchlist.json")
        else:
            self.filepath = filepath
        self.watchlist = set()
        self.load()

    def load(self):
        """Loads watchlist from json file."""
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.watchlist = set(data.get("symbols", []))
            except Exception as e:
                print(f"[warn] Failed to load watchlist: {e}")
                self.watchlist = set()

    def save(self):
        """Saves watchlist to json file and triggers git sync."""
        try:
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump({"symbols": sorted(list(self.watchlist))}, f, indent=4)
            self._git_sync()
        except Exception as e:
            print(f"[warn] Failed to save watchlist: {e}")

    def add(self, symbol: str) -> bool:
        """Adds a symbol to the watchlist. Returns True if added, False if already present."""
        symbol = symbol.upper().strip()
        if not symbol.endswith(".NS"):
            symbol += ".NS"
            
        if symbol not in self.watchlist:
            self.watchlist.add(symbol)
            self.save()
            return True
        return False

    def remove(self, symbol: str) -> bool:
        """Removes a symbol from the watchlist. Returns True if removed."""
        symbol = symbol.upper().strip()
        if not symbol.endswith(".NS"):
            symbol += ".NS"
            
        if symbol in self.watchlist:
            self.watchlist.remove(symbol)
            self.save()
            return True
        return False

    def get_all(self) -> list[str]:
        """Returns the sorted list of watched symbols."""
        return sorted(list(self.watchlist))

    def _git_sync(self):
        """Attempts to commit and push changes to git."""
        try:
            # Check if inside a git repository
            repo_dir = os.path.dirname(os.path.dirname(self.filepath))
            
            # git add
            subprocess.run(["git", "add", self.filepath], cwd=repo_dir, check=True, capture_output=True)
            
            # git commit
            commit_res = subprocess.run(["git", "commit", "-m", "Auto-sync watchlist.json"], cwd=repo_dir, capture_output=True)
            
            # git push only if commit was successful (i.e. there were changes)
            if commit_res.returncode == 0:
                subprocess.run(["git", "push"], cwd=repo_dir, check=True, capture_output=True)
                print("[info] Watchlist synced to git successfully.")
        except Exception as e:
            # We don't want to crash the app if git fails, just log it.
            print(f"[warn] Git sync failed: {e}")
