from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from PyQt5.QtCore import Qt, QTimer, QUrl
from PyQt5.QtGui import QColor, QDesktopServices, QPainter, QLinearGradient, QBrush
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.automation.chrome import list_chrome_profiles
from app.bridge import Bridge
from app.store import load_state, save_state
from app.theme import (
    background_for,
    normalize_theme,
    resolve_theme,
    stylesheet_for,
)


def short_url(url: str) -> str:
    try:
        parsed = urlparse(url)
        host = parsed.hostname or url
        path = (parsed.path or "").rstrip("/")
        if not path:
            return host
        tail = path.split("/")[-1]
        if len(tail) > 36:
            tail = tail[:34] + "…"
        return f"{host} · {tail}"
    except Exception:
        return url


def empty_profile() -> dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "name": "",
        "chromeProfileNumber": 0,
        "chromeDisplayName": "Default",
        "selected": True,
        "imap": {
            "preset": "outlook",
            "host": "outlook.office365.com",
            "port": 993,
            "user": "",
            "auth": "oauth",
            "password": "",
        },
    }


def progress_pct(jobs: list[dict[str, Any]]) -> int:
    if not jobs:
        return 0
    done = sum(1 for j in jobs if j.get("state") in {"submitted", "skipped", "failed"})
    return int(round((done / len(jobs)) * 100))


def state_object_name(state: str) -> str:
    key = str(state or "").strip().lower()
    if key in {"submitted", "done", "success"}:
        return "stateOk"
    if key in {"failed", "error", "stopped"}:
        return "stateBad"
    if key in {"queued", "ready", "—", "-", ""}:
        return "stateIdle"
    return "stateRun"


def job_header_label(index: int, url: str = "") -> str:
    if url:
        short = short_url(url)
        if len(short) > 42:
            short = short[:40] + "…"
        return f"Job {index}\n{short}"
    return f"Job {index}"


def soft_shadow(
    widget: QWidget,
    blur: int = 28,
    dy: int = 8,
    rgba: tuple[int, int, int, int] = (15, 61, 46, 28),
) -> None:
    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(blur)
    effect.setOffset(0, dy)
    effect.setColor(QColor(*rgba))
    widget.setGraphicsEffect(effect)


class GradientBackground(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._palette = background_for("light")

    def set_palette(self, palette: dict[str, Any]) -> None:
        self._palette = palette
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        grad = QLinearGradient(0, 0, self.width(), self.height())
        for color, stop in self._palette.get("stops", []):
            grad.setColorAt(stop, QColor(color))
        painter.fillRect(self.rect(), QBrush(grad))

        painter.setPen(Qt.NoPen)
        for orb in self._palette.get("orbs", []):
            r, g, b, a = orb["rgba"]
            w, h = orb["size"]
            ox, oy = orb["offset"]
            anchor = orb["anchor"]
            if anchor == "tl":
                x, y = ox, oy
            elif anchor == "br":
                x = self.width() - w - abs(ox)
                y = self.height() - h - abs(oy)
            else:
                x = int(self.width() * 0.35) + ox
                y = oy
            painter.setBrush(QColor(r, g, b, a))
            painter.drawEllipse(x, y, w, h)


class SettingsDialog(QDialog):
    def __init__(self, settings: dict[str, Any], stylesheet: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Paths & tools")
        self.setModal(True)
        self.resize(640, 520)
        self.setStyleSheet(stylesheet)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 18)
        root.setSpacing(14)

        title = QLabel("Paths & tools")
        title.setObjectName("sectionTitle")
        root.addWidget(title)

        hint = QLabel("Theme, browser mode, and project paths. Browser mode controls whether Greenhouse uses private Chrome copies or your live profiles.")
        hint.setObjectName("sectionHint")
        hint.setWordWrap(True)
        root.addWidget(hint)

        theme_row = QHBoxLayout()
        theme_label = QLabel("Theme")
        theme_label.setObjectName("sectionHint")
        self.theme_combo = QComboBox()
        self.theme_combo.addItem("System", "system")
        self.theme_combo.addItem("Light", "light")
        self.theme_combo.addItem("Dark", "dark")
        current = normalize_theme(settings.get("theme"))
        index = max(0, self.theme_combo.findData(current))
        self.theme_combo.setCurrentIndex(index)
        theme_row.addWidget(theme_label)
        theme_row.addWidget(self.theme_combo, 1)
        root.addLayout(theme_row)

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
        root.addLayout(browser_row)

        form = QFormLayout()
        form.setSpacing(12)
        form.setLabelAlignment(Qt.AlignLeft)
        self.inputs: dict[str, QLineEdit] = {}
        fields = [
            ("chromeUserDataDir", "Chrome User Data"),
            ("promptsDir", "Prompts folder"),
            ("profileContextDir", "Profile context folder"),
            ("profilesJsonPath", "profiles.json"),
            ("mainPyPath", "Resume main.py"),
            ("resumeOutputDir", "Resume output"),
            ("pythonPath", "Python for main.py"),
        ]
        for key, label in fields:
            edit = QLineEdit(str(settings.get(key, "")))
            self.inputs[key] = edit
            form.addRow(label, edit)
        root.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def values(self) -> dict[str, Any]:
        data: dict[str, Any] = {key: edit.text().strip() for key, edit in self.inputs.items()}
        data["theme"] = normalize_theme(self.theme_combo.currentData())
        data["browserMode"] = self.browser_combo.currentData() or "isolated"
        return data


class MainWindow(QMainWindow):
    def __init__(self, user_data: Path):
        super().__init__()
        self.user_data = user_data
        self.user_data.mkdir(parents=True, exist_ok=True)
        self.bridge = Bridge(user_data)
        self.state = load_state(user_data)
        self.status_by_profile: dict[str, dict[str, Any]] = {}
        self.running = False
        self._resolved_theme = resolve_theme(self.state["settings"].get("theme"))
        self._shadow_widgets: list[tuple[QWidget, int, int]] = []

        self.setWindowTitle("Greenhouse")
        self.resize(1240, 820)
        self.setMinimumSize(1040, 700)

        shell = GradientBackground()
        self.shell = shell
        self.setCentralWidget(shell)
        root = QVBoxLayout(shell)
        root.setContentsMargins(28, 24, 28, 20)
        root.setSpacing(18)

        # Brand hero
        hero = QVBoxLayout()
        hero.setSpacing(4)
        brand = QLabel("Greenhouse")
        brand.setObjectName("brand")
        tagline = QLabel("Apply selected jobs across Chrome profiles — DeepSeek writes, you launch.")
        tagline.setObjectName("tagline")
        hero.addWidget(brand)
        hero.addWidget(tagline)
        root.addLayout(hero)

        # Main workspace
        workspace = QHBoxLayout()
        workspace.setSpacing(16)
        root.addLayout(workspace, 5)

        self.jobs_panel = self._section(
            "Jobs",
            "Pick the Greenhouse links to apply. Only checked ones run.",
        )
        self.profiles_panel = self._section(
            "People",
            "Name must match prompts/profiles.json. Number is the Chrome profile index.",
        )
        workspace.addWidget(self.jobs_panel, 3)
        workspace.addWidget(self.profiles_panel, 2)

        job_tools = QHBoxLayout()
        job_tools.setSpacing(8)
        select_all_jobs = QPushButton("Select all")
        select_all_jobs.setObjectName("ghost")
        select_all_jobs.setToolTip("Check every job link")
        select_all_jobs.clicked.connect(self.select_all_urls)
        clear_jobs = QPushButton("Clear")
        clear_jobs.setObjectName("ghost")
        clear_jobs.setToolTip("Uncheck every job link")
        clear_jobs.clicked.connect(self.clear_url_selection)
        remove_checked = QPushButton("Remove checked")
        remove_checked.setObjectName("ghost")
        remove_checked.setToolTip("Delete checked job links from the list")
        remove_checked.clicked.connect(self.remove_selected_urls)
        job_tools.addWidget(select_all_jobs)
        job_tools.addWidget(clear_jobs)
        job_tools.addWidget(remove_checked)
        job_tools.addStretch(1)
        self.jobs_panel.layout().addLayout(job_tools)

        self.url_list = QVBoxLayout()
        self.profile_list = QVBoxLayout()
        self.jobs_panel.layout().addWidget(self._scroll(self.url_list), 1)
        self.profiles_panel.layout().addWidget(self._scroll(self.profile_list), 1)

        # Job composer
        compose = QHBoxLayout()
        compose.setSpacing(8)
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Paste a Greenhouse job URL")
        self.url_input.returnPressed.connect(self.add_url)
        add_url_btn = QPushButton("Add job")
        add_url_btn.setObjectName("primary")
        add_url_btn.clicked.connect(self.add_url)
        compose.addWidget(self.url_input, 1)
        compose.addWidget(add_url_btn)
        self.jobs_panel.layout().addLayout(compose)

        add_profile_btn = QPushButton("Add person")
        add_profile_btn.setObjectName("ghost")
        add_profile_btn.clicked.connect(self.add_profile)
        self.profiles_panel.layout().addWidget(add_profile_btn)

        # Analytics board: profiles × jobs
        status_panel = self._section(
            "Run analytics",
            "Each column is a job URL. Color shows status — green submitted, blue in progress, red failed. Scroll sideways if many jobs.",
        )
        root.addWidget(status_panel, 3)
        self.status_table = QTableWidget(0, 1)
        self.status_table.setObjectName("analyticsTable")
        self.status_table.setHorizontalHeaderLabels(["Person"])
        self.status_table.verticalHeader().setVisible(False)
        self.status_table.setSelectionMode(QTableWidget.NoSelection)
        self.status_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.status_table.setFocusPolicy(Qt.NoFocus)
        self.status_table.setShowGrid(True)
        self.status_table.setWordWrap(True)
        self.status_table.setAlternatingRowColors(True)
        self.status_table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.status_table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.status_table.horizontalHeader().setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.status_table.horizontalHeader().setMinimumSectionSize(168)
        self.status_table.horizontalHeader().setMinimumHeight(46)
        self.status_table.horizontalHeader().setDefaultSectionSize(200)
        self.status_table.horizontalHeader().setStretchLastSection(False)
        self.status_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeToContents
        )
        self.status_table.setMinimumHeight(280)
        self.status_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        status_panel.layout().addWidget(self.status_table)

        # Action dock
        dock = QFrame()
        dock.setObjectName("dock")
        self._track_shadow(dock, 36, 10)
        dock_layout = QHBoxLayout(dock)
        dock_layout.setContentsMargins(22, 16, 16, 16)
        dock_layout.setSpacing(16)

        meta_col = QVBoxLayout()
        meta_col.setSpacing(4)
        self.meta = QLabel("Nothing selected")
        self.meta.setObjectName("meta")
        self.meta_sub = QLabel("Check at least one job and one person, then Start.")
        self.meta_sub.setObjectName("metaSub")
        self.meta_sub.setWordWrap(True)
        self.run_progress = QProgressBar()
        self.run_progress.setRange(0, 100)
        self.run_progress.setValue(0)
        self.run_progress.setTextVisible(False)
        self.run_progress.setFixedHeight(10)
        self.run_progress.setVisible(False)
        meta_col.addWidget(self.meta)
        meta_col.addWidget(self.meta_sub)
        meta_col.addWidget(self.run_progress)
        dock_layout.addLayout(meta_col, 1)

        self.theme_combo = QComboBox()
        self.theme_combo.setObjectName("themePick")
        self.theme_combo.setToolTip("Appearance")
        self.theme_combo.addItem("System", "system")
        self.theme_combo.addItem("Light", "light")
        self.theme_combo.addItem("Dark", "dark")
        theme_choice = normalize_theme(self.state["settings"].get("theme"))
        self.theme_combo.setCurrentIndex(max(0, self.theme_combo.findData(theme_choice)))
        self.theme_combo.currentIndexChanged.connect(self.on_theme_changed)
        dock_layout.addWidget(self.theme_combo)

        settings_btn = QPushButton("Paths")
        settings_btn.setObjectName("dockGhost")
        settings_btn.clicked.connect(self.open_settings)
        dock_layout.addWidget(settings_btn)

        self.start_btn = QPushButton("Start apply")
        self.start_btn.setObjectName("start")
        self.start_btn.clicked.connect(self.toggle_run)
        dock_layout.addWidget(self.start_btn)
        root.addWidget(dock)

        self.bridge.statusChanged.connect(self.on_status)
        self.bridge.runStateChanged.connect(self.on_run_state)

        self.theme_timer = QTimer(self)
        self.theme_timer.setInterval(2500)
        self.theme_timer.timeout.connect(self._sync_system_theme)
        self.theme_timer.start()

        self.apply_theme(force=True)
        self.reload_lists()
        self.refresh_status_cards()
        self.update_meta()

    def _track_shadow(self, widget: QWidget, blur: int, dy: int) -> None:
        self._shadow_widgets.append((widget, blur, dy))

    def _section(self, title: str, hint: str) -> QFrame:
        frame = QFrame()
        frame.setObjectName("panel")
        self._track_shadow(frame, 24, 6)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)
        heading = QLabel(title)
        heading.setObjectName("sectionTitle")
        sub = QLabel(hint)
        sub.setObjectName("sectionHint")
        sub.setWordWrap(True)
        layout.addWidget(heading)
        layout.addWidget(sub)
        return frame

    def _scroll(self, inner_layout: QVBoxLayout) -> QScrollArea:
        host = QWidget()
        host.setObjectName("listHost")
        host.setAutoFillBackground(False)
        host.setAttribute(Qt.WA_StyledBackground, True)
        host.setStyleSheet("background: transparent;")
        host.setLayout(inner_layout)
        inner_layout.setContentsMargins(0, 0, 0, 0)
        inner_layout.setSpacing(8)
        scroll = QScrollArea()
        scroll.setObjectName("listScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setAutoFillBackground(False)
        scroll.setAttribute(Qt.WA_StyledBackground, True)
        scroll.setStyleSheet("QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; }")
        if scroll.viewport():
            scroll.viewport().setObjectName("listViewport")
            scroll.viewport().setAutoFillBackground(False)
            scroll.viewport().setAttribute(Qt.WA_StyledBackground, True)
            scroll.viewport().setStyleSheet("background: transparent;")
        scroll.setWidget(host)
        return scroll

    def _empty_state(self, title: str, body: str) -> QFrame:
        box = QFrame()
        box.setObjectName("row")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(16, 18, 16, 18)
        t = QLabel(title)
        t.setObjectName("emptyTitle")
        b = QLabel(body)
        b.setObjectName("muted")
        b.setWordWrap(True)
        layout.addWidget(t)
        layout.addWidget(b)
        return box

    def persist(self) -> None:
        save_state(self.user_data, self.state)

    def reload_lists(self) -> None:
        self._clear_layout(self.url_list)
        self._clear_layout(self.profile_list)

        if not self.state["urls"]:
            self.url_list.addWidget(
                self._empty_state(
                    "No jobs yet",
                    "Paste a Greenhouse application URL below. You can stack several and only run the ones you check.",
                )
            )
        else:
            for url_item in self.state["urls"]:
                self.url_list.addWidget(self._url_row(url_item))

        if not self.state["profiles"]:
            self.profile_list.addWidget(
                self._empty_state(
                    "No people yet",
                    "Add someone like “Robert Yuan”, set their Chrome profile number, and optional IMAP for security codes.",
                )
            )
        else:
            for profile in self.state["profiles"]:
                self.profile_list.addWidget(self._profile_row(profile))

        self.url_list.addStretch(1)
        self.profile_list.addStretch(1)

    def _clear_layout(self, layout: QVBoxLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def _url_row(self, url_item: dict[str, Any]) -> QFrame:
        row = QFrame()
        row.setObjectName("row")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(12, 10, 10, 10)
        layout.setSpacing(10)

        check = QCheckBox()
        check.setChecked(bool(url_item.get("selected", True)))
        check.setToolTip(url_item.get("url") or "")
        check.stateChanged.connect(
            lambda state, item=url_item: self._set_url_selected(item, state == Qt.Checked)
        )
        layout.addWidget(check)

        label = QLabel(url_item.get("url") or "")
        label.setToolTip(url_item.get("url") or "")
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(label, 1)

        remove = QPushButton("×")
        remove.setObjectName("danger")
        remove.setToolTip("Remove job")
        remove.clicked.connect(lambda _=False, item=url_item: self.remove_url(item))
        layout.addWidget(remove)
        return row

    def _profile_row(self, profile: dict[str, Any]) -> QFrame:
        row = QFrame()
        row.setObjectName("row")
        layout = QVBoxLayout(row)
        layout.setContentsMargins(12, 10, 10, 10)
        layout.setSpacing(8)

        top = QHBoxLayout()
        top.setSpacing(8)
        check = QCheckBox()
        check.setChecked(bool(profile.get("selected", True)))
        check.stateChanged.connect(
            lambda state, item=profile: self._set_profile_selected(item, state == Qt.Checked)
        )
        top.addWidget(check)

        name = QLineEdit(profile.get("name") or "")
        name.setPlaceholderText("Full name (exact prompt match)")
        name.textChanged.connect(lambda text, item=profile: self._set_profile_name(item, text))
        top.addWidget(name, 3)

        number = QSpinBox()
        number.setRange(0, 200)
        number.setPrefix("Chrome ")
        number.setValue(int(profile.get("chromeProfileNumber") or 0))
        number.setToolTip("Chrome profile index (Profile 12 → 12, Default → 0)")
        number.setMinimumWidth(110)
        number.valueChanged.connect(
            lambda value, item=profile: self._set_profile_number(item, value)
        )
        top.addWidget(number)

        remove = QPushButton("×")
        remove.setObjectName("danger")
        remove.setToolTip("Remove person")
        remove.clicked.connect(lambda _=False, item=profile: self.remove_profile(item))
        top.addWidget(remove)
        layout.addLayout(top)
        return row

    def _open_resume_folder(self, folder: str) -> None:
        path = Path(folder)
        if not path.exists():
            self._alert("Folder missing", f"Resume folder not found:\n{folder}")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve())))

    def _job_cell_widget(self, job: dict[str, Any] | None, fallback: str = "—") -> QWidget:
        card = QFrame()
        card.setObjectName("statusCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(5)

        if not job:
            label = QLabel(fallback)
            label.setObjectName("muted")
            layout.addWidget(label)
            return card

        url = str(job.get("url") or "").strip()
        if url:
            url_label = QLabel(short_url(url))
            url_label.setObjectName("jobUrl")
            url_label.setWordWrap(True)
            url_label.setToolTip(url)
            layout.addWidget(url_label)

        state = str(job.get("state") or "queued")
        state_label = QLabel(state)
        state_label.setObjectName(state_object_name(state))
        state_label.setWordWrap(True)
        state_label.setToolTip(state)
        layout.addWidget(state_label)

        folder = str(job.get("resumeFolder") or "").strip()
        if not folder and job.get("pdfPath"):
            try:
                folder = str(Path(job["pdfPath"]).parent)
            except Exception:
                folder = ""
        if folder:
            link = QLabel(f'<a href="folder">{Path(folder).name}</a>')
            link.setObjectName("jobLine")
            link.setTextFormat(Qt.RichText)
            link.setTextInteractionFlags(Qt.TextBrowserInteraction)
            link.setOpenExternalLinks(False)
            link.setWordWrap(True)
            link.setToolTip(folder)
            link.linkActivated.connect(lambda _href, f=folder: self._open_resume_folder(f))
            layout.addWidget(link)
            open_btn = QPushButton("Open folder")
            open_btn.setObjectName("ghost")
            open_btn.setToolTip(folder)
            open_btn.clicked.connect(lambda _=False, f=folder: self._open_resume_folder(f))
            layout.addWidget(open_btn)
        elif job.get("error"):
            err_text = str(job.get("error") or "").strip()
            err = QLabel(err_text[:220] + ("…" if len(err_text) > 220 else ""))
            err.setObjectName("muted")
            err.setWordWrap(True)
            err.setToolTip(err_text)
            layout.addWidget(err)

        layout.addStretch(1)
        return card

    def _job_headers(self, selected_urls: list[dict[str, Any]], job_count: int, live_jobs: list[dict[str, Any]] | None = None) -> list[str]:
        headers = ["Person"]
        for i in range(1, job_count + 1):
            url = ""
            if live_jobs and i - 1 < len(live_jobs):
                url = str(live_jobs[i - 1].get("url") or "")
            if not url and i - 1 < len(selected_urls):
                url = str(selected_urls[i - 1].get("url") or "")
            headers.append(job_header_label(i, url))
        return headers

    def refresh_status_cards(self) -> None:
        selected_profiles = [p for p in self.state["profiles"] if p.get("selected")]
        selected_urls = [u for u in self.state["urls"] if u.get("selected")]
        job_count = max(len(selected_urls), 1)

        # Prefer live run job list length when a run is active.
        sample_jobs: list[dict[str, Any]] = []
        for status in self.status_by_profile.values():
            jobs = status.get("jobs") or []
            if len(jobs) > job_count:
                job_count = len(jobs)
            if not sample_jobs and jobs:
                sample_jobs = list(jobs)

        headers = self._job_headers(selected_urls, job_count, sample_jobs)
        self.status_table.clear()
        self.status_table.setColumnCount(len(headers))
        self.status_table.setHorizontalHeaderLabels(headers)
        self.status_table.setRowCount(len(selected_profiles))

        # Full URL on header hover.
        for col in range(1, len(headers)):
            item = self.status_table.horizontalHeaderItem(col)
            if not item:
                continue
            tip = ""
            if sample_jobs and col - 1 < len(sample_jobs):
                tip = str(sample_jobs[col - 1].get("url") or "")
            if not tip and col - 1 < len(selected_urls):
                tip = str(selected_urls[col - 1].get("url") or "")
            if tip:
                item.setToolTip(tip)

        if not selected_profiles:
            self.status_table.setRowCount(1)
            self.status_table.setItem(0, 0, QTableWidgetItem("Select people to track"))
            for col in range(1, len(headers)):
                self.status_table.setItem(0, col, QTableWidgetItem("—"))
            self._apply_table_column_widths(job_count)
            return

        for row, profile in enumerate(selected_profiles):
            person = QTableWidgetItem(profile.get("name") or "Unnamed")
            person.setToolTip(f"Chrome profile {profile.get('chromeProfileNumber', 0)}")
            self.status_table.setItem(row, 0, person)

            status = self.status_by_profile.get(profile.get("id") or "", {})
            jobs = list(status.get("jobs") or [])
            # Seed queued placeholders from selected URLs before/during start.
            if not jobs and selected_urls:
                jobs = [
                    {"urlId": u.get("id"), "url": u.get("url"), "state": "ready"}
                    for u in selected_urls
                ]

            for col in range(1, job_count + 1):
                job = jobs[col - 1] if col - 1 < len(jobs) else None
                self.status_table.setCellWidget(row, col, self._job_cell_widget(job))
                # Keep a readable minimum row height so state text isn't crushed.
                self.status_table.setRowHeight(row, max(self.status_table.rowHeight(row), 96))

            # If there is an overall profile message and no per-job detail yet.
            if status.get("message") and jobs:
                first = jobs[0]
                if first.get("state") in {"queued", "ready", None, ""}:
                    first = {**first, "state": status.get("message")}
                    self.status_table.setCellWidget(row, 1, self._job_cell_widget(first))

        self.status_table.resizeRowsToContents()
        for row in range(self.status_table.rowCount()):
            self.status_table.setRowHeight(row, max(self.status_table.rowHeight(row), 104))
        self._apply_table_column_widths(job_count)
        self._refresh_run_summary()

    def _apply_table_column_widths(self, job_count: int) -> None:
        header = self.status_table.horizontalHeader()
        header.setMinimumSectionSize(168)
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        # Few jobs: stretch so cells stay wide. Many jobs: fixed min width + horizontal scroll.
        mode = QHeaderView.Stretch if job_count <= 3 else QHeaderView.Interactive
        for col in range(1, self.status_table.columnCount()):
            header.setSectionResizeMode(col, mode)
            if mode == QHeaderView.Interactive:
                self.status_table.setColumnWidth(col, max(188, self.status_table.columnWidth(col)))
        self.status_table.setMinimumHeight(max(280, min(420, 110 * max(1, self.status_table.rowCount()))))

    def _refresh_run_summary(self) -> None:
        if not self.status_by_profile:
            self.run_progress.setVisible(False)
            return
        all_jobs: list[dict[str, Any]] = []
        for status in self.status_by_profile.values():
            all_jobs.extend(status.get("jobs") or [])
        if not all_jobs:
            self.run_progress.setVisible(False)
            return
        submitted = sum(1 for j in all_jobs if str(j.get("state") or "") == "submitted")
        failed = sum(1 for j in all_jobs if str(j.get("state") or "") == "failed")
        skipped = sum(1 for j in all_jobs if str(j.get("state") or "") == "skipped")
        pct = progress_pct(all_jobs)
        self.run_progress.setVisible(True)
        self.run_progress.setValue(pct)
        if self.running:
            self.meta_sub.setText(
                f"Live: {submitted} submitted · {failed} failed · {skipped} skipped · {pct}%"
            )
        elif submitted or failed or skipped:
            self.meta.setText(
                f"{submitted} submitted · {failed} failed"
                + (f" · {skipped} skipped" if skipped else "")
            )
            self.meta_sub.setText("Open a green cell’s folder link to review the resume PDF.")

    def update_meta(self) -> None:
        if self.running or any(
            str(j.get("state") or "") in {"submitted", "failed", "skipped"}
            for status in self.status_by_profile.values()
            for j in (status.get("jobs") or [])
        ):
            self._refresh_run_summary()
            if self.running:
                profiles = sum(1 for p in self.state["profiles"] if p.get("selected"))
                jobs = sum(1 for u in self.state["urls"] if u.get("selected"))
                self.meta.setText(
                    f"{jobs} job{'s' if jobs != 1 else ''}  ·  {profiles} person{'s' if profiles != 1 else ''}"
                )
            return
        profiles = sum(1 for p in self.state["profiles"] if p.get("selected"))
        jobs = sum(1 for u in self.state["urls"] if u.get("selected"))
        self.run_progress.setVisible(False)
        if profiles == 0 and jobs == 0:
            self.meta.setText("Nothing selected")
            self.meta_sub.setText("Check at least one job and one person, then Start.")
        else:
            self.meta.setText(f"{jobs} job{'s' if jobs != 1 else ''}  ·  {profiles} person{'s' if profiles != 1 else ''}")
            self.meta_sub.setText("Start opens one tiled Chrome window per person.")

    def add_url(self) -> None:
        url = self.url_input.text().strip()
        if not url:
            return
        self.state["urls"].append({"id": str(uuid.uuid4()), "url": url, "selected": True})
        self.url_input.clear()
        self.persist()
        self.reload_lists()
        self.update_meta()

    def remove_url(self, item: dict[str, Any]) -> None:
        self.state["urls"] = [u for u in self.state["urls"] if u.get("id") != item.get("id")]
        self.persist()
        self.reload_lists()
        self.refresh_status_cards()
        self.update_meta()

    def select_all_urls(self) -> None:
        for url_item in self.state["urls"]:
            url_item["selected"] = True
        self.persist()
        self.reload_lists()
        self.refresh_status_cards()
        self.update_meta()

    def clear_url_selection(self) -> None:
        for url_item in self.state["urls"]:
            url_item["selected"] = False
        self.persist()
        self.reload_lists()
        self.refresh_status_cards()
        self.update_meta()

    def remove_selected_urls(self) -> None:
        kept = [u for u in self.state["urls"] if not u.get("selected")]
        if len(kept) == len(self.state["urls"]):
            return
        self.state["urls"] = kept
        self.persist()
        self.reload_lists()
        self.refresh_status_cards()
        self.update_meta()

    def add_profile(self) -> None:
        profile = empty_profile()
        chrome_profiles = list_chrome_profiles(self.state["settings"].get("chromeUserDataDir"))
        if chrome_profiles:
            first = chrome_profiles[0]
            profile["chromeProfileNumber"] = first.get("number", 0)
            profile["chromeDisplayName"] = first.get("displayName") or "Default"
        self.state["profiles"].append(profile)
        self.persist()
        self.reload_lists()
        self.refresh_status_cards()
        self.update_meta()

    def remove_profile(self, item: dict[str, Any]) -> None:
        self.state["profiles"] = [p for p in self.state["profiles"] if p.get("id") != item.get("id")]
        self.status_by_profile.pop(item.get("id") or "", None)
        self.persist()
        self.reload_lists()
        self.refresh_status_cards()
        self.update_meta()

    def _set_url_selected(self, item: dict[str, Any], selected: bool) -> None:
        item["selected"] = selected
        self.persist()
        self.refresh_status_cards()
        self.update_meta()

    def _set_profile_selected(self, item: dict[str, Any], selected: bool) -> None:
        item["selected"] = selected
        self.persist()
        self.refresh_status_cards()
        self.update_meta()

    def _set_profile_name(self, item: dict[str, Any], text: str) -> None:
        item["name"] = text.strip()
        self.persist()
        self.refresh_status_cards()

    def _set_profile_number(self, item: dict[str, Any], value: int) -> None:
        item["chromeProfileNumber"] = int(value)
        item["chromeDisplayName"] = f"Profile {value}" if value else "Default"
        self.persist()
        self.refresh_status_cards()

    def _set_imap_preset(self, item: dict[str, Any], preset: str) -> None:
        imap = item.setdefault("imap", {})
        imap["preset"] = preset
        if preset == "gmail":
            imap["host"] = "imap.gmail.com"
            imap["port"] = 993
        else:
            imap["host"] = "outlook.office365.com"
            imap["port"] = 993
        self.persist()

    def _set_imap_field(self, item: dict[str, Any], field: str, value: str) -> None:
        imap = item.setdefault("imap", {})
        imap[field] = value
        self.persist()

    def apply_theme(self, force: bool = False) -> None:
        choice = normalize_theme(self.state["settings"].get("theme"))
        resolved = resolve_theme(choice)
        if not force and resolved == self._resolved_theme:
            return
        self._resolved_theme = resolved
        sheet = stylesheet_for(resolved)
        self.setStyleSheet(sheet)
        self.shell.set_palette(background_for(resolved))
        shadow = tuple(background_for(resolved)["shadow"])
        for widget, blur, dy in self._shadow_widgets:
            soft_shadow(widget, blur=blur, dy=dy, rgba=shadow)
        # Keep start button running state visually correct after stylesheet reset
        if hasattr(self, "start_btn"):
            self.start_btn.setProperty("running", "true" if self.running else "false")
            self.start_btn.style().unpolish(self.start_btn)
            self.start_btn.style().polish(self.start_btn)

    def on_theme_changed(self, _index: int = 0) -> None:
        choice = normalize_theme(self.theme_combo.currentData())
        self.state["settings"]["theme"] = choice
        self.persist()
        self.apply_theme(force=True)

    def _sync_system_theme(self) -> None:
        if normalize_theme(self.state["settings"].get("theme")) != "system":
            return
        self.apply_theme(force=False)

    def open_settings(self) -> None:
        dialog = SettingsDialog(
            self.state["settings"],
            stylesheet_for(self._resolved_theme),
            self,
        )
        if dialog.exec_() == QDialog.Accepted:
            values = dialog.values()
            self.state["settings"].update(values)
            self.persist()
            # Keep dock theme picker in sync
            theme = normalize_theme(values.get("theme"))
            blocked = self.theme_combo.blockSignals(True)
            self.theme_combo.setCurrentIndex(max(0, self.theme_combo.findData(theme)))
            self.theme_combo.blockSignals(blocked)
            self.apply_theme(force=True)

    def _set_running_ui(self, running: bool) -> None:
        self.running = running
        self.start_btn.setText("Stop run" if running else "Start apply")
        self.start_btn.setProperty("running", "true" if running else "false")
        self.start_btn.style().unpolish(self.start_btn)
        self.start_btn.style().polish(self.start_btn)

    def toggle_run(self) -> None:
        if self.running:
            self.bridge.stop()
            self.start_btn.setText("Stopping…")
            return

        self.persist()
        urls = [u for u in self.state["urls"] if u.get("selected") and u.get("url")]
        profiles = [p for p in self.state["profiles"] if p.get("selected") and p.get("name")]
        if not urls or not profiles:
            self._alert("Almost there", "Select at least one job and one person with a name before starting.")
            return

        try:
            self.bridge.start(urls, profiles, self.state["settings"])
        except Exception as error:
            self._alert("Could not start", str(error), critical=True)
            return

        self._set_running_ui(True)
        for profile in profiles:
            self.status_by_profile[profile["id"]] = {
                "message": "Starting…",
                "progress": 0,
                "jobs": [
                    {"urlId": u["id"], "url": u["url"], "state": "queued"} for u in urls
                ],
            }
        self.refresh_status_cards()

    def on_status(self, payload: str) -> None:
        data = json.loads(payload)
        profile_id = data.get("profileId")
        if not profile_id:
            return
        current = self.status_by_profile.get(profile_id, {})
        current.update(data)
        self.status_by_profile[profile_id] = current
        self.refresh_status_cards()
        self.update_meta()

    def on_run_state(self, payload: str) -> None:
        data = json.loads(payload)
        self._set_running_ui(bool(data.get("running")))
        self.update_meta()
        if data.get("error"):
            self._alert("Run failed", data["error"], critical=True)

    def _alert(self, title: str, text: str, *, critical: bool = False) -> None:
        box = QMessageBox(self)
        box.setWindowTitle(title)
        box.setText(text)
        box.setIcon(QMessageBox.Critical if critical else QMessageBox.Warning)
        box.setStyleSheet(stylesheet_for(self._resolved_theme))
        box.exec_()

    def closeEvent(self, event) -> None:
        self.persist()
        if self.running:
            self.bridge.stop()
        super().closeEvent(event)
