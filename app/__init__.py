# coding: utf-8
"""Unlock Music GUI — 基于 PySide6 + QFluentWidgets 的分层应用包。

分层组织：
- ``common``     基础设施层（配置 / 信号总线 / 日志 / 资源 / 工具）
- ``components`` 可复用 UI 组件层
- ``service``   业务服务层（封装外部进程与业务逻辑）
- ``view``      界面层（主窗口与各页面）
- ``resource``  静态资源
"""

import contextlib
import io

# 屏蔽 QFluentWidgets Pro 推广输出（必须位于任何 qfluentwidgets 导入之前）
with contextlib.redirect_stdout(io.StringIO()):
    import qfluentwidgets.common.config  # noqa: F401

# 注册 Qt 资源（img/ 下的图片经 qrc 编译后用 :/img/... 访问）
from . import resource_rc  # noqa: F401  pylint: disable=wrong-import-position
