# coding: utf-8
"""主界面 —— 工具检测卡片 + 路径快捷卡片 + 开始/停止按钮。"""

import os

from PySide6.QtCore import QFile, QSize, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QGridLayout, QHBoxLayout
from qfluentwidgets import (
    CaptionLabel,
    CardWidget,
    FluentIcon,
    HorizontalFlipView,
    InfoBar,
    InfoBarPosition,
    PrimaryPushButton,
    ProgressBar,
    StrongBodyLabel,
)

from ..common.config import cfg
from ..common.resource import image
from ..common.signal_bus import signalBus
from ..components.interface import Interface
from ..components.path_card import PathCard
from ..components.version_card import VersionCard


class AutoResizeFlipView(HorizontalFlipView):
    """item 尺寸跟随自身宽度的 Banner 轮播（全屏不露边）。"""

    def __init__(self, parent=None):
        super().__init__(parent)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.setItemSize(self.size())


class HomeInterface(Interface):
    """主界面（首页）。"""

    def __init__(self, parent=None):
        super().__init__("HomeInterface", parent)

        # Banner 轮播（item 宽度自适应视口，全屏时铺满不裁边）
        self.flipView = AutoResizeFlipView(self)
        self.flipView.setFixedHeight(220)
        self.flipView.setBorderRadius(16)
        self.flipView.setAspectRatioMode(Qt.KeepAspectRatioByExpanding)
        welcome_path = image("welcome.png")
        if QFile.exists(welcome_path):
            self.flipView.addImage(welcome_path)
            self.flipView.setCurrentIndex(0)
        self.vLayout.addWidget(self.flipView)

        # 工具检测卡片（三卡均分，与下方路径卡片同构对齐）
        self.umCard = VersionCard(
            "Unlock Music (um)", image("pwa.png"), "音乐解锁核心引擎"
        )
        self.ffmpegCard = VersionCard(
            "FFmpeg", image("ffmpeg.png"), "音频转码 / 元数据写入"
        )
        self.qmpcCard = VersionCard(
            "QMPC MMKV", image("fliew.png"), "QQ 音乐密钥自动提取"
        )
        self.umCard.set_detecting()
        self.ffmpegCard.set_detecting()
        self.qmpcCard.set_detecting()

        self.toolsTitle = StrongBodyLabel("工具检测", self)
        self.vLayout.addWidget(self.toolsTitle)

        # 网格布局：一行两个，强制同列等宽对齐
        self.toolsGrid = QGridLayout()
        self.toolsGrid.setContentsMargins(0, 0, 0, 0)
        self.toolsGrid.setHorizontalSpacing(20)
        self.toolsGrid.setVerticalSpacing(12)
        self.toolsGrid.addWidget(self.umCard, 0, 0)
        self.toolsGrid.addWidget(self.ffmpegCard, 0, 1)
        self.toolsGrid.addWidget(self.qmpcCard, 1, 0)
        self.toolsGrid.setColumnStretch(0, 1)
        self.toolsGrid.setColumnStretch(1, 1)
        self.vLayout.addLayout(self.toolsGrid)

        # 目录快捷卡片（与工具行同构，均分对齐）
        self.pathsTitle = StrongBodyLabel("目录", self)
        self.vLayout.addWidget(self.pathsTitle)

        self.pathCardsLayout = QHBoxLayout()
        self.pathCardsLayout.setContentsMargins(0, 0, 0, 0)
        self.pathCardsLayout.setSpacing(20)
        self.inputDirCard = PathCard(
            "输入目录", "未设置输入目录", FluentIcon.FOLDER, self
        )
        self.outputDirCard = PathCard(
            "输出目录", "未设置输出目录", FluentIcon.MUSIC_FOLDER, self
        )
        self.pathCardsLayout.addWidget(self.inputDirCard, 1)
        self.pathCardsLayout.addWidget(self.outputDirCard, 1)
        self.vLayout.addLayout(self.pathCardsLayout)

        # 转换控制卡片（左侧进度条 + 右侧开始/停止合并按钮）
        self.controlCard = CardWidget(self)
        self.controlLayout = QHBoxLayout(self.controlCard)
        self.controlLayout.setContentsMargins(18, 14, 18, 14)
        self.controlLayout.setSpacing(16)

        self.progressText = CaptionLabel("就绪", self)
        self.progressBar = ProgressBar(self)
        self.btnAction = PrimaryPushButton(FluentIcon.PLAY, "开始解密", self)
        self.btnAction.setFixedSize(160, 36)

        self.controlLayout.addWidget(self.progressText, 0, Qt.AlignVCenter)
        self.controlLayout.addWidget(self.progressBar, 1)
        self.controlLayout.addWidget(self.btnAction, 0, Qt.AlignRight)
        self.vLayout.addWidget(self.controlCard)

        self.vLayout.addStretch(1)

        # 进度跟踪状态
        self._total_files = 0
        self._done_files = 0

        self._connect_signals()
        self._set_button_state("idle")
        self.refresh_paths()

    def _connect_signals(self):
        self.btnAction.clicked.connect(self._on_action_clicked)
        self.inputDirCard.clicked.connect(self._open_input_dir)
        self.outputDirCard.clicked.connect(self._open_output_dir)
        signalBus.tools_detected.connect(self._on_tools_detected)
        signalBus.toast_requested.connect(self._show_toast)
        signalBus.conversion_started.connect(self._on_conversion_started)
        signalBus.file_finished.connect(self._on_file_progress)
        signalBus.conversion_finished.connect(lambda *_: self._set_button_state("idle"))
        signalBus.paths_changed.connect(self.refresh_paths)

    # ----------------------------------------------------------- 事件处理
    def _on_action_clicked(self):
        """合并按钮：idle → 开始；running → 停止。"""
        if self._button_state == "idle":
            signalBus.request_start.emit()
        elif self._button_state == "running":
            signalBus.request_stop.emit()
            self._set_button_state("stopping")

    def _on_tools_detected(self, um_ver, um_ready, ff_ver, ff_ready, qmpc_ver, qmpc_ready):
        self.umCard.update_info(um_ver, um_ready)
        self.ffmpegCard.update_info(ff_ver, ff_ready)
        self.qmpcCard.update_info(qmpc_ver, qmpc_ready)

    def _open_input_dir(self):
        self._open_directory(cfg.input_dir.value, "输入目录")

    def _open_output_dir(self):
        self._open_directory(cfg.output_dir.value, "输出目录")

    def _open_directory(self, path, label):
        if not path or not os.path.isdir(path):
            self._show_toast(f"{label}未设置或路径不存在", "warning")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def _show_toast(self, message: str, level: str):
        """在主窗口右上角弹 InfoBar 浮层提示。"""
        bar_cls = {
            "error": InfoBar.error,
            "success": InfoBar.success,
        }.get(level, InfoBar.warning)
        bar_cls(
            title="提示",
            content=message,
            orient=Qt.Horizontal,
            isClosable=True,
            duration=3000,
            position=InfoBarPosition.TOP_RIGHT,
            parent=self.window(),
        )

    # ----------------------------------------------------------- 状态更新
    def refresh_paths(self):
        self.inputDirCard.set_path(cfg.input_dir.value, "未设置输入目录")
        self.outputDirCard.set_path(cfg.output_dir.value, "未设置输出目录")

    def _on_conversion_started(self, total: int):
        """新一轮任务开始：重置进度并切到 running 态。"""
        self._total_files = max(total, 1)
        self._done_files = 0
        self.progressBar.setMinimum(0)
        self.progressBar.setMaximum(self._total_files)
        self.progressBar.setValue(0)
        self._update_progress_text()
        self._set_button_state("running")

    def _on_file_progress(self, _path: str, _success: bool):
        """单个文件处理完成：推进进度条。"""
        self._done_files = min(self._done_files + 1, self._total_files)
        self.progressBar.setValue(self._done_files)
        self._update_progress_text()

    def _update_progress_text(self):
        self.progressText.setText(f"{self._done_files} / {self._total_files}")

    def _set_button_state(self, state: str):
        """合并按钮三态：idle=开始转换，running=停止转换，stopping=收尾中。"""
        self._button_state = state

        if state == "running":
            self.btnAction.setEnabled(True)
            self.btnAction.setText("停止解密")
            self.btnAction.setIcon(FluentIcon.CANCEL)
            return

        if state == "stopping":
            self.btnAction.setEnabled(False)
            self.btnAction.setText("正在收尾...")
            self.btnAction.setIcon(FluentIcon.SYNC)
            return

        self.btnAction.setEnabled(True)
        self.btnAction.setText("开始解密")
        self.btnAction.setIcon(FluentIcon.PLAY)
