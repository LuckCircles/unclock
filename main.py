# coding: utf-8
"""应用入口 —— 屏蔽 QFluentWidgets 推广输出后启动 GUI。"""

import contextlib
import io
import sys

# 屏蔽 QFluentWidgets Pro 推广输出（必须位于首次导入 qfluentwidgets 之前）
with contextlib.redirect_stdout(io.StringIO()):
    import qfluentwidgets.common.config  # noqa: F401

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QWidget
from qfluentwidgets import MessageBox

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
    # 单实例：已有实例在运行则提示并退出（不重复启动）
    if app.already_running:
        logger.warning("检测到已有实例在运行，退出本次启动")
        # Fluent MessageBox 依赖父窗口尺寸铺满遮罩，此时主窗口尚未创建：
        # 用与主屏可用区域等大的透明无边框宿主充当父对象，点击确定后随进程退出
        host = QWidget()
        host.setWindowTitle("音乐解锁工具")
        host.setWindowFlag(Qt.FramelessWindowHint)
        host.setAttribute(Qt.WA_TranslucentBackground)
        host.setGeometry(QApplication.primaryScreen().availableGeometry())
        host.show()
        box = MessageBox("音乐解锁工具", "程序已经在运行中。", host)
        box.yesButton.setText("确定")
        box.cancelButton.hide()
        box.exec()
        host.close()
        return
    window = MainWindow()
    window.show()
    app.aboutToQuit.connect(window.on_exit)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
