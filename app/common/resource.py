# coding: utf-8
"""资源路径常量。

图片资源经 ``app/resource.qrc`` 编译为 ``app/resource_rc.py`` 后，
以 Qt 资源路径 ``:/img/<name>`` 访问（不依赖文件系统）。
可执行文件仍走文件系统 ``app/resources/``。
"""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

RESOURCES_DIR = PROJECT_ROOT / "app" / "resources"


def image(name: str) -> str:
    """返回 qrc 注册的图片资源路径 ``:/img/<name>``。"""
    return f":/img/{name}"


def binary(name: str) -> str:
    """返回 app/resources/ 目录下指定可执行文件的绝对路径字符串。"""
    return str(RESOURCES_DIR / name)

