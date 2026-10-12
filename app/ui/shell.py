from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.bridge import Bridge
from app.history import record_bids
from app.store import checked_profiles, load_state, save_state
from app.theme import normalize_theme, resolve_theme, stylesheet_for
from app.ui.analytics_page import AnalyticsPage
from app.ui.dashboard import DashboardPage
from app.ui.profiles_page import ProfilesPage
from app.ui.settings_page import SettingsPage
from app.ui.widgets import polish


class MainWindow(QMainWindow):
    def __init__(self, user_data: Path):
        super().__init__()
        self.user_data = user_data
        self.user_data.mkdir(parents=True, exist_ok=True)
        self.bridge = Bridge(user_data)
        self.state = load_state(user_data)
        self.status_by_profile: dict[str, dict[str, Any]] = {}
        self.finish_message = ""
        self.running = False
        self._section = "dashboard"
        self._resolved_theme = resolve_theme(self.state["settings"].get("theme"))

        self.setWindowTitle("Bidding")
        self.resize(1100, 760)
        self.setMinimumSize(880, 640)

        shell = QWidget()
        shell.setObjectName("appRoot")
        self.shell = shell
        self.setCentralWidget(shell)
        root = QHBoxLayout(shell)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.apply_theme(force=True)

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(188)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(10, 16, 10, 16)
        side.setSpacing(2)
        title = QLabel("Bidding")
        title.setObjectName("sideTitle")
        side.addWidget(title)

        self.dashboard_btn = self._nav_button("Main", self.show_dashboard)
        self.analytics_btn = self._nav_button("Analytics", self.show_analytics)
        self.profiles_btn = self._nav_button("Profiles", self.show_profiles)
        self.settings_btn = self._nav_button("Settings", self.show_settings)
        side.addWidget(self.dashboard_btn)
        side.addWidget(self.analytics_btn)
        side.addWidget(self.profiles_btn)
        side.addWidget(self.settings_btn)
        side.addStretch(1)

        content = QWidget()
        content.setObjectName("content")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(20, 16, 20, 16)
        self.stack = QStackedWidget()
        self.dashboard = DashboardPage(self)
        self.analytics_page = AnalyticsPage(self)
        self.profiles_page = ProfilesPage(self)
        self.settings_page = SettingsPage(self)
        self.stack.addWidget(self.dashboard)
        self.stack.addWidget(self.analytics_page)
        self.stack.addWidget(self.profiles_page)
        self.stack.addWidget(self.settings_page)
        content_layout.addWidget(self.stack)
        root.addWidget(sidebar)
        root.addWidget(content, 1)

        self.bridge.statusChanged.connect(self.on_status)
        self.bridge.runStateChanged.connect(self.on_run_state)

        self.theme_timer = QTimer(self)
        self.theme_timer.setInterval(2500)
        self.theme_timer.timeout.connect(self._sync_system_theme)
        self.theme_timer.start()

        self.show_dashboard()

    def persist(self, *, commit: bool = True) -> None:
        if commit and hasattr(self, "dashboard"):
            self.dashboard.commit_urls()
        save_state(self.user_data, self.state)

    def alert(self, title: str, text: str, critical: bool = False) -> None:
        box = QMessageBox(self)
        box.setWindowTitle(title)
        box.setText(text)
        box.setIcon(QMessageBox.Critical if critical else QMessageBox.Warning)
        box.setStyleSheet(stylesheet_for(self._resolved_theme))
        box.exec_()

    def on_profiles_changed(self) -> None:
        self.dashboard.refresh_lists()

    def show_dashboard(self) -> None:
        self.stack.setCurrentWidget(self.dashboard)
        self.dashboard.refresh_lists()
        self.dashboard.refresh_progress()
        self._mark_nav("dashboard")

    def show_analytics(self) -> None:
        self.stack.setCurrentWidget(self.analytics_page)
        self.analytics_page.refresh()
        self._mark_nav("analytics")

    def show_profiles(self) -> None:
        self.stack.setCurrentWidget(self.profiles_page)
        self.profiles_page.refresh()
        self._mark_nav("profiles")

    def show_settings(self) -> None:
        self.stack.setCurrentWidget(self.settings_page)
        self._mark_nav("settings")

    def _nav_button(self, label: str, handler) -> QPushButton:
        button = QPushButton(label)
        button.setObjectName("nav")
        button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        button.clicked.connect(handler)
        return button

    def _mark_nav(self, which: str) -> None:
        self._section = which
        buttons = (
            ("dashboard", self.dashboard_btn),
            ("analytics", self.analytics_btn),
            ("profiles", self.profiles_btn),
            ("settings", self.settings_btn),
        )
        for key, button in buttons:
            button.setProperty("active", "true" if key == which else "false")
            polish(button)

    def apply_theme(self, force: bool = False) -> None:
        choice = normalize_theme(self.state["settings"].get("theme"))
        resolved = resolve_theme(choice)
        if not force and resolved == self._resolved_theme:
            return
        self._resolved_theme = resolved
        self.setStyleSheet(stylesheet_for(resolved))
        if hasattr(self, "dashboard"):
            self.dashboard.set_running(self.running)
            self.dashboard.refresh_lists()
            self.dashboard.refresh_progress()
        if hasattr(self, "analytics_page"):
            self.analytics_page.refresh()
        if hasattr(self, "profiles_page"):
            self.profiles_page.refresh()
        self.update()
        if hasattr(self, "dashboard_btn"):
            self._mark_nav(self._section)

    def _sync_system_theme(self) -> None:
        if normalize_theme(self.state["settings"].get("theme")) != "system":
            return
        self.apply_theme(force=False)

    def toggle_run(self) -> None:
        if self.running:
            self.bridge.stop()
            self.dashboard.set_running(True, "Stopping…")
            return

        self.dashboard.commit_urls()
        self.persist()
        urls = [item for item in self.state.get("urls") or [] if item.get("url")]
        profiles = [
            profile
            for profile in checked_profiles(self.state)
            if (profile.get("name") or "").strip()
        ]
        if not urls or not profiles:
            self.alert(
                "Almost there",
                "Check at least one active profile with a name, and paste at least one link.",
            )
            return

        self.finish_message = ""
        self.running = True
        self.status_by_profile = {
            str(profile.get("id") or ""): {
                "message": "Starting…",
                "progress": 0,
                "jobs": [
                    {"urlId": item.get("id"), "url": item.get("url"), "state": "queued"}
                    for item in urls
                ],
            }
            for profile in profiles
        }
        self.dashboard.set_running(True)
        self.dashboard.refresh_progress()
        self._remember_statuses()
        try:
            self.bridge.start(urls, profiles, self.state["settings"])
        except Exception as error:
            self.running = False
            self.finish_message = "Start failed"
            for status in self.status_by_profile.values():
                for job in status.get("jobs") or []:
                    job["state"] = "failed"
            self.dashboard.set_running(False)
            self.dashboard.refresh_progress()
            self._remember_statuses()
            self.alert("Could not start", str(error), critical=True)

    def _remember_statuses(self) -> None:
        names = {
            str(profile.get("id") or ""): (profile.get("name") or "").strip() or "Unnamed"
            for profile in self.state.get("profiles") or []
        }
        for profile_id, status in self.status_by_profile.items():
            record_bids(
                self.user_data,
                str(profile_id),
                names.get(str(profile_id), "Unnamed"),
                list(status.get("jobs") or []),
            )
        if hasattr(self, "analytics_page"):
            self.analytics_page.refresh()

    def on_status(self, payload: str) -> None:
        data = json.loads(payload)
        profile_id = data.get("profileId")
        if not profile_id:
            return
        current = self.status_by_profile.get(profile_id, {})
        current.update(data)
        self.status_by_profile[profile_id] = current
        self.dashboard.refresh_progress()
        self._remember_statuses()

    def on_run_state(self, payload: str) -> None:
        data = json.loads(payload)
        self.running = bool(data.get("running"))
        if not self.running:
            self.finish_message = str(data.get("message") or "Finished")
        self.dashboard.set_running(self.running)
        self.dashboard.refresh_progress()
        if data.get("error"):
            self.alert("Run failed", str(data.get("error")), critical=True)

    def closeEvent(self, event) -> None:
        # Persist profiles/settings; URLs are cleared again on next load_state.
        self.persist()
        if self.running:
            self.bridge.stop()
        super().closeEvent(event)
