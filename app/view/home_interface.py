# coding: utf-8
"""主界面 —— 工具检测卡片 + 路径快捷卡片 + 开始/停止按钮。"""

import os
from pathlib import Path

from PySide6.QtCore import QFile, QSize, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QHBoxLayout
from qfluentwidgets import (
    CaptionLabel,
    FluentIcon,
    HorizontalFlipView,
    PrimaryPushButton,
    StrongBodyLabel,
    SubtitleLabel,
    TogglePushButton,
)

from ..common.config import cfg
from ..common.resource import image
from ..common.signal_bus import signalBus
from ..components.interface import Interface
from ..components.path_card import PathCard
from ..components.version_card import VersionCard, VersionCardView


class HomeInterface(Interface):
    """主界面（首页）。"""

    def __init__(self, parent=None):
        super().__init__("HomeInterface", parent)

        # Banner 轮播
        self.flipView = HorizontalFlipView(self)
        self.flipView.setFixedHeight(220)
        self.flipView.setBorderRadius(16)
        self.flipView.setItemSize(QSize(940, 220))
        self.flipView.setAspectRatioMode(Qt.KeepAspectRatioByExpanding)
        welcome_path = image("welcome.png")
        if QFile.exists(welcome_path):
            self.flipView.addImage(welcome_path)
            self.flipView.setCurrentIndex(0)
        self.vLayout.addWidget(self.flipView)

        # 标题区（单行紧凑：标题左、副标题右下对齐）
        self.heroLayout = QHBoxLayout()
        self.heroLayout.setContentsMargins(0, 0, 0, 0)
        self.heroTitle = SubtitleLabel("音乐解锁工具", self)
        self.heroSubtitle = CaptionLabel(
            "快速查看环境、打开目录并管理当前转换任务", self
        )
        self.heroLayout.addWidget(self.heroTitle)
        self.heroLayout.addStretch(1)
        self.heroLayout.addWidget(self.heroSubtitle, 0, Qt.AlignBottom)
        self.vLayout.addLayout(self.heroLayout)

        # 工具检测卡片（两卡均分，与下方路径卡片同构对齐）
        self.umCard = VersionCard("Unlock Music (um)", image("pwa.png"))
        self.ffmpegCard = VersionCard("FFmpeg", image("ffmpeg.png"))
        self.umCard.update_info("检测中...", "", False)
        self.ffmpegCard.update_info("检测中...", "", False)

        self.toolsTitle = StrongBodyLabel("工具检测", self)
        self.vLayout.addWidget(self.toolsTitle)

        self.toolsRow = QHBoxLayout()
        self.toolsRow.setContentsMargins(0, 0, 0, 0)
        self.toolsRow.setSpacing(20)
        self.toolsRow.addWidget(self.umCard, 1)
        self.toolsRow.addWidget(self.ffmpegCard, 1)
        self.vLayout.addLayout(self.toolsRow)

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

        # 开始 / 停止按钮（开始按钮用主题色填充，更醒目）
        self.buttonLayout = QHBoxLayout()
        self.buttonLayout.setSpacing(18)
        self.buttonLayout.setAlignment(Qt.AlignCenter)
        self.btnStart = PrimaryPushButton(self)
        self.btnStart.setCheckable(True)
        self.btnStart.setFixedSize(210, 46)
        self.btnStop = TogglePushButton("停止转换", self)
        self.btnStop.setFixedSize(210, 46)
        self.buttonLayout.addWidget(self.btnStart)
        self.buttonLayout.addWidget(self.btnStop)
        self.vLayout.addLayout(self.buttonLayout)

        self.vLayout.addStretch(1)

        self._connect_signals()
        self._set_button_state("idle")
        self.refresh_paths()

    def _connect_signals(self):
        self.btnStart.clicked.connect(self._on_start_clicked)
        self.btnStop.clicked.connect(self._on_stop_clicked)
        self.inputDirCard.clicked.connect(self._open_input_dir)
        self.outputDirCard.clicked.connect(self._open_output_dir)
        signalBus.tools_detected.connect(self._on_tools_detected)
        signalBus.conversion_started.connect(lambda: self._set_button_state("running"))
        signalBus.conversion_finished.connect(lambda *_: self._set_button_state("idle"))
        signalBus.paths_changed.connect(self.refresh_paths)

    # ----------------------------------------------------------- 事件处理
    def _on_start_clicked(self):
        if self._button_state == "idle":
            signalBus.request_start.emit()
        else:
            self.btnStart.setChecked(True)

    def _on_stop_clicked(self):
        if self._button_state == "running":
            signalBus.request_stop.emit()
            self._set_button_state("stopping")
        self.btnStop.setChecked(self._button_state == "running")

    def _on_tools_detected(self, um_ver, um_ready, ff_ver, ff_ready):
        um_path = cfg.um_path.value
        ff_path = cfg.ffmpeg_path.value
        self.umCard.update_info(um_ver, um_path, um_ready)
        self.ffmpegCard.update_info(ff_ver, ff_path, ff_ready)

    def _open_input_dir(self):
        self._open_directory(cfg.input_dir.value, "输入目录")

    def _open_output_dir(self):
        self._open_directory(cfg.output_dir.value, "输出目录")

    @staticmethod
    def _open_directory(path, label):
        if not path or not os.path.isdir(path):
            signalBus.log_emitted.emit(f"{label}未设置或路径不存在。", "warning")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    # ----------------------------------------------------------- 状态更新
    def refresh_paths(self):
        self.inputDirCard.set_path(cfg.input_dir.value, "未设置输入目录")
        self.outputDirCard.set_path(cfg.output_dir.value, "未设置输出目录")

    def _set_button_state(self, state: str):
        self._button_state = state

        if state == "running":
            self.btnStart.setEnabled(True)
            self.btnStart.setText("转换中")
            self.btnStart.setIcon(FluentIcon.PAUSE)
            self.btnStart.setChecked(True)
            self.btnStop.setEnabled(True)
            self.btnStop.setIcon(FluentIcon.CANCEL)
            self.btnStop.setChecked(False)
            return

        if state == "stopping":
            self.btnStart.setEnabled(False)
            self.btnStart.setText("正在收尾...")
            self.btnStart.setIcon(FluentIcon.SYNC)
            self.btnStart.setChecked(True)
            self.btnStop.setEnabled(False)
            self.btnStop.setIcon(FluentIcon.CANCEL)
            self.btnStop.setChecked(True)
            return

        self.btnStart.setEnabled(True)
        self.btnStart.setText("开始转换")
        self.btnStart.setIcon(FluentIcon.PLAY)
        self.btnStart.setChecked(False)
        self.btnStop.setEnabled(False)
        self.btnStop.setText("停止转换")
        self.btnStop.setIcon(FluentIcon.CANCEL)
        self.btnStop.setChecked(False)
