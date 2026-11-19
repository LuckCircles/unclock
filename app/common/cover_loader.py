# coding: utf-8
"""内嵌专辑封面提取与缓存（纯逻辑层，不依赖任何 UI）。

从音频文件提取内嵌封面图，统一输出 PNG 字节：调用内置 ffmpeg 把首张
内嵌图片（attached picture）以 image2pipe 输出到内存，不经磁盘。无封面 /
损坏 / ffmpeg 缺失 / 超时全部静默返回 None，绝不抛异常打断调用方。

缓存以 ``(路径, mtime)`` 为键，mtime 变化即失效（刷新后文件被覆盖也能
拿到新封面）；``None`` 也是有效缓存值（表示该文件确认无封面），避免
对无封面文件反复起 ffmpeg 进程。使用 OrderedDict 做 LRU 上限，防止
千级文件的缓存无限增长。
"""

import os
import subprocess
import threading
from collections import OrderedDict

# 缓存未命中哨兵（区分「未缓存」与「已缓存且确认无封面」的 None）
CACHE_MISS = object()

# 默认缓存容量：缩略图 PNG 通常几十 KB，512 条约几十 MB 上限，覆盖大列表可见范围
_DEFAULT_MAXSIZE = 512
# 单文件提取超时（秒）：本地进程通常几十毫秒，超时多为损坏文件，不宜久等
_EXTRACT_TIMEOUT = 3.0


def extract_cover_bytes(ffmpeg_path: str, audio_path: str) -> bytes | None:
    """提取单个音频文件的内嵌封面，返回 PNG 字节；无封面或任何失败返回 None。

    ``-map 0:v:0?`` 的 ``?`` 表示无视频流时不报错（但 ffmpeg 仍可能以非 0
    退出且输出为空），因此以 ``returncode==0 且 stdout 非空且带 PNG 签名``
    作为成功判据。stderr 丢弃，避免无封面文件的报错日志刷屏。
    """
    if not ffmpeg_path or not os.path.isfile(ffmpeg_path):
        return None
    if not audio_path or not os.path.isfile(audio_path):
        return None
    cmd = [
        ffmpeg_path, "-hide_banner", "-loglevel", "error",
        "-i", audio_path,
        "-map", "0:v:0?",          # 首张内嵌图；? = 无则可选
        "-frames:v", "1",
        "-f", "image2pipe", "-vcodec", "png", "pipe:1",
    ]
    kwargs = {
        "stdout": subprocess.PIPE,
        "stderr": subprocess.DEVNULL,
        "timeout": _EXTRACT_TIMEOUT,
    }
    # Windows 下抑制 ffmpeg 子进程控制台黑框闪现（GUI 程序无控制台时尤其重要）
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        result = subprocess.run(cmd, **kwargs)
    except (OSError, subprocess.SubprocessError):
        return None
    data = result.stdout or b""
    if result.returncode != 0 or not data:
        return None
    # PNG 签名校验：防止异常输出被当作封面喂给 QImage
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        return None
    return data


class CoverCache:
    """线程安全的封面字节 LRU 缓存（键 = (路径, mtime)）。"""

    # 未命中哨兵的类级别名（与模块级 CACHE_MISS 同一对象），供调用方引用
    MISS = CACHE_MISS

    def __init__(self, maxsize: int = _DEFAULT_MAXSIZE):
        self._maxsize = maxsize
        self._data: "OrderedDict[tuple, bytes | None]" = OrderedDict()
        self._lock = threading.Lock()

    def get(self, path: str, mtime: float):
        """命中返回字节或 None（确认无封面）；未命中返回 ``CACHE_MISS``。"""
        key = (path, mtime)
        with self._lock:
            if key not in self._data:
                return CACHE_MISS
            self._data.move_to_end(key)
            return self._data[key]

    def put(self, path: str, mtime: float, data: bytes | None):
        key = (path, mtime)
        with self._lock:
            self._data[key] = data
            self._data.move_to_end(key)
            while len(self._data) > self._maxsize:
                self._data.popitem(last=False)

    def clear(self):
        with self._lock:
            self._data.clear()
