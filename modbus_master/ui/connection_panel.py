from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QWidget,
)

from modbus_master.core.port_scanner import list_serial_ports


class ConnectionPanel(QWidget):
    connect_requested = pyqtSignal(dict)
    disconnect_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.mode_rtu = QRadioButton("RTU")
        self.mode_tcp = QRadioButton("TCP/IP")
        self.mode_rtu.setChecked(True)
        self.mode_group = QButtonGroup(self)
        self.mode_group.addButton(self.mode_rtu)
        self.mode_group.addButton(self.mode_tcp)

        self.port_combo = QComboBox()
        self.refresh_button = QPushButton("Refresh")
        self.baud_combo = QComboBox()
        self.baud_combo.addItems(["1200", "2400", "4800", "9600", "19200", "38400", "57600", "115200"])
        self.baud_combo.setCurrentText("9600")
        self.parity_combo = QComboBox()
        self.parity_combo.addItems(["None", "Even", "Odd"])
        self.stop_combo = QComboBox()
        self.stop_combo.addItems(["1", "1.5", "2"])
        self.data_combo = QComboBox()
        self.data_combo.addItems(["7", "8"])
        self.data_combo.setCurrentText("8")

        self.tcp_host = QLineEdit("127.0.0.1")
        self.tcp_port = QSpinBox()
        self.tcp_port.setRange(1, 65535)
        self.tcp_port.setValue(502)

        self.slave_spin = QSpinBox()
        self.slave_spin.setRange(1, 247)
        self.slave_spin.setValue(1)
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(50, 60000)
        self.timeout_spin.setValue(1000)
        self.timeout_spin.setSuffix(" ms")

        self.connect_button = QPushButton("Connect")
        self.status_dot = QLabel()
        self.status_dot.setFixedSize(14, 14)
        self.status_text = QLabel("Disconnected")

        mode_row = QHBoxLayout()
        mode_row.addWidget(self.mode_rtu)
        mode_row.addWidget(self.mode_tcp)
        mode_row.addStretch(1)

        serial_row = QHBoxLayout()
        serial_row.addWidget(self.port_combo, 1)
        serial_row.addWidget(self.refresh_button)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        form.addRow("Mode", mode_row)
        form.addRow("COM Port", serial_row)
        form.addRow("Baudrate", self.baud_combo)
        form.addRow("Parity", self.parity_combo)
        form.addRow("Stop Bits", self.stop_combo)
        form.addRow("Data Bits", self.data_combo)

        tcp_form = QFormLayout()
        tcp_form.setLabelAlignment(Qt.AlignRight)
        tcp_form.addRow("IP Address", self.tcp_host)
        tcp_form.addRow("TCP Port", self.tcp_port)
        tcp_form.addRow("Slave ID", self.slave_spin)
        tcp_form.addRow("Timeout", self.timeout_spin)

        status_row = QHBoxLayout()
        status_row.addWidget(self.status_dot)
        status_row.addWidget(self.status_text)
        status_row.addStretch(1)
        status_row.addWidget(self.connect_button)

        grid = QGridLayout()
        grid.setContentsMargins(10, 8, 10, 8)
        grid.setHorizontalSpacing(18)
        grid.addLayout(form, 0, 0)
        grid.addLayout(tcp_form, 0, 1)
        grid.addLayout(status_row, 0, 2)
        grid.setColumnStretch(0, 2)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 1)
        self.setLayout(grid)

        self.refresh_button.clicked.connect(self.refresh_ports)
        self.connect_button.clicked.connect(self._toggle_connection)
        self.mode_rtu.toggled.connect(self._apply_mode_visibility)

        self.refresh_ports()
        self.set_connected(False)
        self._apply_mode_visibility()

    def refresh_ports(self) -> None:
        current = self.port_combo.currentData() or self.port_combo.currentText()
        self.port_combo.clear()
        for device, label in list_serial_ports():
            self.port_combo.addItem(label, device)
        if self.port_combo.count() == 0:
            self.port_combo.addItem("No serial ports found", "")
        idx = self.port_combo.findData(current)
        if idx >= 0:
            self.port_combo.setCurrentIndex(idx)

    def config(self) -> dict:
        return {
            "mode": "TCP" if self.mode_tcp.isChecked() else "RTU",
            "port": self.port_combo.currentData() or "",
            "baudrate": int(self.baud_combo.currentText()),
            "parity": self.parity_combo.currentText(),
            "stopbits": float(self.stop_combo.currentText()),
            "bytesize": int(self.data_combo.currentText()),
            "slave_id": self.slave_spin.value(),
            "timeout_ms": self.timeout_spin.value(),
            "tcp_host": self.tcp_host.text().strip(),
            "tcp_port": self.tcp_port.value(),
        }

    def set_config(self, config: dict) -> None:
        if config.get("mode") == "TCP":
            self.mode_tcp.setChecked(True)
        else:
            self.mode_rtu.setChecked(True)
        self._set_combo_text(self.baud_combo, str(config.get("baudrate", 9600)))
        self._set_combo_text(self.parity_combo, str(config.get("parity", "None")))
        self._set_combo_text(self.stop_combo, str(config.get("stopbits", 1)).rstrip("0").rstrip("."))
        self._set_combo_text(self.data_combo, str(config.get("bytesize", 8)))
        self.slave_spin.setValue(int(config.get("slave_id", 1)))
        self.timeout_spin.setValue(int(config.get("timeout_ms", 1000)))
        self.tcp_host.setText(str(config.get("tcp_host", "127.0.0.1")))
        self.tcp_port.setValue(int(config.get("tcp_port", 502)))
        port = config.get("port", "")
        idx = self.port_combo.findData(port)
        if idx >= 0:
            self.port_combo.setCurrentIndex(idx)

    def set_connected(self, connected: bool) -> None:
        color = "#2ecc71" if connected else "#d84c4c"
        self.status_dot.setStyleSheet(f"background:{color};border-radius:7px;border:1px solid #111;")
        self.status_text.setText("Connected" if connected else "Disconnected")
        self.connect_button.setText("Disconnect" if connected else "Connect")

    def _toggle_connection(self) -> None:
        if self.connect_button.text() == "Disconnect":
            self.disconnect_requested.emit()
        else:
            self.connect_requested.emit(self.config())

    def _apply_mode_visibility(self) -> None:
        is_rtu = self.mode_rtu.isChecked()
        for widget in (self.port_combo, self.refresh_button, self.baud_combo, self.parity_combo, self.stop_combo, self.data_combo):
            widget.setEnabled(is_rtu)
        self.tcp_host.setEnabled(not is_rtu)
        self.tcp_port.setEnabled(not is_rtu)

    def _set_combo_text(self, combo: QComboBox, value: str) -> None:
        idx = combo.findText(value)
        if idx >= 0:
            combo.setCurrentIndex(idx)
