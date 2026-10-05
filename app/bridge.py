from __future__ import annotations

import json
import threading
import traceback
from pathlib import Path
from typing import Any

from PyQt5.QtCore import QObject, QThread, pyqtSignal, pyqtSlot
from PyQt5.QtWidgets import QApplication

from app.automation.chrome import list_chrome_profiles
from app.automation.runner import Runner
from app.store import load_state, save_state


class RunnerWorker(QThread):
    status = pyqtSignal(str)
    run_state = pyqtSignal(str)
    finished_ok = pyqtSignal()
    failed = pyqtSignal(str)

    def __init__(
        self,
        settings: dict[str, Any],
        work_area: dict[str, int],
        urls: list[dict[str, Any]],
        profiles: list[dict[str, Any]],
        user_data: Path,
        parent=None,
    ):
        super().__init__(parent)
        self.settings = settings
        self.work_area = work_area
        self.urls = urls
        self.profiles = profiles
        self.user_data = user_data
        self.runner: Runner | None = None

    def run(self) -> None:
        try:
            self.runner = Runner(
                settings=self.settings,
                work_area=self.work_area,
                on_status=lambda payload: self.status.emit(json.dumps(payload)),
                on_run_state=lambda payload: self.run_state.emit(json.dumps(payload)),
                user_data_root=self.user_data,
            )
            # Playwright Sync API refuses to start when an asyncio loop is already
            # running. Some Qt setups leave a loop on the QThread, so drive the
            # runner from a plain OS thread that has no event loop.
            errors: list[BaseException] = []

            def _drive() -> None:
                try:
                    assert self.runner is not None
                    self.runner.start(self.urls, self.profiles)
                except BaseException as exc:  # noqa: BLE001 - surface to QThread
                    errors.append(exc)

            worker = threading.Thread(target=_drive, name="greenhouse-runner", daemon=True)
            worker.start()
            while worker.is_alive():
                worker.join(0.25)
            if errors:
                raise errors[0]
            self.finished_ok.emit()
        except Exception as error:
            self.failed.emit(f"{error}\n{traceback.format_exc()}")

    def request_stop(self) -> None:
        if self.runner:
            self.runner.stop()


class Bridge(QObject):
    statusChanged = pyqtSignal(str)
    runStateChanged = pyqtSignal(str)

    def __init__(self, user_data: Path, parent=None):
        super().__init__(parent)
        self._work_area = {"x": 0, "y": 0, "width": 1280, "height": 900}
        self.user_data = user_data
        self.worker: RunnerWorker | None = None

    def set_work_area(self, work_area: dict[str, int]) -> None:
        self._work_area = work_area

    @pyqtSlot(result=str)
    def getState(self) -> str:
        return json.dumps(load_state(self.user_data))

    @pyqtSlot(str, result=str)
    def saveState(self, payload: str) -> str:
        data = json.loads(payload)
        return json.dumps(save_state(self.user_data, data))

    @pyqtSlot(result=str)
    def listChromeProfiles(self) -> str:
        state = load_state(self.user_data)
        return json.dumps(
            list_chrome_profiles(state["settings"].get("chromeUserDataDir"))
        )

    def start(self, urls: list[dict[str, Any]], profiles: list[dict[str, Any]], settings: dict[str, Any]) -> None:
        if self.worker and self.worker.isRunning():
            raise RuntimeError("Already running")

        app = QApplication.instance()
        screen = app.primaryScreen() if app else None
        if screen:
            geo = screen.availableGeometry()
            self._work_area = {
                "x": geo.x(),
                "y": geo.y(),
                "width": geo.width(),
                "height": geo.height(),
            }

        self.worker = RunnerWorker(
            settings=settings,
            work_area=self._work_area,
            urls=urls,
            profiles=profiles,
            user_data=self.user_data,
        )
        self.worker.status.connect(self.statusChanged.emit)
        self.worker.run_state.connect(self.runStateChanged.emit)
        self.worker.failed.connect(lambda err: self.runStateChanged.emit(
            json.dumps({"running": False, "message": "Start failed", "error": err})
        ))
        self.worker.finished_ok.connect(lambda: self.runStateChanged.emit(
            json.dumps({"running": False, "message": "Finished"})
        ))
        self.worker.start()

    def stop(self) -> None:
        if self.worker:
            self.worker.request_stop()
