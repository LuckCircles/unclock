# coding: utf-8
"""FlowLayout 扩展：强制偶数列 + 安全移除（含占位格）。

供 ``GridCardContainer`` 替换 ``QGridLayout`` 使用，满足项目硬约束：

- 列数恒为偶数（2/4/6…）—— ``AdaptiveFlowLayout`` 原生不强制偶；
- 卡片宽度按行均摊拉伸铺满整行，两侧不留空白（继承 AdaptiveFlowLayout）；
- ``needAni`` 固定关闭：原生每卡一个 ``QPropertyAnimation`` 并行位移，是
  项目曾为性能优化掉的模式（全屏切换顿挫），改由基类自写的单动画 FLIP 接管；
- 覆写 ``takeAt(index)`` 安全移除任意 item：``FlowLayout.takeAt`` 会调用
  ``item.widget().property('flowAni')``，对 ``QSpacerItem``（``widget()`` 为
  None）触发 ``AttributeError``，且只返回 ``.widget()`` 丢掉 item 本身——
  PySide6/Qt 内部调用 ``takeAt`` 时期望拿到 ``QLayoutItem``，拿到 widget 会
  RuntimeWarning 并导致条目漏挂（实测重排后 count 丢失）。这里返回 item 本身，
  占位格也可安全回收进池复用。

列数计算与 ``GridCardContainer`` 基类共用模块级 ``calc_cards_per_row``
（同公式、同取偶规则），保证基类以为的列数 == 布局实际摆出的列数。
"""
from PySide6.QtCore import QPoint, QRect, QSize
from PySide6.QtWidgets import QLayoutItem, QWidgetItem

from qfluentwidgets import AdaptiveFlowLayout


def calc_cards_per_row(available_width: int, card_min_width: int,
                       space_x: int) -> int:
    """计算每行卡片数：向下取偶、最小 2。

    ``EvenFlowLayout._doLayout`` 与 ``GridCardContainer`` 基类共用同一公式，
    保证基类以为的列数 == 布局实际摆出的列数——懒加载物化/回收的行计算、
    FLIP 位移都依赖二者严格一致，绝不能各写一份产生偏差。
    """
    if card_min_width + space_x <= 0:
        return 2
    raw = (available_width + space_x) // (card_min_width + space_x)
    cols = raw if raw % 2 == 0 else max(raw - 1, 2)
    return max(cols, 2)


class EvenFlowLayout(AdaptiveFlowLayout):
    """AdaptiveFlowLayout 的偶数列变体 + 占位格安全移除。"""

    def __init__(self, parent=None, card_min_width: int = 260):
        # needAni=False：禁用每卡位移动画；isTight=False：隐藏卡片仍占位，
        # 与基类「回收时 hide 但保留几何位」的策略一致
        super().__init__(parent, needAni=False, isTight=False)
        # 与基类 _CARD_MIN_W 对齐，保证列数公式一致
        self._widgetMinimumWidth = card_min_width
        # 几何缓存：懒加载物化/回收是占位格↔卡片的同索引原位互换，两者
        # 同高（64）同宽，目标矩形完全一致，无需每次都全量 _doLayout。
        # 缓存最近一次真实布局（move=True）的 rect / 高度 / item 数，
        # rect 与数量均未变且未被标记脏时直接短路返回，把滚动物化从
        # O(n) 降到 O(k)（k=变化卡片数）。heightForWidth 纯查询单独缓存。
        self._geo_dirty = True
        self._last_layout_rect = QRect()
        self._last_height = 0
        self._last_count = -1
        self._last_hfw_width = -1
        self._last_hfw_height = 0

    def invalidate(self):
        """标记几何脏：下次 _doLayout 必须全量重算（数量变化/外部失效）。"""
        self._geo_dirty = True
        super().invalidate()

    def insertWidget(self, index, w):
        """按扁平索引插入控件。

        覆写 FlowLayout.insertWidget：原版无条件调用 ``addChildWidget(w)``，
        当 ``w`` 已是本布局父容器（scrollContent）的子控件——即重排时回填的
        缓存卡片、或回收后复用的卡片——Qt 内部会检测到它曾属本布局并先
        ``takeAt`` 摘除，恰好摘掉刚 ``insertItem`` 进去的项，导致卡片丢失
        （count 减少）。这里对已在正确父容器下的控件跳过 ``addChildWidget``
        （reparent 与事件过滤器都已就位）；首次插入的新卡（父容器不同）仍
        走 ``addChildWidget`` 完成 reparent。
        """
        self.insertItem(index, QWidgetItem(w))
        if w.parentWidget() is not self.parentWidget():
            self.addChildWidget(w)
        self._onWidgetAdded(w, index)

    def _doLayout(self, rect: QRect, move: bool):
        """复制父类几何算法（cardsPerRow 取偶），并加几何缓存短路。

        懒加载滚动物化是占位格↔卡片的同索引原位互换：两者同高（64）同宽，
        目标矩形完全一致，全量重算纯属浪费。这里缓存最近一次真实布局
        （move=True）的 rect / 高度 / item 数——rect 与数量均未变、且未被
        标记脏时直接短路返回，把滚动物化的 O(n) 全量遍历降到 O(1) 返回。
        heightForWidth 是纯查询（move=False），不修改 widget 几何，单独
        缓存宽度→高度，避免 QScrollArea 重复查询时反复遍历全部 item。
        """
        n = len(self._items)
        if move:
            # 真实布局：rect 未变、未脏、item 数未变 → 几何已应用，直接复用
            if (not self._geo_dirty and rect == self._last_layout_rect
                    and n == self._last_count):
                return self._last_height
            total = self._compute_layout(rect, move=True)
            self._last_layout_rect = QRect(rect)
            self._last_count = n
            self._last_height = total
            self._geo_dirty = False
            # 真实布局后高度即权威值，heightForWidth 同宽查询直接复用
            self._last_hfw_width = rect.width()
            self._last_hfw_height = total
            return total
        # heightForWidth 纯查询：宽度未变、未脏、数量未变 → 复用
        if (not self._geo_dirty and rect.width() == self._last_hfw_width
                and n == self._last_count):
            return self._last_hfw_height
        total = self._compute_layout(rect, move=False)
        self._last_hfw_width = rect.width()
        self._last_hfw_height = total
        return total

    def _compute_layout(self, rect: QRect, move: bool):
        """实际几何计算（与父类逐行等价，仅 cardsPerRow 取偶 + 末列吃余像素）。"""
        aniRestart = False
        margin = self.contentsMargins()
        spaceX = self.horizontalSpacing()
        spaceY = self.verticalSpacing()

        availableWidth = rect.width() - margin.left() - margin.right()

        # 列数公式与基类 GridCardContainer 共用 calc_cards_per_row，避免分叉
        cardsPerRow = calc_cards_per_row(
            availableWidth, self._widgetMinimumWidth, spaceX
        )

        if cardsPerRow > 1:
            cardWidth = (availableWidth - (cardsPerRow - 1) * spaceX) // cardsPerRow
        else:
            cardWidth = availableWidth

        if self._widgetMaximumWidth is not None and cardWidth > self._widgetMaximumWidth:
            cardWidth = self._widgetMaximumWidth

        x = rect.x() + margin.left()
        y = rect.y() + margin.top()
        rowHeight = 0
        colIndex = 0

        for i, item in enumerate(self._items):
            if item.widget() and not item.widget().isVisible() and self.isTight:
                continue

            nextX = x + cardWidth + spaceX

            if colIndex >= cardsPerRow and cardsPerRow > 0:
                x = rect.x() + margin.left()
                y = y + rowHeight + spaceY
                nextX = x + cardWidth + spaceX
                rowHeight = 0
                colIndex = 0

            if move:
                w_card = cardWidth
                if colIndex == cardsPerRow - 1:
                    # 最后一列吃掉整数除法的余数像素，保证整行精确铺满、右侧
                    # 不留缝隙（QGridLayout 的 setColumnStretch 原生铺满，
                    # AdaptiveFlowLayout 用 // 整除会剩 1~几 px 空白）
                    w_card = rect.x() + rect.width() - margin.right() - x
                targetSize = QSize(w_card, item.sizeHint().height())
                target = QRect(QPoint(x, y), targetSize)
                if not self.needAni:
                    item.setGeometry(target)
                elif i < len(self._anis) and target != self._anis[i].endValue():
                    self._anis[i].stop()
                    self._anis[i].setEndValue(target)
                    aniRestart = True

            x = nextX
            rowHeight = max(rowHeight, item.sizeHint().height())
            colIndex += 1

        if self.needAni and aniRestart:
            self._aniGroup.stop()
            self._aniGroup.start()

        return y + rowHeight + margin.bottom() - rect.y()

    def replace_item(self, pos: int, new_item: QLayoutItem) -> QLayoutItem:
        """原位替换 pos 处的 item，复用其几何，不触发全量重排。返回旧 item。

        懒加载物化（占位格→卡片）与回收（卡片→占位格）是同索引互换：两者
        同高同宽，目标矩形完全一致。直接替换 ``_items[pos]`` 并把新 item
        设到旧几何，跳过 invalidate——避免每次滚动物化都走 O(n) 全量
        ``_doLayout``（实测 1500 项单次 activate 约 21ms，超出一帧预算）。
        仅当旧几何无效（尚未布局过，如初始化铺格前）时才标记脏，回退到
        下次全量计算。新 widget 若父容器不对会先 reparent 到布局父容器。
        """
        old = self._items[pos]
        geo = old.geometry()
        w = new_item.widget()
        if w is not None and w.parentWidget() is not self.parentWidget():
            w.setParent(self.parentWidget())
        self._items[pos] = new_item
        if geo.width() > 0 and geo.height() > 0:
            new_item.setGeometry(geo)
        else:
            self._geo_dirty = True
        return old

    def takeAt(self, index: int):
        """安全移除并返回索引处的 QLayoutItem（含 QSpacerItem）。

        覆写 ``FlowLayout.takeAt``：原版对占位格崩溃（``widget()`` 为 None 时
        访问 ``.property('flowAni')``），且返回 ``.widget()`` 而非 item 本身——
        Qt 内部调用 ``takeAt`` 时期望 ``QLayoutItem``，拿到 widget 会触发
        RuntimeWarning 并漏挂条目。这里返回 item 本身，``needAni=False`` 故无
        动画需清理（仍做兼容清理以防未来开启）。
        """
        if 0 <= index < len(self._items):
            item = self._items.pop(index)
            w = item.widget()
            if w is not None:
                ani = w.property('flowAni')
                if ani:
                    try:
                        self._anis.remove(ani)
                        self._aniGroup.removeAnimation(ani)
                        ani.deleteLater()
                    except (ValueError, RuntimeError):
                        pass
            return item
        return None
