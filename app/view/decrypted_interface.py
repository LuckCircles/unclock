# coding: utf-8
"""已解密文件页面 —— 卡片网格展示输出目录中已解密的文件。

支持：顶部搜索栏快速过滤、右键卡片播放 / 删除文件（删除带确认）、刷新 / 打开目录。
"""

import os

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QVBoxLayout
from qfluentwidgets import (
    Action,
    CaptionLabel,
    CardWidget,
    FluentIcon,
    MessageBox,
    RoundMenu,
    SearchLineEdit,
    TransparentPushButton,
)

from ..common.config import cfg
from ..common.logger import logger
from ..common.signal_bus import signalBus
from ..common.utils import is_supported_file
from ..components.empty_status import EmptyStatusWidget
from ..components.interface import Interface
from ..components.task_card import TaskCard

# 网格布局参数：卡片最小宽 + 水平间距，用于计算列数
_CARD_MIN_W = 300
_H_SPACING = 12


class DecryptedInterface(Interface):
    """已解密文件管理页面（卡片式，仿任务管理网格均分 + 贴顶排布）。"""

    def __init__(self, parent=None):
        super().__init__("DecryptedInterface", parent)
        self._cards: list[TaskCard] = []
        self._grid_cols = 0
        self._filter = ""
        self._empty_msg = "输出目录暂无已解密文件"

        # 顶部工具栏卡片：计数 + 搜索 + 刷新 / 打开目录
        self.toolbarCard = CardWidget(self)
        self.toolbarLayout = QHBoxLayout(self.toolbarCard)
        self.toolbarLayout.setContentsMargins(15, 12, 15, 12)
        self.toolbarLayout.setSpacing(10)

        self.countLabel = CaptionLabel("0 个已解密文件", self)
        self.searchEdit = SearchLineEdit(self)
        self.searchEdit.setPlaceholderText("搜索已解密文件")
        self.searchEdit.setFixedWidth(240)
        self.btnRefresh = TransparentPushButton(FluentIcon.SYNC, "刷新列表", self)
        self.btnOpenDir = TransparentPushButton(FluentIcon.FOLDER, "打开目录", self)

        self.toolbarLayout.addWidget(self.countLabel)
        self.toolbarLayout.addStretch(1)
        self.toolbarLayout.addWidget(self.searchEdit)
        self.toolbarLayout.addWidget(self.btnRefresh)
        self.toolbarLayout.addWidget(self.btnOpenDir)

        self.vLayout.addWidget(self.toolbarCard)

        # 卡片容器（网格均分：卡片拉伸填满整行，列数随宽度自适应；贴顶排布）
        self.listCard = CardWidget(self)
        self.listLayout = QVBoxLayout(self.listCard)
        self.listLayout.setContentsMargins(15, 15, 15, 15)
        self.listLayout.setSpacing(10)

        self.emptyHint = EmptyStatusWidget(self._empty_msg, self)
        self.gridLayout = QGridLayout()
        self.gridLayout.setContentsMargins(0, 0, 0, 0)
        self.gridLayout.setHorizontalSpacing(_H_SPACING)
        self.gridLayout.setVerticalSpacing(10)
        self.listLayout.addWidget(self.emptyHint)
        # 网格取自然高度贴顶，剩余空间由底部 stretch 吸收（避免固定高卡片漂浮）
        self.listLayout.addLayout(self.gridLayout)
        self.listLayout.addStretch(1)

        self.vLayout.addWidget(self.listCard, 1)

        # 信号连接
        self.btnRefresh.clicked.connect(self.refresh)
        self.btnOpenDir.clicked.connect(self._open_output_dir)
        self.searchEdit.textChanged.connect(self._on_search)
        # 输出目录变更 / 一批解密结束 → 刷新已解密列表
        signalBus.paths_changed.connect(self.refresh)
        signalBus.conversion_finished.connect(lambda *_: self.refresh())

        self.refresh()

    def resizeEvent(self, e):
        """页面尺寸变化时按新宽度重排列数，卡片保持填充。"""
        super().resizeEvent(e)
        self._relayout()

    # ------------------------------------------------------------ 网格排布
    def _visible_cards(self):
        """按当前搜索词过滤卡片（匹配文件名，大小写不敏感）。"""
        q = self._filter.strip().lower()
        if not q:
            return list(self._cards)
        return [c for c in self._cards if q in os.path.basename(c.file_path).lower()]

    def _relayout(self):
        """按当前宽度计算列数并重排（仅可见卡片），宽度均分填满整行。"""
        while self.gridLayout.count():
            item = self.gridLayout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
        visible = self._visible_cards()
        available = max(self.viewport().width() - 60, 0)
        cols = max(1, (available - 30) // (_CARD_MIN_W + _H_SPACING))
        for i, card in enumerate(visible):
            self.gridLayout.addWidget(card, i // cols, i % cols)
        # 强制各列等宽（带复位防幽灵列），与任务页一致
        prev = getattr(self, "_grid_cols", 0)
        for col in range(max(prev, cols)):
            self.gridLayout.setColumnStretch(col, 0)
        for col in range(cols):
            self.gridLayout.setColumnStretch(col, 1)
        self._grid_cols = cols
        self.gridLayout.activate()
        self._update_count()

    # ------------------------------------------------------------ 文件操作
    def refresh(self):
        """扫描输出目录，列出已解密文件（按修改时间倒序）。"""
        out = cfg.output_dir.value
        matched = []
        if not out:
            self._empty_msg = "尚未设置输出目录，请到配置界面设置"
        elif not os.path.isdir(out):
            self._empty_msg = "输出目录不存在"
        else:
            self._empty_msg = "输出目录暂无已解密文件"
            try:
                for name in os.listdir(out):
                    full = os.path.join(out, name)
                    if os.path.isfile(full) and is_supported_file(full):
                        matched.append(full)
            except OSError:
                matched = []
            matched.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        self._replace_files(matched)

    def _replace_files(self, paths):
        for c in self._cards:
            c.deleteLater()
        self._cards.clear()
        for path in paths:
            card = TaskCard(path, self)
            card.set_status("success")   # 已解密徽章
            # 右键菜单：删除文件
            card.setContextMenuPolicy(Qt.CustomContextMenu)
            card.customContextMenuRequested.connect(
                lambda pos, c=card: self._show_card_menu(c, pos)
            )
            self._cards.append(card)
        self._relayout()

    def _on_search(self, text):
        self._filter = text
        self._relayout()

    def _open_output_dir(self):
        out = cfg.output_dir.value
        if not out or not os.path.isdir(out):
            signalBus.toast_requested.emit("输出目录未设置或路径不存在。", "warning")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(out))

    # ------------------------------------------------------------ 右键菜单
    def _show_card_menu(self, card, pos):
        """在卡片上弹右键菜单（播放 / 删除）。"""
        menu = RoundMenu(parent=self.window())
        play_act = Action(FluentIcon.PLAY, "播放音乐")
        play_act.triggered.connect(lambda: self._play_file(card))
        menu.addAction(play_act)
        del_act = Action(FluentIcon.DELETE, "删除文件")
        del_act.triggered.connect(lambda: self._confirm_delete(card))
        menu.addAction(del_act)
        menu.exec(card.mapToGlobal(pos))

    def _play_file(self, card):
        """用系统默认播放器打开音乐文件。"""
        QDesktopServices.openUrl(QUrl.fromLocalFile(card.file_path))

    def _confirm_delete(self, card):
        path = card.file_path
        name = os.path.basename(path)
        box = MessageBox(
            "删除文件", f"确定要删除「{name}」吗？此操作不可恢复。", self.window()
        )
        box.yesButton.setText("删除")
        box.cancelButton.setText("取消")
        if not box.exec():
            return
        try:
            os.remove(path)
        except OSError as exc:
            logger.error(f"删除文件失败: {path} ({exc})")
            signalBus.toast_requested.emit(f"删除失败: {name}", "error")
            return
        # 从列表与网格移除该卡片
        if card in self._cards:
            self._cards.remove(card)
        card.deleteLater()
        self._relayout()
        signalBus.log_emitted.emit(f"已删除文件: {name}", "success")
        signalBus.toast_requested.emit(f"已删除 {name}", "success")

    # ------------------------------------------------------------ 工具栏
    def _update_count(self):
        visible = self._visible_cards()
        total = len(self._cards)
        if self._filter.strip() and total != len(visible):
            self.countLabel.setText(f"{len(visible)} / {total} 个已解密文件")
        else:
            self.countLabel.setText(f"{total} 个已解密文件")
        if not visible:
            if self._filter.strip() and total > 0:
                self.emptyHint.label.setText(f"未找到与“{self._filter.strip()}”匹配的文件")
            else:
                self.emptyHint.label.setText(self._empty_msg)
            self.emptyHint.setVisible(True)
        else:
            self.emptyHint.setVisible(False)
