from __future__ import annotations

import sys
from pathlib import Path

from PyQt5.QtWidgets import QApplication

from app.ui import MainWindow


def main() -> int:
    root = Path(__file__).resolve().parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    from app.automation.resume_server import start_resume_server, stop_resume_server
    from app.store import load_state

    settings = load_state(root / ".app-data")["settings"]
    start_resume_server(int(settings.get("resumeServerPort") or 615))

    app = QApplication(sys.argv)
    app.setApplicationName("Greenhouse Auto Apply")
    window = MainWindow(root / ".app-data")
    window.show()
    code = app.exec_()
    stop_resume_server()
    return code


if __name__ == "__main__":
    raise SystemExit(main())
