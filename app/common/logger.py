# coding: utf-8
"""loguru 日志配置 —— 写入项目根 app.log（已 gitignore）。"""

from loguru import logger

from .config import PROJECT_ROOT

logger.remove()
logger.add(
    str(PROJECT_ROOT / "app.log"),
    rotation="5 MB",
    encoding="utf-8",
    level="DEBUG",
    format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <7} | {name}:{function}:{line} | {message}",
)

__all__ = ["logger"]
