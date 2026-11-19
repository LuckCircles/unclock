# coding: utf-8
"""文件信息对话框 —— 展示单个已解密文件的详细元数据。

基于 QFluentWidgets 的 ``MessageBoxBase``：所有控件均为 Fluent 控件，
随应用主题（浅色/深色）与强调色自动切换。标题居中；键值表**左列右对齐、
右列左对齐**（值贴近键列起排，扫读更顺）。**所有值均单行显示**：文本过长
（超出右列宽）时由跑马灯自动首尾相连滚动完整展示，不过长则静态单行，绝不
换行堆高，14 行统一行高；完整路径额外带强调色可点击链接（点击在文件管理器
中定位选中）与 Fluent ``ToolTip`` 悬停提示。仅保留单个「关闭」按钮。
"""

import os
import time

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import QGridLayout

from qfluentwidgets import (
    CaptionLabel,
    MessageBoxBase,
    TitleLabel,
    ToolTipFilter,
    ToolTipPosition,
    qconfig,
)

from ..common.media_info import UNKNOWN
from ..common.signal_bus import signalBus
from ..common.utils import format_size, open_file_location

from .marquee_label import MarqueeLabel


def _fmt_time(mtime: float) -> str:
    """mtime 时间戳 → 可读日期时间（本地时区）。"""
    try:
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(mtime))
    except (OSError, ValueError, OverflowError):
        return UNKNOWN


class _PathClickFilter(QObject):
    """跑马灯路径控件的点击过滤器：左键点击在文件管理器中定位文件。

    自动滚动由 ``MarqueeLabel`` 自身驱动，Fluent 提示由 ``ToolTipFilter``
    独立负责，本过滤器只处理点击，除点击外一律返回 False，保证与同时安装的
    ToolTipFilter 事件过滤器链互不干扰。
    """

    def __init__(self, callback, parent=None):
        super().__init__(parent)
        self._callback = callback

    def eventFilter(self, obj, event):
        if event.type() == QEvent.MouseButtonPress \
                and event.button() == Qt.LeftButton:
            self._callback()
            return True
        return False


class FileInfoDialog(MessageBoxBase):
    """只读文件信息对话框：键值表 + 单一「关闭」按钮。

    ``media`` 为 ``probe_audio_info()`` 的返回字典（可能为空 —— 探测失败时
    音频相关字段统一显示「—」）；``source`` 为来源标签（已解密/已添加）。
    ``parent`` 必须传入有效窗口：Fluent 掩码对话框按父窗口尺寸定位铺满遮罩。
    """

    def __init__(self, path: str, size: int, mtime: float,
                 source: str, media: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("文件信息")

        self.titleLabel = TitleLabel("文件信息", self.widget)
        self.titleLabel.setAlignment(Qt.AlignCenter)
        self.viewLayout.addWidget(self.titleLabel)

        # 键值表：左列 CaptionLabel（右对齐）、右列 MarqueeLabel（单行，溢出自动滚动）
        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(20)
        self.grid.setVerticalSpacing(10)
        # 列宽占比 左 2/5 : 右 3/5（QGridLayout 按 stretch 比例分配扣除
        # 内容最小宽后的剩余空间，实测 124:186 = 2:3）。左列变宽也同步
        # 把右对齐的键名整体往右带，贴合「左列往右」的观感
        self.grid.setColumnStretch(0, 2)
        self.grid.setColumnStretch(1, 3)
        self.viewLayout.addLayout(self.grid)

        ext = os.path.splitext(path)[1]
        rows = [
            ("文件名", os.path.basename(path)),
            ("完整路径", path),
            ("文件大小", format_size(size)),
            ("修改时间", _fmt_time(mtime)),
            ("来源", source or UNKNOWN),
            ("文件格式", ext.lstrip(".").upper() or UNKNOWN),
            ("时长", media.get("duration", UNKNOWN)),
            ("编码", media.get("codec", UNKNOWN)),
            ("采样率", media.get("sample_rate", UNKNOWN)),
            ("声道", media.get("channels", UNKNOWN)),
            ("码率", media.get("bitrate", UNKNOWN)),
            ("标题", media.get("title", UNKNOWN)),
            ("艺术家", media.get("artist", UNKNOWN)),
            ("专辑", media.get("album", UNKNOWN)),
        ]
        self._add_rows(rows, path)
        # 路径链接颜色随主题 / 强调色切换刷新
        qconfig.themeChanged.connect(self._apply_path_color)
        qconfig.themeColorChanged.connect(self._apply_path_color)

        # 只保留「关闭」：隐藏取消、复用主按钮
        self.hideCancelButton()
        self.yesButton.setText("关闭")

        # 收窄宽度：键值左右对齐后值列不再需要大片居中留白；
        # 超长内容统一走跑马灯滚动，不会被固定宽撑破
        self.widget.setMinimumWidth(380)
        self.widget.setMaximumWidth(430)

    def _add_rows(self, rows, path: str):
        """按行填充键值表：字段名右对齐；所有值统一单行跑马灯。

        短值静态单行、长值（溢出右列宽）自动首尾相连滚动完整展示，绝不换行
        堆高行或与其他行重叠。``path`` 供路径点击回调闭包使用。
        """
        self._path_label = None
        # 统一固定行高：Fluent 标签一旦被 setStyleSheet（路径行染强调色），
        # sizeHint 高度会由 14 突变为 30，令它比其他值行高一截；固定行高让
        # 14 行严格等高，且与跑马灯水平滚动、2:3 列宽分配互不影响。
        row_h = self.fontMetrics().height() + 4
        for row, (key, value) in enumerate(rows):
            key_label = CaptionLabel(key, self.widget)
            key_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

            # 值：全部单行跑马灯（普通体；auto=True 溢出即自动滚动，
            # 不溢出则静态只显示一份、定时器零开销）
            val_label = MarqueeLabel(
                str(value), self.widget, bold=False, auto=True
            )
            val_label.setFixedHeight(row_h)
            if key == "完整路径":
                # 路径额外带强调色可点击链接 + Fluent 悬停提示（其余字段普通态）
                val_label.setCursor(Qt.PointingHandCursor)
                val_label.setToolTip(
                    "<b>完整路径</b><br/>自动滚动展示 · 点击打开文件所在位置"
                )
                val_label.setToolTipDuration(-1)
                self._path_tip = ToolTipFilter(
                    val_label, showDelay=300, position=ToolTipPosition.BOTTOM
                )
                val_label.installEventFilter(self._path_tip)
                # 两个过滤器都由 self 持有：PySide 不持有 Python 侧引用，
                # 局部对象会被 GC 回收导致事件过滤静默失效
                self._path_filter = _PathClickFilter(
                    lambda: self._open_location(path), self
                )
                val_label.installEventFilter(self._path_filter)
                self._path_label = val_label
                self._apply_path_color()

            # 左列右对齐；右列跑马灯需拉伸填满列宽（Ignored 策略）才能检测
            # 溢出并滚动，故只做垂直居中；其内部文本本就左对齐，与左列贴边
            self.grid.addWidget(
                key_label, row, 0, Qt.AlignRight | Qt.AlignVCenter
            )
            self.grid.addWidget(val_label, row, 1, Qt.AlignVCenter)

    def _apply_path_color(self, *_):
        """把路径文字染成强调色（主题/强调色切换时刷新）。

        走 MarqueeLabel.setTextColor()：直接作用到每份文本子控件，避免
        Fluent 全局 QSS 覆盖父控件 stylesheet 导致颜色不生效。
        """
        if getattr(self, "_path_label", None) is None:
            return
        self._path_label.setTextColor(qconfig.themeColor.value)

    def _open_location(self, path: str):
        """点击路径 → 在文件管理器中定位选中；失败给出 toast 提示。"""
        if not open_file_location(path):
            signalBus.toast_requested.emit("无法打开：文件已不存在或路径无效。", "warning")
