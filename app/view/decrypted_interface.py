# coding: utf-8
"""已解密文件页面 —— 卡片网格展示输出目录中的音乐文件。

按来源打标签：由本工具从加密输入解密产生 → 「已解密」（绿）；输出目录原本就有、
不对应任何加密输入 → 「已添加」（黄）。只扫描常见音乐文件类型。
支持：顶部分类下拉框（全部/已解密/已添加/歌手名/专辑名）与搜索栏过滤、
右键卡片播放 / 删除文件（删除带确认）、刷新 / 打开目录。「歌手名」「专辑名」
为归类排序（同值相邻、无信息排末尾），标签经内置 ffmpeg 后台批量探测并缓存。
"""

from collections import deque
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
    ToolTipFilter,
    ToolTipPosition,
    TransparentPushButton,
    qconfig,
)

from ..common.config import cfg
from ..common.cover_loader import CoverCache
from ..common.decrypt_scanner import build_input_basenames, output_source_label
from ..common.logger import logger
from ..common.media_info import guess_artist_from_name, probe_audio_info, probe_media
from ..common.signal_bus import signalBus
from ..common.utils import is_music_file
from ..components.file_info_dialog import FileInfoDialog
from ..components.grid_card_container import GridCardContainer
from ..components.task_card import TaskCard

# 搜索输入防抖（毫秒）：逐字符触发全量铺格实测 6 字符 526ms，合并后只重排一次
_SEARCH_DEBOUNCE_MS = 120
# 媒体探测同时在途上限：ffmpeg 是 CPU/IO 密集进程，不能占满全局线程。
# 探测任务**不再一次性全量塞进线程池**（QThreadPool 队列是 FIFO，会让
# 当前屏幕的封面排在几千个文件之后），改由主线程按「当前视口可见优先」
# 的双队列按需喂入，见 _ensure_media / _pump_media。
_MEDIA_MAX_THREADS = 2


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


class _MediaRunnable(QRunnable):
    """后台一次探测单文件封面 + 完整标签：结果入队，无参信号通知主线程。

    封面与元数据原本各起一个 ffmpeg 进程（同一文件读两遍）；``probe_media``
    用一次调用同时拿 stdout 封面 PNG + stderr 元数据，进程数减半。数据仍走
    ``queue.SimpleQueue``，信号只表达到达——避开跨线程 emit Python 对象的坑。
    无内嵌歌手标签时回退按文件名「歌名 - 歌手」解析（网络下载常见格式）。
    """

    def __init__(self, item, results: "queue.SimpleQueue", notify):
        super().__init__()
        self._item = item
        self._results = results
        self._notify = notify

    def run(self):
        cover = None
        info = {}
        tags = {"artist": "", "album": ""}
        try:
            cover, info = probe_media(cfg.ffmpeg_path.value, self._item[0])
            artist = (info.get("artist") or "").strip()
            album = (info.get("album") or "").strip()
            if not artist:
                artist = guess_artist_from_name(self._item[0])
            tags = {"artist": artist, "album": album}
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"媒体探测异常: {self._item[0]} ({exc})")
        self._results.put((self._item, cover, tags, info))
        try:
            self._notify.emit()
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"媒体就绪通知失败: {exc}")


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
    # 媒体探测完成通知（无参，payload 走 _media_results 队列）
    # 封面 + 标签一次 ffmpeg 调用搞定，两处回填共用同一批结果
    mediaDone = Signal()

    def __init__(self, parent=None):
        super().__init__("DecryptedInterface", parent)
        self._filter = ""
        self._empty_msg = "输出目录暂无已解密文件"
        self._input_basenames = set()  # 输入目录加密文件基名集合（建卡时判定来源）
        self._scan_gen = 0             # 扫描代次号：丢弃过期结果（连点刷新时旧扫描作废）
        self._scan_results = queue.SimpleQueue()  # 后台扫描结果（线程安全）
        self._sources = {}             # 条目 → 来源标签缓存（纯字符串计算，懒求解）
        self._refresh_mode = False     # 本次扫描是否由「刷新」触发（决定呈现契约）
        # 媒体探测统一状态：一次 ffmpeg 同时产出封面 + 标签，共用结果队列/在途集合
        self._cover_cache = CoverCache()   # 封面字节 LRU（按 (路径,mtime) 失效）
        self._tags = {}                    # item → {'artist','album'}（含空串，避免重复探测）
        self._media_info = {}              # item → 完整 info（供「查看信息」复用，免重复起进程）
        self._media_results = queue.SimpleQueue()
        self._media_pool = QThreadPool(self)  # 专用：密集探测不占满全局线程
        self._media_pool.setMaxThreadCount(_MEDIA_MAX_THREADS)
        # 探测调度：两条队列 + 三组状态，让「当前屏幕可见」的封面不必等
        # 整份列表按序跑完。一次性 start() 千级文件时，可见项在 FIFO 队列
        # 里永远排在队尾，屏幕上会长时间停留在占位图。
        self._media_urgent = deque()       # 视口可见项：appendleft → 队首最优先
        self._media_normal = deque()       # 全量补探测（归类排序需要所有标签）
        self._media_queued = set()         # 仍在队列中、尚未提交
        self._media_urgent_set = set()     # 已在 urgent（防止重复提权）
        self._media_inflight = set()       # 已提交、结果未回填（不可抢占）
        self._name_lower = {}              # path → basename.lower()（搜索缓存）
        # 搜索防抖：连续输入合并成一次重排
        self._searchTimer = QTimer(self)
        self._searchTimer.setSingleShot(True)
        self._searchTimer.setInterval(_SEARCH_DEBOUNCE_MS)
        self._searchTimer.timeout.connect(self._apply_search)
        self._tag_relayoutTimer = QTimer(self)  # 归类回填后防抖重排（批量归类）
        self._tag_relayoutTimer.setSingleShot(True)
        self._tag_relayoutTimer.setInterval(120)
        self._tag_relayoutTimer.timeout.connect(self._relayout)

        # 工具栏：计数 + 搜索 + 分类下拉 + 刷新 / 打开目录
        self.countLabel = CaptionLabel("0 个音乐文件", self)
        self.searchEdit = SearchLineEdit(self)
        self.searchEdit.setPlaceholderText("搜索音乐文件")
        self.searchEdit.setFixedWidth(240)
        # 分类下拉框：全部 / 已解密 / 已添加 / 歌手名 / 专辑名（后两项为归类排序）
        self.filterCombo = ComboBox(self)
        self.filterCombo.addItems(["全部", "已解密", "已添加", "歌手名", "专辑名"])
        self.filterCombo.setFixedWidth(112)
        self.btnRefresh = TransparentPushButton(FluentIcon.SYNC, "刷新列表", self)
        self.btnOpenDir = TransparentPushButton(FluentIcon.FOLDER, "打开目录", self)

        self.toolbarLayout.addWidget(self.countLabel)
        self.toolbarLayout.addStretch(1)
        self.toolbarLayout.addWidget(self.searchEdit)
        self.toolbarLayout.addWidget(self.filterCombo)
        self.toolbarLayout.addWidget(self.btnRefresh)
        self.toolbarLayout.addWidget(self.btnOpenDir)

        # 工具栏按钮提示：Fluent ToolTip（与任务页一致，进入 300ms 显示）
        self._buttonTips = []
        for btn, tip in (
            (self.btnRefresh, "<b>刷新列表</b><br/>重新扫描输出目录并更新文件列表"),
            (self.btnOpenDir, "<b>打开目录</b><br/>在文件管理器中打开输出目录"),
        ):
            btn.setToolTip(tip)
            btn.setToolTipDuration(-1)  # 鼠标移开才隐藏
            tip_filter = ToolTipFilter(
                btn, showDelay=300, position=ToolTipPosition.TOP
            )
            btn.installEventFilter(tip_filter)
            self._buttonTips.append(tip_filter)

        # 信号连接
        self.btnRefresh.clicked.connect(self.refresh)
        self.btnOpenDir.clicked.connect(self._open_output_dir)
        self.searchEdit.textChanged.connect(self._on_search)
        self.filterCombo.currentIndexChanged.connect(self._on_filter_changed)
        self.scanDone.connect(self._on_scan_done)
        self.mediaDone.connect(self._on_media_done)
        # 主题 / 强调色切换 → 重绘仍显示占位图的封面（真实封面不受影响）
        qconfig.themeChanged.connect(self._on_theme_changed_for_cover)
        qconfig.themeColorChanged.connect(self._on_theme_changed_for_cover)
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
        """构建单张文件卡片（预取元数据 + 来源徽章，不回退访问磁盘）。

        封面仅在物化（进入视口）时按需取：命中缓存直接设图，未命中则提交
        后台 ffmpeg 读取；卡片先显示主题色占位图，读取完成再回填。
        """
        path, size, mtime = item
        label = self._item_source(item)
        card = TaskCard(
            path,
            self,
            meta=(size, mtime),
            badge=(label, "success" if label == "已解密" else "warning"),
            cover=True,
        )
        card._source = label
        # 右键菜单：播放 / 删除
        card.setContextMenuPolicy(Qt.CustomContextMenu)
        card.customContextMenuRequested.connect(
            lambda pos, c=card: self._show_card_menu(c, pos)
        )
        self._apply_cover(item, card)
        return card

    # ------------------------------------------------------------ 卡片复用（滚动流畅性）
    def _park_card(self, card):
        """回收：隐藏入池、不销毁（省去滚动时 Fluent 控件反复重建）。"""
        card.hide()
        if len(self._card_pool) < self.card_pool_max:
            self._card_pool.append(card)
        else:
            card.deleteLater()

    def _reuse_card(self, item):
        """从池取一张卡片重新绑定条目；命中即省掉约 3.5ms 的控件构建。

        实测滚完千级列表原本触发 956 次 ``_make_card``（累计约 3.3s），
        复用后只有首次进入视口的条目需要真正建卡。右键菜单连接绑定在
        卡片对象上（``c=card`` 默认参数），复用时无需重连也不会重复连。
        """
        if not self._card_pool:
            return None
        card = self._card_pool.pop()
        path, size, mtime = item
        label = self._item_source(item)
        card.file_path = path
        card._lazy_item = item
        card._source = label
        card.nameLabel.set_hovered(False)   # 清掉上一文件的悬停滚动状态
        card.nameLabel.setText(os.path.basename(path))
        card.update_meta(size, mtime)
        card.set_badge(label, "success" if label == "已解密" else "warning")
        card.set_cover(None)                # 先清占位图，避免残留上一个封面
        self._apply_cover(item, card)
        return card

    # ------------------------------------------------------------ 媒体探测（封面 + 标签一次完成）
    def _apply_cover(self, item, card: TaskCard):
        """封面命中缓存立即设图；未命中则统一登记媒体探测（顺便拿标签）。"""
        cached = self._cover_cache.get(item[0], item[2])
        if cached is not CoverCache.MISS:
            card.set_cover(cached)   # None 也走占位图
            return
        # 物化范围含上下预载行，这里只按普通优先级登记；真正「屏幕上可见」
        # 的条目由 _on_visible_items / _prioritize_visible_items 提权。
        self._ensure_media(item)

    # ------------------------------------------------------------ 基类钩子：当前屏幕优先
    def _on_visible_items(self, items):
        """视口可见条目变化 → 把它们的封面探测插到队列最前。

        ``items`` 是网格自上而下的展示顺序；用 reversed + appendleft 让
        最上方的卡片排在 urgent 队首，屏幕内仍自上而下出图。已在运行的
        任务无法抢占也不重复提交，还排在后方的条目则直接提权，不再按
        整份列表的顺序等待。
        """
        for it in reversed(items):
            self._ensure_media(it, priority=True, pump=False)
        self._pump_media()

    def _prioritize_visible_items(self):
        """把当前视口的可见项提权（供全量补探测前调用，兜底钩子未触发的情形）。"""
        for it in reversed(self.visible_items()):
            self._ensure_media(it, priority=True, pump=False)

    def _ensure_media(self, item, priority: bool = False, pump: bool = True):
        """登记一次媒体探测（封面 + 标签共用一次 ffmpeg）。

        ``priority=True`` 表示「当前屏幕可见」：若该条目还在普通队列里排队，
        就复制一份插到 urgent 队首（原位置的条目出队时按 ``_media_queued``
        判重自动作废）；已在 ffmpeg 中运行的无法抢占，最多等一个任务完成
        （约几十毫秒）即可轮到。``pump=False`` 供批量登记时最后统一喂入。
        """
        if item in self._tags or item in self._media_inflight:
            return
        if priority:
            if item in self._media_urgent_set:
                return
            if item not in self._media_queued:
                self._media_queued.add(item)
            self._media_urgent_set.add(item)
            self._media_urgent.appendleft(item)
        else:
            if item in self._media_queued or item in self._media_urgent_set:
                return
            self._media_queued.add(item)
            self._media_normal.append(item)
        if pump:
            self._pump_media()

    def _pump_media(self):
        """按「可见优先」把队列喂给线程池，始终只保持最多 2 个在途任务。

        不让 QThreadPool 自己排长队：每次登记 / 每次结果回填都补喂一次，
        滚动、搜索、切分类后新出现的可见项就能立刻插队，而不是等前面
        几百上千个 ffmpeg 跑完。
        """
        while len(self._media_inflight) < _MEDIA_MAX_THREADS:
            item = self._take_media_item()
            if item is None:
                return
            self._media_queued.discard(item)
            self._media_inflight.add(item)
            self._media_pool.start(
                _MediaRunnable(item, self._media_results, self.mediaDone)
            )

    def _take_media_item(self):
        """取下一个待探测条目：先 urgent 后 normal，跳过已提权/回填的失效项。"""
        while self._media_urgent:
            cand = self._media_urgent.popleft()
            self._media_urgent_set.discard(cand)
            if (cand in self._media_queued
                    and cand not in self._media_inflight
                    and cand not in self._tags):
                return cand
        while self._media_normal:
            cand = self._media_normal.popleft()
            if (cand in self._media_queued
                    and cand not in self._media_inflight
                    and cand not in self._tags):
                return cand
        return None

    def _ensure_all_media(self):
        """为所有条目补探测（切到归类时调用；已探测的命中缓存直接跳过）。

        全量只按普通优先级排队：归类排序需要所有标签，但不必抢当前屏幕
        的封面带宽——pump 永远先取 urgent 队列。
        """
        for it in self._items:
            self._ensure_media(it, pump=False)
        self._prioritize_visible_items()
        self._pump_media()

    def _prune_media_queue(self):
        """列表重建后丢弃已不在新列表里的排队项（在途任务跑完自然作废）。"""
        valid = set(self._items)
        self._media_urgent = deque(it for it in self._media_urgent if it in valid)
        self._media_normal = deque(it for it in self._media_normal if it in valid)
        self._media_urgent_set.intersection_update(valid)
        self._media_queued.intersection_update(valid)

    def _on_media_done(self):
        """取空结果队列：一次回填封面 LRU + 标签缓存 + 存活卡片；归类时防抖重排。"""
        got = False
        while True:
            try:
                item, cover, tags, info = self._media_results.get_nowait()
            except queue.Empty:
                break
            got = True
            self._media_inflight.discard(item)
            self._cover_cache.put(item[0], item[2], cover)
            self._tags[item] = tags
            self._media_info[item] = info
            card = self._card_cache.get(item)
            # 仅回填当前 item 对应的存活卡片：重建 / 移除后 item 不在缓存，
            # 或 mtime 已变（新条目），旧封面不会被贴到错误文件上
            if card is not None and not self._is_card_stale(card, item):
                card.set_cover(cover)
        if got:
            # 有线程空出：立即按当前优先级补喂，可见项始终先出图
            self._pump_media()
            if self.filterCombo.currentText() in ("歌手名", "专辑名"):
                self._tag_relayoutTimer.start()

    def _is_card_stale(self, card: TaskCard, item) -> bool:
        """卡片是否已脱离当前展示条目（重建/移除后 item 不再匹配）。"""
        return getattr(card, "_lazy_item", None) != item

    def _on_theme_changed_for_cover(self, *_):
        """主题 / 强调色切换：重绘所有仍显示占位图的封面位。"""
        for card in self._card_cache.values():
            card.refresh_cover_placeholder()

    def _item_source(self, item) -> str:
        """条目来源标签（已解密 / 已添加），纯字符串计算 + 缓存。"""
        src = self._sources.get(item)
        if src is None:
            src = output_source_label(item[0], self._input_basenames)
            self._sources[item] = src
        return src

    # ------------------------------------------------------------ 歌手/专辑归类
    def _tag_of(self, item, field: str) -> str:
        """取条目的歌手 / 专辑值（未探测到返回空串，归类时排末尾）。"""
        tags = self._tags.get(item)
        return (tags.get(field) or "") if tags else ""

    def _on_filter_changed(self, *_):
        """切换分类：歌手名 / 专辑名需先确保标签探测，再按标签归类重排。"""
        if self.filterCombo.currentText() in ("歌手名", "专辑名"):
            # 顺序关键：先重排 → 物化触发可见项提权并立即开跑，再补齐全量
            # 标签。反序会让千级全量任务先占满 2 个线程，当前屏幕的封面
            # 被压到队尾，屏幕上迟迟还是占位图。
            self._relayout()
            self._ensure_all_media()
        else:
            self._relayout()

    def _lazy_filter(self) -> list:
        """按分类下拉 + 搜索词过滤/排列条目（未建卡也算数）。

        - 全部：仅按搜索词过滤，保持 mtime 倒序；
        - 已解密 / 已添加：按来源过滤；
        - 歌手名 / 专辑名：按标签归类排序——同值相邻、无标签排末尾，
          组内保持原 mtime 倒序（Python 稳定排序 + 原始列表有序保证）。
        """
        q = self._filter.strip().lower()
        cat = self.filterCombo.currentText()
        tag_field = (
            "artist" if cat == "歌手名" else "album" if cat == "专辑名" else None
        )
        if not q and cat == "全部":
            return list(self._items)
        view = []
        for it in self._items:
            if cat in ("已解密", "已添加") and self._item_source(it) != cat:
                continue
            if q:
                # 小写文件名按路径缓存：原实现对每个条目都做 basename+lower，
                # 千级条目是全量过滤里最重的一步（实测 3000 条约 12ms）
                name = self._name_lower.get(it[0])
                if name is None:
                    name = os.path.basename(it[0]).lower()
                    self._name_lower[it[0]] = name
                if q not in name:
                    continue
            view.append(it)
        if tag_field:
            # 稳定排序：键 (有值=0/无值=1, 值小写)；同值相邻、无值末尾、组内保序。
            # 每个元素只取一次标签值（避免原实现对同一元素调用两次 _tag_of）。
            def group_key(it):
                value = self._tag_of(it, tag_field)
                return (0, value.casefold()) if value else (1, "")
            view.sort(key=group_key)
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
        self._name_lower.clear()  # 每次扫描清一次，避免已删除文件路径残留
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
        # 重建后排队项可能属于已被删掉的旧文件：清掉，别让它们挡住当前
        # 屏幕的封面（在途的两个任务跑完自然作废，无需也不能取消）
        self._prune_media_queue()
        # 首次加载 / 列表条目变化后，若当前正处于标签归类则补探测新条目
        if self.filterCombo.currentText() in ("歌手名", "专辑名"):
            self._ensure_all_media()

    def _on_search(self, text):
        self._filter = text
        # 防抖：连续输入期间只更新过滤词，停下后再一次性重排
        self._searchTimer.start()

    def _apply_search(self):
        self._relayout()

    def _open_output_dir(self):
        out = cfg.output_dir.value
        if not out or not os.path.isdir(out):
            signalBus.toast_requested.emit("输出目录未设置或路径不存在。", "warning")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(out))

    # ------------------------------------------------------------ 右键菜单
    def _show_card_menu(self, card, pos):
        """在卡片上弹右键菜单（查看信息 / 播放 / 删除）。"""
        menu = RoundMenu(parent=self.window())
        info_act = Action(FluentIcon.INFO, "查看信息")
        info_act.triggered.connect(lambda: self._show_file_info(card))
        menu.addAction(info_act)
        play_act = Action(FluentIcon.PLAY, "播放音乐")
        play_act.triggered.connect(lambda: self._play_file(card))
        menu.addAction(play_act)
        del_act = Action(FluentIcon.DELETE, "删除文件")
        del_act.triggered.connect(lambda: self._confirm_delete(card))
        menu.addAction(del_act)
        menu.exec(card.mapToGlobal(pos))

    def _show_file_info(self, card):
        """弹出只读对话框展示文件的详细元数据。

        基础信息（大小/修改时间）来自建卡时预取的 stat，来源取卡片缓存；
        音频参数由内置 ffmpeg 同步探测（用户主动点击、单文件、约几十毫秒）。
        探测失败不阻断——对话框对缺失字段统一显示「—」。
        """
        path = card.file_path
        # 优先用已缓存的 stat，避免再访问磁盘；无缓存时回退 os.stat
        item = getattr(card, "_lazy_item", None)
        if item and len(item) == 3:
            _, size, mtime = item
        else:
            try:
                st = os.stat(path)
                size, mtime = st.st_size, st.st_mtime
            except OSError:
                size, mtime = 0, 0
        source = getattr(card, "_source", None) or ""
        if not source and item:
            source = self._item_source(item)
        # 优先复用后台探测时已缓存的完整 info（封面提取顺带解析），
        # 未缓存时才同步探测一次——避免同一文件重复起 ffmpeg。
        media = self._media_info.get(item) if item else None
        if media is None:
            media = probe_audio_info(cfg.ffmpeg_path.value, path)
        dialog = FileInfoDialog(
            path, size, mtime, source, media, self.window()
        )
        dialog.exec()

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
