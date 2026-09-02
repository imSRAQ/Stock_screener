"""
bot_worker.py
-------------
Standalone 24/7 Telegram bot listener.
Deploy this on Render.com as a Background Worker.

It syncs portfolio.json and watchlist.json from GitHub on startup,
then runs the bot polling loop forever so the bot responds to
/chart, /portfolio, /entry, /exit, /watch etc. at any time of day.
"""

import os
import sys
import subprocess

# ── Ensure local imports work when deployed ───────────────────────────────────
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

REPO_ROOT = os.path.dirname(HERE)  # one level above stocks_monitoring_and_notifying/


def _configure_git():
    """Configure git with GITHUB_TOKEN so the bot can pull/push data files."""
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        print("[warn] GITHUB_TOKEN not set — bot cannot sync data with GitHub.")
        return
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=REPO_ROOT, capture_output=True, text=True
        )
        remote_url = result.stdout.strip()
        if "github.com" in remote_url and "x-access-token" not in remote_url:
            authed = remote_url.replace(
                "https://github.com/",
                f"https://x-access-token:{token}@github.com/"
            )
            subprocess.run(["git", "remote", "set-url", "origin", authed],
                           cwd=REPO_ROOT, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "bot@render.com"],
                       cwd=REPO_ROOT, capture_output=True)
        subprocess.run(["git", "config", "user.name", "NSE Bot Worker"],
                       cwd=REPO_ROOT, capture_output=True)
        print("[info] Git configured with GITHUB_TOKEN.")
    except Exception as exc:
        print(f"[warn] Git setup failed: {exc}")


def _pull_latest():
    """Pull latest portfolio.json / watchlist.json committed by GitHub Actions."""
    try:
        result = subprocess.run(
            ["git", "pull", "--rebase"],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=30
        )
        print(f"[info] Git pull: {result.stdout.strip() or 'already up to date'}")
    except Exception as exc:
        print(f"[warn] Git pull failed: {exc}")


def main():
    print("[info] NSE Bot Worker starting up...")
    _configure_git()
    _pull_latest()

    from config_manager import ConfigManager
    from watchlist_manager import WatchlistManager
    from portfolio_manager import PortfolioManager
    from telegram_notifier import TelegramNotifier

    config = ConfigManager()
    errors = config.validate(require_secrets=True)
    if errors:
        for e in errors:
            print(f"[error] {e}")
        sys.exit(1)

    watchlist = WatchlistManager()
    portfolio = PortfolioManager()
    notifier = TelegramNotifier(config, watchlist, portfolio)

    if not notifier.is_configured:
        print("[error] Telegram token / chat_id missing. Exiting.")
        sys.exit(1)

    print("[info] All systems go. Telegram bot is listening 24/7...")
    # Blocks forever — Render will auto-restart if it ever crashes
    notifier._run_bot_loop()


if __name__ == "__main__":
    main()
