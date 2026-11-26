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
from app.common.i18n import apply_language
from app.common.logger import logger
from app.common.application import SingletonApplication
from app.view.main_window import MainWindow


def main():
    logger.info("=" * 60)
    logger.info("音乐解锁工具 启动")
    logger.info(f"Python {sys.version.split()[0]} | PySide6")
    logger.info(f"项目根目录: {PROJECT_ROOT}")
    app = SingletonApplication(sys.argv, "unclock")
    # 语言必须在任何控件创建前生效，之后新建的文案设置会自动走翻译过滤
    apply_language()
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
    # 构造参数形式传入的文案（分组标题等）绕过 setText 拦截，建窗后再统一重翻译
    apply_language()
    window.show()
    app.aboutToQuit.connect(window.on_exit)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
