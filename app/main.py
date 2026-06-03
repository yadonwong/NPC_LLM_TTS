import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from app.core.config import load_settings
from app.core.logger import LogEmitter, setup_logger
from app.ui.main_window import MainWindow


def load_qss(app: QApplication):
    qss_path = Path(__file__).resolve().parent / "ui" / "style.qss"
    if qss_path.exists():
        app.setStyleSheet(qss_path.read_text(encoding="utf-8"))


def main():
    app = QApplication(sys.argv)
    load_qss(app)

    config = load_settings()
    emitter = LogEmitter()
    logger = setup_logger(qt_emitter=emitter)

    w = MainWindow(config=config, logger=logger, log_emitter=emitter)
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
