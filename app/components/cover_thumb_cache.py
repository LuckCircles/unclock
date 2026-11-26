# coding: utf-8
"""已显示封面的 44×44 圆角缩略图 LRU 缓存（components 层，主线程专用）。

``common/cover_loader.CoverCache`` 缓存的是标签直读 / ffmpeg 输出的**原始封面字节**
（JPEG 或 PNG，实测真实专辑图约 1MB / 800×800）。仅缓存字节时，卡片每次重新进入视口
都要重跑 ``QImage.fromData`` → 缩放 → 圆角裁剪，实测 16.3ms/张，40 张可见
卡片约 651ms——滚动、全屏重排、切页时就是肉眼可见的卡顿。

本缓存直接保存**已经裁剪完的 QPixmap**：命中即 ``QLabel.setPixmap``，
实测 40 张仅 0.17ms，视觉上「秒加载」。缓存键与字节缓存同为
``(path, mtime)``，文件被覆盖后自动失效。``None`` 是有效值，表示该文件
确认无封面，避免反复画占位图 / 反复起 ffmpeg。

注意：QPixmap 是 GUI 资源，只能在主线程创建与使用；本类的所有调用都发生
在 ``DecryptedInterface`` 的主线程回填 / 物化路径，后台线程只回传字节。
"""

from collections import OrderedDict
import threading

from PySide6.QtGui import QPixmap

# 缓存未命中哨兵（区分「未缓存」与「已缓存且确认无封面」的 None）
CACHE_MISS = object()

# 44×44 ARGB32 单张约 7.7KB，2048 条约 16MB，足以覆盖千级音乐库的全部封面；
# 远大于 CoverCache 的 512 字节缓存，让「显示过一次」的缩略图不会被挤掉。
_DEFAULT_MAXSIZE = 2048


class CoverThumbCache:
    """(路径, mtime) → 44×44 圆角 QPixmap | None 的线程安全 LRU。"""

    MISS = CACHE_MISS

    def __init__(self, maxsize: int = _DEFAULT_MAXSIZE):
        self._maxsize = maxsize
        self._data: "OrderedDict[tuple, QPixmap | None]" = OrderedDict()
        self._lock = threading.Lock()

    def get(self, path: str, mtime: float):
        """命中返回 QPixmap 或 None（确认无封面）；未命中返回 ``MISS``。"""
        key = (path, mtime)
        with self._lock:
            if key not in self._data:
                return CACHE_MISS
            self._data.move_to_end(key)
            return self._data[key]

    def put(self, path: str, mtime: float, pixmap: QPixmap | None):
        key = (path, mtime)
        with self._lock:
            self._data[key] = pixmap
            self._data.move_to_end(key)
            while len(self._data) > self._maxsize:
                self._data.popitem(last=False)

    def clear(self):
        with self._lock:
            self._data.clear()

    def __len__(self):
        with self._lock:
            return len(self._data)
