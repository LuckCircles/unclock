# coding: utf-8
"""配置页面 —— 路径与转换选项设置。"""

from PySide6.QtWidgets import QFileDialog
from qfluentwidgets import (
    ComboBoxSettingCard,
    FluentIcon,
    PushSettingCard,
    SettingCardGroup,
    SwitchSettingCard,
    ToolTipFilter,
    ToolTipPosition,
    qconfig,
    setTheme,
)

from ..common.config import CONVERSION_OPTIONS, cfg
from ..common.signal_bus import signalBus
from ..components.interface import Interface


class SettingInterface(Interface):
    """配置页面。"""

    def __init__(self, parent=None):
        super().__init__("SettingInterface", parent)

        # ===== 外观设置 =====
        # 与转换设置统一用 ComboBoxSettingCard：绑定库内置 themeMode（枚举型
        # OptionsConfigItem），下拉项 texts 与 config.py 重排后的
        # options（AUTO/LIGHT/DARK）一一对应。qconfig.set 只写配置 + 发
        # themeChanged，另接 comboBox 信号到 setTheme 刷新全局 QSS。
        self.appearanceGroup = SettingCardGroup("外观设置", self.view)
        self.themeCard = ComboBoxSettingCard(
            qconfig.themeMode, FluentIcon.BRUSH, "主题",
            "跟随系统：自动采用系统浅色/深色偏好；也可手动指定。",
            ["跟随系统", "浅色模式", "深色模式"], self.appearanceGroup,
        )
        self.appearanceGroup.addSettingCard(self.themeCard)
        self.vLayout.addWidget(self.appearanceGroup)

        # ===== 基础设置 =====
        self.basicGroup = SettingCardGroup("基础设置", self.view)
        # 解密引擎选择：选项文本顺序必须与 config.py 的 OptionsValidator 一致
        # （"um" → "um-cli-rs"）。qconfig 由卡片内部写入并持久化。
        self.engineCard = ComboBoxSettingCard(
            cfg.decrypt_engine, FluentIcon.COMMAND_PROMPT, "解密工具",
            "默认使用 um 链路，可切换为官方 Rust 工具 um-cli-rs。",
            ["um", "um-cli-rs"], self.view,
        )
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
        self.qmpcPathCard = PushSettingCard(
            "选择文件", FluentIcon.COMMAND_PROMPT, "qmpc-mmkv-cli 路径",
            cfg.qmpc_path.value, self.view,
        )
        self.umCliRsPathCard = PushSettingCard(
            "选择文件", FluentIcon.COMMAND_PROMPT, "um-cli-rs 路径",
            cfg.um_cli_rs_path.value, self.view,
        )
        for card in (
            self.engineCard, self.inputCard, self.outputCard, self.umPathCard,
            self.ffmpegPathCard, self.qmpcPathCard, self.umCliRsPathCard,
        ):
            self.basicGroup.addSettingCard(card)
        self.vLayout.addWidget(self.basicGroup)

        # 「选择目录 / 选择文件」按钮提示：Fluent ToolTip（进入 300ms 显示）
        self._buttonTips = []
        for btn, tip in (
            (self.inputCard.button, "<b>选择目录</b><br/>设置加密音乐所在的输入目录"),
            (self.outputCard.button, "<b>选择目录</b><br/>设置解密结果的输出目录"),
            (self.umPathCard.button, "<b>选择文件</b><br/>指定 um.exe 的路径"),
            (self.ffmpegPathCard.button, "<b>选择文件</b><br/>指定 ffmpeg.exe 的路径"),
            (self.qmpcPathCard.button, "<b>选择文件</b><br/>指定 qmpc-mmkv-cli.exe 的路径"),
            (self.umCliRsPathCard.button, "<b>选择文件</b><br/>指定 um_cli_rs.exe 的路径（选择 Rust 引擎时使用）"),
        ):
            btn.setToolTip(tip)
            btn.setToolTipDuration(-1)  # 鼠标移开才隐藏
            tip_filter = ToolTipFilter(
                btn, showDelay=300, position=ToolTipPosition.TOP
            )
            btn.installEventFilter(tip_filter)
            self._buttonTips.append(tip_filter)

        # ===== 转换设置 =====
        self.convGroup = SettingCardGroup("转换设置", self.view)
        # 选项元数据由 common 层提供，service 与 view 共用同一份，避免参数/默认值漂移
        for config_item, label, arg, um_default_on in CONVERSION_OPTIONS:
            hint = f"对应参数: {arg} · um 默认: {'开启' if um_default_on else '关闭'}"
            if um_default_on:
                # um 未提供关闭参数：明确告知用户「否」无法关闭，避免静默误导
                hint += "（无关闭参数，选“否”仍按默认执行）"
            card = ComboBoxSettingCard(
                config_item, FluentIcon.SETTING, label,
                hint, ["否", "是", "默认"], self.convGroup,
            )
            self.convGroup.addSettingCard(card)
        self.vLayout.addWidget(self.convGroup)

        # ===== 任务行为 =====
        self.behaviorGroup = SettingCardGroup("任务行为", self.view)
        self.reconvertCard = SwitchSettingCard(
            FluentIcon.SYNC, "覆盖已转换",
            "开启后重新解密已成功解密的文件；关闭则自动跳过已解密文件，仅处理待解密/失败项。",
            cfg.reconvert_done, self.behaviorGroup,
        )
        self.behaviorGroup.addSettingCard(self.reconvertCard)
        self.vLayout.addWidget(self.behaviorGroup)

        self.vLayout.addStretch(1)

        # 信号
        # 下拉框变化仅写入 themeMode 配置，需显式 setTheme 刷新全部控件样式表
        self.themeCard.comboBox.currentIndexChanged.connect(self._on_theme_changed)
        self.inputCard.clicked.connect(self._select_input)
        self.outputCard.clicked.connect(self._select_output)
        self.umPathCard.clicked.connect(self._select_um)
        self.ffmpegPathCard.clicked.connect(self._select_ffmpeg)
        self.qmpcPathCard.clicked.connect(self._select_qmpc)
        self.umCliRsPathCard.clicked.connect(self._select_um_cli_rs)

    def _on_theme_changed(self, index):
        """应用主题：setTheme 内部刷新全局样式表并持久化 themeMode。

        下拉项 userData 存的是 Theme 枚举（ComboBoxSettingCard 写入 options）；
        qconfig.set 已由卡片内部先执行，这里补做全局 QSS 刷新。
        """
        if index < 0:
            return
        setTheme(self.themeCard.comboBox.itemData(index))

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

    def _select_qmpc(self):
        file, _ = QFileDialog.getOpenFileName(
            self, "选择 qmpc-mmkv-cli.exe", "", "Executable (*.exe)"
        )
        if file:
            qconfig.set(cfg.qmpc_path, file)
            self.qmpcPathCard.setContent(file)

    def _select_um_cli_rs(self):
        file, _ = QFileDialog.getOpenFileName(
            self, "选择 um_cli_rs.exe", "", "Executable (*.exe)"
        )
        if file:
            qconfig.set(cfg.um_cli_rs_path, file)
            self.umCliRsPathCard.setContent(file)
