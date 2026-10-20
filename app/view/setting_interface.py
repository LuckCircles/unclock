# coding: utf-8
"""配置页面 —— 路径与转换选项设置。"""

from PySide6.QtWidgets import QFileDialog
from qfluentwidgets import (
    FluentIcon,
    OptionsSettingCard,
    OptionsValidator,
    PushSettingCard,
    SettingCardGroup,
    qconfig,
)

from ..common.config import cfg
from ..common.signal_bus import signalBus
from ..components.interface import Interface


class SettingInterface(Interface):
    """配置页面。"""

    def __init__(self, parent=None):
        super().__init__("SettingInterface", parent)

        # ===== 基础设置 =====
        self.basicGroup = SettingCardGroup("基础设置", self.view)
        self.inputCard = PushSettingCard(
            "选择目录", FluentIcon.FOLDER, "输入目录",
            cfg.input_dir.value or "未设置", self.view,
        )
        self.outputCard = PushSettingCard(
            "选择目录", FluentIcon.FOLDER, "输出目录",
            cfg.output_dir.value or "未设置", self.view,
        )
        self.umPathCard = PushSettingCard(
            "选择文件", FluentIcon.COMMAND_PROMPT, "um 路径",
            cfg.um_path.value, self.view,
        )
        self.ffmpegPathCard = PushSettingCard(
            "选择文件", FluentIcon.VIDEO, "ffmpeg 路径",
            cfg.ffmpeg_path.value, self.view,
        )
        for card in (self.inputCard, self.outputCard, self.umPathCard, self.ffmpegPathCard):
            self.basicGroup.addSettingCard(card)
        self.vLayout.addWidget(self.basicGroup)

        # ===== 转换设置 =====
        self.convGroup = SettingCardGroup("转换设置", self.view)
        options_meta = [
            (cfg.remove_source, "删除源文件", "--rs"),
            (cfg.verbose, "详细输出", "-V"),
            (cfg.overwrite, "覆盖输出", "--overwrite"),
            (cfg.watch, "监听输入目录", "--watch"),
            (cfg.update_metadata, "更新封面", "--update-metadata"),
            (cfg.skip_noop, "跳过无动作解码器", "-n"),
        ]
        for config_item, label, arg in options_meta:
            card = OptionsSettingCard(
                config_item, FluentIcon.SETTING, label,
                f"对应参数: {arg}", ["否", "是", "默认"], self.convGroup,
            )
            self.convGroup.addSettingCard(card)
        self.vLayout.addWidget(self.convGroup)
        self.vLayout.addStretch(1)

        # 信号
        self.inputCard.clicked.connect(self._select_input)
        self.outputCard.clicked.connect(self._select_output)
        self.umPathCard.clicked.connect(self._select_um)
        self.ffmpegPathCard.clicked.connect(self._select_ffmpeg)

    def _select_input(self):
        folder = QFileDialog.getExistingDirectory(self, "选择输入目录")
        if not folder:
            return
        qconfig.set(cfg.input_dir, folder)
        self.inputCard.setContent(folder)
        signalBus.paths_changed.emit()

    def _select_output(self):
        folder = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if not folder:
            return
        qconfig.set(cfg.output_dir, folder)
        self.outputCard.setContent(folder)
        signalBus.paths_changed.emit()

    def _select_um(self):
        file, _ = QFileDialog.getOpenFileName(
            self, "选择 um.exe", "", "Executable (*.exe)"
        )
        if file:
            qconfig.set(cfg.um_path, file)
            self.umPathCard.setContent(file)

    def _select_ffmpeg(self):
        file, _ = QFileDialog.getOpenFileName(
            self, "选择 ffmpeg.exe", "", "Executable (*.exe)"
        )
        if file:
            qconfig.set(cfg.ffmpeg_path, file)
            self.ffmpegPathCard.setContent(file)
