# coding: utf-8
"""主页目录快捷卡片 —— 点击打开系统文件管理器。"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    CardWidget,
    FluentIcon,
    IconWidget,
)


class PathCard(CardWidget):
    """主页目录快捷卡片。"""

    clicked = Signal()

    def __init__(self, title: str, description: str, icon, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)

        self.hLayout = QHBoxLayout(self)
        self.hLayout.setContentsMargins(18, 16, 18, 16)
        self.hLayout.setSpacing(14)

        self.iconWidget = IconWidget(icon, self)
        self.iconWidget.setFixedSize(22, 22)

        self.textLayout = QVBoxLayout()
        self.textLayout.setSpacing(4)
        self.titleLabel = BodyLabel(title, self)
        self.pathLabel = CaptionLabel(description, self)
        self.pathLabel.setWordWrap(True)
        self.openIcon = IconWidget(FluentIcon.RIGHT_ARROW, self)
        self.openIcon.setFixedSize(16, 16)

        self.textLayout.addWidget(self.titleLabel)
        self.textLayout.addWidget(self.pathLabel)

        self.hLayout.addWidget(self.iconWidget, 0, Qt.AlignTop)
        self.hLayout.addLayout(self.textLayout, 1)
        self.hLayout.addWidget(self.openIcon, 0, Qt.AlignVCenter)

    def set_path(self, path: str, fallback: str):
        self.pathLabel.setText(path or fallback)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)
