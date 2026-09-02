"""
bot_worker.py
-------------
Standalone 24/7 Telegram bot listener.
Deploy this on Render.com as a FREE Web Service.

It runs a tiny keep-alive web server (so Render's free tier doesn't sleep)
alongside the Telegram polling loop. Pair with UptimeRobot (free) to ping
the URL every 5 minutes and the bot stays awake 24/7 for $0.
"""

import os
import sys
import subprocess
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

# ── Ensure local imports work when deployed ───────────────────────────────────
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
REPO_ROOT = os.path.dirname(HERE)


# ── Keep-alive web server ─────────────────────────────────────────────────────
class _PingHandler(BaseHTTPRequestHandler):
    """Tiny HTTP handler so Render's health checks and UptimeRobot pings succeed."""
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"NSE Bot is alive and listening on Telegram!")

    def log_message(self, fmt, *args):
        pass  # suppress noisy access logs


def _start_keep_alive():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), _PingHandler)
    print(f"[info] Keep-alive web server listening on port {port}")
    server.serve_forever()


# ── Git helpers ───────────────────────────────────────────────────────────────
def _configure_git():
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        print("[warn] GITHUB_TOKEN not set — portfolio changes won't sync to GitHub.")
        return
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=REPO_ROOT, capture_output=True, text=True
        )
        remote = result.stdout.strip()
        if "github.com" in remote and "x-access-token" not in remote:
            authed = remote.replace("https://github.com/",
                                    f"https://x-access-token:{token}@github.com/")
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
    try:
        r = subprocess.run(["git", "pull", "--rebase"],
                           cwd=REPO_ROOT, capture_output=True, text=True, timeout=30)
        print(f"[info] Git pull: {r.stdout.strip() or 'already up to date'}")
    except Exception as exc:
        print(f"[warn] Git pull failed: {exc}")


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print("[info] NSE Bot Worker starting up...")

    _configure_git()
    _pull_latest()

    # Start keep-alive server in background so Render's free tier stays awake
    threading.Thread(target=_start_keep_alive, daemon=True).start()

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
    notifier._run_bot_loop()  # blocks forever


if __name__ == "__main__":
    main()
