# coding: utf-8
"""全局信号总线 —— 解耦 view / service / components 之间的通信。

view 与 service 之间不持有对方引用，统一通过 ``signalBus`` 收发事件。
"""

from PySide6.QtCore import QObject, Signal


class SignalBus(QObject):
    """跨层事件总线（全局单例 ``signalBus``）。"""

    # ===== 转换控制（view → service） =====
    request_start = Signal()
    request_stop = Signal()

    # ===== 转换事件（service → view） =====
    conversion_started = Signal(int)          # total（本轮任务文件总数，供进度条计算）
    conversion_finished = Signal(int)        # exit_code
    file_started = Signal(str)              # file_path
    file_finished = Signal(str, bool)       # file_path, success
    log_emitted = Signal(str, str)          # message, level
    toast_requested = Signal(str, str)      # message, level（请求首页弹 InfoBar 浮层）

    # ===== 工具检测（service → home） =====
    tools_detected = Signal(str, bool, str, bool, str, bool)  # um_ver, um_ready, ff_ver, ff_ready, qmpc_ver, qmpc_ready

    # ===== 路径变更 / 队列管理 =====
    paths_changed = Signal()                # 输入/输出目录变更
    queue_remove = Signal(str)              # file_path（从解密待处理队列移除，移交出列表/删除）


signalBus = SignalBus()
