# coding: utf-8
"""主窗口 —— MSFluentWindow，持有 service 实例并装配各页面。"""

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication
from qfluentwidgets import FluentIcon, MSFluentWindow, NavigationItemPosition

from ..common.config import cfg
from ..common.logger import logger
from ..common.resource import binary
from ..common.signal_bus import signalBus
from ..service.converter import UnlockMusicConverter
from ..service.tool_detector import ToolDetector
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
        self.logInterface = LogInterface(self)
        self.settingInterface = SettingInterface(self)

        self.init_navigation()
        self.init_window()
        self.init_signals()

        # 首次刷新与工具检测
        self.homeInterface.refresh_paths()
        self.taskInterface.refresh_from_config()
        self.detector.detect()

    def init_navigation(self):
        self.addSubInterface(self.homeInterface, FluentIcon.HOME, "主界面")
        self.addSubInterface(self.taskInterface, FluentIcon.MUSIC, "任务管理")
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
            if input_dir and __import__("os").path.exists(input_dir):
                signalBus.log_emitted.emit(
                    f"列表为空，正在扫描输入目录: {input_dir}", "info"
                )
                self.taskInterface.scan_directory(input_dir)
                files = self.taskInterface.get_file_paths()
        # 真正启动转换
        self.converter.start(files)

    def on_exit(self):
        """应用退出前的清理钩子。"""
        try:
            self.converter.stop()
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"退出清理异常: {exc}")
