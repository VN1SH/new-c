from __future__ import annotations

import traceback
from pathlib import Path
from typing import Dict, List

from PySide6.QtCore import QObject, QThread, Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QWidget,
)

from core.ai_client import AIClient
from core.ai_local_advisor import build_local_ai_result, merge_remote_into_local
from core.analyzer import Analyzer
from core.cleaner import Cleaner, write_cleanup_plan, write_cleanup_result
from core.payload_builder import PayloadBuilder
from core.report import export_ai_report_html
from core.scanner import ScanItem, Scanner
from core.storage import get_runtime_dir, load_json, write_json
from ui.pages.ai_page import AIAdvisorPage
from ui.pages.ai_report_page import AIReportPage
from ui.pages.analyzer_page import AnalyzerPage
from ui.pages.cleaner_page import CleanerPage
from ui.pages.dashboard_page import DashboardPage, format_bytes
from ui.pages.settings_page import SettingsPage


class Worker(QObject):
    finished = Signal(object)
    error = Signal(str)
    progress = Signal(dict)


class ScanWorker(Worker):
    def __init__(self, stop_flag: dict):
        super().__init__()
        self.stop_flag = stop_flag

    def run(self) -> None:
        try:
            scanner = Scanner(stop_flag=self.stop_flag, progress_callback=self.progress.emit)
            self.finished.emit(scanner.scan())
        except Exception as exc:
            self.error.emit(f"{exc}\n{traceback.format_exc()}")


class CleanWorker(Worker):
    def __init__(self, items: List[ScanItem], dry_run: bool):
        super().__init__()
        self.items = items
        self.dry_run = dry_run

    def run(self) -> None:
        try:
            cleaner = Cleaner(dry_run=self.dry_run)
            self.finished.emit(cleaner.clean(self.items))
        except Exception as exc:
            self.error.emit(f"{exc}\n{traceback.format_exc()}")


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
                progress_callback=self.progress.emit,
            )
            self.finished.emit(client.request_analysis(self.payload))
        except Exception as exc:
            self.error.emit(f"{exc}\n{traceback.format_exc()}")


class ModelsWorker(Worker):
    def __init__(self, base_url: str, api_key: str):
        super().__init__()
        self.base_url = base_url
        self.api_key = api_key

    def run(self) -> None:
        try:
            self.finished.emit(AIClient.fetch_models(self.base_url, self.api_key))
        except Exception as exc:
            self.error.emit(f"{exc}\n{traceback.format_exc()}")


class ApiTestWorker(Worker):
    def __init__(self, base_url: str, api_key: str, model: str):
        super().__init__()
        self.base_url = base_url
        self.api_key = api_key
        self.model = model

    def run(self) -> None:
        try:
            self.finished.emit(AIClient.test_connection(self.base_url, self.api_key, self.model))
        except Exception as exc:
            self.error.emit(f"{exc}\n{traceback.format_exc()}")


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("new-c C盘清理工具")
        self.setFixedSize(1200, 800)
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
        self.ai_advice: Dict = {}
        self.ai_report: Dict = {}
        self.stats: Dict = {}
        self.scan_in_progress = False
        self.ai_in_progress = False
        self.models_in_progress = False
        self.api_test_in_progress = False
        self._models_silent = False

        self._build_ui()
        self._load_settings()

    def _build_ui(self) -> None:
        container = QWidget()
        layout = QHBoxLayout(container)

        self.nav = QListWidget()
        self.nav.addItems(["总览", "清理", "分析", "AI建议", "AI报告", "设置"])
        self.nav.setFixedWidth(160)

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
        self.ai_page.request_clean_selected.connect(self.clean_ai_selected)
        self.analyzer_page.request_export.connect(self.export_analysis)
        self.ai_report_page.request_export.connect(self.export_ai_report)

        self.settings_page.settings_saved.connect(self.save_settings)
        self.settings_page.request_refresh_models.connect(self.fetch_models)
        self.settings_page.request_test_api.connect(self.test_api_connection)

    def _load_settings(self) -> None:
        settings = load_json(
            self.settings_path,
            {
                "base_url": "https://api.openai.com/v1",
                "api_key": "",
                "model": "gpt-4o-mini",
                "mask_paths": False,
                "cache_enabled": True,
                "allow_l2": False,
            },
        )
        settings["base_url"] = AIClient.normalize_base_url(settings.get("base_url", "https://api.openai.com/v1"))
        settings.pop("large_file_threshold_mb", None)
        self.settings = settings
        self.settings_page.load_settings(settings)
        if settings.get("base_url") and settings.get("api_key"):
            self.fetch_models(settings.get("base_url", ""), settings.get("api_key", ""), silent=True)

    def save_settings(self, settings: dict) -> None:
        settings["base_url"] = AIClient.normalize_base_url(settings.get("base_url", ""))
        settings.pop("large_file_threshold_mb", None)
        self.settings = settings
        write_json(self.settings_path, settings)
        if settings.get("base_url") and settings.get("api_key"):
            self.fetch_models(settings.get("base_url", ""), settings.get("api_key", ""), silent=True)
        self.settings_page.set_status("设置已保存")
        QMessageBox.information(self, "设置", "设置已保存。")

    def fetch_models(self, base_url: str, api_key: str, silent: bool = False) -> None:
        if self.models_in_progress:
            return

        normalized = AIClient.normalize_base_url(base_url)
        if not normalized:
            self.settings_page.set_status("模型检测失败：Base URL 为空")
            return
        if not api_key:
            self.settings_page.set_status("请输入 API Key 后再检测模型。")
            return

        self.models_in_progress = True
        self._models_silent = silent
        self.settings_page.set_models_loading(True)

        self.models_thread = QThread()
        self.models_worker = ModelsWorker(normalized, api_key)
        self.models_worker.moveToThread(self.models_thread)
        self.models_thread.started.connect(self.models_worker.run)
        self.models_worker.finished.connect(self._on_models_finished)
        self.models_worker.error.connect(self._on_models_error)
        self.models_worker.finished.connect(self.models_thread.quit)
        self.models_worker.error.connect(self.models_thread.quit)
        self.models_worker.finished.connect(self.models_worker.deleteLater)
        self.models_worker.error.connect(self.models_worker.deleteLater)
        self.models_thread.finished.connect(self.models_thread.deleteLater)
        self.models_thread.start()

    def _on_models_finished(self, models: object) -> None:
        self.models_in_progress = False
        self.settings_page.set_models_loading(False)

        model_list = [m for m in models if isinstance(m, str)] if isinstance(models, list) else []
        self.settings_page.set_models(model_list, keep_current=True)
        self.settings_page.set_status(f"模型检测成功，共 {len(model_list)} 个模型。")
        if model_list and not self._models_silent:
            QMessageBox.information(self, "模型检测", f"检测成功，共 {len(model_list)} 个模型。")

    def _on_models_error(self, message: str) -> None:
        self.models_in_progress = False
        self.settings_page.set_models_loading(False)
        first_line = message.splitlines()[0] if message else "模型检测失败"
        self.settings_page.set_status(f"模型检测失败：{first_line}")
        if not self._models_silent:
            QMessageBox.warning(self, "模型检测失败", first_line)

    def test_api_connection(self, settings: dict) -> None:
        if self.api_test_in_progress:
            return

        base_url = AIClient.normalize_base_url(settings.get("base_url", "")) if isinstance(settings, dict) else ""
        api_key = settings.get("api_key", "") if isinstance(settings, dict) else ""
        model = settings.get("model", "") if isinstance(settings, dict) else ""

        if not base_url:
            QMessageBox.warning(self, "API测试", "Base URL 为空。")
            return
        if not api_key:
            QMessageBox.warning(self, "API测试", "API Key 为空。")
            return
        if not model:
            QMessageBox.warning(self, "API测试", "模型为空。")
            return

        self.api_test_in_progress = True
        self.settings_page.set_status("正在进行 API 测试...")

        self.api_test_thread = QThread()
        self.api_test_worker = ApiTestWorker(base_url, api_key, model)
        self.api_test_worker.moveToThread(self.api_test_thread)
        self.api_test_thread.started.connect(self.api_test_worker.run)
        self.api_test_worker.finished.connect(self._on_api_test_finished)
        self.api_test_worker.error.connect(self._on_api_test_error)
        self.api_test_worker.finished.connect(self.api_test_thread.quit)
        self.api_test_worker.error.connect(self.api_test_thread.quit)
        self.api_test_worker.finished.connect(self.api_test_worker.deleteLater)
        self.api_test_worker.error.connect(self.api_test_worker.deleteLater)
        self.api_test_thread.finished.connect(self.api_test_thread.deleteLater)
        self.api_test_thread.start()

    def _on_api_test_finished(self, result: object) -> None:
        self.api_test_in_progress = False
        payload = result if isinstance(result, dict) else {"ok": False, "message": "未知返回"}
        ok = bool(payload.get("ok", False))
        message = str(payload.get("message", ""))
        if ok:
            self.settings_page.set_status("API 测试成功")
            QMessageBox.information(self, "API测试成功", message or "连接成功。")
        else:
            self.settings_page.set_status("API 测试失败")
            QMessageBox.warning(self, "API测试失败", message or "连接失败。")

    def _on_api_test_error(self, message: str) -> None:
        self.api_test_in_progress = False
        first_line = message.splitlines()[0] if message else "API测试失败"
        self.settings_page.set_status(f"API 测试失败：{first_line}")
        QMessageBox.warning(self, "API测试失败", first_line)

    def start_scan(self) -> None:
        if self.scan_in_progress:
            QMessageBox.information(self, "提示", "扫描正在进行中。")
            return

        self.scan_in_progress = True
        self._set_scan_buttons_enabled(False)
        self.dashboard_page.set_scan_running(True)
        self.cleaner_page.set_scan_running(True)
        self.stop_flag["stop"] = False

        self.scan_thread = QThread()
        self.scan_worker = ScanWorker(self.stop_flag)
        self.scan_worker.moveToThread(self.scan_thread)

        self.scan_thread.started.connect(self.scan_worker.run)
        self.scan_worker.progress.connect(self.on_scan_progress)
        self.scan_worker.finished.connect(self.on_scan_finished)
        self.scan_worker.error.connect(self.on_scan_error)
        self.scan_worker.finished.connect(self.scan_thread.quit)
        self.scan_worker.error.connect(self.scan_thread.quit)
        self.scan_worker.finished.connect(self.scan_worker.deleteLater)
        self.scan_worker.error.connect(self.scan_worker.deleteLater)
        self.scan_thread.finished.connect(self.scan_thread.deleteLater)
        self.scan_thread.start()

    def on_scan_progress(self, payload: dict) -> None:
        self.dashboard_page.update_scan_progress(payload)
        self.cleaner_page.update_scan_progress(payload)

    def stop_scan(self) -> None:
        self.stop_flag["stop"] = True

    def on_scan_finished(self, result) -> None:
        try:
            self.items = result.items
            write_json(self.scan_cache_path, result.to_dict())
            summary = sum(item.size_bytes for item in self.items)
            self.dashboard_page.update_summary(f"扫描完成：共 {len(self.items)} 项，可清理约 {format_bytes(summary)}")
            self.cleaner_page.set_items([item.to_dict() for item in self.items])

            analyzer = Analyzer(self.items)
            self.stats = analyzer.build_stats()
            Analyzer.write_stats(self.stats, self.stats_path)
            self.analyzer_page.update_stats(self.stats)
        except Exception as exc:
            self.on_worker_error(f"{exc}\n{traceback.format_exc()}")
        finally:
            self.scan_in_progress = False
            self._set_scan_buttons_enabled(True)
            self.dashboard_page.set_scan_running(False)
            self.cleaner_page.set_scan_running(False)

    def on_scan_error(self, message: str) -> None:
        self.scan_in_progress = False
        self._set_scan_buttons_enabled(True)
        self.dashboard_page.set_scan_running(False)
        self.cleaner_page.set_scan_running(False)
        self.on_worker_error(message)

    def on_worker_error(self, message: str) -> None:
        try:
            error_log = self.runtime_dir / "error.log"
            with error_log.open("a", encoding="utf-8") as fp:
                fp.write(message.strip())
                fp.write("\n\n")
        except Exception:
            pass
        first_line = message.splitlines()[0] if message else "未知错误"
        QMessageBox.warning(self, "错误", first_line)

    def _set_scan_buttons_enabled(self, enabled: bool) -> None:
        self.dashboard_page.scan_button.setEnabled(enabled)
        self.cleaner_page.scan_button.setEnabled(enabled)
        self.cleaner_page.stop_button.setEnabled(not enabled)

    def _set_ai_buttons_enabled(self, enabled: bool) -> None:
        self.dashboard_page.ai_button.setEnabled(enabled)
        self.dashboard_page.ai_clean_button.setEnabled(enabled)
        self.cleaner_page.clean_l1_button.setEnabled(enabled)
        self.cleaner_page.clean_l12_button.setEnabled(enabled)
        self.ai_page.clean_l1_button.setEnabled(enabled)
        self.ai_page.clean_l12_button.setEnabled(enabled)
        self.ai_page.clean_selected_button.setEnabled(enabled)

    def select_ai_level(self, level: int) -> None:
        target_levels = {"L1"} if level == 1 else {"L1", "L2"}
        for row in range(self.cleaner_page.table.rowCount()):
            level_item = self.cleaner_page.table.item(row, 6)
            check_item = self.cleaner_page.table.item(row, 0)
            if level_item and check_item and level_item.text() in target_levels:
                check_item.setCheckState(Qt.Checked)

    def clean_selected(self) -> None:
        selected_rows = self.cleaner_page.selected_items()
        selected_items = [self.items[idx] for idx in selected_rows if idx < len(self.items)]
        self._run_cleanup(selected_items)

    def clean_ai(self, level: int) -> None:
        allowed_levels = {"L1"} if level == 1 else {"L1", "L2"}
        selected_items = [item for item in self.items if item.ai_level in allowed_levels]
        if level > 1 and not self.settings.get("allow_l2", False):
            QMessageBox.information(self, "提示", "设置中未开启 L2 一键清理。")
            return
        self._run_cleanup(selected_items)

    def clean_ai_selected(self, entries) -> None:
        if not isinstance(entries, list) or not entries:
            QMessageBox.information(self, "提示", "请先勾选 AI 清单中的目标。")
            return

        path_map = {item.path.lower(): item for item in self.items}
        selected: List[ScanItem] = []
        selected_paths = set()
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            item: ScanItem | None = None
            item_id = entry.get("item_id")
            if isinstance(item_id, int) and 0 <= item_id < len(self.items):
                item = self.items[item_id]
            if item is None:
                target = str(entry.get("target", "")).lower()
                item = path_map.get(target)
            if item is None:
                continue
            if item.path not in selected_paths:
                selected.append(item)
                selected_paths.add(item.path)

        if not selected:
            QMessageBox.information(self, "提示", "勾选项未匹配到本地可清理文件。")
            return
        self._run_cleanup(selected)

    def _run_cleanup(self, items: List[ScanItem]) -> None:
        if not items:
            QMessageBox.information(self, "提示", "没有可清理项。")
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
        self.clean_worker.error.connect(self.clean_thread.quit)
        self.clean_worker.finished.connect(self.clean_worker.deleteLater)
        self.clean_worker.error.connect(self.clean_worker.deleteLater)
        self.clean_thread.finished.connect(self.clean_thread.deleteLater)
        self.clean_thread.start()

    def on_clean_finished(self, result) -> None:
        write_cleanup_result(result, self.cleanup_result_path)
        QMessageBox.information(self, "完成", f"已处理 {len(result.deleted)} 项。")

    def start_ai(self) -> None:
        if self.ai_in_progress:
            QMessageBox.information(self, "提示", "AI 分析正在运行。")
            return
        if not self.items:
            QMessageBox.information(self, "提示", "请先执行扫描。")
            return

        builder = PayloadBuilder(mask_paths=self.settings.get("mask_paths", False), max_items=max(1, len(self.items)))
        user_intent = {
            "mode": "balanced",
            "allow_auto_level": "L1" if not self.settings.get("allow_l2") else "L2",
            "rating_policy": "five_level_only",
            "required_fields": ["file_name", "path", "level", "reason", "recommended_action"],
        }
        payload = builder.build(self.items, self.stats, user_intent)
        builder.write_payload(payload, self.payload_path)

        if not self.settings.get("api_key"):
            local = build_local_ai_result(self.items, self.stats)
            self.ai_advice = local.get("advice", {})
            self.ai_report = local.get("report", {})
            write_json(self.ai_advice_path, self.ai_advice)
            write_json(self.ai_report_path, self.ai_report)
            self.ai_page.update_advice(self.ai_advice)
            self.ai_report_page.update_report(self.ai_report)
            self._apply_ai_to_items()
            self.ai_page.update_ai_progress({"stage": "done", "detail": "已使用本地策略完成诊断（未配置 API Key）"})
            return

        self.ai_in_progress = True
        self._set_ai_buttons_enabled(False)
        self.ai_page.set_ai_running(True)
        self.ai_page.update_ai_progress({"stage": "prepare", "detail": "正在准备分析任务..."})

        self.ai_thread = QThread()
        self.ai_worker = AIWorker(self.settings, payload, self.ai_cache_path)
        self.ai_worker.moveToThread(self.ai_thread)
        self.ai_thread.started.connect(self.ai_worker.run)
        self.ai_worker.progress.connect(self.on_ai_progress)
        self.ai_worker.finished.connect(self.on_ai_finished)
        self.ai_worker.error.connect(self.on_ai_error)
        self.ai_worker.finished.connect(self.ai_thread.quit)
        self.ai_worker.error.connect(self.ai_thread.quit)
        self.ai_worker.finished.connect(self.ai_worker.deleteLater)
        self.ai_worker.error.connect(self.ai_worker.deleteLater)
        self.ai_thread.finished.connect(self.ai_thread.deleteLater)
        self.ai_thread.start()

    def on_ai_progress(self, payload: dict) -> None:
        self.ai_page.update_ai_progress(payload)

    def on_ai_error(self, message: str) -> None:
        self.ai_in_progress = False
        self._set_ai_buttons_enabled(True)

        local = build_local_ai_result(self.items, self.stats)
        self.ai_advice = local.get("advice", {})
        self.ai_report = local.get("report", {})
        write_json(self.ai_advice_path, self.ai_advice)
        write_json(self.ai_report_path, self.ai_report)
        self.ai_page.update_advice(self.ai_advice)
        self.ai_report_page.update_report(self.ai_report)
        self._apply_ai_to_items()
        self.ai_page.update_ai_progress({"stage": "failed", "detail": "远端 AI 失败，已回退到本地策略"})
        self.on_worker_error(message)

    def on_ai_finished(self, result: dict) -> None:
        try:
            if not isinstance(result, dict):
                raise RuntimeError(f"AI 返回类型异常：{type(result).__name__}")

            local = build_local_ai_result(self.items, self.stats)
            merged = merge_remote_into_local(local, result, self.items)
            self.ai_advice = merged.get("advice", {})
            self.ai_report = merged.get("report", {})
            write_json(self.ai_advice_path, self.ai_advice)
            write_json(self.ai_report_path, self.ai_report)
            self.ai_page.update_advice(self.ai_advice)
            self.ai_report_page.update_report(self.ai_report)
            self._apply_ai_to_items()
            self.ai_page.update_ai_progress({"stage": "done", "detail": "AI 分析完成。"})
        except Exception as exc:
            self.on_worker_error(f"{exc}\n{traceback.format_exc()}")
            self.ai_page.update_ai_progress({"stage": "failed", "detail": str(exc)})
        finally:
            self.ai_in_progress = False
            self._set_ai_buttons_enabled(True)

    def _apply_ai_to_items(self) -> None:
        advice_items = [item for item in self.ai_advice.get("items", []) if isinstance(item, dict)]
        advice_by_path = {str(item.get("target", "")).lower(): item for item in advice_items}
        advice_by_id = {item.get("item_id"): item for item in advice_items if isinstance(item.get("item_id"), int)}

        for idx, item in enumerate(self.items):
            advice = advice_by_id.get(idx)
            if advice is None:
                advice = advice_by_path.get(item.path.lower())
            if advice is None:
                continue
            item.ai_level = str(advice.get("level", item.ai_level))
            item.ai_reason = str(advice.get("reason", ""))
            item.recommended_action = str(advice.get("recommended_action", ""))
            item.ai_risk_notes = str(advice.get("risk_notes", ""))
            item.ai_confidence = float(advice.get("confidence", 0.0) or 0.0)
            item.ai_requires_confirmation = bool(advice.get("requires_confirmation", item.ai_requires_confirmation))

        self.cleaner_page.set_items([item.to_dict() for item in self.items])

    def export_analysis(self) -> None:
        path = self.runtime_dir / "analysis_export.json"
        write_json(path, self.stats)
        QMessageBox.information(self, "导出", f"已保存到：{path}")

    def export_ai_report(self) -> None:
        path = self.runtime_dir / "ai_report.html"
        export_ai_report_html(self.ai_report, path)
        QMessageBox.information(self, "导出", f"已保存到：{path}")
