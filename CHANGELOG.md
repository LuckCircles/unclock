# 更新日志

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 规范。
版本号语义见 `pyproject.toml`（当前 `0.1.0`）。

---

## [未发布] - 2026-11-05

### 新增

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

### 修复

- **空状态提示闪现**：首次进入已解密页时，卡片渐进填充尚未开始，`_update_count` 先按「0 个文件」把居中空提示画了出来，首批卡建完又隐藏——视觉上「先悬浮中部、再跑到置顶」。新增 `_filling` 状态在填充期间强制隐藏空提示，填充结束按真实状态刷新；任务页目录不存在的提前返回路径同样正确解除抑制。

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
