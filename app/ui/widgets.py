from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)


def card(title: str) -> tuple[QFrame, QVBoxLayout]:
    f = QFrame()
    f.setObjectName("Card")
    layout = QVBoxLayout(f)
    header = QLabel(title)
    header.setObjectName("CardTitle")
    layout.addWidget(header)
    return f, layout


def status_badge(text: str) -> QLabel:
    lb = QLabel(text)
    lb.setObjectName("StatusBadge")
    return lb


def action_button(text: str, object_name: str = "PrimaryButton") -> QPushButton:
    b = QPushButton(text)
    b.setObjectName(object_name)
    return b
