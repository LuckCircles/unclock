# coding: utf-8
"""应用入口 —— 屏蔽 QFluentWidgets 推广输出后启动 GUI。"""

import contextlib
import io
import sys

# 屏蔽 QFluentWidgets Pro 推广输出（必须位于首次导入 qfluentwidgets 之前）
with contextlib.redirect_stdout(io.StringIO()):
    import qfluentwidgets.common.config  # noqa: F401

from app.common.config import PROJECT_ROOT
from app.common.logger import logger
from app.common.application import SingletonApplication
from app.view.main_window import MainWindow


def main():
    logger.info("=" * 60)
    logger.info("音乐解锁工具 启动")
    logger.info(f"Python {sys.version.split()[0]} | PySide6")
    logger.info(f"项目根目录: {PROJECT_ROOT}")
    app = SingletonApplication(sys.argv, "unclock")
    window = MainWindow()
    window.show()
    app.aboutToQuit.connect(window.on_exit)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
