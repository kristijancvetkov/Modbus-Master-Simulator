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
    message_ready = pyqtSignal(str, str)
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
        slave_start = int(self.params["slave_start"])
        slave_stop = int(self.params["slave_stop"])
        if slave_stop < slave_start:
            slave_start, slave_stop = slave_stop, slave_start

        total = count * (slave_stop - slave_start + 1)
        completed = 0
        for slave_id in range(slave_start, slave_stop + 1):
            for offset in range(count):
                if self.cancelled:
                    break
                address = start + offset
                result = self.client.read(fc, address, 1, slave_id=slave_id)
                if result.ok:
                    value = result.values[0] if result.values else ""
                    self.row_ready.emit(
                        {
                            "slave_id": slave_id,
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
                elif result.status == "NO RESPONSE":
                    skipped = count - offset - 1
                    completed += skipped + 1
                    self.progress.emit(int((completed / total) * 100))
                    self.message_ready.emit(
                        f"Slave {slave_id} skipped after no response from address {address}",
                        "Error",
                    )
                    break
                completed += 1
                self.progress.emit(int((completed / total) * 100))
            if self.cancelled:
                break
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
        self.slave_start_spin = QSpinBox()
        self.slave_start_spin.setRange(1, 247)
        self.slave_start_spin.setValue(1)
        self.slave_stop_spin = QSpinBox()
        self.slave_stop_spin.setRange(1, 247)
        self.slave_stop_spin.setValue(1)
        self.fc_combo = QComboBox()
        self.fc_combo.addItems(list(FC_LABELS.keys()))
        self.fc_combo.setCurrentText("FC03 Holding Registers")

        self.scan_button = QPushButton("Scan Registers")
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)

        form = QFormLayout()
        form.addRow("Start Address", self.start_spin)
        form.addRow("Count", self.count_spin)
        form.addRow("Start Slave ID", self.slave_start_spin)
        form.addRow("Stop Slave ID", self.slave_stop_spin)
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
            "slave_start": self.slave_start_spin.value(),
            "slave_stop": self.slave_stop_spin.value(),
            "function_code": FC_LABELS[self.fc_combo.currentText()],
        }

    def set_params(self, data: dict) -> None:
        self.start_spin.setValue(int(data.get("start", 0)))
        self.count_spin.setValue(int(data.get("count", 32)))
        slave_start = int(data.get("slave_start", data.get("slave_id", 1)))
        self.slave_start_spin.setValue(slave_start)
        self.slave_stop_spin.setValue(int(data.get("slave_stop", slave_start)))
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
