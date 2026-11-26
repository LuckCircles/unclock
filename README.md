# unclock

基于 PySide6 + QFluentWidgets 的 [Unlock Music](https://git.um-react.app/um/cli)（`um`）图形化前端，面向 Windows 平台。提供文件管理、批量转换、实时日志、可视化配置，以及带内嵌专辑封面与详细元数据的已解密音乐库。界面统一采用官方 Fluent 组件与主题色，支持跟随系统 / 浅色 / 深色三种主题。

## 功能

- **主界面**：Banner 轮播、`um` / `ffmpeg` / `qmpc-mmkv-cli` / `um-cli-rs` 四张工具检测卡片（版本 + 功能描述 + READY/MISS 状态徽章）、输入/输出目录快捷卡片、进度条 + 开始/停止合并按钮。启动时检测在后台线程执行，不阻塞窗口；`SingletonApplication` 保证单实例。
- **双解密引擎**：设置页选择 `um`（Go 版原链路，支持格式最广，默认）或 `um-cli-rs`（官方 Rust 流程：`-I` 探测 JSON → 密钥解析 → 二次解密，覆盖 NCM / KGM / KWM / QMC2）；两引擎共用同一队列、并发调度与对外信号，ui 其余部分零差异。详见 [um-使用文档.md](docs/um-使用文档.md) 与 [um-cli-rs-使用文档.md](docs/um-cli-rs-使用文档.md)。
- **文件管理**：受支持格式列表（`ncm` / `qmc*` / `kgm` / `mgg` / `mflac*` / `vpr` / `x2m` 等加密音乐格式纳入解密；明文 `mp3/flac/ogg/wav/m4a` 等跳过），支持添加、拖入（文件或目录，目录取顶层）、刷新（仅当前目录，不遍历子目录）、删除完成后、清空列表、直接开始解密；卡片状态徽章（待解密/解密中/已解密/失败/已跳过）与实时状态分布计数。**列表按状态排序**：未解密在上、已解密沉底，整批转换结束后自动重排。
- **已解密页**：卡片网格展示输出目录全部音乐文件，来源徽章（本工具解密产生 →「已解密」绿；输出目录原有 →「已添加」黄）。
  - **内嵌专辑封面**：卡片最左侧 44×44 圆角封面，FLAC/MP3 直接读标签块（毫秒级、零进程），其它格式回退 `ffmpeg`；读不到时回退占位图，随主题切换刷新。
  - **分类 + 搜索**：下拉支持 `全部 / 已解密 / 已添加 / 歌手名 / 专辑名`；后两项按标签**归类**——同一歌手/专辑的文件排在一起，读不到信息的排末尾。搜索框按文件名过滤（120ms 防抖）。
  - **右键菜单**：查看信息 / 播放音乐 / 删除文件。
  - **元数据**：封面由标签块直读，音频信息仍由一次 `ffmpeg` 探测；结果写入封面 LRU、`_tags`、`_media_info` 三份缓存，供归类与信息弹窗复用。
- **文件信息弹窗**：Fluent `MessageBoxBase`，14 行键值信息（文件名、完整路径、大小、修改时间、来源、格式、时长、编码、采样率、声道、码率、标题、艺术家、专辑）。左列右对齐、右列左对齐，列宽 2:3；**所有值单行显示**，仅当文本溢出右列时才自动跑马灯滚动，不换行堆高，14 行统一行高。完整路径带强调色与手型光标，点击在文件管理器中定位选中；悬停显示 Fluent `ToolTip`。
- **运行日志**：实时解析并展示 `um` 进程输出，按级别着色（INFO/WARN/ERROR/SUCCESS，明暗主题自适应），右上角图标按钮一键清空。
- **配置界面**：
  - **外观设置**：主题下拉（跟随系统 / 浅色 / 深色），与转换设置统一采用 `ComboBoxSettingCard`。
  - **基础设置**：**解密工具选择**（`um` 原链路 / `um-cli-rs` 官方 Rust 流程，`ComboBoxSettingCard`，按选择启用对应路径卡）、输入/输出目录、`um.exe` / `ffmpeg.exe` / `qmpc-mmkv-cli.exe` / `um_cli_rs.exe` 路径（`PushSettingCard`，按钮带 Fluent 提示）。
  - **转换设置**：删除源文件 `--rs`、详细输出 `-V`、覆盖输出 `--overwrite`、监听输入目录 `--watch`、更新封面 `--update-metadata`、跳过无动作解码器 `-n`，均为「否 / 是 / 默认」三态。`um` 未提供这些参数的关闭形式，选「否」时不传参、仍按 um 默认执行（界面已明示）。
  - **任务行为**：「覆盖已转换」开关（`SwitchSettingCard`），开启后重新解密已成功的文件，关闭则自动跳过、仅处理待解密/失败项。
- **主题链路**：`qconfig.themeMode` 选项重排为 `AUTO / LIGHT / DARK`；手动切换经 `setTheme()` 刷新全局 QSS；「跟随系统」由 `SystemThemeListener` 监听系统深浅色变化并触发 `setTheme(Theme.AUTO)` 实时换肤。深色模式下列表容器关闭 `autoFillBackground`，避免浅底白字。

## 性能设计

千级文件下仍保持流畅，关键机制与 offscreen 实测数据（基准脚本已清理，数据见 `CHANGELOG.md`）：

| 场景 | 机制 |
| --- | --- |
| 懒加载网格 | 仅视口内 + 上下各 2 行预载真实建卡，其余用 `QSpacerItem` 占位；占位格与卡片行 stride 统一，内容高度不漂移 |
| 重排 / 搜索 | 视图与列数未变时短路；保留 parent 摘挂、占位格池、卡片复用池；视口外卡片回收；搜索 120ms 防抖 + 小写文件名缓存 |
| 专辑封面 | 视口可见项优先的**双队列**（urgent / normal）+ 最多 2 个在途元数据探测；FLAC/MP3 封面直读标签块不占进程，新进入屏幕的封面最多等 1 个任务即可插队；专用线程池不与转换/扫描抢线程 |
| 淡入动画 | 刷新后列表回到顶部、自上而下错峰淡入；单个 `QVariantAnimation` 批量驱动、按绝对时间补发节拍、滚动时收敛在途动画并卸载 effect |

| 指标（offscreen 基准） | 优化前 | 优化后 |
| --- | --- | --- |
| 视图未变全量重排 @1000 | 97 ms | 0.38 ms |
| 连续输入 6 字符 @1000 | 526 ms | 3.38 ms |
| 滚到底常驻卡片 | 876 张 | 约 60 张 |
| 滚动全程真实建卡 | 956 次 | 32 次 |
| 在途淡入动画峰值 | 28 个 | 2 个 |

> offscreen 绝对耗时含事件循环、绘制与 Fluent 事件，不作为用户态帧耗时的唯一指标。在途的元数据探测不可取消，故「可见优先」语义为最多等 1 个任务完成。

## 技术栈

| 依赖 | 版本 / 说明 |
| --- | --- |
| Python | `>=3.12`（`.python-version` 固定 3.12） |
| PySide6 | `>=6.11.0` |
| PySide6-Fluent-Widgets | `>=1.11.2` |
| loguru | `>=0.7.3` |
| Nuitka | standalone 多文件目录打包 |
| 外部可执行 | `um.exe`、`ffmpeg.exe`、`qmpc-mmkv-cli.exe`、`um_cli_rs.exe`，**已随仓库附带于 `tools/`** |

> `ffmpeg.exe` 用途：转换时供 `um` 更新封面/元数据；已解密页用它读取音频信息，并为不可识别格式兜底提取封面。FLAC/MP3 封面直读标签块，零新增 Python 依赖；打包版保留 `qjpeg.dll` 以解码原始 JPEG 封面。

## 快速开始

```bash
# 安装依赖（推荐 uv）
uv sync

# tools/ 下四个 exe 已随仓库附带，无需另外下载；
# 如需换版本，直接覆盖同名文件即可（程序启动时自动探测并填入默认路径）

# 启动
uv run python main.py
# 或：.venv/Scripts/python.exe main.py
```

首次运行会自动生成 `config.json`（输入/输出目录留空，四个 exe 指向 `tools/`），该文件已被 `.gitignore` 忽略。

## 打包

```bash
# 预编译 qrc 资源 + Nuitka standalone 多文件目录打包
uv run python build.py
# 等价：.venv/Scripts/python.exe build.py

# 产物：releases/main.dist/音乐解锁工具.exe（内嵌四个 exe）
```

目录名由入口脚本决定（`main.py` → `main.dist`），`--output-filename` 只改 exe 文件名。打包产物不纳入版本管理，仓库不附带预编译程序。

## 项目结构

参照 [Fluent-M3U8](https://github.com/zhiyiYo/Fluent-M3U8) 的分层设计，按 `common / components / service / view / resource` 五层组织：

```
unclock/
├── main.py                       # 薄入口：屏蔽推广输出 + 单实例 + Application + MainWindow
├── build.py                      # Nuitka standalone 打包脚本
├── CHANGELOG.md                  # 更新日志（Keep a Changelog 风格）
├── tools/                        # 外部可执行工具（已随仓库附带，启动时自动探测）
│   ├── um.exe                     #   Unlock Music CLI（Go 版，当前解密引擎）
│   ├── ffmpeg.exe                 #   FFmpeg（转换 + 封面/元数据探测）
│   ├── qmpc-mmkv-cli.exe          #   QQ 音乐 MMKV 密钥提取
│   └── um_cli_rs.exe              #   um-cli-rs（Rust 版，官方 GUI 的解密核心；首页卡片检测展示）
├── docs/
│   ├── qmpc-mmkv-使用教程.md
│   └── 已解密列表-内嵌专辑封面可行性分析.md
├── app/
│   ├── resource.qrc               # 图片资源清单（含 icon.svg；编译为 resource_rc.py）
│   ├── resource_rc.py             # qrc 编译产物（:/img/ 访问）
│   ├── resources/img/icon.svg     # 窗口图标源图；build.py 据此生成打包用多尺寸 ico
│   ├── common/                    # 基础设施层（不依赖任何 UI 层）
│   │   ├── application.py          #   SingletonApplication（Windows 命名互斥体单实例）
│   │   ├── config.py               #   QConfig + 全局 cfg + 转换选项元数据 + 主题选项重排
│   │   ├── signal_bus.py           #   全局信号总线（解耦 view ↔ service）
│   │   ├── logger.py               #   loguru 配置
│   │   ├── resource.py             #   资源路径常量
│   │   ├── icon.py                 #   FluentIcon 别名
│   │   ├── decrypt_scanner.py      #   已解密判定（输入/输出目录「去后缀」比对）
│   │   ├── cover_loader.py         #   FLAC/MP3 标签块封面直读 + ffmpeg 兜底 + 保存时转 PNG + 线程安全 LRU
│   │   ├── media_info.py           #   ffmpeg 元数据探测 / 封面+标签汇总 / 文件名回退歌手
│   │   └── utils.py                #   受支持格式 / 路径压缩 / 进程输出解析 / 打开所在位置
│   ├── components/                # 可复用 UI 组件层（只依赖 common）
│   │   ├── interface.py            #   页面基类 Interface(ScrollArea)（sticky 工具栏）
│   │   ├── grid_card_container.py  #   卡片页骨架：固定工具栏 + 滚动网格（懒加载 / 池化 / 淡入调度 / 可见项钩子）
│   │   ├── version_card.py         #   工具版本卡片 + 流式容器
│   │   ├── path_card.py            #   主页目录快捷卡片
│   │   ├── task_card.py            #   任务卡片（状态徽章、元数据、可选封面位、文件名跑马灯）
│   │   ├── marquee_label.py        #   无缝跑马灯（悬停 / 自动双模式、溢出才滚、可染色）
│   │   ├── file_info_dialog.py     #   文件信息弹窗（14 行单行值、路径点击定位、Fluent 提示）
│   │   └── empty_status.py         #   空状态提示（表情卡片 + 文案）
│   ├── service/                   # 业务服务层（只依赖 common，经 signalBus 广播，不 import view）
│   │   ├── tool_detector.py        #   检测 um / ffmpeg / qmpc-mmkv-cli / um_cli_rs 版本（后台线程）
│   │   ├── task_planner.py         #   工具路径解析、并行数规则、claim / lane 任务规划
│   │   ├── rust_decrypt.py         #   um-cli-rs 官方流程：子命令映射 / -I 探测 / 密钥解析 / 落盘
│   │   └── converter.py            #   UnlockMusicConverter：双引擎批量队列 + QProcess + 超时 + 事件广播
│   ├── resources/img/              # 图片资源（qrc 引用）
│   └── view/                      # 界面层（仅 MainWindow 持有 service 实例）
│       ├── main_window.py          #   MSFluentWindow 主窗口 + SystemThemeListener 系统主题跟随
│       ├── home_interface.py       #   首页（banner + 工具检测 + 路径卡片 + 启动按钮）
│       ├── task_interface.py       #   任务管理（状态排序、拖入/右键/状态联动）
│       ├── decrypted_interface.py  #   已解密（懒加载网格 + 封面/标签探测可见优先调度 + 归类 + 搜索 + 右键）
│       ├── log_interface.py        #   运行日志（级别着色 + 清空）
│       └── setting_interface.py    #   配置界面（外观 / 基础 / 转换 / 任务行为）
├── pyproject.toml
└── uv.lock
```

### 分层与通信

- **严格单向依赖**：`common → components / service → view（MainWindow 为装配根）→ main.py`；`service` 只经 `signalBus` 广播、不得 import `view`，跨层依赖违规数保持 0。
- **view ↔ service 解耦**：view 通过 `signalBus.request_start / request_stop` 驱动服务，service 反向经 `signalBus` 广播事件——`conversion_started`（含总数）、`file_started`、`file_finished`、`file_cancelled`（用户停止时标记被取消的文件）、`log_emitted`、`conversion_finished`、`tools_detected`（`ToolsReport` dataclass 载荷）；view 监听这些信号更新 UI，双方互不持有引用。
- **MainWindow 协调**：首页「开始」按钮 → `request_start` → MainWindow 从 TaskInterface 取文件列表交给 `UnlockMusicConverter.start(files)`；单文件超时（120s）自动 kill 并按失败收尾。
- **样式策略**：以官方 Fluent 组件、主题色与 `themeChanged / themeColorChanged` 信号为主；仅在跑马灯文本染色、拖拽高亮等极少数位置使用局部 `setStyleSheet()`，无全局自定义 QSS 文件。
- **主题切换**：`setTheme()` 负责刷新全局样式表；`SystemThemeListener` 仅在 `themeMode == AUTO` 时发出 `systemThemeChanged`，主窗口接到后再次 `setTheme(Theme.AUTO)` 完成实时换肤，退出时幂等停止监听线程。

### qmpc-mmkv-cli 集成

`qmpc-mmkv-cli.exe`（LSR@UnlockMusic；本机 `1.0.4`）用于从 QQ Music 的 MMKV 存储中自动提取解密密钥。两条引擎路径都会用到它：`um` 引擎自动附加 `--qmpc-mmkv-cli-exe`；`um-cli-rs` 引擎仅在 `qmc2 -I` 得到 `MusicEx` 且无内嵌 ekey 时，直接调用 `qmpc-mmkv-cli -o - -f plaintext -F <媒体文件名>`（exit=5 重试 5 次）。详细说明见 `docs/qmpc-mmkv-cli-使用文档.md` 与 `docs/qmpc-mmkv-使用教程.md`。

### 官方 um-conv 工具链设计参考

官方 GUI（[um-conv](https://git.um-react.app/um/um-conv)）的工具分工与本项目不同，仅作设计参考：

- **Go 版 `um`**：单体编排器，一条命令完成解密、密钥库查询、输出与可选的网络元数据更新；本项目默认引擎。
- **Rust 版 `um-cli-rs`**：纯离线解密原语，按 `ncm` / `kgm` / `kuwo` / `qmc2` 等子命令工作；`-I/--info-only` 先输出 JSON 探测结果（含 `metadataType`、`ekey`、伪装 `.flac` 识别），再由宿主决定是否调用 `qmpc-mmkv-cli` 或 ADB 取密钥并二次解密。本项目已按此流程实现为可选引擎；ADB 相关密钥（QMC STag / 酷我 v2）暂未接入。
- **`ffmpeg`**：官方用 `-encoders` 缓存音频编码器列表并按 `libfdk_aac → aac`、`libopus → libvorbis` 自动降级；`-progress pipe:1` 做转码进度。本项目仍只用它做封面/元数据探测、Rust 产物格式识别与 um 子进程 PATH 注入，尚无输出编码器预设。

## 文档

| 文档 | 内容 |
| --- | --- |
| [CHANGELOG.md](CHANGELOG.md) | 按需求逐条记录改动、根因、方案、验证数据与踩坑 |
| [docs/um-使用文档.md](docs/um-使用文档.md) | Go 版 um 的命令行选项、支持格式与本项目集成方式 |
| [docs/um-cli-rs-使用文档.md](docs/um-cli-rs-使用文档.md) | Rust 版解密工具的子命令、`-I` 探测 JSON、密钥分流与本项目集成 |
| [docs/qmpc-mmkv-cli-使用文档.md](docs/qmpc-mmkv-cli-使用文档.md) | MMKV 密钥提取工具的命令行参数与两条引擎调用路径 |
| [docs/qmpc-mmkv-使用教程.md](docs/qmpc-mmkv-使用教程.md) | QQ 音乐 MMKV 密钥提取原理与深度排错 |
| [docs/已解密列表-内嵌专辑封面可行性分析.md](docs/已解密列表-内嵌专辑封面可行性分析.md) | 内嵌封面方案评估（原结论 ffmpeg + QImage；2026-11-26 已按 B 方案升级为标签块直读） |

## 运行时文件

下列文件由程序运行时生成或属本地环境，已通过 `.gitignore` 忽略、**不纳入版本管理**：

| 文件 / 目录 | 用途 |
| --- | --- |
| `config.json` | QFluentWidgets `QConfig` 持久化的路径、转换选项与主题模式 |
| `app.log` | loguru 写入的运行日志（5MB 轮转） |
| `releases/` | Nuitka 打包产物目录（`main.dist/`） |
| `.venv/` | 本地虚拟环境 |
| `__pycache__/` | Python 字节码缓存 |
| `.workbuddy/` | 本地工作区数据（记忆、日志） |

> 如需共享配置，请基于 `config.json` 自行另存为 `config.example.json`（`.gitignore` 已放行 `!*.example.json`）。

## 许可证

见 [LICENSE](LICENSE)。
