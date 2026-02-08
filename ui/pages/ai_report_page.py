from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QTextEdit, QPushButton


class AIReportPage(QWidget):
    request_export = Signal()

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        self.report_view = QTextEdit()
        self.report_view.setReadOnly(True)
        layout.addWidget(self.report_view)

        self.export_button = QPushButton("导出 AI 报告 HTML")
        layout.addWidget(self.export_button)
        self.export_button.clicked.connect(self.request_export.emit)

    def update_report(self, report: dict) -> None:
        self.report_view.setText(str(report))
