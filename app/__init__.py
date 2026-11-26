# coding: utf-8
"""Unlock Music GUI — 基于 PySide6 + QFluentWidgets 的分层应用包。

分层组织（依赖方向自下而上，下层不得反向 import 上层）：

- ``common``     基础设施 + 无状态纯逻辑层
                 配置 / 信号总线 / 日志 / 国际化 / 资源 / 工具函数，
                 以及**不持有 Qt 对象生命周期、不向 signalBus 广播事件**的
                 纯业务逻辑——含外部进程的无状态封装（解密流程编排、ffmpeg
                 编码器 / 元数据探测、封面与标签解析、任务规划、目录扫描
                 归类等）。这些模块可脱离事件循环单独调用与单测，故归入
                 common 而非 service。
- ``components`` 可复用 UI 组件层（自定义控件、卡片、对话框、网格容器基类）。
                 只依赖 common 与同层组件，经信号 / 回调与上层解耦，
                 自身不广播 signalBus、不管理业务进程生命周期。
- ``service``    有状态的 Qt 应用服务层
                 QObject 子类，持有 QProcess / 线程池等生命周期，经 signalBus
                 与 view 双向收发领域事件（如批量解密调度、工具链检测）。
                 纯逻辑 / 无状态进程封装留给 common，本层只做编排与事件桥接。
- ``view``       界面层（主窗口与各页面）：装配 components、持有 service 实例、
                 桥接信号总线，只负责呈现与用户交互编排。
- ``resource``   静态资源（图片 / 翻译文件经 qrc 编译内嵌，运行时以 ``:/`` 访问）。
"""

import contextlib
import io

# 屏蔽 QFluentWidgets Pro 推广输出（必须位于任何 qfluentwidgets 导入之前）
with contextlib.redirect_stdout(io.StringIO()):
    import qfluentwidgets.common.config  # noqa: F401

# 注册 Qt 资源（resource/img/ 下的图片经 qrc 编译后用 :/img/... 访问）
from .resource import resource_rc  # noqa: F401  pylint: disable=wrong-import-position
