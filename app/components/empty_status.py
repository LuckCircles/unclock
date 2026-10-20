# coding: utf-8
"""空状态提示组件。"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QWidget
from qfluentwidgets import CaptionLabel, IconWidget, FluentIcon


class EmptyStatusWidget(QWidget):
    """列表为空时的居中提示。"""

    def __init__(self, hint: str = "暂无文件", parent=None):
        super().__init__(parent)
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(0, 24, 0, 24)
        self.layout.setAlignment(Qt.AlignCenter)

        self.icon = IconWidget(FluentIcon.INFO, self)
        self.icon.setFixedSize(24, 24)
        self.label = CaptionLabel(hint, self)

        self.layout.addWidget(self.icon)
        self.layout.addWidget(self.label)
