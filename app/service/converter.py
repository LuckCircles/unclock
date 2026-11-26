# coding: utf-8
"""解密服务 —— 封装 um.exe / um-cli-rs 进程调用与批量任务队列。

view 层通过 ``signalBus.request_start`` / ``request_stop`` 驱动本服务，
本服务经 ``signalBus`` 反向广播解密事件（file_started / file_finished /
log_emitted / conversion_started / conversion_finished），实现 view 与
service 解耦。

交互算法借鉴官方 um-conv（仅后端，UI 零改动）：
- preflight：先解析外部工具，再决定是否启动任务；
- plan：一次扫描完成 claim / 输出基名 / lane 标记；
- worker pool：受控并发，QMC 密钥查询串行、同名输出串行；
- generation：丢弃上一轮在飞进程的迟到回调；
- cancel：只置位、不 kill 在飞进程，未领取的任务标记 cancelled。
"""

import ctypes
import os
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer

from ..common.config import (
    CONVERSION_OPTIONS,
    PROJECT_ROOT,
    cfg,
)
from ..common.logger import logger
from ..common.encoder_probe import (
    AAC_CANDIDATES,
    OGG_CANDIDATES,
    encoding_args,
    probe_encoders,
    resolve_encoder,
)
from ..common.i18n import translate_ui
from ..common.rust_decrypt import (
    RustEngineError,
    cleanup_temp,
    decrypt_args_for,
    finalize_output,
    parse_probe,
    prepare_rust_job,
    subcommand_for,
)
from ..common.signal_bus import signalBus
from ..common.task_planner import (
    ToolResolveError,
    build_decrypt_plan,
    resolve_executable,
    resolve_parallel,
)
from ..common.utils import decode_process_output, simplify_process_line

# 三态选项 → 是否启用
_TRISTATE = {"否": False, "是": True, "默认": None}

# 单文件处理超时（毫秒）：超过即 kill 进程、标记失败并跳过，防止卡死整个队列
_FILE_TIMEOUT_MS = 120_000

# Windows 空闲优先级：OpenProcess(PROCESS_SET_INFORMATION) + SetPriorityClass
_PROCESS_SET_INFORMATION = 0x0200
_IDLE_PRIORITY_CLASS = 0x00000040


@dataclass
class _Job:
    """单个在规划中的解密任务及其运行时状态。"""

    task: object  # common.task_planner.DecryptTask
    process: QProcess | None = None
    timer: QTimer | None = None
    handled: bool = False
    timed_out: bool = False
    saw_failure: bool = False
    # um-cli-rs 引擎的阶段状态：probe（-I 探测）→ decrypt（带 ekey 解密）
    program: str = ""
    args: list[str] = field(default_factory=list)
    stage: str = ""
    subcommand: str = ""
    dest: str = ""
    sidecars: tuple[str, ...] = ()
    tmp_dir: str = ""
    output_chunks: list[bytes] = field(default_factory=list)


def _set_idle_priority(pid: int) -> None:
    """Windows 下把刚启动的子进程设为空闲优先级，避免抢占前台交互。"""
    if os.name != "nt" or not pid:
        return
    try:
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(_PROCESS_SET_INFORMATION, False, int(pid))
        if not handle:
            return
        try:
            kernel32.SetPriorityClass(handle, _IDLE_PRIORITY_CLASS)
        finally:
            kernel32.CloseHandle(handle)
    except (AttributeError, OSError, ValueError) as exc:
        logger.debug(f"设置子进程空闲优先级失败: {exc}")


class UnlockMusicConverter(QObject):
    """带预检与受控并发的批量解密服务。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pending: list[_Job] = []
        self._active: dict[str, _Job] = {}
        self._active_lanes: set[str] = set()
        self._generation = 0
        self._running = False
        self._stop_requested = False
        self._ok_count = 0
        self._fail_count = 0
        self._skipped_count = 0
        self._cancelled_count = 0
        self._um_path = ""
        self._ffmpeg_path = ""
        self._qmpc_path = ""
        self._rust_path = ""
        self._encoding_args: dict[str, list[str]] = {}
        self._engine = "um"
        self._worker_limit = 1
        self._wire_signals()

    # ------------------------------------------------------------------ 信号
    def _wire_signals(self):
        # request_start 不直连本服务：由 MainWindow._dispatch_start 统一取文件列表后调用
        # start(files)，否则 files=None 的空队列路径会先弹"没有可转换文件"假警告
        signalBus.request_stop.connect(self.stop)
        # 任务页移除/删除排队中的文件时，同步从待处理队列剔除
        signalBus.queue_remove.connect(self._remove_from_queue)

    # ------------------------------------------------------------- 公共 API
    @property
    def pending_files(self) -> list[str]:
        """兼容旧属性：当前排队（尚未启动）的路径列表。"""
        return [job.task.path for job in self._pending]

    @property
    def current_file(self) -> str | None:
        """兼容旧属性：第一个在飞文件路径（并发下仅代表其中之一）。"""
        return next(iter(self._active), None)

    def start(self, files=None):
        """启动转换。``files`` 为 None 时保留已有待处理队列。"""
        if self._running:
            signalBus.log_emitted.emit("任务已经在运行中。", "warning")
            return

        if files is not None:
            self._pending = [_Job(task) for task in build_decrypt_plan(files)]

        if not self._pending:
            signalBus.log_emitted.emit("没有可解密的加密文件。", "warning")
            signalBus.toast_requested.emit("没有可解密的加密文件。", "warning")
            signalBus.conversion_finished.emit(-1)
            logger.warning("解密启动失败: 没有可解密的加密文件")
            return

        # preflight：先解析所选引擎及其辅助工具，失败即时反馈，不让任务跑一半才报错
        self._engine = str(cfg.decrypt_engine.value or "um")
        um, ffmpeg, qmpc, rust = self._preflight()
        if not (rust if self._engine == "um-cli-rs" else um):
            return
        self._um_path, self._ffmpeg_path, self._qmpc_path, self._rust_path = (
            um, ffmpeg, qmpc, rust
        )
        self._apply_encoding_policy()

        self._ok_count = 0
        self._fail_count = 0
        self._skipped_count = 0
        self._cancelled_count = 0
        self._stop_requested = False
        self._active.clear()
        self._active_lanes.clear()
        self._generation += 1

        wanted = resolve_parallel(
            bool(cfg.parallel_enabled.value), int(cfg.parallel_count.value)
        )
        # 同名输出/QMC 密钥 lane 互斥，实际并发不必超过待办 lane 数
        lanes = {job.task.lane for job in self._pending}
        self._worker_limit = max(1, min(wanted, len(lanes)))
        signalBus.log_emitted.emit(
            f"解密调度（{self._engine}）：{len(self._pending)} 个任务 / "
            f"{len(lanes)} 条互斥通道 / {self._worker_limit} 个并发 worker。",
            "info",
        )
        if self._engine == "um-cli-rs":
            signalBus.log_emitted.emit(
                "um-cli-rs 引擎不使用 um 的六个三态选项，已忽略；"
                "仅处理 NCM / KGM / KWM / QMC2 官方支持的格式。",
                "info",
            )
        else:
            self._warn_unsupported_negative_options()
        self._running = True
        signalBus.conversion_started.emit(len(self._pending))
        logger.info(f"开始解密任务: {len(self._pending)} 个文件")
        signalBus.log_emitted.emit(
            f"准备解密 {len(self._pending)} 个文件。", "info"
        )
        self._pump()

    def _apply_encoding_policy(self):
        """解析 AAC/OGG 编码器策略并留痕。

        两条解密链路目前只做封装探测与元数据写入、不转码，所以生成的参数
        暂不参与输出；配置与探测结果先落地，后续接入转码时直接取用。
        """
        available = probe_encoders(self._ffmpeg_path)
        aac = resolve_encoder(str(cfg.aac_encoder.value), AAC_CANDIDATES, available)
        ogg = resolve_encoder(str(cfg.ogg_encoder.value), OGG_CANDIDATES, available)
        self._encoding_args = encoding_args(aac, bool(cfg.fdk_vbr.value), ogg)
        detail = f"AAC={aac or '不可用'} / OGG={ogg or '不可用'}"
        if aac is None or ogg is None:
            signalBus.log_emitted.emit(
                f"部分编码器不可用（{detail}），请检查 ffmpeg 路径或设置页选择。",
                "warning",
            )
        signalBus.log_emitted.emit(
            f"编码策略：{detail}（当前链路仅解密不转码，参数暂存）。", "info"
        )
        logger.info(f"编码策略: {detail}")

    def _preflight(self) -> tuple[str, str, str, str]:
        """解析所选引擎 + 辅助工具路径；所选引擎缺失即终止，其余仅告警。"""
        tools_dir = PROJECT_ROOT / "tools"
        primary_name = "um_cli_rs" if self._engine == "um-cli-rs" else "um"
        primary_cfg = (
            cfg.um_cli_rs_path.value if self._engine == "um-cli-rs"
            else cfg.um_path.value
        )
        try:
            primary = resolve_executable(primary_cfg, primary_name, tools_dir)
        except ToolResolveError as exc:
            msg = (
                f"未找到{self._engine} 可执行文件，请在配置界面设置路径。（{exc}）"
            )
            signalBus.log_emitted.emit(msg, "error")
            signalBus.toast_requested.emit(msg, "error")
            signalBus.conversion_finished.emit(-1)
            logger.error(f"解密启动失败: {exc}")
            return "", "", "", ""

        optional = {}
        for label, configured, name in (
            ("ffmpeg", cfg.ffmpeg_path.value, "ffmpeg"),
            ("qmpc-mmkv-cli", cfg.qmpc_path.value, "qmpc-mmkv-cli"),
            ("um", cfg.um_path.value, "um"),
            ("um_cli_rs", cfg.um_cli_rs_path.value, "um_cli_rs"),
        ):
            try:
                optional[label] = resolve_executable(configured, name, tools_dir)
            except ToolResolveError as exc:
                optional[label] = ""
                signalBus.log_emitted.emit(
                    f"未找到 {label}，相关能力可能不可用：{exc}", "warning"
                )
        um = primary if self._engine != "um-cli-rs" else optional["um"]
        rust = primary if self._engine == "um-cli-rs" else optional["um_cli_rs"]
        return um, optional["ffmpeg"], optional["qmpc-mmkv-cli"], rust

    def stop(self):
        """优雅停止：未领取的任务立即取消；在飞任务跑完后统一收尾。

        借鉴官方语义——取消只置位，不打断在飞进程，避免把写了一半的输出
        留在磁盘上。generation 不变，保证在飞回调仍能正常收尾。
        """
        if not self._running:
            return
        if not self._stop_requested:
            self._stop_requested = True
            for job in self._pending:
                self._cancelled_count += 1
                signalBus.file_cancelled.emit(job.task.path)
            self._pending.clear()
            signalBus.log_emitted.emit("正在停止任务（在飞文件将处理完成后退出）...", "warning")
            signalBus.toast_requested.emit("已停止解密，未开始的文件已取消。", "warning")
            logger.warning("用户请求停止解密任务")

        if not self._active:
            self._finish_run()

    def _remove_from_queue(self, path: str):
        """把指定文件从待处理队列剔除（任务页移出列表/删除时调用）。"""
        for job in self._pending:
            if job.task.path == path:
                self._pending.remove(job)
                logger.info(f"已从待处理队列移除: {Path(path).name}")
                return

    def _warn_unsupported_negative_options(self):
        """「否」+ um 默认开启的选项：um 未提供关闭参数，明确提示而非静默等价「默认」。"""
        for item, label, _arg, um_default_on in CONVERSION_OPTIONS:
            if item.value == "否" and um_default_on:
                signalBus.log_emitted.emit(
                    f"「{label}」um 默认开启且无关闭参数，选项“否”已按默认执行。",
                    "warning",
                )

    # --------------------------------------------------------------- 调度器
    def _pump(self):
        """按 worker 数与 lane 互斥规则领取待办任务。"""
        if not self._running or self._stop_requested:
            if not self._active:
                self._finish_run()
            return
        while len(self._active) < self._worker_limit:
            candidate = next(
                (job for job in self._pending if job.task.lane not in self._active_lanes),
                None,
            )
            if candidate is None:
                break
            self._pending.remove(candidate)
            self._start_job(candidate, self._generation)
        if not self._active and not self._pending:
            self._finish_run()

    def _start_job(self, job: _Job, generation: int):
        path = job.task.path
        name = Path(path).name
        if not os.path.isfile(path):
            signalBus.log_emitted.emit(f"跳过（文件不存在）: {name}", "warning")
            logger.info(f"跳过不存在的文件: {path}")
            self._finalize_job(job, False, 0, generation, skipped=True)
            return

        self._active[path] = job
        self._active_lanes.add(job.task.lane)
        signalBus.file_started.emit(path)
        if not self._prepare_job(job, generation):
            return
        signalBus.log_emitted.emit(f"开始处理: {name}", "info")
        self._launch_process(job, generation)

    def _prepare_job(self, job: _Job, generation: int) -> bool:
        """按所选引擎准备首阶段命令；失败时收尾并返回 False。"""
        if self._engine != "um-cli-rs":
            job.program = self._um_path
            job.args = self._build_file_args(job.task)
            job.stage = ""
            return True

        try:
            plan = prepare_rust_job(
                job.task.path,
                job.task.basename,
                str(cfg.temp_dir.value or ""),
            )
        except RustEngineError as exc:
            self._rust_failure(job, generation, str(exc))
            return False
        job.program = self._rust_path
        job.args = plan["args"]
        job.stage = plan["stage"]
        job.subcommand = plan["subcommand"]
        job.dest = plan["dest"]
        job.sidecars = plan["sidecars"]
        job.tmp_dir = plan["tmp_dir"]
        job.output_chunks = []
        return True

    def _launch_process(self, job: _Job, generation: int):
        """启动（或续启）一个 QProcess；信号接线对 probe / decrypt 两阶段通用。"""
        if job.process is not None:
            job.process.deleteLater()  # 上一阶段（-I）的进程，不能在 finished 回调里同步析构
            job.process = None
        if job.timer is not None:
            job.timer.stop()
            job.timer.deleteLater()
            job.timer = None
        process = QProcess(self)
        process.setProcessEnvironment(self._process_environment())
        job.process = process
        job.timer = QTimer(self)
        job.timer.setSingleShot(True)
        job.timer.timeout.connect(
            lambda j=job, g=generation: self._on_timeout(j, g)
        )
        process.readyReadStandardOutput.connect(
            lambda j=job, g=generation: self._on_output(j, g, process.readAllStandardOutput)
        )
        process.readyReadStandardError.connect(
            lambda j=job, g=generation: self._on_output(j, g, process.readAllStandardError)
        )
        process.finished.connect(
            lambda code, status, j=job, g=generation: self._on_finished(code, j, g)
        )
        process.errorOccurred.connect(
            lambda error, j=job, g=generation: self._on_process_error(error, j, g)
        )

        args = job.args
        logger.debug(f"启动命令: {job.program} {' '.join(args)}")
        process.start(job.program, args)
        if not process.waitForStarted(3000):
            signalBus.log_emitted.emit(f"启动失败: {Path(job.task.path).name}", "error")
            self._finalize_job(job, False, -1, generation)
            return
        _set_idle_priority(process.processId())
        job.timed_out = False
        job.timer.start(_FILE_TIMEOUT_MS)

    def _process_environment(self) -> QProcessEnvironment:
        """把 ffmpeg 目录前置注入子进程 PATH（um 查找 ffmpeg 只认 PATH）。"""
        env = QProcessEnvironment.systemEnvironment()
        if self._ffmpeg_path:
            ffmpeg_dir = str(Path(self._ffmpeg_path).parent)
            current = env.value("PATH", "")
            env.insert("PATH", f"{ffmpeg_dir}{os.pathsep}{current}" if current else ffmpeg_dir)
        return env

    def _build_file_args(self, task) -> list[str]:
        args = ["-i", task.path]
        if cfg.output_dir.value:
            args.extend(["-o", cfg.output_dir.value])
        if task.needs_key_lookup and self._qmpc_path:
            args.extend(["--qmpc-mmkv-cli-exe", self._qmpc_path])
        for item, _label, arg, _um_default_on in CONVERSION_OPTIONS:
            if _TRISTATE.get(item.value) is True:
                args.append(arg)
        return args

    # ------------------------------------------------------------- 进程回调
    def _on_output(self, job: _Job, generation: int, reader):
        if generation != self._generation or job.handled:
            return
        raw = reader().data()
        if job.stage == "probe":
            # -I 输出含 ekey（敏感），只缓存给解析器，绝不写进运行日志
            job.output_chunks.append(raw)
            return
        self._log_process_output(job, raw)

    def _log_process_output(self, job: _Job, raw: bytes):
        text = decode_process_output(raw)
        for line in text.replace("\r", "\n").splitlines():
            if not line.strip():
                continue
            logger.debug(f"{self._engine} 输出: {line}")
            lower = line.lower()
            if "conversion failed" in lower or "run app failed" in lower:
                job.saw_failure = True
            simplified, level = simplify_process_line(line)
            if simplified and level in ("success", "error"):
                signalBus.log_emitted.emit(simplified, level)

    def _on_finished(self, exit_code: int, job: _Job, generation: int):
        if generation != self._generation or job.handled:
            return
        if job.stage == "probe":
            self._continue_rust_job(job, generation, exit_code)
            return
        success = exit_code == 0 and not job.saw_failure
        if self._engine == "um-cli-rs" and success:
            target, skipped = self._finalize_rust_output(job)
            if target and not skipped:
                signalBus.log_emitted.emit(
                    f"{Path(job.task.path).name} 已输出：{target}", "success"
                )
            self._finalize_job(
                job, target is not None and not skipped,
                exit_code, generation, skipped=skipped,
            )
            return
        self._finalize_job(job, success, exit_code, generation)

    def _continue_rust_job(self, job: _Job, generation: int, exit_code: int):
        """``-I`` 探测完成：解析 JSON、补齐 ekey 参数，续启第二阶段解密。"""
        name = Path(job.task.path).name
        if exit_code != 0 or job.timed_out:
            self._rust_failure(job, generation, f"探测 {name} 失败（退出码 {exit_code}）")
            return
        try:
            subcmd = subcommand_for(job.task.path) or job.subcommand
            info = parse_probe(
                subcmd, decode_process_output(b"".join(job.output_chunks))
            )
            args = decrypt_args_for(
                subcmd, job.task.path, job.dest, info,
                self._qmpc_path, self._rust_path,
                str(cfg.temp_dir.value or ""),
            )
        except RustEngineError as exc:
            self._rust_failure(job, generation, str(exc))
            return

        job.args = args
        job.stage = "decrypt"
        job.subcommand = subcmd
        job.output_chunks = []
        logger.debug(f"um-cli-rs {subcmd} 探测完成，进入解密阶段: {name}")
        self._launch_process(job, generation)

    def _finalize_rust_output(self, job: _Job) -> tuple[str | None, bool]:
        """把临时产物按真实格式落到目标目录，并清理临时旁路文件。"""
        try:
            return finalize_output(
                job.dest,
                job.task.basename,
                cfg.output_dir.value,
                str(Path(job.task.path).parent),
                self._ffmpeg_path,
                bool(cfg.reconvert_done.value),
                job.task.path,
            )
        except (OSError, ValueError) as exc:
            signalBus.log_emitted.emit(f"写入解密结果失败：{exc}", "error")
            logger.warning(f"写入解密结果失败: {exc}")
            return None, False
        finally:
            cleanup_temp(job.tmp_dir)

    def _rust_failure(self, job: _Job, generation: int, reason: str):
        """Rust 引擎错误：写日志、清理临时目录并按失败收尾。"""
        name = Path(job.task.path).name
        signalBus.log_emitted.emit(f"{name}：{reason}", "error")
        signalBus.toast_requested.emit(f"{name} 解密失败：{reason}", "error")
        logger.warning(f"um-cli-rs 引擎失败: {name} - {reason}")
        cleanup_temp(job.tmp_dir)
        self._finalize_job(job, False, -1, generation)

    def _on_process_error(self, error, job: _Job, generation: int):
        if generation != self._generation or job.handled:
            return
        if error == QProcess.Crashed:
            self._finalize_job(job, False, -1, generation)
        elif error == QProcess.FailedToStart:
            signalBus.log_emitted.emit(
                f"进程启动失败，请检查 {self._engine} 可执行文件路径与权限。", "error"
            )
        else:
            signalBus.log_emitted.emit(f"进程错误: {error}", "warning")

    def _on_timeout(self, job: _Job, generation: int):
        """单文件超时：kill 该进程并由 finished 回调统一收尾。"""
        if generation != self._generation or job.handled or job.process is None:
            return
        if job.process.state() != QProcess.Running:
            return
        job.timed_out = True
        name = Path(job.task.path).name
        signalBus.log_emitted.emit(
            f"处理超时（{_FILE_TIMEOUT_MS // 1000} 秒），终止 {name} 并跳过。", "warning"
        )
        logger.warning(f"文件处理超时被终止: {name}")
        job.process.kill()

    def _finalize_job(self, job: _Job, success: bool, exit_code: int,
                      generation: int, skipped: bool = False):
        """收尾单个任务：发信号、计数、释放 lane，再推进队列。"""
        if generation != self._generation or job.handled:
            return
        job.handled = True
        if job.timer is not None:
            job.timer.stop()
        self._active.pop(job.task.path, None)
        self._active_lanes.discard(job.task.lane)
        if job.process is not None:
            job.process.deleteLater()
        if self._engine == "um-cli-rs" and job.tmp_dir:
            cleanup_temp(job.tmp_dir)  # 幂等：失败/超时路径也要清理临时目录

        signalBus.file_finished.emit(job.task.path, success)
        name = Path(job.task.path).name
        if skipped:
            self._skipped_count += 1
        elif success:
            self._ok_count += 1
            if (self._engine == "um-cli-rs"
                    and _TRISTATE.get(cfg.remove_source.value) is True):
                try:
                    os.remove(job.task.path)
                    logger.info(f"已按设置删除源文件: {job.task.path}")
                except OSError as exc:
                    signalBus.log_emitted.emit(
                        f"源文件删除失败：{name}（{exc}）", "warning"
                    )
            signalBus.log_emitted.emit(
                f"{name} 处理完成，退出码: {exit_code}", "success"
            )
            logger.info(f"文件处理完成: {name} 退出码={exit_code}")
        else:
            self._fail_count += 1
            if job.timed_out:
                reason = (f"{name} 处理超时（{_FILE_TIMEOUT_MS // 1000} 秒），"
                          "已终止并跳过，继续后续文件。")
            else:
                reason = f"{name} 解密失败（退出码 {exit_code}），已记录并跳过，继续后续文件。"
            signalBus.log_emitted.emit(reason, "error")
            signalBus.toast_requested.emit(
                f"{name} {translate_ui('解密失败，已跳过并继续。')}", "error"
            )
            logger.warning(f"文件解密失败（跳过）: {name} 退出码={exit_code}")

        QTimer.singleShot(0, self._pump)

    def _finish_run(self):
        """整批结束：按官方汇总格式写日志与提示，UI 信号保持原样。"""
        if not self._running:
            return
        self._running = False
        self._stop_requested = False
        done = self._ok_count + self._skipped_count + self._fail_count
        total = done + self._cancelled_count
        summary = (f"已处理 {done}/{total} 个文件，成功 {self._ok_count}，"
                   f"跳过 {self._skipped_count}，错误 {self._fail_count}，"
                   f"取消 {self._cancelled_count}。")
        signalBus.log_emitted.emit(summary, "warning" if self._fail_count else "success")
        logger.info(summary)
        if self._fail_count:
            signalBus.toast_requested.emit(summary, "warning")
        elif self._cancelled_count:
            signalBus.toast_requested.emit(summary, "info")
        else:
            signalBus.toast_requested.emit(
                f"全部解密完成：成功 {self._ok_count} 个文件。", "success"
            )
        signalBus.conversion_finished.emit(0)
