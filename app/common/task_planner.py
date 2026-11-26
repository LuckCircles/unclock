# coding: utf-8
"""解密任务规划与外部工具解析（纯逻辑层，不依赖任何 UI）。

借鉴官方 um-conv 的交互算法但按本项目实际收敛：

- ``resolve_executable``：配置值是绝对路径则必须存在；留空/仅文件名时先查
  内置 ``tools/``，再回退 ``$PATH``（Windows 自动补 ``.exe``）。
- ``build_decrypt_plan``：一次扫描完成 claim（是否加密）、输出基名计算与
  lane 标记。需要 qmpc 密钥的文件归入同一 ``qmc`` lane 串行执行，其余按
  去后缀基名分 lane —— 同一输出基名的文件不会并发写盘，避免撞名。
- ``resolve_parallel``：官方规则（关闭→1；<=0→CPU 核数；上限 256），
  本项目再按待办 lane 数收敛，避免开无用 worker。
"""

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from .utils import is_encrypted_file, target_basename

# QQ 音乐加密格式：需要 qmpc-mmkv-cli 取密钥，并发调用会争用同一工具，
# 借鉴官方「密钥查询串行化」的做法单独占一条 lane。
QMC_SUFFIXES = {
    ".mflac", ".mflac0", ".mflac1", ".mflac2", ".mflaca",
    ".mflach", ".mflacl", ".mflacm",
    ".mgg", ".mgg0", ".mgg1", ".mgg2", ".mgga", ".mggh", ".mggl", ".mggm",
    ".qmc0", ".qmc2", ".qmc3", ".qmc4", ".qmc6", ".qmc8",
    ".qmcflac", ".qmcogg", ".tkm", ".tm0", ".tm2", ".tm3", ".tm6",
}

MAX_PARALLEL = 256
QMC_LANE = "qmc"


class ToolResolveError(RuntimeError):
    """配置的工具路径无法解析为用户可执行的二进制。"""


@dataclass(frozen=True)
class DecryptTask:
    """单个待解密任务的规划结果。"""

    path: str
    basename: str
    lane: str

    @property
    def needs_key_lookup(self) -> bool:
        return self.lane == QMC_LANE


def is_key_lookup_file(path: str) -> bool:
    """是否属于需要 qmpc 取密钥的 QQ 音乐格式。"""
    lower = str(path).lower()
    return any(lower.endswith(suffix) for suffix in QMC_SUFFIXES)


def resolve_executable(configured: str, default_name: str,
                       search_dir: str | os.PathLike | None = None) -> str:
    """把配置值解析为真实可执行文件绝对路径。

    - 含路径分隔符/盘符：按绝对路径处理，必须存在，否则抛 ``ToolResolveError``；
    - 留空或仅文件名：先查 ``search_dir``（内置目录），再查 ``$PATH``。
    """
    value = (configured or "").strip()
    looks_like_path = (
        os.path.isabs(value)
        or bool(os.path.splitdrive(value)[0])
        or "/" in value
        or "\\" in value
    )
    if looks_like_path:
        if os.path.isfile(value):
            return str(Path(value).resolve())
        raise ToolResolveError(f"配置的可执行文件不存在：{value}")

    name = value or default_name
    if os.name == "nt" and not name.lower().endswith(".exe"):
        name += ".exe"
    if search_dir:
        candidate = Path(search_dir) / name
        if candidate.is_file():
            return str(candidate.resolve())
    found = shutil.which(name)
    if found:
        return str(Path(found).resolve())
    raise ToolResolveError(f"内置目录与 PATH 中均未找到可执行文件：{name}")


def resolve_parallel(enabled: bool, count: int) -> int:
    """官方并行数规则：关闭→1，<=0→CPU 核数，1..256 原样，>256 截断。"""
    if not enabled:
        return 1
    if count <= 0:
        count = os.cpu_count() or 1
    return max(1, min(count, MAX_PARALLEL))


def build_decrypt_plan(files) -> list[DecryptTask]:
    """过滤非加密文件并生成任务列表，保持输入顺序。

    只做一次后缀判定与基名计算，结果供调度器与参数构造复用，避免
    「规划时判定一次、真正启动时再判定一次」产生漂移。
    """
    tasks: list[DecryptTask] = []
    for path in files or []:
        if not is_encrypted_file(path):
            continue
        # 文件缺失仍保留任务：调度时按「跳过」收尾并推进进度信号。
        basename = target_basename(Path(path).name)
        lane = QMC_LANE if is_key_lookup_file(path) else basename.casefold()
        tasks.append(DecryptTask(str(path), basename, lane))
    return tasks
