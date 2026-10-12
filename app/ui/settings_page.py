from __future__ import annotations

from pathlib import Path
from typing import Any

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.theme import normalize_theme
from app.ui.widgets import section


class SettingsPage(QWidget):
    """Theme, browser mode, and extension folder."""

    def __init__(self, host: Any):
        super().__init__()
        self.host = host
        settings = host.state["settings"]

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        panel = section(
            host,
            "Settings",
            "Theme, browser mode, and the extension folder that contains prompts/, profile-context/, and profiles.json.",
        )
        root.addWidget(panel)
        root.addStretch(1)

        theme_row = QHBoxLayout()
        theme_label = QLabel("Theme")
        theme_label.setObjectName("sectionHint")
        self.theme_combo = QComboBox()
        self.theme_combo.addItem("System", "system")
        self.theme_combo.addItem("Light", "light")
        self.theme_combo.addItem("Dark", "dark")
        current = normalize_theme(settings.get("theme"))
        self.theme_combo.setCurrentIndex(max(0, self.theme_combo.findData(current)))
        theme_row.addWidget(theme_label)
        theme_row.addWidget(self.theme_combo, 1)
        panel.layout().addLayout(theme_row)

        browser_row = QHBoxLayout()
        browser_label = QLabel("Browser mode")
        browser_label.setObjectName("sectionHint")
        self.browser_combo = QComboBox()
        self.browser_combo.addItem("Isolated (keep normal Chrome open)", "isolated")
        self.browser_combo.addItem("Live (real profiles via debug port)", "live")
        mode = str(settings.get("browserMode") or "isolated").lower()
        if mode not in {"isolated", "live"}:
            mode = "isolated"
        self.browser_combo.setCurrentIndex(max(0, self.browser_combo.findData(mode)))
        self.browser_combo.setToolTip(
            "Isolated: private profile copies under .app-data — your everyday Chrome stays open.\n"
            "Live: opens selected profiles in your real Chrome; requires Chrome started with debugging."
        )
        browser_row.addWidget(browser_label)
        browser_row.addWidget(self.browser_combo, 1)
        panel.layout().addLayout(browser_row)

        form = QFormLayout()
        form.setSpacing(12)
        form.setLabelAlignment(Qt.AlignLeft)

        ext_row = QHBoxLayout()
        ext_row.setSpacing(8)
        cur_ext = str(settings.get("extensionDir") or "")
        if not cur_ext and settings.get("promptsDir"):
            cur_ext = str(Path(settings["promptsDir"]).parent)
        self.extension_dir_edit = QLineEdit(cur_ext)
        self.extension_dir_edit.setPlaceholderText(
            "Folder with prompts/, profile-context/, and profiles.json"
        )
        browse_btn = QPushButton("Browse...")
        browse_btn.setObjectName("ghost")
        browse_btn.clicked.connect(self._browse_extension_dir)
        ext_row.addWidget(self.extension_dir_edit, 1)
        ext_row.addWidget(browse_btn)
        form.addRow("Extension folder", ext_row)
        panel.layout().addLayout(form)

        actions = QHBoxLayout()
        save = QPushButton("Save")
        save.setObjectName("primary")
        save.clicked.connect(self.save)
        self.saved_label = QLabel("")
        self.saved_label.setObjectName("muted")
        actions.addWidget(save)
        actions.addWidget(self.saved_label)
        actions.addStretch(1)
        panel.layout().addLayout(actions)

    def _browse_extension_dir(self) -> None:
        initial = self.extension_dir_edit.text().strip()
        directory = QFileDialog.getExistingDirectory(
            self, "Select Chrome Extension Folder", initial or ""
        )
        if directory:
            self.extension_dir_edit.setText(directory)

    def values(self) -> dict[str, Any]:
        ext_dir = self.extension_dir_edit.text().strip()
        data: dict[str, Any] = {
            "extensionDir": ext_dir,
            "theme": normalize_theme(self.theme_combo.currentData()),
            "browserMode": self.browser_combo.currentData() or "isolated",
        }
        if ext_dir:
            root = Path(ext_dir)
            data["promptsDir"] = str(root / "prompts")
            data["profileContextDir"] = str(root / "profile-context")
            data["profilesJsonPath"] = str(root / "profiles.json")
        return data

    def save(self) -> None:
        self.host.state["settings"].update(self.values())
        self.host.persist()
        self.host.apply_theme(force=True)
        self.saved_label.setText("Saved")
