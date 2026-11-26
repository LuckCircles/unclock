# coding: utf-8
"""Windows 文件属性版本读取 —— 仅用标准库，供工具检测优先取版本号。

资源管理器「属性 → 详细信息 → 文件版本 / 产品版本」对应 PE 的 VS_VERSIONINFO
字符串资源；Go 编译的 exe 通常没有该资源，此时返回 ``None``，由调用方回退到
命令行版本参数。非 Windows 平台同样返回 ``None``。
"""

import ctypes
import struct
import sys
from pathlib import Path


def read_file_version(path) -> str | None:
    """从 exe 文件属性读取版本号，无法提取时返回 ``None``。

    优先级：FileVersion → ProductVersion → VS_FIXEDFILEINFO 数字版本。
    """
    if sys.platform != "win32":
        return None

    file_path = str(path or "")
    if not file_path or not Path(file_path).is_file():
        return None

    try:
        from ctypes import wintypes

        version_dll = ctypes.WinDLL("version", use_last_error=True)

        get_size = version_dll.GetFileVersionInfoSizeW
        get_size.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(wintypes.DWORD)]
        get_size.restype = wintypes.DWORD
        size = get_size(file_path, None)
        if not size:
            return None

        get_info = version_dll.GetFileVersionInfoW
        get_info.argtypes = [
            wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p
        ]
        get_info.restype = wintypes.BOOL
        buffer = ctypes.create_string_buffer(size)
        if not get_info(file_path, 0, size, buffer):
            return None

        query = version_dll.VerQueryValueW
        query.argtypes = [
            ctypes.c_void_p,
            wintypes.LPCWSTR,
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(wintypes.UINT),
        ]
        query.restype = wintypes.BOOL

        def _read_block(sub_block: str, as_text: bool = True):
            ptr = ctypes.c_void_p()
            length = wintypes.UINT()
            if not query(buffer, sub_block, ctypes.byref(ptr), ctypes.byref(length)):
                return None
            if not ptr.value or not length.value:
                return None
            if as_text:
                # 字符串以 WCHAR'\0' 结尾，按 wstring_at 读到结尾即可
                return ctypes.wstring_at(ptr.value).strip() or None
            return ctypes.string_at(ptr.value, length.value)

        # StringFileInfo 需先经 Translation 块拿到语言/代码页组合
        translations = _read_block("\\VarFileInfo\\Translation", as_text=False)
        if translations:
            for offset in range(0, len(translations) - 3, 4):
                lang, codepage = struct.unpack_from("<HH", translations, offset)
                key = f"{lang:04x}{codepage:04x}"
                for field in ("FileVersion", "ProductVersion"):
                    value = _read_block(f"\\StringFileInfo\\{key}\\{field}")
                    if value:
                        return value

        # 字符串资源缺失时退到 VS_FIXEDFILEINFO 的四段数字版本
        fixed = _read_block("\\", as_text=False)
        if fixed and len(fixed) >= 16:
            _, _, ms, ls = struct.unpack_from("<IIII", fixed, 0)
            parts = [str(ms >> 16), str(ms & 0xFFFF), str(ls >> 16), str(ls & 0xFFFF)]
            while len(parts) > 2 and parts[-1] == "0":
                parts.pop()
            return ".".join(parts)
        return None
    except (OSError, ValueError, struct.error, ctypes.ArgumentError):
        # 无版本资源 / 版本 DLL 不可用 / 字段异常：视为无法从文件属性提取
        return None
