# coding: utf-8
"""任务管理页面 —— 卡片式待转换文件列表（网格均分填充）。"""

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QVBoxLayout,
)
from qfluentwidgets import (
    Action,
    CaptionLabel,
    CardWidget,
    FluentIcon,
    MessageBox,
    RoundMenu,
    TransparentPushButton,
)

from ..common.config import cfg
from ..common.decrypt_scanner import (
    build_decrypted_basenames,
    is_already_decrypted,
)
from ..common.logger import logger
from ..common.signal_bus import signalBus
from ..common.utils import is_encrypted_file
from ..components.empty_status import EmptyStatusWidget
from ..components.interface import Interface
from ..components.task_card import TaskCard

# 网格布局参数：卡片最小宽 + 水平间距，用于计算列数
_CARD_MIN_W = 300
_H_SPACING = 12

# 卡片排序优先级（值越小越靠上）：待解密 → 解密中 → 失败/跳过 → 已解密
_STATUS_ORDER = {
    "pending": 0,
    "running": 1,
    "failed": 2,
    "skipped": 3,
    "success": 4,
}


class TaskInterface(Interface):
    """待转换文件管理页面（卡片式）。"""

    def __init__(self, parent=None):
        super().__init__("TaskInterface", parent)
        self._cards: list[TaskCard] = []

        # 顶部工具栏卡片
        self.toolbarCard = CardWidget(self)
        self.toolbarLayout = QHBoxLayout(self.toolbarCard)
        self.toolbarLayout.setContentsMargins(15, 12, 15, 12)
        self.toolbarLayout.setSpacing(10)

        self.countLabel = CaptionLabel("0 个文件", self)
        self.toolbarLayout.addWidget(self.countLabel)
        self.toolbarLayout.addStretch(1)

        # 工具栏按钮（FluentIcon 走内置 SVG，无需系统字体，不会渲染成方块）
        self.btnAdd = TransparentPushButton(FluentIcon.ADD, "添加文件", self)
        self.btnRefresh = TransparentPushButton(FluentIcon.SYNC, "刷新列表", self)
        self.btnDelete = TransparentPushButton(FluentIcon.DELETE, "删除完成", self)
        self.btnClear = TransparentPushButton(FluentIcon.BROOM, "清空列表", self)
        for btn in (self.btnAdd, self.btnRefresh, self.btnDelete, self.btnClear):
            self.toolbarLayout.addWidget(btn)

        self.vLayout.addWidget(self.toolbarCard)

        # 卡片容器（网格均分：卡片拉伸填满整行，列数随宽度自适应）
        self.listCard = CardWidget(self)
        self.listLayout = QVBoxLayout(self.listCard)
        self.listLayout.setContentsMargins(15, 15, 15, 15)
        self.listLayout.setSpacing(10)

        self.emptyHint = EmptyStatusWidget("暂无文件，点击“添加文件”或刷新列表", self)
        self.gridLayout = QGridLayout()
        self.gridLayout.setContentsMargins(0, 0, 0, 0)
        self.gridLayout.setHorizontalSpacing(_H_SPACING)
        self.gridLayout.setVerticalSpacing(10)
        self.listLayout.addWidget(self.emptyHint)
        # 网格取自然高度贴顶排布，剩余空间由底部 stretch 吸收：
        # 若给 gridLayout 加 stretch，Qt 会把额外高度分摊到各行、使固定高度的卡片
        # 垂直居中漂浮，出现上方大片空白——故此处不给 grid 拉伸，改在末尾加 stretch。
        self.listLayout.addLayout(self.gridLayout)
        self.listLayout.addStretch(1)

        self.vLayout.addWidget(self.listCard, 1)

        # 信号连接
        self.btnAdd.clicked.connect(self._add_files)
        self.btnRefresh.clicked.connect(self.refresh_from_config)
        self.btnDelete.clicked.connect(self._remove_completed)
        self.btnClear.clicked.connect(self.clear_files)
        signalBus.file_started.connect(self._on_file_started)
        signalBus.file_finished.connect(self._on_file_finished)
        signalBus.paths_changed.connect(self.refresh_from_config)

        self.refresh_from_config()

    def resizeEvent(self, e):
        """页面尺寸变化时按新宽度重排列数，卡片保持填充。"""
        super().resizeEvent(e)
        self._relayout()

    # ------------------------------------------------------------ 网格排布
    def _relayout(self):
        """按当前宽度计算列数并重排卡片（宽度均分填满整行）。"""
        # 先按状态排序：待解密在上、已解密沉底，保持视觉稳定
        self._cards.sort(key=lambda c: _STATUS_ORDER.get(c.status, 9))
        # 摘除现有 item（不销毁 widget）
        while self.gridLayout.count():
            item = self.gridLayout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
        # 可用宽 = 视口宽 - 页面边距(60) - listCard 内边距(30)
        available = max(self.viewport().width() - 60, 0)
        cols = max(1, (available - 30) // (_CARD_MIN_W + _H_SPACING))
        for i, card in enumerate(self._cards):
            self.gridLayout.addWidget(card, i // cols, i % cols)
        # 强制各列等宽：先复位旧列拉伸，再为当前所有列设相同 stretch，
        # 避免个别卡片内容 sizeHint 偏大致使列宽不一致（如长文件名、不同徽章文本）
        prev = getattr(self, "_grid_cols", 0)
        for col in range(max(prev, cols)):
            self.gridLayout.setColumnStretch(col, 0)
        for col in range(cols):
            self.gridLayout.setColumnStretch(col, 1)
        self._grid_cols = cols
        self.gridLayout.activate()
        self._update_count()

    # ------------------------------------------------------------ 文件操作
    def refresh_from_config(self):
        input_dir = cfg.input_dir.value
        if input_dir and os.path.exists(input_dir):
            self.scan_directory(input_dir)

    def scan_directory(self, path: str):
        if not path or not os.path.exists(path):
            return
        matched = []
        try:
            for name in os.listdir(path):
                full = os.path.join(path, name)
                # 只纳入加密音乐文件；明文音频等非加密文件跳过
                if os.path.isfile(full) and is_encrypted_file(full):
                    matched.append(full)
        except OSError:
            return
        self._replace_files(matched)

    def _add_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择待解密文件", "", "All Files (*)"
        )
        if not files:
            return
        if not self._append_files(files):
            signalBus.toast_requested.emit("未选择可解密的加密音乐文件。", "warning")

    def _append_files(self, paths):
        existing = {card.file_path for card in self._cards}
        # 输入/输出目录对比：扫描输出目录建已解密基名集合
        decrypted_names = build_decrypted_basenames(cfg.output_dir.value)
        added = False
        for path in paths:
            # 非加密文件跳过；仅纳入加密音乐文件
            if not is_encrypted_file(path) or path in existing:
                continue
            existing.add(path)
            card = TaskCard(path, self)
            # 加密文件按去后缀在输出目录命中 → 已解密
            if is_already_decrypted(path, decrypted_names):
                card.set_status("success")
            # 右键菜单：删除文件 / 移出列表
            card.setContextMenuPolicy(Qt.CustomContextMenu)
            card.customContextMenuRequested.connect(
                lambda pos, c=card: self._show_card_menu(c, pos)
            )
            self._cards.append(card)
            added = True
        if added:
            self._relayout()
        return added

    def _replace_files(self, paths):
        for c in self._cards:
            c.deleteLater()
        self._cards.clear()
        self._append_files(paths)

    def _remove_completed(self):
        """移除状态为"已解密"的卡片。"""
        kept = []
        removed = False
        for c in self._cards:
            if c.status == "success":
                signalBus.queue_remove.emit(c.file_path)
                c.deleteLater()
                removed = True
            else:
                kept.append(c)
        self._cards = kept
        if removed:
            self._relayout()

    def clear_files(self):
        for c in self._cards:
            signalBus.queue_remove.emit(c.file_path)
            c.deleteLater()
        self._cards.clear()
        self._relayout()

    # ------------------------------------------------------------ 右键菜单
    def _show_card_menu(self, card, pos):
        """卡片右键菜单：删除文件 / 移出列表。"""
        menu = RoundMenu(parent=self.window())
        del_act = Action(FluentIcon.DELETE, "删除文件")
        del_act.triggered.connect(lambda: self._delete_file(card))
        menu.addAction(del_act)
        rm_act = Action(FluentIcon.CLOSE, "移出列表")
        rm_act.triggered.connect(lambda: self._remove_from_list(card))
        menu.addAction(rm_act)
        menu.exec(card.mapToGlobal(pos))

    def _delete_file(self, card):
        """删除文件：从磁盘删除并移除卡片（刷新后不再出现）。"""
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
        self._remove_card(card)
        signalBus.log_emitted.emit(f"已删除文件: {name}", "success")
        signalBus.toast_requested.emit(f"已删除 {name}", "success")

    def _remove_from_list(self, card):
        """仅移出列表：不动磁盘文件（刷新后因文件仍在输入目录会重新出现）。"""
        name = os.path.basename(card.file_path)
        self._remove_card(card)
        signalBus.log_emitted.emit(
            f"已移出列表: {name}（文件保留，刷新后仍在输入目录会重新出现）", "info"
        )

    def _remove_card(self, card):
        """从卡片列表与网格移除单个卡片并刷新；同步从转换队列剔除该文件。"""
        if card in self._cards:
            self._cards.remove(card)
        signalBus.queue_remove.emit(card.file_path)
        card.deleteLater()
        self._relayout()

    def get_file_paths(self) -> list[str]:
        return [c.file_path for c in self._cards]

    # ------------------------------------------------------------ 状态回调
    def _on_file_started(self, path: str):
        for card in self._cards:
            if card.file_path == path:
                card.set_status("running")
                break
        # 仅刷新右上角状态分布与计数，不重排网格——避免每转换一个文件整页卡片跳动
        self._update_count()

    def _on_file_finished(self, path: str, success: bool):
        for card in self._cards:
            if card.file_path == path:
                card.set_status("success" if success else "failed")
                break
        # 仅刷新右上角状态分布与计数，不重排网格——避免每转换一个文件整页卡片跳动
        self._update_count()

    # ------------------------------------------------------------ 工具栏
    def _update_count(self):
        count = len(self._cards)
        # 输入/输出对比的状态分布：待解密 / 解密中 / 已解密 / 失败
        pending = running = success = failed = 0
        for c in self._cards:
            if c.status == "pending":
                pending += 1
            elif c.status == "running":
                running += 1
            elif c.status == "success":
                success += 1
            elif c.status == "failed":
                failed += 1
        parts = []
        if pending:
            parts.append(f"待解密 {pending}")
        if running:
            parts.append(f"解密中 {running}")
        if success:
            parts.append(f"已解密 {success}")
        if failed:
            parts.append(f"失败 {failed}")
        if parts:
            self.countLabel.setText(" · ".join(parts) + f" · 共 {count}")
        else:
            self.countLabel.setText(f"共 {count} 个文件")
        self.emptyHint.setVisible(count == 0)
