from __future__ import annotations

from typing import Any

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.history import load_bids
from app.ui.widgets import polish

def _bucket(state: str) -> str:
    key = (state or "").lower()
    if key == "submitted" or key.startswith("submitted"):
        return "submitted"
    if key == "failed" or key.startswith("failed"):
        return "failed"
    if key == "skipped" or key.startswith("skipped"):
        return "skipped"
    return "progress"


class AnalyticsPage(QWidget):
    """Bidding history that stays after the Main session is cleared."""

    def __init__(self, host: Any):
        super().__init__()
        self.host = host
        self._bids: list[dict[str, Any]] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        title = QLabel("Analytics")
        title.setObjectName("sectionTitle")
        hint = QLabel("Every bid recorded so far. The Main page still starts empty each time you open the app.")
        hint.setObjectName("sectionHint")
        hint.setWordWrap(True)
        root.addWidget(title)
        root.addWidget(hint)

        filters = QHBoxLayout()
        filters.setSpacing(8)
        self.profile_filter = QComboBox()
        self.profile_filter.setMinimumWidth(160)
        self.status_filter = QComboBox()
        self.status_filter.setMinimumWidth(140)
        for label, value in (
            ("All statuses", "all"),
            ("Submitted", "submitted"),
            ("Failed", "failed"),
            ("In progress", "progress"),
            ("Skipped", "skipped"),
        ):
            self.status_filter.addItem(label, value)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Filter by URL or name")
        self.profile_filter.currentIndexChanged.connect(self._apply)
        self.status_filter.currentIndexChanged.connect(self._apply)
        self.search.textChanged.connect(self._apply)
        filters.addWidget(self.profile_filter)
        filters.addWidget(self.status_filter)
        filters.addWidget(self.search, 1)
        root.addLayout(filters)

        self.summary = QLabel("")
        self.summary.setObjectName("muted")
        root.addWidget(self.summary)

        card = QFrame()
        card.setObjectName("resultCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(12, 10, 12, 10)
        self.table = QTableWidget(0, 4)
        self.table.setObjectName("progressTable")
        self.table.setHorizontalHeaderLabels(["Profile", "URL", "Status", "Updated"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.NoSelection)
        self.table.setFocusPolicy(Qt.NoFocus)
        self.table.setShowGrid(True)
        self.table.setWordWrap(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        card_layout.addWidget(self.table)
        root.addWidget(card, 1)

        self.refresh()

    def refresh(self) -> None:
        self._bids = load_bids(self.host.user_data)
        names = sorted({str(item.get("profileName") or "Unnamed") for item in self._bids})
        current = self.profile_filter.currentData()
        self.profile_filter.blockSignals(True)
        self.profile_filter.clear()
        self.profile_filter.addItem("All profiles", "all")
        for name in names:
            self.profile_filter.addItem(name, name)
        index = self.profile_filter.findData(current)
        self.profile_filter.setCurrentIndex(index if index >= 0 else 0)
        self.profile_filter.blockSignals(False)
        self._apply()

    def _apply(self) -> None:
        profile = self.profile_filter.currentData() or "all"
        status = self.status_filter.currentData() or "all"
        query = self.search.text().strip().lower()
        rows = []
        for bid in self._bids:
            name = str(bid.get("profileName") or "Unnamed")
            url = str(bid.get("url") or "")
            state = str(bid.get("state") or "queued")
            if profile != "all" and name != profile:
                continue
            if status != "all" and _bucket(state) != status:
                continue
            if query and query not in url.lower() and query not in name.lower():
                continue
            rows.append(bid)
        rows.sort(key=lambda item: str(item.get("updatedAt") or ""), reverse=True)
        self._fill(rows)
        self._summarize(rows)

    def _summarize(self, rows: list[dict[str, Any]]) -> None:
        submitted = sum(1 for item in rows if _bucket(str(item.get("state") or "")) == "submitted")
        failed = sum(1 for item in rows if _bucket(str(item.get("state") or "")) == "failed")
        progress = sum(1 for item in rows if _bucket(str(item.get("state") or "")) == "progress")
        skipped = sum(1 for item in rows if _bucket(str(item.get("state") or "")) == "skipped")
        self.summary.setText(
            f"{len(rows)} shown  ·  {submitted} submitted  ·  {failed} failed  ·  "
            f"{progress} in progress  ·  {skipped} skipped"
        )

    def _fill(self, rows: list[dict[str, Any]]) -> None:
        text = self._text_color()
        self.table.setRowCount(len(rows))
        for index, bid in enumerate(rows):
            state = str(bid.get("state") or "queued")
            error = str(bid.get("error") or "").strip()
            label = state
            if _bucket(state) == "failed" and error and error.lower() not in state.lower():
                label = f"failed: {error}"
            url = str(bid.get("url") or "")
            updated = str(bid.get("updatedAt") or "").replace("T", " ")
            values = (
                str(bid.get("profileName") or "Unnamed"),
                url,
                label,
                updated,
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                item.setForeground(self._status_color(state) if column == 2 else text)
                self.table.setItem(index, column, item)
        if not rows:
            polish(self.summary)

    def _dark(self) -> bool:
        return getattr(self.host, "_resolved_theme", "light") == "dark"

    def _text_color(self) -> QColor:
        return QColor("#f3f4f6" if self._dark() else "#1f2937")

    def _status_color(self, state: str) -> QColor:
        dark = self._dark()
        bucket = _bucket(state)
        if bucket == "submitted":
            return QColor("#4ade80" if dark else "#15803d")
        if bucket == "failed":
            return QColor("#fca5a5" if dark else "#b91c1c")
        if bucket == "skipped":
            return QColor("#d1d5db" if dark else "#6b7280")
        return QColor("#93c5fd" if dark else "#1d4ed8")
