# coding: utf-8
"""封面预览对话框（当前未接线，保留备用）。

2026-11-23 用户取消保存成功提示条上的「查看」按钮、改为默认成功提示后，
本组件不再被任何页面引用；保留实现以便日后需要大图预览时直接复用。

基于 QFluentWidgets 的 ``MessageBoxBase``：遮罩 + Fluent 标题 / 按钮，随应用
主题（浅色/深色）自动换肤，风格与 ``FileInfoDialog`` 一致。图片从**磁盘上
刚保存的 PNG** 读取（不是卡片上的 44×44 缩略图），超过最大边长时等比缩小、
小图不放大以免糊；只提供「关闭」按钮，不修改文件、不调用系统图片查看器。
"""

import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QLabel
from qfluentwidgets import CaptionLabel, MessageBoxBase, TitleLabel

# 预览最大边长（px）：800×800 的真实内嵌封面等比缩到 520，避免把对话框撑满全屏
_MAX_PREVIEW_SIDE = 520


class CoverPreviewDialog(MessageBoxBase):
    """只读封面大图预览：标题 + 等比缩放的图片 + 文件名/尺寸 + 「关闭」。

    ``parent`` 必须传入有效窗口：Fluent 掩码对话框按父窗口尺寸定位铺满遮罩。
    图片读取失败（文件被移动 / 非图片）时显示文字提示，不会抛异常或空白崩溃。
    """

    def __init__(self, path: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("封面预览")

        self.titleLabel = TitleLabel("封面预览", self.widget)
        self.titleLabel.setAlignment(Qt.AlignCenter)
        self.viewLayout.addWidget(self.titleLabel)

        self.imageLabel = QLabel(self.widget)
        self.imageLabel.setAlignment(Qt.AlignCenter)
        self.imageLabel.setMinimumSize(240, 240)
        self.viewLayout.addWidget(self.imageLabel, 1, Qt.AlignCenter)

        pixmap = QPixmap(path)
        if pixmap.isNull():
            self.imageLabel.setText("封面图片无法读取或已被移动")
            hint = os.path.basename(path)
        else:
            orig_w, orig_h = pixmap.width(), pixmap.height()
            if orig_w > _MAX_PREVIEW_SIDE or orig_h > _MAX_PREVIEW_SIDE:
                pixmap = pixmap.scaled(
                    _MAX_PREVIEW_SIDE, _MAX_PREVIEW_SIDE,
                    Qt.KeepAspectRatio, Qt.SmoothTransformation,
                )
            self.imageLabel.setPixmap(pixmap)
            hint = f"{os.path.basename(path)} · 原图 {orig_w} × {orig_h}"

        self.captionLabel = CaptionLabel(hint, self.widget)
        self.captionLabel.setAlignment(Qt.AlignCenter)
        self.captionLabel.setWordWrap(True)
        self.captionLabel.setMaximumWidth(_MAX_PREVIEW_SIDE)
        self.viewLayout.addWidget(self.captionLabel)

        # 只保留「关闭」：隐藏取消、复用主按钮
        self.hideCancelButton()
        self.yesButton.setText("关闭")
        self.widget.setMinimumWidth(420)
