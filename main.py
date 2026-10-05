from __future__ import annotations

import sys
from pathlib import Path

from PyQt5.QtWidgets import QApplication

from app.ui import MainWindow


def main() -> int:
    root = Path(__file__).resolve().parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    app = QApplication(sys.argv)
    app.setApplicationName("Greenhouse Auto Apply")
    window = MainWindow(root / ".app-data")
    window.show()
    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
