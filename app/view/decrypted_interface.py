# coding: utf-8
"""已解密文件页面 —— 卡片网格展示输出目录中的音乐文件。

按来源打标签：由本工具从加密输入解密产生 → 「已解密」（绿）；输出目录原本就有、
不对应任何加密输入 → 「已添加」（黄）。只扫描常见音乐文件类型。
支持：顶部分类下拉框（全部/已解密/已添加）与搜索栏过滤、右键卡片播放 / 删除
文件（删除带确认）、刷新 / 打开目录。
"""

import os

from PySide6.QtCore import Qt, QRunnable, QThreadPool, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from qfluentwidgets import (
    Action,
    CaptionLabel,
    ComboBox,
    FluentIcon,
    MessageBox,
    RoundMenu,
    SearchLineEdit,
    TransparentPushButton,
)

from ..common.config import cfg
from ..common.decrypt_scanner import build_input_basenames, output_source_label
from ..common.logger import logger
from ..common.signal_bus import signalBus
from ..common.utils import is_music_file
from ..components.grid_card_container import GridCardContainer
from ..components.task_card import TaskCard


def _scan_output(out_dir: str, input_dir: str):
    """扫描输出目录音乐文件（含 stat 元数据）与输入基名集合（纯函数，可在后台线程执行）。

    返回 ``(items, input_basenames, empty_msg)``：items 为
    ``(path, size, mtime)`` 元组列表，按修改时间倒序——stat 结果随扫描
    一次取齐，建卡时不再逐卡访问磁盘（scandir 单系统调用取 is_file + stat）。
    """
    input_basenames = build_input_basenames(input_dir)
    items = []
    if not out_dir:
        return items, input_basenames, "尚未设置输出目录，请到配置界面设置"
    if not os.path.isdir(out_dir):
        return items, input_basenames, "输出目录不存在"
    try:
        with os.scandir(out_dir) as it:
            for entry in it:
                try:
                    if entry.is_file() and is_music_file(entry.path):
                        st = entry.stat()
                        items.append((entry.path, st.st_size, st.st_mtime))
                except OSError:
                    continue
    except OSError:
        items = []
    items.sort(key=lambda t: t[2], reverse=True)
    return items, input_basenames, "输出目录暂无音乐文件"


class _ScanRunnable(QRunnable):
    """后台扫描任务：完成后经 ``done`` 信号回主线程（携带代次号防过期）。"""

    def __init__(self, out_dir: str, input_dir: str, gen: int, done: Signal):
        super().__init__()
        self._out_dir = out_dir
        self._input_dir = input_dir
        self._gen = gen
        self._done = done

    def run(self):
        items, input_basenames, empty_msg = _scan_output(self._out_dir, self._input_dir)
        self._done.emit((self._gen, items, input_basenames, empty_msg))


class DecryptedInterface(GridCardContainer):
    """已解密文件管理页面（固定工具栏 + 滚动卡片网格）。

    懒加载页：输出目录可能积累千级文件，全部预建卡片会拖慢首屏与滚动——
    改为占位格 + 视口内按需物化，真实卡片数量始终与可见范围相当。
    """

    # 懒加载开关：仅创建视口内可见卡片
    lazy_fill = True

    # 后台扫描完成（后台线程 emit，自动队列连接回主线程）
    scanDone = Signal(object)

    def __init__(self, parent=None):
        super().__init__("DecryptedInterface", parent)
        self._filter = ""
        self._empty_msg = "输出目录暂无已解密文件"
        self._input_basenames = set()  # 输入目录加密文件基名集合（建卡时判定来源）
        self._scan_gen = 0             # 扫描代次号：丢弃过期结果（连点刷新时旧扫描作废）
        self._sources = {}             # 条目 → 来源标签缓存（纯字符串计算，懒求解）

        # 工具栏：计数 + 搜索 + 分类下拉 + 刷新 / 打开目录
        self.countLabel = CaptionLabel("0 个音乐文件", self)
        self.searchEdit = SearchLineEdit(self)
        self.searchEdit.setPlaceholderText("搜索音乐文件")
        self.searchEdit.setFixedWidth(240)
        # 分类下拉框：全部 / 已解密 / 已添加
        self.filterCombo = ComboBox(self)
        self.filterCombo.addItems(["全部", "已解密", "已添加"])
        self.filterCombo.setFixedWidth(104)
        self.btnRefresh = TransparentPushButton(FluentIcon.SYNC, "刷新列表", self)
        self.btnOpenDir = TransparentPushButton(FluentIcon.FOLDER, "打开目录", self)

        self.toolbarLayout.addWidget(self.countLabel)
        self.toolbarLayout.addStretch(1)
        self.toolbarLayout.addWidget(self.searchEdit)
        self.toolbarLayout.addWidget(self.filterCombo)
        self.toolbarLayout.addWidget(self.btnRefresh)
        self.toolbarLayout.addWidget(self.btnOpenDir)

        # 信号连接
        self.btnRefresh.clicked.connect(self.refresh)
        self.btnOpenDir.clicked.connect(self._open_output_dir)
        self.searchEdit.textChanged.connect(self._on_search)
        self.filterCombo.currentIndexChanged.connect(lambda *_: self._relayout())
        self.scanDone.connect(self._on_scan_done)
        # 输出目录变更 / 一批解密结束 → 后台扫描刷新已解密列表
        signalBus.paths_changed.connect(self.refresh)
        signalBus.conversion_finished.connect(lambda *_: self.refresh())

        # 不在构造时建卡：本页不在首页，首次切进来再分批渐进填充——
        # 启动阶段省掉这数百张卡的构建；期间 paths_changed 触发的 refresh 会
        # 同步建卡并置位 _filled_once，避免首次显示时重复劳动
        self._filled_once = False
        # 首次填充完成前抑制空提示（防止"0 个文件"假象闪现在页面中部）
        self._filling = True

    def showEvent(self, e):
        super().showEvent(e)
        if not self._filled_once:
            self._filled_once = True
            QTimer.singleShot(0, self._start_scan)

    # ------------------------------------------------------------ 基类钩子
    def _make_card(self, item) -> TaskCard:
        """构建单张文件卡片（预取元数据 + 来源徽章，不回退访问磁盘）。"""
        path, size, mtime = item
        label = self._item_source(item)
        card = TaskCard(
            path,
            self,
            meta=(size, mtime),
            badge=(label, "success" if label == "已解密" else "warning"),
        )
        card._source = label
        # 右键菜单：播放 / 删除
        card.setContextMenuPolicy(Qt.CustomContextMenu)
        card.customContextMenuRequested.connect(
            lambda pos, c=card: self._show_card_menu(c, pos)
        )
        return card

    def _item_source(self, item) -> str:
        """条目来源标签（已解密 / 已添加），纯字符串计算 + 缓存。"""
        src = self._sources.get(item)
        if src is None:
            src = output_source_label(item[0], self._input_basenames)
            self._sources[item] = src
        return src

    def _lazy_filter(self) -> list:
        """按分类下拉（全部/已解密/已添加）+ 搜索词过滤条目（未建卡也算数）。"""
        q = self._filter.strip().lower()
        cat = self.filterCombo.currentText()
        if not q and cat == "全部":
            return list(self._items)
        view = []
        for it in self._items:
            if cat != "全部" and self._item_source(it) != cat:
                continue
            if q and q not in os.path.basename(it[0]).lower():
                continue
            view.append(it)
        return view

    def _update_count(self):
        """计数与空状态（条目级统计：未物化的条目同样计入）。"""
        visible = self._view
        total = len(self._items)
        n_visible = len(visible)
        dec = sum(1 for it in visible if self._item_source(it) == "已解密")
        add = n_visible - dec
        parts = []
        if dec:
            parts.append(f"已解密 {dec}")
        if add:
            parts.append(f"已添加 {add}")
        summary = " · ".join(parts) if parts else "0"
        if self._filter.strip() and total != n_visible:
            self.countLabel.setText(f"{summary} · 匹配 {n_visible}/{total}")
        else:
            self.countLabel.setText(f"{summary} · 共 {total}")
        if not visible:
            if self._filter.strip() and total > 0:
                self.emptyHint.label.setText(f"未找到与“{self._filter.strip()}”匹配的文件")
            else:
                self.emptyHint.label.setText(self._empty_msg)
        self._set_empty_visible(not visible)

    # ------------------------------------------------------------ 文件操作
    def refresh(self):
        """后台扫描输出目录，完成后渐进重建卡片（主线程零阻塞）。"""
        self._start_scan()

    def _start_scan(self):
        """启动后台扫描（代次号 +1，旧扫描的过期结果将被丢弃）。"""
        self._scan_gen += 1
        # cfg 读取在主线程完成，只把纯字符串交给工作线程
        QThreadPool.globalInstance().start(
            _ScanRunnable(
                cfg.output_dir.value, cfg.input_dir.value,
                self._scan_gen, self.scanDone,
            )
        )

    def _on_scan_done(self, payload):
        """后台扫描完成：应用结果，懒加载铺格重建（真实卡片视口内按需创建）。"""
        gen, items, input_basenames, empty_msg = payload
        if gen != self._scan_gen:
            return  # 过期结果（期间又发起了更新一次的扫描）
        self._filled_once = True
        self._empty_msg = empty_msg
        self._input_basenames = input_basenames
        self._sources = {}  # 输入基名集合已更新，来源标签缓存全部失效
        self._replace_cards(items)

    def _on_search(self, text):
        self._filter = text
        self._relayout()

    def _open_output_dir(self):
        out = cfg.output_dir.value
        if not out or not os.path.isdir(out):
            signalBus.toast_requested.emit("输出目录未设置或路径不存在。", "warning")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(out))

    # ------------------------------------------------------------ 右键菜单
    def _show_card_menu(self, card, pos):
        """在卡片上弹右键菜单（播放 / 删除）。"""
        menu = RoundMenu(parent=self.window())
        play_act = Action(FluentIcon.PLAY, "播放音乐")
        play_act.triggered.connect(lambda: self._play_file(card))
        menu.addAction(play_act)
        del_act = Action(FluentIcon.DELETE, "删除文件")
        del_act.triggered.connect(lambda: self._confirm_delete(card))
        menu.addAction(del_act)
        menu.exec(card.mapToGlobal(pos))

    def _play_file(self, card):
        """用系统默认播放器打开音乐文件。"""
        QDesktopServices.openUrl(QUrl.fromLocalFile(card.file_path))

    def _confirm_delete(self, card):
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
