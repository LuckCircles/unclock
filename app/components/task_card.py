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
)

from ..common.utils import format_size
from .marquee_label import MarqueeLabel

# 任务状态 → (徽章构造方法, 文本)
_STATUS_META = {
    "pending": ("info", "待解密"),
    "running": ("success", "解密中"),
    "success": ("success", "已解密"),
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

        # 固定高度、宽度自适应拉伸（网格均分填满整行）：
        # 高度固定保证网格行高与实际渲染一致，不重叠
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumWidth(300)
        self.setFixedHeight(64)

        self.hLayout = QHBoxLayout(self)
        self.hLayout.setContentsMargins(14, 10, 14, 10)
        self.hLayout.setSpacing(10)

        self.textLayout = QVBoxLayout()
        self.textLayout.setSpacing(2)
        self.textLayout.setContentsMargins(0, 0, 0, 0)

        # 文件名用跑马灯：拉伸填满左侧，过长时悬停整张卡片即首尾相连无缝滚动展示完整文件名
        # （MarqueeLabel 水平策略为 Ignored：不撑宽网格列，列宽保持一致）
        self.nameLabel = MarqueeLabel(os.path.basename(file_path), self)
        self.nameLabel.setMinimumWidth(0)
        self.nameLabel.setAttribute(Qt.WA_TransparentForMouseEvents, True)

        # 单行省略号，避免文本换行撑高卡片导致网格行高不一致
        self.metaLabel = CaptionLabel(self._meta_text(file_path), self)
        self.metaLabel.setWordWrap(False)
        self.metaLabel.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Minimum)
        self.metaLabel.setMinimumWidth(0)
        self.metaLabel.setAttribute(Qt.WA_TransparentForMouseEvents, True)

        self.textLayout.addWidget(self.nameLabel)
        self.textLayout.addWidget(self.metaLabel)

        # 文件名区拉伸填满，徽章按自然宽度贴在右侧——避免给徽章固定 1/5 造成其右侧大片留白
        self.hLayout.addLayout(self.textLayout, 1)

        self._badge = None
        self.set_status("pending")

    def _meta_text(self, file_path: str) -> str:
        try:
            stats = os.stat(file_path)
            when = time.strftime("%Y-%m-%d %H:%M", time.localtime(stats.st_mtime))
            return f"{format_size(stats.st_size)} · {when}"
        except OSError:
            return ""

    def set_status(self, status: str):
        if status not in _STATUS_META:
            return
        self._status = status
        method, text = _STATUS_META[status]
        self.set_badge(text, method)

    def set_badge(self, text: str, kind: str = "info"):
        """设置任意文本徽章（kind: info / success / warning）。

        先移除旧徽章再销毁，避免 deleteLater 延迟生效导致新旧徽章同帧叠加闪烁。
        """
        if self._badge is not None:
            self.hLayout.removeWidget(self._badge)
            self._badge.deleteLater()
            self._badge = None
        if kind == "success":
            self._badge = InfoBadge.success(text, parent=self)
        elif kind == "warning":
            self._badge = InfoBadge.warning(text, parent=self)
        else:
            self._badge = InfoBadge.info(text, parent=self)
        self._badge.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.hLayout.addWidget(self._badge, 0, Qt.AlignTop)   # 徽章自然宽度、贴右

    # ------------------------------------------------------------ 悬停驱动跑马灯
    def enterEvent(self, e):
        # 鼠标进入整张卡片：若文件名过长则开始滚动
        self.nameLabel.set_hovered(True)
        super().enterEvent(e)

    def leaveEvent(self, e):
        # 鼠标离开卡片：停止滚动并复位到开头
        self.nameLabel.set_hovered(False)
        super().leaveEvent(e)

    @property
    def status(self) -> str:
        return self._status
