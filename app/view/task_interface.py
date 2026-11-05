# coding: utf-8
"""任务管理页面 —— 卡片式待转换文件列表（固定工具栏 + 滚动网格）。

支持：添加文件 / 刷新列表 / 拖入文件（文件或目录，目录取顶层）/ 删除 / 清空；
只纳入加密音乐文件（明文音频等非加密文件跳过）。
"""

import os

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QFileDialog, QLabel
from qfluentwidgets import (
    Action,
    CaptionLabel,
    FluentIcon,
    MessageBox,
    RoundMenu,
    TransparentPushButton,
    qconfig,
)

from ..common.config import cfg
from ..common.decrypt_scanner import (
    build_decrypted_basenames,
    is_already_decrypted,
)
from ..common.logger import logger
from ..common.signal_bus import signalBus
from ..common.utils import is_encrypted_file
from ..components.grid_card_container import GridCardContainer
from ..components.task_card import TaskCard

# 卡片排序优先级（值越小越靠上）：待解密 → 解密中 → 失败/跳过 → 已解密
_STATUS_ORDER = {
    "pending": 0,
    "running": 1,
    "failed": 2,
    "skipped": 3,
    "success": 4,
}


class TaskInterface(GridCardContainer):
    """待转换文件管理页面（固定工具栏 + 滚动卡片网格）。"""

    def __init__(self, parent=None):
        super().__init__("TaskInterface", parent)

        # 支持拖入文件（文件/目录）——ScrollArea 子控件默认不接收拖拽，事件统一冒泡到本页
        self.setAcceptDrops(True)

        # 输出目录已解密基名集合（建卡时判定「已解密」状态）
        self._decrypted_names = set()
        # 首次扫描填充完成前抑制空提示（页面先出、卡片随后流式出现）
        self._filling = True

        # 工具栏：计数 + 按钮组（FluentIcon 走内置 SVG，无需系统字体，不会渲染成方块）
        self.countLabel = CaptionLabel("共 0 个文件", self)
        self.toolbarLayout.addWidget(self.countLabel)
        self.toolbarLayout.addStretch(1)
        self.btnAdd = TransparentPushButton(FluentIcon.ADD, "添加文件", self)
        self.btnRefresh = TransparentPushButton(FluentIcon.SYNC, "刷新列表", self)
        self.btnDelete = TransparentPushButton(FluentIcon.DELETE, "删除完成", self)
        self.btnClear = TransparentPushButton(FluentIcon.BROOM, "清空列表", self)
        for btn in (self.btnAdd, self.btnRefresh, self.btnDelete, self.btnClear):
            self.toolbarLayout.addWidget(btn)

        # 拖入提示浮层：拖文件经过时盖在滚动区上方（对鼠标透明，不拦正常操作）
        self.dropHint = QLabel("松开鼠标，添加至任务列表", self.scrollArea)
        self.dropHint.setAlignment(Qt.AlignCenter)
        self.dropHint.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.dropHint.hide()

        # 信号连接
        self.btnAdd.clicked.connect(self._add_files)
        self.btnRefresh.clicked.connect(self.refresh_from_config)
        self.btnDelete.clicked.connect(self._remove_completed)
        self.btnClear.clicked.connect(self.clear_files)
        signalBus.file_started.connect(self._on_file_started)
        signalBus.file_finished.connect(self._on_file_finished)
        signalBus.file_cancelled.connect(self._on_file_cancelled)
        signalBus.paths_changed.connect(self.refresh_from_config)

        # 启动不同步建卡：延后到事件循环首轮，并分批渐进填充——
        # 数百张卡的输入目录会把启动拖死数秒，现在窗口先出、卡片随后流式出现
        QTimer.singleShot(0, self._startup_scan)

    # ------------------------------------------------------------ 基类钩子
    def _make_card(self, path: str) -> TaskCard:
        card = TaskCard(path, self)
        # 加密文件按去后缀在输出目录命中 → 已解密
        if is_already_decrypted(path, self._decrypted_names):
            card.set_status("success")
        # 右键菜单：删除文件 / 移出列表
        card.setContextMenuPolicy(Qt.CustomContextMenu)
        card.customContextMenuRequested.connect(
            lambda pos, c=card: self._show_card_menu(c, pos)
        )
        return card

    def _sort_cards(self):
        # 待解密在上、已解密沉底，保持视觉稳定
        self._cards.sort(key=lambda c: _STATUS_ORDER.get(c.status, 9))

    def _on_card_removed(self, card):
        # 同步从转换服务待处理队列剔除该文件
        signalBus.queue_remove.emit(card.file_path)

    def _sync_overlay_geometry(self):
        super()._sync_overlay_geometry()
        # 拖入提示浮层跟随滚动区尺寸
        self.dropHint.setGeometry(self.scrollArea.rect())

    def _update_count(self):
        count = len(self._cards)
        # 输入/输出对比的状态分布：待解密 / 解密中 / 已解密 / 失败
        pending = running = success = failed = 0
        for c in self._cards:
            if c.status == "pending":
                pending += 1
            elif c.status == "running":
                running += 1
            elif c.status == "success":
                success += 1
            elif c.status == "failed":
                failed += 1
        parts = []
        if pending:
            parts.append(f"待解密 {pending}")
        if running:
            parts.append(f"解密中 {running}")
        if success:
            parts.append(f"已解密 {success}")
        if failed:
            parts.append(f"失败 {failed}")
        if parts:
            self.countLabel.setText(" · ".join(parts) + f" · 共 {count}")
        else:
            self.countLabel.setText(f"共 {count} 个文件")
        if count == 0:
            self.emptyHint.label.setText(
                "暂无文件，点击“添加文件”、刷新列表，或直接拖入文件"
            )
        self._set_empty_visible(count == 0)

    # ------------------------------------------------------------ 拖入文件
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            self._show_drop_hint(True)
        else:
            # 非文件拖入：收起提示（防御 leave 事件偶发不达导致高亮残留）
            self._show_drop_hint(False)
            e.ignore()

    def dragMoveEvent(self, e):
        # 拖动过程中持续确认（工具栏按钮/卡片均不接收拖拽，事件冒泡到本页）
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
        else:
            self._show_drop_hint(False)
            e.ignore()

    def dragLeaveEvent(self, e):
        self._show_drop_hint(False)
        e.accept()

    def dropEvent(self, e):
        self._show_drop_hint(False)
        paths = self._collect_drop_paths(e)
        if not paths:
            signalBus.toast_requested.emit("未识别到本地文件或目录。", "warning")
            e.acceptProposedAction()
            return
        r = self._append_files(paths)
        added, dup, invalid = r["added"], r["duplicate"], r["invalid"]
        if added:
            skipped = []
            if dup:
                skipped.append(f"重复 {dup} 个")
            if invalid:
                skipped.append(f"非加密 {invalid} 个")
            msg = f"已拖入添加 {added} 个文件"
            if skipped:
                msg += "（跳过 " + "、".join(skipped) + "）"
            signalBus.toast_requested.emit(msg, "success")
            signalBus.log_emitted.emit(
                f"拖入添加 {added} 个文件（重复 {dup}、非加密 {invalid}）", "success"
            )
        elif dup and not invalid:
            signalBus.toast_requested.emit("拖入的文件已在列表中。", "warning")
        elif invalid and not dup:
            signalBus.toast_requested.emit("未找到可解密的加密音乐文件。", "warning")
        else:
            signalBus.toast_requested.emit(
                "拖入的文件均不可解密或已在列表中。", "warning"
            )
        e.acceptProposedAction()

    def _collect_drop_paths(self, e) -> list[str]:
        """收集拖入的本地文件：文件直接纳入；目录取其顶层文件（与目录扫描一致，不递归）。

        路径统一 ``normpath`` 规范化：``QUrl.toLocalFile()`` 返回正斜杠路径，与
        文件对话框 / 目录扫描的反斜杠原生路径字符串不同，不去重会出现同一文件两张卡。
        """
        paths = []
        for url in e.mimeData().urls():
            if not url.isLocalFile():
                continue
            local = os.path.normpath(url.toLocalFile())
            if os.path.isdir(local):
                try:
                    for name in os.listdir(local):
                        full = os.path.join(local, name)
                        if os.path.isfile(full):
                            paths.append(full)
                except OSError:
                    continue
            elif os.path.isfile(local):
                paths.append(local)
        return paths

    def _show_drop_hint(self, show: bool):
        """拖入经过时在滚动区显示提示浮层（主题色半透明底 + 虚线框）。"""
        if show:
            self.dropHint.setGeometry(self.scrollArea.rect())
            if not self.dropHint.isVisible():
                c = qconfig.themeColor.value
                self.dropHint.setStyleSheet(
                    f"background: rgba({c.red()}, {c.green()}, {c.blue()}, 90);"
                    f"border: 2px dashed rgba({c.red()}, {c.green()}, {c.blue()}, 220);"
                    "border-radius: 8px;"
                    "color: white; font-size: 16px; font-weight: 500;"
                )
                self.dropHint.raise_()
        self.dropHint.setVisible(show)

    # ------------------------------------------------------------ 文件操作
    def refresh_from_config(self):
        input_dir = cfg.input_dir.value
        if input_dir and os.path.exists(input_dir):
            self.scan_directory(input_dir)

    def _startup_scan(self):
        """启动时的首次扫描：分批建卡（progressive），避免长列表卡住界面。"""
        self.scan_directory(cfg.input_dir.value, progressive=True)

    def scan_directory(self, path: str, progressive: bool = False):
        matched = []
        if path and os.path.exists(path):
            try:
                for name in os.listdir(path):
                    full = os.path.join(path, name)
                    # 只纳入加密音乐文件；明文音频等非加密文件跳过
                    if os.path.isfile(full) and is_encrypted_file(full):
                        matched.append(full)
            except OSError:
                matched = []
        elif progressive:
            # 目录不存在：填充流程不会走到，手动解除空提示抑制
            self._filling = False
            self._update_count()
            return
        self._decrypted_names = build_decrypted_basenames(cfg.output_dir.value)
        self._replace_cards(matched, progressive=progressive)

    def _add_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择待解密文件", "", "All Files (*)"
        )
        if not files:
            return
        if not self._append_files(files)["added"]:
            signalBus.toast_requested.emit("未选择可解密的加密音乐文件。", "warning")

    def _append_files(self, paths) -> dict:
        """追加文件到任务列表，返回分类计数 ``{added, duplicate, invalid}``。

        路径先 ``normpath`` 规范化再比对，避免拖入（正斜杠）与对话框/扫描
        （反斜杠）同一文件字符串不一致导致去重失效。
        - added：实际新增卡片数；
        - duplicate：因已在列表被跳过数；
        - invalid：非加密文件被跳过数。
        """
        existing = {card.file_path for card in self._cards}
        # 输入/输出目录对比：扫描输出目录建已解密基名集合
        decrypted_names = build_decrypted_basenames(cfg.output_dir.value)
        result = {"added": 0, "duplicate": 0, "invalid": 0}
        new_paths = []
        for path in paths:
            path = os.path.normpath(path)
            # 非加密文件跳过；仅纳入加密音乐文件
            if not is_encrypted_file(path):
                result["invalid"] += 1
                continue
            if path in existing:
                result["duplicate"] += 1
                continue
            existing.add(path)
            new_paths.append(path)
            result["added"] += 1
        if new_paths:
            self._decrypted_names = decrypted_names
            self._add_cards([self._make_card(p) for p in new_paths])
        return result

    def _remove_completed(self):
        """移除状态为"已解密"的卡片。"""
        self._remove_cards([c for c in self._cards if c.status == "success"])

    def clear_files(self):
        self._clear_cards()

    # ------------------------------------------------------------ 右键菜单
    def _show_card_menu(self, card, pos):
        """卡片右键菜单：删除文件 / 移出列表。"""
        menu = RoundMenu(parent=self.window())
        del_act = Action(FluentIcon.DELETE, "删除文件")
        del_act.triggered.connect(lambda: self._delete_file(card))
        menu.addAction(del_act)
        rm_act = Action(FluentIcon.CLOSE, "移出列表")
        rm_act.triggered.connect(lambda: self._remove_from_list(card))
        menu.addAction(rm_act)
        menu.exec(card.mapToGlobal(pos))

    def _delete_file(self, card):
        """删除文件：从磁盘删除并移除卡片（刷新后不再出现）。"""
        path = card.file_path
        name = os.path.basename(path)
        box = MessageBox(
            "删除文件", f"确定要删除「{name}」吗？此操作不可恢复。", self.window()
        )
        box.yesButton.setText("删除")
        box.cancelButton.setText("取消")
        if not box.exec():
            return
        try:
            os.remove(path)
        except OSError as exc:
            logger.error(f"删除文件失败: {path} ({exc})")
            signalBus.toast_requested.emit(f"删除失败: {name}", "error")
            return
        self._remove_card(card)
        signalBus.log_emitted.emit(f"已删除文件: {name}", "success")
        signalBus.toast_requested.emit(f"已删除 {name}", "success")

    def _remove_from_list(self, card):
        """仅移出列表：不动磁盘文件（刷新后因文件仍在输入目录会重新出现）。"""
        name = os.path.basename(card.file_path)
        self._remove_card(card)
        signalBus.log_emitted.emit(
            f"已移出列表: {name}（文件保留，刷新后仍在输入目录会重新出现）", "info"
        )

    def get_file_paths(self) -> list[str]:
        return [c.file_path for c in self._cards]

    # ------------------------------------------------------------ 状态回调
    def _on_file_started(self, path: str):
        for card in self._cards:
            if card.file_path == path:
                card.set_status("running")
                break
        # 仅刷新右上角状态分布与计数，不重排网格——避免每转换一个文件整页卡片跳动
        self._update_count()

    def _on_file_finished(self, path: str, success: bool):
        for card in self._cards:
            if card.file_path == path:
                card.set_status("success" if success else "failed")
                break
        # 仅刷新右上角状态分布与计数，不重排网格——避免每转换一个文件整页卡片跳动
        self._update_count()

    def _on_file_cancelled(self, path: str):
        """用户停止任务：未处理完的文件（处理中 + 排队中）回退为「待解密」。"""
        for card in self._cards:
            if card.file_path == path:
                card.set_status("pending")
                break
        self._update_count()
