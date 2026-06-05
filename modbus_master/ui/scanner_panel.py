import csv
from pathlib import Path

from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


FC_LABELS = {
    "FC01 Coils": 1,
    "FC02 Discrete Inputs": 2,
    "FC03 Holding Registers": 3,
    "FC04 Input Registers": 4,
}


class ScannerWorker(QObject):
    row_ready = pyqtSignal(dict)
    progress = pyqtSignal(int)
    finished = pyqtSignal()

    def __init__(self, client, params: dict):
        super().__init__()
        self.client = client
        self.params = params
        self.cancelled = False

    def cancel(self) -> None:
        self.cancelled = True

    def run(self) -> None:
        start = int(self.params["start"])
        count = int(self.params["count"])
        fc = int(self.params["function_code"])
        for offset in range(count):
            if self.cancelled:
                break
            address = start + offset
            result = self.client.read(fc, address, 1)
            value = result.values[0] if result.values else ""
            self.row_ready.emit(
                {
                    "address": address,
                    "value": value,
                    "status": result.status if result.ok else result.error or result.status,
                    "ok": result.ok,
                    "no_response": result.status == "NO RESPONSE",
                    "tx": result.tx_hex,
                    "rx": result.rx_hex,
                }
            )
            self.progress.emit(int(((offset + 1) / count) * 100))
        self.finished.emit()


class ScannerPanel(QWidget):
    scan_requested = pyqtSignal(dict)
    cancel_requested = pyqtSignal()

    COLUMNS = ["Address", "Hex Address", "Value (Dec)", "Value (Hex)", "Value (Bin)", "Status"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.start_spin = QSpinBox()
        self.start_spin.setRange(0, 65535)
        self.count_spin = QSpinBox()
        self.count_spin.setRange(1, 2000)
        self.count_spin.setValue(32)
        self.fc_combo = QComboBox()
        self.fc_combo.addItems(list(FC_LABELS.keys()))
        self.fc_combo.setCurrentText("FC03 Holding Registers")

        self.scan_button = QPushButton("Scan Registers")
        self.export_button = QPushButton("Export CSV")
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)

        self.table = QTableWidget(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setAlternatingRowColors(True)

        form = QFormLayout()
        form.addRow("Start Address", self.start_spin)
        form.addRow("Count", self.count_spin)
        form.addRow("Function Code", self.fc_combo)

        buttons = QHBoxLayout()
        buttons.addWidget(self.scan_button)
        buttons.addWidget(self.export_button)
        buttons.addStretch(1)

        layout = QVBoxLayout()
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addLayout(form)
        layout.addLayout(buttons)
        layout.addWidget(self.progress)
        layout.addWidget(self.table)
        self.setLayout(layout)

        self.scan_button.clicked.connect(self._scan_or_cancel)
        self.export_button.clicked.connect(self.export_csv)

    def params(self) -> dict:
        return {
            "start": self.start_spin.value(),
            "count": self.count_spin.value(),
            "function_code": FC_LABELS[self.fc_combo.currentText()],
        }

    def set_params(self, data: dict) -> None:
        self.start_spin.setValue(int(data.get("start", 0)))
        self.count_spin.setValue(int(data.get("count", 32)))
        fc = int(data.get("function_code", 3))
        for label, code in FC_LABELS.items():
            if code == fc:
                self.fc_combo.setCurrentText(label)
                break

    def _scan_or_cancel(self) -> None:
        if self.scan_button.text() == "Cancel":
            self.cancel_requested.emit()
            return
        self.table.setRowCount(0)
        self.progress.setValue(0)
        self.scan_requested.emit(self.params())

    def set_scanning(self, scanning: bool) -> None:
        self.scan_button.setText("Cancel" if scanning else "Scan Registers")
        self.export_button.setEnabled(not scanning)

    def add_result(self, data: dict) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        value = data.get("value", "")
        try:
            value_hex = f"0x{int(value) & 0xFFFF:04X}"
            value_bin = format(int(value) & 0xFFFF, "016b")
        except (TypeError, ValueError):
            value_hex = ""
            value_bin = ""

        cells = [
            str(data["address"]),
            f"0x{int(data['address']):04X}",
            str(value),
            value_hex,
            value_bin,
            str(data.get("status", "")),
        ]
        color = "#173b22" if data.get("ok") else "#3f3333" if data.get("no_response") else "#4a2020"
        for column, text in enumerate(cells):
            item = QTableWidgetItem(text)
            item.setBackground(QColor(color))
            self.table.setItem(row, column, item)

    def export_csv(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export scan results", str(Path.home() / "scan_results.csv"), "CSV files (*.csv)")
        if not path:
            return
        with Path(path).open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(self.COLUMNS)
            for row in range(self.table.rowCount()):
                writer.writerow([self.table.item(row, col).text() if self.table.item(row, col) else "" for col in range(self.table.columnCount())])
