# coding: utf-8
"""已解密文件页面 —— 卡片网格展示输出目录中的音乐文件。

按来源打标签：由本工具从加密输入解密产生 → 「已解密」（绿）；输出目录原本就有、
不对应任何加密输入 → 「已添加」（黄）。只扫描常见音乐文件类型。
支持：顶部分类下拉框（全部/已解密/已添加）与搜索栏过滤、右键卡片播放 / 删除
文件（删除带确认）、刷新 / 打开目录。
"""

import os
import queue

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

    返回 ``(items, input_basenames, empty_msg, scan_error)``：items 为
    ``(path, size, mtime)`` 元组列表，按修改时间倒序——stat 结果随扫描
    一次取齐，建卡时不再逐卡访问磁盘（scandir 单系统调用取 is_file + stat）。
    ``scan_error`` 为 True 表示目录读取失败（权限 / 掉线），调用方应保留
    旧列表，而不是把已有卡片清空后误报「暂无音乐文件」。
    """
    input_basenames = build_input_basenames(input_dir)
    items = []
    if not out_dir:
        return items, input_basenames, "尚未设置输出目录，请到配置界面设置", False
    if not os.path.isdir(out_dir):
        return items, input_basenames, "输出目录不存在", False
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
        return ([], input_basenames,
                "无法读取输出目录，请检查路径或权限（列表保持上次结果）", True)
    items.sort(key=lambda t: t[2], reverse=True)
    return items, input_basenames, "输出目录暂无音乐文件", False


class _ScanRunnable(QRunnable):
    """后台扫描任务：结果写入线程安全队列，再发无参通知让主线程取件。

    原实现由 QRunnable 直接持有 ``Signal(object)`` 并跨线程 emit 一个
    payload 元组，打包运行时该 SignalInstance 会退化为「0 参签名」并抛
    ``TypeError: only accepts 0 argument(s), 1 given!``，页面永久停在旧列表。
    改为数据走 ``queue.SimpleQueue``（纯 Python、线程安全），信号只表达
    「有结果到达」——不再依赖 Qt 对 Python 对象参数的跨线程封送。
    """

    def __init__(self, out_dir: str, input_dir: str, gen: int,
                 results: "queue.SimpleQueue", notify):
        super().__init__()
        self._out_dir = out_dir
        self._input_dir = input_dir
        self._gen = gen
        self._results = results
        self._notify = notify

    def run(self):
        try:
            items, input_basenames, empty_msg, scan_error = _scan_output(
                self._out_dir, self._input_dir
            )
        except Exception as exc:  # noqa: BLE001
            # 扫描本身异常也要回包，否则页面会永久停在旧状态 / 「检测中」
            logger.warning(f"输出目录扫描失败: {exc}")
            items, input_basenames, empty_msg, scan_error = (
                [], set(), "扫描输出目录时出错", True
            )
        # 先入队再通知：主线程收到通知时结果一定已可见
        self._results.put(
            (self._gen, items, input_basenames, empty_msg, scan_error)
        )
        try:
            self._notify.emit()
        except Exception as exc:  # noqa: BLE001
            # 退出竞态（Signal source deleted）或运行时信号异常都不得让
            # QRunnable::run() 抛出，否则 PySide 会打印整段 override traceback
            logger.debug(f"输出目录扫描通知失败: 代次 {self._gen}, {exc}")


class DecryptedInterface(GridCardContainer):
    """已解密文件管理页面（固定工具栏 + 滚动卡片网格）。

    懒加载页：输出目录可能积累千级文件，全部预建卡片会拖慢首屏与滚动——
    改为占位格 + 视口内按需物化，真实卡片数量始终与可见范围相当。
    """

    # 懒加载开关：仅创建视口内可见卡片
    lazy_fill = True

    # 后台扫描完成通知（后台线程 emit，自动队列连接回主线程）。
    # 无参：payload 从 _scan_results 队列取，避免跨线程封送 Python 对象
    scanDone = Signal()

    def __init__(self, parent=None):
        super().__init__("DecryptedInterface", parent)
        self._filter = ""
        self._empty_msg = "输出目录暂无已解密文件"
        self._input_basenames = set()  # 输入目录加密文件基名集合（建卡时判定来源）
        self._scan_gen = 0             # 扫描代次号：丢弃过期结果（连点刷新时旧扫描作废）
        self._scan_results = queue.SimpleQueue()  # 后台扫描结果（线程安全）
        self._sources = {}             # 条目 → 来源标签缓存（纯字符串计算，懒求解）
        self._refresh_mode = False     # 本次扫描是否由「刷新」触发（决定呈现契约）

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
            self._refresh_mode = False
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
        count_text = (
            f"{summary} · 匹配 {n_visible}/{total}"
            if self._filter.strip() and total != n_visible
            else f"{summary} · 共 {total}"
        )
        # 文本未变就不 setText：QLabel.setText 会 updateGeometry 并投递
        # LayoutRequest，刷新（数据未变）时无需惊动整页布局
        if self.countLabel.text() != count_text:
            self.countLabel.setText(count_text)
        if not visible:
            hint = (
                f"未找到与“{self._filter.strip()}”匹配的文件"
                if self._filter.strip() and total > 0
                else self._empty_msg
            )
            if self.emptyHint.label.text() != hint:
                self.emptyHint.label.setText(hint)
        self._set_empty_visible(not visible)

    # ------------------------------------------------------------ 文件操作
    def refresh(self):
        """后台扫描输出目录，完成后按「回顶部 + 自上而下」呈现（主线程零阻塞）。"""
        self._refresh_mode = True
        self._start_scan()

    def _start_scan(self):
        """启动后台扫描（代次号 +1，旧扫描的过期结果将被丢弃）。"""
        self._scan_gen += 1
        # cfg 读取在主线程完成，只把纯字符串交给工作线程
        QThreadPool.globalInstance().start(
            _ScanRunnable(
                cfg.output_dir.value, cfg.input_dir.value,
                self._scan_gen, self._scan_results, self.scanDone,
            )
        )

    def _on_scan_done(self):
        """扫描完成通知：取空队列，只应用当前代次的结果。"""
        payload = None
        while True:
            try:
                candidate = self._scan_results.get_nowait()
            except queue.Empty:
                break
            # 队列顺序是「线程完成顺序」，不保证代次递增：连点刷新时
            # 较新代次可能先完成。不能简单取队列最后一个，否则它的
            # payload 会被随后到达的较旧代次覆盖、整批被 gen 校验丢弃，
            # 页面永久停在旧列表。这里只认当前代次，其余全部作废。
            if candidate[0] == self._scan_gen:
                payload = candidate
        if payload is None:
            # 当前代次还在扫描中，稍后它自己的通知会再进本槽
            return
        (_gen, items, input_basenames, empty_msg, scan_error) = payload
        # 页面从未显示过时，隐藏视口只有 98×28：按它算列数只会建 1 列 /
        # 3 张卡，还会把首次切入的入场动画提前吃掉。丢弃这次结果，
        # 等 showEvent 用真实视口重新扫描（代次号继续串联，不残留在途）。
        if not self.isVisible() and not self._filled_once:
            return
        refresh = self._refresh_mode
        if scan_error:
            # 目录读取失败：保留旧列表，不把已有卡片清空成「暂无文件」，
            # 也不覆盖输入基名集合。列表为空时至少把错误文案显示出来。
            self._empty_msg = empty_msg
            logger.warning("输出目录扫描失败：保留上次列表")
            if not self._items:
                self._update_count()
            if refresh:
                self.replay_from_top()
            signalBus.toast_requested.emit(
                "刷新失败：无法读取输出目录，列表保持上次结果。", "warning"
            )
            return
        sources_changed = input_basenames != self._input_basenames
        self._empty_msg = empty_msg
        self._input_basenames = input_basenames
        self._sources = {}  # 输入基名集合已更新，来源标签缓存全部失效
        # 只比较路径集合：文件数量没变时，元数据（size / mtime）变化或
        # 输入目录变化都不该整页重建——前者只更新卡片上的大小/时间，
        # 后者只更新来源徽章。真有增删才重建（按 mtime 倒序重排）。
        same_paths = (
            len(items) == len(self._items)
            and {it[0] for it in items} == {it[0] for it in self._items}
        )
        if same_paths:
            if items != self._items:
                new_by_path = {it[0]: it for it in items}
                for old_it, card in self._card_cache.items():
                    new_it = new_by_path.get(old_it[0])
                    if new_it is not None and new_it[1:] != old_it[1:]:
                        card.update_meta(new_it[1], new_it[2])
            if sources_changed:
                for it, card in self._card_cache.items():
                    label = self._item_source(it)
                    if getattr(card, "_source", None) != label:
                        card.set_badge(
                            label, "success" if label == "已解密" else "warning"
                        )
                        card._source = label
                # 分类筛选依赖来源标签，筛选项可能变化，需重算 _view
                if self.filterCombo.currentText() != "全部" or self._filter.strip():
                    self._relayout_lazy()
            self._update_count()
            (self.replay_from_top if refresh else self.replay_fade_in)()
            return
        self._replace_cards(items, refresh=refresh)

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
