import os
import time

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHeaderView,
    QHBoxLayout,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    CaptionLabel,
    CardWidget,
    CheckBox,
    FluentIcon,
    ScrollArea,
    TableWidget,
    TransparentPushButton,
)


SUPPORTED_SUFFIXES = {
    ".666c6163",
    ".6d3461",
    ".6d7033",
    ".6f6767",
    ".776176",
    ".aac",
    ".bkcape",
    ".bkcflac",
    ".bkcm4a",
    ".bkcmp3",
    ".bkcogg",
    ".bkcwav",
    ".bkcwma",
    ".flac",
    ".kgg",
    ".kgm",
    ".kgm.flac",
    ".kgma",
    ".kwm",
    ".m4a",
    ".mflac",
    ".mflac0",
    ".mflac1",
    ".mflaca",
    ".mflach",
    ".mflacl",
    ".mflacm",
    ".mgg",
    ".mgg0",
    ".mgg1",
    ".mgga",
    ".mggh",
    ".mggl",
    ".mggm",
    ".mmp4",
    ".mp3",
    ".ncm",
    ".ogg",
    ".qmc0",
    ".qmc2",
    ".qmc3",
    ".qmc4",
    ".qmc6",
    ".qmc8",
    ".qmcflac",
    ".qmcogg",
    ".tkm",
    ".tm0",
    ".tm2",
    ".tm3",
    ".tm6",
    ".vpr",
    ".vpr.flac",
    ".wav",
    ".wma",
    ".x2m",
    ".x3m",
    ".xm",
}


class FileInterface(ScrollArea):
    """待处理文件管理页面"""

    files_changed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.supported_exts = set(SUPPORTED_SUFFIXES)
        self._batch_updating = False

        self.view = QWidget(self)
        self.vLayout = QVBoxLayout(self.view)
        self.vLayout.setContentsMargins(30, 30, 30, 30)
        self.vLayout.setSpacing(20)

        self.setWidget(self.view)
        self.setWidgetResizable(True)
        self.setObjectName("FileInterface")

        self.listCard = CardWidget(self)
        self.cardLayout = QVBoxLayout(self.listCard)
        self.cardLayout.setContentsMargins(15, 15, 15, 15)
        self.cardLayout.setSpacing(10)

        self.headerLayout = QHBoxLayout()
        self.allCheckBox = CheckBox("全选", self)
        self.allCheckBox.stateChanged.connect(self._on_all_checked_changed)
        self.headerLayout.addWidget(self.allCheckBox)

        self.countLabel = CaptionLabel("0 个文件")
        self.headerLayout.addWidget(self.countLabel)
        self.headerLayout.addStretch(1)

        self.btnAdd = TransparentPushButton(FluentIcon.ADD, "添加文件", self)
        self.btnRefresh = TransparentPushButton(FluentIcon.SYNC, "刷新列表", self)
        self.btnDelete = TransparentPushButton(FluentIcon.DELETE, "移除勾选", self)
        self.btnClear = TransparentPushButton(FluentIcon.CLOSE, "清空列表", self)

        self.headerLayout.addWidget(self.btnAdd)
        self.headerLayout.addWidget(self.btnRefresh)
        self.headerLayout.addWidget(self.btnDelete)
        self.headerLayout.addWidget(self.btnClear)
        self.cardLayout.addLayout(self.headerLayout)

        self.tableWidget = TableWidget(self)
        self.tableWidget.setColumnCount(4)
        self.tableWidget.setHorizontalHeaderLabels(["", "文件名", "修改时间", "大小"])
        self.tableWidget.verticalHeader().hide()
        self.tableWidget.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.tableWidget.setColumnWidth(0, 44)
        self.tableWidget.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.tableWidget.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeToContents
        )
        self.tableWidget.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeToContents
        )
        self.tableWidget.setEditTriggers(TableWidget.NoEditTriggers)
        self.tableWidget.setSelectionBehavior(TableWidget.SelectRows)
        self.tableWidget.setSelectionMode(TableWidget.NoSelection)
        self.tableWidget.setWordWrap(False)

        self.cardLayout.addWidget(self.tableWidget, 1)
        self.vLayout.addWidget(self.listCard, 1)

        self.btnAdd.clicked.connect(self._add_files)
        self.btnRefresh.clicked.connect(self.refresh_from_config)
        self.btnDelete.clicked.connect(self._remove_checked)
        self.btnClear.clicked.connect(self.clear_files)
        self.tableWidget.cellClicked.connect(self._on_cell_clicked)
        self.tableWidget.itemChanged.connect(self._on_item_changed)

    def is_supported_file(self, path):
        lower_path = str(path).lower()
        return any(lower_path.endswith(suffix) for suffix in self.supported_exts)

    def _on_cell_clicked(self, row, column):
        if self._batch_updating or column == 0:
            return
        check_item = self.tableWidget.item(row, 0)
        if not check_item:
            return
        self._batch_updating = True
        check_item.setCheckState(
            Qt.Unchecked if check_item.checkState() == Qt.Checked else Qt.Checked
        )
        self._batch_updating = False
        self._sync_header_checkbox()

    def _on_item_changed(self, item):
        if self._batch_updating or item.column() != 0:
            return
        self._sync_header_checkbox()

    def _on_all_checked_changed(self, state):
        if self._batch_updating:
            return
        check_state = Qt.Checked if state == Qt.Checked or state == 2 else Qt.Unchecked
        self._batch_updating = True
        self.tableWidget.setUpdatesEnabled(False)
        for row in range(self.tableWidget.rowCount()):
            item = self.tableWidget.item(row, 0)
            if item:
                item.setCheckState(check_state)
        self.tableWidget.setUpdatesEnabled(True)
        self._batch_updating = False

    def _sync_header_checkbox(self):
        total = self.tableWidget.rowCount()
        if total == 0:
            self.allCheckBox.blockSignals(True)
            self.allCheckBox.setChecked(False)
            self.allCheckBox.blockSignals(False)
            return

        checked = 0
        for row in range(total):
            item = self.tableWidget.item(row, 0)
            if item and item.checkState() == Qt.Checked:
                checked += 1

        self.allCheckBox.blockSignals(True)
        self.allCheckBox.setChecked(checked == total)
        self.allCheckBox.blockSignals(False)

    def _format_size(self, size):
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return f"{size:.2f} {unit}"
            size /= 1024
        return f"{size:.2f} TB"

    def _collect_table_paths(self):
        paths = set()
        for row in range(self.tableWidget.rowCount()):
            item = self.tableWidget.item(row, 1)
            if item:
                full_path = item.data(Qt.UserRole)
                if full_path:
                    paths.add(full_path)
        return paths

    def _create_row_items(self, full_path):
        check_item = QTableWidgetItem()
        check_item.setFlags(
            Qt.ItemIsEnabled | Qt.ItemIsUserCheckable | Qt.ItemIsSelectable
        )
        check_item.setCheckState(Qt.Unchecked)

        name_item = QTableWidgetItem(os.path.basename(full_path))
        name_item.setData(Qt.UserRole, full_path)

        try:
            stats = os.stat(full_path)
            mod_time = time.strftime("%Y-%m-%d %H:%M", time.localtime(stats.st_mtime))
            date_item = QTableWidgetItem(mod_time)
            date_item.setTextAlignment(Qt.AlignCenter)
            size_item = QTableWidgetItem(self._format_size(stats.st_size))
            size_item.setTextAlignment(Qt.AlignCenter)
        except OSError:
            date_item = QTableWidgetItem("未知")
            date_item.setTextAlignment(Qt.AlignCenter)
            size_item = QTableWidgetItem("未知")
            size_item.setTextAlignment(Qt.AlignCenter)

        return check_item, name_item, date_item, size_item

    def _append_paths(self, paths, reset=False):
        unique_paths = []
        seen = set() if reset else self._collect_table_paths()

        for path in paths:
            if not self.is_supported_file(path):
                continue
            if path in seen:
                continue
            seen.add(path)
            unique_paths.append(path)

        if reset:
            self.tableWidget.setRowCount(0)
            self.allCheckBox.blockSignals(True)
            self.allCheckBox.setChecked(False)
            self.allCheckBox.blockSignals(False)

        if not unique_paths:
            self._update_count()
            return

        start_row = self.tableWidget.rowCount()
        self._batch_updating = True
        self.tableWidget.setUpdatesEnabled(False)
        self.tableWidget.setRowCount(start_row + len(unique_paths))

        for offset, full_path in enumerate(unique_paths):
            row = start_row + offset
            check_item, name_item, date_item, size_item = self._create_row_items(
                full_path
            )
            self.tableWidget.setItem(row, 0, check_item)
            self.tableWidget.setItem(row, 1, name_item)
            self.tableWidget.setItem(row, 2, date_item)
            self.tableWidget.setItem(row, 3, size_item)

        self.tableWidget.setUpdatesEnabled(True)
        self._batch_updating = False
        self._update_count()
        self._sync_header_checkbox()

    def refresh_from_config(self):
        from .um import cfg

        input_dir = cfg.input_dir.value
        if input_dir and os.path.exists(input_dir):
            self.scan_directory(input_dir)

    def scan_directory(self, path):
        if not path or not os.path.exists(path):
            return

        matched_paths = []
        try:
            for file_name in os.listdir(path):
                full_path = os.path.join(path, file_name)
                if os.path.isfile(full_path) and self.is_supported_file(full_path):
                    matched_paths.append(full_path)
        except OSError:
            return

        self._append_paths(matched_paths, reset=True)

    def _add_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择待转换文件", "", "All Files (*)"
        )
        if files:
            self._append_paths(files, reset=False)

    def _remove_checked(self):
        to_remove = []
        for row in range(self.tableWidget.rowCount()):
            item = self.tableWidget.item(row, 0)
            if item and item.checkState() == Qt.Checked:
                to_remove.append(row)
        if not to_remove:
            return

        self._batch_updating = True
        self.tableWidget.setUpdatesEnabled(False)
        for row in reversed(to_remove):
            self.tableWidget.removeRow(row)
        self.tableWidget.setUpdatesEnabled(True)
        self._batch_updating = False
        self._update_count()
        self._sync_header_checkbox()

    def clear_files(self):
        self._batch_updating = True
        self.tableWidget.setRowCount(0)
        self._batch_updating = False
        self._update_count()
        self._sync_header_checkbox()

    def _update_count(self):
        count = self.tableWidget.rowCount()
        self.countLabel.setText(f"{count} 个文件")
        self.files_changed.emit(count)

    def get_file_paths(self):
        checked_paths = []
        all_paths = []
        for row in range(self.tableWidget.rowCount()):
            path_item = self.tableWidget.item(row, 1)
            if not path_item:
                continue
            path = path_item.data(Qt.UserRole)
            if not path:
                continue
            all_paths.append(path)
            check_item = self.tableWidget.item(row, 0)
            if check_item and check_item.checkState() == Qt.Checked:
                checked_paths.append(path)
        return checked_paths if checked_paths else all_paths
