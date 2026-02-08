from __future__ import annotations

import shutil
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QHBoxLayout,
    QGroupBox,
)


def format_bytes(value: int) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if value < 1024:
            return f"{value:.2f} {unit}"
        value /= 1024
    return f"{value:.2f} PB"


class DashboardPage(QWidget):
    request_scan = Signal()
    request_ai = Signal()
    request_ai_clean = Signal()

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)

        self.disk_label = QLabel("C盘容量读取中...")
        layout.addWidget(self.disk_label)

        summary_box = QGroupBox("最近一次扫描摘要")
        summary_layout = QVBoxLayout(summary_box)
        self.summary_label = QLabel("尚未扫描")
        summary_layout.addWidget(self.summary_label)
        layout.addWidget(summary_box)

        button_row = QHBoxLayout()
        self.scan_button = QPushButton("开始扫描")
        self.ai_button = QPushButton("AI 分析")
        self.ai_clean_button = QPushButton("按 AI 一键清理")
        button_row.addWidget(self.scan_button)
        button_row.addWidget(self.ai_button)
        button_row.addWidget(self.ai_clean_button)
        layout.addLayout(button_row)

        layout.addStretch(1)

        self.scan_button.clicked.connect(self.request_scan.emit)
        self.ai_button.clicked.connect(self.request_ai.emit)
        self.ai_clean_button.clicked.connect(self.request_ai_clean.emit)

        self.refresh_disk_info()

    def refresh_disk_info(self) -> None:
        try:
            usage = shutil.disk_usage("C:\\")
            self.disk_label.setText(
                f"C盘容量: {format_bytes(usage.total)} | 已用: {format_bytes(usage.used)} | 可用: {format_bytes(usage.free)}"
            )
        except Exception:
            self.disk_label.setText("无法读取C盘信息（可能非Windows环境）")

    def update_summary(self, text: str) -> None:
        self.summary_label.setText(text)
