# coding: utf-8
"""转换服务 —— 封装 um.exe 进程调用与批量任务队列。

view 层通过 ``signalBus.request_start`` / ``request_stop`` 驱动本服务，
本服务经 ``signalBus`` 反向广播转换事件（file_started / file_finished /
log_emitted / conversion_started / conversion_finished），实现 view 与
service 解耦。
"""

import os
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, QTimer

from ..common.config import cfg
from ..common.logger import logger
from ..common.signal_bus import signalBus
from ..common.utils import (
    decode_process_output,
    is_encrypted_file,
    simplify_process_line,
)

# 三态选项 → 是否启用
_TRISTATE = {"否": False, "是": True, "默认": None}

# QQ 音乐加密格式后缀（仅这些格式需要 qmpc-mmkv-cli 提取密钥）
_QMC_SUFFIXES = {
    ".mflac", ".mflac0", ".mflac1", ".mflac2", ".mflaca",
    ".mflach", ".mflacl", ".mflacm",
    ".mgg", ".mgg0", ".mgg1", ".mgg2", ".mgga", ".mggh", ".mggl", ".mggm",
    ".qmc0", ".qmc2", ".qmc3", ".qmc4", ".qmc6", ".qmc8",
    ".qmcflac", ".qmcogg",
    ".tkm", ".tm0", ".tm2", ".tm3", ".tm6",
}


def _is_qmc_file(path: str) -> bool:
    lower = path.lower()
    return any(lower.endswith(s) for s in _QMC_SUFFIXES)


class UnlockMusicConverter(QObject):
    """单个 QProcess 串行处理一批待转换文件。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.process = QProcess(self)
        self.pending_files: list[str] = []
        self.current_file: str | None = None
        self._handled = False  # 当前文件是否已被收尾（防崩溃/结束双信号重复处理）
        self._ok_count = 0     # 本轮任务成功数（供结束汇总 InfoBar）
        self._fail_count = 0   # 本轮任务失败数

        self._wire_process()
        self._wire_signals()

    # ------------------------------------------------------------------ 信号
    def _wire_process(self):
        self.process.readyReadStandardOutput.connect(self._on_stdout)
        self.process.readyReadStandardError.connect(self._on_stderr)
        self.process.finished.connect(self._on_finished)
        self.process.errorOccurred.connect(self._on_process_error)

    def _wire_signals(self):
        # request_start 不直连本服务：由 MainWindow._dispatch_start 统一取文件列表后调用
        # start(files)，否则 files=None 的空队列路径会先弹"没有可转换文件"假警告
        signalBus.request_stop.connect(self.stop)

    # ------------------------------------------------------------- 公共 API
    def start(self, files=None):
        """启动转换。``files`` 为 None 时保留已有待处理队列。"""
        if files is not None:
            files = [p for p in files if is_encrypted_file(p)]
            self.pending_files = list(files)
            self.current_file = None

        if self.process.state() != QProcess.NotRunning:
            signalBus.log_emitted.emit("任务已经在运行中。", "warning")
            return

        if not os.path.exists(cfg.um_path.value):
            signalBus.log_emitted.emit("未找到 um.exe，请在配置界面设置路径。", "error")
            signalBus.toast_requested.emit("未找到 um.exe，请在配置界面设置路径。", "error")
            signalBus.conversion_finished.emit(-1)
            logger.error(f"转换启动失败: um.exe 不存在 {cfg.um_path.value}")
            return

        if not self.pending_files:
            signalBus.log_emitted.emit("没有可解密的加密文件。", "warning")
            signalBus.toast_requested.emit("没有可解密的加密文件。", "warning")
            signalBus.conversion_finished.emit(-1)
            logger.warning("转换启动失败: 没有可解密的加密文件")
            return

        self._ok_count = 0
        self._fail_count = 0
        signalBus.conversion_started.emit(len(self.pending_files))
        logger.info(f"开始转换任务: {len(self.pending_files)} 个文件")
        signalBus.log_emitted.emit(
            f"准备处理 {len(self.pending_files)} 个受支持文件。", "info"
        )
        self._start_next_file()

    def stop(self):
        if self.process.state() == QProcess.Running:
            self.pending_files.clear()
            self.current_file = None
            self._handled = True
            self.process.kill()
            signalBus.log_emitted.emit("正在停止任务...", "warning")
            signalBus.toast_requested.emit("已停止转换。", "warning")
            logger.warning("用户请求停止转换任务")
        # 复位按钮态（用户停止或退出清理时都回到 idle）
        signalBus.conversion_finished.emit(0)

    # ----------------------------------------------------------------- 内部
    def _start_next_file(self):
        if not self.pending_files:
            self.current_file = None
            self._handled = True
            signalBus.log_emitted.emit("全部转换任务已完成。", "success")
            signalBus.conversion_finished.emit(0)
            return

        self.current_file = self.pending_files.pop(0)
        self._handled = False
        args = self._build_file_args(self.current_file)
        signalBus.file_started.emit(self.current_file)
        signalBus.log_emitted.emit(
            f"开始处理: {Path(self.current_file).name}", "info"
        )
        # 启动命令属详细信息，只写 app.log，不显示在 UI 日志页
        logger.debug(f"启动命令: {cfg.um_path.value} {' '.join(args)}")
        self.process.start(cfg.um_path.value, args)
        if not self.process.waitForStarted(3000):
            signalBus.log_emitted.emit(
                f"启动失败: {Path(self.current_file).name}", "error"
            )
            # 同步收尾该文件（标记失败/跳过）并继续；随后 errorOccurred
            # (FailedToStart) 仅补记日志，不重复收尾
            self._finalize_current_file(False, -1)
            return

    def _build_file_args(self, file_path: str) -> list[str]:
        args = ["-i", file_path]
        if cfg.output_dir.value:
            args.extend(["-o", cfg.output_dir.value])

        # QQ Music 密钥自动获取：仅 QQ 音乐格式才传 qmpc-mmkv-cli 路径，
        # 非 QQ 格式（ncm/kgm 等）不传，避免 um 无谓调用 qmpc 触发 WARN
        if _is_qmc_file(file_path) and cfg.qmpc_path.value and os.path.exists(cfg.qmpc_path.value):
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
        """um 进程输出处理：所有原始行写 app.log，UI 只显示 success/error 关键结果。"""
        text = decode_process_output(raw)
        for line in text.replace("\r", "\n").splitlines():
            if not line.strip():
                continue
            # 原始输出全部写入 app.log（详细排查用）
            logger.debug(f"um 输出: {line}")
            simplified, level = simplify_process_line(line)
            # UI 日志页只显示用户关心的处理结果（成功/失败）
            if simplified and level in ("success", "error"):
                signalBus.log_emitted.emit(simplified, level)

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
        """单文件正常结束（含 um 自身返回非 0 退出码）。

        无论成功失败都记录并继续后续文件；本方法只负责收尾，
        实际「继续/结束」由 ``_finalize_current_file`` 内统一推进。
        """
        self._finalize_current_file(exit_code == 0, exit_code)

    def _on_process_error(self, error):
        """进程错误：单文件崩溃时跳过并记录、继续后续转换，不中断整批。"""
        if error == QProcess.Crashed:
            self._finalize_current_file(False, -1)
        elif error == QProcess.FailedToStart:
            # 启动失败已在 _start_next_file 的 waitForStarted 分支同步收尾，
            # 此处仅补记日志，避免与同步处理重复收尾
            signalBus.log_emitted.emit(
                "进程启动失败，请检查 um.exe 路径与权限。", "error"
            )
        else:
            signalBus.log_emitted.emit(f"进程错误: {error}", "warning")

    def _finalize_current_file(self, success: bool, exit_code: int):
        """收尾单个文件：发出 file_finished、更新完成记录、写日志，并推进队列。

        守卫：``_handled`` 为 True（已被崩溃/启动失败的同源信号收尾）或
        ``current_file`` 为 None 时直接返回，避免一条进程死亡触发
        errorOccurred(Crashed) 与 finished 双信号时重复收尾。
        """
        if self._handled or self.current_file is None:
            return
        self._handled = True

        path = self.current_file
        self.current_file = None
        signalBus.file_finished.emit(path, success)

        name = Path(path).name
        if success:
            self._ok_count += 1
            signalBus.log_emitted.emit(
                f"{name} 处理完成，退出码: {exit_code}", "success"
            )
            logger.info(f"文件处理完成: {name} 退出码={exit_code}")
        else:
            self._fail_count += 1
            signalBus.log_emitted.emit(
                f"{name} 转换失败（退出码 {exit_code}），已记录并跳过，继续后续文件。",
                "error",
            )
            # 单文件失败：浮层提示（跳过并继续，不中断整批）
            signalBus.toast_requested.emit(
                f"{name} 转换失败，已跳过并继续。", "error"
            )
            logger.warning(f"文件转换失败（跳过）: {name} 退出码={exit_code}")

        self._continue_internal()

    def _continue_internal(self):
        """推进下一个待处理文件；队列空则结束整批任务。"""
        if self.pending_files:
            # 延迟到下一轮事件循环再启动：确保崩溃/结束的残存信号先被消化，
            # 避免误把下一个文件当成失败收尾
            QTimer.singleShot(0, self._start_next_file)
            return

        total = self._ok_count + self._fail_count
        signalBus.log_emitted.emit("全部文件处理完毕。", "success")
        logger.info(f"转换任务全部结束 成功={self._ok_count} 失败={self._fail_count}")
        # 整批结束浮层汇总：全部成功→success；有失败→warning
        if self._fail_count:
            signalBus.toast_requested.emit(
                f"转换结束：成功 {self._ok_count} 个，失败 {self._fail_count} 个。",
                "warning",
            )
        else:
            signalBus.toast_requested.emit(
                f"全部转换完成：{total} 个文件。", "success"
            )
        signalBus.conversion_finished.emit(0)
