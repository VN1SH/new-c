from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ui.pages.dashboard_page import format_bytes


CATEGORY_LABELS = {
    "system_core_files": "系统核心文件",
    "driver_packages": "驱动与设备包",
    "windows_update_cache": "Windows 更新缓存",
    "system_temp_files": "系统临时文件",
    "temporary_files": "用户临时文件",
    "app_runtime_cache": "软件运行缓存",
    "package_manager_cache": "开发包管理缓存",
    "browser_cache_files": "浏览器缓存",
    "browser_profile_data": "浏览器配置/站点数据",
    "thumbnail_cache_files": "缩略图缓存",
    "crash_dump_files": "崩溃转储文件",
    "application_log_files": "应用日志文件",
    "game_data": "游戏数据",
    "chat_media_data": "聊天软件数据",
    "image_raster_files": "图片-位图",
    "image_vector_files": "图片-矢量图",
    "image_raw_files": "图片-RAW源片",
    "video_standard_files": "视频-常规格式",
    "video_production_files": "视频-制作素材",
    "audio_lossy_files": "音频-有损",
    "audio_lossless_files": "音频-无损",
    "word_documents": "文档-文本/Word",
    "spreadsheet_documents": "文档-表格",
    "presentation_documents": "文档-演示文稿",
    "pdf_documents": "文档-PDF",
    "document_text_files": "文档-纯文本",
    "structured_data_documents": "文档-结构化数据",
    "archive_files": "压缩文件",
    "disk_image_files": "磁盘镜像",
    "database_files": "数据库文件",
    "virtual_machine_files": "虚拟机镜像",
    "source_code_files": "源代码",
    "script_files": "脚本文件",
    "installer_packages": "安装包",
    "executable_binaries": "可执行/二进制",
    "software_runtime_files": "软件程序文件",
    "font_files": "字体文件",
    "large_files": "超大文件",
    "other_files": "其他文件",
    # Backward compatible keys
    "system_files": "系统文件（旧分类）",
    "software_cache": "软件缓存（旧分类）",
    "browser_cache": "浏览器缓存（旧分类）",
    "log_and_dump_files": "日志与转储（旧分类）",
    "image_files": "图片文件（旧分类）",
    "video_files": "视频文件（旧分类）",
    "audio_files": "音频文件（旧分类）",
    "document_files": "文档文件（旧分类）",
    "software_files": "软件附属文件（旧分类）",
    "system_cache": "系统缓存（旧分类）",
}


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


class CleanerPage(QWidget):
    request_scan = Signal()
    request_stop = Signal()
    request_clean_selected = Signal()
    request_ai_select = Signal(int)
    request_ai_clean = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)

        toolbar = QHBoxLayout()
        self.scan_button = QPushButton("开始扫描")
        self.stop_button = QPushButton("停止")
        self.dry_run_checkbox = QCheckBox("仅模拟（Dry-run）")
        self.clean_button = QPushButton("清理选中项")
        self.select_l1_button = QPushButton("勾选 AI L1")
        self.select_l12_button = QPushButton("勾选 AI L1+L2")
        self.clean_l1_button = QPushButton("一键清理 L1")
        self.clean_l12_button = QPushButton("一键清理 L1+L2")

        for widget in [
            self.scan_button,
            self.stop_button,
            self.dry_run_checkbox,
            self.clean_button,
            self.select_l1_button,
            self.select_l12_button,
            self.clean_l1_button,
            self.clean_l12_button,
        ]:
            toolbar.addWidget(widget)
        layout.addLayout(toolbar)

        self.scan_status_label = QLabel("扫描状态：空闲")
        self.scan_status_label.setWordWrap(False)
        self.scan_status_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.scan_progress = QProgressBar()
        self.scan_progress.setRange(0, 1)
        self.scan_progress.setValue(0)
        layout.addWidget(self.scan_status_label)
        layout.addWidget(self.scan_progress)

        filter_bar = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("搜索路径")
        self.days_limit = QSpinBox()
        self.days_limit.setRange(0, 365)
        self.days_limit.setValue(0)
        self.days_limit.setSuffix(" 天内")
        self.ai_level_filter = QComboBox()
        self.ai_level_filter.addItems(["全部", "L1", "L2", "L3", "L4", "L5"])

        filter_bar.addWidget(QLabel("过滤："))
        filter_bar.addWidget(self.search_input)
        filter_bar.addWidget(QLabel("最近修改"))
        filter_bar.addWidget(self.days_limit)
        filter_bar.addWidget(QLabel("AI等级"))
        filter_bar.addWidget(self.ai_level_filter)
        layout.addLayout(filter_bar)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["分类", "体积", "数量", "风险", "AI等级分布"])
        layout.addWidget(self.tree, 2)

        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels(
            ["选择", "文件名", "路径", "大小", "修改时间", "规则风险", "AI等级", "评级理由", "删除建议"]
        )
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table, 3)

        self.scan_button.clicked.connect(self.request_scan.emit)
        self.stop_button.clicked.connect(self.request_stop.emit)
        self.clean_button.clicked.connect(self.request_clean_selected.emit)
        self.select_l1_button.clicked.connect(lambda: self.request_ai_select.emit(1))
        self.select_l12_button.clicked.connect(lambda: self.request_ai_select.emit(2))
        self.clean_l1_button.clicked.connect(lambda: self.request_ai_clean.emit(1))
        self.clean_l12_button.clicked.connect(lambda: self.request_ai_clean.emit(2))

        self.search_input.textChanged.connect(self.apply_filters)
        self.days_limit.valueChanged.connect(self.apply_filters)
        self.ai_level_filter.currentIndexChanged.connect(self.apply_filters)

        self.items: list[dict] = []
        self.filtered_items: list[dict] = []
        self._filtered_source_indexes: list[int] = []

    def set_scan_running(self, running: bool) -> None:
        if running:
            self.scan_progress.setRange(0, 0)
            self._set_status("扫描状态：运行中...")
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
        if stage in {"scanning_file", "matched"}:
            full = f"扫描状态：{stage_cn} | 文件：{current} | 已扫描 {files_seen} | 命中 {items_found}"
            self._set_status(full, full)
        elif stage == "completed":
            duration = progress.get("duration", 0.0)
            self._set_status(f"扫描完成，用时 {duration:.1f}s | 已扫描 {files_seen} | 命中 {items_found}")
            self.set_scan_running(False)
        elif stage == "stopped":
            self._set_status("扫描已停止。")
            self.set_scan_running(False)
        else:
            full = f"扫描状态：{stage_cn} | {current}"
            self._set_status(full, full)

    def set_items(self, items: list[dict]) -> None:
        self.items = items
        self.apply_filters()
        self._populate_tree()

    def _populate_tree(self) -> None:
        self.tree.clear()
        categories = {}
        for item in self.filtered_items:
            cat = item.get("category", "other_files")
            entry = categories.setdefault(cat, {"size": 0, "count": 0, "risk": set(), "levels": {}})
            entry["size"] += int(item.get("size_bytes", 0))
            entry["count"] += 1
            entry["risk"].add(str(item.get("rule_risk", "")))
            level = str(item.get("ai_level", ""))
            entry["levels"].setdefault(level, 0)
            entry["levels"][level] += 1

        for cat, data in categories.items():
            display_cat = CATEGORY_LABELS.get(cat, cat)
            level_summary = ", ".join(f"{k}:{v}" for k, v in data["levels"].items())
            item = QTreeWidgetItem(
                [display_cat, format_bytes(data["size"]), str(data["count"]), ",".join(sorted(data["risk"])), level_summary]
            )
            self.tree.addTopLevelItem(item)

    def apply_filters(self) -> None:
        text = self.search_input.text().lower().strip()
        days_limit = self.days_limit.value()
        ai_filter = self.ai_level_filter.currentText()
        self.filtered_items = []
        self._filtered_source_indexes = []

        for idx, item in enumerate(self.items):
            item_path = str(item.get("path", "")).lower()
            if text and text not in item_path:
                continue
            if days_limit and bool(item.get("is_recent")):
                continue
            if ai_filter != "全部" and str(item.get("ai_level", "")) != ai_filter:
                continue
            self._filtered_source_indexes.append(idx)
            self.filtered_items.append(item)

        self._populate_table()
        self._populate_tree()

    def _populate_table(self) -> None:
        self.table.setRowCount(0)
        for row, item in enumerate(self.filtered_items):
            self.table.insertRow(row)
            checkbox = QTableWidgetItem()
            checkbox.setCheckState(Qt.Unchecked)
            self.table.setItem(row, 0, checkbox)
            path = str(item.get("path", ""))
            file_name = path.split("\\")[-1] if path else ""
            self.table.setItem(row, 1, QTableWidgetItem(file_name))
            self.table.setItem(row, 2, QTableWidgetItem(path))
            self.table.setItem(row, 3, QTableWidgetItem(format_bytes(int(item.get("size_bytes", 0)))))
            self.table.setItem(row, 4, QTableWidgetItem(str(item.get("mtime", ""))))
            self.table.setItem(row, 5, QTableWidgetItem(str(item.get("rule_risk", ""))))
            self.table.setItem(row, 6, QTableWidgetItem(str(item.get("ai_level", ""))))
            self.table.setItem(row, 7, QTableWidgetItem(str(item.get("ai_reason", ""))))
            self.table.setItem(row, 8, QTableWidgetItem(str(item.get("recommended_action", ""))))

    def selected_items(self) -> list[int]:
        selected: list[int] = []
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item and item.checkState() == Qt.Checked:
                if row < len(self._filtered_source_indexes):
                    selected.append(self._filtered_source_indexes[row])
        return selected

    def is_dry_run(self) -> bool:
        return self.dry_run_checkbox.isChecked()
