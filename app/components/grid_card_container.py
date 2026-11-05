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
"""

from collections import deque
import time

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtWidgets import (
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


class GridCardContainer(QWidget):
    """固定工具栏 + 滚动卡片网格的页面骨架（消除两页约 60% 的重复代码）。"""

    # 懒加载开关：True 时仅创建视口内可见卡片（大数据量页面开启）
    lazy_fill = False

    def __init__(self, object_name: str, parent=None):
        super().__init__(parent)
        self._object_name = object_name
        self._cards = []
        self._grid_cols = 0
        self._pending_paths = deque()  # 分批建卡的在途路径队列
        self._filling = False     # 渐进填充进行中：抑制空状态提示闪现

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
            self.gridLayout.addWidget(card, i // cols, i % cols)
        # 强制各列等宽：先复位旧列拉伸，再为当前所有列设相同 stretch，
        # 避免个别卡片内容 sizeHint 偏大致使列宽不一致（如长文件名、不同徽章文本）
        for col in range(max(self._grid_cols, cols)):
            self.gridLayout.setColumnStretch(col, 0)
        for col in range(cols):
            self.gridLayout.setColumnStretch(col, 1)
        self._grid_cols = cols
        self.gridLayout.activate()
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
                self.gridLayout.addWidget(card, i // cols, i % cols)
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

    # ------------------------------------------------------------ 懒加载物化
    def _on_lazy_scroll(self, _value):
        """滚动条移动 → 物化视口内占位格（即时页为空操作）。"""
        if self.lazy_fill:
            self._materialize_visible()

    def _materialize_visible(self):
        """把视口覆盖行（上下各预载 _LAZY_PRELOAD_ROWS 行）的占位格替换为真实卡片。

        未进过视口的条目始终保持占位格——千级文件也只维护几十张真实卡片，
        内存与构建开销都只与可见范围相关。
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
            self.gridLayout.addWidget(card, pos // cols, pos % cols)

    # ------------------------------------------------------------ 卡片管理
    def _add_cards(self, cards, relayout: bool = True):
        """追加一批已构建好的卡片。"""
        if not cards:
            return
        self._cards.extend(cards)
        if relayout:
            self._relayout()

    def _replace_cards(self, paths, progressive: bool = False):
        """用一组条目重建卡片列表（``progressive=True`` 时分批渐进填充）。

        条目内容对基类不透明：直接传给子类 ``_make_card``——可以是路径
        字符串，也可以是携带预取元数据的元组（避免建卡时再访问磁盘）。
        """
        if self.lazy_fill:
            # 懒加载路径：只记条目 + 铺占位格，真实卡片滚动到视口才创建——
            # 千级文件也只建首屏几十张卡，扫描回包不再批量建卡
            self._pending_paths = deque()
            self._clear_grid()
            for c in self._card_cache.values():
                c.deleteLater()
            self._card_cache.clear()
            self._items = list(paths)
            self._filling = True  # 与其他路径一致：铺格完成前抑制空提示
            self._relayout()
            self._filling = False
            self._update_count()
            return
        self._pending_paths = deque()  # 取消在途的分批填充，避免旧批次串扰新列表
        for c in self._cards:
            c.deleteLater()
        self._cards.clear()
        if progressive:
            # 填充期间抑制空提示：避免"清空→首批建完"之间闪现居中的空状态
            self._filling = True
        self._relayout()  # 先空排一次，确定当前列数供分批补格使用
        if progressive:
            self._pending_paths = deque(paths)
            self._fill_next_chunk()
        else:
            for p in paths:
                self._cards.append(self._make_card(p))
            self._filling = False
            self._relayout()

    def _fill_next_chunk(self):
        """时间片分批建卡：单帧构建满 _FILL_BUDGET_MS 毫秒即让出事件循环。

        页面先出、卡片渐进填充不假死；时间切片让每帧开销可控且稳定，
        填充期间滚动 / 悬停等交互不掉帧。
        """
        if not self._pending_paths:
            # 队列清空：填充结束，恢复空提示判定
            self._filling = False
            self._update_count()
            return
        start = len(self._cards)
        t0 = time.monotonic()
        while self._pending_paths:
            self._cards.append(self._make_card(self._pending_paths.popleft()))
            if time.monotonic() - t0 >= _FILL_BUDGET_MS:
                break
        # 只把本时间片新增卡片补进网格末尾（列数未变时与全量重排等价，避免 O(n²) 重排）
        cols = self._grid_cols or 1
        for i, card in enumerate(self._cards[start:]):
            self.gridLayout.addWidget(card, (start + i) // cols, (start + i) % cols)
        self._update_count()
        if self._pending_paths:
            QTimer.singleShot(0, self._fill_next_chunk)
        else:
            # 全部填充完成：解除空提示抑制（目录为空时正确显示空状态）
            self._filling = False
            self._update_count()

    def _remove_cards(self, cards):
        """批量移除卡片并重排一次。"""
        if self.lazy_fill:
            removed_items = []
            for c in cards:
                item = getattr(c, "_lazy_item", None)
                if item is None or item not in self._items:
                    continue
                self._card_cache.pop(item, None)
                self._on_card_removed(c)
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
            self._cards.remove(c)
            self._on_card_removed(c)
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
        if visible:
            self._sync_overlay_geometry()
            self.emptyHint.raise_()
        self.emptyHint.setVisible(visible)

    def _sync_overlay_geometry(self):
        # 浮层几何跟随滚动区视口（geometry() 已是 scrollArea 坐标系）
        self.emptyHint.setGeometry(self.scrollArea.viewport().geometry())
