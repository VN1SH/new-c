from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import List

from PySide6.QtCore import Qt, QThread, QObject, Signal
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QHBoxLayout,
    QListWidget,
    QStackedWidget,
    QMessageBox,
)

from core.analyzer import Analyzer
from core.ai_client import AIClient
from core.cleaner import Cleaner, write_cleanup_plan, write_cleanup_result
from core.payload_builder import PayloadBuilder
from core.scanner import ScanItem, Scanner
from core.storage import get_runtime_dir, load_json, write_json
from core.report import export_ai_report_html
from ui.pages.dashboard_page import DashboardPage, format_bytes
from ui.pages.cleaner_page import CleanerPage
from ui.pages.analyzer_page import AnalyzerPage
from ui.pages.ai_page import AIAdvisorPage
from ui.pages.ai_report_page import AIReportPage
from ui.pages.settings_page import SettingsPage


class Worker(QObject):
    finished = Signal(object)
    error = Signal(str)


class ScanWorker(Worker):
    def __init__(self, stop_flag: dict):
        super().__init__()
        self.stop_flag = stop_flag

    def run(self) -> None:
        try:
            scanner = Scanner(stop_flag=self.stop_flag)
            result = scanner.scan()
            self.finished.emit(result)
        except Exception as exc:
            self.error.emit(str(exc))


class CleanWorker(Worker):
    def __init__(self, items: List[ScanItem], dry_run: bool):
        super().__init__()
        self.items = items
        self.dry_run = dry_run

    def run(self) -> None:
        try:
            cleaner = Cleaner(dry_run=self.dry_run)
            result = cleaner.clean(self.items)
            self.finished.emit(result)
        except Exception as exc:
            self.error.emit(str(exc))


class AIWorker(Worker):
    def __init__(self, settings: dict, payload: dict, cache_path: Path):
        super().__init__()
        self.settings = settings
        self.payload = payload
        self.cache_path = cache_path

    def run(self) -> None:
        try:
            client = AIClient(
                base_url=self.settings.get("base_url", ""),
                api_key=self.settings.get("api_key", ""),
                model=self.settings.get("model", ""),
                cache_enabled=self.settings.get("cache_enabled", True),
                cache_path=self.cache_path,
            )
            result = client.request_analysis(self.payload)
            self.finished.emit(result)
        except Exception as exc:
            self.error.emit(str(exc))


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("new-c C盘清理工具")
        self.runtime_dir = get_runtime_dir()

        self.scan_cache_path = self.runtime_dir / "scan_cache.json"
        self.stats_path = self.runtime_dir / "analysis_stats.json"
        self.payload_path = self.runtime_dir / "analysis_payload.json"
        self.ai_advice_path = self.runtime_dir / "ai_advice.json"
        self.ai_report_path = self.runtime_dir / "ai_report.json"
        self.cleanup_plan_path = self.runtime_dir / "cleanup_plan.json"
        self.cleanup_result_path = self.runtime_dir / "cleanup_result.json"
        self.settings_path = self.runtime_dir / "settings.json"
        self.ai_cache_path = self.runtime_dir / "ai_cache.json"

        self.stop_flag = {"stop": False}
        self.items: List[ScanItem] = []
        self.ai_advice = {}
        self.ai_report = {}
        self.stats = {}

        self._build_ui()
        self._load_settings()

    def _build_ui(self) -> None:
        container = QWidget()
        layout = QHBoxLayout(container)

        self.nav = QListWidget()
        self.nav.addItems(["Dashboard", "Cleaner", "Analyzer", "AI Advisor", "AI Report", "Settings"])
        self.nav.setFixedWidth(140)

        self.stack = QStackedWidget()
        self.dashboard_page = DashboardPage()
        self.cleaner_page = CleanerPage()
        self.analyzer_page = AnalyzerPage()
        self.ai_page = AIAdvisorPage()
        self.ai_report_page = AIReportPage()
        self.settings_page = SettingsPage()

        for page in [
            self.dashboard_page,
            self.cleaner_page,
            self.analyzer_page,
            self.ai_page,
            self.ai_report_page,
            self.settings_page,
        ]:
            self.stack.addWidget(page)

        layout.addWidget(self.nav)
        layout.addWidget(self.stack, 1)
        self.setCentralWidget(container)

        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.nav.setCurrentRow(0)

        self.dashboard_page.request_scan.connect(self.start_scan)
        self.dashboard_page.request_ai.connect(self.start_ai)
        self.dashboard_page.request_ai_clean.connect(lambda: self.clean_ai(1))

        self.cleaner_page.request_scan.connect(self.start_scan)
        self.cleaner_page.request_stop.connect(self.stop_scan)
        self.cleaner_page.request_clean_selected.connect(self.clean_selected)
        self.cleaner_page.request_ai_select.connect(self.select_ai_level)
        self.cleaner_page.request_ai_clean.connect(self.clean_ai)

        self.ai_page.request_clean.connect(self.clean_ai)
        self.analyzer_page.request_export.connect(self.export_analysis)
        self.ai_report_page.request_export.connect(self.export_ai_report)
        self.settings_page.settings_saved.connect(self.save_settings)

    def _load_settings(self) -> None:
        settings = load_json(
            self.settings_path,
            {
                "base_url": "https://api.openai.com",
                "api_key": "",
                "model": "gpt-4o-mini",
                "mask_paths": True,
                "cache_enabled": True,
                "allow_l2": False,
                "large_file_threshold_mb": 500,
            },
        )
        self.settings = settings
        self.settings_page.load_settings(settings)

    def save_settings(self, settings: dict) -> None:
        self.settings = settings
        write_json(self.settings_path, settings)
        QMessageBox.information(self, "设置", "设置已保存")

    def start_scan(self) -> None:
        self.stop_flag["stop"] = False
        self.scan_thread = QThread()
        self.scan_worker = ScanWorker(self.stop_flag)
        self.scan_worker.moveToThread(self.scan_thread)
        self.scan_thread.started.connect(self.scan_worker.run)
        self.scan_worker.finished.connect(self.on_scan_finished)
        self.scan_worker.error.connect(self.on_worker_error)
        self.scan_worker.finished.connect(self.scan_thread.quit)
        self.scan_thread.start()

    def stop_scan(self) -> None:
        self.stop_flag["stop"] = True

    def on_scan_finished(self, result) -> None:
        self.items = result.items
        write_json(self.scan_cache_path, result.to_dict())
        summary = sum(item.size_bytes for item in self.items)
        self.dashboard_page.update_summary(
            f"扫描完成，文件数 {len(self.items)}，可清理约 {format_bytes(summary)}"
        )
        self.cleaner_page.set_items([item.to_dict() for item in self.items])
        analyzer = Analyzer(self.items)
        self.stats = analyzer.build_stats()
        Analyzer.write_stats(self.stats, self.stats_path)
        self.analyzer_page.update_stats(self.stats)

    def on_worker_error(self, message: str) -> None:
        QMessageBox.warning(self, "错误", message)

    def select_ai_level(self, level: int) -> None:
        target_levels = {"L1"} if level == 1 else {"L1", "L2"}
        for row in range(self.cleaner_page.table.rowCount()):
            level_item = self.cleaner_page.table.item(row, 5)
            if level_item and level_item.text() in target_levels:
                self.cleaner_page.table.item(row, 0).setCheckState(Qt.Checked)

    def clean_selected(self) -> None:
        selected_rows = self.cleaner_page.selected_items()
        selected_items = [self.items[idx] for idx in selected_rows if idx < len(self.items)]
        self._run_cleanup(selected_items)

    def clean_ai(self, level: int) -> None:
        allowed_levels = {"L1"} if level == 1 else {"L1", "L2"}
        selected_items = [item for item in self.items if item.ai_level in allowed_levels]
        if level > 1 and not self.settings.get("allow_l2", False):
            QMessageBox.information(self, "提示", "设置中未允许 L2 一键清理")
            return
        self._run_cleanup(selected_items)

    def _run_cleanup(self, items: List[ScanItem]) -> None:
        if not items:
            QMessageBox.information(self, "提示", "没有可清理项")
            return
        confirm = QMessageBox.question(self, "确认", f"即将清理 {len(items)} 项，是否继续？")
        if confirm != QMessageBox.Yes:
            return
        write_cleanup_plan(items, self.cleanup_plan_path)
        dry_run = self.cleaner_page.is_dry_run()
        self.clean_thread = QThread()
        self.clean_worker = CleanWorker(items, dry_run)
        self.clean_worker.moveToThread(self.clean_thread)
        self.clean_thread.started.connect(self.clean_worker.run)
        self.clean_worker.finished.connect(self.on_clean_finished)
        self.clean_worker.error.connect(self.on_worker_error)
        self.clean_worker.finished.connect(self.clean_thread.quit)
        self.clean_thread.start()

    def on_clean_finished(self, result) -> None:
        write_cleanup_result(result, self.cleanup_result_path)
        QMessageBox.information(self, "清理完成", f"已清理 {len(result.deleted)} 项")

    def start_ai(self) -> None:
        if not self.items:
            QMessageBox.information(self, "提示", "请先扫描")
            return
        builder = PayloadBuilder(mask_paths=self.settings.get("mask_paths", True))
        user_intent = {
            "mode": "balanced",
            "allow_auto_level": "L1" if not self.settings.get("allow_l2") else "L2",
            "thresholds": {"large_file_mb": self.settings.get("large_file_threshold_mb", 500)},
        }
        payload = builder.build(self.items, self.stats, user_intent)
        builder.write_payload(payload, self.payload_path)

        if not self.settings.get("api_key"):
            QMessageBox.warning(self, "AI", "未配置 API Key")
            return

        self.ai_thread = QThread()
        self.ai_worker = AIWorker(self.settings, payload, self.ai_cache_path)
        self.ai_worker.moveToThread(self.ai_thread)
        self.ai_thread.started.connect(self.ai_worker.run)
        self.ai_worker.finished.connect(self.on_ai_finished)
        self.ai_worker.error.connect(self.on_worker_error)
        self.ai_worker.finished.connect(self.ai_thread.quit)
        self.ai_thread.start()

    def on_ai_finished(self, result: dict) -> None:
        self.ai_advice = result.get("advice", {})
        self.ai_report = result.get("report", {})
        write_json(self.ai_advice_path, self.ai_advice)
        write_json(self.ai_report_path, self.ai_report)
        self.ai_page.update_advice(self.ai_advice)
        self.ai_report_page.update_report(self.ai_report)
        self._apply_ai_to_items()

    def _apply_ai_to_items(self) -> None:
        advice_map = {item.get("target"): item for item in self.ai_advice.get("items", [])}
        for item in self.items:
            advice = advice_map.get(item.path)
            if not advice:
                continue
            item.ai_level = advice.get("level", item.ai_level)
            item.ai_reason = advice.get("reason", "")
            item.ai_confidence = advice.get("confidence", 0.0)
        self.cleaner_page.set_items([item.to_dict() for item in self.items])

    def export_analysis(self) -> None:
        path = self.runtime_dir / "analysis_export.json"
        write_json(path, self.stats)
        QMessageBox.information(self, "导出", f"分析报告已保存: {path}")

    def export_ai_report(self) -> None:
        path = self.runtime_dir / "ai_report.html"
        export_ai_report_html(self.ai_report, path)
        QMessageBox.information(self, "导出", f"AI 报告已保存: {path}")
