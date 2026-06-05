from datetime import datetime
from pathlib import Path

from PyQt5.QtCore import QThread, QTimer, Qt
from PyQt5.QtWidgets import (
    QAction,
    QFileDialog,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QWidget,
    QVBoxLayout,
)

from modbus_master import __version__
from modbus_master.core.data_types import decode_registers, encode_value, registers_to_hex, required_registers
from modbus_master.core.modbus_client import ModbusClient
from modbus_master.core.session import SessionData, load_last_session, load_session, save_last_session, save_session
from modbus_master.ui.connection_panel import ConnectionPanel
from modbus_master.ui.log_panel import LogPanel
from modbus_master.ui.register_table import RegisterTable
from modbus_master.ui.scanner_panel import ScannerPanel, ScannerWorker


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Modbus Master Simulator")
        self.resize(1380, 860)

        self.client = ModbusClient()
        self.error_count = 0
        self.scanner_thread: QThread | None = None
        self.scanner_worker: ScannerWorker | None = None

        self.connection_panel = ConnectionPanel()
        self.register_table = RegisterTable()
        self.scanner_panel = ScannerPanel()
        self.log_panel = LogPanel()

        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self.poll_registers)

        self._build_layout()
        self._build_menu()
        self._build_status_bar()
        self._connect_signals()
        self.setStyleSheet(self._dark_stylesheet())

        self.restore_last_session()
        self.poll_timer.start(self.register_table.interval_spin.value())

    def _build_layout(self) -> None:
        main_splitter = QSplitter(Qt.Horizontal)
        main_splitter.addWidget(self.scanner_panel)
        main_splitter.addWidget(self.register_table)
        main_splitter.setStretchFactor(0, 1)
        main_splitter.setStretchFactor(1, 3)

        vertical_splitter = QSplitter(Qt.Vertical)
        vertical_splitter.addWidget(main_splitter)
        vertical_splitter.addWidget(self.log_panel)
        vertical_splitter.setStretchFactor(0, 5)
        vertical_splitter.setStretchFactor(1, 2)

        root = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.connection_panel)
        layout.addWidget(vertical_splitter, 1)
        root.setLayout(layout)
        self.setCentralWidget(root)

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("File")
        new_action = QAction("New session", self)
        open_action = QAction("Open session...", self)
        save_action = QAction("Save session...", self)
        exit_action = QAction("Exit", self)
        file_menu.addActions([new_action, open_action, save_action])
        file_menu.addSeparator()
        file_menu.addAction(exit_action)

        connection_menu = self.menuBar().addMenu("Connection")
        connect_action = QAction("Connect", self)
        disconnect_action = QAction("Disconnect", self)
        port_settings_action = QAction("Port settings", self)
        connection_menu.addActions([connect_action, disconnect_action, port_settings_action])

        view_menu = self.menuBar().addMenu("View")
        toggle_log = QAction("Toggle Log", self, checkable=True, checked=True)
        toggle_scanner = QAction("Toggle Scanner", self, checkable=True, checked=True)
        view_menu.addActions([toggle_log, toggle_scanner])

        help_menu = self.menuBar().addMenu("Help")
        about_action = QAction("About", self)
        help_menu.addAction(about_action)

        new_action.triggered.connect(self.new_session)
        open_action.triggered.connect(self.open_session)
        save_action.triggered.connect(self.save_session_as)
        exit_action.triggered.connect(self.close)
        connect_action.triggered.connect(lambda: self.connect_modbus(self.connection_panel.config()))
        disconnect_action.triggered.connect(self.disconnect_modbus)
        port_settings_action.triggered.connect(lambda: self.connection_panel.setFocus())
        toggle_log.triggered.connect(self.log_panel.setVisible)
        toggle_scanner.triggered.connect(self.scanner_panel.setVisible)
        about_action.triggered.connect(self.about)

    def _build_status_bar(self) -> None:
        self.connection_status = QLabel("Disconnected")
        self.last_poll_status = QLabel("Last poll: never")
        self.error_status = QLabel("Errors: 0")
        self.statusBar().addWidget(self.connection_status)
        self.statusBar().addPermanentWidget(self.last_poll_status)
        self.statusBar().addPermanentWidget(self.error_status)

    def _connect_signals(self) -> None:
        self.connection_panel.connect_requested.connect(self.connect_modbus)
        self.connection_panel.disconnect_requested.connect(self.disconnect_modbus)
        self.register_table.poll_interval_changed.connect(self.poll_timer.setInterval)
        self.register_table.write_requested.connect(self.write_register)
        self.scanner_panel.scan_requested.connect(self.start_scan)
        self.scanner_panel.cancel_requested.connect(self.cancel_scan)

    def connect_modbus(self, config: dict) -> None:
        try:
            self.client.connect(config)
        except Exception as exc:
            self.connection_panel.set_connected(False)
            self.connection_status.setText("Disconnected")
            self.log(f"Connection failed: {exc}", "Error")
            QMessageBox.warning(self, "Connection failed", str(exc))
            return

        self.connection_panel.set_connected(True)
        self.connection_status.setText(f"Connected ({config.get('mode')})")
        self.log(f"Connected using {config.get('mode')} settings", "Info")

    def disconnect_modbus(self) -> None:
        self.client.disconnect()
        self.connection_panel.set_connected(False)
        self.connection_status.setText("Disconnected")
        self.log("Disconnected", "Info")

    def poll_registers(self) -> None:
        if not self.client.connected or not self.register_table.auto_poll.isChecked():
            return

        for row in range(self.register_table.table.rowCount()):
            if not self.register_table.table.cellWidget(row, 1).isChecked():
                continue
            cfg = self.register_table.row_config(row)
            data_type = cfg["data_type"]
            count = required_registers(data_type, cfg["length"])
            result = self.client.read(cfg["function_code"], cfg["address"], count)
            self.log_modbus(result, f"Poll row {row + 1}")
            if not result.ok:
                self.record_error(result.error or result.status)
                continue

            try:
                value = decode_registers(result.values, data_type)
                raw = " ".join("01" if bool(v) else "00" for v in result.values) if cfg["function_code"] in (1, 2) else registers_to_hex(result.values)
                old = self.register_table.table.item(row, 7).text()
                changed = old not in ("", str(value)) and str(value) != old
                self.register_table.update_row_value(row, str(value), raw, self.timestamp(), changed)
            except Exception as exc:
                self.record_error(str(exc))

        self.last_poll_status.setText(f"Last poll: {self.timestamp()}")

    def write_register(self, row: int) -> None:
        if row < 0 or row >= self.register_table.table.rowCount():
            return
        if not self.client.connected:
            QMessageBox.information(self, "Not connected", "Connect before writing a value.")
            return

        cfg = self.register_table.row_config(row)
        if cfg["function_code"] in (2, 4):
            QMessageBox.warning(self, "Read-only function", "FC02 discrete inputs and FC04 input registers are read-only.")
            return

        value, ok = QInputDialog.getText(self, "Write value", f"New value for address {cfg['address']}:")
        if not ok:
            return
        try:
            registers, coil_value = encode_value(value, cfg["data_type"])
            result = self.client.write(cfg["function_code"], cfg["address"], registers, coil_value)
        except Exception as exc:
            self.record_error(str(exc))
            QMessageBox.warning(self, "Write failed", str(exc))
            return

        self.log_modbus(result, f"Write row {row + 1}")
        if result.ok:
            self.poll_registers()
        else:
            self.record_error(result.error or result.status)
            QMessageBox.warning(self, "Write failed", result.error or result.status)

    def start_scan(self, params: dict) -> None:
        if not self.client.connected:
            QMessageBox.information(self, "Not connected", "Connect before scanning registers.")
            return
        if self.scanner_thread is not None:
            return

        self.scanner_panel.set_scanning(True)
        self.scanner_thread = QThread(self)
        self.scanner_worker = ScannerWorker(self.client, params)
        self.scanner_worker.moveToThread(self.scanner_thread)
        self.scanner_thread.started.connect(self.scanner_worker.run)
        self.scanner_worker.row_ready.connect(self.on_scan_row)
        self.scanner_worker.progress.connect(self.scanner_panel.progress.setValue)
        self.scanner_worker.finished.connect(self.scan_finished)
        self.scanner_worker.finished.connect(self.scanner_thread.quit)
        self.scanner_worker.finished.connect(self.scanner_worker.deleteLater)
        self.scanner_thread.finished.connect(self.scanner_thread.deleteLater)
        self.scanner_thread.start()
        self.log(f"Register scan started: start={params['start']} count={params['count']} fc={params['function_code']}", "Info")

    def cancel_scan(self) -> None:
        if self.scanner_worker:
            self.scanner_worker.cancel()

    def on_scan_row(self, data: dict) -> None:
        self.scanner_panel.add_result(data)
        status = data.get("status", "")
        level = "Info" if data.get("ok") else "Error"
        self.log(f"[{self.timestamp()}] TX: {data.get('tx', '')} | RX: {data.get('rx', '')} | Status: {status}", level)
        if not data.get("ok"):
            self.record_error(status)

    def scan_finished(self) -> None:
        self.scanner_panel.set_scanning(False)
        self.log("Register scan finished", "Info")
        self.scanner_thread = None
        self.scanner_worker = None

    def new_session(self) -> None:
        self.disconnect_modbus()
        self.register_table.load_rows([])
        self.scanner_panel.set_params({})
        self.error_count = 0
        self.error_status.setText("Errors: 0")
        self.log_panel.log_view.clear()

    def open_session(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open session", str(Path.home()), "JSON files (*.json)")
        if not path:
            return
        try:
            self.apply_session(load_session(Path(path)))
            self.log(f"Loaded session: {path}", "Info")
        except Exception as exc:
            QMessageBox.warning(self, "Open session failed", str(exc))

    def save_session_as(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Save session", str(Path.home() / "modbus_session.json"), "JSON files (*.json)")
        if path:
            save_session(Path(path), self.current_session())
            self.log(f"Saved session: {path}", "Info")

    def restore_last_session(self) -> None:
        try:
            self.apply_session(load_last_session())
        except Exception as exc:
            self.log(f"Could not restore last session: {exc}", "Error")
            self.register_table.load_rows([])

    def apply_session(self, session: SessionData) -> None:
        self.connection_panel.set_config(session.connection)
        self.register_table.interval_spin.setValue(session.poll_interval_ms)
        self.register_table.load_rows(session.registers)
        self.scanner_panel.set_params(session.scanner)

    def current_session(self) -> SessionData:
        return SessionData(
            connection=self.connection_panel.config(),
            registers=self.register_table.rows(),
            poll_interval_ms=self.register_table.interval_spin.value(),
            scanner=self.scanner_panel.params(),
        )

    def closeEvent(self, event) -> None:
        if self.scanner_worker:
            self.scanner_worker.cancel()
        try:
            save_last_session(self.current_session())
        except Exception as exc:
            self.log(f"Autosave failed: {exc}", "Error")
        self.disconnect_modbus()
        super().closeEvent(event)

    def about(self) -> None:
        QMessageBox.about(
            self,
            "About",
            f"Modbus Master Simulator\nVersion {__version__}\n\n"
            "Supports Modbus RTU and TCP polling with pymodbus.\n"
            "FC01/FC02 read bits; FC03/FC04 read 16-bit registers. RTU frames use CRC16.",
        )

    def log_modbus(self, result, prefix: str) -> None:
        level = "Info" if result.ok else "Error"
        self.log(
            f"[{self.timestamp()}] {prefix} | TX: {result.tx_hex} | RX: {result.rx_hex} | Status: {result.status}"
            + (f" | {result.error}" if result.error else ""),
            level,
        )

    def log(self, message: str, level: str = "Info") -> None:
        if message.startswith("["):
            line = message
        else:
            line = f"[{self.timestamp()}] {message}"
        self.log_panel.append(line, level)

    def record_error(self, message: str) -> None:
        self.error_count += 1
        self.error_status.setText(f"Errors: {self.error_count}")
        if message:
            self.statusBar().showMessage(message, 5000)

    def timestamp(self) -> str:
        return datetime.now().strftime("%H:%M:%S.%f")[:-3]

    def _dark_stylesheet(self) -> str:
        return """
        QMainWindow, QWidget { background: #171a1f; color: #d7dde7; font-size: 10pt; }
        QMenuBar, QMenu { background: #20242b; color: #d7dde7; }
        QMenuBar::item:selected, QMenu::item:selected { background: #32404f; }
        QPushButton { background: #2b3440; border: 1px solid #465463; border-radius: 4px; padding: 5px 10px; }
        QPushButton:hover { background: #344352; }
        QPushButton:pressed { background: #1f6f8b; }
        QLineEdit, QSpinBox, QComboBox { background: #101318; border: 1px solid #3d4652; border-radius: 4px; padding: 3px 6px; color: #ecf0f6; }
        QTableWidget, QPlainTextEdit { background: #101318; color: #dce3ec; gridline-color: #2b3440; selection-background-color: #2e6f8f; font-family: Consolas, 'Courier New', monospace; }
        QHeaderView::section { background: #242b34; color: #edf2f7; border: 1px solid #394552; padding: 4px; }
        QProgressBar { border: 1px solid #394552; border-radius: 4px; text-align: center; background: #101318; }
        QProgressBar::chunk { background: #2c9a70; border-radius: 3px; }
        QStatusBar { background: #111419; color: #c9d3df; }
        QSplitter::handle { background: #2a3038; }
        """
