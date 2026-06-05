from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QProgressBar,
    QPushButton,
    QSpinBox,
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
            if result.ok:
                value = result.values[0] if result.values else ""
                self.row_ready.emit(
                    {
                        "address": address,
                        "function_code": fc,
                        "value": value,
                        "status": result.status,
                        "ok": True,
                        "no_response": False,
                        "tx": result.tx_hex,
                        "rx": result.rx_hex,
                    }
                )
            self.progress.emit(int(((offset + 1) / count) * 100))
        self.finished.emit()


class ScannerPanel(QWidget):
    scan_requested = pyqtSignal(dict)
    cancel_requested = pyqtSignal()

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
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)

        form = QFormLayout()
        form.addRow("Start Address", self.start_spin)
        form.addRow("Count", self.count_spin)
        form.addRow("Function Code", self.fc_combo)

        buttons = QHBoxLayout()
        buttons.addWidget(self.scan_button)
        buttons.addStretch(1)

        layout = QVBoxLayout()
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addLayout(form)
        layout.addLayout(buttons)
        layout.addWidget(self.progress)
        layout.addStretch(1)
        self.setLayout(layout)

        self.scan_button.clicked.connect(self._scan_or_cancel)

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
        self.progress.setValue(0)
        self.scan_requested.emit(self.params())

    def set_scanning(self, scanning: bool) -> None:
        self.scan_button.setText("Cancel" if scanning else "Scan Registers")
