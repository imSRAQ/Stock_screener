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


def _push_latest():
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        print("[warn] GITHUB_TOKEN not set — cannot push updates to GitHub.")
        return
    try:
        # Add the specific generated files using -f because JSONs are in .gitignore
        files_to_add = [
            "stocks_monitoring_and_notifying/docs/index.html",
            "stocks_monitoring_and_notifying/latest_universe_data.json",
            "stocks_monitoring_and_notifying/watchlist.json",
            "stocks_monitoring_and_notifying/portfolio.json",
            "stocks_monitoring_and_notifying/virtual_portfolio.json",
            "stocks_monitoring_and_notifying/fundamental_cache.json",
            "stocks_monitoring_and_notifying/historical_recommendations.json",
            "stocks_monitoring_and_notifying/universe_snapshot.json",
            "stocks_monitoring_and_notifying/universe_snapshot_prev.json"
        ]
        
        for f in files_to_add:
            subprocess.run(["git", "add", "-f", f], cwd=REPO_ROOT, capture_output=True)
            
        diff = subprocess.run(["git", "diff", "--staged", "--quiet"], cwd=REPO_ROOT)
        if diff.returncode != 0: # Changes exist
            subprocess.run(["git", "commit", "-m", "Auto-update state from 24/7 bot worker"], cwd=REPO_ROOT, capture_output=True)
            r = subprocess.run(["git", "push"], cwd=REPO_ROOT, capture_output=True, text=True)
            if r.returncode == 0:
                print("[info] Successfully pushed state to GitHub.")
            else:
                print(f"[error] Failed to push to GitHub: {r.stderr}")
        else:
            print("[info] No state changes to push.")
    except Exception as exc:
        print(f"[warn] Git push failed: {exc}")


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

    # ── Background Scheduler (Replaces GitHub Actions) ──
    try:
        from scheduler import Scheduler
        from apscheduler.schedulers.background import BackgroundScheduler
        import pytz
        
        app_scheduler = Scheduler()
        ist = pytz.timezone('Asia/Kolkata')
        cron_sched = BackgroundScheduler(timezone=ist)
        
        def job_full_scan():
            _pull_latest()
            print("[info] Running full scheduled scan...")
            app_scheduler.run_full()
            _push_latest()

        def job_hourly_scan():
            _pull_latest()
            print("[info] Running hourly scheduled scan...")
            app_scheduler.run_hourly()
            _push_latest()
            
        # Parse full scan time
        f_time = config.schedule.get("full_scan_time_ist", "08:00")
        f_hr, f_mn = f_time.split(":")
        cron_sched.add_job(job_full_scan, 'cron', day_of_week='mon-fri', hour=int(f_hr), minute=int(f_mn))
        
        # Parse hourly start/end
        h_start = int(config.schedule.get("hourly_start_ist", "10:00").split(":")[0])
        h_end = int(config.schedule.get("hourly_end_ist", "16:00").split(":")[0])
        cron_sched.add_job(job_hourly_scan, 'cron', day_of_week='mon-fri', hour=f"{h_start}-{h_end}", minute=0)
        
        # ── RSI Reversal Strategy Scheduler (Option A — same service, zero extra cost) ──
        try:
            import sys as _sys
            _rev_path = os.path.join(REPO_ROOT, "Multi Timeframe RSI Reversal")
            if _rev_path not in _sys.path:
                _sys.path.insert(0, _rev_path)

            def job_reversal_full_scan():
                _pull_latest()
                print("[info] Running RSI Reversal full scan (19:00 IST)...")
                from scheduler import Scheduler as RevScheduler
                RevScheduler().run_full()
                _push_latest()

            # Parse reversal scan time from reversal config (default 19:00)
            from config_manager import ConfigManager as RevConfig
            rev_cfg  = RevConfig()
            rev_time = rev_cfg.schedule.get("full_scan_time_ist", "19:00")
            rv_hr, rv_mn = rev_time.split(":")
            cron_sched.add_job(
                job_reversal_full_scan, "cron",
                day_of_week="mon-fri", hour=int(rv_hr), minute=int(rv_mn),
                id="reversal_full_scan"
            )
            print(f"[info] RSI Reversal scan scheduled at {rev_time} IST (Mon–Fri).")

            # Optional hourly breakout re-check for reversal watchlist
            if rev_cfg.hourly_enabled:
                def job_reversal_hourly():
                    from scheduler import Scheduler as RevScheduler
                    RevScheduler().run_hourly()

                rh_start = int(rev_cfg.schedule.get("hourly_start_ist", "09:15").split(":")[0])
                rh_end   = int(rev_cfg.schedule.get("hourly_end_ist",   "15:30").split(":")[0])
                cron_sched.add_job(
                    job_reversal_hourly, "cron",
                    day_of_week="mon-fri", hour=f"{rh_start}-{rh_end}", minute=15,
                    id="reversal_hourly"
                )
                print(f"[info] RSI Reversal hourly re-check: {rh_start}:15–{rh_end}:15 IST.")
        except Exception as rev_e:
            print(f"[warn] Could not schedule RSI Reversal jobs: {rev_e}")
        # ── End Reversal Scheduler ──────────────────────────────────────────────────

        cron_sched.start()
        print(f"[info] APScheduler started (IST). Full scan at {f_time}, hourly between {h_start}:00 and {h_end}:00.")
    except Exception as e:
        print(f"[warn] Failed to start APScheduler: {e}. Please ensure 'apscheduler' and 'pytz' are in requirements.txt.")

    print("[info] All systems go. Telegram bot is listening 24/7...")
    notifier._run_bot_loop()  # blocks forever


if __name__ == "__main__":
    main()
