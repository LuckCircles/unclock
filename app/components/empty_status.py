# coding: utf-8
"""空状态提示组件 —— 表情卡片 + 提示文字，居中显示。"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget, QVBoxLayout
from qfluentwidgets import CaptionLabel, FluentIcon, IconWidget

from ..common.resource import image

# 表情卡片边长（正方形，与提示文字上下排列）
_EMOJI_SIZE = 96


class EmptyStatusWidget(QWidget):
    """列表为空时的居中提示：表情卡片在上、说明文字在下。

    ``image_name`` 对应的资源不存在时退回旧样式（信息图标 + 文字单行居中）。
    """

    def __init__(self, hint: str = "暂无文件", parent=None, image_name: str = ""):
        super().__init__(parent)
        self.vLayout = QVBoxLayout(self)
        self.vLayout.setContentsMargins(0, 24, 0, 24)
        self.vLayout.setSpacing(12)
        self.vLayout.setAlignment(Qt.AlignCenter)

        pix = QPixmap(image(image_name)) if image_name else QPixmap()
        has_image = not pix.isNull()

        if has_image:
            # 正方形表情卡片，等比缩放、平滑插值，整体居中
            self.imageLabel = QLabel(self)
            self.imageLabel.setPixmap(
                pix.scaled(
                    _EMOJI_SIZE,
                    _EMOJI_SIZE,
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation,
                )
            )
            self.imageLabel.setFixedSize(_EMOJI_SIZE, _EMOJI_SIZE)
            self.imageLabel.setAlignment(Qt.AlignCenter)
            self.vLayout.addWidget(self.imageLabel, 0, Qt.AlignHCenter)

        # 文字过长时自动换行，避免空状态提示横向溢出
        self.label = CaptionLabel(hint, self)
        self.label.setWordWrap(True)

        if has_image:
            self.vLayout.addWidget(self.label, 0, Qt.AlignHCenter)
        else:
            # 无图退路：信息图标 + 文字单行居中
            self.icon = IconWidget(FluentIcon.INFO, self)
            self.icon.setFixedSize(24, 24)
            self.row = QWidget(self)
            self.rowLayout = QHBoxLayout(self.row)
            self.rowLayout.setContentsMargins(0, 0, 0, 0)
            self.rowLayout.setSpacing(8)
            self.rowLayout.addWidget(self.icon)
            self.rowLayout.addWidget(self.label)
            self.vLayout.addWidget(self.row, 0, Qt.AlignHCenter)
