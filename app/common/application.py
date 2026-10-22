# coding: utf-8
"""应用入口的 Application 包装（含 Windows 单实例锁）。"""

import ctypes
import sys
from ctypes import wintypes

from PySide6.QtWidgets import QApplication

# 单实例互斥体名（本会话命名空间，足够防止同一用户重复启动）
_MUTEX_NAME = "unclock_single_instance_mutex"
_ERROR_ALREADY_EXISTS = 183


class SingletonApplication(QApplication):
    """应用对象：带单实例锁——已有实例在运行时，再启动则提示并退出。

    非 Windows 平台不取锁（退回允许多开）；取锁失败也不致命。
    """

    def __init__(self, argv, name: str = "unclock"):
        super().__init__(argv)
        self.setApplicationName(name)
        self.setApplicationDisplayName("音乐解锁工具")
        self._mutex_handle = None
        self._already_running = False
        self._acquire_single_instance()

    def _acquire_single_instance(self):
        """创建命名互斥体；若已存在（GetLastError==ERROR_ALREADY_EXISTS）则已有实例。

        互斥体句柄须在进程生命周期内保持不关，故存为实例属性。
        """
        if sys.platform != "win32":
            return
        try:
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.CreateMutexW.restype = wintypes.HANDLE
            kernel32.CreateMutexW.argtypes = (
                wintypes.LPCVOID, wintypes.BOOL, wintypes.LPCWSTR,
            )
            self._mutex_handle = kernel32.CreateMutexW(None, False, _MUTEX_NAME)
            self._already_running = (
                ctypes.get_last_error() == _ERROR_ALREADY_EXISTS
            )
        except Exception as exc:  # noqa: BLE001
            # 取锁失败不致命：退回允许多开
            self._mutex_handle = None
            self._already_running = False
            print(f"[app] 单实例锁获取失败: {exc}")

    @property
    def already_running(self) -> bool:
        """是否已有另一个实例在运行。"""
        return self._already_running
