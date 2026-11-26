# coding: utf-8
"""图标集中定义 —— FluentIcon 别名 + 自定义平台图标。

自定义图标遵循 QFluentWidgets 官方「添加图标」范式
（https://qfluentwidgets.com/zh/pages/icon/）：继承 ``FluentIconBase`` + ``Enum``，
重写 ``path()`` 返回 ``:/`` 开头的 qrc 资源路径，即可作为图标参数传给任意
接受 ``FluentIconBase`` 的官方组件。

与普通 FluentIcon（黑白 SVG、随主题换色）不同：平台 logo 是彩色 PNG，
``path()`` 忽略 theme 参数、始终返回同一路径，避免主题切换时被错误着色。
所需图片经 ``app/resource/resource.qrc`` 编译进 ``app/resource/resource_rc.py``。
"""

from enum import Enum

from qfluentwidgets import FluentIcon as FIcon
from qfluentwidgets import FluentIconBase, Theme

__all__ = ["FIcon", "PlatformIcon"]


class PlatformIcon(FluentIconBase, Enum):
    """音乐平台图标（qrc 资源 ``:/img/<name>.png``）。

    可直接传给接受 ``FluentIconBase`` 的组件；也可调用 ``icon()`` / ``qicon()``
    得到 ``QIcon``。``path()`` 返回 ``:/`` 资源路径，不依赖文件系统。
    """

    QQ_MUSIC = "QQMusic"
    NETEASE_CLOUD = "WangYiYun_Music"
    KUGOU = "KuGou_Music"
    KUWO = "KuWo_Music"
    XIMALAYA = "XM_Music"
    QISHUI = "QiShui_Music"  # 预留：um v0.2.20 无独立汽水格式

    def path(self, theme=Theme.AUTO) -> str:
        """返回 qrc 资源路径。

        官方 SVG 图标用 ``getIconColor(theme)`` 切黑/白版本；平台 logo 为彩色
        PNG，与主题无关，故忽略 ``theme``，任何时候都返回同一 ``:/`` 路径。
        """
        return f":/img/{self.value}.png"
