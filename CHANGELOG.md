# 更新日志

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 规范。
版本号语义见 `pyproject.toml`（当前 `0.1.0`）。

---

## [未发布] - 2026-10-22

### 变更

- **跑马灯效果优化**（`app/components/marquee_label.py` 重写）：
  - **首尾相连无缝循环**——内部持两份相同文本，滚动偏移在「文本宽 + 48px 间距」周期内取模：第二份恰好在第一份完全滚出视区时接替，回绕即一帧之差的正常滚动，**无跳变、无停顿**；相邻两份间距恒定 48px，未滚动时第二份隐藏只显示一份。
  - **启动提速**——悬停起始延迟 0.35s → **0.15s**，并加 0.15s 起步加速（速度 50%→100% 平滑升起），约 **0.30s 达到全速**（原约 1.15s）。
  - 保留时间驱动（`QElapsedTimer`，16ms≈60fps + `PreciseTimer`）与 110px/s 全速；`_MAX_DT` 钳制单帧步长防卡顿跳跃；resize 时 offset 钳制回周期内；`hideEvent` 停表复位。
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

- **README 与实现存在不一致**：README「文件管理」仍写「刷新（递归子目录）」，而扫描已改为**不遍历子目录**（仅当前目录）；且「支持格式」应区分**加密格式**（纳入解密）与**明文音频**（跳过）。后续更新 README 时需同步。
- 上述改动均在工作区**未提交**（相对 `5a8e8bd`）；远端推送仍受代理未运行限制。
