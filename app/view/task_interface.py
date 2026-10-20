# coding: utf-8
"""任务管理页面 —— 卡片式待转换文件列表。"""

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QVBoxLayout,
)
from qfluentwidgets import (
    CaptionLabel,
    CardWidget,
    FluentIcon,
    FlowLayout,
    TransparentPushButton,
)

from ..common.config import cfg
from ..common.signal_bus import signalBus
from ..common.utils import is_supported_file
from ..components.empty_status import EmptyStatusWidget
from ..components.interface import Interface
from ..components.task_card import TaskCard


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

        self.btnAdd = TransparentPushButton(FluentIcon.ADD, "添加文件", self)
        self.btnRefresh = TransparentPushButton(FluentIcon.SYNC, "刷新列表", self)
        self.btnDelete = TransparentPushButton(FluentIcon.DELETE, "移除已完成", self)
        self.btnClear = TransparentPushButton(FluentIcon.CLOSE, "清空列表", self)
        for btn in (self.btnAdd, self.btnRefresh, self.btnDelete, self.btnClear):
            self.toolbarLayout.addWidget(btn)

        self.vLayout.addWidget(self.toolbarCard)

        # 卡片容器
        self.listCard = CardWidget(self)
        self.listLayout = QVBoxLayout(self.listCard)
        self.listLayout.setContentsMargins(15, 15, 15, 15)
        self.listLayout.setSpacing(10)

        self.emptyHint = EmptyStatusWidget("暂无文件，点击“添加文件”或刷新列表", self)
        self.flowLayout = FlowLayout()
        self.flowLayout.setContentsMargins(0, 0, 0, 0)
        self.flowLayout.setHorizontalSpacing(12)
        self.flowLayout.setVerticalSpacing(10)
        self.listLayout.addWidget(self.emptyHint)
        self.listLayout.addLayout(self.flowLayout, 1)

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
            for dirpath, _dirnames, filenames in os.walk(path):
                for name in filenames:
                    full = os.path.join(dirpath, name)
                    if is_supported_file(full):
                        matched.append(full)
        except OSError:
            return
        self._replace_files(matched)

    def _add_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择待转换文件", "", "All Files (*)"
        )
        if files:
            self._append_files(files)

    def _append_files(self, paths):
        existing = {card.file_path for card in self._cards}
        for path in paths:
            if not is_supported_file(path) or path in existing:
                continue
            existing.add(path)
            card = TaskCard(path, self)
            self.flowLayout.addWidget(card)
            self._cards.append(card)
        self._update_count()

    def _replace_files(self, paths):
        self._cards.clear()
        while self.flowLayout.count():
            item = self.flowLayout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self._append_files(paths)

    def _remove_completed(self):
        """移除状态为"已完成"的卡片。"""
        kept = []
        for c in self._cards:
            if c.status == "success":
                self.flowLayout.removeWidget(c)
                c.deleteLater()
            else:
                kept.append(c)
        self._cards = kept
        self._update_count()

    def clear_files(self):
        for c in self._cards:
            self.flowLayout.removeWidget(c)
            c.deleteLater()
        self._cards.clear()
        self._update_count()

    def get_file_paths(self) -> list[str]:
        return [c.file_path for c in self._cards]

    # ------------------------------------------------------------ 状态回调
    def _on_file_started(self, path: str):
        for card in self._cards:
            if card.file_path == path:
                card.set_status("running")
                break

    def _on_file_finished(self, path: str, success: bool):
        for card in self._cards:
            if card.file_path == path:
                card.set_status("success" if success else "failed")
                break

    # ------------------------------------------------------------ 工具栏
    def _update_count(self):
        count = len(self._cards)
        self.countLabel.setText(f"{count} 个文件")
        self.emptyHint.setVisible(count == 0)
        signalBus.files_changed.emit(count)
