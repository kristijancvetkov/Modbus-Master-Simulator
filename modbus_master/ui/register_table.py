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
    QMessageBox,
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
    value_edit_requested = pyqtSignal(int, str)
    poll_interval_changed = pyqtSignal(int)

    COLUMNS = [
        "#",
        "Auto",
        "Slave ID",
        "Address",
        "Alias/Name",
        "Function Code",
        "Length",
        "Data Type",
        "Value",
        "Raw Hex",
        "Write",
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.add_button = QPushButton("Add Row")
        self.remove_button = QPushButton("Remove")
        self.remove_all_button = QPushButton("Remove All")
        self.auto_poll = QCheckBox("Auto Poll")
        self.auto_poll.setChecked(True)
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(100, 60000)
        self.interval_spin.setValue(1000)
        self.interval_spin.setSuffix(" ms")

        toolbar = QHBoxLayout()
        toolbar.addWidget(self.add_button)
        toolbar.addWidget(self.remove_button)
        toolbar.addWidget(self.remove_all_button)
        toolbar.addStretch(1)
        toolbar.addWidget(self.auto_poll)
        toolbar.addWidget(self.interval_spin)

        self.table = QTableWidget(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.verticalHeader().setVisible(False)
        self._updating_value_cells = False
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setStretchLastSection(False)
        self.table.setColumnWidth(0, 54)
        self.table.setColumnWidth(1, 58)
        self.table.setColumnWidth(2, 82)
        self.table.setColumnWidth(3, 96)
        self.table.setColumnWidth(4, 220)
        self.table.setColumnWidth(5, 136)
        self.table.setColumnWidth(6, 86)
        self.table.setColumnWidth(7, 124)
        self.table.setColumnWidth(8, 170)
        self.table.setColumnWidth(9, 170)
        self.table.setColumnWidth(10, 90)
        for column in (0, 1, 2, 3, 5, 6, 7, 10):
            header.setSectionResizeMode(column, QHeaderView.Fixed)
        for column in (4, 8, 9):
            header.setSectionResizeMode(column, QHeaderView.Stretch)

        layout = QVBoxLayout()
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addLayout(toolbar)
        layout.addWidget(self.table)
        self.setLayout(layout)

        self.add_button.clicked.connect(lambda: self.add_register())
        self.remove_button.clicked.connect(self.remove_selected)
        self.remove_all_button.clicked.connect(self.remove_all)
        self.interval_spin.valueChanged.connect(self.poll_interval_changed.emit)
        self.table.customContextMenuRequested.connect(self.open_context_menu)
        self.table.itemChanged.connect(self._on_item_changed)

    def add_register(self, data: dict | None = None, sort_after: bool = True) -> int:
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

        slave = QSpinBox()
        slave.setRange(1, 247)
        slave.setMinimumWidth(72)
        slave.setValue(int(data.get("slave_id", 1)))
        self.table.setCellWidget(row, 2, slave)

        self.table.setItem(row, 3, QTableWidgetItem(str(data.get("address", row))))
        self.table.setItem(row, 4, QTableWidgetItem(str(data.get("alias", ""))))

        fc = QComboBox()
        fc.addItems(FC_LABELS)
        fc.setMinimumWidth(104)
        fc.setCurrentText(CODE_TO_FC.get(int(data.get("function_code", 3)), "FC03"))
        self.table.setCellWidget(row, 5, fc)

        length = QSpinBox()
        length.setRange(1, 125)
        length.setMinimumWidth(72)
        length.setValue(int(data.get("length", 1)))
        self.table.setCellWidget(row, 6, length)

        dtype = QComboBox()
        dtype.addItems([item.value for item in DataType])
        dtype.setMinimumWidth(96)
        dtype.setCurrentText(str(data.get("data_type", DataType.UINT16.value)))
        self.table.setCellWidget(row, 7, dtype)

        value = QTableWidgetItem(str(data.get("value", "")))
        raw = QTableWidgetItem(str(data.get("raw_hex", "")))
        raw.setFlags(raw.flags() & ~Qt.ItemIsEditable)
        self._updating_value_cells = True
        try:
            self.table.setItem(row, 8, value)
            self.table.setItem(row, 9, raw)
            self._set_value_editable(row, FC_TO_CODE[fc.currentText()])
        finally:
            self._updating_value_cells = False

        write = QPushButton("Write")
        write.clicked.connect(self._emit_write_for_sender)
        self.table.setCellWidget(row, 10, write)

        dtype.currentTextChanged.connect(lambda text, spin=length: spin.setValue(required_registers(text, spin.value())))
        fc.currentTextChanged.connect(lambda _text, combo=fc: self._set_value_editable_for_combo(combo))
        if sort_after:
            self.sort_by_address()
            return self.find_row(self._data_slave_id(data), self._data_address(data, row), self._data_function_code(data))
        return row

    def upsert_scanned_register(self, data: dict) -> None:
        slave_id = int(data.get("slave_id", 1))
        function_code = int(data.get("function_code", 3))
        address = int(data.get("address", 0))
        value = str(data.get("value", ""))
        raw_hex = self._scan_raw_value(function_code, value)
        row = self.find_row(slave_id, address, function_code)

        if row is None:
            row = self.add_register(
                {
                    "slave_id": slave_id,
                    "address": address,
                    "alias": f"Slave {slave_id} FC{function_code:02d} {address}",
                    "function_code": function_code,
                    "length": 1,
                    "data_type": "BOOL" if function_code in (1, 2) else "UINT16",
                    "value": value,
                    "raw_hex": raw_hex,
                }
            )
            self.flash_row(row)
            return

        old = self._item_text(row, 8)
        self.update_row_value(row, value, raw_hex, old not in ("", value))

    def find_row(self, slave_id: int, address: int, function_code: int) -> int | None:
        for row in range(self.table.rowCount()):
            cfg = self.row_config(row)
            if cfg["slave_id"] == slave_id and cfg["address"] == address and cfg["function_code"] == function_code:
                return row
        return None

    def rows(self) -> list[dict]:
        rows = []
        for row in range(self.table.rowCount()):
            rows.append(self.row_config(row))
        return rows

    def row_config(self, row: int) -> dict:
        return {
            "auto_poll": self.table.cellWidget(row, 1).isChecked(),
            "slave_id": self.table.cellWidget(row, 2).value(),
            "address": self._item_int(row, 3, 0),
            "alias": self._item_text(row, 4),
            "function_code": FC_TO_CODE[self.table.cellWidget(row, 5).currentText()],
            "length": self.table.cellWidget(row, 6).value(),
            "data_type": self.table.cellWidget(row, 7).currentText(),
            "value": self._item_text(row, 8),
            "raw_hex": self._item_text(row, 9),
        }

    def load_rows(self, rows: list[dict]) -> None:
        self.table.setRowCount(0)
        for row in rows:
            self.add_register(row, sort_after=False)
        self.sort_by_address()

    def remove_selected(self) -> None:
        selected = sorted({index.row() for index in self.table.selectedIndexes()}, reverse=True)
        for row in selected:
            self.table.removeRow(row)
        self.renumber()

    def remove_all(self) -> None:
        if self.table.rowCount() == 0:
            return
        answer = QMessageBox.question(
            self,
            "Remove all registers",
            "Remove all saved registers?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        self.table.setRowCount(0)
        self.renumber()

    def update_row_value(self, row: int, value: str, raw_hex: str, changed: bool) -> None:
        if row < 0 or row >= self.table.rowCount():
            return
        self._updating_value_cells = True
        try:
            self.table.item(row, 8).setText(value)
            self.table.item(row, 9).setText(raw_hex)
        finally:
            self._updating_value_cells = False
        if changed:
            self.flash_row(row)

    def set_row_auto_poll(self, row: int, enabled: bool) -> None:
        if row < 0 or row >= self.table.rowCount():
            return
        self.table.cellWidget(row, 1).setChecked(enabled)

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

            QApplication.clipboard().setText(self._item_text(row, 8))
        elif action == alias_action:
            alias, ok = QInputDialog.getText(self, "Set alias", "Alias:", text=self._item_text(row, 4))
            if ok:
                self.table.item(row, 4).setText(alias)
        elif action == remove_action:
            self.table.removeRow(row)
            self.renumber()

    def renumber(self) -> None:
        for row in range(self.table.rowCount()):
            self.table.item(row, 0).setText(str(row + 1))

    def sort_by_address(self) -> None:
        rows = sorted(self.rows(), key=lambda row: (row["slave_id"], row["address"], row["function_code"], row["alias"]))
        self.table.setRowCount(0)
        for row in rows:
            self.add_register(row, sort_after=False)
        self.renumber()

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

    def _scan_raw_value(self, function_code: int, value: str) -> str:
        try:
            numeric = int(value)
        except ValueError:
            return ""
        if function_code in (1, 2):
            return "01" if bool(numeric) else "00"
        return f"{numeric & 0xFFFF:04X}"

    def _data_address(self, data: dict, default: int) -> int:
        try:
            value = data.get("address", default)
            return int(value, 0) if isinstance(value, str) else int(value)
        except (TypeError, ValueError):
            return default

    def _data_slave_id(self, data: dict) -> int:
        try:
            return int(data.get("slave_id", 1))
        except (TypeError, ValueError):
            return 1

    def _data_function_code(self, data: dict) -> int:
        try:
            return int(data.get("function_code", 3))
        except (TypeError, ValueError):
            return 3

    def _set_value_editable_for_combo(self, combo: QComboBox) -> None:
        for row in range(self.table.rowCount()):
            if self.table.cellWidget(row, 5) is combo:
                self._set_value_editable(row, FC_TO_CODE[combo.currentText()])
                return

    def _set_value_editable(self, row: int, function_code: int) -> None:
        item = self.table.item(row, 8)
        if item is None:
            return
        flags = item.flags()
        if function_code == 3:
            item.setFlags(flags | Qt.ItemIsEditable)
        else:
            item.setFlags(flags & ~Qt.ItemIsEditable)

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if self._updating_value_cells or item.column() != 8:
            return
        row = item.row()
        if self.row_config(row)["function_code"] == 3:
            self.value_edit_requested.emit(row, item.text())

    def _emit_write_for_sender(self) -> None:
        button = self.sender()
        for row in range(self.table.rowCount()):
            if self.table.cellWidget(row, 10) is button:
                self.write_requested.emit(row)
                return
