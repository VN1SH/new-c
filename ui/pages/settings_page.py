from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.ai_client import AIClient


class SettingsPage(QWidget):
    settings_saved = Signal(dict)
    request_refresh_models = Signal(str, str)
    request_test_api = Signal(dict)

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.base_url = QLineEdit("https://api.openai.com/v1")
        self.api_key = QLineEdit()
        self.api_key.setEchoMode(QLineEdit.Password)

        self.model_combo = QComboBox()
        self.model_combo.setEditable(True)
        self.model_combo.setInsertPolicy(QComboBox.NoInsert)
        self.model_combo.addItem("gpt-4o-mini")

        self.refresh_models_button = QPushButton("检测可用模型 (/v1/models)")
        self.test_api_button = QPushButton("API 连接测试")
        self.refresh_models_button.setMinimumWidth(220)
        self.test_api_button.setMinimumWidth(140)
        action_row = QHBoxLayout()
        action_row.addWidget(self.refresh_models_button)
        action_row.addWidget(self.test_api_button)
        action_row.addStretch(1)
        action_widget = QWidget()
        action_widget.setLayout(action_row)

        self.status_label = QLabel("状态：待检测")
        self.status_label.setWordWrap(True)

        self.mask_paths = QCheckBox("发送给 AI 前脱敏本地路径")
        self.mask_paths.setChecked(False)
        self.cache_enabled = QCheckBox("启用 AI 结果缓存")
        self.cache_enabled.setChecked(True)
        self.allow_l2 = QCheckBox("允许 L2 一键清理")
        self.allow_l2.setChecked(False)

        form.addRow(QLabel("接口地址"), self.base_url)
        form.addRow(QLabel("API Key"), self.api_key)
        form.addRow(QLabel("模型"), self.model_combo)
        form.addRow(QLabel("模型与连接"), action_widget)
        form.addRow(QLabel("接口状态"), self.status_label)
        form.addRow(self.mask_paths)
        form.addRow(self.cache_enabled)
        form.addRow(self.allow_l2)

        layout.addLayout(form)
        self.save_button = QPushButton("保存设置")
        layout.addWidget(self.save_button)
        layout.addStretch(1)

        self.save_button.clicked.connect(self._emit_save)
        self.refresh_models_button.clicked.connect(self._emit_refresh_models)
        self.test_api_button.clicked.connect(self._emit_test_api)
        self.base_url.editingFinished.connect(self._on_base_url_edited)
        self.api_key.editingFinished.connect(self._emit_refresh_models)

    def _normalize_base_url_field(self) -> str:
        normalized = AIClient.normalize_base_url(self.base_url.text())
        if normalized:
            self.base_url.setText(normalized)
        return normalized

    def _on_base_url_edited(self) -> None:
        self._normalize_base_url_field()
        self._emit_refresh_models()

    def _emit_save(self) -> None:
        self._normalize_base_url_field()
        self.settings_saved.emit(self.collect_settings())

    def _emit_refresh_models(self) -> None:
        url = self._normalize_base_url_field()
        api_key = self.api_key.text().strip()
        if not url:
            return
        self.request_refresh_models.emit(url, api_key)

    def _emit_test_api(self) -> None:
        self._normalize_base_url_field()
        self.request_test_api.emit(self.collect_settings())

    def collect_settings(self) -> dict:
        return {
            "base_url": self.base_url.text().strip(),
            "api_key": self.api_key.text().strip(),
            "model": self.model_combo.currentText().strip(),
            "mask_paths": self.mask_paths.isChecked(),
            "cache_enabled": self.cache_enabled.isChecked(),
            "allow_l2": self.allow_l2.isChecked(),
        }

    def load_settings(self, settings: dict) -> None:
        self.base_url.setText(AIClient.normalize_base_url(settings.get("base_url", "https://api.openai.com/v1")))
        self.api_key.setText(settings.get("api_key", ""))
        self.set_models([settings.get("model", "gpt-4o-mini")], keep_current=False)
        self.model_combo.setCurrentText(settings.get("model", "gpt-4o-mini"))
        self.mask_paths.setChecked(settings.get("mask_paths", False))
        self.cache_enabled.setChecked(settings.get("cache_enabled", True))
        self.allow_l2.setChecked(settings.get("allow_l2", False))

    def set_models(self, models: list[str], keep_current: bool = True) -> None:
        current = self.model_combo.currentText().strip()
        new_models = [m.strip() for m in models if isinstance(m, str) and m.strip()]
        if keep_current and current and current not in new_models:
            new_models.insert(0, current)
        if not new_models:
            if current:
                new_models = [current]
            else:
                new_models = ["gpt-4o-mini"]

        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        self.model_combo.addItems(new_models)
        if current:
            self.model_combo.setCurrentText(current)
        self.model_combo.blockSignals(False)

    def set_models_loading(self, loading: bool) -> None:
        self.refresh_models_button.setEnabled(not loading)
        self.test_api_button.setEnabled(not loading)
        if loading:
            self.status_label.setText("状态：正在获取模型列表...")

    def set_status(self, text: str) -> None:
        self.status_label.setText(f"状态：{text}")
