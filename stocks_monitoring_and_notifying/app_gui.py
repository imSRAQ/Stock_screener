import sys
import os
import traceback
import numpy as np

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGroupBox, QLabel, QSpinBox, QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QSplitter, QStatusBar, QProgressBar, QMessageBox, QTabWidget,
    QLineEdit, QCheckBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal

import matplotlib
matplotlib.use("QtAgg")
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from data_fetcher import DataFetcher
from uptrend_analyzer import UptrendAnalyzer
from watchlist_manager import WatchlistManager
from config_manager import ConfigManager
from telegram_notifier import TelegramNotifier

class ScannerThread(QThread):
    progress = pyqtSignal(int, int)
    finished = pyqtSignal(list, dict)
    error = pyqtSignal(str)

    def __init__(self, config: ConfigManager):
        super().__init__()
        self.config = config

    def run(self):
        try:
            filters = self.config.filters
            lookback_days = filters.get("lookback_days", 90)
            sma_long = filters.get("sma_long", 200)
            
            # Need enough days for the longest indicator
            fetch_days = max(lookback_days, sma_long) + 20
            
            fetcher = DataFetcher()
            def progress_callback(current, total):
                self.progress.emit(current, total)
                
            universe_data = fetcher.fetch_all_universe(period_days=fetch_days, progress_callback=progress_callback)
            
            if not universe_data:
                self.error.emit("Failed to fetch data or empty universe.")
                return

            analyzer = UptrendAnalyzer(
                sma_short=filters.get("sma_short", 50),
                sma_long=sma_long,
                rsi_min=filters.get("rsi_min", 40.0),
                rsi_max=filters.get("rsi_max", 65.0),
                adx_min=filters.get("adx_min", 25.0),
                volume_ratio_min=filters.get("volume_ratio_min", 1.0),
                atr_multiplier=filters.get("atr_stop_loss_multiplier", 1.5)
            )
            
            results = analyzer.filter_and_rank(universe_data, lookback_days=lookback_days)
            self.finished.emit(results, universe_data)
        except Exception as e:
            self.error.emit(traceback.format_exc())


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("NSE Uptrend Scanner")
        self.resize(1100, 700)
        
        self.config = ConfigManager()
        self.watchlist_mgr = WatchlistManager()
        self.notifier = TelegramNotifier(self.config, self.watchlist_mgr)
        
        # Start Telegram bot listener if configured
        if self.notifier.is_configured:
            self.notifier.start_bot_listener()
            
        self.universe_data = {}
        self.scanner_thread = None

        self._setup_ui()

    def _setup_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)

        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)
        
        # --- Scanner Tab ---
        scanner_tab = QWidget()
        scanner_layout = QVBoxLayout(scanner_tab)
        
        controls_group = QGroupBox("Scan Settings")
        controls_layout = QHBoxLayout(controls_group)
        
        # Add Hourly Toggle
        self.chk_hourly = QCheckBox("Enable Hourly Scans")
        self.chk_hourly.setChecked(self.config.hourly_enabled)
        self.chk_hourly.stateChanged.connect(self.on_hourly_toggled)
        controls_layout.addWidget(self.chk_hourly)
        
        controls_layout.addStretch()
        
        self.btn_run = QPushButton("Run Full Scan")
        self.btn_run.clicked.connect(self.start_scan)
        controls_layout.addWidget(self.btn_run)
        
        scanner_layout.addWidget(controls_group)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        scanner_layout.addWidget(splitter)

        self.table = QTableWidget()
        self.table.setColumnCount(10)
        self.table.setHorizontalHeaderLabels([
            "Symbol", "Price", "50 SMA", "200 SMA", "Slope",
            "RSI", "ADX", "Vol Ratio", "Stop Loss", "Watch"
        ])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self.on_table_selection)
        splitter.addWidget(self.table)

        self.figure = Figure(figsize=(5, 4), dpi=100)
        self.canvas = FigureCanvas(self.figure)
        self.ax = self.figure.add_subplot(111)
        self.ax.set_title("Select a stock to view chart")
        splitter.addWidget(self.canvas)
        
        splitter.setSizes([700, 400])
        self.tabs.addTab(scanner_tab, "Uptrend Scanner")
        
        # --- Watchlist Tab ---
        watchlist_tab = QWidget()
        wl_layout = QVBoxLayout(watchlist_tab)
        
        wl_controls = QHBoxLayout()
        wl_controls.addWidget(QLabel("Add Symbol:"))
        self.txt_add_symbol = QLineEdit()
        wl_controls.addWidget(self.txt_add_symbol)
        
        btn_add = QPushButton("Add to Watchlist")
        btn_add.clicked.connect(self.add_to_watchlist)
        wl_controls.addWidget(btn_add)
        
        btn_remove = QPushButton("Remove Selected")
        btn_remove.clicked.connect(self.remove_from_watchlist)
        wl_controls.addWidget(btn_remove)
        wl_controls.addStretch()
        
        wl_layout.addLayout(wl_controls)
        
        self.wl_table = QTableWidget()
        self.wl_table.setColumnCount(1)
        self.wl_table.setHorizontalHeaderLabels(["Symbol"])
        self.wl_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.wl_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.wl_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        wl_layout.addWidget(self.wl_table)
        
        self.tabs.addTab(watchlist_tab, "Special Watchlist")
        
        self.tabs.currentChanged.connect(self.refresh_watchlist_ui)

        # Status Bar
        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximumWidth(300)
        self.progress_bar.setVisible(False)
        self.status.addPermanentWidget(self.progress_bar)

    def on_hourly_toggled(self, state):
        self.config.hourly_enabled = (state == Qt.CheckState.Checked.value)
        self.config.save()

    def start_scan(self):
        self.btn_run.setEnabled(False)
        self.table.setRowCount(0)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.status.showMessage("Fetching data... this may take a few minutes if cache is cold.")

        self.scanner_thread = ScannerThread(self.config)
        self.scanner_thread.progress.connect(self.on_progress)
        self.scanner_thread.finished.connect(self.on_scan_finished)
        self.scanner_thread.error.connect(self.on_scan_error)
        self.scanner_thread.start()

    def on_progress(self, current, total):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)

    def on_scan_finished(self, results, universe_data):
        self.universe_data = universe_data
        self.progress_bar.setVisible(False)
        self.btn_run.setEnabled(True)
        
        if not results:
            self.status.showMessage("Scan complete: No stocks found matching criteria.")
            return

        self.status.showMessage(f"Scan complete: Found {len(results)} matching stocks.")
        
        self.table.setRowCount(len(results))
        for row, data in enumerate(results):
            self.table.setItem(row, 0, QTableWidgetItem(data["symbol"]))
            self.table.setItem(row, 1, QTableWidgetItem(f"{data['price']:.2f}"))
            self.table.setItem(row, 2, QTableWidgetItem(f"{data['sma_50']:.2f}"))
            self.table.setItem(row, 3, QTableWidgetItem(f"{data['sma_200']:.2f}"))
            self.table.setItem(row, 4, QTableWidgetItem(f"{data['slope']:.4f}"))
            self.table.setItem(row, 5, QTableWidgetItem(f"{data['rsi']:.1f}"))
            self.table.setItem(row, 6, QTableWidgetItem(f"{data['adx']:.1f}"))
            self.table.setItem(row, 7, QTableWidgetItem(f"{data['volume_ratio']:.2f}"))
            self.table.setItem(row, 8, QTableWidgetItem(f"{data['stop_loss']:.2f}"))
            
            btn_watch = QPushButton("Watch")
            btn_watch.clicked.connect(lambda _, s=data['symbol']: self.watchlist_mgr.add(s))
            self.table.setCellWidget(row, 9, btn_watch)

        self.table.resizeColumnsToContents()

    def on_scan_error(self, error_msg):
        self.progress_bar.setVisible(False)
        self.btn_run.setEnabled(True)
        self.status.showMessage("Scan failed.")
        QMessageBox.critical(self, "Error", f"An error occurred during scan:\n{error_msg}")

    def on_table_selection(self):
        selected_items = self.table.selectedItems()
        if not selected_items:
            return
        
        symbol = self.table.item(selected_items[0].row(), 0).text()
        
        if symbol not in self.universe_data:
            return
        
        data = self.universe_data[symbol]
        if isinstance(data, dict):
            prices = data["close"]
        else:
            prices = data
            
        self.ax.clear()
        
        # Plot prices
        self.ax.plot(prices, label="Close", color="blue")
        
        # Calculate and plot SMAs
        if len(prices) >= 50:
            sma_50 = np.convolve(prices, np.ones(50)/50, mode='valid')
            x_50 = np.arange(49, len(prices))
            self.ax.plot(x_50, sma_50, label="50 SMA", color="orange")
            
        if len(prices) >= 200:
            sma_200 = np.convolve(prices, np.ones(200)/200, mode='valid')
            x_200 = np.arange(199, len(prices))
            self.ax.plot(x_200, sma_200, label="200 SMA", color="red")
            
        self.ax.set_title(f"{symbol} - Price History")
        self.ax.legend()
        self.canvas.draw()
        
    def refresh_watchlist_ui(self):
        items = self.watchlist_mgr.get_all()
        self.wl_table.setRowCount(len(items))
        for row, symbol in enumerate(items):
            self.wl_table.setItem(row, 0, QTableWidgetItem(symbol))
            
    def add_to_watchlist(self):
        sym = self.txt_add_symbol.text()
        if sym:
            if self.watchlist_mgr.add(sym):
                self.txt_add_symbol.clear()
                self.refresh_watchlist_ui()
                self.status.showMessage(f"Added {sym} to watchlist.")
            else:
                self.status.showMessage(f"{sym} already in watchlist.")
                
    def remove_from_watchlist(self):
        selected = self.wl_table.selectedItems()
        if not selected:
            return
            
        sym = selected[0].text()
        if self.watchlist_mgr.remove(sym):
            self.refresh_watchlist_ui()
            self.status.showMessage(f"Removed {sym} from watchlist.")

