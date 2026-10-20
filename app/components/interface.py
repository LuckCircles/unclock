# coding: utf-8
"""页面基类 —— 统一 ScrollArea 的边距与可缩放容器骨架。"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout
from qfluentwidgets import ScrollArea


class Interface(ScrollArea):
    """所有页面的基类，提供统一布局容器 ``vLayout``。"""

    def __init__(self, object_name: str, parent=None):
        super().__init__(parent)
        self._object_name = object_name

        self.view = QWidget(self)
        self.vLayout = QVBoxLayout(self.view)
        self.vLayout.setContentsMargins(30, 30, 30, 30)
        self.vLayout.setSpacing(20)
        self.vLayout.setAlignment(Qt.AlignTop)

        self.setWidget(self.view)
        self.setWidgetResizable(True)
        self.setObjectName(object_name)

        # 让滚动区背景透明，融入 MSFluentWindow 的主题背景色，
        # 避免内容区出现与窗口不一致的白色/深色分层色块
        self.enableTransparentBackground()
