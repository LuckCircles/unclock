# coding: utf-8
"""跑马灯标签 —— 鼠标悬停时若文本过长则自动水平滚动，完整展示内容。

实现：内部持有**两份相同文本**的 ``StrongBodyLabel`` 子控件，外层
``MarqueeLabel`` 作为可视窗口（Qt 默认把子控件裁剪到父控件矩形内）。仅当
**鼠标悬停**且文本宽度超过可视宽度时，才用定时器按时间片把两份文本同步左移：
滚动偏移在「文本宽 + 间距」周期内**取模循环**，第二份文本恰好在第一份完全
滚出视区时接替其位置，像素级重合，视觉上**首尾相连**无缝循环；未悬停或能
容纳时静态左对齐只显示一份（零开销，第二份隐藏）。
滚动为**时间驱动**（``QElapsedTimer`` 计量帧间隔）：定时器帧率波动不影响
观感速度；悬停后经短起始延迟 + 0.15s 起步加速即进入全速循环，启动跟手。
子控件设为对鼠标透明，保证悬停进入/离开事件落到本控件上。
"""

from PySide6.QtCore import QElapsedTimer, QSize, Qt, QTimer
from PySide6.QtWidgets import QSizePolicy, QWidget
from qfluentwidgets import StrongBodyLabel


class MarqueeLabel(QWidget):
    """单行文本，悬停且溢出时首尾相连无缝循环滚动。"""

    _INTERVAL = 16        # 定时器间隔（ms）≈60fps
    _SPEED = 85           # 滚动速度（像素/秒）
    _START_DELAY = 0.15   # 悬停后起始延迟（秒）：兼顾启动速度与误触发过滤
    _RAMP = 0.15          # 起步加速时长（秒）：速度由 50% 平滑升至 100%
    _GAP = 48             # 首尾相连时相邻两份文本的间距（像素）
    _MAX_DT = 0.05        # 单帧最大计入时长（秒）：系统卡顿后防止大跳跃

    def __init__(self, text: str = "", parent=None):
        super().__init__(parent)
        # 首尾两份相同文本：第二份在第一份滚出后接替，实现无缝循环。
        # 第二份**按需创建**（仅在真正开始滚动时）——不滚动的卡片永远只有一份，
        # 数百张卡的启动/刷新场景下省掉约一半标签构建开销。
        self._labels = [self._make_label()]
        self._offset = 0.0     # 当前滚动偏移（一个周期内取模）
        self._age = 0.0        # 本次滚动启动后的时长（秒），用于起步加速
        self._pause = 0.0      # 剩余起始延迟（秒）
        self._text_width = 0
        self._period = 1       # 滚动周期 = 文本宽 + 间距
        self._hovered = False
        self._need_scroll = False
        self._clock = QElapsedTimer()
        self._timer = QTimer(self)
        self._timer.setInterval(self._INTERVAL)
        self._timer.setTimerType(Qt.PreciseTimer)
        self._timer.timeout.connect(self._tick)
        self.setMinimumWidth(0)
        # 水平 Ignored：sizeHint（完整文本宽）不参与父布局分配，避免长文件名
        # 把所在网格列撑宽导致列宽不一致；控件仍会拉伸填满可用宽度并在其内滚动
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        if text:
            self.setText(text)

    def _make_label(self, text: str = "") -> StrongBodyLabel:
        """创建一份文本子控件（对鼠标透明，悬停事件才能落到本控件）。"""
        lb = StrongBodyLabel(text, self)
        lb.setWordWrap(False)
        lb.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        lb.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        return lb

    def text(self) -> str:
        return self._labels[0].text()

    def setText(self, text: str):
        for lb in self._labels:
            lb.setText(text or "")
        self._offset = 0
        self._age = 0
        self._pause = 0
        self._recalc()

    # ------------------------------------------------------------------ 内部
    def _recalc(self):
        """按完整文本宽度布局子控件，并据当前宽度/悬停状态决定是否滚动。"""
        for lb in self._labels:
            lb.adjustSize()
            if self.height() > 0:
                lb.setFixedHeight(self.height())
        self._text_width = self._labels[0].width()
        self._period = self._text_width + self._GAP
        # 宽度变化（如窗口缩放）时把偏移钳回周期内，防止越界
        if self._period > 0:
            self._offset %= self._period
        self._need_scroll = self.width() > 0 and self._text_width > self.width()
        self._place()
        self._apply_scrolling()

    def _ensure_second(self):
        """按需创建第二份文本（首尾相连循环用）；已存在则直接返回。"""
        if len(self._labels) >= 2:
            return
        lb = self._make_label(self._labels[0].text())
        lb.adjustSize()
        if self.height() > 0:
            lb.setFixedHeight(self.height())
        self._labels.append(lb)

    def _place(self):
        """按当前偏移摆放首尾两份文本（偏移在周期内取模，回绕无感）。"""
        p = self._period
        for k, lb in enumerate(self._labels):
            lb.move(k * p - round(self._offset), 0)

    def _apply_scrolling(self):
        """仅当「悬停 且 文本溢出」时才滚动，否则静态并复位到开头。"""
        should = self._need_scroll and self._hovered
        if should and not self._timer.isActive():
            self._ensure_second()
            self._offset = 0
            self._age = 0
            self._pause = self._START_DELAY
            self._labels[1].setVisible(True)
            self._clock.start()
            self._timer.start()
        elif not should:
            if self._timer.isActive():
                self._stop()
            elif len(self._labels) > 1:
                # 静止态：隐藏第二份文本（若已创建），确保只显示一份
                self._labels[1].setVisible(False)
        self.update()

    def _stop(self):
        """停止滚动并复位到开头（隐藏第二份文本，若已创建）。"""
        self._timer.stop()
        self._offset = 0
        self._age = 0
        self._pause = 0
        if len(self._labels) > 1:
            self._labels[1].setVisible(False)
        self._labels[0].move(0, 0)

    def _tick(self):
        if self._period <= 0 or self.width() <= 0 or self._text_width <= self.width():
            self._stop()
            return
        # 时间驱动：帧间隔波动不影响观感速度；卡顿后限制单帧步长防跳跃
        dt = min(self._clock.restart() / 1000.0, self._MAX_DT)
        if self._pause > 0:
            self._pause -= dt
            self._place()
            return
        # 起步加速：启动后前 _RAMP 秒由 50% 平滑升至全速，随后恒定
        self._age += dt
        factor = 1.0 if self._age >= self._RAMP else 0.5 + 0.5 * (self._age / self._RAMP)
        step = self._SPEED * factor * dt
        # 首尾相连：偏移在「文本宽 + 间距」周期内取模，回绕时视觉无变化
        self._offset = (self._offset + step) % self._period
        self._place()

    # ------------------------------------------------------------------ 悬停驱动
    def set_hovered(self, hovered: bool):
        """由父卡片在鼠标进入/离开整张卡片时调用，驱动滚动启停。"""
        self._hovered = hovered
        self._apply_scrolling()

    # ------------------------------------------------------------------ Qt 重载
    def sizeHint(self):
        return QSize(self._text_width, self._labels[0].sizeHint().height())

    def minimumSizeHint(self):
        # 最小宽度给 0，允许被布局压缩到很窄从而触发滚动，而不是撑宽卡片
        return QSize(0, self._labels[0].sizeHint().height())

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._recalc()

    def hideEvent(self, e):
        # 页面切换/控件隐藏时停表复位，避免后台空转
        super().hideEvent(e)
        if self._timer.isActive():
            self._stop()
