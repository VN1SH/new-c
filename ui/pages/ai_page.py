from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QTableWidget, QTableWidgetItem


class AIAdvisorPage(QWidget):
    request_clean = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["目标", "等级", "置信度", "原因", "风险提示", "动作"])
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)

        self.clean_l1_button = QPushButton("一键清理 L1")
        self.clean_l12_button = QPushButton("一键清理 L1+L2")
        layout.addWidget(self.clean_l1_button)
        layout.addWidget(self.clean_l12_button)

        self.clean_l1_button.clicked.connect(lambda: self.request_clean.emit(1))
        self.clean_l12_button.clicked.connect(lambda: self.request_clean.emit(2))

    def update_advice(self, advice: dict) -> None:
        self.table.setRowCount(0)
        for row, item in enumerate(advice.get("items", [])):
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(item.get("target", "")))
            self.table.setItem(row, 1, QTableWidgetItem(item.get("level", "")))
            self.table.setItem(row, 2, QTableWidgetItem(str(item.get("confidence", ""))))
            self.table.setItem(row, 3, QTableWidgetItem(item.get("reason", "")))
            self.table.setItem(row, 4, QTableWidgetItem(item.get("risk_notes", "")))
            self.table.setItem(row, 5, QTableWidgetItem(item.get("recommended_action", "")))
