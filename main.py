import sys
from PySide6.QtWidgets import QApplication
from src.um import UnlockMusicGUI


def main():
    app = QApplication(sys.argv)
    window = UnlockMusicGUI()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
