from PySide6.QtGui import QColor
from PySide6.QtWidgets import QWidget, QVBoxLayout, QPlainTextEdit
from qfluentwidgets import ScrollArea, CardWidget, themeColor


class LogInterface(ScrollArea):
    """运行日志页面"""

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

        self.logText = QPlainTextEdit(self)
        self.logText.setReadOnly(True)
        self.logText.setMaximumBlockCount(2000)
        self._apply_theme_style()

        self.cardLayout.addWidget(self.logText)
        self.vLayout.addWidget(self.logCard, 1)

    def _apply_theme_style(self):
        accent = themeColor()
        panel_bg = self._with_alpha(accent, 20)
        editor_bg = self._with_alpha(accent, 28)
        border = self._with_alpha(accent, 80)
        selection_bg = self._with_alpha(accent, 70)
        # self.logCard.setStyleSheet(f"""
        #     CardWidget {{
        #         background-color: {panel_bg};
        #         border: 1px solid {border};
        #         border-radius: 12px;
        #     }}
        # """)

        # self.logText.setStyleSheet(f"""
        #     QPlainTextEdit {{
        #         background-color: {editor_bg};
        #         color: #2b2b2b;
        #         font-family: 'Consolas', 'Microsoft YaHei UI', monospace;
        #         font-size: 12px;
        #         border: 1px solid {border};
        #         border-radius: 10px;
        #         padding: 8px 10px;
        #         selection-background-color: {selection_bg};
        #         selection-color: #1f1f1f;
        #     }}
        # """)

    def _with_alpha(self, color: QColor, alpha: int) -> str:
        result = QColor(color)
        result.setAlpha(alpha)
        return result.name(QColor.HexArgb)

    def append_log(self, message):
        self.logText.appendPlainText(message)
        self.logText.ensureCursorVisible()

    def clear_log(self):
        self.logText.clear()
