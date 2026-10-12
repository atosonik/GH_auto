from __future__ import annotations

import uuid
from typing import Any

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.store import active_profiles
from app.ui.widgets import TickCheckBox, clear_layout, polish

_DONE_STATES = {"submitted", "skipped", "failed"}


def _finish_object_name(message: str, running: bool) -> str:
    if running:
        return "stateRun"
    text = (message or "").lower()
    if "fail" in text or "error" in text:
        return "stateBad"
    if "stop" in text:
        return "stateIdle"
    return "stateOk"


class DashboardPage(QWidget):
    """Bulk URL paste, profile checkboxes, Start, and live Profile/URL/Status table."""

    def __init__(self, host: Any):
        super().__init__()
        self.host = host
        self._loading_urls = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        bar = QHBoxLayout()
        bar.setSpacing(10)
        platform_label = QLabel("Platform")
        platform_label.setObjectName("muted")
        self.platform_combo = QComboBox()
        self.platform_combo.setMinimumWidth(160)
        self.platform_combo.addItem("Greenhouse", "greenhouse")
        self.platform_combo.setEnabled(False)
        bar.addWidget(platform_label)
        bar.addWidget(self.platform_combo)
        bar.addSpacing(18)
        self.check_row = QHBoxLayout()
        self.check_row.setSpacing(16)
        bar.addLayout(self.check_row, 1)
        root.addLayout(bar)

        self.url_input = QPlainTextEdit()
        self.url_input.setPlaceholderText("Paste job URLs, one per line")
        self.url_input.setMinimumHeight(220)
        self.url_input.textChanged.connect(self.commit_urls)
        root.addWidget(self.url_input, 1)

        actions = QHBoxLayout()
        actions.setSpacing(12)
        self.start_btn = QPushButton("Start")
        self.start_btn.setObjectName("start")
        self.start_btn.clicked.connect(host.toggle_run)
        self.hint = QLabel("Checked people are included.")
        self.hint.setObjectName("muted")
        self.hint.setWordWrap(True)
        actions.addWidget(self.start_btn)
        actions.addWidget(self.hint, 1)
        root.addLayout(actions)

        self.result_card = QFrame()
        self.result_card.setObjectName("resultCard")
        card = QVBoxLayout(self.result_card)
        card.setContentsMargins(12, 10, 12, 10)
        card.setSpacing(8)
        self.finish_label = QLabel("")
        self.finish_label.setWordWrap(True)
        card.addWidget(self.finish_label)
        self.run_progress = QProgressBar()
        self.run_progress.setRange(0, 100)
        self.run_progress.setValue(0)
        self.run_progress.setTextVisible(False)
        self.run_progress.setFixedHeight(6)
        self.run_progress.setVisible(False)
        card.addWidget(self.run_progress)
        self.table = QTableWidget(0, 3)
        self.table.setObjectName("progressTable")
        self.table.setHorizontalHeaderLabels(["Profile", "URL", "Status"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.NoSelection)
        self.table.setFocusPolicy(Qt.NoFocus)
        self.table.setShowGrid(True)
        self.table.setWordWrap(False)
        self.table.setMinimumHeight(180)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        card.addWidget(self.table, 1)
        self.result_card.setVisible(False)
        root.addWidget(self.result_card, 2)

        self.refresh_lists()
        self.refresh_progress()

    def refresh_lists(self) -> None:
        self._refresh_checks()
        self._load_urls()
        self.update_meta()

    def _load_urls(self) -> None:
        if self.url_input.hasFocus():
            return
        text = "\n".join(
            str(item.get("url") or "")
            for item in self.host.state.get("urls") or []
            if item.get("url")
        )
        if self.url_input.toPlainText() == text:
            return
        self._loading_urls = True
        self.url_input.setPlainText(text)
        self._loading_urls = False

    def commit_urls(self) -> None:
        if self._loading_urls:
            return
        existing = {
            str(item.get("url") or ""): item
            for item in self.host.state.get("urls") or []
            if item.get("url")
        }
        urls: list[dict[str, str]] = []
        seen: set[str] = set()
        for line in self.url_input.toPlainText().splitlines():
            url = line.strip()
            if not url or url in seen:
                continue
            seen.add(url)
            previous = existing.get(url)
            if previous and previous.get("id"):
                urls.append({"id": str(previous["id"]), "url": url})
            else:
                urls.append({"id": str(uuid.uuid4()), "url": url})
        self.host.state["urls"] = urls
        self.update_meta()
        self.host.persist(commit=False)

    def _refresh_checks(self) -> None:
        clear_layout(self.check_row)
        selected = {str(item) for item in self.host.state.get("selectedProfileIds") or []}
        profiles = active_profiles(self.host.state)
        if not profiles:
            note = QLabel("No active profiles. Turn them on under Profiles.")
            note.setObjectName("muted")
            self.check_row.addWidget(note)
        else:
            for profile in profiles:
                self.check_row.addWidget(self._check(profile, selected))
        self.check_row.addStretch(1)

    def _check(self, profile: dict[str, Any], selected: set[str]) -> TickCheckBox:
        profile_id = str(profile.get("id") or "")
        name = (profile.get("name") or "").strip() or "Unnamed"
        box = TickCheckBox(name)
        box.setChecked(profile_id in selected)
        chrome = profile.get("chromeDisplayName") or f"Chrome {profile.get('chromeProfileNumber', 0)}"
        box.setToolTip(str(chrome))
        box.stateChanged.connect(
            lambda state, pid=profile_id: self._set_checked(pid, state == Qt.Checked)
        )
        return box

    def _set_checked(self, profile_id: str, checked: bool) -> None:
        current = [
            item
            for item in self.host.state.get("selectedProfileIds") or []
            if item != profile_id
        ]
        if checked:
            current.append(profile_id)
        self.host.state["selectedProfileIds"] = current
        self.host.persist(commit=False)

    def set_running(self, running: bool, label: str | None = None) -> None:
        if label:
            self.start_btn.setText(label)
        else:
            self.start_btn.setText("Stop" if running else "Start")
        self.start_btn.setProperty("running", "true" if running else "false")
        polish(self.start_btn)
        self.update_meta()

    def refresh_progress(self) -> None:
        statuses: dict[str, dict[str, Any]] = self.host.status_by_profile
        running = bool(self.host.running)
        finish = str(self.host.finish_message or "").strip()
        show = bool(statuses) or bool(finish) or running
        self.result_card.setVisible(show)
        if not show:
            self.table.setRowCount(0)
            self.run_progress.setVisible(False)
            self.update_meta()
            return

        if finish and not running:
            self.finish_label.setText(finish)
            self.finish_label.setObjectName(_finish_object_name(finish, False))
        elif running:
            self.finish_label.setText("Running")
            self.finish_label.setObjectName("stateRun")
        else:
            self.finish_label.setText("Result")
            self.finish_label.setObjectName("sectionTitle")
        polish(self.finish_label)

        names = {
            str(profile.get("id") or ""): (profile.get("name") or "").strip() or "Unnamed"
            for profile in self.host.state.get("profiles") or []
        }
        rows: list[tuple[str, dict[str, Any]]] = []
        for profile_id, status in statuses.items():
            name = names.get(str(profile_id), "Unnamed")
            for job in status.get("jobs") or []:
                rows.append((name, job))
        self.table.setRowCount(len(rows))
        for index, (name, job) in enumerate(rows):
            url = str(job.get("url") or "")
            state = str(job.get("state") or "queued")
            detail = str(job.get("error") or "").strip()
            label = f"{state}: {detail}" if state == "failed" and detail else state
            text_color = self._text_color()
            profile_item = QTableWidgetItem(name)
            profile_item.setForeground(text_color)
            url_item = QTableWidgetItem(url)
            url_item.setToolTip(url)
            url_item.setForeground(text_color)
            status_item = QTableWidgetItem(label)
            status_item.setToolTip(label)
            status_item.setForeground(self._status_color(state))
            self.table.setItem(index, 0, profile_item)
            self.table.setItem(index, 1, url_item)
            self.table.setItem(index, 2, status_item)
        self._paint_bar()
        self.update_meta()

    def _dark(self) -> bool:
        return getattr(self.host, "_resolved_theme", "light") == "dark"

    def _text_color(self) -> QColor:
        return QColor("#f3f4f6" if self._dark() else "#1f2937")

    def _status_color(self, state: str) -> QColor:
        dark = self._dark()
        key = state.lower()
        if key == "submitted" or key.startswith("submitted"):
            return QColor("#4ade80" if dark else "#15803d")
        if key == "failed" or key.startswith("failed"):
            return QColor("#fca5a5" if dark else "#b91c1c")
        if key in {"skipped", "queued", "ready"}:
            return QColor("#d1d5db" if dark else "#6b7280")
        return QColor("#93c5fd" if dark else "#1d4ed8")

    def _counts(self) -> tuple[int, int, int, int]:
        jobs: list[dict[str, Any]] = []
        for status in self.host.status_by_profile.values():
            jobs.extend(status.get("jobs") or [])
        submitted = sum(1 for job in jobs if str(job.get("state") or "") == "submitted")
        failed = sum(1 for job in jobs if str(job.get("state") or "").startswith("failed"))
        skipped = sum(1 for job in jobs if str(job.get("state") or "") == "skipped")
        return submitted, failed, skipped, len(jobs)

    def _paint_bar(self) -> None:
        _submitted, _failed, _skipped, total = self._counts()
        if not total:
            self.run_progress.setVisible(False)
            self.run_progress.setValue(0)
            return
        done = sum(
            1
            for status in self.host.status_by_profile.values()
            for job in (status.get("jobs") or [])
            if str(job.get("state") or "") in _DONE_STATES
        )
        self.run_progress.setVisible(True)
        self.run_progress.setValue(int(round((done / total) * 100)))

    def update_meta(self) -> None:
        submitted, failed, skipped, total = self._counts()
        if self.host.running:
            if total:
                self.hint.setText(f"{submitted} submitted · {failed} failed · {skipped} skipped")
            else:
                self.hint.setText("Starting…")
            return
        if self.host.finish_message and total:
            extra = f" · {skipped} skipped" if skipped else ""
            self.hint.setText(f"{submitted} submitted · {failed} failed{extra}")
            return
        urls = len(self.host.state.get("urls") or [])
        self.hint.setText(
            f"{urls} link{'s' if urls != 1 else ''}. Checked people are included."
        )
