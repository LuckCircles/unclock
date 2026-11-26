# coding: utf-8
"""转换任务卡片 —— 单文件状态展示，由 TaskInterface 流式排布。

卡片最左侧的 44×44 缩略图位支持两种模式（共用同一 QLabel）：
- ``cover=True``：已解密页的专辑封面，初始主题占位图、后台回填；
- ``icon=True``：任务页的平台图标，按后缀显示对应平台 logo，未映射
  的后缀（明文等）显示默认音乐图标。
两种模式互斥；均不启用时左侧位完全不创建，布局零改变。
"""

import os
import time

from PySide6.QtCore import QByteArray, QEasingCurve, QRect, Qt, QVariantAnimation
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
)
from qfluentwidgets import (
    CaptionLabel,
    CardWidget,
    FluentIcon,
    FluentIconBase,
    InfoBadge,
    qconfig,
)

from ..common.utils import format_size
from .marquee_label import MarqueeLabel

# 封面缩略图尺寸 / 圆角半径（卡片高 64，内容区 44，正好贴合）
_COVER_SIDE = 44
_COVER_RADIUS = 6
# 封面真图淡入时长：占位图 → 专辑封面的平滑过渡，与滚动短淡入
# （_FADE_SCROLL_MS=170）同量级，快到不打断浏览节奏、慢到不觉得闪现
_COVER_FADE_MS = 220

# 任务状态 → (徽章构造方法, 文本)
_STATUS_META = {
    "pending": ("info", "待解密"),
    "running": ("success", "解密中"),
    "success": ("success", "已解密"),
    "failed": ("warning", "失败"),
    "skipped": ("info", "已跳过"),
}


def _rounded_pixmap(pixmap: QPixmap, side: int = _COVER_SIDE,
                    radius: int = _COVER_RADIUS) -> QPixmap:
    """QPixmap → 居中裁剪 + 圆角缩略图（保持宽高比，不拉伸变形）。

    封面字节与 qrc 平台图标统一走此函数：先把来源转成 QPixmap，再做同一套
    居中裁剪 + 圆角，保证两类缩略图视觉一致。
    """
    if pixmap.isNull():
        return QPixmap()
    scaled = pixmap.toImage().scaled(side, side, Qt.KeepAspectRatioByExpanding,
                                     Qt.SmoothTransformation)
    x, y = (scaled.width() - side) // 2, (scaled.height() - side) // 2
    square = scaled.copy(max(0, x), max(0, y), side, side)
    out = QImage(side, side, QImage.Format_ARGB32)
    out.fill(Qt.transparent)
    painter = QPainter(out)
    painter.setRenderHint(QPainter.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(0, 0, side, side, radius, radius)
    painter.setClipPath(path)
    painter.drawImage(0, 0, square)
    painter.end()
    return QPixmap.fromImage(out)


def _rounded_cover(png_bytes: bytes, side: int = _COVER_SIDE,
                   radius: int = _COVER_RADIUS) -> QPixmap:
    """封面图片字节（JPEG/PNG） → 居中裁剪 + 圆角缩略图（保持宽高比）。"""
    img = QImage.fromData(QByteArray(png_bytes))
    return _rounded_pixmap(QPixmap.fromImage(img), side, radius)


def _placeholder_cover(side: int = _COVER_SIDE,
                       radius: int = _COVER_RADIUS) -> QPixmap:
    """无封面时的占位图：主题强调色淡底 + 音符图标（随主题切换重绘）。"""
    color = qconfig.themeColor.value
    img = QImage(side, side, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    painter = QPainter(img)
    painter.setRenderHint(QPainter.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(0, 0, side, side, radius, radius)
    painter.setClipPath(path)
    painter.fillRect(0, 0, side, side,
                     QColor(color.red(), color.green(), color.blue(), 40))
    icon_size = 24
    FluentIcon.MUSIC.render(
        painter, QRect((side - icon_size) // 2, (side - icon_size) // 2,
                       icon_size, icon_size), qconfig.theme
    )
    painter.end()
    return QPixmap.fromImage(img)


class TaskCard(CardWidget):
    """单个待转换/已转换文件卡片。"""

    def __init__(self, file_path: str, parent=None, meta=None, badge=None,
                 cover=False, icon=False, platform_icon=None):
        """构建单张文件卡片。

        ``meta`` 为 ``(size, mtime)`` 预取元数据：由扫描线程批量取齐后
        传入，建卡不再逐卡访问磁盘；缺省时回退为本地 ``os.stat``。
        ``badge`` 为 ``(文本, kind)`` 初始徽章：跳过默认"待解密"徽章的
        创建-销毁-重建，长列表批量建卡时省一半徽章控件。
        ``cover=True`` 在最左侧启用专辑封面位（仅已解密页使用）。
        ``icon=True`` 在最左侧启用平台图标位（仅任务页使用），``platform_icon``
        为官方 ``FluentIconBase`` 图标（如 ``PlatformIcon.QQ_MUSIC``）；其
        ``path()`` 返回 ``:/`` qrc 路径，为 None 时显示默认音乐图标占位图。
        两者均不传时完全不创建左侧缩略图控件，布局零改变。
        """
        super().__init__(parent)
        self.file_path = file_path
        self._status = "pending"
        self._badge = None
        self._cover_label = None
        self._has_real_cover = False   # 左侧位当前是否显示真实图片（区别于默认占位图）

        # 固定高度、宽度自适应拉伸（网格均分填满整行）：
        # 高度固定保证网格行高与实际渲染一致，不重叠
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        # 最小宽 240：与网格 6 列布局（卡宽可至约 260）兼容，避免顶破网格
        self.setMinimumWidth(240)
        self.setFixedHeight(64)

        self.hLayout = QHBoxLayout(self)
        self.hLayout.setContentsMargins(14, 10, 14, 10)
        self.hLayout.setSpacing(10)

        # 左侧缩略图位：cover（已解密页封面）/ icon（任务页平台图标）共用同一
        # 44×44 位与相同布局，插在最左侧；立即放图避免空档。两者都不传时整段
        # 跳过，卡片布局零改变。
        if cover or icon:
            self._cover_label = QLabel(self)
            self._cover_label.setFixedSize(_COVER_SIDE, _COVER_SIDE)
            self._cover_label.setAlignment(Qt.AlignCenter)
            self._cover_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            if icon:
                self.set_platform_icon(platform_icon)
            else:
                self._cover_label.setPixmap(_placeholder_cover())
            self.hLayout.addWidget(self._cover_label, 0, Qt.AlignVCenter)

        self.textLayout = QVBoxLayout()
        self.textLayout.setSpacing(2)
        self.textLayout.setContentsMargins(0, 0, 0, 0)

        # 文件名用跑马灯：拉伸填满左侧，过长时悬停整张卡片即首尾相连无缝滚动展示完整文件名
        # （MarqueeLabel 水平策略为 Ignored：不撑宽网格列，列宽保持一致）
        self.nameLabel = MarqueeLabel(os.path.basename(file_path), self)
        self.nameLabel.setMinimumWidth(0)
        self.nameLabel.setAttribute(Qt.WA_TransparentForMouseEvents, True)

        # 单行省略号，避免文本换行撑高卡片导致网格行高不一致
        self.metaLabel = CaptionLabel(self._meta_text(file_path, meta), self)
        self.metaLabel.setWordWrap(False)
        self.metaLabel.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Minimum)
        self.metaLabel.setMinimumWidth(0)
        self.metaLabel.setAttribute(Qt.WA_TransparentForMouseEvents, True)

        self.textLayout.addWidget(self.nameLabel)
        self.textLayout.addWidget(self.metaLabel)

        # 文件名区拉伸填满，徽章按自然宽度贴在右侧——避免给徽章固定 1/5 造成其右侧大片留白
        self.hLayout.addLayout(self.textLayout, 1)

        self._badge = None
        if badge is not None:
            self.set_badge(*badge)
        else:
            self.set_status("pending")

    def _meta_text(self, file_path: str, meta=None) -> str:
        try:
            if meta is not None:
                size, mtime = meta
            else:
                stats = os.stat(file_path)
                size, mtime = stats.st_size, stats.st_mtime
            when = time.strftime("%Y-%m-%d %H:%M", time.localtime(mtime))
            return f"{format_size(size)} · {when}"
        except OSError:
            return ""

    def update_meta(self, size, mtime):
        """刷新时同步卡片上的大小 / 修改时间（文本未变不 setText）。

        元数据变化不该触发整页重建；文本相同也不投递 LayoutRequest。
        """
        text = self._meta_text(self.file_path, (size, mtime))
        if self.metaLabel.text() != text:
            self.metaLabel.setText(text)

    def set_status(self, status: str):
        if status not in _STATUS_META:
            return
        self._status = status
        method, text = _STATUS_META[status]
        self.set_badge(text, method)

    def set_badge(self, text: str, kind: str = "info"):
        """设置任意文本徽章（kind: info / success / warning）。

        文本与类型都没变时直接返回：卡片复用 / 状态重复刷新时省去
        InfoBadge 的销毁-重建（长列表滚动省一半徽章控件开销）。
        先移除旧徽章再销毁，避免 deleteLater 延迟生效导致新旧徽章同帧叠加闪烁。
        """
        if (self._badge is not None
                and getattr(self, "_badge_key", None) == (text, kind)):
            return
        self._badge_key = (text, kind)
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

    # ------------------------------------------------------------ 平台图标（任务页）
    def set_platform_icon(self, icon: FluentIconBase | None):
        """设置平台图标；None 或无效资源回退默认音乐占位图。

        ``icon`` 为官方 ``FluentIconBase`` 图标，经 ``icon.path()`` 取得 ``:/``
        qrc 资源路径加载（遵循官方自定义图标用法），再复用与封面一致的圆角裁剪。
        真实平台图标标记 ``_has_real_cover=True``，主题切换时不重绘覆盖。
        """
        if self._cover_label is None:
            return
        if icon:
            pixmap = _rounded_pixmap(QPixmap(icon.path()))
            if not pixmap.isNull():
                self._cover_label.setPixmap(pixmap)
                self._has_real_cover = True
                return
        self._cover_label.setPixmap(_placeholder_cover())
        self._has_real_cover = False

    # ------------------------------------------------------------ 封面（可选能力）
    def _fade_in_cover(self):
        """封面真图淡入：占位图 → 专辑封面平滑过渡。

        淡入期间给缩略图挂 QGraphicsOpacityEffect，结束后移除——稳态零
        开销，不改变卡片其余部分的合成方式。重入（快速连续回填）时先收
        掉上一次动画，从当前不透明度继续，不闪烁。
        """
        label = self._cover_label
        if label is None:
            return
        ani = getattr(self, "_cover_fade_ani", None)
        if ani is not None:
            return  # 回填已排队：本次 setPixmap 已就位，等动画收尾即可
        effect = QGraphicsOpacityEffect(label)
        label.setGraphicsEffect(effect)
        effect.setOpacity(0.0)
        ani = QVariantAnimation(self, duration=_COVER_FADE_MS)
        ani.setStartValue(0.0)
        ani.setEndValue(1.0)
        ani.setEasingCurve(QEasingCurve.OutCubic)

        def _tick(v, eff=effect):
            eff.setOpacity(v)

        def _done(ani_ref=ani, lab=label):
            self._cover_fade_ani = None
            lab.setGraphicsEffect(None)   # 移除合成层，稳态绘制零开销
            ani_ref.deleteLater()

        ani.valueChanged.connect(_tick)
        ani.finished.connect(_done)
        self._cover_fade_ani = ani
        ani.start()

    def set_cover_pixmap(self, pixmap: QPixmap | None):
        """直接贴已裁剪好的 44×44 圆角缩略图（缩略图缓存命中路径）。

        与 ``set_cover`` 的区别：跳过 PNG 解码 / 缩放 / 圆角裁剪，实测
        40 张从约 651ms 降到 0.17ms。``None`` 表示该文件确认无封面，
        回退主题色占位图。调用方负责保证 pixmap 尺寸与圆角已处理完毕。
        """
        if self._cover_label is None:
            return
        if pixmap is not None and not pixmap.isNull():
            self._cover_label.setPixmap(pixmap)
            if not self._has_real_cover:
                self._fade_in_cover()   # 占位 → 真图：淡入过渡
            self._has_real_cover = True
        else:
            self._cover_label.setPixmap(_placeholder_cover())
            self._has_real_cover = False

    def set_cover(self, png_bytes: bytes | None) -> QPixmap | None:
        """PNG 字节 → 解码裁剪并显示；返回生成的缩略图供调用方缓存。

        返回 ``None`` 表示无封面 / 字节无效（当前显示占位图）；调用方应把
        这个 None 也缓存起来，避免对无封面文件重复解码、重复起 ffmpeg。
        """
        if self._cover_label is None:
            return None
        if png_bytes:
            pixmap = _rounded_cover(png_bytes)
            if not pixmap.isNull():
                self._cover_label.setPixmap(pixmap)
                if not self._has_real_cover:
                    self._fade_in_cover()   # 占位 → 真图：淡入过渡
                self._has_real_cover = True
                return pixmap
        self._cover_label.setPixmap(_placeholder_cover())
        self._has_real_cover = False
        return None

    def refresh_cover_placeholder(self):
        """主题/强调色切换时重绘占位图——只影响仍显示占位图的卡片。"""
        if self._cover_label is None or self._has_real_cover:
            return
        self._cover_label.setPixmap(_placeholder_cover())

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
