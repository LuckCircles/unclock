# coding: utf-8
"""应用入口的薄 Application 包装。"""

from PySide6.QtWidgets import QApplication


class SingletonApplication(QApplication):
    """应用对象（保留分层占位，便于后续接入单实例锁）。"""

    def __init__(self, argv, name: str = "unclock"):
        super().__init__(argv)
        self.setApplicationName(name)
        self.setApplicationDisplayName("音乐解锁工具")
