# coding: utf-8
"""内嵌专辑封面提取与缓存（纯逻辑层，不依赖 app 的 UI 层）。

FLAC 的 PICTURE 块与 MP3 的 ID3v2 APIC 帧直接读标签块取图（纯 Python、
毫秒级，无需启动 ffmpeg），返回**容器内原始图片字节**（PNG 或 JPEG）。
QImage 可同时解码两种格式，因此列表/详情展示零转码；只有「保存封面」把
原始图转成 PNG 写到固定的 ``<歌名>.png``（`cover_bytes_to_png`）。无法识别
的容器或标签损坏才回退 ffmpeg（其输出为 PNG）。无封面 / 损坏 / 超时全部
静默返回 ``None``，绝不抛异常打断调用方。

缓存以 ``(路径, mtime)`` 为键，mtime 变化即失效（刷新后文件被覆盖也能
拿到新封面）；``None`` 也是有效缓存值（表示该文件确认无封面），避免对
无封面文件反复探测。使用 OrderedDict 做 LRU 上限，防止千级文件缓存无限增长。
"""

import os
import subprocess
import threading
from collections import OrderedDict

from PySide6.QtCore import QByteArray, QBuffer, QIODevice
from PySide6.QtGui import QImage

# 缓存未命中哨兵（区分「未缓存」与「已缓存且确认无封面」的 None）
CACHE_MISS = object()

# 默认缓存容量：缩略图 PNG 通常几十 KB，512 条约几十 MB 上限，覆盖大列表可见范围
_DEFAULT_MAXSIZE = 512
# ffmpeg 兜底超时（秒）：本地进程通常几十毫秒，超时多为损坏文件，不宜久等
_EXTRACT_TIMEOUT = 3.0
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
# 标签字段长度上限：超过即视为损坏，交给 ffmpeg 兜底，避免异常文件触发大块读取
_MAX_FIELD = 64 * 1024 * 1024


def _u32(data: bytes) -> int:
    return int.from_bytes(data, "big")


def _syncsafe(data: bytes) -> int:
    return (data[0] << 21) | (data[1] << 14) | (data[2] << 7) | data[3]


def _read_flac_picture(path: str) -> "tuple[bytes | None, bool]":
    """读 FLAC PICTURE 块，返回 ``(原始图片字节, 是否识别容器)``。

    识别但无 PICTURE 块时返回 ``(None, True)``，调用方据此**不启动 ffmpeg**。
    """
    try:
        with open(path, "rb") as f:
            if f.read(4) != b"fLaC":
                return None, False
            while True:
                head = f.read(4)
                if len(head) < 4:
                    return None, True
                last = bool(head[0] & 0x80)
                block_type = head[0] & 0x7F
                size = _u32(head[1:4])
                block_start = f.tell()
                if block_type == 6:  # PICTURE
                    f.read(4)  # picture type
                    mime_len = _u32(f.read(4))
                    if mime_len > 4096:
                        return None, False
                    mime = f.read(mime_len)
                    desc_len = _u32(f.read(4))  # 位于 MIME 之后
                    if desc_len > 65536:
                        return None, False
                    if not mime.lower().startswith(b"image/"):
                        f.seek(block_start + size)
                    else:
                        f.seek(desc_len, 1)
                        f.read(16)  # width / height / depth / colors
                        data_len = _u32(f.read(4))
                        if data_len > _MAX_FIELD:
                            return None, False
                        return (f.read(data_len) or None), True
                else:
                    f.seek(block_start + size)
                if last:
                    return None, True
    except (OSError, ValueError, IndexError):
        return None, False


def _read_id3_picture(path: str) -> "tuple[bytes | None, bool]":
    """读 MP3 ID3v2 的 APIC（v2.2 为 PIC）帧，返回同上。"""
    try:
        with open(path, "rb") as f:
            if f.read(3) != b"ID3":
                return None, False
            version = f.read(2)[0]
            flags = f.read(1)[0]
            total = _syncsafe(f.read(4))
            pos = 0
            if flags & 0x40:  # extended header
                ext = _syncsafe(f.read(4)) if version >= 4 else _u32(f.read(4))
                f.seek(ext, 1)
                pos += 4 + ext
            while pos + 10 <= total:
                head = f.read(10)
                if len(head) < 10:
                    break
                frame_id = head[:4]
                if not any(frame_id):
                    break
                frame_size = _syncsafe(head[4:8]) if version >= 4 else _u32(head[4:8])
                if frame_size <= 0 or frame_size > _MAX_FIELD:
                    return None, False
                body = f.read(frame_size)
                pos += 10 + frame_size
                if frame_id not in (b"APIC", b"PIC"):
                    continue
                encoding = body[0]
                if frame_id == b"PIC":  # ID3v2.2：3 字节图片格式 + 1 字节类型
                    fmt = body[1:4].upper()
                    mime = b"image/jpeg" if fmt == b"JPG" else b"image/" + fmt.lower()
                    offset = 5
                else:
                    end = body.find(b"\x00", 1)
                    if end < 0:
                        continue
                    mime = body[1:end]
                    offset = end + 2  # MIME 终止符 + picture type
                if not mime.lower().startswith(b"image/"):
                    continue
                terminator = b"\x00\x00" if encoding in (1, 2) else b"\x00"
                desc_end = body.find(terminator, offset)
                if desc_end < 0:
                    continue
                data = body[desc_end + len(terminator):]
                return (data or None), True
            return None, True
    except (OSError, ValueError, IndexError):
        return None, False


def read_embedded_cover(audio_path: str) -> "tuple[bytes | None, bool]":
    """从已知容器直接读内嵌图片，返回 ``(原始图片字节, 容器是否可识别)``。

    当前实现覆盖 FLAC 与 MP3（实测音乐库的全部格式）；其它后缀返回
    ``(None, False)``，由调用方回退 ffmpeg，保证格式兼容不回退。
    """
    if not audio_path or not os.path.isfile(audio_path):
        return None, False
    lower = audio_path.lower()
    if lower.endswith(".flac"):
        return _read_flac_picture(audio_path)
    if lower.endswith(".mp3"):
        return _read_id3_picture(audio_path)
    return None, False


def cover_bytes_to_png(data: bytes) -> bytes | None:
    """原始封面字节（JPEG/PNG）→ PNG 字节；本身是 PNG 则原样返回。

    只在用户点击「保存封面」时调用：800×800 JPEG 转 PNG 实测约 226ms，
    不能放到每张卡片的后台探测路径里。
    """
    if not data:
        return None
    if data.startswith(_PNG_SIGNATURE):
        return data
    img = QImage.fromData(QByteArray(data))
    if img.isNull():
        return None
    # QBuffer 不拷贝传入的 QByteArray：必须持有 byte_array 到写入结束，
    # 否则底层缓冲被回收会导致 save() 崩溃（实测段错误）
    byte_array = QByteArray()
    buffer = QBuffer(byte_array)
    buffer.open(QIODevice.WriteOnly)
    try:
        if not img.save(buffer, "PNG"):
            return None
        png = bytes(buffer.data())
    finally:
        buffer.close()
    return png if png.startswith(_PNG_SIGNATURE) else None


def _ffmpeg_cover_bytes(ffmpeg_path: str, audio_path: str) -> bytes | None:
    """原 ffmpeg 路径：把首张内嵌图编码为 PNG 输出，作为不可识别格式的兜底。"""
    if not ffmpeg_path or not os.path.isfile(ffmpeg_path):
        return None
    cmd = [
        ffmpeg_path, "-hide_banner", "-loglevel", "error",
        "-i", audio_path,
        "-map", "0:v:0?",
        "-frames:v", "1",
        "-f", "image2pipe", "-vcodec", "png", "pipe:1",
    ]
    kwargs = {
        "stdout": subprocess.PIPE,
        "stderr": subprocess.DEVNULL,
        "timeout": _EXTRACT_TIMEOUT,
    }
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        result = subprocess.run(cmd, **kwargs)
    except (OSError, subprocess.SubprocessError):
        return None
    data = result.stdout or b""
    if result.returncode != 0 or not data:
        return None
    return data if data.startswith(_PNG_SIGNATURE) else None


def extract_cover_bytes(ffmpeg_path: str, audio_path: str) -> bytes | None:
    """提取内嵌封面，返回**原始图片字节**（PNG 或 JPEG），失败返回 ``None``。

    签名与既有调用方保持一致。FLAC / MP3 走标签块直读（不启进程），其余
    格式或异常才回退 ffmpeg（输出为 PNG）。显示层用 QImage 直接解码，无需
    在批量探测路径上做昂贵的 JPEG→PNG 转码。
    """
    if not audio_path or not os.path.isfile(audio_path):
        return None
    raw, recognized = read_embedded_cover(audio_path)
    if raw is not None:
        return raw
    if recognized:
        # 容器可识别且确认无内嵌图：不启动任何进程
        return None
    return _ffmpeg_cover_bytes(ffmpeg_path, audio_path)


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
