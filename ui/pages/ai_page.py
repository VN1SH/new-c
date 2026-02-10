from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


STAGE_LABELS = {
    "prepare": "准备任务",
    "cache_hit": "命中缓存",
    "cache_miss": "未命中缓存",
    "request": "请求模型",
    "parse": "解析返回",
    "retry": "重试中",
    "done": "完成",
    "failed": "失败",
}


class AIAdvisorPage(QWidget):
    request_clean = Signal(int)
    request_clean_selected = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)

        self.status_label = QLabel("AI 状态：空闲")
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        layout.addWidget(self.status_label)
        layout.addWidget(self.progress_bar)

        self.progress_table = QTableWidget(0, 4)
        self.progress_table.setHorizontalHeaderLabels(["阶段", "状态", "详情", "时间"])
        self.progress_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.progress_table)

        diagnosis_title = QLabel("AI 诊断（基于本地扫描清单）")
        diagnosis_title.setStyleSheet("font-size:15px; font-weight:600;")
        layout.addWidget(diagnosis_title)
        self.diagnosis_view = QTextEdit()
        self.diagnosis_view.setReadOnly(True)
        self.diagnosis_view.setPlaceholderText("诊断结果将在分析完成后显示。")
        self.diagnosis_view.setMinimumHeight(140)
        layout.addWidget(self.diagnosis_view)

        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("谨慎等级筛选："))
        self.level_filter = QComboBox()
        self.level_filter.addItems(["全部", "L1", "L2", "L3", "L4", "L5"])
        filter_row.addWidget(self.level_filter)
        self.level_summary = QLabel("等级分布：-")
        filter_row.addWidget(self.level_summary, 1)
        layout.addLayout(filter_row)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(["勾选", "文件名", "文件路径", "等级", "评级理由", "删除建议", "风险说明"])
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table, 1)

        button_row = QHBoxLayout()
        self.select_visible_button = QPushButton("全选当前筛选")
        self.unselect_all_button = QPushButton("取消全选")
        self.clean_selected_button = QPushButton("一键清理勾选项")
        self.clean_l1_button = QPushButton("一键清理 L1")
        self.clean_l12_button = QPushButton("一键清理 L1+L2")
        for widget in [
            self.select_visible_button,
            self.unselect_all_button,
            self.clean_selected_button,
            self.clean_l1_button,
            self.clean_l12_button,
        ]:
            button_row.addWidget(widget)
        layout.addLayout(button_row)

        self.clean_l1_button.clicked.connect(lambda: self.request_clean.emit(1))
        self.clean_l12_button.clicked.connect(lambda: self.request_clean.emit(2))
        self.clean_selected_button.clicked.connect(self._emit_clean_selected)
        self.select_visible_button.clicked.connect(self._select_visible_rows)
        self.unselect_all_button.clicked.connect(self._unselect_all_rows)
        self.level_filter.currentIndexChanged.connect(self._populate_advice_table)

        self._progress_rows: dict[str, int] = {}
        self._advice_items: list[dict] = []

    def set_ai_running(self, running: bool) -> None:
        if running:
            self.status_label.setText("AI 状态：分析中...")
            self.progress_bar.setRange(0, 0)
            self.progress_table.setRowCount(0)
            self._progress_rows.clear()
        else:
            self.progress_bar.setRange(0, 1)
            self.progress_bar.setValue(1)

    def update_ai_progress(self, progress: dict) -> None:
        step = str(progress.get("stage", "step"))
        detail = str(progress.get("detail", ""))
        step_cn = STAGE_LABELS.get(step, step)

        status = "进行中"
        if step in {"done", "cache_hit"}:
            status = "完成"
        elif step in {"failed"}:
            status = "失败"
        elif step in {"retry"}:
            status = "重试"

        now = datetime.now().strftime("%H:%M:%S")
        row = self._progress_rows.get(step)
        if row is None:
            row = self.progress_table.rowCount()
            self.progress_table.insertRow(row)
            self._progress_rows[step] = row

        self.progress_table.setItem(row, 0, QTableWidgetItem(step_cn))
        self.progress_table.setItem(row, 1, QTableWidgetItem(status))
        self.progress_table.setItem(row, 2, QTableWidgetItem(detail))
        self.progress_table.setItem(row, 3, QTableWidgetItem(now))
        self.status_label.setText(f"AI 状态：{step_cn} - {detail}")

        if step in {"done", "cache_hit", "failed"}:
            self.set_ai_running(False)

    def update_advice(self, advice: dict) -> None:
        if not isinstance(advice, dict):
            advice = {}

        diagnosis = advice.get("diagnosis", {})
        self.diagnosis_view.setPlainText(self._build_diagnosis_text(diagnosis))

        items = advice.get("items", [])
        if not isinstance(items, list):
            items = []
        self._advice_items = [item for item in items if isinstance(item, dict)]

        self._update_level_summary()
        self._populate_advice_table()

    def _build_diagnosis_text(self, diagnosis: object) -> str:
        if isinstance(diagnosis, str):
            return diagnosis
        if not isinstance(diagnosis, dict):
            return "无诊断结果。"

        lines: list[str] = []
        summary = diagnosis.get("summary")
        if summary:
            lines.append(f"总体结论：{summary}")

        highlights = diagnosis.get("highlights", [])
        if isinstance(highlights, list) and highlights:
            lines.append("")
            lines.append("关键发现：")
            lines.extend([f"- {item}" for item in highlights if item])

        risks = diagnosis.get("risks", [])
        if isinstance(risks, list) and risks:
            lines.append("")
            lines.append("风险提醒：")
            lines.extend([f"- {item}" for item in risks if item])

        actions = diagnosis.get("actions", [])
        if isinstance(actions, list) and actions:
            lines.append("")
            lines.append("建议动作：")
            lines.extend([f"- {item}" for item in actions if item])

        if not lines:
            return "无诊断结果。"
        return "\n".join(lines)

    def _update_level_summary(self) -> None:
        counts = {"L1": 0, "L2": 0, "L3": 0, "L4": 0, "L5": 0}
        for item in self._advice_items:
            level = str(item.get("level", "")).upper()
            if level in counts:
                counts[level] += 1
        summary_text = ", ".join([f"{key}:{value}" for key, value in counts.items()])
        self.level_summary.setText(f"等级分布：{summary_text}")

    def _populate_advice_table(self) -> None:
        self.table.setRowCount(0)
        selected_level = self.level_filter.currentText()

        for item in self._advice_items:
            level = str(item.get("level", "")).upper()
            if selected_level != "全部" and level != selected_level:
                continue

            row = self.table.rowCount()
            self.table.insertRow(row)

            checkbox = QTableWidgetItem()
            checkbox.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable | Qt.ItemIsSelectable)
            checkbox.setCheckState(Qt.Unchecked)
            self.table.setItem(row, 0, checkbox)

            target_path = str(item.get("target", ""))
            file_name = str(item.get("file_name", "")).strip()
            if not file_name and target_path:
                file_name = Path(target_path).name

            self.table.setItem(row, 1, QTableWidgetItem(file_name))
            path_item = QTableWidgetItem(target_path)
            path_item.setData(Qt.UserRole, item)
            self.table.setItem(row, 2, path_item)
            self.table.setItem(row, 3, QTableWidgetItem(level))
            self.table.setItem(row, 4, QTableWidgetItem(str(item.get("reason", ""))))
            self.table.setItem(row, 5, QTableWidgetItem(str(item.get("recommended_action", ""))))
            self.table.setItem(row, 6, QTableWidgetItem(str(item.get("risk_notes", ""))))

    def _select_visible_rows(self) -> None:
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item is not None:
                item.setCheckState(Qt.Checked)

    def _unselect_all_rows(self) -> None:
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item is not None:
                item.setCheckState(Qt.Unchecked)

    def _emit_clean_selected(self) -> None:
        selected: list[dict] = []
        for row in range(self.table.rowCount()):
            check_item = self.table.item(row, 0)
            path_item = self.table.item(row, 2)
            if not check_item or not path_item:
                continue
            if check_item.checkState() == Qt.Checked:
                raw = path_item.data(Qt.UserRole)
                if isinstance(raw, dict):
                    selected.append(raw)
        self.request_clean_selected.emit(selected)
