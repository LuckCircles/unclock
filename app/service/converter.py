# coding: utf-8
"""解密服务 —— 封装 um.exe 进程调用与批量任务队列。

view 层通过 ``signalBus.request_start`` / ``request_stop`` 驱动本服务，
本服务经 ``signalBus`` 反向广播解密事件（file_started / file_finished /
log_emitted / conversion_started / conversion_finished），实现 view 与
service 解耦。
"""

import os
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer

from ..common.config import CONVERSION_OPTIONS, cfg
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

# 单文件处理超时（毫秒）：超过即 kill 进程、标记失败并跳过，防止卡死整个队列
_FILE_TIMEOUT_MS = 120_000


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
        self._timed_out = False  # 当前文件是否因超时被 kill（区分失败原因）
        self._stopped = False    # 本轮是否被用户停止（阻止延迟排队继续启动下一文件）
        self._saw_failure = False  # 当前文件输出中是否出现失败标志（退出码之外的兜底）

        # 单文件处理超时计时器：启动进程时计时，收尾时停止
        self._timeout_timer = QTimer(self)
        self._timeout_timer.setSingleShot(True)
        self._timeout_timer.timeout.connect(self._on_file_timeout)

        self._wire_process()
        self._wire_signals()
        # 软件启动时注入一次 ffmpeg PATH（配置变更时在 _wire_signals 里同步刷新），
        # 对 um 子进程全程生效，无需每个文件启动前重复设置
        self._apply_ffmpeg_env()

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
        # 任务页移除/删除排队中的文件时，同步从待处理队列剔除（解密不管理已移出列表的文件）
        signalBus.queue_remove.connect(self._remove_from_queue)
        # 配置页修改 ffmpeg 路径后立即重新注入，无需重启软件
        cfg.ffmpeg_path.valueChanged.connect(self._on_ffmpeg_path_changed)

    def _on_ffmpeg_path_changed(self, *_args):
        self._apply_ffmpeg_env()

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
            logger.error(f"解密启动失败: um.exe 不存在 {cfg.um_path.value}")
            return

        if not self.pending_files:
            signalBus.log_emitted.emit("没有可解密的加密文件。", "warning")
            signalBus.toast_requested.emit("没有可解密的加密文件。", "warning")
            signalBus.conversion_finished.emit(-1)
            logger.warning("解密启动失败: 没有可解密的加密文件")
            return

        self._ok_count = 0
        self._fail_count = 0
        self._stopped = False
        self._warn_unsupported_negative_options()
        signalBus.conversion_started.emit(len(self.pending_files))
        logger.info(f"开始解密任务: {len(self.pending_files)} 个文件")
        signalBus.log_emitted.emit(
            f"准备解密 {len(self.pending_files)} 个文件。", "info"
        )
        self._start_next_file()

    def _warn_unsupported_negative_options(self):
        """「否」+ um 默认开启的选项：um 未提供关闭参数，明确提示而非静默等价「默认」。

        um v0.2.20 六个参数中仅 ``-n``（跳过无动作解码器）默认开启，且无
        ``--no-*`` 形式；其余五个默认关闭，「否」与「默认」同为不传参。
        """
        for item, label, _arg, um_default_on in CONVERSION_OPTIONS:
            if item.value == "否" and um_default_on:
                signalBus.log_emitted.emit(
                    f"「{label}」um 默认开启且无关闭参数，选项“否”已按默认执行。",
                    "warning",
                )

    def stop(self):
        """停止本轮任务：无论 QProcess 处于 Running / Starting / NotRunning，
        都清空队列并阻止已排队的延迟启动继续处理，避免「按钮已复位、后台还在跑」。
        """
        cancelled = []
        if self.current_file:
            cancelled.append(self.current_file)
        cancelled.extend(self.pending_files)
        had_task = bool(cancelled) or self.process.state() != QProcess.NotRunning

        self._stopped = True
        self.pending_files.clear()
        self.current_file = None
        self._handled = True
        self._timeout_timer.stop()
        if self.process.state() != QProcess.NotRunning:
            self.process.kill()

        if had_task:
            signalBus.log_emitted.emit("正在停止任务...", "warning")
            signalBus.toast_requested.emit("已停止解密。", "warning")
            logger.warning("用户请求停止解密任务")
            for path in cancelled:
                signalBus.file_cancelled.emit(path)
        # 复位按钮态（用户停止或退出清理时都回到 idle）
        signalBus.conversion_finished.emit(0)

    def _remove_from_queue(self, path: str):
        """把指定文件从待处理队列剔除（用户在任务页移出列表/删除时调用）。

        仅影响尚未开始的排队文件；正在处理的无从回退。
        """
        if path in self.pending_files:
            self.pending_files.remove(path)
            logger.info(f"已从待处理队列移除: {Path(path).name}")

    # ----------------------------------------------------------------- 内部
    def _start_next_file(self):
        if self._stopped:
            return  # 用户停止后，已排队的 QTimer.singleShot 不得再启动任何文件
        if not self.pending_files:
            self.current_file = None
            self._handled = True
            signalBus.log_emitted.emit("全部解密任务已完成。", "success")
            signalBus.conversion_finished.emit(0)
            return

        self.current_file = self.pending_files.pop(0)
        self._handled = False
        self._saw_failure = False
        # 排队期间被删除/移走的文件（含用户在任务页移除、或外部删除）：跳过，
        # 不计失败；仍发 file_finished 推进进度条，然后继续后续文件。
        if not os.path.exists(self.current_file):
            missing = self.current_file
            self.current_file = None
            self._handled = True
            signalBus.file_finished.emit(missing, False)
            signalBus.log_emitted.emit(
                f"跳过（文件不存在）: {Path(missing).name}", "warning"
            )
            logger.info(f"跳过不存在的文件: {missing}")
            self._continue_internal()
            return
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
        # 进程已启动：开始单文件超时计时（收尾时停止）
        self._timed_out = False
        self._timeout_timer.start(_FILE_TIMEOUT_MS)

    def _on_file_timeout(self):
        """单文件处理超时：kill 进程，复用既有 finished/Crashed 收尾链路。

        ``_timed_out`` 标记供 ``_finalize_current_file`` 区分「超时终止」与
        「进程自身失败」，给出不同的失败文案。
        """
        if self.process.state() != QProcess.Running or self.current_file is None:
            return
        self._timed_out = True
        name = Path(self.current_file).name
        signalBus.log_emitted.emit(
            f"处理超时（{_FILE_TIMEOUT_MS // 1000} 秒），终止 {name} 并跳过。", "warning"
        )
        logger.warning(f"文件处理超时被终止: {name}")
        self.process.kill()

    def _build_file_args(self, file_path: str) -> list[str]:
        args = ["-i", file_path]
        if cfg.output_dir.value:
            args.extend(["-o", cfg.output_dir.value])

        # QQ Music 密钥自动获取：仅 QQ 音乐格式才传 qmpc-mmkv-cli 路径，
        # 非 QQ 格式（ncm/kgm 等）不传，避免 um 无谓调用 qmpc 触发 WARN
        if _is_qmc_file(file_path) and cfg.qmpc_path.value and os.path.exists(cfg.qmpc_path.value):
            args.extend(["--qmpc-mmkv-cli-exe", cfg.qmpc_path.value])

        for item, _label, arg, _um_default_on in CONVERSION_OPTIONS:
            # 「是」才追加参数；「否」/「默认」均不传（um 未提供关闭参数，
            # 无法表达显式关闭，_warn_unsupported_negative_options 已提示用户）
            if _TRISTATE.get(item.value) is True:
                args.append(arg)
        return args

    def _apply_ffmpeg_env(self):
        """把 ffmpeg 所在目录前置注入 um 子进程 PATH（仅本软件派生的子进程生效）。

        软件启动时与配置变更时各调用一次：QProcessEnvironment 设置后对
        该进程对象后续所有 start 持续生效。um 查找 ffmpeg/ffprobe 只认
        自己进程的 PATH（不接受路径参数，也不搜索自身目录）；不注入则
        系统未装 ffmpeg 的用户即使配置了路径、打包产物内嵌了 ffmpeg.exe，
        开启「更新封面」也会失败。
        """
        env = QProcessEnvironment.systemEnvironment()
        ffmpeg_path = cfg.ffmpeg_path.value
        if ffmpeg_path and os.path.isfile(ffmpeg_path):
            ffmpeg_dir = str(Path(ffmpeg_path).parent)
            current = env.value("PATH", "")
            env.insert("PATH", f"{ffmpeg_dir}{os.pathsep}{current}" if current else ffmpeg_dir)
        self.process.setProcessEnvironment(env)

    def _log_process_output(self, raw: bytes, default_level: str):
        """um 进程输出处理：所有原始行写 app.log，UI 只显示 success/error 关键结果。"""
        text = decode_process_output(raw)
        for line in text.replace("\r", "\n").splitlines():
            if not line.strip():
                continue
            # 原始输出全部写入 app.log（详细排查用）
            logger.debug(f"um 输出: {line}")
            lower = line.lower()
            # 退出码之外的兜底：um 明确报失败时即使返回 0 也不算成功
            if "conversion failed" in lower or "run app failed" in lower:
                self._saw_failure = True
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
        self._finalize_current_file(
            exit_code == 0 and not self._saw_failure, exit_code
        )

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
        self._timeout_timer.stop()

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
            if self._timed_out:
                reason = f"{name} 处理超时（{_FILE_TIMEOUT_MS // 1000} 秒），已终止并跳过，继续后续文件。"
            else:
                reason = f"{name} 解密失败（退出码 {exit_code}），已记录并跳过，继续后续文件。"
            signalBus.log_emitted.emit(reason, "error")
            # 单文件失败：浮层提示（跳过并继续，不中断整批）
            signalBus.toast_requested.emit(
                f"{name} 解密失败，已跳过并继续。", "error"
            )
            logger.warning(f"文件解密失败（跳过）: {name} 退出码={exit_code}")

        self._continue_internal()

    def _continue_internal(self):
        """推进下一个待处理文件；队列空则结束整批任务。"""
        if self._stopped:
            return  # 已停止：不得再广播「全部完成」或推进队列
        if self.pending_files:
            # 延迟到下一轮事件循环再启动：确保崩溃/结束的残存信号先被消化，
            # 避免误把下一个文件当成失败收尾
            QTimer.singleShot(0, self._start_next_file)
            return

        total = self._ok_count + self._fail_count
        signalBus.log_emitted.emit("全部文件解密完毕。", "success")
        logger.info(f"解密任务全部结束 成功={self._ok_count} 失败={self._fail_count}")
        # 整批结束浮层汇总：全部成功→success；有失败→warning
        if self._fail_count:
            signalBus.toast_requested.emit(
                f"解密结束：成功 {self._ok_count} 个，失败 {self._fail_count} 个。",
                "warning",
            )
        else:
            signalBus.toast_requested.emit(
                f"全部解密完成：{total} 个文件。", "success"
            )
        signalBus.conversion_finished.emit(0)
