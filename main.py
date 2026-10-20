import contextlib
import io
import sys

# 屏蔽 QFluentWidgets 推广输出（必须位于首次导入 qfluentwidgets 之前）
with contextlib.redirect_stdout(io.StringIO()):
    import qfluentwidgets.common.config  # noqa: F401

from PySide6.QtWidgets import QApplication

from src.um import UnlockMusicGUI


def main():
    app = QApplication(sys.argv)
    window = UnlockMusicGUI()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
