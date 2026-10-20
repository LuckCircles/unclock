# coding: utf-8
"""工具检测服务 —— 检测 um / ffmpeg 版本与可用性，结果经信号总线广播。"""

import re
import subprocess
from pathlib import Path

from PySide6.QtCore import QObject

from ..common.config import cfg
from ..common.logger import logger
from ..common.signal_bus import signalBus


class ToolDetector(QObject):
    """检测 um.exe / ffmpeg.exe / qmpc-mmkv-cli.exe 是否存在并解析其版本号。"""

    def detect(self):
        um_ver, um_ready = self._check_um()
        ff_ver, ff_ready = self._check_ffmpeg()
        qmpc_ver, qmpc_ready = self._check_qmpc()
        signalBus.tools_detected.emit(
            um_ver, um_ready, ff_ver, ff_ready, qmpc_ver, qmpc_ready
        )

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
            return (match.group(0) if match else "v0.0.0"), True
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"获取 um 版本失败: {exc}")
            return "v0.0.0", True

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
            return (match.group(1) if match else "0.0.0"), True
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"获取 ffmpeg 版本失败: {exc}")
            return "0.0.0", True

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
            return (match.group(0) if match else "v0.0.0"), True
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"获取 qmpc-mmkv-cli 版本失败: {exc}")
            return "v0.0.0", True
