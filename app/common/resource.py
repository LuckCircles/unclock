# coding: utf-8
"""资源路径常量。

图片资源（含应用图标）经 ``app/resource/resource.qrc`` 编译为
``app/resource/resource_rc.py``
后，以 Qt 资源路径 ``:/img/<name>`` 访问（不依赖文件系统）。
外部可执行文件位于项目根目录 ``tools/``。
"""


def image(name: str) -> str:
    """返回 qrc 注册的图片资源路径 ``:/img/<name>``。"""
    return f":/img/{name}"
