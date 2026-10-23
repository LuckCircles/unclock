# coding: utf-8
"""工具检测服务 —— 检测 um / ffmpeg 版本与可用性，结果经信号总线广播。"""

import re
import subprocess
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QThreadPool

from ..common.config import cfg
from ..common.logger import logger
from ..common.signal_bus import signalBus


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


class ToolDetector(QObject):
    """检测 um.exe / ffmpeg.exe / qmpc-mmkv-cli.exe 是否存在并解析其版本号。"""

    def __init__(self, parent=None):
        super().__init__(parent)

    def detect(self):
        logger.info("开始工具链自动检测")
        um_ver, um_ready = self._check_um()
        ff_ver, ff_ready = self._check_ffmpeg()
        qmpc_ver, qmpc_ready = self._check_qmpc()
        logger.info(
            f"工具链检测完成: um={um_ver}({'就绪' if um_ready else '缺失'}) "
            f"ffmpeg={ff_ver}({'就绪' if ff_ready else '缺失'}) "
            f"qmpc={qmpc_ver}({'就绪' if qmpc_ready else '缺失'})"
        )
        # 工具监测情况同步到运行日志页（每个 exe 一行）
        for name, ver, ready in (
            ("um.exe", um_ver, um_ready),
            ("ffmpeg.exe", ff_ver, ff_ready),
            ("qmpc-mmkv-cli.exe", qmpc_ver, qmpc_ready),
        ):
            signalBus.log_emitted.emit(
                f"工具监测 {name}: {ver} ({'就绪' if ready else '缺失'})", "info"
            )
        signalBus.tools_detected.emit(
            um_ver, um_ready, ff_ver, ff_ready, qmpc_ver, qmpc_ready
        )

    def detect_async(self):
        """后台线程池执行检测：不占用启动关键路径，结果经信号总线异步更新界面。"""
        QThreadPool.globalInstance().start(_DetectTask(self))

    def _check_um(self):
        path = Path(cfg.um_path.value)
        if not path.exists():
            return "未找到", False
        try:
            res = subprocess.run(
                [str(path), "--version"],
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            match = re.search(r"v\d+\.\d+\.\d+", res.stdout)
            return (match.group(0) if match else "版本未知"), True
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"获取 um 版本失败: {exc}")
            return "版本未知", True

    def _check_ffmpeg(self):
        path = Path(cfg.ffmpeg_path.value)
        if not path.exists():
            return "未找到", False
        try:
            res = subprocess.run(
                [str(path), "-version"],
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            line = res.stdout.splitlines()[0] if res.stdout else ""
            match = re.search(r"version\s+(\d+(?:\.\d+)*)", line, re.I)
            return (match.group(1) if match else "版本未知"), True
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"获取 ffmpeg 版本失败: {exc}")
            return "版本未知", True

    def _check_qmpc(self):
        path = Path(cfg.qmpc_path.value)
        if not path.exists():
            return "未找到", False
        try:
            res = subprocess.run(
                [str(path), "-h"],
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            output = res.stderr or res.stdout
            match = re.search(r"v\d+\.\d+\.\d+", output)
            return (match.group(0) if match else "版本未知"), True
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"获取 qmpc-mmkv-cli 版本失败: {exc}")
            return "版本未知", True
