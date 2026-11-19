# coding: utf-8
"""主窗口 —— MSFluentWindow，持有 service 实例并装配各页面。"""

import os

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication
from qfluentwidgets import (
    FluentIcon,
    MSFluentWindow,
    NavigationItemPosition,
    SystemThemeListener,
    Theme,
    setTheme,
)

from ..common.config import cfg
from ..common.decrypt_scanner import classify_files
from ..common.logger import logger
from ..common.resource import image
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
        self.init_theme_listener()

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
        self.setWindowIcon(QIcon(image("um.ico")))
        desktop = QApplication.primaryScreen().availableGeometry()
        w, h = desktop.width(), desktop.height()
        self.move(w // 2 - self.width() // 2, h // 2 - self.height() // 2)

    def init_signals(self):
        # 首页"开始" → 取任务页文件交给转换服务
        signalBus.request_start.connect(self._dispatch_start)

    def init_theme_listener(self):
        """监听系统深浅色变化，实现「跟随系统」模式的实时换肤。

        官方 SystemThemeListener 在系统主题变化时只更新 qconfig.theme 并发
        themeChanged / systemThemeChanged，不会刷新全局控件样式表（QSS）。
        因此把 systemThemeChanged 接到 setTheme，由它调用 updateStyleSheet
        完成全体控件换肤；listener 内部已保证仅 themeMode==AUTO 时才触发。
        """
        self.themeListener = SystemThemeListener(self)
        self.themeListener.systemThemeChanged.connect(self._on_system_theme_changed)
        self._theme_listener_stopped = False
        self.themeListener.start()

    def _on_system_theme_changed(self):
        """系统主题变化 → 刷新全局样式表（listener 保证此时 themeMode==AUTO）。"""
        setTheme(Theme.AUTO)

    def _stop_theme_listener(self):
        """停止系统主题监听线程（幂等：closeEvent 与 on_exit 都会调用）。

        Windows 上 darkdetect.listener 是无限阻塞循环，无法用中断标志退出，
        只能 terminate()；随后 deleteLater() 交回事件循环清理 QThread 对象。
        """
        if self._theme_listener_stopped:
            return
        self._theme_listener_stopped = True
        listener = getattr(self, "themeListener", None)
        if listener is not None:
            listener.terminate()
            listener.deleteLater()

    def closeEvent(self, event):
        """关闭窗口时停止监听线程，避免 QThread 仍在运行时被销毁。"""
        self._stop_theme_listener()
        super().closeEvent(event)

    def _dispatch_start(self):
        files = self.taskInterface.get_file_paths()
        if not files:
            input_dir = cfg.input_dir.value
            if input_dir and os.path.isdir(input_dir):
                signalBus.log_emitted.emit(
                    f"列表为空，正在扫描输入目录: {input_dir}", "info"
                )
                # 任务页渐进建卡（不阻塞 UI）；本轮待处理路径取页面实际
                # 纳入的扫描结果（已应用用户移出 / 手工添加规则），
                # 不再依赖卡片是否已同步建完
                files = self.taskInterface.scan_directory(
                    input_dir, progressive=True
                )

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
        self._stop_theme_listener()
        try:
            self.converter.stop()
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"退出清理异常: {exc}")
