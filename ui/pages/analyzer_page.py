from __future__ import annotations

from PySide6.QtCharts import QChart, QChartView, QPieSeries
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QLabel

from ui.pages.dashboard_page import format_bytes


class AnalyzerPage(QWidget):
    request_export = Signal()

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        self.summary_label = QLabel("等待分析数据")
        layout.addWidget(self.summary_label)

        self.chart = QChart()
        self.series = QPieSeries()
        self.chart.addSeries(self.series)
        self.chart_view = QChartView(self.chart)
        self.chart_view.setRenderHint(self.chart_view.renderHints() | self.chart_view.renderHints())
        layout.addWidget(self.chart_view)

        self.export_button = QPushButton("导出分析报告")
        layout.addWidget(self.export_button)
        self.export_button.clicked.connect(self.request_export.emit)

    def update_stats(self, stats: dict) -> None:
        self.series.clear()
        ext_breakdown = stats.get("ext_breakdown", {})
        total = sum(v["size"] for v in ext_breakdown.values()) if ext_breakdown else 0
        for ext, data in list(ext_breakdown.items())[:8]:
            self.series.append(ext, data["size"])
        self.summary_label.setText(f"统计文件总量: {format_bytes(total)} (Top 扩展名展示)")
