from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QAction,
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QMenu,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from modbus_master.core.data_types import DataType, required_registers


FC_LABELS = ["FC01", "FC02", "FC03", "FC04"]
FC_TO_CODE = {"FC01": 1, "FC02": 2, "FC03": 3, "FC04": 4}
CODE_TO_FC = {value: key for key, value in FC_TO_CODE.items()}


class RegisterTable(QWidget):
    write_requested = pyqtSignal(int)
    poll_interval_changed = pyqtSignal(int)

    COLUMNS = [
        "#",
        "Auto",
        "Address",
        "Alias/Name",
        "Function Code",
        "Length",
        "Data Type",
        "Value",
        "Raw Hex",
        "Last Updated",
        "Write",
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.add_button = QPushButton("Add Row")
        self.remove_button = QPushButton("Remove")
        self.auto_poll = QCheckBox("Auto Poll")
        self.auto_poll.setChecked(True)
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(100, 60000)
        self.interval_spin.setValue(1000)
        self.interval_spin.setSuffix(" ms")

        toolbar = QHBoxLayout()
        toolbar.addWidget(self.add_button)
        toolbar.addWidget(self.remove_button)
        toolbar.addStretch(1)
        toolbar.addWidget(self.auto_poll)
        toolbar.addWidget(self.interval_spin)

        self.table = QTableWidget(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.setColumnWidth(0, 42)
        self.table.setColumnWidth(1, 52)
        self.table.setColumnWidth(2, 90)
        self.table.setColumnWidth(3, 170)
        self.table.setColumnWidth(4, 110)
        self.table.setColumnWidth(5, 70)
        self.table.setColumnWidth(6, 100)
        self.table.setColumnWidth(7, 130)
        self.table.setColumnWidth(8, 130)
        self.table.setColumnWidth(9, 150)
        self.table.setColumnWidth(10, 80)

        layout = QVBoxLayout()
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addLayout(toolbar)
        layout.addWidget(self.table)
        self.setLayout(layout)

        self.add_button.clicked.connect(lambda: self.add_register())
        self.remove_button.clicked.connect(self.remove_selected)
        self.interval_spin.valueChanged.connect(self.poll_interval_changed.emit)
        self.table.customContextMenuRequested.connect(self.open_context_menu)

    def add_register(self, data: dict | None = None) -> None:
        data = data or {}
        row = self.table.rowCount()
        self.table.insertRow(row)

        number = QTableWidgetItem(str(row + 1))
        number.setFlags(number.flags() & ~Qt.ItemIsEditable)
        self.table.setItem(row, 0, number)

        auto = QCheckBox()
        auto.setChecked(bool(data.get("auto_poll", True)))
        auto.setStyleSheet("margin-left:14px;")
        self.table.setCellWidget(row, 1, auto)

        self.table.setItem(row, 2, QTableWidgetItem(str(data.get("address", row))))
        self.table.setItem(row, 3, QTableWidgetItem(str(data.get("alias", ""))))

        fc = QComboBox()
        fc.addItems(FC_LABELS)
        fc.setCurrentText(CODE_TO_FC.get(int(data.get("function_code", 3)), "FC03"))
        self.table.setCellWidget(row, 4, fc)

        length = QSpinBox()
        length.setRange(1, 125)
        length.setValue(int(data.get("length", 1)))
        self.table.setCellWidget(row, 5, length)

        dtype = QComboBox()
        dtype.addItems([item.value for item in DataType])
        dtype.setCurrentText(str(data.get("data_type", DataType.UINT16.value)))
        self.table.setCellWidget(row, 6, dtype)

        value = QTableWidgetItem(str(data.get("value", "")))
        value.setFlags(value.flags() & ~Qt.ItemIsEditable)
        self.table.setItem(row, 7, value)
        raw = QTableWidgetItem(str(data.get("raw_hex", "")))
        raw.setFlags(raw.flags() & ~Qt.ItemIsEditable)
        self.table.setItem(row, 8, raw)
        updated = QTableWidgetItem(str(data.get("last_updated", "")))
        updated.setFlags(updated.flags() & ~Qt.ItemIsEditable)
        self.table.setItem(row, 9, updated)

        write = QPushButton("Write")
        write.clicked.connect(self._emit_write_for_sender)
        self.table.setCellWidget(row, 10, write)

        dtype.currentTextChanged.connect(lambda text, spin=length: spin.setValue(required_registers(text, spin.value())))

    def rows(self) -> list[dict]:
        rows = []
        for row in range(self.table.rowCount()):
            rows.append(self.row_config(row))
        return rows

    def row_config(self, row: int) -> dict:
        return {
            "auto_poll": self.table.cellWidget(row, 1).isChecked(),
            "address": self._item_int(row, 2, 0),
            "alias": self._item_text(row, 3),
            "function_code": FC_TO_CODE[self.table.cellWidget(row, 4).currentText()],
            "length": self.table.cellWidget(row, 5).value(),
            "data_type": self.table.cellWidget(row, 6).currentText(),
            "value": self._item_text(row, 7),
            "raw_hex": self._item_text(row, 8),
            "last_updated": self._item_text(row, 9),
        }

    def load_rows(self, rows: list[dict]) -> None:
        self.table.setRowCount(0)
        if rows:
            for row in rows:
                self.add_register(row)
        else:
            self.add_register({"address": 0, "alias": "Register 0", "function_code": 3, "data_type": "UINT16"})
        self.renumber()

    def remove_selected(self) -> None:
        selected = sorted({index.row() for index in self.table.selectedIndexes()}, reverse=True)
        for row in selected:
            self.table.removeRow(row)
        self.renumber()

    def update_row_value(self, row: int, value: str, raw_hex: str, timestamp: str, changed: bool) -> None:
        if row < 0 or row >= self.table.rowCount():
            return
        self.table.item(row, 7).setText(value)
        self.table.item(row, 8).setText(raw_hex)
        self.table.item(row, 9).setText(timestamp)
        if changed:
            self.flash_row(row)

    def flash_row(self, row: int) -> None:
        color = QColor("#65591f")
        original = QColor("#20242b")
        for col in range(self.table.columnCount()):
            item = self.table.item(row, col)
            if item:
                item.setBackground(color)
        QTimer.singleShot(650, lambda: self._restore_row(row, original))

    def open_context_menu(self, point) -> None:
        row = self.table.rowAt(point.y())
        if row < 0:
            return
        menu = QMenu(self)
        copy_action = QAction("Copy value", self)
        alias_action = QAction("Set alias", self)
        remove_action = QAction("Remove row", self)
        menu.addAction(copy_action)
        menu.addAction(alias_action)
        menu.addAction(remove_action)
        action = menu.exec_(self.table.viewport().mapToGlobal(point))
        if action == copy_action:
            from PyQt5.QtWidgets import QApplication

            QApplication.clipboard().setText(self._item_text(row, 7))
        elif action == alias_action:
            alias, ok = QInputDialog.getText(self, "Set alias", "Alias:", text=self._item_text(row, 3))
            if ok:
                self.table.item(row, 3).setText(alias)
        elif action == remove_action:
            self.table.removeRow(row)
            self.renumber()

    def renumber(self) -> None:
        for row in range(self.table.rowCount()):
            self.table.item(row, 0).setText(str(row + 1))

    def _restore_row(self, row: int, color: QColor) -> None:
        if row >= self.table.rowCount():
            return
        for col in range(self.table.columnCount()):
            item = self.table.item(row, col)
            if item:
                item.setBackground(color)

    def _item_text(self, row: int, col: int) -> str:
        item = self.table.item(row, col)
        return item.text() if item else ""

    def _item_int(self, row: int, col: int, default: int) -> int:
        try:
            return int(self._item_text(row, col), 0)
        except ValueError:
            return default

    def _emit_write_for_sender(self) -> None:
        button = self.sender()
        for row in range(self.table.rowCount()):
            if self.table.cellWidget(row, 10) is button:
                self.write_requested.emit(row)
                return
