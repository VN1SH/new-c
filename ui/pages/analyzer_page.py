from __future__ import annotations

from PySide6.QtCharts import QChart, QChartView, QPieSeries
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ui.pages.cleaner_page import CATEGORY_LABELS
from ui.pages.dashboard_page import format_bytes


PIE_COLORS = [
    "#EF4444",
    "#F97316",
    "#EAB308",
    "#22C55E",
    "#14B8A6",
    "#06B6D4",
    "#3B82F6",
    "#6366F1",
    "#8B5CF6",
    "#EC4899",
    "#10B981",
    "#F43F5E",
    "#84CC16",
    "#0EA5E9",
]


class AnalyzerPage(QWidget):
    request_export = Signal()

    def __init__(self) -> None:
        super().__init__()
        root = QVBoxLayout(self)

        title = QLabel("分析总览")
        title.setStyleSheet("font-size:18px; font-weight:600;")
        root.addWidget(title)

        self.summary_label = QLabel("等待分析数据")
        root.addWidget(self.summary_label)

        cards = QHBoxLayout()
        self.total_size_label = QLabel("可清理体积：-")
        self.total_files_label = QLabel("命中文件数：-")
        self.category_count_label = QLabel("分类数量：-")
        for card in [self.total_size_label, self.total_files_label, self.category_count_label]:
            card.setAlignment(Qt.AlignCenter)
            card.setStyleSheet(
                "background:#f5f7fb; border:1px solid #dbe2ef; border-radius:8px; padding:10px; font-weight:600;"
            )
            cards.addWidget(card)
        root.addLayout(cards)

        body = QHBoxLayout()
        root.addLayout(body, 1)

        left = QVBoxLayout()
        body.addLayout(left, 3)

        self.chart = QChart()
        self.series = QPieSeries()
        self.series.setPieSize(0.78)
        self.series.setHoleSize(0.38)
        self.chart.addSeries(self.series)
        self.chart.setTitle("文件分类体积分布（Top 12）")
        self.chart.legend().setVisible(True)
        self.chart.legend().setAlignment(Qt.AlignRight)

        self.chart_view = QChartView(self.chart)
        self.chart_view.setRenderHint(QPainter.Antialiasing)
        left.addWidget(self.chart_view, 4)

        self.category_table = QTableWidget(0, 4)
        self.category_table.setHorizontalHeaderLabels(["分类", "体积", "占比", "文件数"])
        self.category_table.horizontalHeader().setStretchLastSection(True)
        left.addWidget(self.category_table, 3)

        right = QVBoxLayout()
        body.addLayout(right, 2)

        suggestion_title = QLabel("模拟场景建议")
        suggestion_title.setStyleSheet("font-size:15px; font-weight:600;")
        right.addWidget(suggestion_title)

        self.suggestion_view = QTextEdit()
        self.suggestion_view.setReadOnly(True)
        self.suggestion_view.setPlaceholderText("扫描完成后将生成建议")
        right.addWidget(self.suggestion_view, 1)

        self.export_button = QPushButton("导出分析报告")
        root.addWidget(self.export_button)
        self.export_button.clicked.connect(self.request_export.emit)

    def update_stats(self, stats: dict) -> None:
        breakdown = stats.get("category_breakdown", {}) or {}
        sorted_items = sorted(breakdown.items(), key=lambda x: x[1].get("size", 0), reverse=True)
        total_size = sum(v.get("size", 0) for _, v in sorted_items)
        total_files = sum(v.get("count", 0) for _, v in sorted_items)
        category_count = len([1 for _, v in sorted_items if v.get("size", 0) > 0])

        self.summary_label.setText(
            f"分析完成：共 {category_count} 类，命中 {total_files} 项，可清理约 {format_bytes(total_size)}"
        )
        self.total_size_label.setText(f"可清理体积\n{format_bytes(total_size)}")
        self.total_files_label.setText(f"命中文件数\n{total_files}")
        self.category_count_label.setText(f"分类数量\n{category_count}")

        self._update_pie(sorted_items, total_size)
        self._update_table(sorted_items, total_size)
        self._update_suggestions(sorted_items, total_size)

    def _update_pie(self, sorted_items: list[tuple[str, dict]], total_size: int) -> None:
        self.series.clear()
        if total_size <= 0:
            self.chart.setTitle("文件分类体积分布（暂无数据）")
            return

        top_n = 12
        top = sorted_items[:top_n]
        tail = sorted_items[top_n:]
        others_size = sum(v.get("size", 0) for _, v in tail)
        pie_items = list(top)
        if others_size > 0:
            pie_items.append(("other_files", {"size": others_size, "count": sum(v.get("count", 0) for _, v in tail)}))

        for idx, (category, data) in enumerate(pie_items):
            size = float(data.get("size", 0))
            if size <= 0:
                continue
            label = CATEGORY_LABELS.get(category, category)
            percentage = (size / total_size) * 100
            slice_item = self.series.append(f"{label} {percentage:.1f}%", size)
            slice_item.setLabelVisible(True)
            slice_item.setBrush(QColor(PIE_COLORS[idx % len(PIE_COLORS)]))
            slice_item.setBorderColor(QColor("#ffffff"))
            slice_item.setBorderWidth(1.0)
            if idx == 0:
                slice_item.setExploded(True)
                slice_item.setExplodeDistanceFactor(0.06)

    def _update_table(self, sorted_items: list[tuple[str, dict]], total_size: int) -> None:
        self.category_table.setRowCount(0)
        if total_size <= 0:
            return
        for row, (category, data) in enumerate(sorted_items[:15]):
            size = int(data.get("size", 0))
            count = int(data.get("count", 0))
            percentage = (size / total_size) * 100 if total_size else 0
            self.category_table.insertRow(row)
            self.category_table.setItem(row, 0, QTableWidgetItem(CATEGORY_LABELS.get(category, category)))
            self.category_table.setItem(row, 1, QTableWidgetItem(format_bytes(size)))
            self.category_table.setItem(row, 2, QTableWidgetItem(f"{percentage:.2f}%"))
            self.category_table.setItem(row, 3, QTableWidgetItem(str(count)))

    def _update_suggestions(self, sorted_items: list[tuple[str, dict]], total_size: int) -> None:
        if total_size <= 0:
            self.suggestion_view.setPlainText("暂无可分析数据。")
            return

        size_map = {category: int(data.get("size", 0)) for category, data in sorted_items}
        cache_like = sum(
            size_map.get(key, 0)
            for key in [
                "temporary_files",
                "system_temp_files",
                "app_runtime_cache",
                "browser_cache_files",
                "thumbnail_cache_files",
                "application_log_files",
                "crash_dump_files",
                "windows_update_cache",
                "package_manager_cache",
            ]
        )
        media_like = sum(
            size_map.get(key, 0)
            for key in [
                "image_raster_files",
                "image_vector_files",
                "image_raw_files",
                "video_standard_files",
                "video_production_files",
                "audio_lossy_files",
                "audio_lossless_files",
            ]
        )
        package_like = sum(size_map.get(key, 0) for key in ["archive_files", "disk_image_files", "installer_packages"])
        high_risk_like = sum(
            size_map.get(key, 0)
            for key in [
                "system_core_files",
                "driver_packages",
                "database_files",
                "virtual_machine_files",
                "software_runtime_files",
                "executable_binaries",
            ]
        )

        lines = [
            "预设场景建议（模拟）",
            "",
            f"1) 日常办公缓存堆积场景：当前缓存/日志类约 {format_bytes(cache_like)}。",
            "建议先清理 L1-L2（临时文件、浏览器缓存、崩溃转储、日志），通常风险最低。",
            "",
            f"2) 素材/下载堆积场景：媒体类约 {format_bytes(media_like)}，安装包/压缩包约 {format_bytes(package_like)}。",
            "建议按“最近访问时间+体积”排序，优先处理大体积重复素材和旧安装包。",
            "",
            f"3) 高谨慎数据场景：系统/数据库/虚拟机/可执行类约 {format_bytes(high_risk_like)}。",
            "建议保留 L4-L5，仅做人工核验，不建议一键删除。",
        ]

        if cache_like / max(total_size, 1) >= 0.4:
            lines.append("")
            lines.append("补充判断：缓存类占比偏高，先做一次仅清缓存的安全清理，通常收益明显。")
        if media_like / max(total_size, 1) >= 0.35:
            lines.append("补充判断：媒体占比高，建议增加“按扩展名+目录”的批量整理规则。")
        if high_risk_like / max(total_size, 1) >= 0.2:
            lines.append("补充判断：高谨慎数据占比不低，建议先导出报告再决定是否清理。")

        self.suggestion_view.setPlainText("\n".join(lines))
