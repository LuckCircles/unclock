# coding: utf-8
"""文件信息对话框 —— 展示单个已解密文件的封面 + 详细元数据。

基于 QFluentWidgets 的 ``MessageBoxBase``：所有控件均为 Fluent 控件，
随应用主题（浅色/深色）与强调色自动切换。布局参照用户提供的详情图：
顶部左对齐「文件名：xxx」标题行（超长文件名自动跑马灯），主体**左右分栏**
——左侧 270×340 竖向画框内嵌封面（等比缩放不裁剪、圆角，无封面时画主题色
音符占位图），右侧 14 行键值表（**键名左对齐**、值左对齐，
键列固定宽、值列吃剩余）。**所有值均单行显示**：文本过长（超出右列宽）时
由跑马灯自动首尾相连滚动完整展示，不过长则静态单行，绝不换行堆高；完整
路径额外带强调色可点击链接（点击在文件管理器中定位选中）与 Fluent
``ToolTip`` 悬停提示。底部两个按钮等分整行宽度铺满：「保存封面」（把内嵌
封面导出到音乐文件同目录，保存动作由调用方注入回调执行，本组件不写盘）
与「关闭窗口」；左侧封面下方预留一行保存结果反馈。
"""

import os
import time

from PySide6.QtCore import QByteArray, QEvent, QObject, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QVBoxLayout

from qfluentwidgets import (
    CaptionLabel,
    FluentIcon,
    MessageBoxBase,
    PushButton,
    StrongBodyLabel,
    ToolTipFilter,
    ToolTipPosition,
    qconfig,
)

from ..common.media_info import UNKNOWN
from ..common.signal_bus import signalBus
from ..common.utils import format_size, open_file_location

from .marquee_label import MarqueeLabel

# 左侧封面画框尺寸（参照详情图的竖向大图）/ 圆角半径
_COVER_W = 270
_COVER_H = 340
_COVER_RADIUS = 12
# 键名列固定宽（容纳最长键「完整路径」4 字 + 余量），值列吃剩余
_KEY_COL_W = 76


def _decode_cover(png_bytes):
    """封面图片字节（JPEG/PNG） → ``(圆角等比缩略图, 原图宽, 原图高)``。

    ``KeepAspectRatio`` 保留整张封面不被裁切：在 270×340 的竖向画框里等比
    缩放并居中留白（专辑封面多为正方形，上下留白属预期），圆角只作用在缩放
    后的实际矩形上，四角透明。字节无效返回 ``(QPixmap(), 0, 0)``，由调用方
    回退占位图——绝不把损坏字节喂给 QLabel。
    """
    if not png_bytes:
        return QPixmap(), 0, 0
    img = QImage.fromData(QByteArray(png_bytes))
    if img.isNull():
        return QPixmap(), 0, 0
    orig_w, orig_h = img.width(), img.height()
    scaled = img.scaled(_COVER_W, _COVER_H, Qt.KeepAspectRatio,
                        Qt.SmoothTransformation)
    w, h = scaled.width(), scaled.height()
    out = QImage(w, h, QImage.Format_ARGB32)
    out.fill(Qt.transparent)
    painter = QPainter(out)
    painter.setRenderHint(QPainter.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, w, h), _COVER_RADIUS, _COVER_RADIUS)
    painter.setClipPath(path)
    painter.drawImage(0, 0, scaled)
    painter.end()
    return QPixmap.fromImage(out), orig_w, orig_h


def _placeholder_pixmap(w: int = _COVER_W, h: int = _COVER_H) -> QPixmap:
    """无封面占位图：主题强调色淡底 + 大号音符（与卡片占位图同风格）。"""
    color = qconfig.themeColor.value
    img = QImage(w, h, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    painter = QPainter(img)
    painter.setRenderHint(QPainter.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, w, h), _COVER_RADIUS, _COVER_RADIUS)
    painter.setClipPath(path)
    painter.fillRect(0, 0, w, h,
                     QColor(color.red(), color.green(), color.blue(), 40))
    icon_size = 96
    FluentIcon.MUSIC.render(
        painter, QRect((w - icon_size) // 2, (h - icon_size) // 2,
                       icon_size, icon_size), qconfig.theme
    )
    painter.end()
    return QPixmap.fromImage(img)


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
    """只读文件信息对话框：左封面 + 右键值表 + 「保存封面」「关闭窗口」。

    ``media`` 为 ``probe_audio_info()`` 的返回字典（可能为空 —— 探测失败时
    音频相关字段统一显示「—」）；``source`` 为来源标签（已解密/已添加）；
    ``cover`` 为 cover_loader 提取的**原始图片字节（JPEG/PNG）**（None / 无效表示无封面，
    回退占位图并禁用「保存封面」）。``save_cover`` 为可选回调，返回
    ``(ok, payload)``：成功时 payload 是导出图片的完整路径，失败时是可直接
    展示的错误文案——落盘与日志仍归调用方，本组件只负责按钮与反馈。
    ``parent`` 必须传入有效窗口：Fluent 掩码对话框按父窗口尺寸定位铺满遮罩。
    """

    def __init__(self, path: str, size: int, mtime: float,
                 source: str, media: dict, parent=None, cover=None,
                 save_cover=None):
        super().__init__(parent)
        self.setWindowTitle("文件信息")
        self._save_cover = save_cover

        # 顶部标题行（参照详情图）：左对齐「文件名：<文件名>」；文件名超长
        # 时走跑马灯，避免撑破对话框宽。窗口标题栏仍是「文件信息」。
        self.titleRow = QHBoxLayout()
        self.titleRow.setSpacing(6)
        self.titleKey = StrongBodyLabel("文件名：", self.widget)
        self.titleRow.addWidget(self.titleKey, 0, Qt.AlignLeft | Qt.AlignVCenter)
        self.titleValue = MarqueeLabel(
            os.path.basename(path), self.widget, bold=True, auto=True
        )
        self.titleValue.setFixedHeight(self.fontMetrics().height() + 8)
        self.titleRow.addWidget(self.titleValue, 1, Qt.AlignLeft | Qt.AlignVCenter)
        self.viewLayout.addLayout(self.titleRow)

        # 主体左右分栏：左封面画框 270×340，右 14 行键值表吃掉剩余宽度。
        # 两栏间距 16，键名列固定宽后不会再空出一大条（用户 2026-11-23
        # 指出「中间间隔不要太大」）。
        self.bodyLayout = QHBoxLayout()
        self.bodyLayout.setSpacing(16)
        self.bodyLayout.setContentsMargins(0, 0, 0, 0)
        self.viewLayout.addLayout(self.bodyLayout, 1)

        self.coverLayout = QVBoxLayout()
        self.coverLayout.setSpacing(8)
        self.coverLayout.setContentsMargins(0, 0, 0, 0)
        self.coverLabel = QLabel(self.widget)
        self.coverLabel.setFixedSize(_COVER_W, _COVER_H)
        self.coverLabel.setAlignment(Qt.AlignCenter)
        self.coverLayout.addWidget(self.coverLabel, 0, Qt.AlignCenter)
        # 保存结果反馈：默认隐藏，只在点击「保存封面」后显示。模态遮罩下首页
        # 的默认成功提示浮层可能被盖住，所以成功/失败都要在对话框内可见。
        self.statusLabel = CaptionLabel("", self.widget)
        self.statusLabel.setFixedWidth(_COVER_W)
        self.statusLabel.setWordWrap(True)
        self.statusLabel.setAlignment(Qt.AlignCenter)
        self.statusLabel.hide()
        self.coverLayout.addWidget(self.statusLabel, 0, Qt.AlignCenter)
        self.coverLayout.addStretch(1)   # 封面贴顶，与信息表首行齐平
        pixmap, _, _ = _decode_cover(cover)
        has_cover = not pixmap.isNull()
        if not has_cover:
            self.coverLabel.setPixmap(_placeholder_pixmap())
        else:
            self.coverLabel.setPixmap(pixmap)
        self.bodyLayout.addLayout(self.coverLayout, 0)

        # 键值表（参照详情图）：左列 CaptionLabel（**左对齐**，与右侧值成两列）、
        # 右列 MarqueeLabel（单行，溢出自动滚动）。与旧版「右对齐 + 1:4 stretch」
        # 不同：键名左对齐后必须给定宽列，否则最长键「完整路径」会把列撑到参差。
        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(18)
        self.grid.setVerticalSpacing(11)
        self.grid.setColumnStretch(0, 0)
        self.grid.setColumnStretch(1, 1)
        self.grid.setColumnMinimumWidth(0, _KEY_COL_W)
        self.bodyLayout.addLayout(self.grid, 1)

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

        # 底部按钮行：「保存封面」（次要）+「关闭窗口」（主）等分整行、铺满
        # 底部。不能用 hideCancelButton()——它会插一份左侧 stretch 留白，把
        # 两个按钮挤到右半区；直接隐藏并摘掉 cancelButton（隐藏项仍参与
        # QBoxLayout 的 stretch 分配），再把 saveButton 插到 yesButton 之前，
        # 两项各持 stretch=1，平分扣除边距与间距后的全部宽度。
        self.cancelButton.hide()
        self.buttonLayout.removeWidget(self.cancelButton)
        self.saveButton = PushButton(FluentIcon.SAVE, "保存封面", self.buttonGroup)
        self.buttonLayout.insertWidget(0, self.saveButton, 1, Qt.AlignVCenter)
        self.yesButton.setText("关闭窗口")
        self.saveButton.clicked.connect(self._on_save_clicked)
        if save_cover is None or not has_cover:
            self.saveButton.setEnabled(False)
            self.saveButton.setToolTip(
                "该文件没有内嵌封面，无法保存" if not has_cover
                else "当前页面不支持保存封面"
            )
            self.saveButton.setToolTipDuration(-1)
            self._save_tip = ToolTipFilter(
                self.saveButton, showDelay=300, position=ToolTipPosition.TOP
            )
            self.saveButton.installEventFilter(self._save_tip)

        # 左右分栏需容纳 270 封面 + 16 间距 + 76 键列 + 18 列间距 + 约 300
        # 值列 + 48 边距；超长内容仍统一走跑马灯滚动，不会被固定宽撑破
        self.widget.setMinimumWidth(780)
        self.widget.setMaximumWidth(840)

    def _on_save_clicked(self):
        """「保存封面」：调用注入的落盘回调，结果在对话框内直接可见。

        不关闭窗口（用户可能还要查看其它字段）；成功显示导出文件名，失败
        显示回调给出的原因。首页的默认成功提示仍由调用方照常发出，但模态
        遮罩可能盖住浮层，因此对话框内的状态行是必需的兜底反馈。
        """
        if self._save_cover is None:
            return
        ok, payload = self._save_cover()
        text = (
            # 左栏只有 270px：手动断成「说明 + 文件名」两行，比自动折成
            # 三四行更整齐；失败文案照旧由 QLabel 自动换行。
            f"已保存到音乐文件同目录\n{os.path.basename(payload)}"
            if ok else str(payload)
        )
        self.statusLabel.setText(text)
        self.statusLabel.show()

    def _add_rows(self, rows, path: str):
        """按行填充键值表：字段名左对齐；所有值统一单行跑马灯。

        短值静态单行、长值（溢出右列宽）自动首尾相连滚动完整展示，绝不换行
        堆高行或与其他行重叠。``path`` 供路径点击回调闭包使用。
        """
        self._path_label = None
        # 统一固定行高：Fluent 标签一旦被 setStyleSheet（路径行染强调色），
        # sizeHint 高度会由 14 突变为 30，令它比其他值行高一截；固定行高让
        # 14 行严格等高，且与跑马灯水平滚动、固定键列宽互不影响。
        row_h = self.fontMetrics().height() + 4
        for row, (key, value) in enumerate(rows):
            key_label = CaptionLabel(key, self.widget)
            key_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

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

            # 左列左对齐（参照详情图：键名成列贴左）；右列跑马灯需拉伸填满
            # 列宽（Ignored 策略）才能检测溢出并滚动，故只做垂直居中，其
            # 内部文本本就左对齐
            self.grid.addWidget(
                key_label, row, 0, Qt.AlignLeft | Qt.AlignVCenter
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
