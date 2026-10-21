# coding: utf-8
"""跑马灯标签 —— 鼠标悬停时若文本过长则自动从左往右滚动，完整展示内容。

实现：内部持有一个 ``StrongBodyLabel`` 子控件并按完整文本宽度布局；外层
``MarqueeLabel`` 作为可视窗口（Qt 默认把子控件裁剪到父控件矩形内）。仅当
**鼠标悬停**且文本宽度超过可视宽度时，才用定时器把子控件逐步左移，从而
「从左往右」滚动揭示完整文件名；未悬停或能容纳时静态左对齐显示（零开销）。
子控件设为对鼠标透明，保证悬停进入/离开事件落到本控件上。
"""

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtWidgets import QSizePolicy, QWidget
from qfluentwidgets import StrongBodyLabel


class MarqueeLabel(QWidget):
    """单行文本，悬停且溢出时自动水平滚动（从左往右揭示完整文本）。"""

    _INTERVAL = 30   # 定时器间隔（ms）
    _STEP = 1        # 每帧滚动像素
    _PAUSE = 24      # 两端停顿帧数

    def __init__(self, text: str = "", parent=None):
        super().__init__(parent)
        self._label = StrongBodyLabel("", self)
        self._label.setWordWrap(False)
        self._label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        # 子控件对鼠标透明：悬停进入/离开事件才能落到本控件
        self._label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._offset = 0
        self._pause = 0
        self._text_width = 0
        self._hovered = False
        self._need_scroll = False
        self._timer = QTimer(self)
        self._timer.setInterval(self._INTERVAL)
        self._timer.timeout.connect(self._tick)
        self.setMinimumWidth(0)
        # 水平 Ignored：sizeHint（完整文本宽）不参与父布局分配，避免长文件名
        # 把所在网格列撑宽导致列宽不一致；控件仍会拉伸填满可用宽度并在其内滚动
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        if text:
            self.setText(text)

    def text(self) -> str:
        return self._label.text()

    def setText(self, text: str):
        self._label.setText(text or "")
        self._offset = 0
        self._pause = 0
        self._recalc()

    # ------------------------------------------------------------------ 内部
    def _recalc(self):
        """按完整文本宽度布局子控件，并据当前宽度/悬停状态决定是否滚动。"""
        self._label.adjustSize()
        self._text_width = self._label.width()
        if self.height() > 0:
            self._label.setFixedHeight(self.height())
        self._label.move(-self._offset, 0)
        self._need_scroll = self.width() > 0 and self._text_width > self.width()
        self._apply_scrolling()

    def _apply_scrolling(self):
        """仅当「悬停 且 文本溢出」时才滚动，否则静态并复位到开头。"""
        should = self._need_scroll and self._hovered
        if should and not self._timer.isActive():
            self._offset = 0
            self._pause = 0
            self._timer.start()
        elif not should and self._timer.isActive():
            self._timer.stop()
            self._offset = 0
            self._pause = 0
            self._label.move(0, 0)
        self.update()

    def _tick(self):
        max_off = max(0, self._text_width - self.width())
        if max_off <= 0:
            self._offset = 0
            self._label.move(0, 0)
            return
        if self._pause > 0:
            self._pause -= 1
            if self._pause == 0 and self._offset >= max_off:
                self._offset = 0
                self._pause = self._PAUSE
            self._label.move(-self._offset, 0)
            return
        self._offset += self._STEP
        if self._offset >= max_off:
            self._offset = max_off
            self._pause = self._PAUSE
        self._label.move(-self._offset, 0)

    # ------------------------------------------------------------------ 悬停驱动
    def set_hovered(self, hovered: bool):
        """由父卡片在鼠标进入/离开整张卡片时调用，驱动滚动启停。"""
        self._hovered = hovered
        self._apply_scrolling()

    # ------------------------------------------------------------------ Qt 重载
    def sizeHint(self):
        return QSize(self._text_width, self._label.sizeHint().height())

    def minimumSizeHint(self):
        # 最小宽度给 0，允许被布局压缩到很窄从而触发滚动，而不是撑宽卡片
        return QSize(0, self._label.sizeHint().height())

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._recalc()
