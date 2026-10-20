# coding: utf-8
"""转换服务 —— 封装 um.exe 进程调用与批量任务队列。

view 层通过 ``signalBus.request_start`` / ``request_stop`` 驱动本服务，
本服务经 ``signalBus`` 反向广播转换事件（file_started / file_finished /
log_emitted / conversion_started / conversion_finished），实现 view 与
service 解耦。
"""

import os
from pathlib import Path

from PySide6.QtCore import QObject, QProcess

from ..common.config import cfg
from ..common.logger import logger
from ..common.signal_bus import signalBus
from ..common.utils import (
    decode_process_output,
    is_supported_file,
    simplify_process_line,
)

# 三态选项 → 是否启用
_TRISTATE = {"否": False, "是": True, "默认": None}


class UnlockMusicConverter(QObject):
    """单个 QProcess 串行处理一批待转换文件。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.process = QProcess(self)
        self.pending_files: list[str] = []
        self.current_file: str | None = None

        self._wire_process()
        self._wire_signals()

    # ------------------------------------------------------------------ 信号
    def _wire_process(self):
        self.process.readyReadStandardOutput.connect(self._on_stdout)
        self.process.readyReadStandardError.connect(self._on_stderr)
        self.process.finished.connect(self._on_finished)
        self.process.errorOccurred.connect(self._on_process_error)

    def _wire_signals(self):
        signalBus.request_start.connect(self.start)
        signalBus.request_stop.connect(self.stop)

    # ------------------------------------------------------------- 公共 API
    def start(self, files=None):
        """启动转换。``files`` 为 None 时保留已有待处理队列。"""
        if files is not None:
            files = [p for p in files if is_supported_file(p)]
            self.pending_files = list(files)
            self.current_file = None

        if self.process.state() != QProcess.NotRunning:
            signalBus.log_emitted.emit("任务已经在运行中。", "warning")
            return

        if not os.path.exists(cfg.um_path.value):
            signalBus.log_emitted.emit("未找到 um.exe，请在配置界面设置路径。", "error")
            signalBus.conversion_finished.emit(-1)
            return

        if not self.pending_files:
            signalBus.log_emitted.emit("没有可转换的受支持文件。", "warning")
            signalBus.conversion_finished.emit(-1)
            return

        signalBus.conversion_started.emit()
        signalBus.log_emitted.emit(
            f"准备处理 {len(self.pending_files)} 个受支持文件。", "info"
        )
        self._start_next_file()

    def stop(self):
        if self.process.state() == QProcess.Running:
            self.pending_files.clear()
            self.process.kill()
            signalBus.log_emitted.emit("正在停止任务...", "warning")

    # ----------------------------------------------------------------- 内部
    def _start_next_file(self):
        if not self.pending_files:
            self.current_file = None
            signalBus.log_emitted.emit("全部转换任务已完成。", "success")
            signalBus.conversion_finished.emit(0)
            return

        self.current_file = self.pending_files.pop(0)
        args = self._build_file_args(self.current_file)
        signalBus.file_started.emit(self.current_file)
        signalBus.log_emitted.emit(
            f"开始处理: {Path(self.current_file).name}", "info"
        )
        signalBus.log_emitted.emit(
            f"启动命令: {cfg.um_path.value} {' '.join(args)}", "debug"
        )
        self.process.start(cfg.um_path.value, args)
        if not self.process.waitForStarted(3000):
            signalBus.log_emitted.emit(
                f"启动失败: {Path(self.current_file).name}", "error"
            )
            signalBus.file_finished.emit(self.current_file, False)
            self._start_next_file()

    def _build_file_args(self, file_path: str) -> list[str]:
        args = ["-i", file_path]
        if cfg.output_dir.value:
            args.extend(["-o", cfg.output_dir.value])

        # QQ Music 密钥自动获取（通过 qmpc-mmkv-cli.exe）
        if cfg.qmpc_path.value and os.path.exists(cfg.qmpc_path.value):
            args.extend(["--qmpc-mmkv-cli-exe", cfg.qmpc_path.value])

        if _TRISTATE.get(cfg.remove_source.value) is True:
            args.append("--rs")
        if _TRISTATE.get(cfg.verbose.value) is True:
            args.append("-V")
        if _TRISTATE.get(cfg.overwrite.value) is True:
            args.append("--overwrite")
        if _TRISTATE.get(cfg.watch.value) is True:
            args.append("--watch")
        if _TRISTATE.get(cfg.update_metadata.value) is True:
            args.append("--update-metadata")
        if _TRISTATE.get(cfg.skip_noop.value) is True:
            args.append("-n")
        return args

    def _log_process_output(self, raw: bytes, default_level: str):
        text = decode_process_output(raw)
        for line in text.replace("\r", "\n").splitlines():
            simplified, level = simplify_process_line(line)
            if simplified:
                signalBus.log_emitted.emit(simplified, level or default_level)

    # ------------------------------------------------------------- 进程回调
    def _on_stdout(self):
        self._log_process_output(
            self.process.readAllStandardOutput().data(), "info"
        )

    def _on_stderr(self):
        self._log_process_output(
            self.process.readAllStandardError().data(), "warning"
        )

    def _on_finished(self, exit_code, _exit_status):
        if self.current_file:
            signalBus.file_finished.emit(
                self.current_file, exit_code == 0
            )
            level = "success" if exit_code == 0 else "error"
            signalBus.log_emitted.emit(
                f"{Path(self.current_file).name} 处理完成，退出码: {exit_code}",
                level,
            )

        if self.pending_files:
            self._start_next_file()
            return

        self.current_file = None
        signalBus.log_emitted.emit(
            f"任务结束，退出码: {exit_code}",
            "success" if exit_code == 0 else "error",
        )
        signalBus.conversion_finished.emit(exit_code)

    def _on_process_error(self, error):
        if error == QProcess.Crashed:
            self.pending_files.clear()
            self.current_file = None
            signalBus.log_emitted.emit("进程异常退出。", "error")
            signalBus.conversion_finished.emit(-1)
