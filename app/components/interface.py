# coding: utf-8
"""页面基类 —— 固定头部（stickyLayout）+ 滚动内容（vLayout）双区结构。

不需要置顶内容的页面（首页 / 设置 / 日志）只用 ``vLayout``，布局与旧版一致；
需要工具栏置顶的页面（任务 / 已解密）把工具栏放进 ``stickyLayout``、列表放进
``vLayout``——垂直滚动只发生在内容区，置顶工具栏始终可见、不随卡片下拉。

滚动区**视口**尺寸变化（窗口缩放 / 滚动条显隐）经事件过滤器通知子类
（``_on_viewport_resized``）：页面 resizeEvent 触发时内嵌滚动区尚未被布局
刷新，视口宽度会滞后一帧，按视口宽度算网格列数的页面必须走此钩子。
"""

from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import QVBoxLayout, QWidget
from qfluentwidgets import ScrollArea


class Interface(QWidget):
    """所有页面的基类：固定头部 + 滚动内容双区骨架。"""

    def __init__(self, object_name: str, parent=None):
        super().__init__(parent)
        self._object_name = object_name

        # 页面级布局：固定头部 + 滚动内容（零边距，边距由两区自行管理）
        self.pageLayout = QVBoxLayout(self)
        self.pageLayout.setContentsMargins(0, 0, 0, 0)
        self.pageLayout.setSpacing(0)

        # 固定头部区：不随内容滚动；无内容时零高度零边距，与旧版单区一致
        self.stickyLayout = QVBoxLayout()
        self.stickyLayout.setContentsMargins(0, 0, 0, 0)
        self.stickyLayout.setSpacing(0)
        self.pageLayout.addLayout(self.stickyLayout)

        # 滚动内容区（旧版 Interface 自身即此 ScrollArea，现内嵌为子区）
        self.scrollArea = ScrollArea(self)
        # 视口尺寸变化 → 通知子类重排（此时视口已是新宽度，比页面 resizeEvent 准）
        self.scrollArea.viewport().installEventFilter(self)
        self.view = QWidget()
        self.vLayout = QVBoxLayout(self.view)
        self.vLayout.setContentsMargins(30, 30, 30, 30)
        self.vLayout.setSpacing(20)
        self.vLayout.setAlignment(Qt.AlignTop)
        self.scrollArea.setWidget(self.view)
        self.scrollArea.setWidgetResizable(True)
        # 让滚动区背景透明，融入 MSFluentWindow 的主题背景色，
        # 避免内容区出现与窗口不一致的白色/深色分层色块
        self.scrollArea.enableTransparentBackground()
        self.pageLayout.addWidget(self.scrollArea, 1)

        self.setObjectName(object_name)

    def eventFilter(self, obj, event):
        # 滚动区视口尺寸变化（窗口缩放 / 滚动条显隐）→ 通知子类重排
        if obj is self.scrollArea.viewport() and event.type() == QEvent.Resize:
            self._on_viewport_resized()
        return super().eventFilter(obj, event)

    def _on_viewport_resized(self):
        """视口尺寸变化钩子——需要按宽度重排网格的页面重写此方法。"""
