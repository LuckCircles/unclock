# coding: utf-8
"""运行日志页面 —— 实时追加 service 广播的日志事件。"""

from PySide6.QtWidgets import QVBoxLayout
from qfluentwidgets import CardWidget, PlainTextEdit

from ..common.signal_bus import signalBus
from ..components.interface import Interface


class LogInterface(Interface):
    """运行日志页面（样式由 Fluent 主题接管）。"""

    def __init__(self, parent=None):
        super().__init__("LogInterface", parent)

        self.logCard = CardWidget(self)
        self.cardLayout = QVBoxLayout(self.logCard)
        self.cardLayout.setContentsMargins(15, 15, 15, 15)

        self.logText = PlainTextEdit(self)
        self.logText.setReadOnly(True)
        self.logText.setMaximumBlockCount(2000)

        self.cardLayout.addWidget(self.logText)
        self.vLayout.addWidget(self.logCard, 1)

        signalBus.log_emitted.connect(self._on_log)

    def _on_log(self, message: str, level: str):
        tag = {
            "info": "[INFO]",
            "error": "[ERROR]",
            "warning": "[WARN]",
            "success": "[OK]",
            "debug": "[DEBUG]",
        }.get(level, "[DEBUG]")
        self.logText.appendPlainText(f"{tag} {message}")
        self.logText.ensureCursorVisible()
