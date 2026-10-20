# coding: utf-8
"""转换任务卡片 —— 单文件状态展示，由 TaskInterface 流式排布。"""

import os
import time

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QSizePolicy, QVBoxLayout
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    CardWidget,
    InfoBadge,
    StrongBodyLabel,
)

from ..common.utils import compact_path, format_size

# 任务状态 → (徽章构造方法, 文本)
_STATUS_META = {
    "pending": ("info", "待处理"),
    "running": ("success", "转换中"),
    "success": ("success", "已完成"),
    "failed": ("warning", "失败"),
    "skipped": ("info", "已跳过"),
}


class TaskCard(CardWidget):
    """单个待转换/已转换文件卡片。"""

    def __init__(self, file_path: str, parent=None):
        super().__init__(parent)
        self.file_path = file_path
        self._status = "pending"
        self._badge = None

        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Minimum)
        self.setFixedWidth(320)

        self.hLayout = QHBoxLayout(self)
        self.hLayout.setContentsMargins(14, 10, 14, 10)
        self.hLayout.setSpacing(10)

        self.textLayout = QVBoxLayout()
        self.textLayout.setSpacing(2)
        self.textLayout.setContentsMargins(0, 0, 0, 0)

        self.nameLabel = StrongBodyLabel(os.path.basename(file_path), self)
        self.nameLabel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        self.metaLabel = CaptionLabel(self._meta_text(file_path), self)
        self.metaLabel.setWordWrap(True)
        self.metaLabel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        self.textLayout.addWidget(self.nameLabel)
        self.textLayout.addWidget(self.metaLabel)

        self.hLayout.addLayout(self.textLayout, 1)
        self.hLayout.addWidget(self._build_badge(), 0, Qt.AlignTop)

        self.set_status("pending")

    def _meta_text(self, file_path: str) -> str:
        try:
            stats = os.stat(file_path)
            when = time.strftime("%Y-%m-%d %H:%M", time.localtime(stats.st_mtime))
            return f"{format_size(stats.st_size)} · {when} · {compact_path(file_path)}"
        except OSError:
            return compact_path(file_path)

    def _build_badge(self):
        method, text = _STATUS_META["pending"]
        self._badge = InfoBadge.info(text, parent=self)
        return self._badge

    def set_status(self, status: str):
        if status not in _STATUS_META:
            return
        self._status = status
        # 重建徽章以切换颜色与文本
        if self._badge is not None:
            self._badge.deleteLater()
        method, text = _STATUS_META[status]
        if method == "success":
            self._badge = InfoBadge.success(text, parent=self)
        elif method == "warning":
            self._badge = InfoBadge.warning(text, parent=self)
        else:
            self._badge = InfoBadge.info(text, parent=self)
        self.hLayout.addWidget(self._badge, 0, Qt.AlignTop)

    @property
    def status(self) -> str:
        return self._status
