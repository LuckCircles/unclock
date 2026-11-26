# coding: utf-8
"""通用工具：受支持格式判定、路径压缩、文件大小格式化、进程输出解析。"""

import ctypes
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from .logger import logger

# 受 Unlock Music 支持的文件后缀集合
# 来源：um v0.2.20 `um --supported-ext`（运行时可用该命令动态核对）
SUPPORTED_SUFFIXES = {
    ".666c6163",
    ".6d3461",
    ".6d7033",
    ".6f6767",
    ".776176",
    ".aac",
    ".bkcape",
    ".bkcflac",
    ".bkcm4a",
    ".bkcmp3",
    ".bkcogg",
    ".bkcwav",
    ".bkcwma",
    ".flac",
    ".kgg",
    ".kgm",
    ".kgm.flac",
    ".kgma",
    ".kwm",
    ".m4a",
    ".mflac",
    ".mflac0",
    ".mflac1",
    ".mflac2",
    ".mflaca",
    ".mflach",
    ".mflacl",
    ".mflacm",
    ".mgg",
    ".mgg0",
    ".mgg1",
    ".mgg2",
    ".mgga",
    ".mggh",
    ".mggl",
    ".mggm",
    ".mmp4",
    ".mp3",
    ".ncm",
    ".ogg",
    ".qmc0",
    ".qmc2",
    ".qmc3",
    ".qmc4",
    ".qmc6",
    ".qmc8",
    ".qmcflac",
    ".qmcogg",
    ".tkm",
    ".tm0",
    ".tm2",
    ".tm3",
    ".tm6",
    ".vpr",
    ".vpr.flac",
    ".wav",
    ".wma",
    ".x2m",
    ".x3m",
    ".xm",
}


def is_supported_file(path) -> bool:
    lower = str(path).lower()
    return any(lower.endswith(suffix) for suffix in SUPPORTED_SUFFIXES)


# 明文音频后缀（非加密，无需解密）
PLAIN_AUDIO_SUFFIXES = {
    ".aac", ".flac", ".m4a", ".mp3", ".ogg", ".wav", ".wma",
}

# 加密格式后缀 = 受支持 - 明文（保留 .kgm.flac / .vpr.flac 等复合后缀）
ENCRYPTED_SUFFIXES = SUPPORTED_SUFFIXES - PLAIN_AUDIO_SUFFIXES


def is_encrypted_file(path) -> bool:
    """是否为加密音乐文件（需要解密）；明文音频与非支持文件均返回 False。"""
    lower = str(path).lower()
    return any(lower.endswith(suffix) for suffix in ENCRYPTED_SUFFIXES)


# 常见音乐文件后缀（解密结果的输出格式，用于「已解密」页扫描显示）
MUSIC_SUFFIXES = {
    ".mp3", ".flac", ".m4a", ".ogg", ".wav", ".wma", ".aac",
    ".opus", ".ape", ".aiff", ".aif", ".wv", ".m4b",
}


def is_music_file(path) -> bool:
    """是否为常见音乐文件（解密输出的展示范围）。"""
    lower = str(path).lower()
    return any(lower.endswith(suffix) for suffix in MUSIC_SUFFIXES)


def target_basename(file_name: str) -> str:
    """去后缀得到目标基名：优先剥掉最长的匹配加密后缀（含 .kgm.flac 复合后缀），
    否则剥掉最后一个扩展名。用于输入/输出目录按文件名比对。"""
    lower = file_name.lower()
    best = ""
    for suffix in ENCRYPTED_SUFFIXES:
        if lower.endswith(suffix) and len(suffix) > len(best):
            best = suffix
    if best:
        return file_name[: len(file_name) - len(best)]
    return Path(file_name).stem


def format_size(size: float) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024:
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} TB"


def decode_process_output(raw: bytes) -> str:
    """以多种编码尝试解码外部进程输出字节。"""
    for encoding in ("utf-8", "gb18030", "cp936"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="ignore")


_ANSI_COLOR_RE = re.compile(r"\x1b\[[0-9;]*m")


def clean_log_text(message) -> str:
    """去除 ANSI 颜色码与空白行。"""
    text = _ANSI_COLOR_RE.sub("", str(message or ""))
    lines = [line.strip() for line in text.replace("\r", "\n").splitlines()]
    return "\n".join(line for line in lines if line)


def simplify_process_line(line: str):
    """把 um 进程单行输出归类为 (展示文本, 级别)，可返回 (None, None)。"""
    text = clean_log_text(line)
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
        return f"解密成功: {source} -> {destination}", "success"

    if "conversion failed" in lower_text:
        source = Path(payload.get("source", "")).name or "未知文件"
        reason = payload.get("error", "未知错误")
        return f"解密失败: {source} ({reason})", "error"

    if "run app failed" in lower_text:
        reason = payload.get("error", text)
        return f"任务执行失败: {reason}", "error"

    if "warn" in lower_text:
        return text, "warning"
    if "error" in lower_text or "fatal" in lower_text:
        return text, "error"
    return text, "info"


def _select_in_explorer(path: str) -> bool:
    """Shell API 定位：打开目录窗口并选中指定文件，成功返回 True。

    64 位 Python 下必须声明 argtypes/restype——否则 PIDL 指针被默认
    截断成 32 位 int，``SHOpenFolderAndSelectItems`` 会访问违例。
    本线程未初始化 COM 时补 ``CoInitialize``（已初始化返回 S_FALSE，无害）。
    """
    from ctypes import wintypes

    try:
        ctypes.oledll.ole32.CoInitialize(None)
        shell32 = ctypes.windll.shell32
        shell32.ILCreateFromPathW.argtypes = [wintypes.LPCWSTR]
        shell32.ILCreateFromPathW.restype = ctypes.c_void_p
        shell32.SHOpenFolderAndSelectItems.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint,
            ctypes.c_void_p,
            ctypes.c_uint,
        ]
        shell32.SHOpenFolderAndSelectItems.restype = ctypes.HRESULT
        shell32.ILFree.argtypes = [ctypes.c_void_p]
    except Exception as exc:  # noqa: BLE001 原型声明失败（非 Windows 等）
        logger.warning(f"Shell API 原型声明失败，回退 explorer /select: {exc}")
        return False

    pidl = shell32.ILCreateFromPathW(path)
    if not pidl:
        return False
    try:
        return shell32.SHOpenFolderAndSelectItems(pidl, 0, None, 0) == 0
    except Exception as exc:  # noqa: BLE001 API 不可用时回退 explorer
        logger.warning(f"SHOpenFolderAndSelectItems 失败，回退 explorer /select: {exc}")
        return False
    finally:
        shell32.ILFree(pidl)


def open_file_location(path: str) -> bool:
    """在文件管理器中打开文件所在目录并选中该文件（跨平台）。

    Windows 优先走 Shell API ``SHOpenFolderAndSelectItems``：打开目标目录并
    **真正高亮该文件**。``Popen(["explorer", "/select,…"])`` 列表形式在路径含
    空格时会被 subprocess 整体加引号，explorer 解析失败退化成只开「文档」，
    故 explorer 仅作 API 失败兜底（字符串形式，路径独立加引号）。
    macOS：``open -R``；Linux 退化为打开所在目录（``xdg-open``）。
    路径不存在时返回 False，调用方据此给出提示。仅使用标准库，不依赖 UI 层。
    """
    if not path or not os.path.exists(path):
        return False
    full = os.path.normpath(os.path.abspath(path))
    folder = os.path.dirname(full)
    try:
        if sys.platform.startswith("win"):
            if _select_in_explorer(full):
                return True
            # 兜底：字符串形式不经 Popen 重新加引号，路径部分自带引号
            subprocess.Popen(f'explorer /select,"{full}"')
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", path])
        else:
            subprocess.Popen(["xdg-open", folder])
        return True
    except OSError:
        return False
