from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QTableWidget,
    QTableWidgetItem,
    QLineEdit,
    QComboBox,
    QSpinBox,
    QLabel,
    QCheckBox,
)

from ui.pages.dashboard_page import format_bytes


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
        self.dry_run_checkbox = QCheckBox("Dry-run")
        self.clean_button = QPushButton("清理选中")
        self.select_l1_button = QPushButton("按 AI 勾选 L1")
        self.select_l12_button = QPushButton("按 AI 勾选 L1+L2")
        self.clean_l1_button = QPushButton("一键清理 AI L1")
        self.clean_l12_button = QPushButton("一键清理 AI L1+L2")

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

        filter_bar = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("搜索路径")
        self.min_size = QSpinBox()
        self.min_size.setRange(0, 1024 * 1024)
        self.min_size.setValue(0)
        self.min_size.setSuffix(" KB")
        self.days_limit = QSpinBox()
        self.days_limit.setRange(0, 365)
        self.days_limit.setValue(0)
        self.days_limit.setSuffix(" 天内")
        self.ai_level_filter = QComboBox()
        self.ai_level_filter.addItems(["全部", "L1", "L2", "L3", "L4", "L5"])
        filter_bar.addWidget(QLabel("过滤:"))
        filter_bar.addWidget(self.search_input)
        filter_bar.addWidget(QLabel("最小大小"))
        filter_bar.addWidget(self.min_size)
        filter_bar.addWidget(QLabel("最近修改"))
        filter_bar.addWidget(self.days_limit)
        filter_bar.addWidget(QLabel("AI等级"))
        filter_bar.addWidget(self.ai_level_filter)
        layout.addLayout(filter_bar)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["分类", "大小", "数量", "风险", "AI等级分布"])
        layout.addWidget(self.tree, 2)

        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(
            ["选择", "路径", "大小", "时间", "规则风险", "AI等级", "AI原因", "建议动作"]
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

        for widget in [self.search_input, self.min_size, self.days_limit, self.ai_level_filter]:
            if hasattr(widget, "textChanged"):
                widget.textChanged.connect(self.apply_filters)
            else:
                widget.valueChanged.connect(self.apply_filters)
        self.ai_level_filter.currentIndexChanged.connect(self.apply_filters)

        self.items = []
        self.filtered_items = []

    def set_items(self, items: list[dict]) -> None:
        self.items = items
        self.apply_filters()
        self._populate_tree()

    def _populate_tree(self) -> None:
        self.tree.clear()
        categories = {}
        for item in self.filtered_items:
            cat = item["category"]
            entry = categories.setdefault(cat, {"size": 0, "count": 0, "risk": set(), "levels": {}})
            entry["size"] += item["size_bytes"]
            entry["count"] += 1
            entry["risk"].add(item["rule_risk"])
            entry["levels"].setdefault(item["ai_level"], 0)
            entry["levels"][item["ai_level"]] += 1

        for cat, data in categories.items():
            level_summary = ", ".join(f"{k}:{v}" for k, v in data["levels"].items())
            item = QTreeWidgetItem(
                [cat, format_bytes(data["size"]), str(data["count"]), ",".join(data["risk"]), level_summary]
            )
            self.tree.addTopLevelItem(item)

    def apply_filters(self) -> None:
        text = self.search_input.text().lower()
        min_size = self.min_size.value() * 1024
        days_limit = self.days_limit.value()
        ai_filter = self.ai_level_filter.currentText()
        self.filtered_items = []
        for item in self.items:
            if text and text not in item["path"].lower():
                continue
            if item["size_bytes"] < min_size:
                continue
            if days_limit and item["is_recent"]:
                continue
            if ai_filter != "全部" and item["ai_level"] != ai_filter:
                continue
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
            self.table.setItem(row, 1, QTableWidgetItem(item["path"]))
            self.table.setItem(row, 2, QTableWidgetItem(format_bytes(item["size_bytes"])))
            self.table.setItem(row, 3, QTableWidgetItem(str(item["mtime"])))
            self.table.setItem(row, 4, QTableWidgetItem(item["rule_risk"]))
            self.table.setItem(row, 5, QTableWidgetItem(item["ai_level"]))
            self.table.setItem(row, 6, QTableWidgetItem(item.get("ai_reason", "")))
            self.table.setItem(row, 7, QTableWidgetItem(item.get("recommended_action", "")))

    def selected_items(self) -> list[int]:
        selected = []
        for row in range(self.table.rowCount()):
            if self.table.item(row, 0).checkState() == Qt.Checked:
                selected.append(row)
        return selected

    def is_dry_run(self) -> bool:
        return self.dry_run_checkbox.isChecked()
