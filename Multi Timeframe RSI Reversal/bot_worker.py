"""
bot_worker.py  (Multi Timeframe RSI Reversal)
---------------------------------------------
Reversal-strategy scheduler process for Render.com.

IMPORTANT — This file does NOT run a Telegram polling loop.
The existing stocks_monitoring_and_notifying/bot_worker.py owns the single
polling loop and handles both uptrend AND reversal (/rev*) commands.

This file's only responsibilities:
  1. Keep-alive HTTP server (port 10001, separate from uptrend's 10000)
  2. APScheduler: full reversal scan at 19:00 IST Mon–Fri
  3. Optional APScheduler: hourly breakout re-check during market hours
  4. Git pull (before scan) and git push (after scan) to persist state

Deployed as a second Render.com worker service — zero extra Telegram bot cost
since it uses direct Bot API sends (send_alert) instead of polling.

Strategy: Multi-Timeframe RSI Reversal
"""

import os
import sys
import subprocess
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

# ── Ensure reversal module folder is on path ───────────────────────────────────
_HERE     = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(_HERE)

if _HERE not in sys.path:
    sys.path.insert(0, _HERE)


# ── Keep-alive web server (port 10001 — different from uptrend's 10000) ───────
class _PingHandler(BaseHTTPRequestHandler):
    """Tiny HTTP handler for Render health checks."""
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"RSI Reversal Scheduler is alive!")

    def log_message(self, fmt, *args):
        pass  # suppress noisy access logs


def _start_keep_alive():
    port   = int(os.environ.get("REV_PORT", 10001))
    server = HTTPServer(("0.0.0.0", port), _PingHandler)
    print(f"[info] Reversal keep-alive server on port {port}")
    server.serve_forever()


# ── Git helpers ────────────────────────────────────────────────────────────────
def _configure_git():
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        print("[warn] GITHUB_TOKEN not set — changes won't sync to GitHub.")
        return
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=REPO_ROOT, capture_output=True, text=True
        )
        remote = result.stdout.strip()
        if "github.com" in remote and "x-access-token" not in remote:
            authed = remote.replace(
                "https://github.com/",
                f"https://x-access-token:{token}@github.com/"
            )
            subprocess.run(["git", "remote", "set-url", "origin", authed],
                           cwd=REPO_ROOT, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "rev-bot@render.com"],
                       cwd=REPO_ROOT, capture_output=True)
        subprocess.run(["git", "config", "user.name", "RSI Reversal Bot"],
                       cwd=REPO_ROOT, capture_output=True)
        print("[info] Git configured.")
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
        print("[warn] GITHUB_TOKEN not set — cannot push to GitHub.")
        return
    try:
        folder = "Multi Timeframe RSI Reversal"
        files_to_add = [
            f"{folder}/docs/index.html",
            f"{folder}/virtual_portfolio.json",
            f"{folder}/blackout_calendar.json",
            f"{folder}/universe_snapshot.json",
            f"{folder}/universe_snapshot_prev.json",
        ]
        # Add scan archive directory
        scan_dir = os.path.join(_HERE, "docs", "scan")
        if os.path.isdir(scan_dir):
            files_to_add.append(f"{folder}/docs/scan/")

        for f in files_to_add:
            subprocess.run(["git", "add", "-f", f], cwd=REPO_ROOT, capture_output=True)

        diff = subprocess.run(["git", "diff", "--staged", "--quiet"], cwd=REPO_ROOT)
        if diff.returncode != 0:
            subprocess.run(
                ["git", "commit", "-m", "Auto-update: RSI Reversal scan results"],
                cwd=REPO_ROOT, capture_output=True
            )
            r = subprocess.run(["git", "push"], cwd=REPO_ROOT, capture_output=True, text=True)
            if r.returncode == 0:
                print("[info] Pushed reversal state to GitHub.")
            else:
                print(f"[error] Git push failed: {r.stderr}")
        else:
            print("[info] No state changes to push.")
    except Exception as exc:
        print(f"[warn] Git push failed: {exc}")


# ── APScheduler jobs ───────────────────────────────────────────────────────────
def _job_full_scan():
    _pull_latest()
    print("[info] Running reversal full scan (19:00 IST)…")
    try:
        from scheduler import Scheduler
        Scheduler().run_full()
    except Exception as exc:
        print(f"[error] Full scan failed: {exc}")
    _push_latest()


def _job_hourly():
    try:
        from scheduler import Scheduler
        Scheduler().run_hourly()
    except Exception as exc:
        print(f"[error] Hourly scan failed: {exc}")


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    print("[info] RSI Reversal Scheduler starting…")

    _configure_git()
    _pull_latest()

    # Start keep-alive in background
    threading.Thread(target=_start_keep_alive, daemon=True).start()

    # Start APScheduler
    try:
        from apscheduler.schedulers.blocking import BlockingScheduler
        import pytz

        ist = pytz.timezone("Asia/Kolkata")

        from config_manager import ConfigManager
        cfg = ConfigManager()

        sched = BlockingScheduler(timezone=ist)

        # Full scan at configured time (default 19:00)
        f_time = cfg.schedule.get("full_scan_time_ist", "19:00")
        f_hr, f_mn = f_time.split(":")
        sched.add_job(
            _job_full_scan, "cron",
            day_of_week="mon-fri",
            hour=int(f_hr), minute=int(f_mn),
            id="reversal_full_scan"
        )
        print(f"[info] Full scan scheduled at {f_time} IST (Mon–Fri).")

        # Optional hourly breakout re-check
        if cfg.hourly_enabled:
            h_start = int(cfg.schedule.get("hourly_start_ist", "09:15").split(":")[0])
            h_end   = int(cfg.schedule.get("hourly_end_ist",   "15:30").split(":")[0])
            sched.add_job(
                _job_hourly, "cron",
                day_of_week="mon-fri",
                hour=f"{h_start}-{h_end}", minute=15,
                id="reversal_hourly"
            )
            print(f"[info] Hourly re-check: {h_start}:15–{h_end}:15 IST.")

        print("[info] RSI Reversal Scheduler running. Waiting for scheduled jobs…")
        sched.start()   # blocks forever

    except (KeyboardInterrupt, SystemExit):
        print("[info] Reversal scheduler stopped.")
    except Exception as exc:
        print(f"[error] APScheduler failed to start: {exc}")
        # Fallback: just keep the HTTP server alive so Render doesn't mark the service as failed
        import time
        while True:
            time.sleep(60)


if __name__ == "__main__":
    main()
