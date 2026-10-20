from PySide6.QtWidgets import QVBoxLayout, QWidget
from qfluentwidgets import CardWidget, PlainTextEdit, ScrollArea


class LogInterface(ScrollArea):
    """运行日志页面（样式由 Fluent 主题接管）"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.view = QWidget(self)
        self.vLayout = QVBoxLayout(self.view)
        self.vLayout.setContentsMargins(30, 30, 30, 30)
        self.vLayout.setSpacing(20)

        self.setWidget(self.view)
        self.setWidgetResizable(True)
        self.setObjectName("LogInterface")

        self.logCard = CardWidget(self)
        self.cardLayout = QVBoxLayout(self.logCard)
        self.cardLayout.setContentsMargins(15, 15, 15, 15)

        self.logText = PlainTextEdit(self)
        self.logText.setReadOnly(True)
        self.logText.setMaximumBlockCount(2000)

        self.cardLayout.addWidget(self.logText)
        self.vLayout.addWidget(self.logCard, 1)

    def append_log(self, message):
        self.logText.appendPlainText(message)
        self.logText.ensureCursorVisible()

    def clear_log(self):
        self.logText.clear()
