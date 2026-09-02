#!/usr/bin/env python3
"""
nse_screener_gui.py  —  PyQt6 desktop GUI for the NSE Shape Screener

INSTALL (one time):
    pip install PyQt6 matplotlib yfinance pandas numpy requests

USAGE:
    python nse_screener_gui.py

Put this file in the SAME folder as:
    data_sources.py
    similarity_engine.py
    nifty500_tickers.py

The GUI replaces the command-line screener; you do not need to run
stock_similarity_screener.py separately when using this GUI.
"""

import sys
import os
import json
import csv
import time
import traceback
from datetime import datetime

import numpy as np
import pandas as pd

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QLabel, QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox,
    QCheckBox, QPushButton, QTableWidget, QTableWidgetItem, QHeaderView,
    QSplitter, QTextEdit, QFileDialog, QStatusBar, QFrame, QGroupBox,
    QProgressBar, QSlider, QSizePolicy, QAbstractItemView, QTabWidget,
    QScrollArea, QMessageBox,
)
from PyQt6.QtCore import (
    Qt, QThread, pyqtSignal, QSize, QTimer,
)
from PyQt6.QtGui import (
    QFont, QColor, QPalette, QIcon, QPixmap,
)

import matplotlib
matplotlib.use("QtAgg")
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.pyplot as plt

# ---------------------------------------------------------------------------
# Colour palette — dark trading terminal aesthetic
# ---------------------------------------------------------------------------
DARK = {
    "bg":          "#13151a",
    "panel":       "#1a1d24",
    "row":         "#1e2129",
    "row_alt":     "#212530",
    "row_sel":     "#1d3357",
    "border":      "#2a2e38",
    "text":        "#e8e6e1",
    "text_dim":    "#7a8088",
    "text_faint":  "#4a4f59",
    "green":       "#2ea35a",
    "red":         "#d6473f",
    "amber":       "#e8a23d",
    "blue":        "#3a82e5",
    "blue_hover":  "#4a93f5",
}

QSS = f"""
QMainWindow, QWidget {{
    background-color: {DARK['bg']};
    color: {DARK['text']};
    font-family: 'Segoe UI', system-ui, sans-serif;
    font-size: 13px;
}}
QGroupBox {{
    background-color: {DARK['panel']};
    border: 1px solid {DARK['border']};
    border-radius: 8px;
    margin-top: 10px;
    padding-top: 10px;
    font-weight: 600;
    font-size: 11px;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: {DARK['text_dim']};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    top: 4px;
}}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background-color: {DARK['row']};
    border: 1px solid {DARK['border']};
    border-radius: 5px;
    padding: 5px 9px;
    color: {DARK['text']};
    font-size: 13px;
    selection-background-color: {DARK['blue']};
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border-color: {DARK['blue']};
}}
QComboBox::drop-down {{ border: none; width: 20px; }}
QComboBox QAbstractItemView {{
    background-color: {DARK['panel']};
    border: 1px solid {DARK['border']};
    selection-background-color: {DARK['blue']};
    color: {DARK['text']};
}}
QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
    background-color: {DARK['border']};
    border: none; width: 16px;
}}
QPushButton {{
    background-color: {DARK['row']};
    border: 1px solid {DARK['border']};
    border-radius: 6px;
    padding: 7px 16px;
    color: {DARK['text']};
    font-size: 13px;
    font-weight: 500;
}}
QPushButton:hover {{ background-color: {DARK['panel']}; border-color: {DARK['text_dim']}; }}
QPushButton:pressed {{ background-color: {DARK['border']}; }}
QPushButton#btn_run {{
    background-color: {DARK['blue']};
    border-color: {DARK['blue']};
    color: white;
    font-size: 14px;
    font-weight: 600;
    padding: 10px 28px;
}}
QPushButton#btn_run:hover {{ background-color: {DARK['blue_hover']}; }}
QPushButton#btn_run:disabled {{ background-color: {DARK['border']}; color: {DARK['text_faint']}; }}
QPushButton#btn_stop {{
    background-color: {DARK['red']};
    border-color: {DARK['red']};
    color: white; font-weight: 600;
}}
QPushButton#btn_stop:hover {{ background-color: #e55a52; }}
QTableWidget {{
    background-color: {DARK['row']};
    border: 1px solid {DARK['border']};
    border-radius: 8px;
    gridline-color: {DARK['border']};
    alternate-background-color: {DARK['row_alt']};
    selection-background-color: {DARK['row_sel']};
    color: {DARK['text']};
    font-size: 12px;
}}
QTableWidget::item {{ padding: 4px 8px; }}
QHeaderView::section {{
    background-color: {DARK['panel']};
    border: none;
    border-bottom: 1px solid {DARK['border']};
    border-right: 1px solid {DARK['border']};
    padding: 6px 8px;
    color: {DARK['text_dim']};
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.07em;
    text-transform: uppercase;
}}
QTextEdit {{
    background-color: {DARK['panel']};
    border: 1px solid {DARK['border']};
    border-radius: 6px;
    color: {DARK['text_dim']};
    font-family: 'Consolas', 'JetBrains Mono', monospace;
    font-size: 12px;
    padding: 6px;
}}
QProgressBar {{
    background-color: {DARK['row']};
    border: 1px solid {DARK['border']};
    border-radius: 4px;
    height: 6px;
    text-align: center;
    color: transparent;
}}
QProgressBar::chunk {{ background-color: {DARK['blue']}; border-radius: 4px; }}
QStatusBar {{
    background-color: {DARK['panel']};
    border-top: 1px solid {DARK['border']};
    color: {DARK['text_dim']};
    font-size: 12px;
    padding: 3px 8px;
}}
QSplitter::handle {{ background-color: {DARK['border']}; }}
QCheckBox {{ color: {DARK['text']}; spacing: 6px; }}
QCheckBox::indicator {{
    width: 16px; height: 16px;
    background-color: {DARK['row']};
    border: 1px solid {DARK['border']};
    border-radius: 3px;
}}
QCheckBox::indicator:checked {{ background-color: {DARK['blue']}; border-color: {DARK['blue']}; }}
QLabel#kpi_value {{
    font-size: 22px; font-weight: 600;
    color: {DARK['text']};
}}
QLabel#kpi_label {{
    font-size: 10px; color: {DARK['text_dim']};
    text-transform: uppercase; letter-spacing: 0.06em;
}}
QLabel#section_title {{
    font-size: 11px; font-weight: 600;
    color: {DARK['text_dim']};
    letter-spacing: 0.07em;
    text-transform: uppercase;
    padding: 4px 0;
}}
QSlider::groove:horizontal {{
    background: {DARK['border']}; height: 4px; border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {DARK['blue']}; width: 14px; height: 14px;
    border-radius: 7px; margin: -5px 0;
}}
QSlider::sub-page:horizontal {{ background: {DARK['blue']}; border-radius: 2px; }}
QTabWidget::pane {{
    border: 1px solid {DARK['border']};
    border-radius: 8px;
    background: {DARK['panel']};
}}
QTabBar::tab {{
    background: {DARK['row']}; border: 1px solid {DARK['border']};
    padding: 7px 18px; color: {DARK['text_dim']};
    border-top-left-radius: 6px; border-top-right-radius: 6px;
    font-size: 12px; font-weight: 500;
}}
QTabBar::tab:selected {{ background: {DARK['panel']}; color: {DARK['text']}; border-bottom-color: {DARK['panel']}; }}
QTabBar::tab:hover {{ color: {DARK['text']}; }}
QScrollBar:vertical {{
    background: {DARK['panel']}; width: 8px; border-radius: 4px;
}}
QScrollBar::handle:vertical {{
    background: {DARK['border']}; border-radius: 4px; min-height: 30px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def fmt_cap(rupees):
    if not rupees:
        return "—"
    c = rupees / 1e7
    if c >= 1e5:
        return f"₹{c/1e5:.2f}L Cr"
    if c >= 1:
        return f"₹{round(c):,} Cr"
    return f"₹{round(rupees/1e5):,} L"


def fmt_pct(v):
    if v is None:
        return "—"
    sign = "+" if v >= 0 else ""
    return f"{sign}{v:.2f}%"


def fmt_roe(v):
    if v is None:
        return "—"
    return f"{v*100:.1f}%"


def normalize(arr):
    mn, mx = np.min(arr), np.max(arr)
    r = mx - mn
    if r == 0:
        return np.zeros_like(arr)
    return (arr - mn) / r


def fmt_score(v):
    """Format a 0–100 composite score."""
    if v is None:
        return "—"
    return f"{v:.0f}"


def score_color(v):
    """Green ≥ 70, amber 50–69, red < 50."""
    if v is None:
        return DARK["text_dim"]
    if v >= 70:
        return DARK["green"]
    if v >= 50:
        return DARK["amber"]
    return DARK["red"]


def fmt_sma_signal(above_50, above_200):
    """Compact SMA position label."""
    if above_50 is None and above_200 is None:
        return "—"
    parts = []
    if above_200 is True:
        parts.append(">200")
    if above_50 is True:
        parts.append(">50")
    if not parts:
        return "Below"
    return " ".join(parts)


# ---------------------------------------------------------------------------
# Worker thread — runs the full screener off the main thread so the UI
# stays responsive during a potentially multi-minute Nifty 500 scan.
# ---------------------------------------------------------------------------

class ScreenerWorker(QThread):
    # Signals back to the main thread
    log         = pyqtSignal(str)          # a log line to append to the console
    progress    = pyqtSignal(int, int)     # (done, total) for the progress bar
    finished    = pyqtSignal(dict)         # the full output dict on success
    error       = pyqtSignal(str)          # error message string on failure

    def __init__(self, params: dict):
        super().__init__()
        self.params = params
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        try:
            self._run()
        except Exception:
            self.error.emit(traceback.format_exc())

    def _run(self):
        p = self.params
        sys.path.insert(0, p["script_dir"])

        # Import backend modules from the same directory as the script
        from data_sources import fetch_reference_ohlc, fetch_universe_ohlc, fetch_fundamentals
        from similarity_engine import rank_candidates
        from nifty500_tickers import get_tickers

        ref_ticker = p["reference"]
        ref_close, ref_dates = None, []

        if ref_ticker:
            if not ref_ticker.endswith(".NS"):
                ref_ticker += ".NS"

            # ── Reference stock ──────────────────────────────────────────────
            self.log.emit(f"▶ Fetching reference: {ref_ticker} ({p['lookback']}d via {p['source']})...")
            ref_close, ref_dates = fetch_reference_ohlc(ref_ticker, p["lookback"], source=p["source"])
            if ref_close is None:
                self.error.emit(
                    f"Could not fetch data for '{ref_ticker}' via '{p['source']}'.\n"
                    f"Check the symbol, your internet connection, or try the other source."
                )
                return
            self.log.emit(f"  ✓ Got {len(ref_close)} trading days of data.")
        else:
            self.log.emit("▶ No reference stock provided. Finding all uptrending stocks...")

        if p.get("tickers_file"):
            df_t = pd.read_csv(p["tickers_file"])
            symbols = df_t.iloc[:, 0].astype(str).str.strip().tolist()
            candidates = [s if s.endswith(".NS") else f"{s}.NS" for s in symbols]
        else:
            candidates = get_tickers()

        if ref_ticker:
            candidates = [t for t in candidates if t != ref_ticker]
        total = len(candidates)
        self.log.emit(f"▶ Scanning {total} candidates via '{p['source']}'...")

        # For yfinance we patch the loop to emit progress signals;
        # NSE backend fetches in bulk so we emit a single progress update.
        candidates_data = {}
        failed = []

        if p["source"] == "yfinance":
            from data_sources import _fetch_yfinance
            import concurrent.futures
            
            def do_fetch(ticker):
                if self._stop: return ticker, None
                # slight pause to avoid hitting yfinance instantly from all threads
                time.sleep(p["delay"] / 2.0)
                return ticker, _fetch_yfinance(ticker, p["lookback"])

            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
                futures = {executor.submit(do_fetch, t): t for t in candidates}
                for i, future in enumerate(concurrent.futures.as_completed(futures), 1):
                    if self._stop:
                        continue
                    
                    ticker = futures[future]
                    try:
                        t, result = future.result()
                        if result:
                            closes, _ = result
                            candidates_data[ticker] = closes
                        else:
                            failed.append(ticker)
                    except Exception:
                        failed.append(ticker)

                    self.progress.emit(i, total)
                    if i % 25 == 0:
                        self.log.emit(f"  …{i}/{total} processed ({len(candidates_data)} ok, {len(failed)} failed)")

            if self._stop:
                self.log.emit("⚠ Scan stopped by user.")
                return
        else:
            self.log.emit("  Downloading NSE Bhavcopy files (one per trading day)…")
            candidates_data, failed = fetch_universe_ohlc(
                candidates, p["lookback"], source="nse", delay=0
            )
            self.progress.emit(total, total)

        self.log.emit(
            f"  ✓ Fetched {len(candidates_data)}/{total} "
            f"({len(failed)} failed/skipped)."
        )

        if self._stop:
            return

        # ── Similarity ranking ───────────────────────────────────────────
        self.log.emit("▶ Ranking by shape similarity (DTW)…")
        ranked = rank_candidates(
            ref_close, candidates_data,
            min_slope=p["min_slope"],
            uptrend_only=True,
        )

        if ranked.empty:
            self.log.emit("⚠ No uptrend matches found. Try a lower min-slope or longer lookback.")
        else:
            top_n = p.get("top_n")
            if top_n:
                ranked = ranked.head(top_n)
            self.log.emit(f"  ✓ {len(ranked)} uptrend match(es) found.")

        # ── Fundamentals (optional) ──────────────────────────────────────
        fundamentals = {}
        if p["with_fundamentals"] and not ranked.empty:
            tickers_for_fund = ([ref_ticker] if ref_ticker else []) + ranked["ticker"].tolist()
            self.log.emit(f"▶ Fetching fundamentals for {len(tickers_for_fund)} tickers…")
            fundamentals = fetch_fundamentals(tickers_for_fund, source=p["source"], delay=p["delay"])
            self.log.emit("  ✓ Fundamentals done.")

        # ── Build output dict ────────────────────────────────────────────
        results_records = ranked.to_dict(orient="records") if not ranked.empty else []

        # Merge fundamentals into results rows
        for row in results_records:
            t = row["ticker"]
            fund = fundamentals.get(t, {})
            row["market_cap"]     = fund.get("market_cap")
            row["current_price"]  = fund.get("current_price")
            row["roe"]            = fund.get("roe")
            row["quick_ratio"]    = fund.get("quick_ratio")
            # NEW fundamental fields
            row["pe_ratio"]       = fund.get("pe_ratio")
            row["eps"]            = fund.get("eps")
            row["pb_ratio"]       = fund.get("pb_ratio")
            row["debt_to_equity"] = fund.get("debt_to_equity")
            row["profit_margin"]  = fund.get("profit_margin")
            row["revenue_growth"] = fund.get("revenue_growth")
            row["free_cash_flow"] = fund.get("free_cash_flow")
            row["dividend_yield"] = fund.get("dividend_yield")
            row["fund_score"]     = fund.get("fund_score")

        ref_fund = fundamentals.get(ref_ticker, {}) if ref_ticker else {}
        output = {
            "generated_at": datetime.now().isoformat(),
            "reference": {
                "ticker":        ref_ticker or "None",
                "lookback_days": p["lookback"],
                "close":         ref_close.round(2).tolist() if ref_close is not None else [],
                "dates":         ref_dates,
                "market_cap":    ref_fund.get("market_cap"),
                "current_price": ref_fund.get("current_price"),
                "roe":           ref_fund.get("roe"),
                "quick_ratio":   ref_fund.get("quick_ratio"),
                "pe_ratio":      ref_fund.get("pe_ratio"),
                "fund_score":    ref_fund.get("fund_score"),
            },
            "params": {
                "min_slope": p["min_slope"],
                "top_n":     p.get("top_n"),
                "source":    p["source"],
            },
            "results":   results_records,
            "candidates_close": {
                t: candidates_data[t].round(2).tolist()
                for t in (ranked["ticker"].tolist() if not ranked.empty else [])
            },
            "fundamentals": {
                t: fundamentals[t] for t in fundamentals if t != ref_ticker
            },
            "failed_count":  len(failed),
            "scanned_count": total,
        }

        self.log.emit("✓ Scan complete.")
        self.finished.emit(output)


# ---------------------------------------------------------------------------
# KPI card widget
# ---------------------------------------------------------------------------

class KpiCard(QFrame):
    def __init__(self, label: str, value: str = "—", accent: str = DARK["text"]):
        super().__init__()
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(f"""
            QFrame {{
                background: {DARK['panel']};
                border: 1px solid {DARK['border']};
                border-radius: 8px;
                padding: 4px;
            }}
        """)
        v = QVBoxLayout(self)
        v.setContentsMargins(12, 10, 12, 10)
        v.setSpacing(2)

        self.lbl = QLabel(label.upper())
        self.lbl.setObjectName("kpi_label")
        self.lbl.setStyleSheet(f"color:{DARK['text_dim']};font-size:10px;letter-spacing:0.06em;")

        self.val = QLabel(value)
        self.val.setObjectName("kpi_value")
        self.val.setStyleSheet(f"color:{accent};font-size:20px;font-weight:600;")

        v.addWidget(self.lbl)
        v.addWidget(self.val)

    def set_value(self, v: str, accent: str = None):
        self.val.setText(v)
        if accent:
            self.val.setStyleSheet(f"color:{accent};font-size:20px;font-weight:600;")


# ---------------------------------------------------------------------------
# Matplotlib chart canvas
# ---------------------------------------------------------------------------

class ChartCanvas(FigureCanvas):
    def __init__(self, parent=None):
        self.fig = Figure(figsize=(5, 2.2), facecolor=DARK["panel"])
        super().__init__(self.fig)
        self.setParent(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.ax = self.fig.add_subplot(111)
        self._style_ax()
        self.fig.tight_layout(pad=0.6)

    def _style_ax(self):
        ax = self.ax
        ax.set_facecolor(DARK["panel"])
        ax.tick_params(colors=DARK["text_dim"], labelsize=9)
        ax.spines[:].set_color(DARK["border"])
        for spine in ax.spines.values():
            spine.set_linewidth(0.8)
        ax.yaxis.label.set_color(DARK["text_dim"])
        ax.xaxis.label.set_color(DARK["text_dim"])

    def plot_reference(self, closes, dates=None, ticker="Reference"):
        self.ax.cla()
        self._style_ax()
        x = range(len(closes))
        self.ax.plot(x, closes, color=DARK["amber"], linewidth=1.8, label=ticker)
        self.ax.set_title(f"{ticker} — Price Chart", color=DARK["text_dim"],
                          fontsize=10, pad=6, loc="left")
        self.ax.legend(fontsize=9, labelcolor=DARK["text_dim"],
                       facecolor=DARK["panel"], edgecolor=DARK["border"])
        self.ax.yaxis.set_major_formatter(
            matplotlib.ticker.FuncFormatter(lambda v, _: f"₹{v:,.0f}")
        )
        self.fig.tight_layout(pad=0.6)
        self.draw()

    def plot_comparison(self, ref_closes, cand_closes, ref_label, cand_label):
        """Normalised overlay — both series on 0-1 scale for shape comparison."""
        self.ax.cla()
        self._style_ax()
        rn = normalize(np.array(ref_closes, dtype=float))
        cn = normalize(np.array(cand_closes, dtype=float))
        # resample to same length
        if len(cn) != len(rn):
            xo = np.linspace(0, 1, len(cn))
            xn = np.linspace(0, 1, len(rn))
            cn = np.interp(xn, xo, cn)
        x = range(len(rn))
        self.ax.plot(x, rn, color=DARK["amber"],  linewidth=1.6,
                     linestyle="--", label=ref_label, alpha=0.8)
        self.ax.plot(x, cn, color=DARK["blue"],   linewidth=2.0, label=cand_label)
        self.ax.set_title("Shape comparison (normalised)",
                          color=DARK["text_dim"], fontsize=10, pad=6, loc="left")
        self.ax.set_ylabel("Normalised price", color=DARK["text_dim"], fontsize=9)
        self.ax.legend(fontsize=9, labelcolor=DARK["text_dim"],
                       facecolor=DARK["panel"], edgecolor=DARK["border"])
        self.fig.tight_layout(pad=0.6)
        self.draw()

    def clear(self):
        self.ax.cla()
        self._style_ax()
        self.draw()


# ---------------------------------------------------------------------------
# Results table
# ---------------------------------------------------------------------------

COLUMNS = [
    ("#",            36,  Qt.AlignmentFlag.AlignCenter),
    ("Ticker",       85,  Qt.AlignmentFlag.AlignLeft),
    ("Similarity",   72,  Qt.AlignmentFlag.AlignRight),
    ("Fund \u2b50",      62,  Qt.AlignmentFlag.AlignRight),
    ("Tech \u2b50",      62,  Qt.AlignmentFlag.AlignRight),
    ("Return",       68,  Qt.AlignmentFlag.AlignRight),
    ("Price \u20b9",      75,  Qt.AlignmentFlag.AlignRight),
    ("Mkt Cap",      88,  Qt.AlignmentFlag.AlignRight),
    ("P/E",          52,  Qt.AlignmentFlag.AlignRight),
    ("ROE",          52,  Qt.AlignmentFlag.AlignRight),
    ("D/E",          52,  Qt.AlignmentFlag.AlignRight),
    ("Margin",       58,  Qt.AlignmentFlag.AlignRight),
    ("RSI",          45,  Qt.AlignmentFlag.AlignRight),
    ("SMA",          60,  Qt.AlignmentFlag.AlignRight),
    ("MACD",         58,  Qt.AlignmentFlag.AlignRight),
    ("ADX",          45,  Qt.AlignmentFlag.AlignRight),
]


class ResultsTable(QTableWidget):
    row_selected = pyqtSignal(dict)   # emits the full result row dict

    def __init__(self):
        super().__init__()
        self.setColumnCount(len(COLUMNS))
        self.setHorizontalHeaderLabels([c[0] for c in COLUMNS])
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setSortingEnabled(True)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.verticalHeader().setVisible(False)
        self.setShowGrid(False)

        hdr = self.horizontalHeader()
        for i, (_, width, _) in enumerate(COLUMNS):
            self.setColumnWidth(i, width)
        hdr.setStretchLastSection(False)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)  # ticker stretches

        self.itemSelectionChanged.connect(self._on_selection)
        self._data = []   # list of result dicts, parallel to table rows

    def load(self, results: list):
        self._data = results
        self.setRowCount(0)
        self.setSortingEnabled(False)

        for i, r in enumerate(results):
            self.insertRow(i)
            self.setRowHeight(i, 34)

            def cell(text, col_idx, align=None, color=None):
                item = QTableWidgetItem(str(text))
                a = align or COLUMNS[col_idx][2]
                item.setTextAlignment(a | Qt.AlignmentFlag.AlignVCenter)
                if color:
                    item.setForeground(QColor(color))
                item.setData(Qt.ItemDataRole.UserRole, r)  # store row dict
                return item

            ret_color = DARK["green"] if r.get("pct_return", 0) >= 0 else DARK["red"]
            sim_color = (
                DARK["green"] if r.get("similarity_score", 0) >= 80
                else DARK["amber"] if r.get("similarity_score", 0) >= 65
                else DARK["text"]
            )

            # RSI color: green 40-70, amber 30-40/70-80, red outside
            rsi_val = r.get("rsi")
            rsi_color = DARK["text_dim"]
            if rsi_val is not None:
                if 40 <= rsi_val <= 70:
                    rsi_color = DARK["green"]
                elif 30 <= rsi_val <= 80:
                    rsi_color = DARK["amber"]
                else:
                    rsi_color = DARK["red"]

            # MACD color
            macd_bull = r.get("macd_bullish")
            macd_text = "—"
            macd_color = DARK["text_dim"]
            if macd_bull is True:
                macd_text = "\u25b2 Bull"
                macd_color = DARK["green"]
            elif macd_bull is False:
                macd_text = "\u25bc Bear"
                macd_color = DARK["red"]

            # SMA signal color
            above_50 = r.get("above_sma_50")
            above_200 = r.get("above_sma_200")
            sma_text = fmt_sma_signal(above_50, above_200)
            sma_color = DARK["green"] if (above_50 or above_200) else DARK["red"] if sma_text == "Below" else DARK["text_dim"]

            col = 0
            self.setItem(i, col, cell(i + 1, col)); col += 1
            self.setItem(i, col, cell(r.get("ticker","").replace(".NS",""), col)); col += 1
            self.setItem(i, col, cell(f"{r.get('similarity_score',0):.1f}", col, color=sim_color)); col += 1
            self.setItem(i, col, cell(fmt_score(r.get("fund_score")), col, color=score_color(r.get("fund_score")))); col += 1
            self.setItem(i, col, cell(fmt_score(r.get("tech_score")), col, color=score_color(r.get("tech_score")))); col += 1
            self.setItem(i, col, cell(fmt_pct(r.get("pct_return")), col, color=ret_color)); col += 1
            self.setItem(i, col, cell(
                f"₹{r['current_price']:,.1f}" if r.get("current_price") else "—", col
            )); col += 1
            self.setItem(i, col, cell(fmt_cap(r.get("market_cap")), col)); col += 1
            self.setItem(i, col, cell(
                f"{r['pe_ratio']:.1f}" if r.get("pe_ratio") else "—", col
            )); col += 1
            self.setItem(i, col, cell(fmt_roe(r.get("roe")), col)); col += 1
            self.setItem(i, col, cell(
                f"{r['debt_to_equity']/100:.2f}" if r.get("debt_to_equity") is not None else "—", col
            )); col += 1
            self.setItem(i, col, cell(
                f"{r['profit_margin']*100:.1f}%" if r.get("profit_margin") is not None else "—", col
            )); col += 1
            self.setItem(i, col, cell(
                f"{rsi_val:.0f}" if rsi_val is not None else "—", col, color=rsi_color
            )); col += 1
            self.setItem(i, col, cell(sma_text, col, color=sma_color)); col += 1
            self.setItem(i, col, cell(macd_text, col, color=macd_color)); col += 1
            self.setItem(i, col, cell(
                f"{r['adx']:.0f}" if r.get("adx") is not None else "—", col
            )); col += 1

        self.setSortingEnabled(True)

    def _on_selection(self):
        rows = self.selectedItems()
        if not rows:
            return
        row_dict = rows[0].data(Qt.ItemDataRole.UserRole)
        if row_dict:
            self.row_selected.emit(row_dict)

    def get_all_data(self):
        return self._data


# ---------------------------------------------------------------------------
# Settings panel
# ---------------------------------------------------------------------------

class SettingsPanel(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(0, 0, 0, 0)

        # ── Reference & scan ───────────────────────────────────────────
        grp_scan = QGroupBox("Scan Settings")
        g = QGridLayout(grp_scan)
        g.setSpacing(8)
        g.setContentsMargins(12, 18, 12, 12)

        def add_label(text, tooltip, row, col=0):
            lbl = QLabel(f"{text} ℹ")
            lbl.setToolTip(tooltip)
            g.addWidget(lbl, row, col)

        add_label("Reference stock:", "Leave blank to just find all uptrend stocks.", 0)
        self.ref_input = QLineEdit()
        self.ref_input.setPlaceholderText("e.g. RELIANCE (optional)")
        g.addWidget(self.ref_input, 0, 1)

        add_label("Data source:", "yfinance: Yahoo Finance (easier, unofficial)\nnse: NSE official Bhavcopy archive", 1)
        self.source_combo = QComboBox()
        self.source_combo.addItems(["yfinance", "nse"])
        g.addWidget(self.source_combo, 1, 1)

        add_label("Lookback (days):", "Number of trading days to analyze.", 2)
        self.lookback_spin = QSpinBox()
        self.lookback_spin.setRange(10, 365)
        self.lookback_spin.setValue(60)
        self.lookback_spin.setSuffix(" days")
        g.addWidget(self.lookback_spin, 2, 1)

        add_label("Top N results:", "0 = show all matches (no cap).", 3)
        self.topn_spin = QSpinBox()
        self.topn_spin.setRange(0, 1000)
        self.topn_spin.setValue(0)
        self.topn_spin.setSpecialValueText("All matches")
        g.addWidget(self.topn_spin, 3, 1)

        add_label("Min trend slope:", "0 = any uptrend; raise to demand stronger slope.", 4)
        self.slope_spin = QDoubleSpinBox()
        self.slope_spin.setRange(0.0, 0.05)
        self.slope_spin.setSingleStep(0.0005)
        self.slope_spin.setDecimals(4)
        self.slope_spin.setValue(0.0)
        g.addWidget(self.slope_spin, 4, 1)

        add_label("Request delay (s):", "Pause between API requests to avoid rate-limiting.", 5)
        self.delay_spin = QDoubleSpinBox()
        self.delay_spin.setRange(0.0, 5.0)
        self.delay_spin.setSingleStep(0.1)
        self.delay_spin.setValue(0.3)
        g.addWidget(self.delay_spin, 5, 1)

        layout.addWidget(grp_scan)

        # ── Fundamentals toggle ─────────────────────────────────────────
        grp_fund = QGroupBox("Fundamentals & Scores")
        gf = QVBoxLayout(grp_fund)
        gf.setContentsMargins(12, 18, 12, 12)
        self.fund_check = QCheckBox("Fetch fundamentals + scores\n(P/E, ROE, D/E, margin, growth…)")
        self.fund_check.setToolTip(
            "Fetches fundamentals from yfinance for shortlisted tickers.\n"
            "Computes Fund Score (0–100) for quick filtering.\n"
            "Tech Score is always computed from price data (free).\n"
            "Off by default to keep scans fast."
        )
        gf.addWidget(self.fund_check)
        layout.addWidget(grp_fund)

        # ── Custom ticker file ─────────────────────────────────────────
        grp_tickers = QGroupBox("Candidate Universe")
        gt = QVBoxLayout(grp_tickers)
        gt.setContentsMargins(12, 18, 12, 12)
        gt.setSpacing(6)
        self.custom_file_label = QLabel("Using: built-in Nifty 500 snapshot")
        self.custom_file_label.setStyleSheet(f"color:{DARK['text_dim']};font-size:12px;")
        gt.addWidget(self.custom_file_label)
        self.btn_browse = QPushButton("Browse custom ticker CSV…")
        self.btn_browse.clicked.connect(self._browse_tickers)
        gt.addWidget(self.btn_browse)
        self._custom_tickers_file = None
        layout.addWidget(grp_tickers)

        layout.addStretch()

    def _browse_tickers(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select ticker CSV", "", "CSV files (*.csv);;All files (*)"
        )
        if path:
            self._custom_tickers_file = path
            self.custom_file_label.setText(f"Using: {os.path.basename(path)}")

    def get_params(self, script_dir: str) -> dict:
        return {
            "script_dir":       script_dir,
            "reference":        self.ref_input.text().strip().upper(),
            "source":           self.source_combo.currentText(),
            "lookback":         self.lookback_spin.value(),
            "top_n":            self.topn_spin.value() or None,
            "min_slope":        self.slope_spin.value(),
            "delay":            self.delay_spin.value(),
            "with_fundamentals": self.fund_check.isChecked(),
            "tickers_file":     self._custom_tickers_file,
        }


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self, script_dir: str):
        super().__init__()
        self.script_dir = script_dir
        self.data = None          # last screener output dict
        self.worker = None        # ScreenerWorker thread

        self.setWindowTitle("NSE Shape Screener")
        self.setMinimumSize(1200, 780)
        self.resize(1380, 860)

        self._build_ui()
        self.setStyleSheet(QSS)
        self._set_status("Ready — configure settings and click Run Scan.")

    # ── UI construction ──────────────────────────────────────────────────

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        # Left sidebar: settings + run controls
        sidebar = QWidget()
        sidebar.setFixedWidth(270)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(10)

        # App title
        title = QLabel("NSE Shape Screener")
        title.setStyleSheet(f"font-size:16px;font-weight:700;color:{DARK['text']};padding:4px 0;")
        subtitle = QLabel("Candlestick pattern similarity — daily TF")
        subtitle.setStyleSheet(f"font-size:11px;color:{DARK['text_dim']};padding-bottom:8px;")
        sidebar_layout.addWidget(title)
        sidebar_layout.addWidget(subtitle)

        # Settings panel
        self.settings = SettingsPanel()
        sidebar_layout.addWidget(self.settings)

        # Run / Stop buttons
        btn_row = QHBoxLayout()
        self.btn_run = QPushButton("▶  Run Scan")
        self.btn_run.setObjectName("btn_run")
        self.btn_run.clicked.connect(self._start_scan)
        self.btn_stop = QPushButton("■  Stop")
        self.btn_stop.setObjectName("btn_stop")
        self.btn_stop.clicked.connect(self._stop_scan)
        self.btn_stop.setEnabled(False)
        btn_row.addWidget(self.btn_run)
        btn_row.addWidget(self.btn_stop)
        sidebar_layout.addLayout(btn_row)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(6)
        self.progress_bar.setValue(0)
        sidebar_layout.addWidget(self.progress_bar)

        # Log console
        log_label = QLabel("SCAN LOG")
        log_label.setObjectName("section_title")
        sidebar_layout.addWidget(log_label)
        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setFixedHeight(160)
        sidebar_layout.addWidget(self.log_box)

        root.addWidget(sidebar)

        # Right main area
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(10)

        # KPI bar
        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(8)
        self.kpi_matches  = KpiCard("Matches",   "—",  DARK["blue"])
        self.kpi_avg_sim  = KpiCard("Avg sim",   "—",  DARK["text"])
        self.kpi_top_gain = KpiCard("Top gainer","—",  DARK["green"])
        self.kpi_ref      = KpiCard("Reference", "—",  DARK["amber"])
        self.kpi_scanned  = KpiCard("Scanned",   "—",  DARK["text_dim"])
        for kpi in [self.kpi_matches, self.kpi_avg_sim, self.kpi_top_gain,
                    self.kpi_ref, self.kpi_scanned]:
            kpi_row.addWidget(kpi)
        right_layout.addLayout(kpi_row)

        # Main splitter: table (top) + chart area (bottom)
        vsplit = QSplitter(Qt.Orientation.Vertical)
        vsplit.setHandleWidth(6)

        # Top half: filter controls + results table
        table_widget = QWidget()
        table_layout = QVBoxLayout(table_widget)
        table_layout.setContentsMargins(0, 0, 0, 0)
        table_layout.setSpacing(6)

        # Filter row above the table
        filter_row = QHBoxLayout()
        filter_row.setSpacing(8)

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search ticker…")
        self.search_box.setFixedWidth(160)
        self.search_box.textChanged.connect(self._apply_filter)
        filter_row.addWidget(QLabel("Filter:"))
        filter_row.addWidget(self.search_box)

        filter_row.addWidget(QLabel("Min similarity:"))
        self.sim_slider = QSlider(Qt.Orientation.Horizontal)
        self.sim_slider.setRange(0, 95)
        self.sim_slider.setValue(0)
        self.sim_slider.setSingleStep(5)
        self.sim_slider.setPageStep(10)
        self.sim_slider.setFixedWidth(100)
        self.sim_slider.valueChanged.connect(self._apply_filter)
        self.sim_label = QLabel("0")
        self.sim_label.setFixedWidth(24)
        self.sim_label.setStyleSheet(f"color:{DARK['amber']};font-weight:600;")
        filter_row.addWidget(self.sim_slider)
        filter_row.addWidget(self.sim_label)

        # NEW: Fund Score filter
        filter_row.addWidget(QLabel("Fund\u2265:"))
        self.fund_slider = QSlider(Qt.Orientation.Horizontal)
        self.fund_slider.setRange(0, 95)
        self.fund_slider.setValue(0)
        self.fund_slider.setSingleStep(5)
        self.fund_slider.setFixedWidth(80)
        self.fund_slider.valueChanged.connect(self._apply_filter)
        self.fund_label = QLabel("0")
        self.fund_label.setFixedWidth(24)
        self.fund_label.setStyleSheet(f"color:{DARK['green']};font-weight:600;")
        filter_row.addWidget(self.fund_slider)
        filter_row.addWidget(self.fund_label)

        # NEW: Tech Score filter
        filter_row.addWidget(QLabel("Tech\u2265:"))
        self.tech_slider = QSlider(Qt.Orientation.Horizontal)
        self.tech_slider.setRange(0, 95)
        self.tech_slider.setValue(0)
        self.tech_slider.setSingleStep(5)
        self.tech_slider.setFixedWidth(80)
        self.tech_slider.valueChanged.connect(self._apply_filter)
        self.tech_label = QLabel("0")
        self.tech_label.setFixedWidth(24)
        self.tech_label.setStyleSheet(f"color:{DARK['blue']};font-weight:600;")
        filter_row.addWidget(self.tech_slider)
        filter_row.addWidget(self.tech_label)

        filter_row.addStretch()

        self.btn_export = QPushButton("⬇ Export CSV")
        self.btn_export.clicked.connect(self._export_csv)
        self.btn_export.setEnabled(False)
        filter_row.addWidget(self.btn_export)

        self.btn_export_json = QPushButton("⬇ Export JSON")
        self.btn_export_json.clicked.connect(self._export_json)
        self.btn_export_json.setEnabled(False)
        filter_row.addWidget(self.btn_export_json)

        self.btn_load_json = QPushButton("📂 Load JSON")
        self.btn_load_json.clicked.connect(self._load_json)
        filter_row.addWidget(self.btn_load_json)

        table_layout.addLayout(filter_row)

        self.table = ResultsTable()
        self.table.row_selected.connect(self._on_row_selected)
        table_layout.addWidget(self.table)

        vsplit.addWidget(table_widget)

        # Bottom half: chart tabs
        chart_tabs = QTabWidget()

        # Tab 1: reference chart
        self.chart_ref = ChartCanvas()
        ref_tab = QWidget()
        ref_tab_layout = QVBoxLayout(ref_tab)
        ref_tab_layout.setContentsMargins(4, 4, 4, 4)
        ref_tab_layout.addWidget(self.chart_ref)
        chart_tabs.addTab(ref_tab, "Reference Pattern")

        # Tab 2: comparison chart (shows when row is selected)
        self.chart_cmp = ChartCanvas()
        cmp_tab = QWidget()
        cmp_tab_layout = QVBoxLayout(cmp_tab)
        cmp_tab_layout.setContentsMargins(4, 4, 4, 4)

        self.cmp_info_label = QLabel(
            "Click a row in the table above to compare its shape with the reference."
        )
        self.cmp_info_label.setStyleSheet(f"color:{DARK['text_dim']};font-size:12px;padding:4px;")
        self.cmp_info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Metrics row below the comparison chart
        self.detail_metrics = QLabel("")
        self.detail_metrics.setStyleSheet(
            f"color:{DARK['text_dim']};font-size:12px;"
            f"background:{DARK['panel']};border-radius:6px;padding:8px 12px;"
        )
        self.detail_metrics.setWordWrap(True)

        cmp_tab_layout.addWidget(self.cmp_info_label)
        cmp_tab_layout.addWidget(self.chart_cmp)
        cmp_tab_layout.addWidget(self.detail_metrics)
        chart_tabs.addTab(cmp_tab, "Shape Comparison")

        vsplit.addWidget(chart_tabs)
        vsplit.setSizes([480, 280])

        right_layout.addWidget(vsplit)
        root.addWidget(right)

        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

    # ── Scan lifecycle ───────────────────────────────────────────────────

    def _start_scan(self):
        params = self.settings.get_params(self.script_dir)
        # reference is now optional

        self.btn_run.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.progress_bar.setValue(0)
        self.progress_bar.setMaximum(0)   # indeterminate spinner until we know total
        self.log_box.clear()
        
        target = params['reference'] if params['reference'] else "Uptrending stocks"
        self._set_status(f"Scanning — {target} via {params['source']}…")

        self.worker = ScreenerWorker(params)
        self.worker.log.connect(self._on_log)
        self.worker.progress.connect(self._on_progress)
        self.worker.finished.connect(self._on_finished)
        self.worker.error.connect(self._on_error)
        self.worker.start()

    def _stop_scan(self):
        if self.worker:
            self.worker.stop()
        self.btn_stop.setEnabled(False)
        self._set_status("Stopping…")

    def _on_log(self, msg: str):
        self.log_box.append(msg)
        self.log_box.verticalScrollBar().setValue(
            self.log_box.verticalScrollBar().maximum()
        )

    def _on_progress(self, done: int, total: int):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(done)
        self._set_status(f"Scanning: {done}/{total} candidates processed…")

    def _on_finished(self, output: dict):
        self.data = output
        self.btn_run.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(100)

        results = output.get("results", [])
        self._update_kpis(output)
        self.table.load(results)
        self.btn_export.setEnabled(bool(results))
        self.btn_export_json.setEnabled(bool(output))

        # Draw reference chart
        ref = output.get("reference", {})
        if ref.get("close"):
            self.chart_ref.plot_reference(
                ref["close"], ref.get("dates"), ref.get("ticker", "").replace(".NS", "")
            )

        n = len(results)
        self._set_status(
            f"✓ Scan complete — {n} match{'es' if n != 1 else ''} found "
            f"out of {output.get('scanned_count','?')} scanned."
        )

    def _on_error(self, msg: str):
        self.btn_run.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        self._on_log(f"✗ ERROR:\n{msg}")
        self._set_status("✗ Scan failed — see log for details.")
        QMessageBox.critical(self, "Scan error", msg[:500])

    # ── Data display ─────────────────────────────────────────────────────

    def _update_kpis(self, output: dict):
        results = output.get("results", [])
        ref = output.get("reference", {})
        ref_ticker = ref.get("ticker", "—").replace(".NS", "")

        avg_sim = (
            sum(r["similarity_score"] for r in results) / len(results)
            if results else 0
        )
        top_gainer = (
            max(results, key=lambda r: r.get("pct_return", 0))
            if results else None
        )

        self.kpi_matches.set_value(str(len(results)), DARK["blue"])
        self.kpi_avg_sim.set_value(f"{avg_sim:.1f}")
        self.kpi_top_gain.set_value(
            fmt_pct(top_gainer["pct_return"]) if top_gainer else "—",
            DARK["green"]
        )
        self.kpi_ref.set_value(ref_ticker, DARK["amber"])
        self.kpi_scanned.set_value(str(output.get("scanned_count", "—")))

    def _on_row_selected(self, row: dict):
        if not self.data:
            return
        cand_closes = self.data.get("candidates_close", {}).get(row["ticker"], [])
        ref_closes  = self.data["reference"].get("close", [])
        ref_label   = self.data["reference"].get("ticker", "Ref").replace(".NS", "")
        cand_label  = row["ticker"].replace(".NS", "")

        if cand_closes:
            if ref_closes:
                self.chart_cmp.plot_comparison(ref_closes, cand_closes, ref_label, cand_label)
            else:
                self.chart_cmp.plot_reference(cand_closes, None, cand_label)
            # Switch to comparison tab automatically
            chart_tabs = self.chart_cmp.parent().parent()
            if hasattr(chart_tabs, 'setCurrentIndex'):
                chart_tabs.setCurrentIndex(1)

        # Update detail metrics label
        parts = [
            f"<b style='color:{DARK['text']}'>{cand_label}</b>",
            f"Sim: <b style='color:{DARK['blue']}'>{row.get('similarity_score','—'):.1f}</b>",
        ]
        # Scores
        fs = row.get("fund_score")
        ts = row.get("tech_score")
        if fs is not None:
            parts.append(f"Fund: <b style='color:{score_color(fs)}'>{fs:.0f}</b>")
        if ts is not None:
            parts.append(f"Tech: <b style='color:{score_color(ts)}'>{ts:.0f}</b>")
        # Return
        parts.append(
            f"Return: <b style='color:{DARK['green'] if row.get('pct_return',0)>=0 else DARK['red']}'>"
            f"{fmt_pct(row.get('pct_return'))}</b>"
        )
        # Fundamentals
        if row.get("pe_ratio"):
            parts.append(f"P/E: <b>{row['pe_ratio']:.1f}</b>")
        if row.get("roe") is not None:
            parts.append(f"ROE: <b>{fmt_roe(row['roe'])}</b>")
        if row.get("debt_to_equity") is not None:
            parts.append(f"D/E: <b>{row['debt_to_equity']/100:.2f}</b>")
        if row.get("market_cap"):
            parts.append(f"MCap: <b>{fmt_cap(row['market_cap'])}</b>")
        # Technicals
        if row.get("rsi") is not None:
            parts.append(f"RSI: <b>{row['rsi']:.0f}</b>")
        macd_b = row.get("macd_bullish")
        if macd_b is not None:
            parts.append(f"MACD: <b style='color:{DARK['green'] if macd_b else DARK['red']}'>{'Bull' if macd_b else 'Bear'}</b>")
        if row.get("adx") is not None:
            parts.append(f"ADX: <b>{row['adx']:.0f}</b>")
        self.detail_metrics.setText("&nbsp;&nbsp;|&nbsp;&nbsp;".join(parts))

    def _apply_filter(self):
        if not self.data:
            return
        q = self.search_box.text().strip().upper()
        min_sim = self.sim_slider.value()
        min_fund = self.fund_slider.value()
        min_tech = self.tech_slider.value()
        self.sim_label.setText(str(min_sim))
        self.fund_label.setText(str(min_fund))
        self.tech_label.setText(str(min_tech))

        all_results = self.data.get("results", [])
        filtered = [
            r for r in all_results
            if (not q or q in r["ticker"].replace(".NS", ""))
            and r.get("similarity_score", 0) >= min_sim
            and (r.get("fund_score") or 0) >= min_fund
            and (r.get("tech_score") or 0) >= min_tech
        ]
        self.table.load(filtered)

    def _export_csv(self):
        if not self.data:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export results", "nse_screener_results.csv",
            "CSV files (*.csv)"
        )
        if not path:
            return

        results = self.table.get_all_data()
        fieldnames = [
            "ticker", "similarity_score", "fund_score", "tech_score",
            "pct_return", "trend_slope", "dtw_distance",
            "current_price", "market_cap",
            "pe_ratio", "roe", "debt_to_equity", "profit_margin",
            "revenue_growth", "eps", "pb_ratio", "free_cash_flow",
            "dividend_yield", "quick_ratio",
            "rsi", "above_sma_50", "above_sma_200", "macd_bullish", "adx",
        ]
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(results)

        self._set_status(f"Exported {len(results)} rows → {path}")
        QMessageBox.information(self, "Export complete",
                                f"Saved {len(results)} rows to:\n{path}")

    def _load_json(self):
        """Load a previously saved screener_output.json directly into the UI."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Load screener output", "",
            "JSON files (*.json);;All files (*)"
        )
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as f:
                output = json.load(f)
            self._on_finished(output)
            self._on_log(f"Loaded from file: {path}")
        except Exception as e:
            QMessageBox.critical(self, "Load failed", str(e))

    def _export_json(self):
        if not hasattr(self, "data") or not self.data:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export JSON", "output/screener_output.json",
            "JSON files (*.json)"
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2)
            self._set_status(f"✓ Exported to {path}.")
        except Exception as e:
            self._on_error(f"Failed to export JSON: {str(e)}")

    def _set_status(self, msg: str):
        self.status_bar.showMessage(msg)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    # Script directory = where the backend modules live.
    # When running as a standalone script, __file__ is in the same folder.
    script_dir = os.path.dirname(os.path.abspath(__file__))

    app = QApplication(sys.argv)
    app.setApplicationName("NSE Shape Screener")

    # Force dark palette at OS level so native widgets (scrollbars, etc.)
    # also go dark where QSS doesn't reach them.
    palette = QPalette()
    bg = QColor(DARK["bg"])
    palette.setColor(QPalette.ColorRole.Window,      bg)
    palette.setColor(QPalette.ColorRole.WindowText,  QColor(DARK["text"]))
    palette.setColor(QPalette.ColorRole.Base,        QColor(DARK["panel"]))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(DARK["row_alt"]))
    palette.setColor(QPalette.ColorRole.Text,        QColor(DARK["text"]))
    palette.setColor(QPalette.ColorRole.Button,      QColor(DARK["row"]))
    palette.setColor(QPalette.ColorRole.ButtonText,  QColor(DARK["text"]))
    palette.setColor(QPalette.ColorRole.Highlight,   QColor(DARK["blue"]))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    app.setPalette(palette)

    win = MainWindow(script_dir)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
