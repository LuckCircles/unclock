# coding: utf-8
"""卡片网格容器基类 —— 固定工具栏 + 独立滚动卡片网格双区骨架。

页面结构（任务管理 / 已解密两页共用）：
- 上侧：工具栏卡片固定，不随列表滚动；
- 下侧：独立滚动区域，内部是自适应列数的卡片网格——滚动条在滚动区内部，
  不再贴着窗口右缘贯穿工具栏高度。

子类钩子：
- ``_make_card(item)``：由条目构建单张卡片（必选）；
- ``_sort_cards()``：重排前对 ``_cards`` 排序（默认保持既有顺序，仅即时页）；
- ``_visible_cards()``：返回参与排布的卡片（默认全部，供搜索/过滤页覆写，仅即时页）；
- ``_lazy_filter()``：懒加载页的条目过滤（默认全部条目）；
- ``_update_count()``：刷新工具栏计数与空状态提示（必选）；
- ``_on_card_removed(card)``：卡片被移除时的联动（默认无操作）。

两种填充模式：
- 即时模式（默认）：条目逐个建卡入网格，时间片分批防假死；
- 懒加载模式（类属性 ``lazy_fill = True``）：先为全部条目铺 QSpacerItem
  占位格（纯几何对象而非控件，千级条目铺格也只花几毫秒），真实卡片
  滚动到视口内（上下各预载 2 行）才按需创建——首屏与滚动均不卡顿，
  滚动条高度始终正确。

入场呈现（类属性 ``fade_in = True``）：新建卡片先在同一帧挂 opacity=0
的透明度效果，再按网格顺序逐张淡入，形成瀑布流式「从少到多、由隐到显」
的错峰铺开。透明度只改绘制、不改几何，结束时立即卸载效果恢复原生绘制，
因此不会触发 Qt 布局补算（不产生卡片位移）。
"""

from collections import deque
import time

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QPropertyAnimation,
    QSignalBlocker,
    Qt,
    QTimer,
)
from PySide6.QtWidgets import (
    QGraphicsOpacityEffect,
    QGridLayout,
    QHBoxLayout,
    QSizePolicy,
    QSpacerItem,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import CardWidget, ScrollArea

from .empty_status import EmptyStatusWidget

# 网格布局参数：卡片最小宽 + 水平间距，用于计算列数。
# 列数取偶（2/4/6…）并随窗口宽度自适应：视口每多容纳一列（≥_CARD_MIN_W）
# 就加列；卡片始终拉伸填满整行，两侧不留空白。
_CARD_MIN_W = 260
_H_SPACING = 12
# 网格垂直间距 + 卡片固定行高（与 TaskCard.setFixedHeight(64) 一致）：
# 懒加载按此计算视口覆盖的行范围
_V_SPACING = 10
_ROW_H = 64
# 时间片分批建卡：单帧构建满此预算（毫秒）即让出事件循环。
# 卡片构建耗时不一（磁盘 stat / 徽章控件创建），按时间切片比固定张数
# 分批更能把每帧开销稳定压在一帧预算内，填充期间交互不卡顿。
_FILL_BUDGET_MS = 12
# 视口 resize 重排防抖（毫秒）：拖拽缩放窗口时合并连续 resize 事件，
# 只在停下后重排一次，避免期间每帧全量摘挂卡片。
_RELAYOUT_DEBOUNCE_MS = 40
# 懒加载视口外预载行数：上下各多建几行，滚动方向上提前物化
_LAZY_PRELOAD_ROWS = 2
# 瀑布流入场：相邻卡片启动间隔 / 单卡淡入时长 / 滚动物化的短淡入。
# 卡片按网格顺序错峰启动，前一张尚未淡完下一张已开始，视觉上逐行铺开。
_FADE_STAGGER_MS = 16
_FADE_DURATION_MS = 220
_FADE_SCROLL_MS = 140
# 单次最多错峰淡入的卡片数：超出部分（视口外）直接完全显示，
# 避免千级列表把动画拖到数秒；40 张 ≈ 5 行 8 列首屏，覆盖典型视口。
_FADE_MAX_CARDS = 40
# 非刷新内部扫描的原地脉冲 / 空列表刷新反馈：目标从该透明度回到 1.0。
# 刻意不从 0 开始、不做错峰——这些场景要的是「闪一次」，而不是把整屏
# 清空后自上而下重新铺一遍；用户主动刷新走 replay_from_top() 的瀑布流。
_REPLAY_MIN_OPACITY = 0.45
_REPLAY_PULSE_MS = 200


class GridCardContainer(QWidget):
    """固定工具栏 + 滚动卡片网格的页面骨架（消除两页约 60% 的重复代码）。"""

    # 懒加载开关：True 时仅创建视口内可见卡片（大数据量页面开启）
    lazy_fill = False
    # 瀑布流入场：新建卡片按网格顺序错峰淡入（只改绘制，不改几何）
    fade_in = True

    def __init__(self, object_name: str, parent=None):
        super().__init__(parent)
        self._object_name = object_name
        self._cards = []
        self._grid_cols = 0
        self._pending_paths = deque()  # 分批建卡的在途路径队列
        self._filling = False     # 渐进填充进行中：抑制空状态提示闪现
        self._fill_restore_value = None  # 渐进重建前的滚动位置（填充完成时恢复）
        self._fill_frozen = False    # 渐进重建期间冻结页面绘制（隐藏中间态）
        self._fill_refresh = False   # 本轮重建是否来自「刷新」（决定回顶部 / 恢复视点）

        # 懒加载状态（lazy_fill=True 的页面使用）
        self._items = []        # 全量数据条目（对基类不透明：路径或元组）
        self._view = []         # 过滤排序后的展示条目
        self._card_cache = {}   # 已物化卡片：item → card
        self._spacer_at = {}    # 未物化占位格：item → QSpacerItem

        # 视口 resize 重排防抖：拖拽缩放期间合并连续事件，停下后重排一次
        self._relayoutTimer = QTimer(self)
        self._relayoutTimer.setSingleShot(True)
        self._relayoutTimer.setInterval(_RELAYOUT_DEBOUNCE_MS)
        self._relayoutTimer.timeout.connect(self._relayout)

        # 瀑布流入场：待淡入队列 + 节拍器 + 进行中的动画（保引用防 GC）
        self._fade_queue = deque()
        self._fade_anims = {}
        self._fade_scheduled = 0  # 本次重建已排入淡入的累计张数（上限 40）
        # 懒加载重建期间关闭物化入场动画（改由 replay_fade_in 整屏脉冲）
        self._suppress_materialize_fade = False
        self._fadeTimer = QTimer(self)
        self._fadeTimer.setInterval(_FADE_STAGGER_MS)
        self._fadeTimer.timeout.connect(self._fade_tick)

        self.setObjectName(object_name)

        # 页面骨架：上侧工具栏固定 + 下侧滚动区平级挂载（滚动区只包卡片网格）
        self.pageLayout = QVBoxLayout(self)
        self.pageLayout.setContentsMargins(30, 30, 30, 30)
        self.pageLayout.setSpacing(20)

        # 固定工具栏卡片：子类把控件放进 toolbarLayout
        self.toolbarCard = CardWidget(self)
        self.toolbarLayout = QHBoxLayout(self.toolbarCard)
        self.toolbarLayout.setContentsMargins(15, 12, 15, 12)
        self.toolbarLayout.setSpacing(10)
        self.pageLayout.addWidget(self.toolbarCard)

        # 滚动区：垂直滚动条在滚动区内部（视口自动收缩，卡片不会被遮挡），
        # 横向禁用（网格列数随宽度自适应，无需横向滚动）
        self.scrollArea = ScrollArea(self)
        self.scrollArea.enableTransparentBackground()
        self.scrollArea.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scrollArea.setWidgetResizable(True)
        self.scrollArea.viewport().installEventFilter(self)
        self.pageLayout.addWidget(self.scrollArea, 1)

        # 滚动内容：网格贴顶排布，剩余高度由底部 stretch 吸收——
        # 若给网格加 stretch，Qt 会把额外高度分摊到各行、使固定高度的卡片
        # 垂直居中漂浮，出现上方大片空白
        self.scrollContent = QWidget()
        self.scrollLayout = QVBoxLayout(self.scrollContent)
        self.scrollLayout.setContentsMargins(0, 0, 0, 0)
        self.gridLayout = QGridLayout()
        self.gridLayout.setContentsMargins(0, 0, 0, 0)
        self.gridLayout.setHorizontalSpacing(_H_SPACING)
        self.gridLayout.setVerticalSpacing(_V_SPACING)
        self.scrollLayout.addLayout(self.gridLayout)
        self.scrollLayout.addStretch(1)
        self.scrollArea.setWidget(self.scrollContent)

        # 懒加载：滚动到新区域时物化视口内占位格为真实卡片（即时页为空操作）
        self.scrollArea.verticalScrollBar().valueChanged.connect(
            self._on_lazy_scroll
        )

        # 空状态提示：叠加在滚动区中央的浮层（表情卡片 + 提示文字，
        # 对鼠标透明，不拦卡片操作）
        self.emptyHint = EmptyStatusWidget(
            "暂无内容", self.scrollArea, image_name="task_complete.png"
        )
        self.emptyHint.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.emptyHint.hide()
        self._empty_shown = False   # 记录显隐状态，避免重复 setVisible 触发布局

    # ------------------------------------------------------------ 钩子（子类实现）
    def _make_card(self, path: str):
        """由路径构建单张卡片（子类必须实现）。"""
        raise NotImplementedError

    def _sort_cards(self):
        """重排前排序钩子（默认保持既有顺序）。"""

    def _visible_cards(self) -> list:
        """参与排布的卡片（默认全部；搜索/过滤页覆写，仅即时页）。"""
        return self._cards

    def _lazy_filter(self) -> list:
        """懒加载页的条目过滤钩子（默认全部条目；搜索/分类页覆写）。"""
        return list(self._items)

    def _update_count(self):
        """刷新工具栏计数与空状态提示（子类必须实现）。"""
        raise NotImplementedError

    def _on_card_removed(self, card):
        """卡片被移除时的联动钩子（默认无操作）。"""

    # ------------------------------------------------------------ 事件
    def eventFilter(self, obj, event):
        # 滚动区视口尺寸变化（窗口缩放 / 滚动条显隐）→ 防抖重排 + 同步浮层
        if obj is self.scrollArea.viewport() and event.type() == QEvent.Resize:
            self._relayoutTimer.start()
            self._sync_overlay_geometry()
        return super().eventFilter(obj, event)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._sync_overlay_geometry()

    # ------------------------------------------------------------ 网格排布
    def _grid_add_widget(self, card, row: int, col: int):
        """卡片入格 + 立即显示。

        必须显式 show：``_make_card`` 建卡的 parent 是页面本身，addWidget
        时 Qt 会把卡片迁移到布局容器（scrollContent），**setParent 迁移
        即 hide**。hidden 的 widget 在布局 sizeHint() 中贡献为 0，QScrollArea
        据此把内容高度压小 → 网格各行被强制压缩、卡片挤到错误位置；卡片
        稍后被显示后高度恢复、卡片又弹回原位——两帧之间的大幅位移就是
        「点刷新后卡片上下晃动」。淡入模式下 show 由 opacity=0 效果遮蔽，
        不会闪现。``_relayout`` 摘挂回填的卡片（takeAt + setParent(None)
        同样触发 hide）也全部经此入口恢复显示。
        """
        self.gridLayout.addWidget(card, row, col)
        card.show()

    def _pin_content_height(self, rows: int):
        """把滚动内容高度主动拉到网格需求（rows 行 × 固定行高），只增不减。

        渐进填充/重建期间，QScrollArea 对 scrollContent 的 resize 是异步
        的（LayoutRequest 逐帧追赶），会出现「网格需求已涨、内容高度未涨」
        的窗口——布局在这个不够的高度内激活，QGridLayout 会把各行强制
        压缩（实测行高 64 被压到 50~59），卡片超出格子相互叠压，视觉即
        「卡片挤压晃动」。这里主动把内容拉高到需求，布局激活时高度永远
        足够，压缩帧不再出现。

        只增不减（``sc.resize`` 也遵守最小值，不压缩当前已更高的内容）：
        不用 ``setMinimumHeight`` 常驻约束——实测它会在 QScrollArea 的
        某些 resize 时序下静默把滚动位置清零（range 缩小时 value 不经
        clamp 直接归 0，破坏「筛选/刷新保持滚动位置」的既定行为）。
        内容变少的收缩交给 QScrollArea 按自身时序异步完成，届时 range
        正常缩小、value 正常 clamp。行高按 _ROW_H 常量计算（与
        TaskCard setFixedHeight(64) 一致，两页共用）。
        """
        h = rows * (_ROW_H + _V_SPACING) - _V_SPACING if rows > 0 else 0
        if self.scrollContent.height() < h:
            self.scrollContent.resize(self.scrollContent.width(), h)

    def _relayout(self):
        """按视口宽度计算列数并重排（宽度均分填满整行）。"""
        if self.lazy_fill:
            self._relayout_lazy()
            return
        self._sort_cards()
        # 摘除现有 item（不销毁 widget）
        while self.gridLayout.count():
            item = self.gridLayout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
        visible = self._visible_cards()
        # 可用宽 = 滚动区视口宽（视口已排除垂直滚动条宽度；页面左右边距在滚动区之外，
        # 网格内容与工具栏卡片左右对齐）
        available = max(self.scrollArea.viewport().width(), 0)
        cols = max(1, available // (_CARD_MIN_W + _H_SPACING))
        # 列数取偶：奇数列会在最右留单张卡片、左右不对称，观感差
        if cols > 1 and cols % 2:
            cols -= 1
        for i, card in enumerate(visible):
            self._grid_add_widget(card, i // cols, i % cols)
        # 强制各列等宽：先复位旧列拉伸，再为当前所有列设相同 stretch，
        # 避免个别卡片内容 sizeHint 偏大致使列宽不一致（如长文件名、不同徽章文本）
        for col in range(max(self._grid_cols, cols)):
            self.gridLayout.setColumnStretch(col, 0)
        for col in range(cols):
            self.gridLayout.setColumnStretch(col, 1)
        self._grid_cols = cols
        self.gridLayout.activate()
        self._pin_content_height((len(visible) + cols - 1) // cols)
        self._update_count()

    def _relayout_lazy(self):
        """懒加载重排：全部条目铺占位格（滚动条高度正确），已建卡片原位回填。"""
        self._clear_grid()
        self._view = self._lazy_filter()
        available = max(self.scrollArea.viewport().width(), 0)
        cols = max(1, available // (_CARD_MIN_W + _H_SPACING))
        if cols > 1 and cols % 2:
            cols -= 1
        for i, item in enumerate(self._view):
            card = self._card_cache.get(item)
            if card is not None:
                self._grid_add_widget(card, i // cols, i % cols)
            else:
                sp = QSpacerItem(
                    _CARD_MIN_W, _ROW_H, QSizePolicy.Expanding, QSizePolicy.Fixed
                )
                self._spacer_at[item] = sp
                self.gridLayout.addItem(sp, i // cols, i % cols)
        for col in range(max(self._grid_cols, cols)):
            self.gridLayout.setColumnStretch(col, 0)
        for col in range(cols):
            self.gridLayout.setColumnStretch(col, 1)
        self._grid_cols = cols
        self.gridLayout.activate()
        self._pin_content_height((len(self._view) + cols - 1) // cols)
        self._materialize_visible()
        self._update_count()

    def _clear_grid(self):
        """摘除网格内全部 item（卡片脱离父对象待回填，占位符直接丢弃）。"""
        while self.gridLayout.count():
            item = self.gridLayout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
        self._spacer_at.clear()

    # ------------------------------------------------------------ 瀑布流入场
    def _cancel_fade_in(self):
        """中止全部淡入动画、恢复原生绘制（重建列表前调用）。

        ``_schedule_fade_in`` 会先给整批卡片挂上 opacity=0 的效果，再把
        第一张之外的卡片放进队列等节拍器。若清空队列时不卸载这些卡片的
        效果，它们会永久停在半透明（实测刷新重建后残留 7 张），滚动过去
        就能看到。队列与进行中的动画都必须逐一 restore。
        """
        self._fadeTimer.stop()
        for card in self._fade_queue:
            self._restore_fade(card)
            try:
                card._fade_cancelled = True
            except RuntimeError:
                pass
        self._fade_queue.clear()
        self._fade_scheduled = 0
        for card, anim in list(self._fade_anims.items()):
            anim.stop()
            self._restore_fade(card)
        self._fade_anims.clear()

    def _forget_fade(self, card):
        """单卡被移除时清理淡入状态；队列里的残留由节拍器跳过。"""
        card._fade_cancelled = True
        anim = self._fade_anims.pop(card, None)
        if anim is not None:
            anim.stop()
        self._restore_fade(card)

    def _restore_fade(self, card):
        """卸载透明度效果，卡片回到原生绘制（圆角 / 背景动画 / 子控件）。"""
        try:
            card.setGraphicsEffect(None)
            card._fade_effect = None
        except RuntimeError:
            pass  # 卡片已被 Qt 销毁，无需恢复

    def _schedule_fade_in(self, cards, stagger: bool = True,
                          budget: int = _FADE_MAX_CARDS):
        """把新建卡片按网格顺序排入「从少到多、由隐到显」的淡入队列。

        所有待淡入卡片在同一帧先挂 opacity=0 的效果（只改绘制、不改几何，
        实测不投递 LayoutRequest），再按节拍逐张淡入，形成瀑布流式错峰铺开。
        超过预算（默认 _FADE_MAX_CARDS）的卡片直接完全显示，避免长列表
        把动画拖到数秒；``budget`` 可由调用方放大以覆盖更大的首屏范围。
        """
        if not self.fade_in or not cards:
            return
        # 一次重建只让预算内张卡片错峰淡入：渐进填充会分多轮建卡，
        # 若每轮各放 40 张，长列表会把动画拖到数秒。滚动新物化走
        # 短淡入，不受该预算限制（每次滚动都该有呈现反馈）。
        if stagger:
            limit = max(budget - self._fade_scheduled, 0)
        else:
            limit = budget
        prepared = []
        for card in list(cards)[:limit]:
            try:
                effect = QGraphicsOpacityEffect(card)
                effect.setOpacity(0.0)
                card.setGraphicsEffect(effect)
                card._fade_effect = effect
                card._fade_cancelled = False
                prepared.append(card)
            except RuntimeError:
                continue  # 排入前卡片已被销毁
        if not prepared:
            return
        if stagger:
            self._fade_scheduled += len(prepared)
        if not stagger:
            # 滚动新物化：同批短淡入，不拖慢滚动观感
            for card in prepared:
                self._start_fade(card, _FADE_SCROLL_MS)
            return
        if self._fadeTimer.isActive() or self._fade_queue:
            # 上一批仍在错峰：本批接队尾，保持全局自上而下的出现顺序
            self._fade_queue.extend(prepared)
            return
        first, *rest = prepared
        self._start_fade(first, _FADE_DURATION_MS)
        self._fade_queue.extend(rest)
        if rest:
            self._fadeTimer.start()

    def replay_from_top(self):
        """刷新呈现（当前契约）：滚回列表顶部 + 卡片从第一张起自上而下逐张刷新。

        用户 2026-11-09 明确要求「刷新后列表从顶部开始往下刷新」，取代
        11-06 的「原地同步脉冲」契约。这里复用初次加载的错峰淡入机制
        （``_schedule_fade_in``），但顺序按网格行列、范围限定回顶部后的
        首屏：所有参与卡片同帧挂 opacity=0，再按 16ms 节拍逐张淡入，
        视觉即「从顶部开始往下刷一遍」。只改绘制，不摘挂网格、不改行高。

        空列表没有卡片可淡入，改为让空状态浮层同步脉冲一次，保证「点刷新
        必有反馈」（实测空列表曾因 ``_card_cache`` 为空而完全无反馈）。
        """
        # 回顶部放在取消动画之前：valueChanged 可能物化顶部占位格并排入
        # 短淡入，随后统一取消，避免两套动画叠加
        sb = self.scrollArea.verticalScrollBar()
        if sb.value() != 0:
            sb.setValue(0)
        self._cancel_fade_in()
        self._fade_scheduled = 0
        y1 = self.scrollArea.viewport().height()
        rows = []
        for i in range(self.gridLayout.count()):
            item = self.gridLayout.itemAt(i)
            w = item.widget() if item is not None else None
            if w is None or not w.isVisible():
                continue
            row, col, _, _ = self.gridLayout.getItemPosition(i)
            if w.y() < y1 + _ROW_H:  # 首屏 + 一行余量，向下衔接自然
                rows.append((row, col, w))
        rows.sort(key=lambda t: (t[0], t[1]))
        cards = [w for _, _, w in rows]
        if cards:
            # 视口内全部参与（默认 40 张预算在宽屏首屏可能不够）
            self._schedule_fade_in(
                cards, stagger=True, budget=max(_FADE_MAX_CARDS, len(cards))
            )
        elif self._empty_shown:
            self._pulse_fade_in([self.emptyHint])

    def replay_fade_in(self):
        """非刷新场景的原地反馈：当前可见卡片整屏同步闪一次（只改绘制）。

        「开始解密」等内部扫描会触发重建，但不应把用户视点拉回顶部，
        仍沿用 11-06 的同步脉冲；用户主动 / 自动刷新一律走
        ``replay_from_top()``。占位格没有 widget，自动跳过；几何零位移。
        """
        self._cancel_fade_in()
        self._fade_scheduled = 0
        # 卡片 y 是 scrollContent 坐标系，与滚动条 value 同一坐标系
        sb = self.scrollArea.verticalScrollBar()
        y0 = sb.value()
        y1 = y0 + self.scrollArea.viewport().height()
        in_view = []
        for i in range(self.gridLayout.count()):
            item = self.gridLayout.itemAt(i)
            w = item.widget() if item is not None else None
            if w is None or not w.isVisible():
                continue
            top = w.y()
            if top < y1 and top + w.height() > y0:
                in_view.append(w)
        self._pulse_fade_in(in_view)

    def _pulse_fade_in(self, cards):
        """整屏同步脉冲：所有卡片同时从 _REPLAY_MIN_OPACITY 回到 1.0。

        与 ``_schedule_fade_in`` 的瀑布流刻意分开：不走错峰队列、不吃
        40 张预算、不排视口外卡片。动画对象仍登记进 ``_fade_anims``，
        由 ``_finish_fade`` 卸载效果、``_cancel_fade_in`` 在重建前统一
        收尾，避免动画回调触碰已删除的卡片。
        """
        for card in cards:
            try:
                effect = QGraphicsOpacityEffect(card)
                effect.setOpacity(_REPLAY_MIN_OPACITY)
                card.setGraphicsEffect(effect)
                card._fade_effect = effect
                card._fade_cancelled = False
            except RuntimeError:
                continue  # 排入前卡片已被销毁
            anim = QPropertyAnimation(effect, b"opacity", card)
            anim.setDuration(_REPLAY_PULSE_MS)
            anim.setStartValue(_REPLAY_MIN_OPACITY)
            anim.setEndValue(1.0)
            anim.setEasingCurve(QEasingCurve.OutCubic)
            self._fade_anims[card] = anim
            anim.finished.connect(lambda c=card, a=anim: self._finish_fade(c, a))
            anim.start()

    def _start_fade(self, card, duration: int):
        """启动单卡淡入；结束后卸载效果（含动画对象），不留常驻开销。"""
        effect = getattr(card, "_fade_effect", None)
        if effect is None:
            return
        anim = QPropertyAnimation(effect, b"opacity", card)
        anim.setDuration(duration)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        self._fade_anims[card] = anim
        anim.finished.connect(lambda c=card, a=anim: self._finish_fade(c, a))
        anim.start()

    def _finish_fade(self, card, anim):
        if self._fade_anims.get(card) is not anim:
            return  # 已被 _cancel_fade_in / _forget_fade 接管
        self._fade_anims.pop(card, None)
        self._restore_fade(card)
        anim.deleteLater()

    def _fade_tick(self):
        """节拍器：每次放出一张卡片淡入，队列空即停。"""
        while self._fade_queue:
            card = self._fade_queue.popleft()
            if getattr(card, "_fade_cancelled", False):
                continue
            self._start_fade(card, _FADE_DURATION_MS)
            break
        if not self._fade_queue:
            self._fadeTimer.stop()

    # ------------------------------------------------------------ 懒加载物化
    def _on_lazy_scroll(self, _value):
        """滚动条移动 → 物化视口内占位格（即时页为空操作）。"""
        if self.lazy_fill:
            self._materialize_visible(stagger=False)

    def _materialize_visible(self, stagger: bool = True):
        """把视口覆盖行（上下各预载 _LAZY_PRELOAD_ROWS 行）的占位格替换为真实卡片。

        未进过视口的条目始终保持占位格——千级文件也只维护几十张真实卡片，
        内存与构建开销都只与可见范围相关。刷新重建期间由
        ``_suppress_materialize_fade`` 关掉入场动画：几何收敛照做，改由
        ``replay_fade_in`` 统一做整屏同步脉冲（避免重建后的卡片又自上而下
        铺开一遍）。标志必须覆盖**全部**物化入口——``_relayout_lazy`` 内部
        也会调用本方法，只改 ``_replace_cards`` 里的显式调用会漏掉它。
        """
        if not self._view or not self._grid_cols:
            return
        cols = self._grid_cols
        stride = _ROW_H + _V_SPACING
        y0 = self.scrollArea.verticalScrollBar().value()
        y1 = y0 + self.scrollArea.viewport().height()
        first_row = max(int(y0 // stride) - _LAZY_PRELOAD_ROWS, 0)
        last_row = min(
            int(y1 // stride) + _LAZY_PRELOAD_ROWS,
            (len(self._view) - 1) // cols,
        )
        changed = False
        new_cards = []
        for pos in range(first_row * cols, (last_row + 1) * cols):
            if pos >= len(self._view):
                break
            item = self._view[pos]
            if item in self._card_cache:
                continue
            sp = self._spacer_at.pop(item, None)
            if sp is not None:
                self.gridLayout.removeItem(sp)
            card = self._make_card(item)
            card._lazy_item = item  # 反向映射：移除时由卡片找回条目
            self._card_cache[item] = card
            self._grid_add_widget(card, pos // cols, pos % cols)
            new_cards.append((pos, card))
            changed = True
        if changed:
            # 动态 addWidget 会把布局重新置脏：占位格状态下算出的行高是
            # 临时值（实测 72），卡片填入后的真实行高是 74。若此时不收敛，
            # 之后任意一次 Qt 布局补算（例如刷新时 countLabel.setText 引发的
            # LayoutRequest）都会把整片卡片按新行高重排，越靠下累积位移越大
            # —— 这就是「点刷新后卡片上下晃动」。物化完立即 activate，
            # 保证任意时刻网格几何都已是最终值、后续重排为零位移。
            self.gridLayout.activate()
            if not self._suppress_materialize_fade:
                # 几何收敛后再挂透明度效果：新建卡片错峰淡入。
                # 顺序以「当前可见区域」为起点（区内仍自上而下），视口外上下
                # 各 2 行的预载卡片排到最后——否则滚到中部刷新时，用户会先等
                # 一批看不见的卡片淡完，可见区域才迟迟开始铺开。
                in_view, preload = [], []
                for pos, card in new_cards:
                    row_top = (pos // cols) * stride
                    (in_view if y0 <= row_top <= y1 else preload).append(card)
                self._schedule_fade_in(in_view + preload, stagger=stagger)

    # ------------------------------------------------------------ 卡片管理
    def pending_items(self) -> list:
        """渐进填充中尚未建卡的在途条目（供子类做去重时合并，避免访问内部状态）。"""
        return list(self._pending_paths)

    def _add_cards(self, cards, relayout: bool = True):
        """追加一批已构建好的卡片。"""
        if not cards:
            return
        self._cards.extend(cards)
        # 追加是一次独立的呈现事件：重置入场预算，让新增卡片同样淡入
        self._fade_scheduled = 0
        self._schedule_fade_in(cards)
        if relayout:
            self._relayout()

    def _replace_cards(self, paths, progressive: bool = False,
                       refresh: bool = False):
        """用一组条目重建卡片列表（``progressive=True`` 时分批渐进填充）。

        条目内容对基类不透明：直接传给子类 ``_make_card``——可以是路径
        字符串，也可以是携带预取元数据的元组（避免建卡时再访问磁盘）。
        ``refresh=True`` 表示由「刷新」触发：重建后回到列表顶部并自上而下
        逐张刷新（当前呈现契约）；内部扫描触发的重建保持原视点与原地反馈。
        """
        # 旧列表即将销毁：先中止其淡入动画，避免动画回调触碰已删除卡片
        self._cancel_fade_in()
        self._fill_refresh = refresh
        # 连点刷新：上一轮渐进填充可能仍冻结着绘制，先收尾再开始新一轮
        # （都在同一同步段内完成，不会产生可见中间帧）
        self._unfreeze_fill(replay_fade=False)
        if self.lazy_fill:
            # 懒加载路径：只记条目 + 铺占位格，真实卡片滚动到视口才创建。
            #
            # 重建必须「原子化」：清空网格会让滚动条最大值骤降为 0，其
            # valueChanged 会用尚未更新的 _view 误物化卡片；滚动条显隐又
            # 触发视口 Resize → 40ms 后二次全量重排。两者叠加就是刷新时
            # 卡片上下晃动。这里阻断滚动条信号、关闭绘制、隐藏旧卡片，
            # 结束后恢复滚动位置并取消期间排队的防抖重排。
            sb = self.scrollArea.verticalScrollBar()
            saved_value = sb.value()
            # 首次进入页面（缓存为空、非刷新）保留瀑布流入场；刷新重建
            # 一律不排物化入场，改由 replay_from_top() 从顶部统一铺开，
            # 避免两套淡入叠加成不可控的逐行刷新。
            had_cards = bool(self._card_cache)
            self._suppress_materialize_fade = had_cards or refresh
            blocker = QSignalBlocker(sb)
            self.scrollArea.setUpdatesEnabled(False)
            try:
                self._pending_paths = deque()
                for c in self._card_cache.values():
                    # 先隐藏再 deleteLater：可见且被摘掉父控件的 QWidget
                    # 会短暂成为顶层窗口，在下一帧闪现成「跳出的卡片」
                    c.hide()
                    c.deleteLater()
                self._card_cache.clear()
                self._clear_grid()
                self._items = list(paths)
                self._filling = True  # 铺格完成前抑制空提示
                self._relayout()
                self._filling = False
                self._update_count()
                # 刷新回顶部；内部重建恢复原滚动位置（超出时自动钳制）。
                # 信号被阻断，故由下方显式按新视口物化一次
                sb.setValue(0 if refresh else saved_value)
                self._materialize_visible()
            finally:
                self._suppress_materialize_fade = False
                blocker.unblock()
                self.scrollArea.setUpdatesEnabled(True)
            # 重建期间因滚动条显隐排队的 resize 重排已无必要（列数按最终
            # 视口宽度算过），取消它以免 40ms 后再摘挂一次全部卡片
            self._relayoutTimer.stop()
            if refresh:
                # 用户 / 自动刷新：回顶部 + 自上而下逐张刷新（当前契约）
                self.replay_from_top()
            elif had_cards:
                # 非刷新的内部重建：原地脉冲，不拉走视点
                self.replay_fade_in()
            return
        self._pending_paths = deque()  # 取消在途的分批填充，避免旧批次串扰新列表
        # 区分「启动首扫」与「已有列表的刷新重建」：只有后者才需要隐藏
        # 中间态，启动时的流式入场（窗口先出、卡片渐次出现）应保留
        had_cards = bool(self._cards)
        for c in self._cards:
            # 同上：脱离布局前先隐藏，避免 deleteLater 生效前闪现
            c.hide()
            c.deleteLater()
        self._cards.clear()
        if progressive:
            # 填充期间抑制空提示：避免"清空→首批建完"之间闪现居中的空状态
            self._filling = True
            self._fill_restore_value = self.scrollArea.verticalScrollBar().value()
            if had_cards:
                # 清空网格后 range 骤降、value 被 clamp 到 0，随后卡片从
                # 第 0 张逐批补格——不受控的中间态会变成一帧一帧的「从
                # 顶部涌现」。冻结整页绘制让中间态完全不可见：完成后一次性
                # 解冻，再由 replay_from_top() 统一呈现受控的「回顶部 +
                # 自上而下逐张刷新」（刷新）或原地脉冲（内部重建）。
                # 布局计算 / resize 不受 updatesEnabled 影响，填充照常跑。
                # 空列表没有「逐批补格」的中间态，冻结毫无意义且会漏掉
                # 完成分支（_fill_next_chunk 直接早退），故不冻结
                if paths:
                    self._fill_frozen = True
                    self.setUpdatesEnabled(False)
        self._relayout()  # 先空排一次，确定当前列数供分批补格使用
        if progressive:
            self._pending_paths = deque(paths)
            self._fill_next_chunk()
        else:
            new_cards = [self._make_card(p) for p in paths]
            self._cards.extend(new_cards)
            self._filling = False
            # 先挂透明度再入网格，避免首帧闪现完整卡片
            self._schedule_fade_in(new_cards)
            self._relayout()
            if refresh:
                self.replay_from_top()

    def _unfreeze_fill(self, replay_fade: bool = True):
        """渐进重建收尾：一次性恢复绘制，可选让可见区整屏闪一次。

        集中处理是为了让「正常完成」「空列表早退」「连点刷新收尾」三条
        路径都能可靠解冻——任何一条漏掉都会把页面永久留在不绘制状态。
        """
        if not self._fill_frozen:
            return
        self._fill_frozen = False
        self.setUpdatesEnabled(True)
        self.update()
        if replay_fade:
            if self._fill_refresh:
                self.replay_from_top()
            else:
                self.replay_fade_in()

    def _fill_next_chunk(self):
        """时间片分批建卡：单帧构建满 _FILL_BUDGET_MS 毫秒即让出事件循环。

        页面先出、卡片渐进填充不假死；时间切片让每帧开销可控且稳定，
        填充期间滚动 / 悬停等交互不掉帧。
        """
        if not self._pending_paths:
            # 队列清空：填充结束，恢复空提示判定。
            # 兜底解冻：走完最后一批的链会先进 else 完成分支解冻，此处
            # 对连点刷新残留的 timer 是 no-op；而「空列表 / 队列被外部
            # 清空」没有完成分支，必须在这里收尾，否则页面会永久停在
            # 不绘制状态（实测清空目录后点刷新即触发）。
            self._filling = False
            self._update_count()
            self._unfreeze_fill(replay_fade=False)
            # 空列表刷新没有「最后一批」完成分支，反馈在这里补一次
            # （replay_from_top 会让空状态浮层同步脉冲，按钮不会像失灵）
            if self._fill_refresh and not self._cards:
                self.replay_from_top()
            return
        start = len(self._cards)
        t0 = time.monotonic()
        while self._pending_paths:
            self._cards.append(self._make_card(self._pending_paths.popleft()))
            # time.monotonic() 单位为秒，预算常量以毫秒定义，必须换算
            if time.monotonic() - t0 >= _FILL_BUDGET_MS / 1000:
                break
        # 只把本时间片新增卡片补进网格末尾（列数未变时与全量重排等价，避免 O(n²) 重排）
        cols = self._grid_cols or 1
        chunk = self._cards[start:]
        # 本批卡片接在上批淡入队列之后，保证整页自上而下的出现顺序。
        # 冻结重建期间不排淡入：动画会在不可见状态下跑完，白费；
        # 解冻后由 _unfreeze_fill() 按 _fill_refresh 选择「回顶部 +
        # 自上而下逐张刷新」或原地脉冲。
        if not self._fill_frozen:
            self._schedule_fade_in(chunk)
        for i, card in enumerate(chunk):
            self._grid_add_widget(card, (start + i) // cols, (start + i) % cols)
        # 每批补格后立即钉住内容最小高度：QScrollArea 的异步 resize 滞后于
        # 网格增长，追赶期间布局会在不够的高度内激活、把行高压扁（卡片叠压）
        self._pin_content_height((len(self._cards) + cols - 1) // cols)
        self._update_count()
        if self._pending_paths:
            QTimer.singleShot(0, self._fill_next_chunk)
        else:
            # 全部填充完成：解除空提示抑制（目录为空时正确显示空状态）
            self._filling = False
            self._update_count()
            # 刷新回到顶部；内部重建把刷新前的滚动位置找回来（超出时钳制）
            restore = getattr(self, "_fill_restore_value", None)
            if restore is not None:
                self._fill_restore_value = None
                self.scrollArea.verticalScrollBar().setValue(
                    0 if self._fill_refresh else restore
                )
            # 一次性解冻：刷新由 replay_from_top() 呈现「回顶部 + 自上而下
            # 逐张刷新」；内部重建保持原视点并原地同步闪一次
            self._unfreeze_fill()

    def _remove_cards(self, cards):
        """批量移除卡片并重排一次。"""
        if self.lazy_fill:
            removed_items = []
            for c in cards:
                self._forget_fade(c)
                item = getattr(c, "_lazy_item", None)
                if item is None or item not in self._items:
                    continue
                self._card_cache.pop(item, None)
                self._on_card_removed(c)
                c.hide()  # 脱离布局前隐藏，避免 deleteLater 生效前闪现
                c.deleteLater()
                removed_items.append(item)
            if not removed_items:
                return
            for it in removed_items:
                try:
                    self._items.remove(it)
                except ValueError:
                    pass
            self._relayout()
            return
        cards = [c for c in cards if c in self._cards]
        if not cards:
            return
        for c in cards:
            self._forget_fade(c)
            self._cards.remove(c)
            self._on_card_removed(c)
            c.hide()
            c.deleteLater()
        self._relayout()

    def _remove_card(self, card):
        """移除单个卡片并重排。"""
        self._remove_cards([card])

    def _clear_cards(self):
        """清空全部卡片并重排（逐卡触发 ``_on_card_removed`` 联动钩子）。"""
        self._remove_cards(list(self._cards))

    # ------------------------------------------------------------ 空状态浮层
    def _set_empty_visible(self, visible: bool):
        """显示/隐藏空状态提示浮层（显示前同步几何并置顶）。

        渐进填充进行中强制隐藏：页面刚打开、首批卡片尚未建完时，
        会短暂出现"0 个文件"的假象，闪现居中空提示后又消失。
        """
        if self._filling:
            visible = False
        if visible == self._empty_shown:
            # 状态未变时直接返回：重复 setVisible / setText 会向 Qt 投递
            # LayoutRequest，进而触发整页布局补算（滚动网格可能被重排）
            return
        self._empty_shown = visible
        if visible:
            self._sync_overlay_geometry()
            self.emptyHint.raise_()
        self.emptyHint.setVisible(visible)

    def _sync_overlay_geometry(self):
        # 浮层几何跟随滚动区视口（geometry() 已是 scrollArea 坐标系）
        self.emptyHint.setGeometry(self.scrollArea.viewport().geometry())
