# 更新日志

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 规范。
版本号语义见 `pyproject.toml`（当前 `0.1.0`）。

---

## [未发布] - 2026-11-09

> **呈现契约反转（用户 2026-11-09 明确圈定）**：本节取代下方 2026-11-05/11-06
> 「刷新 = 屏幕闪一次、卡片位置与内容均不变」的契约。新契约为
> **「刷新后列表回到顶部，卡片从第一张开始自上而下逐张刷新」**。

### 变更

- **刷新呈现：原地同步脉冲 → 回顶部 + 自上而下瀑布流**（`GridCardContainer`）
  - 新增 `replay_from_top()`：先把滚动条 `setValue(0)`，再按 `getItemPosition()` 的行 / 列顺序收集回顶部后首屏（视口高 + 1 行余量）的卡片，同帧全部挂 `opacity=0`，交由 `_schedule_fade_in()` 按 16ms 节拍逐张淡回（单卡 220ms）；`budget=max(40, 视口内卡片数)`，宽屏首屏不留「下面几行不刷」。列表为空时对空状态浮层做一次 0.45→1.0 同步脉冲，**保证点刷新必有反馈**。
  - `_replace_cards(paths, ..., refresh=False)` 新增 `refresh` 标志：刷新触发的重建一律回顶部（渐进填充完成分支 `setValue(0)`、懒加载分支不再 `setValue(saved_value)`），并统一调用 `replay_from_top()`；**启动首扫、首次进入页面、开始解密兜底扫描** 仍保持原视点与原有入场 / 原地脉冲。
  - `replay_fade_in()` 保留但降级为「非刷新内部扫描」的原地反馈；`_unfreeze_fill()` / `_fill_next_chunk()` 按 `_fill_refresh` 选择反馈通道。空列表早退分支补一次 `replay_from_top()`（该分支没有「最后一批」完成回调）。
  - 任务页 `scan_directory(..., refresh=False)` 与已解密页 `_refresh_mode` 分别把「用户点刷新 / `paths_changed` / `conversion_finished`」和「内部扫描」区分开。

### 修复（上轮检视 9 条实测问题，本轮全部关闭）

**任务页（`app/view/task_interface.py`）**

- **#6 失败态不按磁盘实况纠正**：快速路径改为「输出目录已有同名明文时，无论原状态（含 `failed` / `running`）一律纠正为已解密；明文被移走时只让 `pending` / `success` 回退」。`failed` 卡不再永远显示失败。
- **#7 转换中刷新丢状态**：重建前把 `running` / `failed` 快照进 `_preserve_status`，`_make_card()` 继承；渐进填充期间到达的 `file_started` / `file_finished` / `file_cancelled` 会在目标卡尚未建出时把最新状态写回快照，避免「填充中信号到达 → 状态永久丢失」。
- **#8 清空 / 删除完成 / 移出 / 手动添加被刷新覆盖**：新增 `_excluded_paths`（用户主动移除的路径刷新时不再由目录扫描加回）与 `_manual_paths`（不在输入目录的手动添加项刷新后继续保留，磁盘已删则剔除）；`_on_card_removed` / `_append_files` 维护两者，换输入目录时清空重新扫描（仅改输出目录不动用户列表）；「移出列表」日志文案同步。
- **#9 刷新时状态变了却不重排、之后突然沉底**：快速路径检测到状态变化立即 `_relayout()` 按「待解密在上、已解密沉底」重排，消除「刷新不动 → 下次窗口缩放 / 滚动条显隐突然整片位移」。
- `scan_directory()` 现返回本轮实际纳入的路径列表；`MainWindow._dispatch_start()` 的「列表为空时扫描兜底」改用该返回值，保证解密队列与页面列表（含排除 / 手工规则）一致。

**已解密页（`app/view/decrypted_interface.py`）**

- **#1 隐藏页按 98×28 视口建卡**：`_on_scan_done()` 在「页面从未显示过且当前不可见」时丢弃扫描结果、不置 `_filled_once`，由 `showEvent()` 用真实视口重新扫描；首次进入的入场瀑布流不再被提前吃掉，也不会先显示 1 列 / 3 张再跳成 2 列 / 20 张。
- **#2 只改 mtime 就整页重建 + 顺序跳变**：快速路径判定由 `items == self._items`（含 `size/mtime`）改为**只比较路径集合**；集合不变时零重建，仅由 `TaskCard.update_meta()` 原地刷新卡片上的大小 / 时间，保持当前顺序。真有增删才重建并按 mtime 倒序重排。
- **#3 输入目录变化导致输出列表整页重建**：`sources_changed` 时不再重建，只更新已物化卡片的来源徽章（标签真变才 `set_badge`）；分类 / 搜索态下重算 `_view` 一次（筛选项可能变化）。
- **#4 输出目录读取失败清空旧列表并误报「暂无音乐文件」**：`_scan_output()` 增加 `scan_error` 返回位，`os.scandir` 抛 `OSError` 时给出「无法读取输出目录，请检查路径或权限（列表保持上次结果）」；`_on_scan_done()` 保留旧列表、弹 warning 提示，并仍给一次刷新反馈。
- **#5 空列表点刷新毫无反馈**：快速路径不再要求 `self._card_cache` 非空，空列表也走 `replay_from_top()`，由空状态浮层同步脉冲一次（实测 opacity 0.45→1.0）。

### 验证（证据 / 验证）

- 全程**只跑源码**：`.venv/Scripts/python.exe` + `QT_QPA_PLATFORM=offscreen` 与**真实 windows 平台双平台**，验证脚本置于系统临时目录、用临时目录造文件。**未执行任何打包命令，未运行任何打包产物**。
- 主要契约 `unclock_verify_top_refresh.py`：任务页数据不变（138 文件 / `value=1200`）、任务页数据真变化（`value=900`）、已解密页（`value=600`）三场景 × 双平台 **ALL=True**——刷新后 `value=0`、首帧视口内卡片 `first_zero=12/12`（8/8）、已点亮卡片数随时间单调增长（自上而下逐张亮起）、终态 opacity 全 1.0 无残留。
- 9 条修复 `unclock_verify_fixes.py`：14 项断言 × 双平台 **14/14 PASS**（失败态纠正、即时重排、running 继承、清空 / 移出 / 手工添加 / 换目录、隐藏页不建卡、元数据零重建、徽章零重建、扫描失败保留列表、空列表反馈 0.45）。
- 边界 `unclock_verify_fill_signal.py`：把时间片压到 0.001ms 强制 56~59 张卡在途时发出 `file_finished`，双平台目标卡最终均为 `success`（状态不丢）。
- `compileall -q app main.py build.py` OK；分层依赖检查 0 违规（仅 `view` 层引用 `components` / `service`）；源码 `MainWindow` offscreen 启动 12s 零异常。
- **未覆盖**：真实 um 转换与刷新并发的长时序、超大 / 网络目录性能（138 文件同数据刷新实测 9.35ms）。

### 新增：工具检测卡片右下角「官网分享」按钮（09:40）

- **方向（用户 2026-11-09 圈定）**：截图为首页「工具检测」三张 `VersionCard`；三张卡**各自**打开对应官方网站 / 官方仓库；右下角放**小图标按钮，点击直接唤起默认浏览器**（不是分享菜单、不是文字按钮）。
- **官网地址**（`app/view/home_interface.py` 模块级 `TOOL_HOMEPAGES`）：Unlock Music (um) → `https://github.com/unlock-music/cli`（来源 `README.md`）；FFmpeg → `https://ffmpeg.org/`；QMPC MMKV → `https://git.um-react.app/um/qmpc-mmkv`（来源 `docs/qmpc-mmkv-使用教程.md`「官方仓库」）。项目自身没有官网，不臆造统一地址。
- **组件层**（`app/components/version_card.py`）：`VersionCard` 新增 keyword-only `homepage` 与 `homepage_requested = Signal(str)`；右侧改为「顶部徽章行 + 底部按钮」竖直列，徽章行宽度固定取 READY / MISS 较宽者，避免后台检测结果到达时文本区宽度跳动；右下角为 `TransparentToolButton(FluentIcon.SHARE)` 20×20（图标 14×14、手型光标、tooltip 显示完整网址），未配置官网时自动隐藏。组件**不调系统服务**，只发信号——与 `PathCard.clicked → view` 的分层一致；`parent` 仍为构造第 4 位参数，保持向后兼容。
- **view 层**（`app/view/home_interface.py`）：三张卡分别传入官网；`_connect_signals()` 统一接 `homepage_requested → _open_homepage(url)`，由 `QDesktopServices.openUrl(QUrl(url))` 打开，返回 False 时弹 warning InfoBar。

#### 验证（证据 / 验证）

- 只跑源码：`.venv` python + `QT_QPA_PLATFORM=offscreen` 与**真实 windows 平台双平台**；探针把 `QDesktopServices` 换成假对象，**未真正唤起浏览器**；验证脚本全部置于系统 Temp。
- `unclock_verify_share_button.py` 双平台 **29/29 PASS**：按钮可见 / 20×20 / 图标有效 / tooltip 含正确网址；几何 `btn=(426,34)`、右距 14 / 下距 10、卡片高仍 64；READY 徽章在 `(374 或 401, 10)` 与按钮不重叠；徽章由隐藏→显示时按钮坐标与文本宽度**零位移**；三张卡分别打开 3 个不同 https 地址；MISS 态、未配置官网（按钮隐藏且点击不打开）兜底通过。
- `unclock_verify_share_realclick.py`：`QTest.mouseClick` 发真实鼠标事件，双平台均打开正确网址且**不误触发 `CardWidget.clicked`**；真实 windows 平台 `HomeInterface` 截图核对三卡视觉（右上角徽章 + 右下角小图标，无重叠）。
- `compileall -q app main.py build.py` OK；分层依赖 0 违规；源码 `MainWindow` offscreen 启动 12s 零异常。**零打包命令、零打包产物运行**。

### 变更：首页 / 日志页提示统一换成 Fluent ToolTip（09:50）

- **方向**：用户指定按 <https://qfluentwidgets.com/zh/pages/components/tooltip> 美化工具提示并补齐「相应」的提示。原 `setToolTip()` 走系统原生提示，与 Fluent 主题不一致。
- **统一机制**：用 `ToolTipFilter(widget, showDelay=300, position=...)` 安装事件过滤器，拦截 `QEvent.ToolTip`，改由组件库 `ToolTip` 显示（主题色圆角 + 投影 + 150ms 淡入）；`setToolTipDuration(-1)` 让提示在鼠标移开时才隐藏，便于阅读完整网址。过滤器实例由各控件持有，避免 Python 侧对象被回收导致浮层失效。
- **提示内容**（QLabel 富文本：加粗标题 + 换行说明，`html.escape` 转义标题与网址）：
  - 三张工具卡分享按钮：`<b>工具名 · 官方网站</b>` / 官网 URL / 「点击在默认浏览器中打开」；`ToolTipPosition.TOP_RIGHT` 右对齐，避免长网址浮层越出窗口右缘。
  - READY / MISS 徽章：工具已就绪（检测通过）/ 工具缺失（检查工具文件或在设置界面重新指定路径）。
  - 两张目录卡片、开始 / 停止按钮（三态文案随 `_set_button_state()` 切换，收尾态按钮禁用不弹提示）、日志页清空按钮。
- **分层**：`components` 只负责自身提示（`version_card.py` 模块级 `_fluent_tip()`、`path_card.py`），`view` 负责按钮状态文案；未引入跨层依赖。

#### 验证（证据 / 验证）

- `unclock_verify_fluent_tooltip.py` **offscreen 与真实 windows 双平台 56/56 PASS**：9 个控件各装 1 个 `ToolTipFilter` 且 duration=-1；模拟 `QEvent.Enter` → 300ms 后 Fluent 浮层出现且文案含工具名 / 官网 / 动作说明；`QToolTip.isVisible()` 恒为 False（原生被拦截，含主动发 `QHelpEvent` 的场景）；`QEvent.Leave` 后浮层隐藏；开始按钮 idle/running 文案切换、收尾态禁用通过。
- 真实 windows 平台**浅色 / 深色主题**浮层截图：加粗标题、圆角、投影、三行文字均清晰可读（offscreen 截图中文呈方框，是该平台缺中文字体，非代码问题）。
- 回归：上一轮 `unclock_verify_share_button.py` offscreen 29/29 PASS、`unclock_verify_share_realclick.py` 真实 windows PASS；分享按钮 `pos=(426,34)`、卡片高 64 未变。`compileall` OK、分层 0 违规、源码 `MainWindow` offscreen 启动 12s 零异常。**零打包命令、零打包产物运行**。

### 修复：删除完成后刷新列表不显示文件（10:00）

- **现象（用户 2026-11-09 报告）**：点「删除完成」→ 点「刷新列表」看不到文件；关闭软件重开后文件列表正常。
- **根因（已实测复现）**：上一轮 #8 引入的 `_excluded_paths` 把「删除完成」也当成用户主动排除。基类 `_remove_cards()` 同步回调 `_on_card_removed()`，无条件把每个 success 卡路径写入排除表并清掉 `_manual_paths`；`scan_directory()` 过滤掉这些路径，于是刷新永远不显示。重启后排除表为空才恢复——与「重启后正常」完全吻合。次生问题：手工添加且不在输入目录的文件被删除完成后，其手工标记被清掉，刷新时也一并消失。
- **修复**（`app/view/task_interface.py`）：新增 `_view_only_removal` 上下文标志；`_remove_completed()` 在移除期间置位，`_on_card_removed()` 在该标志下**不登记排除、不清手工标记**，仅照常清理状态快照并广播 `queue_remove`。语义区分：**删除完成 = 只清视图**（刷新按磁盘实况重扫，已解密的仍以「已解密」回来）；**移出列表 / 清空列表 / 删除文件 = 用户主动排除**（刷新不回来，保持上一轮 #8 契约）。`try/finally` 保证标志不残留。
- **范围说明**：本轮只按用户描述修「删除完成」；「清空列表」目前仍是刷新后保持为空。若也要改成刷新重扫，需一并调整该契约。

#### 验证（证据 / 验证）

- `unclock_verify_delete_refresh.py`：修复前 offscreen **9/15 PASS（6 项 FAIL）**——A2 刷新后仍 2 张、B2 空列表刷新仍 0 张、`excluded=['song000.ncm']`，而 C0 新实例 3 张复现「重启后正常」；修复后 **offscreen + 真实 windows 双平台 15/15 PASS**。覆盖部分 / 全部已解密、删除完成后空列表刷新、模拟重启、清空 / 移出 / 磁盘删除语义保持、手工添加外部文件保留。
- 回归：上一轮 9 条修复 `unclock_verify_fixes.py` 双平台 14/14 PASS；刷新契约 `unclock_verify_top_refresh.py` 3/3 ALL=True；分享按钮 29/29、Fluent 提示 56/56 PASS。
- `compileall` OK、分层 0 违规、源码 `MainWindow` offscreen 启动 12s 零异常。**零打包命令、零打包产物运行**。

### 修正：um 官方链接改为官方自托管仓库（10:05）

- **方向（用户 2026-11-09 指定）**：Unlock Music (um) 的官方链接修正为 <https://git.um-react.app/um/cli>。本节取代上方「09:40」条目里记录的 `https://github.com/unlock-music/cli`（该行保留作为当时决策的历史记录，不再作为现行地址）。
- **改动**：`app/view/home_interface.py` 模块级 `TOOL_HOMEPAGES["um"]` 改为新地址并更新来源注释；`README.md` 首段介绍里的 um 链接同步统一。FFmpeg 与 QMPC MMKV 两个地址**未动**。
- **链接核验（证据）**：实际抓取该地址，返回 Gitea 仓库页 `um/cli: 音乐解锁，但是命令行。 - cli - um git`，README 为「Unlock Music Project - CLI Edition」，含 Release / Go 构建说明与 `um.exe` 产物描述，确认是本工具 `um.exe` 的官方上游，链接可公开访问。
- **单点生效**：`VersionCard` 的分享按钮点击 URL、Fluent 提示里的网址文案均由传入的 `homepage` 动态生成，无需改组件层；实测 `toolTip()` 已显示新地址且不含旧域名。

#### 验证（证据 / 验证）

- `unclock_verify_share_button.py` **offscreen + 真实 windows 双平台 29/29 PASS**；`unclock_verify_share_realclick.py` 真实 windows 平台 `QTest.mouseClick` 打开 `['https://git.um-react.app/um/cli']`、未误触发 `CardWidget.clicked`。
- `unclock_verify_fluent_tooltip.py` 双平台 **56/56 PASS**；静态断言 `TOOL_HOMEPAGES['um']`、tooltip 富文本、ffmpeg/qmpc 未变均通过。
- `compileall -q app main.py build.py` OK；源码 `MainWindow` offscreen 启动 12s 零异常；全项目仅 `CHANGELOG.md` 历史记录行仍留有旧地址（刻意保留）。**零打包命令、零打包产物运行**。

---

## [未发布] - 2026-11-05

### 新增

- **卡片瀑布流入场**（`GridCardContainer`，两页统一）：新建卡片先在同一帧挂 `QGraphicsOpacityEffect(opacity=0)`，再按 16ms 节拍逐张淡入（单卡 220ms / OutCubic 缓出），形成「从少到多、由隐到显」的错峰铺开；顺序以**当前可见区域**为起点（区内仍自上而下），视口外上下各 2 行的预载卡片排到最后，避免滚到中部刷新时先等一批看不见的卡片淡完；一次重建最多错峰 40 张，其余（视口外）直接完全显示，千级列表不拖动画；滚动新物化改用 140ms 同批短淡入。动画结束立即卸载效果恢复原生绘制，卡片移除 / 列表重建时统一取消并清理动画与队列。透明度只改绘制、不改几何（实测挂/卸效果零 `Move` / `LayoutRequest`），因此不触碰刚修好的「点刷新零位移」。
- **`GridCardContainer` 卡片页公共基类**（`app/components/grid_card_container.py`，新建）：抽取任务页与已解密页约 60% 的重复骨架——「固定工具栏卡片 + 独立滚动区」双区平级结构（工具栏不再被滚动区包裹，滚动条归属滚动区内部、不再贴窗口右缘贯穿工具栏高度）、视口自适应网格、空状态浮层、批量建卡/移除、5 个子类钩子（`_make_card` / `_sort_cards` / `_visible_cards` / `_lazy_filter` / `_update_count` / `_on_card_removed`）。两页重写为子类，各自只保留差异逻辑。
- **已解密页懒加载机制**（类属性 `lazy_fill = True`）：扫描完成后只为全部条目铺 `QSpacerItem` 占位格（纯几何对象而非控件，千级条目铺格仅几毫秒），真实卡片**滚动进视口才创建**（上下各预载 2 行），滚出视口的卡片保留缓存不销毁（滚回来零重建、信号不重连）；滚动条高度始终正确。实测 300 文件：扫描后仅建 20 张卡（视口内），滚到底累计 50 张。
- **过滤/搜索/计数改条目级**（懒加载页）：未物化的条目同样参与分类下拉 + 搜索词过滤与计数统计，300 个文件不建一张卡即可搜出匹配项；来源标签（已解密/已添加）改纯字符串计算 + 缓存，不再依赖卡片存在。
- **已解密页扫描移入后台线程**：`_ScanRunnable` + `QThreadPool`，`os.scandir` 单系统调用取 `is_file` + `stat`，元数据 `(path, size, mtime)` 随扫描一次取齐；带**代次号**防过期（连点刷新时旧扫描结果直接丢弃）；cfg 读取在主线程完成，仅纯字符串进工作线程。扫描回包后主线程铺格，全程零阻塞。
- **`TaskCard` 预取参数**：`meta=(size, mtime)` 由扫描线程批量取齐传入，建卡不再逐卡 `os.stat`；`badge=(文本, kind)` 初始徽章跳过默认「待解密」徽章的创建-销毁-重建，批量建卡省一半徽章控件。
- **运行日志级别着色 + 清空按钮**（`log_interface.py` 重写）：`appendHtml` + `html.escape`（防日志内容注入标记），INFO/WARN/ERROR/OK/DEBUG 五级明暗主题双色板（`isDarkTheme()` 实时取色）；标题行右侧**纯图标**清空按钮（`TransparentToolButton` + 悬停提示），2000 行上限保留。
- **单文件解密超时机制**（`converter.py`）：`_FILE_TIMEOUT_MS = 120_000`，`QTimer` 超时 `kill()` 后复用既有 `finished/Crashed → _finalize_current_file` 收尾链路（`_handled` 守卫防双信号重复收尾），失败文案区分「超时终止」与「进程失败」。
- **文件取消独立信号** `file_cancelled = Signal(str)`：`converter.stop()` 收集「处理中 + 排队未开始」的文件逐个广播取消；任务页卡片回退「待解密」态；首页进度条照常推进到满（取消≠失败）。
- **空状态表情卡片**（`empty_status.py` 重写）：96×96 正方形表情卡片（等比缩放、平滑插值）居中在上、提示文字在下（自动换行）；资源缺失时退回信息图标 + 单行文字。任务页与已解密页空列表（清空/目录无文件）共用；`task_complete.png` 注册进 qrc。

### 变更

- **卡片网格列数自适应且取偶**：列数随视口宽度自适应（每多容纳一列 ≥260px 就加列），强制偶数（2/4/6…）；卡片始终拉伸填满整行、两侧零空白；`TaskCard` 最小宽 300 → 240 配合 6 列不溢出。
- **时间片分批建卡**：固定 40 张/批 → **12ms 时间片**（单帧构建满预算即让出事件循环），卡片构建耗时不一（磁盘 stat / 徽章创建）时每帧开销更稳定，填充期间滚动/悬停不掉帧；分批增量补格避免 O(n²) 重排。
- **视口 resize 重排防抖**（40ms）：拖拽缩放窗口时合并连续 resize 事件，停稳后重排一次，不再每帧全量摘挂卡片。
- **单实例提示 Fluent 化**（`main.py`）：原生 `QMessageBox` → qfluentwidgets `MessageBox`；因 `MaskDialogBase` 依赖父窗口尺寸铺满遮罩而主窗口尚未创建，用与主屏可用区域等大的透明无边框宿主窗口充当父对象，仅保留「确定」按钮。
- **`tools_detected` 信号 dataclass 化**：6 个裸参数 → `Signal(object)` 传 `ToolsReport` frozen dataclass（`ToolInfo{version, ready}` × um/ffmpeg/qmpc）；`tool_detector` 三个 `_check_*` 返回 `ToolInfo`，首页接收方改属性访问。
- **qrc 资源更新**：`welcome.png` → `interface.png`（首页 Banner 引用同步）；新增 `task_complete.png`。
- **工具 exe 目录迁移**：三个可执行文件从 `app/resources/` 移至项目根目录 `tools/`（与 `app/` 同级），`config.py` 默认路径与启动自动探测同步更新（旧 config.json 中残留的旧路径会在下次启动被新探测路径覆盖，无需手动清理）；`build.py` 预检与打包改通配 `tools/*.exe`（打包后落在 `dist/tools/`，与运行时探测路径一致）；`app/resources/` 仅保留图片资源。

### 修复

- **「点刷新后从顶部开始往下刷新」：整屏重放淡入改为一次同步脉冲**（用户圈定目标：屏幕闪一次，卡片位置与内容均不变）
  - 定位：此前验证只跑 `offscreen`，本轮补跑**真实 windows 平台**并统计 `QEvent.Paint`。双平台一致：滚到 `value=2000` 点刷新后位置恒 2000、冻结期 Paint=0、无挤压/回弹；唯一可见变化是**可见卡片瞬间全部变透明，再从视口最上一行逐行淡回（≈0.8s）**——即上一轮为修「刷新没反馈」加的 `replay_fade_in()` 整屏重放瀑布流，它让刷新看起来像整页重新加载。
  - 修复（`app/components/grid_card_container.py`）：`replay_fade_in()` 不再走 `_schedule_fade_in` 的错峰队列，改为新增 `_pulse_fade_in()`——只对**当前视口内**卡片挂 `opacity=0.45` 并**同时**在 200ms 内回到 1.0（常量 `_REPLAY_MIN_OPACITY` / `_REPLAY_PULSE_MS`）。不隐藏、不逐行铺开、视口外卡片不参与；网格 / 尺寸 / 内容高度 / 滚动位置一律不动。初次加载与新建卡片的瀑布流入场保持不变。
  - 顺带修掉两条仍在「自上而下铺开」的路径：① **已解密页目录真有增删**时走懒加载重建，末尾 `_materialize_visible()` 用默认 `stagger=True`，实测 effect_y 从 1162 递增到 1710；现加 `_suppress_materialize_fade` 标志（覆盖 `_relayout_lazy` 内部的物化入口，不只 `_replace_cards` 的显式调用），刷新重建时不排入场动画、解冻后统一脉冲，首次进入页面仍保留瀑布流。② `_cancel_fade_in()` 只卸载「已启动动画」卡片的 effect，队列里等待的卡片会**永久停在半透明**（实测刷新重建后残留 7 张），现遍历队列逐一 `_restore_fade`。
  - 调用方注释同步：`task_interface.py` / `decrypted_interface.py` / `_unfreeze_fill` / `_fill_next_chunk`。
  - 验证（全程只跑源码，未执行任何打包命令）：新增 `verify_pulse.py` 五场景（任务页顶部/中部、已解密页中部、两页数据变化重建）**offscreen 与真实 windows 双平台 ALL PASS 53/53**——首帧 opacity 恒 0.450、全显时刻离散 0ms、视口外动画 0、几何零位移 `Move=0/Resize=0`、行高恒 64、动画收尾 queue/anims/timer 全 0。回归：`verify_final` 7 项、`verify_replay` 4/4、`verify_scroll_replay` 8/8、徽章同步、瀑布流初次淡入 / 边界 / 任务页淡入、重建冻结、138 文件挤压 / 渐进重建 / 晃动、空目录、连点 5 次、滚动 6 位置全部 ALL PASS；`py_compile`、分层依赖 0 违规、双平台启动 12s 零异常。
  - 验证脚本判据同步（`verify_replay.py` / `verify_fade.py`）：把「自上而下淡入时序」改为「同步离散 ≤1 帧 + 最低 opacity ≥0.44 + 无残留」；`verify_fade` [2] 改为脉冲判据、[3] 改为「`_fade_scheduled` 归零」，初次进入的瀑布流判据 [1] 保留不变。

- **「刷新后顶部开始出现」：滚到中部点刷新，整页跳顶 + 卡片从第 0 张重新涌现**：两个叠加原因，均在 138 文件 / 30 张已解密 / `value=2000` 场景下实测复现。
  - **根因①（最常见，文件一个没变也全量重建）**：`_relayout()` 会调用 `_sort_cards()` 按状态重排 `_cards`（待解密在上、已解密沉底），而 `list_encrypted_files()` 返回目录扫描顺序。只要有过窗口缩放 / 切页 / 滚动条显隐触发的一次 `_relayout`，`current == matched` 就永久为 False（实测 `current[0]=song030.ncm` vs `matched[0]=song000.ncm`），快速路径失效 → 每次点刷新都走全量渐进重建。
  - **根因②**：真有文件增删时必然重建，而渐进重建的中间态被完整绘制出来——清空网格使 range 骤降、`value` 被 clamp 到 0，卡片从第 0 张逐批补格，填充完成后才 `setValue` 跳回。实测 `value=2000` 归零 **16/36 帧（≈640ms）**，期间 effect 卡片最小 y 从 0 递增到 1406，即用户看到的「从顶部开始出现」。
  - 修复①（`app/view/task_interface.py`）：快速路径判定由「列表顺序相等」改为**文件集合等价**（`len` 相等 + `sorted(current) == sorted(matched)`）。集合未变就零重建并保持当前视觉顺序，彻底消除排序差异造成的误重建。
  - 修复②（`app/components/grid_card_container.py`）：渐进重建且**已有列表 + 新列表非空**时冻结整页绘制（`setUpdatesEnabled(False)`，布局/resize 计算不受影响，填充照常跑），冻结期间不排淡入（否则动画在不可见状态下跑完）；最后一批完成后由 `_unfreeze_fill()` 一次性解冻 + 恢复滚动位置 + 按当前可见区重放淡入。用户看到的是「旧列表 → 新列表（同一位置）」的一帧原子切换，没有清空 / 跳顶 / 从顶部涌现。启动首扫（`had_cards=False`）刻意不冻结，保留原有流式入场。
  - 边界（`_unfreeze_fill()` 统一收尾覆盖三条路径）：**空目录刷新**时 `_fill_next_chunk` 直接早退、没有完成分支，实测会把页面**永久卡在不绘制状态**（`updatesEnabled=False / frozen=True`）；现改为空列表不冻结 + 早退分支兜底解冻，连点刷新时上一轮冻结也在新 `_replace_cards` 开头收尾。
  - 验证（全部源码运行，未执行任何打包命令）：`diag_top_start.py` 三场景——数据不变零重建、resize 后**不再重建**（`_replace_cards` 调用消失）、真变化时**归零且可绘制帧 = 0**（11 个归零帧全部落在冻结窗口），解冻瞬间 `value=2000`；`verify_rebuild_fade.py` **ALL PASS 3/3**（中间态不可见 / 视口内 16 张全部参与淡入 / 终态 143 张、位置 2000、绘制已恢复）；空目录探针 PASS、连点 5 次（目录不变 + 目录 +8）PASS、启动首扫流式淡入 PASS；`verify_final` 7 项、`verify_replay` 4/4、`verify_scroll_replay` 8/8、徽章同步、瀑布流淡入 / 边界 / 任务页淡入、138 文件挤压 / 渐进重建（含清空目录）/ 晃动回归全部 ALL PASS；`py_compile`、分层依赖 0 违规、`main.py` offscreen 启动 12s 零异常。
- **下拉到中/下部后点「刷新列表」，卡片完全不动（淡入预算全落在视口外）**：上一轮的 `replay_fade_in()` 按网格**第 0 行起算**错峰，且沿用 40 张预算，滚动位置这一维度没有纳入——滚到中/下部时，前 40 张全是用户看不见的顶部卡片，可见区域的卡片一张都不淡入，直观表现即「刷新失效、卡片不动」。
  - 实测证据（`diag_scroll_refresh.py`，138 文件，逐帧只采**视口内**卡片）：任务页 value=0 → 16/16 张淡入；value=1200 → **8/18**；value=3000 → **0/18**（全页 effect 峰值恒为 40，说明刷新与动画都执行了，只是全在视口外）。已解密页因懒加载缓存较小未复现，但同一逻辑隐患存在。上一轮 `verify_replay.py` 只在 value=0 验证，是明确盲区。
  - 修复（`app/components/grid_card_container.py`）：`replay_fade_in()` 改为**可见区优先**——按 `scrollBar.value()` / 视口高度把已入格卡片分成 `in_view` / `off_view`（区内保持行列自上而下，与 `_materialize_visible` 策略一致），顺序为 `in_view + off_view`；`_schedule_fade_in()` 新增可选 `budget` 参数（默认仍是 `_FADE_MAX_CARDS`，其余 4 条调用点行为零变化），重放时传 `max(40, 视口内卡片数)`，保证大窗口多行时整个可见区都参与淡入，视口外卡片只吃剩余额度、不拖长动画。
  - 验证（全部源码运行，未执行任何打包命令）：`diag_scroll_refresh.py` 两页 × 3 个滚动位置（0 / 1200 / 3000）**视口内卡片 100% 参与淡入**、几何漂移 0；`verify_scroll_replay.py` **ALL PASS 8/8**——中部刷新 `Move=0 / Resize=0 / drift=0`、`value` / `max` 不变、行高恒 64，视口内 18 张全参与且自上而下（前 8 张全显 10.5 帧 vs 后 8 张 15.6 帧），滚到中部新增/删除 5 文件后刷新条目数 143 / 138 正确；`verify_replay`（顶部）、徽章双向同步、`verify_final` 7 项、瀑布流淡入、边界、任务页淡入、138 文件挤压 / 渐进重建 / 晃动回归全部 ALL PASS；`py_compile`、分层依赖 0 违规、`main.py` offscreen 启动 12s 零异常。
- **点「刷新列表」像失灵：刷新后卡片一点不动（零反馈）**：上一轮为消除挤压晃动给两页加了「数据不变零重建」快速路径，但它连同**瀑布流淡入**一起跳过了——按钮确实触发扫描，页面上却没有任何可见变化，用户直观判断为「刷新功能失效」。
  - 实测证据（`diag_refresh_dead.py`，20 个 .ncm / 9 个 mp3）：数据不变点刷新时 `scan_directory` 调用正常、`effect` 采样 13 帧**全 0**、卡片数 / 几何 / `value` / `range` 全恒定；而数据变化路径功能**完全正常**（新增 5 文件→25 张、删除→20 张、输出目录新增同名明文→徽章 success、滚动 setValue 正常）。即：不是刷新逻辑坏了，是**零重建把刷新反馈也一起砍了**。
  - 修复①（`app/components/grid_card_container.py`）：新增 `replay_fade_in()`——`_cancel_fade_in()` 清残留、重置入场预算后，按 `gridLayout.getItemPosition(i)` 取**行列顺序**遍历当前已入格的可见卡片（占位格 `QSpacerItem` 无 widget 自动跳过），重新挂 `opacity=0` 并错峰淡入。只改绘制、**不摘挂网格 / 不改尺寸 / 不动滚动位置**，因此不会重现挤压与晃动；两页共用。
  - 修复②（`app/view/task_interface.py` / `decrypted_interface.py`）：两条快速路径在 `_update_count()` 后调用 `replay_fade_in()`，刷新重新「从少到多、由隐到显」；已解密页因走后台扫描，淡入开始比任务页晚约 1 帧（既有异步扫描延迟，非新增）。
  - 修复③（任务页）：快速路径的徽章同步改**双向**——输出目录同名明文出现→`success`，明文被移走→回退 `pending`；只在状态真变时 `set_status()`（它会重建徽章控件，无条件调用会惊动布局），`running` / `failed` 仍由转换服务接管。`_update_count()` 补「文本未变不 `setText`」守卫（与已解密页对齐），消除 `QLabel.setText` 在零重建刷新时投递的 `LayoutRequest`。
  - 验证（全部源码运行，未执行任何打包命令）：`verify_replay.py` 两页 **几何零位移**（`Move=0 / Resize=0 / drift=0`、`value` / `max` / `sc_h` 全不变、`minRowH=64` 无压缩帧）+ **淡入时序**（任务页全显 0→40、已解密页 0→20，单调递增且自上而下：前 8 张均值 10.5 / 后 8 张 31.0 帧）**ALL PASS 4/4**；徽章双向同步 3 项 ALL PASS；`verify_final` 7 项、瀑布流淡入、边界、任务页淡入、138 文件挤压/重建回归全部 ALL PASS；`py_compile`、分层依赖 0 违规、`main.py` offscreen 启动 12s 零异常。
- **任务页点「刷新列表」后卡片挤压晃动（GIF 实录，138 文件场景）**：用户动图显示卡片相互叠压、整体晃动。任务页与已解密页此前修复的差异：它是**即时模式 + 渐进填充**，且**没有「数据不变零重建」快速路径**——点刷新必然全量重建，把两个问题全部踩中。
  - 实测证据（138 个 .ncm、滚到中部 value=1200、点刷新）：① **行高压缩帧**——渐进填充期间 QScrollArea 对 scrollContent 的 resize 滞后于网格增长（+90ms 实测 `glHint=730 > sc=582`），布局在不够的高度内激活，QGridLayout 把 64px 行硬压到 50~59，卡片超出格子相互叠压（即 GIF 里的「挤压」）；② **视点跳顶**——清空网格瞬间 range 4514→0，value 1200 被 clamp 归 0，滚动位置丢失。
  - 修复①（`app/components/grid_card_container.py`）：新增 `_pin_content_height(rows)`——按行数计算网格需求高度，`scrollContent` 不足时**主动 resize 拉高**（只增不减），保证任何布局激活时内容高度足够、压缩帧不再出现。接入 `_relayout` / `_relayout_lazy` / `_fill_next_chunk` 每批补格后。刻意不用 `setMinimumHeight` 常驻约束：实测它会在 QScrollArea 的某些 resize 时序下把滚动位置静默清零（range 缩小时 value 不经 clamp 直接归 0、无 valueChanged 事件），破坏「筛选/刷新保持滚动位置」；改用只增不减的主动拉高后该回归消失（value 156 全程保持）。
  - 修复②（`app/components/grid_card_container.py`）：`_replace_cards` 渐进分支记录刷新前滚动位置 `_fill_restore_value`，全部填充完成（range 已按最终内容恢复）后一次 `setValue` 找回（超出时钳制），把「整页跳顶再涌回」收敛为一次原子位移。
  - 修复③（`app/view/task_interface.py`）：`scan_directory` 增加「数据不变零重建」快速路径（与已解密页对齐）——列表与扫描结果一致且无在途填充时，只同步已解密徽章（pending→success）与计数，绝不摘挂网格；「点刷新但目录没变」这一最常见场景彻底零布局变化。首扫空目录时同步解除 `_filling` 抑制，空状态正常显示。
  - 验证（全部源码运行，未执行任何打包命令）：138 文件滚到中部点刷新（数据不变）**全程零变化**（cards/行高/sc/value/range 逐帧恒定）；数据变化渐进重建期间**行高恒 64、squeezed=0、内容高度不低于需求**；填充完成后滚动位置恢复（1200→1200）；删 60/清空目录场景正常；已解密页 7 项综合回归 + 瀑布流淡入 + 边界验证 + 任务页淡入全部 **ALL PASS**；`py_compile` 通过；分层依赖违规 0；`main.py` offscreen 启动 12s 无异常。
- **点击刷新仍有卡片晃动（第三轮根因：物化卡片 hidden → 布局 sizeHint 虚小 → 内容高度被压再弹回）**：前两轮（零重建快速路径 / `activate()` 收敛）修完后，数据未变时已零位移，但**目录内容有变化触发重建**时仍晃。旧验证只测了「数据不变」路径，本轮补测数据变化场景才复现。
  - 实测证据（真实切页、滚到中部 value=1500、删 60 文件后点刷新）：重建后 +50ms 时**20 张新物化卡片全部 `isHidden()`**，`gridLayout.sizeHint()=1280`（恰好 = spacer 行总高，卡片行贡献为 0）；QScrollArea 按虚小的 hint 把 `scrollContent` 压到 1152 → 30 行 Fixed 64 被硬塞进压缩高度，**行高压成 61/多行归零、卡片挤到错误位置**（第一帧）；+300ms 卡片被显示后 hint 恢复 2010 → 内容高度拉回 → **卡片又弹回正确位置**（song028 实测 y 307→1060，跳 753px）。两帧间的大幅弹跳即晃动。此前两轮的信号阻断 / `setUpdatesEnabled` 冻结只覆盖同步段，而本次物化由「range 骤降 clamp → `valueChanged` → 滚动物化」触发在**异步段**（冻结窗口外），故未防住。
  - 根因：`_make_card` 建卡的 parent 是页面本身，`gridLayout.addWidget(card)` 时 Qt 把卡片迁移到布局容器（scrollContent），**`setParent` 迁移即 hide**，此后无人 show；hidden 的 widget 在 `QWidgetItem::sizeHint()`（`isEmpty()`）语义下对布局贡献为 0。`_relayout` 摘挂回填的卡片（`takeAt` + `setParent(None)` 同样触发 hide）存在同一问题。
  - 修复（`app/components/grid_card_container.py`）：新增 `_grid_add_widget(card, row, col)`（addWidget + 立即 `show()`），统一替换全部 4 处入格点——懒加载物化、懒加载重排回填、即时页重排回填、时间片分批补格。淡入模式下 `show()` 由 `opacity=0` 效果遮蔽，不会闪现完整卡片。
  - 验证（全部源码运行，未执行任何打包命令）：删 60 文件重建全程**行高恒 64、无压缩帧**，range 仅剩内容真实变小的单向调整（1456→1466，无「骤降→回升」双跳）；touch 排序变化重建同卡 y 跳变 **0**；删/增 60 文件仅剩一次性单向位移（内容真实变化合理重排，无回弹振荡）；7 项综合回归 ALL PASS；瀑布流淡入验证（错峰时序 / 收尾清理 / 重建边界）ALL PASS；`py_compile` 通过；`main.py` offscreen 启动 12s 无异常。
- **点击刷新仍有卡片上下晃动（第二轮根因：网格布局长期未收敛）**：上一轮已做到「数据未变时零重建」，但用户实测仍晃。改用**真实切页 + 卡片 `QEvent.Move` 事件监听**复现（此前只统计 `_replace_cards` 调用次数，漏判了不改数据结构的布局重算）。
  - 实测证据（真实 `switchTo` 到已解密页、滚到中部 value=1500）：点刷新时**没有任何 `_relayout` / `_replace_cards` 调用**，调用栈只有 `_on_scan_done → _update_count`，却产生 **44 个 `Move` 事件**，卡片 y 从 2075→2140、2004→2066……越靠下位移越小（+65→+49，每行约 2px 累积）；同时 `gridLayout` 总高 3930→4060、滚动条 `max` 3356→3486。
  - 根因：`_relayout_lazy()` 先 `gridLayout.activate()` 铺占位格，随后 `_materialize_visible()` 动态 `addWidget` 把布局重新置脏且**没有再次收敛**。网格长期停在占位格的临时行高（72），卡片填入后真实行高是 74。点刷新时 `countLabel.setText()` 即便文本相同也会 `updateGeometry()` 并投递 `LayoutRequest`，Qt 顺带补算整个网格 → 行高 72→74，越靠下累积偏移越大，肉眼即「整片卡片晃一下」。决定性实验：手动 `gridLayout.activate()` 让其收敛（行高 74 / `max` 3486）后再点刷新，`Move` = **0**，连点 2 次仍为 0。
  - 修复①（`app/components/grid_card_container.py`）：`_materialize_visible()` 在本次确有新增卡片时，末尾立即 `gridLayout.activate()`，保证任意时刻网格几何都是最终值；新增 `_empty_shown` 状态，`_set_empty_visible()` 在显隐未变时直接返回，避免重复 `setVisible` 触发无谓布局。
  - 修复②（`app/view/decrypted_interface.py`）：`_update_count()` 先与现有文本比较，相同则不 `setText`（`QLabel.setText` 会投递 `LayoutRequest`）；空提示文案同样短路。
  - 修复③（`app/view/decrypted_interface.py`）：零重建快速路径**去掉「必须无筛选」限制** —— 筛选/搜索态下 `_view` 由 `_items / _filter / 分类 / 输入基名` 决定，这些都没变时同样无需重建，原先搜索态点刷新仍会全量重建而晃。
  - 验证（全部源码运行，未执行任何打包命令）：真实切页 7 项综合验证 **ALL PASS** —— 连点 3 次刷新 `Move=0` / `replace=0` / 卡片几何完全一致 / value 与 max 保持；筛选+搜索态刷新 `Move=0` / `replace=0` / 计数与 `_view` 正确；新增 20 文件重建 1 次且滚动位置保持；徽章不一致 0；清空目录队列残留 0、无父可见卡片 0。旧 7 阶段回归全通过；30 文件 `py_compile` 0 失败；分层依赖违规 0；`main.py` offscreen 启动 12s 无异常。
- **刷新修复引入的 2 处回归（复检发现并修复）**：
  - ① **代次竞态导致最新结果被整体丢弃**：`_on_scan_done` 原先取空队列时只保留最后一个 payload，但队列顺序是「线程完成顺序」，不保证代次递增。连点刷新时若较新代次先完成，其 payload 会被随后到达的较旧代次覆盖，`gen != _scan_gen` 校验把整批丢弃，页面永久停在旧列表（实测：清空输出目录后刷新仍显示 40 个文件、`items=40`）。改为遍历队列、只认 `gen == _scan_gen` 的 payload；只有过期结果时直接丢弃，等当前代次自己的通知再进槽。
  - ② **输入目录变化后卡片徽章不更新**：快速路径（`items == _items` 时不重建网格）不同步已物化卡片的来源徽章，输入目录新增同名 `.kgm` 后计数已变「已解密」而卡片仍显示「已添加」（实测 1 张不一致）。快速路径增加「输入基名集合未变化」条件，`sources_changed` 时重建一次，兼顾零晃动与数据一致性。
  - 验证（全部源码运行）：4 个代次到达顺序用例全 PASS（较新先完成 / 较旧先完成 / 仅过期 / 含超前代次）；7 阶段完整窗口回归 —— 连点 3 次刷新重建 0 次且滚动位置保持 3850、数据增减滚动位置正确钳制、徽章不一致 0、清空目录 `items=0 / cards=0`、队列残留 0、全程无 `TypeError` / `QRunnable` 报错；30 文件 `py_compile` 通过；`main.py` offscreen 启动 12s 无异常。
- **点击「刷新列表」后卡片上下晃动**：`_replace_cards` 懒加载分支刷新时无条件清空网格，三重中间态叠加——滚动条最大值骤降为 0 触发 `valueChanged`，用尚未更新的 `_view` 误物化卡片；滚动条显隐引起视口 Resize → 40ms 防抖重排又全量摘挂一次；旧卡片 `setParent(None)` 后仍 visible，`deleteLater()` 生效前短暂浮为顶层窗口。同时滚动位置被清零（内容跳回顶部）。
  - 修复①（`app/components/grid_card_container.py`）：重建期间用 `QSignalBlocker` 阻断滚动条信号、`setUpdatesEnabled(False)` 关闭中间绘制，旧卡片先 `hide()` 再 `deleteLater()`；结束后恢复滚动位置、按新视口物化一次，并 `stop()` 掉期间排队的防抖重排，让整次重建表现为一次原子更新。`_remove_cards` 两条分支同样补 `hide()`。
  - 修复②（`app/view/decrypted_interface.py`）：扫描结果与当前 `_items` 完全一致且无搜索/分类筛选时，只刷新计数与来源标签、**不重建网格**（点刷新但目录没变是最常见场景，零布局变化）。
  - 验证（offscreen 源码运行）：滚到中部 value=3850 → 连点 3 次刷新，`_replace_cards` 调用 **0 次**、value 仍 3850；新增 20 文件后重建 1 次、value 仍 3850、卡片全部可见、`_relayoutTimer` 未排队。
- **已解密页刷新报 `QRunnable::run()` TypeError**：`_ScanRunnable` 原先跨线程 `emit((gen, items, basenames, empty_msg))` 到 `Signal(object)`，打包运行时该 `SignalInstance` 退化为 0 参签名，抛 `TypeError: only accepts 0 argument(s), 1 given!`，页面永久停在旧列表。源码环境连点刷新不复现；实测 `Signal()` 无参信号 emit 一个参数的报错文本与之完全一致（信号签名为空）。
  - 修复：结果改走 `queue.SimpleQueue`（标准库、线程安全），`scanDone` 改为**无参**信号，只表达「有结果到达」；主线程槽取空队列并按代次号只应用最新结果；`_ScanRunnable.run()` 的 emit 捕获所有异常，保证 `QRunnable::run()` 不再向外抛整段 override traceback。
  - 验证：30 文件 `py_compile` 0 失败；完整 MainWindow offscreen 连点 3 次刷新无异常、条目数正确；另用 Nuitka `--module` 编译探针确认「无参信号 + 队列」跨线程回包在编译模块下 payload 完整送达。**按项目约定，本轮起不再用 standalone 打包产物做验证，结论均来自源码运行。**
- **空状态提示闪现**：首次进入已解密页时，卡片渐进填充尚未开始，`_update_count` 先按「0 个文件」把居中空提示画了出来，首批卡建完又隐藏——视觉上「先悬浮中部、再跑到置顶」。新增 `_filling` 状态在填充期间强制隐藏空提示，填充结束按真实状态刷新；任务页目录不存在的提前返回路径同样正确解除抑制。
- **`build.py` 打包排除项误杀硬依赖、导致 exe 启动崩溃**（两处）：现象为添加二次排除后 `releases/main.dist/音乐解锁工具.exe` 启动即抛 `ImportError: Module 'PySide6.QtXml' was actively excluded from Nuitka compilation`，而源码运行正常。
  - 根因①：`qfluentwidgets/common/icon.py:6` 顶层 `from PySide6.QtXml import QDomDocument`（SVG 图标着色），`common/__init__.py` 是 qfluentwidgets 导入必经路径；`--nofollow-import-to=PySide6.QtXml` 与 `--noinclude-dlls=*Qt6Xml*` 把绑定和运行库一起排掉了。
  - 根因②（修完①后重打包启动才暴露）：`qframelesswindow/utils/win32_utils.py:9-12`、`windows/__init__.py:5-7`、`windows/window_effect.py:7-9` 无条件 `import win32api / win32con / win32gui / win32print`，`qfluentwidgets/components/widgets/frameless_window.py:8` 亦 import win32con；原注释「全 site-packages 零 import win32」判断错误，4 条 `--nofollow-import-to=win32*` 与 `--noinclude-dlls=pywintypes312.dll` 同样误杀。
  - 修复：删除上述 6 条排除项，并在 `build.py` 内就地写明硬依赖证据；保留 QtNetwork 排除（全量扫描零 import，且 `PySide6/__init__.py:89` 的探测有 `try/except ImportError` 保护）及其余 DLL / 插件排除。全量扫描确认实际依赖仅 QtCore / QtGui / QtWidgets / QtSvg / QtSvgWidgets / QtXml。
  - 顺带修正：`preflight()` 改以 `importlib.util.find_spec("nuitka")` 判定 Nuitka（构建命令走 `python -m nuitka`，当前 venv 无 `Scripts/nuitka.exe` 且 PATH 无该命令，旧判断会误报「未找到 Nuitka」直接退出）；产物目录由 `音乐解锁工具.dist` 改为按入口脚本名生成的 `main.dist`，文件头注释同步。
  - 验证：Nuitka 4.3.1 / Python 3.12 重打包成功（182.2 MB）；产物含 `QtXml.pyd` / `qt6xml.dll` / `win32api.pyd` / `pywintypes312.dll`；启动 exe 持续运行无 traceback，`main.dist/app.log` 记录「音乐解锁工具 启动」及三个工具 exe 全部就绪。OpenSSL 两条排除经本次启动验证当前路径未触发 `import ssl`，但若后续引入网络/HTTPS 代码须删除。
- **P0/P1 逐代码检视后的分层修复**（本轮）：按 common → components → service → view → 脚本 顺序修复；跨层依赖检查 **0 违规**（components / service 只依赖 common，view 作为装配根持有 service 实例，service 零反向依赖 view）。
  - **common**：`config.py` 内置 exe 仅在「未配置 / 路径失效」时回退，**尊重用户自定义且有效的工具路径**（此前设置页改动重启即被覆盖）；`_config_existed` 移到 `qconfig.load` 之前；新增 `CONVERSION_OPTIONS` 元数据（um 参数 + 默认值）下沉 common，供 service / view 共用，消除两处硬编码。`decrypt_scanner.py` 的 `build_decrypted_basenames` 只纳入音乐文件（输出目录里同名 `song.txt` 曾让 `song.kgm` 被误判已解密）；新增纯函数 `list_encrypted_files` 统一输入目录扫描规则。
  - **components**：`grid_card_container.py` 时间片预算由 `time.monotonic()`（秒）与 12（毫秒）直比改为 `/1000`，12ms 让出真正生效、长列表分批建卡不再一次性同步跑完；新增 `pending_items()` 封装在途条目供子类去重，不暴露内部队列。
  - **service**：`converter.py` 的 `stop()` 无论 QProcess 处于 Running / Starting / NotRunning 都清空队列并置 `_stopped`，拦截已排队的 `QTimer.singleShot`，修复「按钮已复位、后台继续解密」竞态；输出中 `conversion failed` / `run app failed` 与退出码共同判定成功；`_build_file_args` 改用 `CONVERSION_OPTIONS`；对「否」+ um 默认开启的 `-n` 发一次明确提示（实测 `um --help`：六个参数中仅 `-n` 默认 true 且无关闭参数；实测无效文件退出码 1，故退出码判定成立、文本为双保险）。`tool_detector.py` 三处版本探测加 8s timeout，`_DetectTask` 兜底捕获所有异常并广播中性报告，版本卡不再永远停在「检测中」。
  - **view**：`task_interface.py` 输入目录失效也刷新（清空旧卡片）、复用 `list_encrypted_files`、去重合并 `pending_items()`；`main_window.py` 列表为空时改渐进建卡 + common 纯扫描取路径，不再同步阻塞 UI；`decrypted_interface.py` 扫描异常也回包；`setting_interface.py` 由元数据生成卡片并标注 um 默认值与「否」的限制。
  - **脚本**：`build.py` 工具扫描基于 `ROOT`（不再依赖 cwd；绝对源路径 + 相对目标路径）；`启动程序.bat` 补 `cd /d "%BAT_DIR%"`。
  - **验证**：30 个业务文件 `py_compile` 全通过；实测 12ms 预算约 12ms 让出、cwd=Temp 时仍含 3 个 exe、`song.txt` 不再误判、隔离 exec 验证「自定义有效路径保留 / 失效回退内置」；service 实测 `stop()` 后队列清空且延迟启动被拦截；`QT_QPA_PLATFORM=offscreen` 源码启动 12s 无异常；Nuitka 4.3.1 重打包成功（182.2 MB，7 个关键文件齐全），exe 启动 12s 无 traceback，`main.dist/app.log` 显示三工具全部就绪。

---

## [未发布] - 2026-10-28

### 变更

- **工具栏置顶（不随列表滚动）**：`Interface` 基类由「整体 ScrollArea」重构为「固定头部（`stickyLayout`）+ 内嵌滚动区（`scrollArea`/`view`/`vLayout`）」双区结构——不需要置顶的页面（首页/日志/设置）只用 `vLayout`，布局与旧版完全一致（stickyLayout 为空时零高度零边距）；任务页与已解密页的工具栏移入 `stickyLayout`，垂直滚动只发生在列表区，**工具栏始终可见**。
  - 边距换算：stickyLayout `(30,30,30,8)` + vLayout 上边距调为 12 → 工具栏与列表间距仍是旧版的 20px。
  - 网格列数改由**滚动区视口 resize 事件过滤器**驱动（`_on_viewport_resized` 钩子）：页面 resizeEvent 触发时内嵌滚动区尚未被布局刷新，视口宽度会滞后一帧；`_relayout` 的可用宽改取 `scrollArea.viewport().width()`（已排除垂直滚动条宽度）。
  - 拖入提示浮层几何同步保留在页面 resizeEvent（权威值仍以拖入开始时为准）。

---

## [未发布] - 2026-10-23

### 新增

- **任务管理界面支持拖入文件**（`app/view/task_interface.py`）：页面开启 `setAcceptDrops`，从资源管理器拖入**文件或目录**即加入任务列表——目录取**顶层**加密文件（与目录扫描一致，不递归子目录）；沿用既有过滤规则（仅加密音乐文件入列，明文音频跳过、重复不添加、命中输出目录标「已解密」）。拖入经过时列表区显示**主题色半透明 + 虚线框提示浮层**（「松开鼠标，添加至任务列表」，对鼠标透明），离开/放下即收起。Toast 分类提示：新增数 + 跳过原因（重复/非加密）；纯文本等非文件拖入忽略。空提示文案补「或直接拖入文件」。
- `_append_files` 返回值由 `bool` 改为分类计数 `dict{added, duplicate, invalid}`，供拖入/选择文件分别给出准确提示。
- **启动速度优化**（cProfile 定位：构造期 3.5s 中 ~3.4s 花在「两页全量建卡 ~410 张 + 3 个子进程检测」）：
  - **任务页首次扫描分批渐进建卡**（`scan_directory(progressive=True)` + `_fill_next_chunk`，每批 40 张、批间让出事件循环，增量补格避免 O(n²) 重排）；`__init__` 中的同步刷新改为 `QTimer.singleShot(0)`。
  - **已解密页懒建卡**：构造不再刷新，首次 `showEvent` 切入本页才分批填充（首页启动看不到本页）；`refresh()` 置位 `_filled_once` 防 `paths_changed` 先触发导致重复建卡。
  - **工具检测移入后台线程池**（`ToolDetector.detect_async` + `QRunnable`）：不再阻塞启动关键路径，结果经信号总线队列连接异步更新首页；`_DetectTask.run` 捕获退出竞态的 `RuntimeError`。
  - **去掉 `MainWindow` 中重复的任务页刷新**（`__init__` 已刷过一次，白建 ~270 张卡）。
  - **工具卡 neutral 初始态**：`VersionCard.set_detecting()` 显示「检测中...」且双徽章隐藏，后台检测结果到达前不闪 MISS。
  - **跑马灯第二份文本按需创建**：仅在真正开始滚动时创建（不滚动的卡片永远只有一份），数百张卡的启动/刷新场景省约一半标签构建。
  - 实测（offscreen，90+60 文件）：**到窗口可见 4995ms → 1745ms**（其中 MainWindow 构造 3471ms → 212ms；剩余为 ~1.1s 的 PySide6/qfluentwidgets/loguru 导入，已近极限）；窗口可见后卡片流式填充、界面全程可响应。

### 修复

- **拖入路径去重失效**：`QUrl.toLocalFile()` 返回**正斜杠**路径，与文件对话框/目录扫描的**反斜杠**原生路径字符串不同，同一文件会被添加两张卡；`_collect_drop_paths` 与 `_append_files` 统一 `os.path.normpath` 规范化后再比对/建卡。
- **拖入高亮残留**：非文件拖入走 `dragEnterEvent` 忽略分支时未收起提示浮层（`dragLeave` 偶发不达时会残留），忽略分支一并收起。

---

## [未发布] - 2026-10-22

### 变更

- **跑马灯效果优化**（`app/components/marquee_label.py` 重写）：
  - **首尾相连无缝循环**——内部持两份相同文本，滚动偏移在「文本宽 + 48px 间距」周期内取模：第二份恰好在第一份完全滚出视区时接替，回绕即一帧之差的正常滚动，**无跳变、无停顿**；相邻两份间距恒定 48px，未滚动时第二份隐藏只显示一份。
  - **启动提速**——悬停起始延迟 0.35s → **0.15s**，并加 0.15s 起步加速（速度 50%→100% 平滑升起），约 **0.30s 达到全速**（原约 1.15s）。
  - 保留时间驱动（`QElapsedTimer`，16ms≈60fps + `PreciseTimer`）与 **85px/s** 全速；`_MAX_DT` 钳制单帧步长防卡顿跳跃；resize 时 offset 钳制回周期内；`hideEvent` 停表复位。
- **已解密页工具栏**：分类下拉框移至**搜索框右侧**（排列：计数 → 搜索框 → 下拉框 → 刷新列表 → 打开目录）。

---

## [未发布] - 2026-10-21

> 相对上一个提交 `5a8e8bd` 的功能迭代汇总；本版改动尚未提交/发布。
> 上一个提交 `5a8e8bd`（逐代码审查 + 修复 9 项 bug/逻辑漏洞 + 项目整体检查）不计入本节。

### 新增

- **已解密判定（输入 / 输出目录「去后缀」比对）**：新增 `app/common/decrypt_scanner.py`——扫描输出目录建立「已解密目标基名集合」；遍历输入文件，**非加密文件跳过**，加密文件按去后缀规则算出目标基名查集合：命中即**已解密**，未命中即**待解密**；并汇总（已解密 / 待解密 / 跳过）输出。`app/common/utils.py` 新增 `PLAIN_AUDIO_SUFFIXES` / `ENCRYPTED_SUFFIXES`、`is_encrypted_file()`、`target_basename()`（支持 `.kgm.flac` / `.vpr.flac` 等复合后缀）。
- **任务四态与实时状态分布**：任务卡徽章区分 `待解密 / 解密中 / 已解密 / 失败 / 已跳过`；工具栏右上角实时显示 `待解密 X · 解密中 Y · 已解密 Z · 失败 W · 共 N`（仅列非零项）。
- **首页合并开始/停止按钮 + 进度条**：新增 `controlCard`（`CardWidget`），内布局 `进度文本 + ProgressBar(stretch) + 合并按钮`；按钮三态：`idle`=开始解密(PLAY)、`running`=停止(CANCEL)、`stopping`=正在收尾(SYNC)。`signalBus.conversion_started` 改为 `Signal(int)` 携带任务总数以计算进度。
- **设置页「覆盖已转换」开关**：新增「任务行为」分组 + `SwitchSettingCard`（绑定 `cfg.reconvert_done`，默认关闭）。开启则**解密全部加密文件**（无论是否已解密）；关闭则**仅解密未解密文件**并提示跳过数量。
- **InfoBar 浮层提示**：`signalBus.toast_requested = Signal(str, str)`。覆盖：未找到 `um.exe`（error）、无待解密文件（warning）、**单文件解密失败**（error，跳过并继续）、**整批结束汇总**（全成功 success / 有失败 warning）、用户停止（warning）。`home_interface._show_toast` 支持 `success→InfoBar.success`。
- **启动工具链检测日志**：启动即检测三个 exe，并在运行日志页逐条输出 `工具监测 um.exe/ffmpeg.exe/qmpc-mmkv-cli.exe: 版本 (就绪/缺失)`。
- **loguru 双轨日志**：`app.log` 记录全量细节（`{name}:{function}:{line}`），UI 日志页只显示处理结果（成功/失败），启动命令等细节只写 `app.log`。
- **qmpc 秘钥兜底**：新增 `qmpc_path` 配置项；仅对 QQ 音乐加密格式（`mgg/mflac/qmc*/tkm/tm0` 等）追加 `--qmpc-mmkv-cli-exe` 参数，缺失秘钥时兜底。
- **Nuitka 感知的项目根目录**：`config._detect_project_root()`——打包后（`__main__.__compiled__`）取 `sys.executable.parent`，开发模式取 `__file__` 的 `parents[2]`；`resource.py`、`logger.py` 改为复用该单点，修复打包后三个 exe 找不到的根因。
- **config.json 首次运行自动生成**：无配置文件时按当前值生成默认配置并落盘——输入/输出目录为空、三个 exe 自动指向 `app/resources/`、其余取默认；内置 exe 探测改为内存覆盖（`save=False`）+ 单次显式生成，避免启动重复写盘、不覆盖用户已存目录。
- **文件名跑马灯（悬停滚动）**：新增 `app/components/marquee_label.py` `MarqueeLabel`；文件名过长时**鼠标悬停整张卡片**才从左往右滚动展示完整名称，离开即停止并复位；放得下则静态。卡片内容控件设鼠标透明，使整卡成为悬停目标。
- **「已解密」侧边栏页面**：新增 `app/view/decrypted_interface.py` 并在 `main_window` 导航注册（位于「任务管理」后，图标 `FluentIcon.COMPLETED`）。仿任务管理卡片网格展示**输出目录**中已解密文件：文件名跑马灯（悬停滚动）+ 大小/时间 + **来源徽章**（由本工具从加密输入解密产生 →「已解密」绿；输出目录原本就有、不对应任何加密输入 →「已添加」**黄**，由 `decrypt_scanner.output_source_label` 按「去后缀基名是否命中加密输入」判定）；计数显示 `已解密 X · 已添加 Y · 共 N`；顶部分类下拉框（全部/已解密/已添加）+ 搜索栏双重过滤；网格均分、列宽等宽、贴顶排布；**右键卡片**弹出菜单——**播放音乐**（`QDesktopServices` 调用默认播放器）与**删除文件**（确认框后删除并移除卡片）；支持「刷新列表 / 打开目录」；输出目录变更或一批解密结束自动刷新；按修改时间倒序；**只扫描常见音乐文件类型**（`utils.is_music_file`：mp3/flac/m4a/ogg/wav/wma/aac/opus/ape/aiff/wv/m4b 等，跳过封面/非音乐）；未设输出目录/空目录有空状态提示。
- **任务管理卡片右键菜单**：任务卡右键弹出两项——**删除文件**（确认框后从磁盘删除并移除卡片，刷新不再出现）与**移出列表**（仅移出列表、不动磁盘文件；因文件仍在输入目录，刷新后会重新出现）。解密只处理当前列表内文件，故已「移出列表」的文件本轮不被管理。
- **build.py standalone 打包增强**：`glob` 通配 `app/resources/*.exe` 逐个 `--include-data-file`，`img` 子目录单独 `--include-data-dir`，无 exe 时给出警告。
- 新增 `启动程序.bat`（`uv run main.py` 快速启动）。

### 变更

- **`config.json` 合并为单文件**，删除 `config/` 遗留目录。
- **三个 exe 优先自动检测内置版本**：`app/resources` 内 exe 存在则运行时覆盖为内置工具；内置缺失时回退占位路径。
- **首页精简**：去掉主标题 / 副标题 label，Banner 后直接进入工具检测区；`AutoResizeFlipView` 在 `resizeEvent` 中 `setItemSize(self.size())`，修复全屏时 Banner 右侧露馅。
- **工具检测卡一行两个**（um+ffmpeg / qmpc）：`QGridLayout` + `setColumnStretch` 强制等宽、上下左右严格对齐；卡高统一 `64px`，与目录卡一致；以功能描述文案替代 path 显示。
- **任务卡网格均分**：`FlowLayout` → `QGridLayout`，列数随视口宽度自适应，卡片拉伸填满整行；固定高 `64px` + 单行省略号，修复重叠与右侧空白。
- **任务卡副标题**：只显示 `大小 · 修改时间`，去掉路径显示。
- **扫描目录不遍历子目录 + 只纳入加密文件**：`os.listdir` 只扫当前目录；明文音频等非加密文件**跳过**（不再进入列表），仅加密音乐文件纳入。
- **转换/解密过程不再整页重排**：`file_started / file_finished` 仅更新对应卡片徽章与右上角计数（`_update_count()`），不再调用 `_relayout()` 排序/重建网格——过程中卡片顺序与网格位置保持不变。排序仅保留在新增 / 刷新 / 移除 / 清空 / 窗口 resize 等离散动作。
- **任务卡徽章防闪烁**：`set_status` 重建徽章前先 `hLayout.removeWidget(旧)` 再 `deleteLater`，避免新旧徽章同帧叠加。
- **卡片贴顶填充**：列表网格不再加 stretch（否则固定高卡片垂直漂浮、上方大片空白），改由底部 stretch 吸收剩余空间。
- **网格列宽强制等宽**：`_relayout` 为当前所有列设相同 stretch（带复位防幽灵列），长文件名不再把所在列撑宽。
- **徽章去留白**：文件名区拉伸填满、徽章按自然宽度贴右，取消固定 1/5 造成的徽章右侧空白。
- **恢复工具栏按钮图标**（`FluentIcon.ADD/SYNC/DELETE/BROOM`）：`FluentIcon` 走内置 SVG，无需系统字体；按钮文案「移除完成」→ **「删除完成后」**。
- **目录卡**：路径单行省略号 + 固定高 `64px`，边距微调。

### 修复

- **转换中移除/删除排队文件未同步到转换队列**：任务页对排队中的文件「移出列表 / 删除文件 / 清空 / 移除已完成」时，此前仅移除卡片而未从 `converter.pending_files` 剔除，导致到达时仍处理（违背「解密不管理已移出列表的文件」）或对已删文件报错。新增 `signalBus.queue_remove`，移除卡片时同步从待处理队列剔除；`_start_next_file` 增加「文件不存在则跳过（不计失败、仍推进进度）」的防御，覆盖外部删除/竞态。
- **术语统一（转换 → 解密）**：补齐用户可见字符串——首页按钮（含构造默认值）、设置页「覆盖已转换」描述、converter 启动失败日志；`utils.simplify_process_line` 的「解密成功/失败」。检测关键字（successfully converted 等）保留匹配 um 输出。
- **`tool_detector` 版本回退更诚实**：取版本无匹配/异常时由假 `v0.0.0` 改为 **「版本未知」**（文件仍在仍算就绪）。
- **`SingletonApplication` 单实例锁**：由占位改为真正实现——Windows 命名互斥体，检测到已有实例则 `main` 弹提示并退出（非 Windows / 取锁失败则退回允许多开）。
- **已解密页不再漏显**：输出目录改为列出**全部常规文件**，去掉 `is_supported_file` 过滤（避免 um 输出集合外格式时不显示）。
- **单文件出错不再中断整批**：非零退出码 / 进程崩溃只跳过该文件、记录失败、继续后续解密（原 `Crashed` 会 `pending_files.clear()` 中断整批）；并用 `_handled` 守卫处理 Qt「崩溃时 `errorOccurred(Crashed)` 与 `finished` 双信号」的重复收尾。
- **跑马灯 sizeHint 撑宽网格列**：`MarqueeLabel.sizeHint` 返回完整文本宽，导致长文件名卡片把所在列撑宽、列宽不一致；改为水平策略 `QSizePolicy.Ignored`（sizeHint 不参与布局分配，控件仍拉伸填满并在其内滚动）。
- **`SwitchSettingCard` 参数顺序错误导致启动崩溃**：`icon / title / content / configItem / parent` 槽位写反，把 `ConfigItem` 传进了 icon 槽，触发 `IconWidget.__init__()` 参数个数错误。
- **`request_start` 双重连接**：converter 直连 `start` 与 `MainWindow._dispatch_start` 重复触发，空队列时弹假警告；改为统一由 `_dispatch_start` 分发。
- **`_check_qmpc` 版本读取**：帮助信息输出在 stderr，改 `res.stderr or res.stdout`，修复版本恒为 `v0.0.0`。
- **`waitForStarted` 启动失败**：改用 `QTimer.singleShot(0, ...)` 进入下一文件，避免递归阻塞 UI；`_on_process_error` 新增 `FailedToStart` 与通用分支，不再吞没进程错误。

### 移除

- 首页主标题 / 副标题 label。
- `request_start` 到 `converter.start` 的直连（避免双重触发）。
- 工具检测卡上的 path 文本显示。
- **`completion` 完成台账**（`app/common/completion.py` 及 `app/completion.json`）：已解密判定改为**输入/输出目录「去后缀」比对**，不再需要持久化台账；converter 的 `mark/forget` 一并移除。
- **死代码清理**：移除未使用的 `VersionCardView`（及其 `FlowLayout`/`QWidget` import）、`compact_path`、`LogInterface.clear_log`、`files_changed` 信号（emit 无接收方）。

---

### 待同步 / 说明

- ~~README 与实现存在不一致~~：已于 2026-11-05 同步——「文件管理」改为**不遍历子目录**并区分**加密格式**（纳入解密）与**明文音频**（跳过）；补齐已解密页（懒加载）、日志页着色/清空、`grid_card_container.py` / `decrypted_interface.py` / `decrypt_scanner.py` / `marquee_label.py` 等结构与信号说明。
- 上述改动均在工作区**未提交**；远端推送仍受代理未运行限制。
