# coding: utf-8
"""任务管理页面 —— 卡片式待转换文件列表（固定工具栏 + 滚动网格）。

支持：添加文件 / 刷新列表 / 开始解密 / 拖入文件（文件或目录，目录取顶层）/ 删除；
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
    ToolTipFilter,
    ToolTipPosition,
    TransparentPushButton,
    qconfig,
)

from ..common.config import cfg
from ..common.decrypt_scanner import (
    build_decrypted_basenames,
    is_already_decrypted,
    list_encrypted_files,
)
from ..common.logger import logger
from ..common.platform_icon import platform_icon
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
        # 用户主动排除的路径（移出列表 / 删除文件）刷新时不再由目录扫描
        # 加回；手动添加且不在输入目录的文件继续随刷新保留。
        # 「删除完成」只清视图、不登记排除，见 _remove_completed()。
        self._excluded_paths = set()
        self._manual_paths = set()
        self._view_only_removal = False
        # 重建期间需要继承的转换状态（解密中 / 失败），键为文件路径
        self._preserve_status = {}
        self._last_input_dir = cfg.input_dir.value

        # 工具栏：计数 + 按钮组（FluentIcon 走内置 SVG，无需系统字体，不会渲染成方块）
        self.countLabel = CaptionLabel("共 0 个文件", self)
        self.toolbarLayout.addWidget(self.countLabel)
        self.toolbarLayout.addStretch(1)
        self.btnAdd = TransparentPushButton(FluentIcon.ADD, "添加文件", self)
        self.btnRefresh = TransparentPushButton(FluentIcon.SYNC, "刷新列表", self)
        self.btnDelete = TransparentPushButton(FluentIcon.DELETE, "删除完成", self)
        # 与「添加文件 / 刷新列表」同一按钮组件；点击开始解密（与主页按钮同一信号）
        self.btnStart = TransparentPushButton(FluentIcon.PLAY, "开始解密", self)
        for btn in (self.btnAdd, self.btnRefresh, self.btnDelete, self.btnStart):
            self.toolbarLayout.addWidget(btn)

        # 工具栏按钮提示：Fluent ToolTip（与主页 / 日志页一致，进入 300ms 显示）
        self._buttonTips = []
        for btn, tip in (
            (self.btnAdd, "<b>添加文件</b><br/>选择一个或多个加密音乐文件加入列表"),
            (self.btnRefresh, "<b>刷新列表</b><br/>重新扫描输入目录并同步已解密状态"),
            (self.btnDelete, "<b>删除完成</b><br/>从列表移除已解密卡片，文件仍在磁盘，刷新可恢复"),
            (self.btnStart, "<b>开始解密</b><br/>扫描输入目录并批量转换加密音乐"),
        ):
            self._install_tip(btn, tip)

        # 拖入提示浮层：拖文件经过时盖在滚动区上方（对鼠标透明，不拦正常操作）
        self.dropHint = QLabel("松开鼠标，添加至任务列表", self.scrollArea)
        self.dropHint.setAlignment(Qt.AlignCenter)
        self.dropHint.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.dropHint.hide()

        # 信号连接
        self.btnAdd.clicked.connect(self._add_files)
        self.btnRefresh.clicked.connect(self.refresh_from_config)
        self.btnDelete.clicked.connect(self._remove_completed)
        self.btnStart.clicked.connect(signalBus.request_start.emit)
        signalBus.file_started.connect(self._on_file_started)
        signalBus.file_finished.connect(self._on_file_finished)
        signalBus.file_cancelled.connect(self._on_file_cancelled)
        signalBus.paths_changed.connect(self._on_paths_changed)
        # 整批转换结束后统一重排一次，让已解密卡片沉底
        signalBus.conversion_finished.connect(self._on_conversion_finished)
        # 主题 / 强调色切换：重绘仍显示默认音乐图标的左侧位（真实平台图标不受影响）
        qconfig.themeChanged.connect(self._on_theme_changed_for_icon)
        qconfig.themeColorChanged.connect(self._on_theme_changed_for_icon)

        # 启动不同步建卡：延后到事件循环首轮，并分批渐进填充——
        # 数百张卡的输入目录会把启动拖死数秒，现在窗口先出、卡片随后流式出现
        QTimer.singleShot(0, self._startup_scan)

    # ------------------------------------------------------------ 工具提示
    def _install_tip(self, widget, text: str):
        """安装 Fluent 风格按钮提示（过滤器由页面持有，避免被回收导致失效）。"""
        widget.setToolTip(text)
        widget.setToolTipDuration(-1)  # 鼠标移开才隐藏
        tip = ToolTipFilter(widget, showDelay=300, position=ToolTipPosition.TOP)
        widget.installEventFilter(tip)
        self._buttonTips.append(tip)

    # ------------------------------------------------------------ 基类钩子
    def _make_card(self, path: str) -> TaskCard:
        # 平台图标按后缀解析为官方 FluentIconBase 枚举；有对应平台显示 logo，
        # 其余（明文等）传 None 显示默认音乐图标。其 path() 返回 :/ qrc 路径。
        # 布局与已解密卡片一致（复用同一 44×44 左侧缩略图位）。
        card = TaskCard(path, self, icon=True,
                        platform_icon=platform_icon(path))
        # 重建期间继承转换服务接管的在途状态（解密中 / 失败），避免刷新把
        # 「解密中」冲回「待解密」；磁盘已有明文时仍以实际结果为准。
        preserved = self._preserve_status.get(path)
        if is_already_decrypted(path, self._decrypted_names):
            card.set_status("success")
        elif preserved:
            card.set_status(preserved)
        # 右键菜单：删除文件 / 移出列表
        card.setContextMenuPolicy(Qt.CustomContextMenu)
        card.customContextMenuRequested.connect(
            lambda pos, c=card: self._show_card_menu(c, pos)
        )
        return card

    def _on_theme_changed_for_icon(self, *_):
        """主题 / 强调色切换：重绘仍显示默认音乐图标的左侧位。

        与已解密页 ``_on_theme_changed_for_cover`` 同理，只重绘占位图卡片，
        真实平台 logo 由图库本身提供、不随主题变色。
        """
        for card in self._cards:
            card.refresh_cover_placeholder()

    def _item_status(self, path: str) -> str:
        """预判条目状态（与 _make_card 判定同源），供重建前预排序使用。

        已解密优先于在途状态：输出目录已有明文时，即使快照里记着
        running / failed，也按已解密沉底——与 _make_card 完全一致。
        """
        if is_already_decrypted(path, self._decrypted_names):
            return "success"
        return self._preserve_status.get(path, "pending")

    def _sort_items(self, items: list) -> list:
        """重建前预排序：未解密在上、已解密沉底，同状态内保持扫描顺序。

        渐进填充路径据此顺序逐张补格，初次加载 / 刷新后即为期望顺序，
        无需等待窗口 resize 触发 _relayout 才突然重排。
        """
        return sorted(items, key=lambda p: _STATUS_ORDER.get(self._item_status(p), 9))

    def _sort_cards(self):
        # 待解密在上、已解密沉底，保持视觉稳定
        self._cards.sort(key=lambda c: _STATUS_ORDER.get(c.status, 9))

    def _on_card_removed(self, card):
        path = card.file_path
        if not self._view_only_removal:
            # 用户主动移出 / 删除文件：刷新时不再由目录扫描加回
            self._excluded_paths.add(path)
            self._manual_paths.discard(path)
        self._preserve_status.pop(path, None)
        # 同步从转换服务待处理队列剔除该文件
        signalBus.queue_remove.emit(path)

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
        text = (
            " · ".join(parts) + f" · 共 {count}" if parts else f"共 {count} 个文件"
        )
        # 文本未变就不 setText：QLabel.setText 会 updateGeometry 并投递
        # LayoutRequest，零重建刷新时无需惊动整页布局（与已解密页对齐）
        if self.countLabel.text() != text:
            self.countLabel.setText(text)
        if count == 0:
            hint = "暂无文件，点击“添加文件”、刷新列表，或直接拖入文件"
            if self.emptyHint.label.text() != hint:
                self.emptyHint.label.setText(hint)
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
    def _on_paths_changed(self):
        """目录配置变更：换输入目录时清空用户的排除/手工条目，再刷新。

        仅输出目录变更（例如改了解密结果存放位置）不应把用户移出的文件
        又加回来，所以按输入目录字符串是否变化来判断。
        """
        current = cfg.input_dir.value
        if current != self._last_input_dir:
            self._last_input_dir = current
            self._excluded_paths.clear()
            self._manual_paths.clear()
        self.refresh_from_config()

    def refresh_from_config(self):
        # 目录被清空或失效时也必须刷新（清空旧卡片），不能让上一目录的
        # 卡片残留；渐进填充避免大目录刷新时阻塞 UI
        self.scan_directory(cfg.input_dir.value, progressive=True, refresh=True)

    def _startup_scan(self):
        """启动时的首次扫描：分批建卡（progressive），避免长列表卡住界面。"""
        self.scan_directory(cfg.input_dir.value, progressive=True)

    def scan_directory(self, path: str, progressive: bool = False,
                       refresh: bool = False) -> list[str]:
        """按目录扫描重建列表，返回本轮实际纳入的文件路径列表。

        ``refresh=True`` 由用户点刷新 / 配置变更触发：呈现走「回顶部 +
        自上而下逐张刷新」；内部扫描（启动首扫、开始解密兜底）保持原视点。
        """
        # 目录扫描规则由 common 层单点提供（只取顶层、只纳入加密文件）
        matched = [p for p in list_encrypted_files(path)
                   if p not in self._excluded_paths]
        # 手动添加、不在输入目录的文件在刷新后继续保留（磁盘已删则剔除）
        for p in list(self._manual_paths):
            if os.path.isfile(p) and is_encrypted_file(p) and p not in matched:
                matched.append(p)
            else:
                self._manual_paths.discard(p)
        self._decrypted_names = build_decrypted_basenames(cfg.output_dir.value)
        # 「点刷新但输入目录没变」是最常见场景（与已解密页快速路径对齐）：
        # 列表与扫描结果完全一致且无在途填充时，只同步已解密徽章与计数，
        # 绝不摘挂网格——渐进重建期间 QScrollArea 的异步布局追赶会造成
        # 行高压缩（卡片叠压）与视点跳顶，用户即见「卡片挤压晃动」
        # 不能用「列表顺序相等」判定：`_relayout()` 会调用 `_sort_cards()`
        # 按状态重排 `_cards`（待解密在上、已解密沉底），而 matched 是目录
        # 扫描顺序。只要有任一卡片不是 pending（转换过 / 输出目录已有同名
        # 明文），窗口缩放、切页、滚动条显隐触发过一次 _relayout 后两者
        # 顺序就不同，快速路径永久失效——文件一个没变，每次点刷新仍走
        # 全量渐进重建（实测 138 文件 / 30 张 success：resize 后
        # current[0]=song030 vs matched[0]=song000），用户即见「刷新后
        # 从顶部开始出现 / 整页跳顶再涌回」。这里只比较文件集合，集合
        # 未变就零重建，并保持当前视觉顺序（最稳，无任何位移）。
        current = [c.file_path for c in self._cards]
        same_files = (
            len(current) == len(matched) and sorted(current) == sorted(matched)
        )
        if same_files and not self.pending_items():
            self._filling = False  # 首扫完成即解除空提示抑制（空目录正常显示空状态）
            # 快速路径不建卡，清空上次重建留下的状态快照，避免陈旧状态
            # 被后续「添加文件」误用
            self._preserve_status = {}
            # 状态按输出目录实况同步：磁盘已有明文时无论原状态（含失败 /
            # 解密中）一律纠正为已解密；明文被移走时只让 pending / success
            # 回退，running / failed 仍由转换服务接管，刷新不覆盖。
            status_changed = False
            for c in self._cards:
                if is_already_decrypted(c.file_path, self._decrypted_names):
                    expected = "success"
                elif c.status in ("pending", "success"):
                    expected = "pending"
                else:
                    expected = c.status
                if c.status != expected:
                    c.set_status(expected)
                    status_changed = True
            if status_changed:
                # 立即按「待解密在上、已解密沉底」重排，避免之后任意一次
                # 布局重算（窗口缩放 / 滚动条显隐）才突然整片沉底
                self._relayout()
            else:
                self._update_count()
            # 刷新：回顶部 + 自上而下逐张刷新；内部扫描：原地脉冲
            (self.replay_from_top if refresh else self.replay_fade_in)()
            return matched
        # 重建前快照转换服务接管的在途状态，供新卡继承（渐进填充期间
        # 到达的状态信号也会写入这张表，见 _on_file_* 回调）
        self._preserve_status = {
            c.file_path: c.status for c in self._cards
            if c.status in ("running", "failed")
        }
        self._replace_cards(matched, progressive=progressive, refresh=refresh)
        return matched

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
        # 渐进填充期间尚未建卡的「在途条目」也要参与去重，否则同一文件
        # 在填充未完成时被再次拖入/添加会建出两张卡（经基类封装，不碰内部队列）
        existing.update(self.pending_items())
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
            # 重新纳入用户此前移出的文件；登记为手工条目，刷新后仍保留
            self._excluded_paths.discard(path)
            self._manual_paths.add(path)
            self._preserve_status.pop(path, None)
            result["added"] += 1
        if new_paths:
            self._decrypted_names = decrypted_names
            self._add_cards([self._make_card(p) for p in new_paths])
        return result

    def _remove_completed(self):
        """移除「已解密」卡片：只清视图，文件仍在磁盘。

        刷新列表时这些文件应重新扫描并按输出目录实况显示（已解密），因此
        不登记排除路径、也不清掉手工添加标记。此前与「移出列表」共用
        ``_on_card_removed`` 的排除逻辑，导致刷新后列表长期缺文件，只有
        重启（排除表清空）才重新出现。
        """
        self._view_only_removal = True
        try:
            self._remove_cards([c for c in self._cards if c.status == "success"])
        finally:
            self._view_only_removal = False

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
            f"已移出列表: {name}（文件保留，刷新后不再出现在列表）", "info"
        )

    def get_file_paths(self) -> list[str]:
        return [c.file_path for c in self._cards]

    # ------------------------------------------------------------ 状态回调
    def _on_file_started(self, path: str):
        # 渐进填充期间目标卡片可能尚未建出：状态写入快照供 _make_card 继承，
        # 避免「重建中刷新 + 转换完成」把状态永久弄丢
        if self._filling:
            self._preserve_status[path] = "running"
        for card in self._cards:
            if card.file_path == path:
                card.set_status("running")
                break
        # 仅刷新右上角状态分布与计数，不重排网格——避免每转换一个文件整页卡片跳动
        self._update_count()

    def _on_file_finished(self, path: str, success: bool):
        status = "success" if success else "failed"
        if self._filling:
            self._preserve_status[path] = status
        for card in self._cards:
            if card.file_path == path:
                card.set_status(status)
                break
        # 仅刷新右上角状态分布与计数，不重排网格——避免每转换一个文件整页卡片跳动
        self._update_count()

    def _on_file_cancelled(self, path: str):
        """用户停止任务：未处理完的文件（处理中 + 排队中）回退为「待解密」。"""
        if self._filling:
            self._preserve_status[path] = "pending"
        for card in self._cards:
            if card.file_path == path:
                card.set_status("pending")
                break
        self._update_count()

    def _on_conversion_finished(self, *_):
        """整批转换结束后统一重排一次：已解密沉底、未解密在上。

        转换过程中逐文件只更新状态与计数、不重排整页（避免跳动）；
        整批结束时一次性按状态排序，把已解密卡片集中到列表下方。
        """
        self._relayout()
