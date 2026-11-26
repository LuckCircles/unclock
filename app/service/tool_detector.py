# coding: utf-8
"""工具检测服务 —— 检测 um / ffmpeg / qmpc / um_cli_rs 版本与可用性，结果经信号总线广播。

版本获取顺序：先读 exe 文件属性（Windows 版本资源），拿不到再执行命令行
版本参数。文件属性是纯文件读取，比启动外部进程更快且无副作用。
"""

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool

from ..common.config import cfg
from ..common.i18n import translate_ui
from ..common.logger import logger
from ..common.signal_bus import signalBus
from ..common.utils import decode_process_output
from ..common.version_info import read_file_version


# 单个工具版本探测超时（秒）：外部 exe 卡住时后台线程不再被永久占用，
# 首页四张版本卡也不会永远停在「检测中...」
_VERSION_TIMEOUT_S = 8
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


@dataclass(frozen=True)
class ToolInfo:
    """单个外部工具的检测结果。"""

    version: str
    ready: bool
    # 版本来源："文件属性" / "命令行 -v" 等，仅用于运行日志留痕
    source: str = ""


@dataclass(frozen=True)
class ToolsReport:
    """一次工具链检测的汇总报告（``tools_detected`` 信号载荷）。"""

    um: ToolInfo
    ffmpeg: ToolInfo
    qmpc: ToolInfo
    um_cli_rs: ToolInfo


class _DetectTask(QRunnable):
    """线程池任务：在后台线程执行一次 ``ToolDetector.detect``。

    ``detect`` 内只做子进程调用与信号广播——signalBus 接收方均在 UI 线程，
    跨线程发送自动转为队列连接，安全无锁。
    """

    def __init__(self, detector: "ToolDetector"):
        super().__init__()
        self._detector = detector

    def run(self):
        try:
            self._detector.detect()
        except RuntimeError as exc:
            # 启动后极短窗口内退出时，解释器拆解可能与信号广播竞态
            # （Signal source has been deleted）——此时结果已无人接收，安全忽略
            logger.debug(f"工具检测任务异常退出（可能为退出竞态）: {exc}")
        except Exception as exc:  # noqa: BLE001
            # 兜底：任何未预期异常都不能让首页四张卡永远停在「检测中...」
            logger.warning(f"工具检测任务异常: {exc}")
            try:
                unknown = ToolInfo("检测异常", False)
                signalBus.tools_detected.emit(
                    ToolsReport(unknown, unknown, unknown, unknown)
                )
            except RuntimeError:
                logger.debug("工具检测兜底广播时对象已销毁，忽略")


class ToolDetector(QObject):
    """检测 um.exe / ffmpeg.exe / qmpc-mmkv-cli.exe 是否存在并解析其版本号。"""

    def __init__(self, parent=None):
        super().__init__(parent)

    def detect(self):
        logger.info(translate_ui("开始工具链自动检测"))
        report = ToolsReport(
            um=self._check_um(),
            ffmpeg=self._check_ffmpeg(),
            qmpc=self._check_qmpc(),
            um_cli_rs=self._check_um_cli_rs(),
        )
        logger.info(
            f"{translate_ui('工具链检测完成:')} "
            f"um={translate_ui(report.um.version)}"
            f"({translate_ui('就绪' if report.um.ready else '缺失')}) "
            f"ffmpeg={translate_ui(report.ffmpeg.version)}"
            f"({translate_ui('就绪' if report.ffmpeg.ready else '缺失')}) "
            f"qmpc={translate_ui(report.qmpc.version)}"
            f"({translate_ui('就绪' if report.qmpc.ready else '缺失')}) "
            f"um_cli_rs={translate_ui(report.um_cli_rs.version)}"
            f"({translate_ui('就绪' if report.um_cli_rs.ready else '缺失')})"
        )
        # 工具监测情况同步到运行日志页（每个 exe 一行，附版本来源）
        for name, info in (
            ("um.exe", report.um),
            ("ffmpeg.exe", report.ffmpeg),
            ("qmpc-mmkv-cli.exe", report.qmpc),
            ("um_cli_rs.exe", report.um_cli_rs),
        ):
            source = f" / {self._source_text(info.source)}" if info.source else ""
            signalBus.log_emitted.emit(
                f"{translate_ui('工具监测')} {name}: {translate_ui(info.version)} "
                f"({translate_ui('就绪' if info.ready else '缺失')}{source})",
                "info",
            )
        signalBus.tools_detected.emit(report)

    @staticmethod
    def _source_text(source: str) -> str:
        """翻译版本来源；「命令行 -v」等带后缀的变体只翻译前缀。"""
        if source.startswith("命令行"):
            return f"{translate_ui('命令行')}{source[len('命令行'):]}"
        return translate_ui(source)

    def detect_async(self):
        """后台线程池执行检测：不占用启动关键路径，结果经信号总线异步更新界面。"""
        QThreadPool.globalInstance().start(_DetectTask(self))

    # ------------------------------------------------------------ 通用探测
    @staticmethod
    def _probe(
        path: Path,
        commands: tuple[tuple[str, ...], ...],
        parser: Callable[[str], str | None],
    ) -> ToolInfo:
        """先读文件属性版本；失败则依次尝试命令行版本参数。"""
        if not path.is_file():
            return ToolInfo("未找到", False)

        file_version = read_file_version(path)
        if file_version:
            return ToolInfo(file_version, True, "文件属性")

        for args in commands:
            try:
                res = subprocess.run(
                    [str(path), *args],
                    capture_output=True,
                    creationflags=_NO_WINDOW,
                    timeout=_VERSION_TIMEOUT_S,
                )
            except (OSError, subprocess.SubprocessError) as exc:
                logger.debug(f"获取 {path.name} 版本失败（{' '.join(args)}）: {exc}")
                continue
            output = "\n".join(
                filter(None, (decode_process_output(res.stdout), decode_process_output(res.stderr)))
            )
            version = parser(output)
            if version:
                return ToolInfo(version, True, f"命令行 {' '.join(args)}")

        # 文件存在但版本拿不到：仍视为就绪（不阻断转换），与既有行为一致
        return ToolInfo("版本未知", True, "命令行")

    # ------------------------------------------------------------ 各工具
    @staticmethod
    def _parse_um(output: str) -> str | None:
        match = re.search(r"v\d+(?:\.\d+)+", output)
        return match.group(0) if match else None

    @staticmethod
    def _parse_ffmpeg(output: str) -> str | None:
        line = output.splitlines()[0] if output else ""
        match = re.search(r"version\s+(\d+(?:\.\d+)*)", line, re.I)
        return match.group(1) if match else None

    @staticmethod
    def _parse_qmpc(output: str) -> str | None:
        # -V 输出 "1.0.4 0061a32"；-h 输出 "v1.0.4 [0061a32]"，两者都兼容
        match = re.search(r"v?(\d+(?:\.\d+){1,2})\b", output)
        return match.group(1) if match else None

    @staticmethod
    def _parse_um_cli_rs(output: str) -> str | None:
        # -V / --version 输出 "um_cli_rs 0.1.13"
        match = re.search(
            r"um[_-]cli[_-]rs\s+v?(\d+(?:\.\d+){1,3})\b", output, re.I
        )
        return match.group(1) if match else None

    def _check_um(self) -> ToolInfo:
        return self._probe(
            Path(cfg.um_path.value),
            (("-v",), ("--version",)),
            self._parse_um,
        )

    def _check_ffmpeg(self) -> ToolInfo:
        # ffmpeg 的 -v 是日志级别参数（会打印版本后报缺参），-version 才是版本参数
        return self._probe(
            Path(cfg.ffmpeg_path.value),
            (("-version",), ("-v",)),
            self._parse_ffmpeg,
        )

    def _check_qmpc(self) -> ToolInfo:
        # qmpc 的 -v 是 verbose（会真实执行密钥提取并写文件），版本参数是 -V
        return self._probe(
            Path(cfg.qmpc_path.value),
            (("-V",), ("-h",)),
            self._parse_qmpc,
        )

    def _check_um_cli_rs(self) -> ToolInfo:
        # clap CLI：-V / --version 都只打印版本，无副作用；-v 是 verbose
        return self._probe(
            Path(cfg.um_cli_rs_path.value),
            (("-V",), ("--version",)),
            self._parse_um_cli_rs,
        )
