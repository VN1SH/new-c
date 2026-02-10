from __future__ import annotations

import shutil
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


def format_bytes(value: int) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if value < 1024:
            return f"{value:.2f} {unit}"
        value /= 1024
    return f"{value:.2f} PB"


def _shorten_text(text: str, limit: int = 92) -> str:
    if len(text) <= limit:
        return text
    return f"{text[:44]} ... {text[-40:]}"


STAGE_LABELS = {
    "starting": "启动",
    "scanning_root": "进入目录",
    "scanning_file": "扫描文件",
    "matched": "命中规则",
    "large_file_scan": "扫描大文件",
    "completed": "完成",
    "stopped": "已停止",
}


class DashboardPage(QWidget):
    request_scan = Signal()
    request_ai = Signal()
    request_ai_clean = Signal()

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)

        self.disk_label = QLabel("正在读取 C 盘信息...")
        layout.addWidget(self.disk_label)

        summary_box = QGroupBox("最近扫描摘要")
        summary_layout = QVBoxLayout(summary_box)
        self.summary_label = QLabel("尚未执行扫描。")
        summary_layout.addWidget(self.summary_label)
        layout.addWidget(summary_box)

        scan_box = QGroupBox("扫描实时状态")
        scan_layout = QVBoxLayout(scan_box)
        self.scan_status_label = QLabel("空闲")
        self.scan_status_label.setWordWrap(False)
        self.scan_status_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.scan_progress = QProgressBar()
        self.scan_progress.setRange(0, 1)
        self.scan_progress.setValue(0)
        scan_layout.addWidget(self.scan_status_label)
        scan_layout.addWidget(self.scan_progress)
        layout.addWidget(scan_box)

        button_row = QHBoxLayout()
        self.scan_button = QPushButton("开始扫描")
        self.ai_button = QPushButton("AI 分析")
        self.ai_clean_button = QPushButton("AI 一键清理（L1）")
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
                f"C 盘容量 {format_bytes(usage.total)} | 已用 {format_bytes(usage.used)} | 可用 {format_bytes(usage.free)}"
            )
        except Exception:
            self.disk_label.setText("读取 C 盘信息失败。")

    def update_summary(self, text: str) -> None:
        self.summary_label.setText(text)

    def set_scan_running(self, running: bool) -> None:
        if running:
            self.scan_progress.setRange(0, 0)
            self.scan_status_label.setText("扫描已启动...")
        else:
            self.scan_progress.setRange(0, 1)
            self.scan_progress.setValue(1)

    def _set_status(self, text: str, full_text: str | None = None) -> None:
        self.scan_status_label.setText(_shorten_text(text))
        self.scan_status_label.setToolTip(full_text or text)

    def update_scan_progress(self, progress: dict) -> None:
        stage = progress.get("stage", "scan")
        stage_cn = STAGE_LABELS.get(str(stage), str(stage))
        current = str(progress.get("current", ""))
        files_seen = progress.get("files_seen", 0)
        items_found = progress.get("items_found", 0)

        if stage == "scanning_file":
            full = f"正在扫描：{current} | 已扫描 {files_seen} 个文件 | 已命中 {items_found}"
            self._set_status(full, full)
        elif stage == "scanning_root":
            full = f"进入目录：{current}"
            self._set_status(full, full)
        elif stage == "matched":
            full = f"命中项目：{current} | 累计命中 {items_found}"
            self._set_status(full, full)
        elif stage == "large_file_scan":
            self._set_status("正在扫描超大文件...")
        elif stage == "completed":
            duration = progress.get("duration", 0.0)
            self._set_status(f"扫描完成，用时 {duration:.1f}s | 已扫描 {files_seen} | 命中 {items_found}")
            self.set_scan_running(False)
        elif stage == "stopped":
            self._set_status("扫描已停止。")
            self.set_scan_running(False)
        else:
            self._set_status(current or stage_cn)
