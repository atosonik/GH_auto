from __future__ import annotations

from typing import Any

from PyQt5.QtCore import QThread, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PyQt5.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from app.automation.chrome import list_chrome_profiles
from app.automation.outlook_oauth import acquire_access_token, token_status
from app.store import new_profile
from app.ui.widgets import clear_layout, empty_state, polish, scroll_area, section


class MailConnectWorker(QThread):
    ok = pyqtSignal(str)
    failed = pyqtSignal(str, str)

    def __init__(self, profile_id: str, email: str, parent=None):
        super().__init__(parent)
        self.profile_id = profile_id
        self.email = email

    def run(self) -> None:
        try:
            acquire_access_token(self.email, interactive=True)
        except Exception as error:
            self.failed.emit(self.profile_id, str(error))
            return
        self.ok.emit(self.profile_id)


class ProfileDialog(QDialog):
    """Edit one profile. Connect mailbox uses the address typed here."""

    def __init__(self, host: Any, profile: dict[str, Any], chrome_profiles: list[dict[str, Any]], parent=None):
        super().__init__(parent)
        self.host = host
        self.profile = profile
        self.chrome_profiles = chrome_profiles
        self.setWindowTitle("Update profile" if (profile.get("name") or "").strip() else "Add profile")
        self.setMinimumWidth(460)
        window = parent.window() if parent is not None else None
        if window is not None:
            self.setStyleSheet(window.styleSheet())

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(12)

        form = QFormLayout()
        form.setSpacing(10)
        self.name_edit = QLineEdit(profile.get("name") or "")
        self.name_edit.setPlaceholderText("Full name (must match the prompt)")
        form.addRow("Name", self.name_edit)

        self.chrome_box = QComboBox()
        self._fill_chrome()
        form.addRow("Chrome profile", self.chrome_box)

        self.email_edit = QLineEdit((profile.get("imap") or {}).get("user") or "")
        self.email_edit.setPlaceholderText("name@outlook.com")
        form.addRow("Outlook", self.email_edit)
        root.addLayout(form)

        mail = QHBoxLayout()
        self.connect_btn = QPushButton("Connect mailbox")
        self.connect_btn.setObjectName("ghost")
        self.mail_status = QLabel()
        self._paint_mail(self.email_edit.text())
        self.connect_btn.clicked.connect(self._connect)
        self.email_edit.textChanged.connect(lambda text: self._paint_mail(text))
        mail.addWidget(self.connect_btn)
        mail.addWidget(self.mail_status, 1)
        root.addLayout(mail)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        save_btn = buttons.button(QDialogButtonBox.Save)
        if save_btn is not None:
            save_btn.setObjectName("primary")
        root.addWidget(buttons)

    def _fill_chrome(self) -> None:
        self.chrome_box.clear()
        number = int(self.profile.get("chromeProfileNumber") or 0)
        found = False
        for meta in self.chrome_profiles:
            self.chrome_box.addItem(_chrome_label(meta), int(meta.get("number") or 0))
            if int(meta.get("number") or 0) == number:
                found = True
        if not found:
            label = self.profile.get("chromeDisplayName") or f"Profile {number}"
            self.chrome_box.insertItem(0, f"{label} · saved", number)
        self.chrome_box.setCurrentIndex(max(0, self.chrome_box.findData(number)))

    def _paint_mail(self, email: str) -> None:
        address = (email or "").strip()
        self.connect_btn.setEnabled(bool(address))
        if not address:
            self.mail_status.setText("Add an Outlook address")
            self.mail_status.setObjectName("muted")
        elif token_status(address).get("cached"):
            self.mail_status.setText("Connected")
            self.mail_status.setObjectName("stateOk")
        else:
            self.mail_status.setText("Not connected")
            self.mail_status.setObjectName("stateIdle")
        polish(self.mail_status)

    def _connect(self) -> None:
        email = self.email_edit.text().strip()
        if not email:
            return
        page = self.parent()
        if not isinstance(page, ProfilesPage):
            return
        page.connect_mailbox(self.profile, email, on_done=self._paint_mail)

    def _save(self) -> None:
        number = self.chrome_box.currentData()
        if number is None:
            QMessageBox.warning(self, "Chrome profile", "Select a Chrome profile.")
            return
        name = self.name_edit.text().strip()
        label = self.chrome_box.currentText()
        match = next(
            (item for item in self.chrome_profiles if int(item.get("number") or 0) == int(number)),
            None,
        )
        self.profile["name"] = name
        self.profile["chromeProfileNumber"] = int(number)
        if match:
            self.profile["chromeDisplayName"] = match.get("displayName") or label
        else:
            self.profile["chromeDisplayName"] = "Default" if int(number) == 0 else f"Profile {number}"
        imap = self.profile.setdefault("imap", {})
        imap["user"] = self.email_edit.text().strip()
        imap["preset"] = "outlook"
        imap["host"] = "outlook.office365.com"
        imap["port"] = 993
        imap["auth"] = "oauth"
        self.accept()


class ProfilesPage(QWidget):
    def __init__(self, host: Any):
        super().__init__()
        self.host = host
        self._workers: dict[str, MailConnectWorker] = {}
        self._mail_callbacks: dict[str, Any] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        self.panel = section(
            host,
            "Profiles",
            "Shared by every job board. Active profiles show up on the dashboard. The name must match the prompt file.",
        )
        root.addWidget(self.panel, 1)

        self.list_layout = QVBoxLayout()
        self.panel.layout().addWidget(scroll_area(self.list_layout), 1)

        add_btn = QPushButton("Add profile")
        add_btn.setObjectName("primary")
        add_btn.clicked.connect(self.add_profile)
        self.panel.layout().addWidget(add_btn)

        self.refresh()

    def refresh(self) -> None:
        clear_layout(self.list_layout)
        profiles = self.host.state.get("profiles") or []
        if not profiles:
            self.list_layout.addWidget(
                empty_state(
                    "No profiles yet",
                    "Add a person, then use update to set their name, Chrome profile, and Outlook address.",
                )
            )
        else:
            for profile in profiles:
                self.list_layout.addWidget(self._row(profile))
        self.list_layout.addStretch(1)

    def add_profile(self) -> None:
        profile = new_profile()
        chrome_profiles = self._chrome_profiles()
        if chrome_profiles:
            first = chrome_profiles[0]
            profile["chromeProfileNumber"] = int(first.get("number") or 0)
            profile["chromeDisplayName"] = first.get("displayName") or "Default"
        dialog = ProfileDialog(self.host, profile, chrome_profiles, self)
        dialog.setWindowTitle("Add profile")
        if dialog.exec_() != QDialog.Accepted:
            return
        self.host.state["profiles"].append(profile)
        self._sync_active(profile)
        self.host.persist()
        self.refresh()
        self.host.on_profiles_changed()

    def _chrome_profiles(self) -> list[dict[str, Any]]:
        return list_chrome_profiles(self.host.state["settings"].get("chromeUserDataDir"))

    def _row(self, profile: dict[str, Any]) -> QFrame:
        row = QFrame()
        row.setObjectName("row")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(12, 10, 10, 10)
        layout.setSpacing(12)

        text = QVBoxLayout()
        text.setSpacing(2)
        name = (profile.get("name") or "").strip() or "Unnamed"
        title = QLabel(name)
        title.setObjectName("sectionTitle")
        chrome = profile.get("chromeDisplayName") or f"Profile {profile.get('chromeProfileNumber', 0)}"
        meta = QLabel(str(chrome))
        meta.setObjectName("muted")
        email = str((profile.get("imap") or {}).get("user") or "").strip()
        mail = QLabel(self._mail_line(email))
        mail.setObjectName("stateOk" if email and token_status(email).get("cached") else "muted")
        text.addWidget(title)
        text.addWidget(meta)
        text.addWidget(mail)
        layout.addLayout(text, 1)

        is_active = bool(profile.get("active"))
        active_btn = self._icon_button(
            "Active — click to turn off" if is_active else "Inactive — click to turn on",
            self._check_icon(is_active),
            "icon",
        )
        active_btn.setProperty("active", "true" if is_active else "false")
        polish(active_btn)
        active_btn.clicked.connect(lambda _checked=False, item=profile: self.toggle_active(item))
        update = self._icon_button("Edit profile", self._edit_icon(), "ghost")
        update.clicked.connect(lambda _checked=False, item=profile: self.edit_profile(item))
        remove = self._icon_button("Delete profile", self.style().standardIcon(QStyle.SP_TrashIcon), "danger")
        remove.clicked.connect(lambda _checked=False, item=profile: self.remove_profile(item))
        layout.addWidget(active_btn)
        layout.addWidget(update)
        layout.addWidget(remove)
        return row

    def _icon_button(self, tip: str, icon: QIcon, object_name: str) -> QPushButton:
        button = QPushButton()
        button.setObjectName(object_name)
        button.setIcon(icon)
        button.setToolTip(tip)
        button.setFixedSize(36, 36)
        button.setCursor(Qt.PointingHandCursor)
        return button

    def _edit_icon(self) -> QIcon:
        dark = getattr(self.window(), "_resolved_theme", "light") == "dark"
        pix = QPixmap(16, 16)
        pix.fill(Qt.transparent)
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor("#93c5fd" if dark else "#1d4ed8"), 1.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.drawLine(3, 13, 12, 4)
        painter.drawLine(10, 3, 13, 6)
        painter.drawLine(2, 14, 5, 13)
        painter.end()
        return QIcon(pix)

    def _mail_line(self, email: str) -> str:
        if not email:
            return "No Outlook address"
        if token_status(email).get("cached"):
            return f"{email}  ·  Connected"
        return f"{email}  ·  Not connected"

    def _check_icon(self, active: bool) -> QIcon:
        dark = getattr(self.window(), "_resolved_theme", "light") == "dark"
        if active:
            color = QColor("#93c5fd" if dark else "#1d4ed8")
        else:
            color = QColor("#6b7280" if dark else "#98a2b3")
        pix = QPixmap(16, 16)
        pix.fill(Qt.transparent)
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(color, 1.4))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(1, 1, 14, 14, 3, 3)
        if active:
            painter.setPen(QPen(color, 1.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            painter.drawLine(4, 8, 7, 12)
            painter.drawLine(7, 12, 12, 4)
        painter.end()
        return QIcon(pix)

    def toggle_active(self, profile: dict[str, Any]) -> None:
        profile["active"] = not bool(profile.get("active"))
        profile_id = str(profile.get("id") or "")
        selected = [item for item in self.host.state.get("selectedProfileIds") or [] if item != profile_id]
        if profile["active"]:
            selected.append(profile_id)
        self.host.state["selectedProfileIds"] = selected
        self.host.persist()
        self.refresh()
        self.host.on_profiles_changed()

    def edit_profile(self, profile: dict[str, Any]) -> None:
        dialog = ProfileDialog(self.host, profile, self._chrome_profiles(), self)
        if dialog.exec_() != QDialog.Accepted:
            return
        self._sync_active(profile)
        self.host.persist()
        self.refresh()
        self.host.on_profiles_changed()

    def _sync_active(self, profile: dict[str, Any]) -> None:
        if profile.get("active"):
            return
        profile_id = str(profile.get("id") or "")
        self.host.state["selectedProfileIds"] = [
            item for item in self.host.state.get("selectedProfileIds") or [] if item != profile_id
        ]

    def _ask(self, title: str, text: str) -> bool:
        box = QMessageBox(self)
        box.setWindowTitle(title)
        box.setText(text)
        box.setIcon(QMessageBox.Question)
        box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        box.setDefaultButton(QMessageBox.No)
        window = self.window()
        if window is not None:
            box.setStyleSheet(window.styleSheet())
        return box.exec_() == QMessageBox.Yes

    def connect_mailbox(self, profile: dict[str, Any], email: str, on_done=None) -> None:
        address = (email or "").strip()
        profile_id = str(profile.get("id") or "")
        if not address:
            self.host.alert("Mailbox", "Enter an Outlook address first.")
            return
        if profile_id in self._workers:
            return
        if not self._ask("Connect mailbox", f"Connect Outlook for {address}?"):
            return
        imap = profile.setdefault("imap", {})
        imap["user"] = address
        imap["preset"] = "outlook"
        imap["host"] = "outlook.office365.com"
        imap["port"] = 993
        imap["auth"] = "oauth"
        if on_done:
            self._mail_callbacks[profile_id] = on_done
            on_done(address)
        worker = MailConnectWorker(profile_id, address, self)
        worker.ok.connect(self._on_mail_ok)
        worker.failed.connect(self._on_mail_failed)
        self._workers[profile_id] = worker
        worker.start()

    def _on_mail_ok(self, profile_id: str) -> None:
        self._workers.pop(profile_id, None)
        callback = self._mail_callbacks.pop(profile_id, None)
        profile = next((item for item in self.host.state.get("profiles") or [] if str(item.get("id")) == profile_id), None)
        email = str((profile.get("imap") or {}).get("user") or "") if profile else ""
        if callback:
            callback(email)
        self.refresh()

    def _on_mail_failed(self, profile_id: str, message: str) -> None:
        self._workers.pop(profile_id, None)
        callback = self._mail_callbacks.pop(profile_id, None)
        if callback:
            callback("")
        self.host.alert("Mailbox", message, critical=True)

    def remove_profile(self, profile: dict[str, Any]) -> None:
        name = (profile.get("name") or "").strip() or "this profile"
        if not self._ask("Remove profile", f'Remove "{name}"?'):
            return
        profile_id = str(profile.get("id") or "")
        self.host.state["profiles"] = [
            item for item in self.host.state["profiles"] if item.get("id") != profile_id
        ]
        self.host.state["selectedProfileIds"] = [
            item for item in self.host.state.get("selectedProfileIds") or [] if item != profile_id
        ]
        self.host.status_by_profile.pop(profile_id, None)
        self.host.persist()
        self.refresh()
        self.host.on_profiles_changed()


def _chrome_label(meta: dict[str, Any]) -> str:
    number = int(meta.get("number") or 0)
    directory = meta.get("directory") or ("Default" if number == 0 else f"Profile {number}")
    name = meta.get("displayName") or directory
    if name == directory:
        return str(directory)
    return f"{name} · {directory}"
