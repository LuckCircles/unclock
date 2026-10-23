# coding: utf-8
"""主窗口 —— MSFluentWindow，持有 service 实例并装配各页面。"""

import os

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication
from qfluentwidgets import FluentIcon, MSFluentWindow, NavigationItemPosition

from ..common.config import cfg
from ..common.decrypt_scanner import classify_files
from ..common.logger import logger
from ..common.resource import binary
from ..common.signal_bus import signalBus
from ..service.converter import UnlockMusicConverter
from ..service.tool_detector import ToolDetector
from .decrypted_interface import DecryptedInterface
from .home_interface import HomeInterface
from .log_interface import LogInterface
from .setting_interface import SettingInterface
from .task_interface import TaskInterface


class MainWindow(MSFluentWindow):
    """应用主窗口。"""

    def __init__(self):
        super().__init__()
        self.config = cfg

        # 业务服务（持有实例以保证生命周期，并桥接信号总线）
        self.converter = UnlockMusicConverter(self)
        self.detector = ToolDetector(self)

        # 页面
        self.homeInterface = HomeInterface(self)
        self.taskInterface = TaskInterface(self)
        self.decryptedInterface = DecryptedInterface(self)
        self.logInterface = LogInterface(self)
        self.settingInterface = SettingInterface(self)

        self.init_navigation()
        self.init_window()
        self.init_signals()

        # 首次刷新与工具检测
        self.homeInterface.refresh_paths()
        # 任务页/已解密页的首次建卡由各自界面延后执行（启动关键路径只留窗口骨架）：
        # 任务页 __init__ 内 singleShot 分批渐进扫描；已解密页首次切入时才建卡。
        # 工具检测移入后台线程池：不阻塞启动，结果经信号总线异步更新首页卡片。
        self.detector.detect_async()

    def init_navigation(self):
        self.addSubInterface(self.homeInterface, FluentIcon.HOME, "主界面")
        self.addSubInterface(self.taskInterface, FluentIcon.MUSIC, "任务管理")
        self.addSubInterface(self.decryptedInterface, FluentIcon.COMPLETED, "已解密")
        self.addSubInterface(self.logInterface, FluentIcon.DOCUMENT, "运行日志")
        self.addSubInterface(
            self.settingInterface, FluentIcon.SETTING, "配置界面",
            position=NavigationItemPosition.BOTTOM,
        )

    def init_window(self):
        self.resize(1080, 760)
        self.setWindowTitle("音乐解锁工具 - Fluent UI")
        self.setWindowIcon(QIcon(binary("img/pwa.ico")))
        desktop = QApplication.primaryScreen().availableGeometry()
        w, h = desktop.width(), desktop.height()
        self.move(w // 2 - self.width() // 2, h // 2 - self.height() // 2)

    def init_signals(self):
        # 首页"开始" → 取任务页文件交给转换服务
        signalBus.request_start.connect(self._dispatch_start)

    def _dispatch_start(self):
        files = self.taskInterface.get_file_paths()
        if not files:
            input_dir = cfg.input_dir.value
            if input_dir and os.path.exists(input_dir):
                signalBus.log_emitted.emit(
                    f"列表为空，正在扫描输入目录: {input_dir}", "info"
                )
                self.taskInterface.scan_directory(input_dir)
                files = self.taskInterface.get_file_paths()

        # 输入/输出目录对比：扫描输出目录建「已解密基名集合」，遍历文件分类汇总
        decrypted, pending, skipped = classify_files(files, cfg.output_dir.value)
        total_enc = len(decrypted) + len(pending)
        if skipped:
            signalBus.log_emitted.emit(
                f"已跳过 {len(skipped)} 个非加密文件。", "info"
            )
        signalBus.log_emitted.emit(
            f"检测到加密文件 {total_enc} 个：已解密 {len(decrypted)}，待解密 {len(pending)}。",
            "info",
        )

        # 覆盖已转换：开启 → 解密全部加密文件；关闭 → 仅解密未解密文件
        if cfg.reconvert_done.value:
            to_convert = decrypted + pending
        else:
            to_convert = pending
            if decrypted:
                signalBus.log_emitted.emit(
                    f"已跳过 {len(decrypted)} 个已解密文件（开启“覆盖已转换”可重新解密）。",
                    "info",
                )

        if not to_convert:
            signalBus.toast_requested.emit("没有待解密的文件。", "warning")
            return

        # 真正启动解密
        self.converter.start(to_convert)

    def on_exit(self):
        """应用退出前的清理钩子。"""
        try:
            self.converter.stop()
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"退出清理异常: {exc}")
