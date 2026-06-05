from pathlib import Path

from PyQt5.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QPushButton,
    QPlainTextEdit,
    QWidget,
)


class LogPanel(QWidget):
    LEVELS = ["Debug", "Info", "Errors only"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.level_combo = QComboBox()
        self.level_combo.addItems(self.LEVELS)

        self.clear_button = QPushButton("Clear")
        self.save_button = QPushButton("Save")
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.log_view.setMaximumBlockCount(5000)

        toolbar = QHBoxLayout()
        toolbar.addWidget(self.level_combo)
        toolbar.addStretch(1)
        toolbar.addWidget(self.clear_button)
        toolbar.addWidget(self.save_button)

        vertical = self._vertical_layout(toolbar)
        self.setLayout(vertical)

        self.clear_button.clicked.connect(self.log_view.clear)
        self.save_button.clicked.connect(self.save_log)

    def _vertical_layout(self, toolbar):
        from PyQt5.QtWidgets import QVBoxLayout

        layout = QVBoxLayout()
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addLayout(toolbar)
        layout.addWidget(self.log_view)
        return layout

    def append(self, line: str, level: str = "Info") -> None:
        current = self.level_combo.currentText()
        if current == "Errors only" and level != "Error":
            return
        if current == "Info" and level == "Debug":
            return
        self.log_view.appendPlainText(line)
        self.log_view.verticalScrollBar().setValue(self.log_view.verticalScrollBar().maximum())

    def save_log(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Save log", str(Path.home() / "modbus_log.txt"), "Text files (*.txt)")
        if path:
            Path(path).write_text(self.log_view.toPlainText(), encoding="utf-8")
