from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLineEdit,
    QLabel,
    QCheckBox,
    QPushButton,
    QFormLayout,
    QSpinBox,
)


class SettingsPage(QWidget):
    settings_saved = Signal(dict)

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.base_url = QLineEdit("https://api.openai.com")
        self.api_key = QLineEdit()
        self.api_key.setEchoMode(QLineEdit.Password)
        self.model = QLineEdit("gpt-4o-mini")
        self.mask_paths = QCheckBox("默认脱敏路径")
        self.mask_paths.setChecked(True)
        self.cache_enabled = QCheckBox("AI 调用缓存")
        self.cache_enabled.setChecked(True)
        self.allow_l2 = QCheckBox("允许一键清理 L2")
        self.allow_l2.setChecked(False)
        self.large_file_threshold = QSpinBox()
        self.large_file_threshold.setRange(100, 10240)
        self.large_file_threshold.setValue(500)
        self.large_file_threshold.setSuffix(" MB")

        form.addRow(QLabel("base_url"), self.base_url)
        form.addRow(QLabel("api_key"), self.api_key)
        form.addRow(QLabel("model"), self.model)
        form.addRow(self.mask_paths)
        form.addRow(self.cache_enabled)
        form.addRow(self.allow_l2)
        form.addRow(QLabel("大文件阈值"), self.large_file_threshold)

        layout.addLayout(form)
        self.save_button = QPushButton("保存设置")
        layout.addWidget(self.save_button)
        layout.addStretch(1)

        self.save_button.clicked.connect(self._emit_save)

    def _emit_save(self) -> None:
        self.settings_saved.emit(self.collect_settings())

    def collect_settings(self) -> dict:
        return {
            "base_url": self.base_url.text().strip(),
            "api_key": self.api_key.text().strip(),
            "model": self.model.text().strip(),
            "mask_paths": self.mask_paths.isChecked(),
            "cache_enabled": self.cache_enabled.isChecked(),
            "allow_l2": self.allow_l2.isChecked(),
            "large_file_threshold_mb": self.large_file_threshold.value(),
        }

    def load_settings(self, settings: dict) -> None:
        self.base_url.setText(settings.get("base_url", "https://api.openai.com"))
        self.api_key.setText(settings.get("api_key", ""))
        self.model.setText(settings.get("model", "gpt-4o-mini"))
        self.mask_paths.setChecked(settings.get("mask_paths", True))
        self.cache_enabled.setChecked(settings.get("cache_enabled", True))
        self.allow_l2.setChecked(settings.get("allow_l2", False))
        self.large_file_threshold.setValue(settings.get("large_file_threshold_mb", 500))
