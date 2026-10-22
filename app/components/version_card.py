# coding: utf-8
"""工具版本卡片 + 卡片容器 —— 官方 Fluent 主题色，无自定义 QSS。"""

from PySide6.QtCore import QFile, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout
from qfluentwidgets import (
    CardWidget,
    CaptionLabel,
    InfoBadge,
    StrongBodyLabel,
)


class VersionCard(CardWidget):
    """工具版本卡片（自适应紧凑版，样式由 Fluent 主题接管）。"""

    def __init__(self, title: str, image_path: str, description: str = "", parent=None):
        super().__init__(parent)
        self.base_title = title

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumWidth(0)
        self.setFixedHeight(64)

        self.hLayout = QHBoxLayout(self)
        self.hLayout.setContentsMargins(14, 10, 14, 10)
        self.hLayout.setSpacing(10)

        # 图标
        self.iconLabel = QLabel(self)
        if QFile.exists(image_path):
            self.iconLabel.setPixmap(
                QPixmap(image_path).scaled(
                    40, 40, Qt.KeepAspectRatio, Qt.SmoothTransformation
                )
            )
        self.iconLabel.setFixedSize(40, 40)

        # 文本区
        self.textLayout = QVBoxLayout()
        self.textLayout.setSpacing(2)
        self.textLayout.setContentsMargins(0, 0, 0, 0)

        self.nameVersionLabel = StrongBodyLabel(title, self)
        self.nameVersionLabel.setSizePolicy(
            QSizePolicy.Ignored, QSizePolicy.Minimum
        )

        # 功能描述（固定文案，不随路径变化，避免长路径截断）
        self.descLabel = CaptionLabel(description, self)
        self.descLabel.setWordWrap(False)
        self.descLabel.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Minimum)

        # 状态徽章（官方 Fluent 主题色）
        self.readyBadge = InfoBadge.success("READY", parent=self)
        self.missBadge = InfoBadge.warning("MISS", parent=self)

        self.textLayout.addWidget(self.nameVersionLabel)
        self.textLayout.addWidget(self.descLabel)

        self.hLayout.addWidget(self.iconLabel, 0, Qt.AlignTop)
        self.hLayout.addLayout(self.textLayout, 1)
        self.hLayout.addWidget(self.readyBadge, 0, Qt.AlignTop)
        self.hLayout.addWidget(self.missBadge, 0, Qt.AlignTop)

        self._set_badge_state(False)

    def update_info(self, version: str, ready: bool = True):
        value = version
        if "um v" in version:
            value = version.replace("um ", "")
        elif version.lower().startswith("ffmpeg "):
            value = version.replace("ffmpeg ", "")

        self.nameVersionLabel.setText(f"{self.base_title} {value}")
        self._set_badge_state(ready)

    def _set_badge_state(self, ready: bool):
        self.readyBadge.setVisible(ready)
        self.missBadge.setVisible(not ready)
