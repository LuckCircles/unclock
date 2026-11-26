# coding: utf-8
"""运行日志页面 —— 实时追加 service 广播的日志事件（按级别着色）。"""

import html

from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout
from qfluentwidgets import (
    CardWidget,
    PlainTextEdit,
    StrongBodyLabel,
    TransparentToolButton,
    FluentIcon,
    ToolTipFilter,
    ToolTipPosition,
    isDarkTheme,
)

from ..common.i18n import translate_ui
from ..common.signal_bus import signalBus
from ..components.interface import Interface

# 级别 → 标签文本
_TAG = {
    "info": "INFO",
    "error": "ERROR",
    "warning": "WARN",
    "success": "OK",
    "debug": "DEBUG",
}

# 级别 → 文字颜色（明 / 暗主题双板，取 Fluent 语义色）
_COLORS_LIGHT = {
    "info": "#0078d4",
    "error": "#c42b1c",
    "warning": "#d83b01",
    "success": "#107c10",
    "debug": "#8a8886",
}
_COLORS_DARK = {
    "info": "#4cc2ff",
    "error": "#ff99a4",
    "warning": "#ffd264",
    "success": "#6ccb5f",
    "debug": "#b3afab",
}


class LogInterface(Interface):
    """运行日志页面（级别着色 + 一键清空，样式由 Fluent 主题接管）。"""

    def __init__(self, parent=None):
        super().__init__("LogInterface", parent)

        self.logCard = CardWidget(self)
        self.cardLayout = QVBoxLayout(self.logCard)
        self.cardLayout.setContentsMargins(15, 12, 15, 15)
        self.cardLayout.setSpacing(10)

        # 标题行：标题居左、清空按钮居右
        self.headerLayout = QHBoxLayout()
        self.headerLayout.setSpacing(10)
        self.titleLabel = StrongBodyLabel("运行日志", self.logCard)
        self.btnClear = TransparentToolButton(FluentIcon.DELETE, self.logCard)
        self.btnClear.setToolTip("<b>清空日志</b><br/>只清空本页显示，不影响日志文件")
        self.btnClear.setToolTipDuration(-1)  # 鼠标移开才隐藏
        self.btnClearTip = ToolTipFilter(
            self.btnClear, showDelay=300, position=ToolTipPosition.TOP
        )
        self.btnClear.installEventFilter(self.btnClearTip)
        self.headerLayout.addWidget(self.titleLabel)
        self.headerLayout.addStretch(1)
        self.headerLayout.addWidget(self.btnClear)

        self.logText = PlainTextEdit(self.logCard)
        self.logText.setReadOnly(True)
        self.logText.setMaximumBlockCount(2000)

        self.cardLayout.addLayout(self.headerLayout)
        self.cardLayout.addWidget(self.logText, 1)
        self.vLayout.addWidget(self.logCard, 1)

        self.btnClear.clicked.connect(self.logText.clear)
        signalBus.log_emitted.connect(self._on_log)

    def _on_log(self, message: str, level: str):
        tag = _TAG.get(level, "DEBUG")
        palette = _COLORS_DARK if isDarkTheme() else _COLORS_LIGHT
        color = palette.get(level, palette["debug"])
        # 数字模板类消息（如「已处理 3/5 个文件…」）按当前语言查表翻译；
        # 未命中模板（含路径/版本号的消息）原样保留
        message = translate_ui(message)
        # 消息体做 HTML 转义，防止日志内容中的尖括号被当作标记解析
        safe = html.escape(message)
        self.logText.appendHtml(
            f'<span style="color:{color};font-weight:600;">[{tag}]</span> {safe}'
        )
        self.logText.ensureCursorVisible()
