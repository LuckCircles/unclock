# coding: utf-8
"""ffmpeg 音频编码器探测与参数生成（纯逻辑，不依赖 UI）。

借鉴官方 um-conv 的策略：先用 ``ffmpeg -encoders`` 得到真实可用列表，
再按「用户显式选择 → 自动降级顺序」解析实际编码器，最后才拼参数。
探测结果按 ffmpeg 路径缓存，避免每次转换/每次打开设置都启进程。
"""

import re
import subprocess
from pathlib import Path

from .logger import logger

# 关注的编码器，顺序即官方降级顺序：FDK 优先于内置 AAC，Opus 优先于 Vorbis
AAC_CANDIDATES = ("libfdk_aac", "aac")
OGG_CANDIDATES = ("libopus", "libvorbis")
ALL_ENCODERS = AAC_CANDIDATES + OGG_CANDIDATES

_PROBE_TIMEOUT_S = 8
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
# 形如 " A....D libfdk_aac           Fraunhofer FDK AAC ..."：
# 6 位能力标志 + 编码器名（至少两个空格后才是描述），借此排除说明行 " V..... = Video"
_ENCODER_LINE = re.compile(r"^\s[VAS][.FXBD]{5}\s+(\S+)\s{2,}")

# key = ffmpeg 路径字符串，value = 可用编码器名集合（冻结）
_cache: dict[str, frozenset[str]] = {}


def probe_encoders(ffmpeg_path: str) -> frozenset[str]:
    """返回该 ffmpeg 可用的编码器名集合；探测失败返回空集合。"""
    if not ffmpeg_path:
        return frozenset()
    key = str(Path(ffmpeg_path))
    if key in _cache:
        return _cache[key]

    found: set[str] = set()
    if Path(ffmpeg_path).is_file():
        try:
            res = subprocess.run(
                [ffmpeg_path, "-hide_banner", "-encoders"],
                capture_output=True,
                creationflags=_NO_WINDOW,
                timeout=_PROBE_TIMEOUT_S,
            )
            output = res.stdout.decode("utf-8", "replace") + "\n" + res.stderr.decode(
                "utf-8", "replace"
            )
            for line in output.splitlines():
                match = _ENCODER_LINE.match(line)
                if match:
                    found.add(match.group(1))
        except (OSError, subprocess.SubprocessError) as exc:
            logger.debug(f"探测 ffmpeg 编码器失败: {exc}")
    available = frozenset(found)
    _cache[key] = available
    return available


def supported_hint(available: frozenset[str]) -> str:
    """设置页提示用的可读列表，固定顺序与官方一致。"""
    return " ".join(name for name in ALL_ENCODERS if name in available) or "未探测到"


def resolve_encoder(
    configured: str, candidates: tuple[str, ...], available: frozenset[str]
) -> str | None:
    """按用户选择与降级顺序返回实际可用的编码器。

    - 显式选择：不可用则返回 None，不做静默降级（由调用方提示用户）。
    - 自动选择：按 candidates 顺序取第一个可用项，全不可用返回 None。
    """
    if configured != "自动选择":
        # 显式值必须既属于该类候选又确实可用，防止配置串类（如 AAC 项填了 opus）
        return configured if configured in candidates and configured in available else None
    for name in candidates:
        if name in available:
            return name
    return None


def encoding_args(
    aac: str | None, fdk_vbr: bool, ogg: str | None
) -> dict[str, list[str]]:
    """生成 ffmpeg 编码参数，供后续转码链路使用。

    质量档位取官方中等档：FDK VBR=5 / 内置 AAC 192k / Opus 192k / Vorbis q6。
    """
    result: dict[str, list[str]] = {}
    if aac == "libfdk_aac":
        result["aac"] = (
            ["-c:a", "libfdk_aac", "-vbr", "5"]
            if fdk_vbr
            else ["-c:a", "libfdk_aac", "-b:a", "192k"]
        )
    elif aac == "aac":
        result["aac"] = ["-c:a", "aac", "-b:a", "192k"]
    if ogg == "libopus":
        result["ogg"] = ["-c:a", "libopus", "-vbr", "on", "-b:a", "192k"]
    elif ogg == "libvorbis":
        result["ogg"] = ["-c:a", "libvorbis", "-q:a", "6"]
    return result
