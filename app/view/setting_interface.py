# coding: utf-8
"""配置页面 —— 路径与转换选项设置。"""

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QFileDialog
from qfluentwidgets import (
    ComboBoxSettingCard,
    FluentIcon,
    PushSettingCard,
    SettingCard,
    SettingCardGroup,
    SpinBox,
    SwitchSettingCard,
    ToolTipFilter,
    ToolTipPosition,
    qconfig,
    setTheme,
)

from ..common.config import CONVERSION_OPTIONS, cfg
from ..common.encoder_probe import probe_encoders, supported_hint
from ..common.i18n import apply_language, register_retranslate_hook, translate_ui
from ..common.signal_bus import signalBus
from ..components.interface import Interface


class SpinBoxSettingCard(SettingCard):
    """带 Fluent 数字输入框的设置卡（库里只有滑块卡，无法表达 0/负数取 CPU 核数）。"""

    def __init__(self, config_item, icon, title, content, minimum, maximum, parent=None):
        super().__init__(icon, title, content, parent)
        self.configItem = config_item
        self.spinBox = SpinBox(self)
        self.spinBox.setRange(minimum, maximum)
        self.spinBox.setValue(int(config_item.value))
        self.spinBox.setFixedWidth(120)
        # hBoxLayout 末尾已有 stretch，追加控件即靠右对齐，与 SwitchSettingCard 一致
        self.hBoxLayout.addWidget(self.spinBox, 0, Qt.AlignRight)
        self.hBoxLayout.addSpacing(16)
        self.spinBox.valueChanged.connect(self._on_value_changed)

    def _on_value_changed(self, value: int):
        qconfig.set(self.configItem, value)


class ChineseSwitchSettingCard(SwitchSettingCard):
    """开关文案中文化。

    库内 ``setValue`` 会强制写回 On/Off，仅构造时调 setOnText/setOffText
    会在首次切换后失效，因此覆盖 setValue 一并重设中文文案。
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_switch_text()

    def _apply_switch_text(self):
        self.switchButton.setOnText("开")
        self.switchButton.setOffText("关")

    def setValue(self, isChecked: bool):
        super().setValue(isChecked)
        self._apply_switch_text()


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
        self.languageCard = ComboBoxSettingCard(
            cfg.language, FluentIcon.LANGUAGE, "语言",
            "中文：始终使用简体中文；英文：始终使用英文；自动：跟随系统语言。",
            ["中文", "英文", "自动"], self.appearanceGroup,
        )
        cfg.language.valueChanged.connect(self._on_language_changed)
        self.appearanceGroup.addSettingCard(self.themeCard)
        self.appearanceGroup.addSettingCard(self.languageCard)
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
        self.tempDirCard = PushSettingCard(
            "选择目录", FluentIcon.FOLDER, "临时目录",
            cfg.temp_dir.value or "系统临时目录（未指定）", self.view,
        )
        for card in (
            self.engineCard, self.inputCard, self.outputCard, self.umPathCard,
            self.ffmpegPathCard, self.qmpcPathCard, self.umCliRsPathCard,
            self.tempDirCard,
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
            (self.tempDirCard.button, "<b>选择目录</b><br/>转换产生的中间文件会保存在这里；不选则使用系统临时目录"),
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
        self._convCards: list[tuple[ComboBoxSettingCard, str, bool]] = []
        for config_item, label, arg, um_default_on in CONVERSION_OPTIONS:
            card = ComboBoxSettingCard(
                config_item, FluentIcon.SETTING, label,
                self._conv_hint(arg, um_default_on), ["否", "是", "默认"], self.convGroup,
            )
            self._convCards.append((card, arg, um_default_on))
            self.convGroup.addSettingCard(card)
        self.vLayout.addWidget(self.convGroup)

        # ===== 任务行为 =====
        self.behaviorGroup = SettingCardGroup("任务行为", self.view)
        self.parallelCard = ChineseSwitchSettingCard(
            FluentIcon.PLAY, "并行转换",
            "开启后多个文件可同时解密；关闭则按顺序串行处理。",
            cfg.parallel_enabled, self.behaviorGroup,
        )
        self.parallelCountCard = SpinBoxSettingCard(
            cfg.parallel_count, FluentIcon.SETTING, "并行数量",
            "0 或负数表示使用 CPU 核心数；实际执行时大于 256 按 256 计。",
            -1, 256, self.behaviorGroup,
        )
        self.reconvertCard = ChineseSwitchSettingCard(
            FluentIcon.SYNC, "覆盖已转换",
            "开启后重新解密已成功解密的文件；关闭则自动跳过已解密文件，仅处理待解密/失败项。",
            cfg.reconvert_done, self.behaviorGroup,
        )
        for card in (self.parallelCard, self.parallelCountCard, self.reconvertCard):
            self.behaviorGroup.addSettingCard(card)
        self.vLayout.addWidget(self.behaviorGroup)

        # ===== 编码设置 =====
        # 当前解密链路不转码，编码器选择先落地为策略配置；探测结果在此如实展示。
        self.encodingGroup = SettingCardGroup("编码设置", self.view)
        self.ffmpegEncoderCard = SettingCard(
            FluentIcon.VIDEO, "FFmpeg",
            "正在探测可用编码器...", self.encodingGroup,
        )
        self.aacCard = ComboBoxSettingCard(
            cfg.aac_encoder, FluentIcon.MUSIC, "AAC 编码器",
            "自动选择按 libfdk_aac → aac 降级；显式选择要求 ffmpeg 支持。",
            ["自动选择", "libfdk_aac", "aac"], self.encodingGroup,
        )
        self.fdkVbrCard = ChineseSwitchSettingCard(
            FluentIcon.SETTING, "FDK 编码器：使用动态码率 (VBR)",
            "开启用 VBR 5，关闭用固定 192k；仅 libfdk_aac 生效。",
            cfg.fdk_vbr, self.encodingGroup,
        )
        self.oggCard = ComboBoxSettingCard(
            cfg.ogg_encoder, FluentIcon.MUSIC, "OGG 编码器",
            "自动选择按 libopus → libvorbis 降级；苹果设备原生不支持 ogg。",
            ["自动选择", "libopus", "libvorbis"], self.encodingGroup,
        )
        for card in (
            self.ffmpegEncoderCard, self.aacCard, self.fdkVbrCard, self.oggCard,
        ):
            self.encodingGroup.addSettingCard(card)
        self.vLayout.addWidget(self.encodingGroup)

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
        self.tempDirCard.clicked.connect(self._select_temp_dir)
        # 编码器探测延后到事件循环，避免构造设置页时同步启 ffmpeg 阻塞界面
        QTimer.singleShot(0, self._refresh_encoder_hint)
        # 语言切换时重建动态拼接文案（参数提示 / 编码器提示）
        register_retranslate_hook(self._retranslate_dynamic_texts)

    @staticmethod
    def _conv_hint(arg: str, um_default_on: bool) -> str:
        """拼装转换选项卡的参数提示；状态词经 translate_ui 按当前语言输出。"""
        state = translate_ui("默认开启" if um_default_on else "默认关闭")
        hint = f"{translate_ui('对应参数:')} {arg} · {state}"
        if um_default_on:
            # um 未提供关闭参数：明确告知用户「否」无法关闭，避免静默误导
            hint += translate_ui("（无关闭参数，选“否”仍按默认执行）")
        return hint

    def _retranslate_dynamic_texts(self):
        """语言切换后重建动态拼接的提示文案（查表无法还原拼接结果）。"""
        for card, arg, um_default_on in self._convCards:
            card.setContent(self._conv_hint(arg, um_default_on))
        self._refresh_encoder_hint()

    def _on_language_changed(self, value=None):
        """语言切换：替换翻译器并重翻译当前界面，无需重启。"""
        apply_language()

    def _refresh_encoder_hint(self):
        """刷新 FFmpeg 卡上真实可用的编码器列表。"""
        available = probe_encoders(str(cfg.ffmpeg_path.value))
        self.ffmpegEncoderCard.setContent(
            f"{translate_ui('支持编码器：')}{supported_hint(available)}"
        )

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
            QTimer.singleShot(0, self._refresh_encoder_hint)

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

    def _select_temp_dir(self):
        folder = QFileDialog.getExistingDirectory(
            self, "选择临时目录", cfg.temp_dir.value or ""
        )
        if not folder:
            return
        qconfig.set(cfg.temp_dir, folder)
        self.tempDirCard.setContent(folder)
        signalBus.log_emitted.emit(f"临时目录已设为: {folder}", "info")
