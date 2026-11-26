# coding: utf-8
"""工具版本卡片 + 卡片容器 —— 官方 Fluent 主题色，无自定义 QSS。"""

from html import escape

from PySide6.QtCore import QFile, QSize, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..common.i18n import translate_ui
from qfluentwidgets import (
    CaptionLabel,
    CardWidget,
    FluentIcon,
    InfoBadge,
    StrongBodyLabel,
    ToolTipFilter,
    ToolTipPosition,
    TransparentToolButton,
)


def _fluent_tip(widget, text: str, position=ToolTipPosition.TOP_RIGHT):
    """把原生 ``QToolTip`` 换成 Fluent 风格 ``ToolTip``（主题色 / 圆角 / 投影 / 淡入）。

    ``ToolTipFilter`` 拦截 ``QEvent.ToolTip``，鼠标进入 300ms 后显示浮层；
    ``toolTipDuration=-1`` 让提示在鼠标移开时才隐藏，便于阅读完整网址。
    返回的过滤器必须被持有，否则 Python 侧对象可能被回收导致浮层失效。
    参考：https://qfluentwidgets.com/zh/pages/components/tooltip
    """
    widget.setToolTip(text)
    widget.setToolTipDuration(-1)
    tip = ToolTipFilter(widget, showDelay=300, position=position)
    widget.installEventFilter(tip)
    return tip


class VersionCard(CardWidget):
    """工具版本卡片（自适应紧凑版，样式由 Fluent 主题接管）。"""

    #: 右下角分享按钮被点击时带出官网地址；打开浏览器由 view 层负责，
    #: 组件层不直接调用系统服务（与 PathCard 的 clicked → view 一致）。
    homepage_requested = Signal(str)

    def __init__(
        self,
        title: str,
        image_path: str,
        description: str = "",
        parent=None,
        *,
        homepage: str = "",
    ):
        super().__init__(parent)
        self.base_title = title
        self.homepage = homepage

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

        # 相应提示：徽章说明状态含义（检测中两枚都隐藏，提示也不会触发）
        self._tip_filters = [
            _fluent_tip(
                self.readyBadge,
                self._status_tip("已就绪", "检测通过，可正常参与解密"),
                ToolTipPosition.TOP,
            ),
            _fluent_tip(
                self.missBadge,
                self._status_tip("缺失", "请检查工具文件，或在设置界面重新指定路径"),
                ToolTipPosition.TOP,
            ),
        ]

        # 右侧列：顶部徽章 / 底部官网分享按钮。两枚徽章共用一行，同一时刻
        # 只有一个可见；行宽固定取较宽者，避免检测结果到达时文本区宽度跳动。
        self.badgeRow = QWidget(self)
        self.badgeRow.setFixedWidth(
            max(self.readyBadge.sizeHint().width(), self.missBadge.sizeHint().width())
        )
        self.badgeLayout = QHBoxLayout(self.badgeRow)
        self.badgeLayout.setContentsMargins(0, 0, 0, 0)
        self.badgeLayout.setSpacing(0)
        self.badgeLayout.addStretch(1)
        self.badgeLayout.addWidget(self.readyBadge, 0, Qt.AlignVCenter)
        self.badgeLayout.addWidget(self.missBadge, 0, Qt.AlignVCenter)

        # 分享按钮：右下角 20px 透明图标，悬停显示官网地址，点击发信号给 view
        self.shareButton = TransparentToolButton(FluentIcon.SHARE, self)
        self.shareButton.setFixedSize(20, 20)
        self.shareButton.setIconSize(QSize(14, 14))
        self.shareButton.setCursor(Qt.PointingHandCursor)
        share_tip = ""
        if homepage:
            share_tip = self._share_tip()
        self.shareButton.setVisible(bool(homepage))
        self.shareButton.clicked.connect(self._on_share_clicked)
        self._tip_filters.append(
            _fluent_tip(self.shareButton, share_tip, ToolTipPosition.TOP_RIGHT)
        )

        self.rightLayout = QVBoxLayout()
        self.rightLayout.setContentsMargins(0, 0, 0, 0)
        self.rightLayout.setSpacing(0)
        self.rightLayout.addWidget(self.badgeRow, 0, Qt.AlignTop)
        self.rightLayout.addStretch(1)
        self.rightLayout.addWidget(
            self.shareButton, 0, Qt.AlignBottom | Qt.AlignRight
        )

        self.textLayout.addWidget(self.nameVersionLabel)
        self.textLayout.addWidget(self.descLabel)

        self.hLayout.addWidget(self.iconLabel, 0, Qt.AlignTop)
        self.hLayout.addLayout(self.textLayout, 1)
        self.hLayout.addLayout(self.rightLayout, 0)

        # 初始 neutral：后台检测结果到达前两个徽章都隐藏（避免启动瞬间闪 MISS）
        self.readyBadge.setVisible(False)
        self.missBadge.setVisible(False)

    # ===== 提示文案（构建时经 translate_ui 翻译；语言切换后由 refresh_tips 重建） =====
    def _status_tip(self, head: str, body: str) -> str:
        """徽章状态提示：标题含工具名，无法整句查表，只能构建时拼装。"""
        return (
            f"<b>{escape(self.base_title)} {translate_ui(head)}</b><br/>"
            f"{translate_ui(body)}"
        )

    def _share_tip(self) -> str:
        return (
            f"<b>{escape(self.base_title)} · {translate_ui('官方网站')}</b><br/>"
            f"{escape(self.homepage)}<br/>"
            f"{translate_ui('点击在默认浏览器中打开')}"
        )

    def refresh_tips(self):
        """语言切换后重建三处 Fluent 提示（ToolTipFilter 动态读取 toolTip）。"""
        self.readyBadge.setToolTip(self._status_tip("已就绪", "检测通过，可正常参与解密"))
        self.missBadge.setToolTip(
            self._status_tip("缺失", "请检查工具文件，或在设置界面重新指定路径")
        )
        if self.homepage:
            self.shareButton.setToolTip(self._share_tip())

    def update_info(self, version: str, ready: bool = True):
        value = version
        if "um v" in version:
            value = version.replace("um ", "")
        elif version.lower().startswith("ffmpeg "):
            value = version.replace("ffmpeg ", "")

        self.nameVersionLabel.setText(f"{self.base_title} {value}")
        self._set_badge_state(ready)

    def set_detecting(self):
        """检测中状态：显示提示文本，徽章 neutral（后台检测结果到达前不亮灯）。"""
        self.nameVersionLabel.setText(f"{self.base_title} 检测中...")
        self.readyBadge.setVisible(False)
        self.missBadge.setVisible(False)

    def _set_badge_state(self, ready: bool):
        self.readyBadge.setVisible(ready)
        self.missBadge.setVisible(not ready)

    def _on_share_clicked(self):
        """右下角分享按钮：把官网地址交给 view 层打开（无地址时不响应）。"""
        if self.homepage:
            self.homepage_requested.emit(self.homepage)
