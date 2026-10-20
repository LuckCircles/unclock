# coding: utf-8
"""资源路径常量。"""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

IMG_DIR = PROJECT_ROOT / "img"
UM_DIR = PROJECT_ROOT / "um"


def image(name: str) -> str:
    """返回 img/ 目录下指定资源的绝对路径字符串。"""
    return str(IMG_DIR / name)


def tool(name: str) -> str:
    """返回 um/ 目录下指定可执行文件的绝对路径字符串。"""
    return str(UM_DIR / name)
