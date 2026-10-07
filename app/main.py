from __future__ import annotations

import sys
from pathlib import Path

# Allow `python -m app.main` and `python app/main.py` from repo root
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QApplication

from app.core.logging_setup import setup_logging
from app.config.manager import ConfigManager
from app.ui.main_window import MainWindow


def main() -> int:
    setup_logging()
    app = QApplication(sys.argv)
    app.setApplicationName("AWS Log Searcher")
    app.setOrganizationName("Company")
    ui_font = QFont()
    ui_font.setStyleHint(QFont.StyleHint.SansSerif)
    ui_font.setPointSize(13)
    app.setFont(ui_font)

    config = ConfigManager(base_dir=_ROOT)
    window = MainWindow(config)
    # Zoom to available desktop (menu bar + dock remain) — not macOS green-button fullscreen
    window.show_zoomed()

    window.raise_()
    window.activateWindow()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
