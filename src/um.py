import json
import os
import re
import subprocess
import sys
from pathlib import Path

from loguru import logger
from PySide6.QtCore import QProcess, QSize, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    CardWidget,
    ConfigItem,
    FlowLayout,
    FluentIcon,
    HorizontalFlipView,
    IconWidget,
    MSFluentWindow,
    NavigationItemPosition,
    OptionsConfigItem,
    OptionsSettingCard,
    OptionsValidator,
    PushSettingCard,
    QConfig,
    ScrollArea,
    SettingCardGroup,
    TitleLabel,
    TogglePushButton,
    qconfig,
)

from .list_view import FileInterface
from .log_view import LogInterface


class Config(QConfig):
    """配置管理"""

    input_dir = ConfigItem("Basic", "input_dir", "")
    output_dir = ConfigItem("Basic", "output_dir", "")
    um_path = ConfigItem("Basic", "um_path", "")
    ffmpeg_path = ConfigItem("Basic", "ffmpeg_path", "")

    remove_source = OptionsConfigItem(
        "Conversion", "remove_source", "默认", OptionsValidator(["否", "是", "默认"])
    )
    verbose = OptionsConfigItem(
        "Conversion", "verbose", "默认", OptionsValidator(["否", "是", "默认"])
    )
    overwrite = OptionsConfigItem(
        "Conversion", "overwrite", "默认", OptionsValidator(["否", "是", "默认"])
    )
    watch = OptionsConfigItem(
        "Conversion", "watch", "默认", OptionsValidator(["否", "是", "默认"])
    )
    update_metadata = OptionsConfigItem(
        "Conversion", "update_metadata", "默认", OptionsValidator(["否", "是", "默认"])
    )
    skip_noop = OptionsConfigItem(
        "Conversion", "skip_noop", "默认", OptionsValidator(["否", "是", "默认"])
    )

    def __init__(self):
        super().__init__()
        self.project_root = Path(__file__).resolve().parent.parent


cfg = Config()
logger.add(str(cfg.project_root / "app.log"), rotation="5 MB", encoding="utf-8")

if not cfg.um_path.value:
    qconfig.set(cfg.um_path, str(cfg.project_root / "um" / "um.exe"))
if not cfg.ffmpeg_path.value:
    qconfig.set(cfg.ffmpeg_path, str(cfg.project_root / "um" / "ffmpeg.exe"))

qconfig.load(str(cfg.project_root / "config.json"), cfg)


class VersionCard(CardWidget):
    """工具版本卡片（自适应紧凑版）"""

    def __init__(self, title, image_path, accent_color, parent=None):
        super().__init__(parent)

        self.accent_color = accent_color
        self.base_title = title

        # ✅ 自适应高度
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Minimum)
        self.setFixedWidth(260)  # 👉 推荐固定宽度（更整齐）

        # ===== 主布局 =====
        self.hLayout = QHBoxLayout(self)
        self.hLayout.setContentsMargins(14, 10, 14, 10)
        self.hLayout.setSpacing(10)

        # ===== 图标 =====
        self.iconLabel = QLabel(self)
        if os.path.exists(image_path):
            self.iconLabel.setPixmap(
                QPixmap(image_path).scaled(
                    40, 40, Qt.KeepAspectRatio, Qt.SmoothTransformation
                )
            )
        self.iconLabel.setFixedSize(40, 40)

        # ===== 文本区 =====
        self.textLayout = QVBoxLayout()
        self.textLayout.setSpacing(2)  # 🔥 超紧凑
        self.textLayout.setContentsMargins(0, 0, 0, 0)

        # 第一行：名称 + 版本
        self.nameVersionLabel = QLabel(title, self)
        self.nameVersionLabel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.nameVersionLabel.setStyleSheet(
            """
            font-size: 15px;
            color: #111827;
            padding: 0px;
            margin: 0px;
        """
        )

        # 第二行：路径
        self.pathLabel = QLabel("路径未设置", self)
        self.pathLabel.setWordWrap(True)
        self.pathLabel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.pathLabel.setStyleSheet(
            """
            font-size: 12px;
            color: #9ca3af;
            padding: 0px;
            margin: 0px;
        """
        )

        # ===== 右上角 badge =====
        self.badgeLabel = QLabel("READY", self)
        self.badgeLabel.setAlignment(Qt.AlignCenter)
        self.badgeLabel.setFixedWidth(56)

        # ===== 布局 =====
        self.textLayout.addWidget(self.nameVersionLabel)
        self.textLayout.addWidget(self.pathLabel)

        self.hLayout.addWidget(self.iconLabel, 0, Qt.AlignTop)
        self.hLayout.addLayout(self.textLayout, 1)
        self.hLayout.addWidget(self.badgeLabel, 0, Qt.AlignTop)

        # ===== 样式 =====
        self.setStyleSheet(
            f"""
            VersionCard {{
                border-radius: 14px;
                border: 1px solid {accent_color}33;
                background-color: {accent_color}0A;
            }}
            VersionCard:hover {{
                border: 1px solid {accent_color}66;
                background-color: {accent_color}14;
            }}
        """
        )

        self._set_badge_style(True)

    def update_info(self, version, path="", ready=True):
        value = version

        if "um v" in version:
            value = version.replace("um ", "")
        elif version.lower().startswith("ffmpeg "):
            value = version.replace("ffmpeg ", "")

        # ✅ 防重复拼接
        self.nameVersionLabel.setText(f"{self.base_title} {value}")

        self.pathLabel.setText(self._compact_path(path) if path else "路径未设置")

        self.badgeLabel.setText("READY" if ready else "MISS")
        self._set_badge_style(ready)

    def _set_badge_style(self, ready):
        bg = "#0f8c4a" if ready else "#6b7280"
        self.badgeLabel.setStyleSheet(
            f"""
            background-color: {bg};
            color: white;
            border-radius: 10px;
            padding: 3px 6px;
            font-size: 11px;
        """
        )

    def _compact_path(self, path):
        normalized = str(path).replace("\\", "/")
        if len(normalized) <= 80:
            return normalized
        return f"...{normalized[-70:]}"


class VersionCardView(QWidget):
    """Version 卡片容器"""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)

        self.titleLabel = QLabel(title, self)

        self.vBoxLayout = QVBoxLayout(self)
        self.flowLayout = FlowLayout()

        self.vBoxLayout.setContentsMargins(24, 8, 24, 8)
        self.vBoxLayout.setSpacing(8)

        self.flowLayout.setContentsMargins(0, 0, 0, 0)
        self.flowLayout.setHorizontalSpacing(12)
        self.flowLayout.setVerticalSpacing(10)

        self.vBoxLayout.addWidget(self.titleLabel)
        self.vBoxLayout.addLayout(self.flowLayout, 1)

        self.titleLabel.setStyleSheet(
            """
            font-size: 16px;
            font-weight: 600;
            color: #111827;
        """
        )

    # ✅ 关键：接收已有卡片
    def addCard(self, card: QWidget):
        self.flowLayout.addWidget(card)


class PathCard(CardWidget):
    """主页目录快捷卡片"""

    clicked = Signal()

    def __init__(self, title, description, icon, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)
        self.hLayout = QHBoxLayout(self)
        self.hLayout.setContentsMargins(18, 16, 18, 16)
        self.hLayout.setSpacing(14)

        self.iconWidget = IconWidget(icon, self)
        self.iconWidget.setFixedSize(22, 22)

        self.textLayout = QVBoxLayout()
        self.textLayout.setSpacing(4)
        self.titleLabel = BodyLabel(title, self)
        self.pathLabel = CaptionLabel(description, self)
        self.pathLabel.setWordWrap(True)
        self.openIcon = IconWidget(FluentIcon.RIGHT_ARROW, self)
        self.openIcon.setFixedSize(16, 16)

        self.textLayout.addWidget(self.titleLabel)
        self.textLayout.addWidget(self.pathLabel)

        self.hLayout.addWidget(self.iconWidget, 0, Qt.AlignTop)
        self.hLayout.addLayout(self.textLayout, 1)
        self.hLayout.addWidget(self.openIcon, 0, Qt.AlignVCenter)

    def set_path(self, path, fallback):
        self.pathLabel.setText(path or fallback)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class HomeInterface(ScrollArea):
    """主界面"""

    start_process_signal = Signal()
    stop_process_signal = Signal()
    open_input_dir_signal = Signal()
    open_output_dir_signal = Signal()

    def __init__(self, config: Config, parent=None):
        super().__init__(parent)
        self.config = config
        self._button_state = "idle"

        self.view = QWidget(self)
        self.vLayout = QVBoxLayout(self.view)
        self.vLayout.setContentsMargins(30, 30, 30, 30)
        self.vLayout.setSpacing(20)
        self.vLayout.setAlignment(Qt.AlignTop)

        self.setWidget(self.view)
        self.setWidgetResizable(True)
        self.setObjectName("HomeInterface")

        img_dir = Path(__file__).resolve().parent.parent / "img"

        self.flipView = HorizontalFlipView(self)
        self.flipView.setFixedHeight(220)
        self.flipView.setBorderRadius(16)
        self.flipView.setItemSize(QSize(940, 220))
        self.flipView.setAspectRatioMode(Qt.KeepAspectRatioByExpanding)

        welcome_path = str(img_dir / "welcome.png")
        if os.path.exists(welcome_path):
            self.flipView.addImage(welcome_path)
            self.flipView.setCurrentIndex(0)
        else:
            logger.warning(f"Banner image not found: {welcome_path}")
        self.vLayout.addWidget(self.flipView)

        self.heroTitle = TitleLabel("音乐解锁工具", self)
        self.heroSubtitle = CaptionLabel(
            "快速查看环境、打开目录并管理当前转换任务", self
        )
        self.vLayout.addWidget(self.heroTitle)
        self.vLayout.addWidget(self.heroSubtitle)

        # self.cardsLayout = QHBoxLayout()
        # self.cardsLayout.setSpacing(20)

        # ===== 工具检测卡片 =====
        self.umCard = VersionCard(
            "Unlock Music (um)", str(img_dir / "pwa.png"), "#0f6cbd"
        )

        self.ffmpegCard = VersionCard("FFmpeg", str(img_dir / "ffmpeg.png"), "#0f6cbd")

        # 初始显示（可选）
        self.umCard.update_info("检测中...", "", False)
        self.ffmpegCard.update_info("检测中...", "", False)

        # ✅ 正确容器（唯一）
        self.cardView = VersionCardView("工具检测")

        self.cardView.addCard(self.umCard)
        self.cardView.addCard(self.ffmpegCard)

        # ✅ 加入主布局
        self.vLayout.addWidget(self.cardView)

        # self.umCard = VersionCard("Unlock Music (um)", str(img_dir / "pwa.png"), "#0f6cbd", self)
        # self.ffmpegCard = VersionCard("FFmpeg", str(img_dir / "ffmpeg.png"), "#0f6cbd", self)
        # self.cardsLayout.addWidget(self.umCard, 1)
        # self.cardsLayout.addWidget(self.ffmpegCard, 1)
        # self.vLayout.addLayout(self.cardsLayout)

        self.pathCardsLayout = QHBoxLayout()
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
        self.inputDirCard.clicked.connect(self.open_input_dir_signal.emit)
        self.outputDirCard.clicked.connect(self.open_output_dir_signal.emit)
        self.refresh_paths()

        self.buttonLayout = QHBoxLayout()
        self.buttonLayout.setSpacing(18)
        self.buttonLayout.setAlignment(Qt.AlignCenter)

        self.btnStart = TogglePushButton(self)
        self.btnStart.setFixedSize(220, 50)
        self.btnStart.clicked.connect(self._handle_click)

        self.btnStop = TogglePushButton("停止转换", self)
        self.btnStop.setFixedSize(220, 50)
        self.btnStop.clicked.connect(self._handle_stop_click)

        self.buttonLayout.addWidget(self.btnStart)
        self.buttonLayout.addWidget(self.btnStop)
        self.vLayout.addLayout(self.buttonLayout)
        self._set_button_state("idle")
        self.vLayout.addStretch(1)

    def _handle_click(self):
        if self._button_state == "idle":
            self.start_process_signal.emit()
        else:
            self.btnStart.setChecked(True)

    def _handle_stop_click(self):
        if self._button_state == "running":
            self.stop_process_signal.emit()
        self.btnStop.setChecked(self._button_state == "running")

    def refresh_paths(self):
        self.inputDirCard.set_path(self.config.input_dir.value, "未设置输入目录")
        self.outputDirCard.set_path(self.config.output_dir.value, "未设置输出目录")

    def _set_button_state(self, state):
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

    def set_running(self, is_running):
        self._set_button_state("running" if is_running else "idle")

    def set_stopping(self):
        self._set_button_state("stopping")


class ConfigInterface(ScrollArea):
    """配置界面"""

    def __init__(self, config: Config, parent=None):
        super().__init__(parent)
        self.config = config
        self.view = QWidget(self)
        self.vLayout = QVBoxLayout(self.view)

        self.setWidget(self.view)
        self.setWidgetResizable(True)
        self.setObjectName("ConfigInterface")

        self.basicGroup = SettingCardGroup("基础设置", self.view)
        self.inputCard = PushSettingCard(
            "选择目录",
            FluentIcon.FOLDER,
            "输入目录",
            self.config.input_dir.value or "未设置",
            self.view,
        )
        self.outputCard = PushSettingCard(
            "选择目录",
            FluentIcon.FOLDER,
            "输出目录",
            self.config.output_dir.value or "未设置",
            self.view,
        )
        self.umPathCard = PushSettingCard(
            "选择文件",
            FluentIcon.COMMAND_PROMPT,
            "um 路径",
            self.config.um_path.value,
            self.view,
        )
        self.ffmpegPathCard = PushSettingCard(
            "选择文件",
            FluentIcon.VIDEO,
            "ffmpeg 路径",
            self.config.ffmpeg_path.value,
            self.view,
        )

        self.basicGroup.addSettingCard(self.inputCard)
        self.basicGroup.addSettingCard(self.outputCard)
        self.basicGroup.addSettingCard(self.umPathCard)
        self.basicGroup.addSettingCard(self.ffmpegPathCard)
        self.vLayout.addWidget(self.basicGroup)

        self.convGroup = SettingCardGroup("转换设置", self.view)
        options_meta = [
            (self.config.remove_source, "删除源文件", "--rs"),
            (self.config.verbose, "详细输出", "-V"),
            (self.config.overwrite, "覆盖输出", "--overwrite"),
            (self.config.watch, "监听输入目录", "--watch"),
            (self.config.update_metadata, "更新封面", "--update-metadata"),
            (self.config.skip_noop, "跳过无动作解码器", "-n"),
        ]
        for config_item, label, arg in options_meta:
            card = OptionsSettingCard(
                config_item,
                FluentIcon.SETTING,
                label,
                f"对应参数: {arg}",
                ["否", "是", "默认"],
                self.convGroup,
            )
            self.convGroup.addSettingCard(card)

        self.vLayout.addWidget(self.convGroup)
        self.vLayout.addStretch(1)
        self.vLayout.setContentsMargins(30, 30, 30, 30)
        self.vLayout.setSpacing(20)

        self.inputCard.clicked.connect(self._select_input)
        self.outputCard.clicked.connect(self._select_output)
        self.umPathCard.clicked.connect(self._select_um)
        self.ffmpegPathCard.clicked.connect(self._select_ffmpeg)

    def _select_input(self):
        folder = QFileDialog.getExistingDirectory(self, "选择输入目录")
        if not folder:
            return
        qconfig.set(self.config.input_dir, folder)
        self.inputCard.setContent(folder)
        main_window = self.window()
        if hasattr(main_window, "homeInterface"):
            main_window.homeInterface.refresh_paths()
        if hasattr(main_window, "fileInterface"):
            main_window.fileInterface.refresh_from_config()

    def _select_output(self):
        folder = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if not folder:
            return
        qconfig.set(self.config.output_dir, folder)
        self.outputCard.setContent(folder)
        main_window = self.window()
        if hasattr(main_window, "homeInterface"):
            main_window.homeInterface.refresh_paths()

    def _select_um(self):
        file, _ = QFileDialog.getOpenFileName(
            self, "选择 um.exe", "", "Executable (*.exe)"
        )
        if file:
            qconfig.set(self.config.um_path, file)
            self.umPathCard.setContent(file)

    def _select_ffmpeg(self):
        file, _ = QFileDialog.getOpenFileName(
            self, "选择 ffmpeg.exe", "", "Executable (*.exe)"
        )
        if file:
            qconfig.set(self.config.ffmpeg_path, file)
            self.ffmpegPathCard.setContent(file)


class UnlockMusicGUI(MSFluentWindow):
    """主窗口"""

    def __init__(self):
        super().__init__()
        self.config = cfg
        self.process = QProcess(self)
        self.pending_files = []
        self.current_file = None

        self.homeInterface = HomeInterface(self.config, self)
        self.fileInterface = FileInterface(self)
        self.logInterface = LogInterface(self)
        self.configInterface = ConfigInterface(self.config, self)

        self.init_navigation()
        self.init_window()
        self.init_process()
        self.check_tools()
        self.homeInterface.refresh_paths()
        self.fileInterface.refresh_from_config()

    def init_navigation(self):
        self.addSubInterface(self.homeInterface, FluentIcon.HOME, "主界面")
        self.addSubInterface(self.fileInterface, FluentIcon.MUSIC, "文件管理")
        self.addSubInterface(self.logInterface, FluentIcon.DOCUMENT, "运行日志")
        self.addSubInterface(
            self.configInterface,
            FluentIcon.SETTING,
            "配置界面",
            position=NavigationItemPosition.BOTTOM,
        )

    def init_window(self):
        self.resize(1080, 860)
        self.setWindowTitle("音乐解锁工具 - Fluent UI")
        self.setWindowIcon(QIcon(":/qfluentwidgets/images/logo.png"))

        desktop = QApplication.primaryScreen().availableGeometry()
        w, h = desktop.width(), desktop.height()
        self.move(w // 2 - self.width() // 2, h // 2 - self.height() // 2)

    def init_process(self):
        self.process.readyReadStandardOutput.connect(self._on_stdout)
        self.process.readyReadStandardError.connect(self._on_stderr)
        self.process.finished.connect(self._on_finished)
        self.process.errorOccurred.connect(self._on_process_error)

        self.homeInterface.start_process_signal.connect(self.start_conversion)
        self.homeInterface.stop_process_signal.connect(self.stop_conversion)
        self.homeInterface.open_input_dir_signal.connect(
            lambda: self._open_directory(self.config.input_dir.value, "输入目录")
        )
        self.homeInterface.open_output_dir_signal.connect(
            lambda: self._open_directory(self.config.output_dir.value, "输出目录")
        )

    def _open_directory(self, path, label):
        if not path or not os.path.isdir(path):
            self.log(f"{label}未设置或路径不存在。", "warning")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def log(self, message, level="info"):
        cleaned = self._clean_log_text(message)
        if not cleaned:
            return

        tag_map = {
            "info": "[INFO]",
            "error": "[ERROR]",
            "warning": "[WARN]",
            "success": "[OK]",
            "debug": "[DEBUG]",
        }
        tag = tag_map.get(level, "[DEBUG]")

        for line in cleaned.splitlines():
            if level == "info":
                logger.info(line)
            elif level == "error":
                logger.error(line)
            elif level == "warning":
                logger.warning(line)
            elif level == "success":
                logger.success(line)
            else:
                logger.debug(line)
            self.logInterface.append_log(f"{tag} {line}")

    def _decode_process_output(self, raw):
        for encoding in ("utf-8", "gb18030", "cp936"):
            try:
                return raw.decode(encoding)
            except UnicodeDecodeError:
                continue
        return raw.decode("utf-8", errors="ignore")

    def _clean_log_text(self, message):
        text = re.sub(r"\x1b\[[0-9;]*m", "", str(message or ""))
        lines = [line.strip() for line in text.replace("\r", "\n").splitlines()]
        lines = [line for line in lines if line]
        return "\n".join(lines)

    def _simplify_process_line(self, line):
        text = self._clean_log_text(line)
        if not text:
            return None, None

        lower_text = text.lower()
        if "try decode failed" in lower_text:
            return None, None

        payload = {}
        payload_match = re.search(r"(\{.*\})$", text)
        if payload_match:
            try:
                payload = json.loads(payload_match.group(1))
            except json.JSONDecodeError:
                payload = {}

        if "successfully converted" in lower_text:
            source = Path(payload.get("source", "")).name or "未知文件"
            destination = Path(payload.get("destination", "")).name or "输出文件"
            return f"转换成功: {source} -> {destination}", "success"

        if "conversion failed" in lower_text:
            source = Path(payload.get("source", "")).name or "未知文件"
            reason = payload.get("error", "未知错误")
            return f"转换失败: {source} ({reason})", "error"

        if "run app failed" in lower_text:
            reason = payload.get("error", text)
            return f"任务执行失败: {reason}", "error"

        if "warn" in lower_text:
            return text, "warning"
        if "error" in lower_text or "fatal" in lower_text:
            return text, "error"
        return text, "info"

    def _log_process_output(self, raw, default_level):
        text = self._decode_process_output(raw)
        for line in text.replace("\r", "\n").splitlines():
            simplified, level = self._simplify_process_line(line)
            if simplified:
                self.log(simplified, level or default_level)

    def check_tools(self):
        um_path = Path(self.config.um_path.value)
        ffmpeg_path = Path(self.config.ffmpeg_path.value)

        # ===== UM =====
        if um_path.exists():
            try:
                res = subprocess.run(
                    [str(um_path), "--version"],
                    capture_output=True,
                    text=True,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                match = re.search(r"v\d+\.\d+\.\d+", res.stdout)
                ver = match.group(0) if match else "v0.0.0"
            except Exception as e:
                ver = "v0.0.0"
                logger.debug(f"获取 um 版本失败: {e}")

            self.homeInterface.umCard.update_info(ver, str(um_path), True)
        else:
            self.homeInterface.umCard.update_info("未找到", str(um_path), False)

        # ===== FFmpeg =====
        if ffmpeg_path.exists():
            try:
                res = subprocess.run(
                    [str(ffmpeg_path), "-version"],
                    capture_output=True,
                    text=True,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                line = res.stdout.splitlines()[0] if res.stdout else ""
                match = re.search(r"version\s+(\d+(?:\.\d+)*)", line, re.I)
                ver = match.group(1) if match else "0.0.0"
            except Exception as e:
                ver = "0.0.0"
                logger.debug(f"获取 ffmpeg 版本失败: {e}")

            self.homeInterface.ffmpegCard.update_info(ver, str(ffmpeg_path), True)
        else:
            self.homeInterface.ffmpegCard.update_info("未找到", str(ffmpeg_path), False)

    def _build_file_args(self, file_path):
        args = ["-i", file_path]
        if self.config.output_dir.value:
            args.extend(["-o", self.config.output_dir.value])

        mapping = {"否": False, "是": True, "默认": None}
        if mapping.get(self.config.remove_source.value) is True:
            args.append("--rs")
        if mapping.get(self.config.verbose.value) is True:
            args.append("-V")
        if mapping.get(self.config.overwrite.value) is True:
            args.append("--overwrite")
        if mapping.get(self.config.watch.value) is True:
            args.append("--watch")
        if mapping.get(self.config.update_metadata.value) is True:
            args.append("--update-metadata")
        if mapping.get(self.config.skip_noop.value) is True:
            args.append("-n")
        return args

    def _start_next_file(self):
        if not self.pending_files:
            self.current_file = None
            self.homeInterface.set_running(False)
            self.log("全部转换任务已完成。", "success")
            return

        self.current_file = self.pending_files.pop(0)
        args = self._build_file_args(self.current_file)
        self.log(f"开始处理: {Path(self.current_file).name}", "info")
        self.log(f"启动命令: {self.config.um_path.value} {' '.join(args)}", "debug")
        self.process.start(self.config.um_path.value, args)
        if not self.process.waitForStarted(3000):
            failed_name = Path(self.current_file).name
            self.log(f"启动失败: {failed_name}", "error")
            self._start_next_file()

    def start_conversion(self):
        if self.process.state() != QProcess.NotRunning:
            self.log("任务已经在运行中。", "warning")
            return

        if not os.path.exists(self.config.um_path.value):
            self.homeInterface.set_running(False)
            self.log("未找到 um.exe，请在配置界面设置路径。", "error")
            return

        files = self.fileInterface.get_file_paths()
        if not files:
            input_dir = self.config.input_dir.value
            if input_dir and os.path.exists(input_dir):
                self.log(f"列表为空，正在扫描输入目录: {input_dir}", "info")
                self.fileInterface.scan_directory(input_dir)
                files = self.fileInterface.get_file_paths()

        files = [path for path in files if self.fileInterface.is_supported_file(path)]
        if not files:
            self.homeInterface.set_running(False)
            self.log("没有可转换的受支持文件。", "warning")
            return

        self.pending_files = list(files)
        self.current_file = None
        self.log(f"准备处理 {len(files)} 个受支持文件。", "info")
        self.homeInterface.set_running(True)
        self._start_next_file()

    def stop_conversion(self):
        if self.process.state() == QProcess.Running:
            self.pending_files.clear()
            self.homeInterface.set_stopping()
            self.process.kill()
            self.log("正在停止任务...", "warning")

    def _on_stdout(self):
        self._log_process_output(self.process.readAllStandardOutput().data(), "info")

    def _on_stderr(self):
        self._log_process_output(self.process.readAllStandardError().data(), "warning")

    def _on_finished(self, exit_code, exit_status):
        if self.current_file:
            level = "success" if exit_code == 0 else "error"
            self.log(
                f"{Path(self.current_file).name} 处理完成，退出码: {exit_code}", level
            )

        if self.pending_files:
            self._start_next_file()
            return

        self.current_file = None
        self.homeInterface.set_running(False)
        self.log(
            f"任务结束，退出码: {exit_code}", "success" if exit_code == 0 else "error"
        )

    def _on_process_error(self, error):
        if error == QProcess.Crashed:
            self.pending_files.clear()
            self.current_file = None
            self.homeInterface.set_running(False)
            self.log("进程异常退出。", "error")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = UnlockMusicGUI()
    window.show()
    sys.exit(app.exec())
