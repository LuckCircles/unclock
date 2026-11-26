# 更新日志

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 规范。
版本号语义见 `pyproject.toml`（当前 `0.1.0`）。

---

## [未发布] - 2026-11-09

> **呈现契约反转（用户 2026-11-09 明确圈定）**：本节取代下方 2026-11-05/11-06
> 「刷新 = 屏幕闪一次、卡片位置与内容均不变」的契约。新契约为
> **「刷新后列表回到顶部，卡片从第一张开始自上而下逐张刷新」**。

### 变更：新增解密引擎选择（um / um-cli-rs）与三份工具文档（2026-11-26）

**需求**：设置页增加解密工具选择；选 `um-cli-rs` 时按官方工具流程解密，选 `um` 时链路不变；在 `docs/` 生成除 ffmpeg 外三个工具的使用文档。

| 文件 | 改动 |
|---|---|
| `app/common/config.py` | 新增 `decrypt_engine`（`um` / `um-cli-rs`，默认 `um`） |
| `app/common/rust_decrypt.py`（新增） | 纯逻辑：后缀→子命令、`prepare_rust_job` 临时目录与 NCM 官方参数、`parse_probe`、`decrypt_args_for`（QMC2 PCv1/QTag/MusicEx/STag 分流、KGM v2/3/v5、KWM v1/v2）、qmpc 取 ekey（exit=5 重试 5 次）、KGM 加密 DB 借 um-cli-rs 解到临时 SQLite 后读 `ShareFileItems`、ffmpeg 探测真实 demuxer 后原子落盘 |
| `app/service/converter.py` | 按 `decrypt_engine` 分派：preflight 校验所选引擎；`_prepare_job` / `_launch_process` 支持 probe→decrypt 两阶段续启；`-I` 输出含 ekey 只缓存不写日志；Rust 路径的跳过/删除源文件/临时目录清理；`um` 分支参数构造与行为保持不变；对外信号签名全部不变 |
| `app/view/setting_interface.py` | 基础设置新增 `ComboBoxSettingCard`「解密工具」，切换时启用对应工具路径卡；`um-cli-rs` 路径卡提示改为引擎路径 |
| `docs/um-使用文档.md`、`docs/um-cli-rs-使用文档.md`、`docs/qmpc-mmkv-cli-使用文档.md`（新增） | 基于 `--help` 实测与官方源码的三份中文文档 |
| `README.md` | 同步双引擎说明、目录结构、qmpc 两条调用路径与文档索引 |

**边界**：Rust 引擎只覆盖官方支持的 NCM / KGM / KWM / QMC2；QMCv1 与 BKC 等格式明确提示切回 um。ADB 密钥（QMC STag / 酷我 v2）未接入，遇此情况报错并跳过该文件。

**验证（源码级，未执行打包命令）**：
- 真实文件端到端：NCM 1.3s 输出 80,941,963 字节 FLAC；QMC2 `.mflac` 0.2s 完成 `-I` 探测 + 带 ekey 解密，输出 28,511,721 字节 FLAC；两者 `conversion_finished=0`，日志无 ekey 泄露。
- `um` 分支回归：假 um 脚本收到原样 `-i/-o/-n` 参数，三态「否」提示仍在；不支持格式给出切回提示；所选引擎缺失时 preflight 立即 `conversion_finished(-1)`。
- 设置页组件：两项文本与配置值顺序一致，切换后仅对应路径卡可用；`py_compile` 通过；跨层依赖违规 0；`build_command()` 静态确认四个 exe 内嵌；离屏启动 8 秒无 Traceback。
- 测试期间设置页控件把新键写进了 `config.json`，已按原内容恢复（原键顺序与值未变）。

### 变更：官方工具链算法分析 + 首页新增 um-cli-rs 卡片（2026-11-26）

**需求**：参考官方 `um-conv` 的 mmkv 密钥提取、`um-cli-rs`、`ffmpeg` 与 AAC/OGG 编码器逻辑，并把 `um-cli-rs` 卡片加到首页。**解密引擎未切换，仍是 Go 版 `um.exe`**；本次只做设计分析 + 检测卡片。

| 文件 | 改动 |
|---|---|
| `app/common/config.py` | 新增 `um_cli_rs_path`（默认 `tools/um_cli_rs.exe`）并纳入启动自动探测；首次运行生成的配置说明由「三个 exe」改为「四个 exe」 |
| `app/service/tool_detector.py` | `ToolsReport` 扩为四项，新增 `_check_um_cli_rs()`：`-V` / `--version` 解析 `um_cli_rs 0.1.13`；运行日志同步增加一行 |
| `app/view/home_interface.py` | 首页新增第四张 `um-cli-rs` 卡片（2×2 网格），官网指向 `lib_um_crypto_rust/releases`；图标复用 qrc 中的 `icon.svg` |
| `app/view/setting_interface.py` | 基础设置新增 `um-cli-rs 路径` 选择卡与 Fluent 提示 |
| `build.py` | 预检清单加入 `um_cli_rs.exe`；`tools/*.exe` glob 已自动内嵌该 exe，无需改打包参数 |

**官方算法结论（仅借鉴，未移植）**：
- `qmpc-mmkv-cli -o - -f plaintext -F <媒体文件名>` → stdout 双行键值交替解析；仅用于 QMC2 `MusicEx` 且文件未内嵌 ekey 时；exit=5（CRC/read-on-write）重试 5 次，密钥查询用互斥锁串行——与本项目「QMC 单独 lane」一致。
- `um-cli-rs` 每个平台一个子命令，`-I/--info-only` 先输出 `footerLen/ekey/metadataType/musicexMediaFilename` JSON 再决定是否取外部密钥；`qmc2 --ekey … --output … -- <src>` 完成解密。Go 版 `um` 是单体编排器（含网络元数据与 `--watch`），Rust 版是纯离线原语。
- `ffmpeg`：`-version` 取版本 + `-encoders` 懒加载缓存编码器；`ffmpeg -i file:<path>` 无输出时 rc=1，用 demuxer 名推断真实扩展（`.webm` 特判）；`-progress pipe:1` + `out_time_us` 算百分比。AAC 自动选 `libfdk_aac → aac`，OGG 选 `libopus → libvorbis`；FDK 可开 VBR，否则按高/中/低 256/192/128k（OGG Opus 192/128/96k、Vorbis q8/6/4）。

**验证（源码级，未执行打包命令）**：四工具真实检测全部就绪（`um v0.2.20` / `ffmpeg 8.1.3-Jellyfin` / `qmpc 1.0.4` / `um_cli_rs 0.1.13`）；缺失路径分支显示「未找到 + MISS」；离屏实例化首页/设置页确认第四张卡片与路径卡、图标非空、网格位置 (1,1)；`build_command()` 静态确认四个 exe 均内嵌且 SVG 插件未被排除；`py_compile` 通过、跨层依赖违规 0、离屏启动 8 秒无 Traceback、`config.json` 未写回。

### 变更：借鉴官方解密交互算法（后端调度，UI 零改动）（2026-11-26）

**需求**：「借鉴解密交互算法，不改ui。」只改 `common` / `service`，沿用现有全部信号与界面。

| 文件 | 改动 |
|---|---|
| `app/common/task_planner.py`（新增） | `resolve_executable()`（绝对路径校验 / 内置 tools → PATH 兜底）、`resolve_parallel()`（官方规则：关闭→1、≤0→CPU 核数、上限 256）、`build_decrypt_plan()`（一次扫描完成 claim / 去后缀基名 / lane 标记；QMC 密钥查询归入同一串行 lane，同名输出同样串行） |
| `app/common/config.py` | 新增 `parallel_enabled`（默认 `False`）与 `parallel_count`（默认 `0`）两个**无 UI 入口**配置项，可在 `config.json` 手动开启 |
| `app/service/converter.py` | 重写为 preflight → plan → worker pool：工具解析失败即停；受控并发且 lane 互斥；`generation` 丢弃旧轮回调；优雅停止（未领取任务 `file_cancelled`，在飞任务跑完再统一收尾）；Windows 子进程设 `IDLE_PRIORITY_CLASS`；结束汇总改为官方风格「已处理 x/y，成功 a，跳过 b，错误 z，取消 d」 |

**验证（源码级，未执行打包命令）**：
- 真实 `um -v` / 工具路径解析、串行默认与并发开关、QMC lane 串行、优雅停止、preflight 缺工具、旧 generation 回调守卫均实测通过。
- 5 个任务开 4 worker 时实际收敛为 3 条 lane、3 个并发 worker；3 个 QMC 任务互不重叠。停止时 2 个在飞任务正常写出结束标记，2 个排队任务收到 `file_cancelled`，`conversion_finished` 仅一次。
- 外部信号签名与 UI 文件零改动；`config.json` 未被写回。

### 变更：窗口标题/图标统一为 icon.svg，移除封面说明标签（2026-11-26）

**需求**：截图中的「内嵌封面 · 800 × 800」标签不要；标题去掉「Fluent UI」；左上角图标与打包图标都换成 `icon.svg`，同步更新 qrc 并重新编译资源。

| 文件 | 改动 |
|---|---|
| `app/components/file_info_dialog.py` | 删除 `coverCaption` 控件（含「无内嵌封面」/「内嵌封面 · W × H」两种文本），保留封面画框与「保存封面」结果反馈标签 |
| `app/view/main_window.py` | 窗口标题改为「音乐解锁工具」；窗口图标由 `um.ico` 改为 qrc 资源 `:/img/icon.svg` |
| `app/resource.qrc` / `app/resource_rc.py` | 注册 `icon.svg`、移除不再使用的 `um.ico` 别名；已用 `pyside6-rcc` 重新编译（资源编译，非 Nuitka 打包） |
| `build.py` | 新增 `build_windows_icon()`：用 QtSvg 把 `icon.svg` 光栅化为 7 个尺寸并手写 ICO（PNG 条目），预检时生成 `app/resources/img/icon.ico`；`--windows-icon-from-ico` 指向该生成物 |

**验证（源码级，未执行 Nuitka 打包）**：
- `py_compile` 通过；`build_command()` 静态检查图标参数为 `icon.ico`，三个 exe 仍内嵌。
- 生成的 ICO：7 个尺寸（16/24/32/48/64/128/256）、ICO 目录偏移与 PNG 签名全部正确；Windows `ExtractIconW` 成功加载。
- 离屏实例化主窗口：标题为「音乐解锁工具」，SVG 图标非空且 64×64 可渲染；文件信息弹窗无 `coverCaption`，无「封面」字样标签。

### 变更：B 方案落地 —— 封面标签块直读，元数据仍用 ffmpeg（2026-11-26）

**需求**：「B 方案改动，增加封面解析的速度。」承接上一轮只读分析结论。

| 文件 | 改动 |
|---|---|
| `app/common/cover_loader.py` | 新增 `_read_flac_picture()`（FLAC `PICTURE` 块）/ `_read_id3_picture()`（MP3 ID3v2 `APIC`/v2.2 `PIC`），`read_embedded_cover()` 返回 **(原始图片字节, 容器是否识别)**；`extract_cover_bytes()` **签名不变**，改为标签块直读优先、不可识别/异常才回退 ffmpeg；新增 `cover_bytes_to_png()`，只在保存时把 JPEG 转成 PNG |
| `app/common/media_info.py` | `probe_media()` 拆开：封面交给 `extract_cover_bytes()`（零进程），元数据仍走一次 `probe_audio_info()`；删除不再使用的 `_PNG_SIGNATURE` |
| `app/view/decrypted_interface.py` | `_save_cover()` 写盘前调用 `cover_bytes_to_png()` —— 目标固定 `<歌名>.png`，不能把 JPEG 字节直接写成 PNG；其余调用点零改动 |
| `build.py` | **恢复 `qjpeg.dll`**（约 0.56MB），否则打包版 `QImage.fromData` 解不了原始 JPEG 封面；其余图片格式仍排除 |
| `task_card.py` / `file_info_dialog.py` / `cover_thumb_cache.py` | 仅同步 docstring（字节从「PNG」改为「JPEG/PNG」），`QImage.fromData` 本身两种格式都支持，解码代码零改动 |
| `README.md` / `docs/已解密列表-内嵌专辑封面可行性分析.md` | 同步功能、性能表与依赖说明；分析文档补 2026-11-26 落地备注 |

**决策说明（证据）**：
- **不新增依赖**：`.venv` 无 mutagen / Pillow；FLAC PICTURE 与 ID3v2 APIC 用 `struct`/`int.from_bytes` 直读即可覆盖当前库，无需 `uv add`。
- **不在探测路径转码**：实测 800×800 JPEG → PNG 约 **226–248ms**，与 ffmpeg 编码 PNG 同量级；改为缓存原始字节、QImage 直接解码，转码只在用户点「保存封面」时发生。JPEG 占当前库 **238/350 FLAC + 29/29 MP3**，这一决策是提速关键。
- **识别容器即不启进程**：确认无内嵌图返回 `(None, True)`，`extract_cover_bytes` 直接返回 `None`；只有未知容器/异常才回退 ffmpeg，格式兼容不回退。

**实测数据**：
- 当前输出目录：350 FLAC（全部有 PICTURE，238 JPEG / 112 PNG）+ 29 MP3（全部 APIC JPEG）。
- 封面提取：FLAC **0.68ms**、MP3 **1.12ms**，monkeypatch 验证 **ffmpeg 调用数 = 0**；改动前同 10 文件 ffmpeg 提取 **4044ms**。
- 整条 `probe_media`：5 文件 **1126ms → 462ms（2.4×）**（元数据探测仍占大头）；独立实测封面字节 72839B + title/artist/duration/codec 均正确。
- PNG 源文件原样返回（字节恒等）；原始 JPEG 卡片缩略图与详情大图解码均非空（44×44 / 800×800）。
- 无封面 FLAC 不启 ffmpeg；未知 WAV 与异常 FLAC 正确回退 ffmpeg。

**踩坑（实现过程）**：
- `QBuffer(QByteArray())` 用临时对象会被回收，实测 **段错误**；改为持有 `byte_array` 局部变量（后续转码只在保存路径触发）。
- FLAC PICTURE 的 `description_len` 位于 MIME **之后**，初版按紧邻 MIME 长度读取导致全部误判为「无封面」。
- 跳过 metadata block 时误用 `seek(absolute, SEEK_CUR)`，应传绝对偏移（默认 `SEEK_SET`）。

**保持不变**：`extract_cover_bytes` / `probe_media` 签名、三张封面缓存与双队列调度、封面字节契约对 UI 透明、固定同名 `.png` 覆盖语义、解密转换仍依赖 ffmpeg。

**验证**：`py_compile` 通过；上述源码实测全部通过；`build_command()` 静态确认 qjpeg 不再排除、QtXml 仍保留、三个 exe 均内嵌；跨层依赖违规 **0**；offscreen 启动 8s 无 Traceback；`config.json` 未改。全程**未执行任何 Nuitka 打包命令**。

### 变更：tools 版本检测改为「文件属性优先，命令行兜底」（2026-11-26）

**需求**：「tools 文件夹里面的 exe 文件版本信息提取，先通过文件属性获取，如果可以获取则显示，如文件属性无法提取，则使用 -v 命令提取。」

| 文件 | 改动 |
|---|---|
| `app/common/version_info.py` | **新增** `read_file_version(path)`：用 `ctypes` 调 `version.dll` 读 PE 版本资源，优先级 `FileVersion → ProductVersion → VS_FIXEDFILEINFO` 数字版本；无资源 / 非 Windows / 读取异常返回 `None`。纯标准库、不依赖 pywin32 |
| `app/service/tool_detector.py` | 三个工具统一走 `_probe()`：先 `read_file_version()`，命中即 `ToolInfo(version, True, "文件属性")`；否则按工具依次尝试命令行版本参数解析；`ToolInfo` 增 `source` 字段，运行日志逐条标注来源 |

**决策说明（证据）**：
- 实测三个 exe 的文件属性：`ffmpeg.exe = 8.1.3-Jellyfin`（可提取）；`um.exe` / `qmpc-mmkv-cli.exe` 为空（Go 编译无版本资源）→ 必须兜底。
- 兜底参数按各工具**真实版本参数**选择：`um -v`（实测 `Unlock Music CLI version v0.2.20 ...`）、`ffmpeg -version`（`-v` 是日志级别参数，会打印版本后报缺参）、`qmpc -V`（`-v` 是 verbose，会**真实执行密钥提取并写 `qmpc-mmkv-v1.mmkv`**，不能用于取版本）。各留一个备用参数（`-h` / `-v` / `--version`）防版本参数变更。
- 文件存在但版本取不到仍判 `ready=True`（沿用既有行为）；版本来源写进 `工具监测 xxx: ... (就绪 / 命令行 -v)` 日志，便于核对。

**保持不变**：`ToolsReport` 信号载荷、`VersionCard` 展示与徽章逻辑、`detect_async()` 线程池路径、超时 8s、配置文件与界面布局。

**验证**：`py_compile` 通过；源码实测 `ToolDetector().detect()` 输出 `um=v0.2.20(命令行 -v)`、`ffmpeg=8.1.3-Jellyfin(文件属性)`、`qmpc=1.0.4(命令行 -V)`；临时假 exe 验证 `--version` 备用参数与「未找到」分支；离屏启动 8s 无 Traceback，跨层依赖违规 **0**，`config.json` 未改。全程**未执行任何 Nuitka 打包命令**。

### 变更：详情界面改为参考图布局（顶部标题行 + 左大图 + 键左对齐）（2026-11-25）

**需求**：用户提供详情界面参考图（手办资料卡），要求「按照这个布局，修改详情界面」。参考图特征：顶部一行左对齐「中文字段名：值」标题；左侧竖向大图占约 1/3 宽；右侧键值表**键名左对齐**、值左对齐，纵向多行。

| 文件 | 改动 |
|---|---|
| `app/components/file_info_dialog.py` | ① 标题由居中 `TitleLabel("文件信息")` 改为左对齐 `StrongBodyLabel("文件名：")` + 跑马灯文件名；② 封面画框 240×240 → **270×340 竖向**（`_COVER_W`/`_COVER_H`，`_decode_cover` 按 KeepAspectRatio 缩放，`_placeholder_pixmap` 同步竖向 + 音符 96px）；③ 键值表由「键右对齐 + stretch 1:4」改为**键左对齐 + 固定键列 76px（ `_KEY_COL_W`）+ 值列吃剩余**，列间距 18、行间距 11，两栏间距 16；④ 对话框宽 720–780 → 780–840；⑤ 移除未再使用的 `TitleLabel` 导入 |

**决策说明（证据）**：
- **键列必须定宽**：旧版键右对齐靠 `stretch 1:4` 自然对齐；改左对齐后若仍用 stretch，最长键「完整路径」会撑宽列、其余键indent 参差。固定 76px（4 字 + 余量）后 14 行键名起点一致。
- **画框竖向但内容等比**：`_decode_cover` 返回的 pixmap 是等比缩放后的**实际尺寸**（正方形封面 → 270×270，非正方形 640×480 → 270×202），画框由 `QLabel.setFixedSize(270, 340)` + `AlignCenter` 承载，正方形图上下留白属预期，不裁切不变形。
- **标题用跑马灯**：文件名可能很长（加密后缀 + 中文名），`MarqueeLabel(bold=True, auto=True)` 溢出自动滚动，不撑破宽度；窗口标题栏仍是「文件信息」。

**保持不变**：14 行字段与完整路径可点击链接、跑马灯单行语义、底部两按钮等分铺满、对话框内 `statusLabel` 兜底、右键菜单 3 项、封面缓存链路、保存回调契约。

**验证**：`compileall` 通过；**33 项 offscreen 断言全 PASS** —— 封面解码（正方形 / 非正方形 / 损坏字节 / 占位图）、标题行控件类型与文案、画框 270×340 / 状态行宽 / 对话框宽 780–840、键左对齐 / 键列 76px / 间距 16-18-11、真实几何封面 x=25 < 键 x=311 < 值 x=405 且间距 16/18px 紧凑、标题在封面上方、14 行 28 项与路径链接零回归、保存回调与状态行、无封面禁用、右键菜单 3 项；offscreen 渲染快照确认视觉；源码 offscreen 启动 3s 无 Traceback，`config.json` 未改，分层依赖违规 **0**。

**踩坑（测试脚本，非实现缺陷）**：初版断言误以为 `_decode_cover` 返回固定画框尺寸，实际返回等比缩放后的实际 pixmap（画框由 QLabel 固定）；菜单源码断言误匹配到 docstring 里的「保存封面不再放在这里」说明。两处断言修正后全过。

**说明**：全程只跑源码验证，**未执行任何 Nuitka 打包命令**。

### 变更：保存成功回归默认提示 + 左右分栏间隔收紧（2026-11-23）

**需求**：「取消保存成功后，信息提示框上的查看按钮，改为默认的成功提示，中间间隔不要太大，紧凑一点。」本条取代同日「封面保存固定同名覆盖 + 提示条『查看』大图预览」中的「查看」链路。

| 文件 | 改动 |
|---|---|
| `app/common/signal_bus.py` | 删除 `cover_saved = Signal(str)`——不再需要专用信号 |
| `app/view/decrypted_interface.py` | `_save_cover()` 成功后由 `cover_saved.emit(target)` 改发 `signalBus.toast_requested.emit(f"已保存到音乐文件同目录: {basename}", "success")`；模块头与 docstring 同步 |
| `app/view/home_interface.py` | 删除 `cover_saved` 连接、`_show_saved_cover_toast()` / `_view_saved_cover()`、`_COVER_TOAST_DURATION_MS` 常量及 `InfoBarIcon` / `TransparentPushButton` / `CoverPreviewDialog` 导入；保存成功统一走既有 `_show_toast()` → `InfoBar.success`（3s、无动作按钮） |
| `app/components/file_info_dialog.py` | `bodyLayout` 两栏间距 24→12、`grid` 键值列间距 20→12、列 stretch 2:3→1:4；注释与 `_on_save_clicked` docstring 同步 |
| `app/components/cover_preview_dialog.py` | **文件保留**、不再接线；docstring 顶部标注「当前未接线，保留备用」及原因 |

**决策说明（证据）**：
- **「默认成功提示」= 既有 `_show_toast` 通道**：`InfoBar.success`，3s、右上角、可关闭、无附加按钮。专用 8s 带按钮提示条整条链路（信号 / 方法 / 常量 / 导入）一并移除，不留死代码。
- **空白来源有两处**：两栏 24px 间距 + 键名列占 2/5 宽后右对齐产生的左侧留白。在同一对话框内切换参数做对照测量：封面右边缘 → 首行键名左边缘 **143px → 58px（降幅 59%）**；键名仍右对齐，值列反而由更宽（实测 325px），长路径跑马灯显示空间更大。
- **预览组件不删**：用户只圈定「取消查看按钮」，保留实现便于日后复用；但已从首页移除 import，全项目无悬空引用。

**保持不变**：对话框内 `statusLabel` 兜底反馈（遮罩仍可能盖住首页浮层）、14 行信息表与路径链接、左封面解码 / 占位图、底部两按钮等分铺满、右键菜单 3 项、封面三级缓存与同名覆盖、成功日志。

**验证**：`compileall` 通过；**31 项 offscreen 断言全 PASS** —— `cover_saved` 源码与运行期属性均消失、首页无「查看」按钮与专用导入、成功仅发一条 `success` toast 且文案含文件名、真实 `MainWindow` 弹出的 InfoBar 无「查看」/无任何动作按钮、旧新参数同控件对照几何、键名右对齐 / 值列更宽 / 14 行、底部按钮仍铺满、对话框状态行成功失败零回归、无封面禁用、封面解码、右键菜单、分层依赖违规 **0**；offscreen 渲染快照确认紧凑效果；源码 offscreen 启动 3s 无 Traceback，`config.json` 未改。

**说明**：全程只跑源码验证，**未执行任何 Nuitka 打包命令**。

### 变更：保存封面入口移入文件信息对话框 + 按钮文案（2026-11-23）

**需求**：「右侧增加一个保存封面按钮，取消右键保存封面。关闭改为关闭窗口。」本条取代上一节「仅保留单个『关闭』按钮」与右键菜单里的保存入口。**同日微调**：「两个按钮占满底部，不要都在右侧」——按钮由挤在右半区改为等分铺满整行，见下方「同日微调」段。

| 文件 | 改动 |
|---|---|
| `app/components/file_info_dialog.py` | 底部按钮行由单个「关闭」改为**等分铺满整行**的「保存封面」（`PushButton(FluentIcon.SAVE, …)`，次要按钮）+「关闭窗口」（复用主按钮）。最终实现不用 `hideCancelButton()`（它会插左侧留白把按钮挤到右半区），改为直接隐藏并 `removeWidget(cancelButton)` 摘掉隐藏项，再把 `saveButton` 插到 `yesButton` 之前，两项各持 `stretch=1` 平分全部宽度；新增可选 `save_cover=None` 回调与左栏 `statusLabel`（默认隐藏）。无封面 / 未注入回调时禁用按钮并给 ToolTip |
| `app/view/decrypted_interface.py` | 右键菜单移除「保存封面」Action（现为 查看信息 / 播放音乐 / 删除文件）；`_show_file_info()` 注入 `save_cover=lambda: self._save_cover(card)`；`_save_cover()` 改返回 `(ok, payload)`（成功=导出完整路径，失败=可直接展示的原因文案），失败不再另发 toast、只记 error 日志；成功仍逐次发 `signalBus.cover_saved`，首页带「查看」提示条与应用内预览不变 |

**决策说明（证据）**：
- **落盘仍在 view，对话框只发意图**：`components` 只依赖 `common`，不写盘；对话框源码内不含 `open(`，通过注入回调调用 `_save_cover(card)`，复用现有字节缓存 / 两级缓存回填 / 同名覆盖写 / 日志全链路。
- **保存反馈必须在对话框内可见**：模态遮罩可能盖住首页 InfoBar 浮层，因此新增左栏状态行做兜底；成功文案手动断成「说明 + 文件名」两行（240px 窄栏自动折行会碎成 3~4 行，offscreen 快照已比对）；失败保持窗口打开、按钮可重试，不自动关窗。
- **隐藏的 cancelButton 会吃掉宽度**：`QBoxLayout` 对 hidden widget 仍计算 stretch，不 `removeWidget` 时两个可见按钮被压窄。首版曾额外补一份左侧 stretch 让按钮落在右半区（x=373 / 560、各 175px），用户同日纠正后去掉全部 stretch，改为等分铺满整行。

**保持不变**：14 行键值表与路径链接、左封面解码 / 占位图、封面三级缓存、同目录同名 `.png` 直接覆盖、成功日志、删除确认；`cover_saved` → 带「查看」InfoBar 链路在同日后续条目中被移除，见最前一条。

**验证**：`compileall` 通过；**62 项 offscreen 断言全 PASS** —— 右键菜单源码 + 运行期菜单文本（3 项，无「保存封面」）、按钮文案与几何（等宽 / 左右顺序 / cancel 已摘除）、成功 / 失败状态行、无封面与无回调两种禁用、13 项信息表与封面解码零回归、查看信息 → 回调 → `_save_cover` 全链路、`_save_cover` 首次 / 重复覆盖 / 无封面 / 写入失败四分支、`cover_saved` 与日志、真实 `MainWindow` 下按钮尺寸与状态行、首页提示条「查看」按钮零回归、分层依赖违规 **0**；两张 offscreen 渲染快照确认按钮不重叠、状态行不挤压封面；源码 offscreen 启动 3s 无 Traceback，`config.json` 未改。

**同日微调：底部按钮等分铺满整行**（用户：「两个按钮占满底部，不要都在右侧」）：`app/components/file_info_dialog.py` 去掉 `hideCancelButton()` 与两份左侧 stretch，改为 `cancelButton.hide()` + `removeWidget(cancelButton)` + `insertWidget(0, saveButton, 1)`，按钮布局由 4 项（2 留白 + 2 按钮）变为 2 项。实测 widget 720px 时 `buttonGroup=718`、两按钮各 329px（x=24 / 365，右界 693），`329+12+329=670 = 718−48`，刚好铺满扣除 24px 左右边距与 12px 间距后的全部宽度；offscreen 渲染快照确认左右贴边、等宽、无重叠。**40 项 offscreen 断言全 PASS**（含 3 个宽度场景、真实 MainWindow、保存回调 / 状态行 / 禁用分支 / 右键菜单 / 分层零回归）。

**踩坑（测试脚本，非实现缺陷）**：① 快照脚本未 `close()` 窗口时进程退出码 127（Qt 后台线程未清理），补 `dlg.close() / win.close() / processEvents()` 后 exit 0；② 对话框未 `show()` 时连续 `widget.resize()` 不触发布局重算，几何停在上一个尺寸导致 780px 断言误报，改为每个宽度独立构造并真实 `show()` 后取几何；③ 遮罩对话框 widget 宽度由 sizeHint 固定为 720px，`AlignCenter` 父布局会把人为 resize 拉回，故三个宽度场景实际都收敛到 720px 且均铺满。

**说明**：全程只跑源码验证，**未执行任何 Nuitka 打包命令**。

### 新增：查看文件信息左右分栏（左封面 / 右信息）（2026-11-23）

**需求**：「查看文件信息附带封面，左侧显示封面，右侧显示信息。」

| 文件 | 改动 |
|---|---|
| `app/components/file_info_dialog.py` | 主体从「单列 14 行键值表」改为 `QHBoxLayout` 左右分栏：左侧 240×240 封面位（等比缩放不裁切 + 圆角，下方标注原图像素），右侧保留原 14 行键值表；新增 `_decode_cover()` / `_placeholder_pixmap()`，`cover=None` / 损坏字节回退主题色大号音符占位图；对话框宽度 380–430 → 720–780。签名在**末尾**追加可选 `cover=None`，原有位置参数顺序不变 |
| `app/view/decrypted_interface.py` | 抽出 `_load_cover_bytes(path, mtime, card, item)` 供「查看信息」与「保存封面」共用：命中字节缓存零 ffmpeg，MISS 现场 `extract_cover_bytes()` 一次并回填字节 + 缩略图两级缓存、让卡片立即出图；`_show_file_info()` 把封面字节传给对话框。两个缓存都 MISS 时用 `probe_media()` 一次 ffmpeg 同时拿标签 + 封面 |

**保持不变**：14 行键值表内容、键右对齐 / 值左对齐、跑马灯单行滚动、完整路径强调色可点击链接 + ToolTip、单「关闭」按钮；封面用的是 ffmpeg 提取的**原始 PNG**，不是卡片上的 44×44 缩略图。

**决策说明**：
- 左侧封面用 `KeepAspectRatio` 而非居中裁剪：非正方形封面（实测 640×480 / 300×600）需完整展示，圆角只作用在缩放后的实际矩形上。
- 双 MISS 走 `probe_media()`：新增封面本会让「查看信息」在极端情况串行起 `probe_audio_info` + `extract_cover_bytes` 两个进程，合并后任何情况最多一次 ffmpeg。

**验证**：`compileall` 通过；**39 项 offscreen 断言全 PASS** —— 解码纯函数（800×800→240×240 / 640×480→240×180 / 300×600→120×240 / 圆角透明 / 无效字节）、占位图、左右两栏顺序与真实布局几何（封面栏 x=25 宽 240、信息栏 x=289 宽 446）、原图像素标注、14 行内容与路径链接零回归、无封面 / 损坏字节 / 不传 cover 三种占位回退、缓存命中零 ffmpeg、MISS 一次提取并回填两级缓存 + 卡片出图、双 MISS 只一次 `probe_media` 且回填后再看零 ffmpeg、「保存封面」零回归；offscreen 真实窗口显示 1.5s 无异常，`config.json` 未改，分层依赖违规 **0**。

**说明**：全程只跑源码验证，**未执行任何 Nuitka 打包命令**。

### 变更：封面保存固定同名覆盖 + 提示条「查看」大图预览（2026-11-23）

**需求（用户明确圈定）**：「保存不带后缀，若是重复，则直接覆盖，然后在弹窗上加一个查看按钮，点击即可查看已保存的封面图。」本条取代下方「同名自动加 `_2/_3`、不覆盖」的策略。

| 文件 | 改动 |
|---|---|
| `app/view/decrypted_interface.py` | 移除 `_unique_cover_path()`，改为纯函数 `_cover_path(music_path)` 固定返回同目录同名 `.png`；`_save_cover()` 以 `"wb"` 直接覆盖写，**不做 `exists` 预检**（避免 TOCTOU 竞态）；成功不再发普通 toast，改发 `signalBus.cover_saved(target)`；写入失败文案补「文件是否被占用」；模块头与 docstring 同步 |
| `app/common/signal_bus.py` | 新增 `cover_saved = Signal(str)`（完整路径），view 之间仍零直接引用 |
| `app/view/home_interface.py` | 连接 `cover_saved` → `_show_saved_cover_toast()`：用 `InfoBar` 直接构造、**先 `addWidget()` 再 `show()`**（InfoBarManager 在 showEvent 按 `infoBar.width()` 算右上角 x，反序会让浮层贴边错位），附 `TransparentPushButton(FluentIcon.VIEW, "查看")`；duration 8000ms（普通 toast 仍 3000ms）；`_view_saved_cover()` 收掉提示条再弹预览，文件已被移动则给 warning |
| `app/components/cover_preview_dialog.py`（新） | `CoverPreviewDialog(MessageBoxBase)`：从磁盘读刚保存的 PNG，超过 520px 等比缩小、小图不放大，标注文件名 + 原图像素，单「关闭」按钮；无效图片降级为文字提示 |

**契约变化**：重复保存**直接覆盖同名 PNG**，不再生成 `_2/_3` 副本，也不再保护目录里原有的同名资源；一键保存仍不弹任何对话框。导出内容仍是 ffmpeg 提取的**原始封面**（非 44×44 缩略图），两级缓存复用、缓存 MISS 现场提取、无封面 warning、写入失败 error toast 均不变。

**决策说明**：「查看」采用**应用内遮罩预览**而非 `QDesktopServices.openUrl()`：不依赖系统 `.png` 关联程序、点即得且可离线断言；与 `FileInfoDialog` 同用 `MessageBoxBase`，主题（浅/深色）自动跟随。

**验证**：`compileall` 通过；**40 项 offscreen 断言全 PASS**——纯函数固定路径 / 多点后缀 / 已存在同名仍返回固定路径、旧序号函数与 `QFileDialog` 彻底移除、首次与重复/第三次保存字节一致且目录只有一张图无 `_2`/`_3`、`cover_saved` 路径与 success 日志、成功不发普通 toast、写入失败 / 无封面 / 缓存 MISS 现提三分支、真实 `MainWindow` 触发 1 条带「查看」按钮的 InfoBar（8000ms、按钮有实际尺寸且位于关闭按钮左侧）、按钮接线、收条 + 弹预览、800×800→520×520 等比缩放 / 小图不放大 / 无效图片降级、文件被移动 warning、`InfoBar.close()` 不抛异常；offscreen 真实窗口显示 2s 无异常，`config.json` 未改，分层依赖违规 **0**。

**说明**：全程只跑源码验证，**未执行任何 Nuitka 打包命令**。

### 变更：保存封面改为一键落盘到音乐文件同目录（2026-11-23）

**需求（用户明确圈定）**：「封面默认保存在音乐文件同目录」。经确认选择「直接保存、不弹框」——原实现虽已把对话框默认路径设为同目录，但仍要求用户每次点确认，不是「默认保存」。

**改动**（仅 `app/view/decrypted_interface.py`）：

- 移除 `QFileDialog.getSaveFileName()` 与 `QFileDialog` import：点击「保存封面」直接写入音乐文件所在目录的 `<歌曲名>.png`，不再弹保存对话框。
- 新增模块级纯函数 `_unique_cover_path(directory, stem)`：同名已存在时依次尝试 `<stem>_2.png` / `_3.png`…，**不覆盖**用户此前导出的图片或目录里原有的同名资源。免对话框意味着没有确认覆盖的机会，这是必须的保护。
- 反馈调整：toast 改为「已保存到音乐文件同目录: xxx.png」，日志仍记完整路径；菜单图标 `FluentIcon.SAVE_AS` → `SAVE`（语义从「另存为」变为「直接保存」）。
- 模块 docstring 与 `_save_cover` docstring 同步新契约。

**保持不变**：导出内容仍是 ffmpeg 提取的**原始 PNG**（非 44×44 缩略图）；缓存命中零 ffmpeg、MISS 时现场提取并回填两级缓存；无封面 warning、写入失败 `logger.error` + error toast；右键菜单顺序「查看信息 / 播放音乐 / 保存封面 / 删除文件」。

**验证**：`compileall` 全项目通过；**19 项单元断言全 PASS**——无 QFileDialog 依赖、菜单顺序与 SAVE 图标、纯函数序号、首次同目录同名写入且字节与源一致（1024×1024 合法 PNG）、缓存命中零 ffmpeg、toast/日志路径、重复保存生成 `_2`/`_3` 且原文件未被覆盖、无封面零写入 + warning、写入失败 error 不抛异常、MISS 现场提取一次并同样落到同目录。offscreen 启动 15 秒无异常，工具链就绪，`config.json` 未改，分层依赖违规 **0**。

**说明**：本轮用缓存中的真实 PNG 字节做端到端落盘验证，未重复跑真实 flac 的 ffmpeg 提取（该链路上一条记录已实测 800×800 / 930KB 合法 PNG，本轮未改动）。全程只跑源码验证，**未执行任何 Nuitka 打包命令**。

### 新增：全屏列数切换的 FLIP 位移动画（2026-11-23）

**需求**：窗口全屏 / 最大化导致 2 列变为 4 列（或更多）时，卡片要有**带移动效果**的过渡动画，而非瞬间硬切。

**替换关系**：本条目取代 2026-11-20「列数变化时视口卡片 0.72→1.0 / 160ms 统一柔和淡入」的方案。淡入只遮掩了硬切、没有位移；现在改为真实几何插值，`_soft_relayout_fade()` 与 `_RELAYOUT_FADE_MS` 已移除。

**实现**（仅 `app/components/grid_card_container.py`）：

- 标准 FLIP（First-Last-Invert-Play）：`_snapshot_visible_geometry()` 在摘布局前记录视口上下各一行卡片的 `QRect`（First）；重排收敛到新几何（Last）后 `_play_relayout_motion()` 把卡片 Invert 回旧位置；单个 `QVariantAnimation` 逐帧 `Play` 到新位置。
- **插值完整 `QRect`（x/y/w/h）而非只 `move()`**：列数变化会同时改变位置**与列宽**（实测 2 列 714px → 4 列 351px），只移动会留下宽度错位/重叠。
- **单动画批量刷几何**：`_apply_relayout_frame()` 一帧内对所有卡片 `setGeometry`，不每卡挂一个 `QPropertyAnimation`——延续项目「几十个动画并发抢事件循环」的既有教训。实测 40 张单帧插值 **0.15ms**，作用域 22/120 张（与卡片总量解耦）。
- **无旧几何的卡片短淡入**：列数变化后新进入视口的卡片归入 `newcomers`，从 0.72 淡入且与位移**共用同一个动画对象**；有位移的卡片保持完全不透明，避免叠加透明度让画面发虚。
- 缓动 `OutCubic` / 280ms，与瀑布流入场的 `OutQuart` 刻意区分：几何移动更需要「稳稳停住」的收尾。
- 类开关 `relayout_motion = True`；`_filling` 期间与首次排布（`_grid_cols == 0`）不触发。即时页 `_relayout()` 与懒加载页 `_relayout_lazy()` 两条路径共用同一套机制。

**收敛设计（关键）**：`eventFilter` 的 viewport Resize、`_on_lazy_scroll`、`_cancel_fade_in()`（重建 / 刷新）三处统一调用 `_cancel_relayout_motion()`，把卡片立即收敛到目标几何并卸载 effect，绝不让卡片停在半路进入下一轮布局。`_snapshot_visible_geometry()` 抓取前也先收敛——业务主动重排若撞在动画播放中途，First 仍是稳定终点而非插值半路。动画结束时 `_settle_relayout_motion()` 精确落到目标 `QRect`，消除插值取整误差。

**风险验证**：Qt 布局是否覆盖逐帧 `setGeometry` 是本次最大不确定点。实测手动置中间态后处理事件循环，几何仍为 `(544,0,532,64)`（start `(726,0,714,64)` / end `(363,0,351,64)`），未被 `QGridLayout` 拉回；动画自然推进期间也确实出现逐帧中间值。

**验证**：`compileall` 全项目通过；两轮 offscreen 实测共 **54 项断言全 PASS**（29 项即时页/边界 + 25 项懒加载/集成）——Invert 起点、插值中间态、布局不覆盖、结束精确落位、4→2 反向、连续切换/滚动/重建收敛、隐藏页 pending、开关关闭零动画、快照收敛、newcomer 淡入无残留、真实 `TaskInterface` 2→4 列触发并收敛、导航切换无异常、平台图标与封面位零回归。offscreen 启动 15 秒无异常，工具链就绪，`config.json` 未改，分层依赖违规 **0**。

**说明**：offscreen 下 `MSFluentWindow` 的 stacked 页面宽恒为 100、`isVisible=False` 且启动期 `_filling=True`，集成验证中显式 `switchTo(task)` + 结束填充并给视口确定宽度，才复现真实全屏状态；此为测试环境限制，非实现缺陷。全程只跑源码验证，**未执行任何 Nuitka 打包命令**。

### 新增：已解密页右键「保存封面」（2026-11-23）

- **需求**：已解密界面右键菜单增加「保存封面」。
- **实现**（`app/view/decrypted_interface.py`）：
  - 菜单顺序改为「查看信息 / 播放音乐 / **保存封面**（`FluentIcon.SAVE_AS`）/ 删除文件」，删除项仍居末。
  - 新增 `_save_cover()`：导出的是 ffmpeg 提取的**原始内嵌封面 PNG**，不是卡片上 44×44 的圆角缩略图。优先复用 `_cover_cache` 已缓存字节（显示过封面的卡片零 ffmpeg、瞬时）；缓存 MISS 才用 `extract_cover_bytes()` 同步提取一次（等待光标反馈），并把结果回填字节缓存 + 缩略图缓存，顺带让卡片立即出图、之后再次显示也秒加载。`None`（确认无封面）同样写入缓存，避免重复起进程。
  - 保存路径走 `QFileDialog.getSaveFileName()`，默认与歌曲同目录、同名 `.png`（filter `PNG 图片 (*.png)`），非 `.png` 结尾自动补后缀；用户取消不写文件；写入失败记 `logger.error` 并给 error toast；成功发 log + success toast。
- **验证**：`compileall` 全项目通过；**20 项单元断言全 PASS**（菜单顺序与 Action 绑定、缓存命中零 ffmpeg、默认路径与标题、后缀补齐、取消不写文件、无封面不弹对话框且给 warning、无封面缓存、MISS 现场提取一次并回填两级缓存、卡片立即出图、写入失败不抛异常）；**真实 flac 端到端导出得到 800×800 / 930KB 合法 PNG**；offscreen 启动无异常、`config.json` 未改、分层依赖违规 0。
- **未验证**：Windows native 保存对话框的实际交互（offscreen 下用 mock 验证调用参数；项目 `setting_interface` / `task_interface` 已用同一 `QFileDialog` API，属既有可靠路径）。
- **全程只跑源码验证，未执行任何 Nuitka 打包命令。**

### 优化：已显示封面再次显示「秒加载」（2026-11-23）

- **需求**：已经显示过的歌曲专辑封面，再次显示到界面时应瞬时出现，优化显示逻辑。
- **实测证据（offscreen，真实 800×800 / 930KB 内嵌封面）**：
  - `ffmpeg` 首次探测单文件封面 + 标签平均 **254.1ms**；输出目录实测 379 个音乐文件。
  - 单次 `_rounded_cover()`（PNG 解码 → 缩放 → 圆角裁剪）**16.3ms**；40 张可见卡片「再次显示」**680.9ms**，其中 40 次占位图重绘另占 18.5ms。
  - 直接贴已生成的 44×44 QPixmap：40 张仅 **0.17ms**，差距约 4000×。
- **根因**：`common/cover_loader.CoverCache` 只缓存 ffmpeg 输出的**原始 PNG 字节**（实测约 1MB/张）。卡片每次重新进入视口（滚动回来、切页回来、全屏 2→4 列重排物化）都要重跑一次 QImage 解码 + 缩放 + 圆角裁剪，缓存挡住了 ffmpeg 却没挡住图像解码。
- **附带发现的逻辑缺陷（实测复现）**：字节 LRU 容量 512 淘汰后，`_apply_cover` MISS → `_ensure_media` 因 `item in self._tags` 判重直接返回，且 `_take_media_item` 又按 `_tags` 把该项当「已完成」丢弃 → **封面永久停在占位图**，直到重启程序。
- **改动**：
  - `app/components/cover_thumb_cache.py`（新）：`(path, mtime) → 44×44 圆角 QPixmap | None` LRU，容量 2048（约 16MB，远大于字节缓存 512，让显示过的缩略图不被挤掉）；`None` 与 `MISS` 用哨兵严格区分。QPixmap 为 GUI 资源，明确约定仅主线程调用。
  - `app/components/task_card.py`：新增 `set_cover_pixmap()`（跳过解码直接贴）；`set_cover()` 改为返回裁剪结果供调用方缓存。
  - `app/view/decrypted_interface.py`：`_apply_cover()` 改三级缓存 —— **缩略图命中 → 直接 setPixmap；字节命中 → 解码一次并回填缩略图；都 MISS → 清旧封面 + 登记 ffmpeg**。`_on_media_done()` 回填时同步写缩略图缓存；`_reuse_card()` 不再无条件 `set_cover(None)`，命中缓存时省掉中间那次占位图重绘，未命中才清。
  - 淘汰缺陷修复：`_ensure_media(..., for_cover=True)` 由 `_apply_cover` 发起，绕过 `_tags` 判重并把 item 记入 `_cover_recheck`；`_take_media_item()` 判据改为 `(cand not in _tags or cand in _cover_recheck)`；`_on_media_done()` / `_prune_media_queue()` 清理标记。**归类用的全量补探测仍走 `_tags` 判重**，不对已有标签的文件重跑 ffmpeg。
- **验证**：`compileall` 全项目通过；**26 项单元断言全 PASS**（三级缓存命中、零解码、None/MISS 区分、mtime 失效、LRU、复用卡片零占位图重绘、淘汰后重载、回填写缓存、归类不重跑、主题切换、任务页平台图标零改变）；**40 张再次显示 680.9ms → 0.26ms（约 2600×）**；真实 MainWindow 集成：379 个文件、预热后 20 张缩略图、切走→切回期间**封面解码次数 = 0**、缓存数 20→20 稳定；offscreen 启动无异常、`config.json` 未改、分层依赖违规 0。
- **未改动**：原始字节 LRU 容量保持 512 不变（归类全量探测时约占用数百 MB，属既有行为；缩容会触发重新探测反而更慢，如需收敛须另做磁盘缩略图持久化，本轮未扩大范围）。
- **全程只跑源码验证，未执行任何 Nuitka 打包命令。**

### 优化：全屏列数切换与页面切换的重排算法（2026-11-20）

- **需求**：全屏时 2 列变 4 列卡顿严重；任务管理 ↔ 已解密 切换也卡顿。要求从逻辑算法层面提升流畅度，而非只调动画参数。
- **实测证据（offscreen 基准，400 张真实 TaskCard）**：
  - 优化前 2→4 列 `_relayout()` **644.6ms**；cProfile 热点 `setParent` 326ms / `show` 274ms / `addWidget` 265ms，伴随 10824 次 QFluentWidgets 样式事件过滤器。
  - 优化前页面切换：任务管理→已解密 **1965ms**（含 `TaskInterface._relayout` 764.5ms）、已解密→任务管理 **2486ms**（含 1019.4ms）。**隐藏页面仍被全量重排**。
- **根因**：`_relayout()`（即时页 / 任务管理）一直沿用旧的「`takeAt` → `setParent(None)` → `addWidget` → `show`」全量摘挂；`_relayout_lazy()`（已解密）早已改为「保留 parent」并有 116ms→21ms 的实测记录，但即时页没跟进。且即时页缺少「视图未变就短路」机制，导航切页引发的 viewport Resize 也会无条件重排一次。
- **改动**：
  - `app/components/grid_card_container.py`：
    - `_relayout()` 改为**只摘布局项、不脱离 parent**：卡片保持 `scrollContent` 子控件与 visible，回填 `addWidget` 不再迁移 parent、无需 `show`；`setUpdatesEnabled(False/True)` 包住避免中间帧。
    - 新增 `_last_layout_seq`（参与排布卡片 id 元组）：**列数与序列都未变即短路**，只刷新计数、零摘挂零布局补算。
    - 可见性判断刻意放在**防抖定时器回调** `_on_relayout_timeout()` 而非 `_relayout()` 内部：业务主动重排（后台重建列表、增删卡片）仍同步执行以保证几何正确，只有尺寸变化类重排才在页面隐藏时跳过；`eventFilter` 隐藏页 Resize 直接记 pending，`showEvent` 统一补排一次。
  - `app/view/decrypted_interface.py`：
    - 新增 `_media_paused` 过渡期节流：`showEvent` 暂缓提交 ffmpeg 240ms（切换动画期间主线程在做整窗重绘），`hideEvent` 暂停，`_pump_media` 早退只攒队列，`_resume_media` 按可见优先恢复；队列不丢任务。
- **优化后实测**：
  - 2→4 列重排 **30.5ms 同步 / 68.1ms 含事件循环**（≈21× / 9.5×）；列数不变重复重排 **0.06ms**。几何校验：4 列、第 5 张落在 `(1,0)`、400 张全 visible、内容高 7390，全部正确。
  - 页面切换（冷态）1965/2486ms → **964/1480ms**；其中重排 764/1019ms → **0/35.6ms**。
  - **稳定态 A→B→A 四次切换重排调用全部为 0**（短路完全生效），耗时 1413→804→753→422ms，剩余为动画与渲染。
  - 媒体节流：切换总耗时 1014→832ms，最慢帧 147→112ms（禁用探测对照组 839ms）。
- **验证（仅源码，禁打包）**：py_compile 4 文件过；10 项回归断言全 PASS（保留 parent、几何位置、短路、隐藏页 pending、媒体暂停/恢复）；offscreen 启动 15s 无异常、工具链就绪、`config.json` 未改、分层违规 0。

### 优化：全屏切换重排与入场动画的流畅度（2026-11-20）

- **需求（用户圈定）**：任务管理 / 已解密两页的卡片列表，在窗口全屏/最大化 ↔ 普通之间切换时重排有顿挫；卡片刷新入场的瀑布流动画想更细腻。**不涉及**左侧导航的页面切换动画。
- **卡顿根因（代码证据）**：
  - `_RELAYOUT_DEBOUNCE_MS=40` 短于 Windows 最大化动画（约 250ms）的偶发帧间隙（45~60ms），会在动画中途触发 2~3 次全量摘挂；
  - viewport Resize 时，在途的错峰淡入 / 滚动短淡入与重排抢事件循环——此前只在 `_on_lazy_scroll` 做了收敛，resize 路径漏掉；
  - 列数跳变时卡片硬切到新位置，没有任何视觉过渡。
- **改动（仅 `app/components/grid_card_container.py`）**：
  - 防抖 40 → **80ms**，覆盖常见动画空档，尺寸稳定后一次到位；
  - `eventFilter` 的 viewport Resize 分支先 `_cancel_fade_in()`，与滚动收敛逻辑对齐；
  - 新增 `_visible_grid_cards()`（只取视口上下各一行，作用域与卡片总量解耦）+ `_soft_relayout_fade()`：列数变化时对视口卡片做 0.72→1.0 / 160ms 统一柔和淡入。**复用 `_batch_fade` 单动画槽位**，而非每卡一个 QPropertyAnimation——实测作用域 44/120 张时仍只有 1 个动画对象，不重蹈「几十个动画并发抢事件循环」的覆辙；
  - 即时页 `_relayout` 与懒加载页 `_relayout_lazy` 两条路径均接入；`_filling` 期间跳过，不与渐进填充的冻结逻辑冲突；
  - 瀑布流参数：三处分散的 `OutCubic` 统一为 `_FADE_EASING = OutQuart`（起步利落、收尾绵长），duration 220→**260ms**，stagger 16→**18ms**，滚动短淡入 140→**170ms**；stagger 仍按绝对时间补发，不受定时器抖动累积。
- **验证（仅源码，禁打包）**：py_compile 通过；13 项单元断言全 PASS（80ms 防抖、18/260/170 参数、OutQuart、即时页/懒加载页列数变化均触发柔和淡入且作用域 44/120 与 44/160、单动画槽位、零并发单卡动画、opacity 起点 0.72、列数不变零额外开销、Resize 收敛在途动画）；offscreen 启动 15s 无异常、工具链就绪、`config.json` 未改、分层违规 0。

### 重构：平台图标改用 QFluentWidgets 官方 FluentIconBase 定义（2026-11-20）

- **需求**：参考 `https://qfluentwidgets.com/zh/pages/icon/` 官方自定义图标定义与用法，改造已注册的平台图标；使用 qrc 编译、`:/` 资源路径。
- **官方范式**：自定义图标继承 `FluentIconBase` + `Enum`，重写 `path()` 返回 `:/` 开头的 qrc 路径，即可作为图标参数传给接受 `FluentIconBase` 的组件；`icon()` / `qicon()` 官方接口直接可用。
- **关键适配**：官方 SVG 用 `getIconColor(theme)` 切黑/白版本；本项目平台 logo 是彩色 PNG，`path()` **忽略 theme**，任何主题都返回同一 `:/img/<name>.png`，避免主题切换错误着色。
- **改动**：
  - `app/common/icon.py`：新增 `PlatformIcon(FluentIconBase, Enum)`（6 成员：QQ/网易云/酷狗/酷我/喜马拉雅/汽水），`path()` 返回 `:/img/{value}.png`；保留 `FIcon` 别名零改动。
  - `app/common/platform_icon.py`：`platform_icon_name()` → `platform_icon()`，返回值由字符串别名改为 `PlatformIcon` 枚举；53 后缀映射与最长匹配逻辑不变。
  - `app/components/task_card.py`：构造参数 `icon_name` → `platform_icon`（`FluentIconBase`）；`set_platform_icon()` 经 `icon.path()` 取 `:/` 路径加载，复用圆角裁剪；移除 `common.resource.image` 依赖。
  - `app/view/task_interface.py`：`_make_card` 传 `platform_icon=platform_icon(path)` 枚举。
  - 重编译 `app/resource_rc.py`（pyside6-rcc，非 Nuitka 打包）。
- **验证（仅源码，禁打包）**：py_compile 4 文件过；10 项端到端断言全 PASS（官方继承关系、53 后缀映射、最长匹配、44px 图标、彩色 PNG 忽略主题、真实图标主题保护、默认音乐图标、cover 零改变）；TaskInterface 接线通过；分层违规 0；offscreen 启动无异常、config 未改。

### 新增：任务管理卡片左侧显示平台图标（2026-11-20）

- **需求**：用 `um --supported-ext` 核对支持后缀与各平台加密格式，`resource` 内的平台 png 用于对应格式，其他格式用默认音乐图标；重编译 qrc；任务管理页左侧加图标，卡片布局参考已解密卡片。
- **平台归属依据（证据）**：实跑 `tools/um.exe --supported-ext` 得 73 个后缀；从 um.exe 二进制提取算法包 `ncm / qmc / kgm / xiami / ximalaya` + 官方支持格式清单确认：
  - `vpr` / `vpr.flac` 走 kgm 解码器（Viper 为酷狗品牌）→ 归**酷狗**；
  - `xm` 由 xiami/ximalaya 共用，按用户约定（XM = 喜马拉雅）与 `x2m/x3m` 一起归**喜马拉雅**；
  - um v0.2.20 无独立汽水音乐解码器，`QiShui_Music.png` 仅注册进 qrc 预留、未绑定后缀。
- **改动**：
  - `app/common/platform_icon.py`（新）：纯函数 `platform_icon_name(path)`，53 个加密后缀全映射到 6 平台图标，7 个明文后缀返回 None；按长度降序保证 `.kgm.flac`/`.mflac1` 等最长匹配。
  - `app/resource.qrc`：注册 6 张平台 png；用 `.venv/Scripts/pyside6-rcc.exe` 重编译 `app/resource_rc.py`（资源编译，非 Nuitka 打包）。运行时 12 张资源全部加载成功。
  - `app/components/task_card.py`：抽 `_rounded_pixmap()` 统一封面字节与 qrc 图标的居中裁剪+圆角；构造新增 `icon/icon_name` 参数，复用已解密卡片同一 44×44 左侧位；新增 `set_platform_icon()`；`cover` 模式行为零改变。修复 `QPixmap.scaled()` 返回 QPixmap、`drawImage` 只收 QImage 的类型错（统一 `.toImage()`）。
  - `app/view/task_interface.py`：`_make_card` 传 `icon=True` + 解析出的平台图标名；连接 `themeChanged`/`themeColorChanged` → 只重绘默认音乐图标占位图，真实平台 logo 不受影响。
- **验证（仅源码，禁打包）**：py_compile 6 文件通过；17 项单元断言全 PASS（无 icon 零改变、平台图标 44px 非空、默认占位图、主题刷新保护真实图标、cover 模式零改变、6 平台缩略图正常）；53 加密后缀映射覆盖 100%、明文 0 误映射；TaskInterface 实例化/建卡/主题回调/状态设置全通过；offscreen 启动 18s 无异常、工具链就绪、`config.json` 未改。

### 文档：README 同步当前实现（2026-11-19）

- **需求**：根据当前情况，修改 README 文件。
- **修正 3 处与代码不符的旧描述**（`README.md`）：
  1. 打包产物 `releases/音乐解锁工具.dist/…` → `releases/main.dist/音乐解锁工具.exe`：Nuitka standalone 目录名由入口脚本 `main.py` 决定，`--output-filename` 只改 exe 名（见 `build.py` 末尾注释）。
  2. 「请将三个 exe 放入 `tools/`」→「已随仓库附带」：`git ls-files` 显示 `tools/um.exe` / `ffmpeg.exe` / `qmpc-mmkv-cli.exe` 均已跟踪，需换版本直接覆盖即可。
  3. 「设置均以 `ComboBoxSettingCard` 呈现」「无任何自定义 QSS」两条已失效：路径卡片是 `PushSettingCard`、任务行为是 `SwitchSettingCard`；`marquee_label.py`（2 处）与 `task_interface.py`（1 处）存在局部 `setStyleSheet()`，改为「以官方 Fluent 组件与主题色为主，仅极少数局部样式」。
- **补充当前功能**：主题三态 + `SystemThemeListener` 实时换肤链路、深色列表 `autoFillBackground(False)`、任务页状态排序、已解密页内嵌封面 / 5 项分类归类 / 120ms 搜索防抖 / 右键查看信息、`FileInfoDialog` 14 行单行值与路径点击定位、封面+标签一次 ffmpeg 探测与可见项优先双队列、性能设计表与 offscreen 实测数据、严格单向分层约束、新增 3 个源码文件与 2 篇 docs、文档索引、运行时文件表扩充（`.venv/` / `__pycache__/` / `.workbuddy/`）。
- **验证**（仅文档，未打包）：文内 4 个本地链接 + 8 个关键路径全部存在；代码块围栏 6 个成对、5 个表格列数一致；14 行字段清单与 `file_info_dialog.py` 的 `rows` 逐项核对（是「码率」非「比特率」，且含「编码」）；「覆盖已转换」名称与 `SwitchSettingCard` 文案、`rotation="5 MB"` 日志配置、`_LAZY_PRELOAD_ROWS = 2` 均已核对。

### 优化：专辑封面按「当前屏幕优先」出图，不再按列表顺序排队（2026-11-19）

- **需求**：不按照顺序展示，优先展示当前所展示界面的列表专辑图。
- **根因（逐代码定位）**：`_ensure_all_media()` 在切「歌手名 / 专辑名」时把 `self._items` 全量按 mtime 顺序一次性 `QThreadPool.start()`；池队列是 **FIFO**，当前视口内卡片的封面任务排在几百上千个任务之后，屏幕上会长时间停留在占位图。滚到中部后更明显——可见项由 `_apply_cover()` 登记时早已被全量队列占位，旧 `_media_pending` 去重直接 return，连插队机会都没有。
- **方案（`app/components/grid_card_container.py`）**：
  - 新增 `visible_items()` 封装（返回**真实视口**内条目，不含上下各 2 行预载）与 `_on_visible_items(items)` 空钩子；`_materialize_visible()` 末尾按 `y0/y1` 算可见范围，仅在可见内容变化时通知子类（行内小幅滚动零开销）。
  - `_clear_grid()` 重置 `_last_visible_items`：分类 / 搜索 / 刷新导致视图变化后强制重新提权，避免新屏幕上的条目仍排在普通队列末尾。
- **方案（`app/view/decrypted_interface.py`）**：把「一次性全量入池」改为**双队列 + 按在途上限喂入**：
  - 状态：`_media_urgent`（视口可见，`appendleft` 队首优先）、`_media_normal`（全量补探测 FIFO）、`_media_queued` / `_media_urgent_set` / `_media_inflight` 三组去重状态，替换原单一 `_media_pending`。
  - `_ensure_media(item, priority=False, pump=True)`：`priority=True` 时若条目还在普通队列，复制一份插到 urgent 队首（原位置出队时按 `_media_queued` 判重自动作废）；已在 ffmpeg 中的不抢占、不重复提交。
  - `_pump_media()`：始终只保持最多 2 个在途，每次登记 / 每次结果回填都补喂一次——新可见项最多等 1 个任务（约几十毫秒）即可插队，而不是等整份列表跑完；`_take_media_item()` 先 urgent 后 normal。
  - `_on_visible_items()` 覆写：`reversed + appendleft` 让最上方卡片排队首，屏幕内仍自上而下出图；`_ensure_all_media()` 末尾 `_prioritize_visible_items()` 兜底钩子未触发的情形。
  - `_prune_media_queue()`：列表重建后丢弃已删除文件的排队项（在途的两个跑完自然作废，QRunnable 无取消接口）。
  - `_on_filter_changed()` 顺序反转为**先 `_relayout()`（物化并提权可见项）再 `_ensure_all_media()`**；反序会让全量任务先占满 2 个线程。`_on_media_done()` 回填后新增 `_pump_media()` 补喂，归类防抖重排行为不变。
- **关键坑（实测）**：
  - 原 `_media_pending` 把「排队中」与「运行中」混成一个集合：可见项若已在队列就无从提权，若已提交又会被重复登记。必须拆成 `queued` / `inflight` 两组。
  - 不能靠 `QThreadPool.start(runnable, priority)` 解决：优先级只影响**尚在池队列里**的任务，已一次性入队的千级任务前两个照样先跑，且无法随滚动动态重排；改为主线程自管队列才可控。
  - 可见范围必须排除 `_LAZY_PRELOAD_ROWS` 预载行，否则上下各 2 行的不可见卡片会稀释真正屏幕内条目的优先级。
- **验证（仅源码，未打包）**：py_compile 全量 13 文件通过；`_verify_visible_first.py` 15 组断言 ALL PASS（可见项插队顺序、排队项提权、在途去重与上限 2、三缓存回填、无重复提交、重建清理、切分类顺序、真实滚动钩子、首屏可见 36 项 / 中部 40 项、即时页零影响、缓存命中、归类防抖、首屏几何、内容高度 18490→18490、视图短路对象身份）；offscreen 启动 15s 无错误日志、`config.json` 前后 md5 一致；分层依赖违规 0。
- 注：在途的 2 个 ffmpeg 任务不可抢占，故「优先」的语义是**最多等 1 个任务完成**即可让当前屏幕出图，而非瞬时中断。全量标签探测仍在后台按序补齐，归类排序结果不受影响。临时脚本已清理。

### 优化：已解密列表流畅性与动画丝滑度（2026-11-19）

- **需求**：优化已解密列表的算法，提高显示列表的流畅性和动画的丝滑度。
- **基准（逐代码读取 + `_bench_decrypted.py` 实测，真实视口 1140×623）**：
  - `_relayout_lazy` @1000 ≈ 97ms；连续输入 6 字符 @1000 526ms、@3000 861ms（每敲一键全量重建）。
  - 滚到底常驻卡片 876 张、一次视图变化重排 2676ms；滚动全程 `_make_card` 真实建卡 956 次；在途淡入动画峰值 28 个。
  - 根因：① 每次重排 `takeAt` + `setParent(None)` + `deleteLater` 全量销毁重建；② 卡片滚出视口不回收，越滚越多；③ 视图未变仍走完整 `_clear_grid` → `_relayout_lazy`；④ 每张卡一个 `QPropertyAnimation` + QTimer 逐拍错峰、延迟累积；⑤ 搜索无防抖、每键全量过滤且重复 `os.path.basename().lower()`；⑥ 媒体探测走 `QThreadPool.globalInstance()`（12 线程）与转换/扫描抢线程。
- **方案（`app/components/grid_card_container.py`）**：
  - 新增常量 `_SPACER_H = _ROW_H + _V_SPACING`（占位格与卡片行 stride 统一 74）、`_LAZY_KEEP_ROWS = 4`、`_CARD_POOL_MAX = 96`。
  - `_clear_grid()` 改为**保留 parent 摘挂**（`takeAt` 后不 `setParent(None)`）+ 占位格进 `_spacer_pool` + 重置 `_last_view`，返回 detached widgets 供复用。
  - `_relayout_lazy()` 增加视图/列数未变短路：`same` 时只 `_materialize_visible()` + `_update_count()`；视图变化才按 `_pos_of` 回填，隐藏筛掉的卡片、复用占位格。
  - 新增 `_recycle_offscreen(first_row, last_row)` 回收视口外卡片入池并补占位格；`_materialize_visible()` 优先 `_reuse_card(item)`；物化/回收后立即 `gridLayout.activate()`。
  - 动画：`_schedule_fade_in(stagger=False)` 由**单个 `QVariantAnimation`** 批量驱动所有新卡片 opacity（原每卡一个）；`_fade_tick()` 按 `time.monotonic()` 绝对时间一次补发多张，消除 QTimer 延迟累积；`_cancel_fade_in()` / `_on_lazy_scroll()` 取消在途瀑布流并卸载 effect。
- **方案（`app/view/decrypted_interface.py`）**：
  - `_SEARCH_DEBOUNCE_MS = 120` 防抖（`_on_search` 只记 `_filter` 并启单次 `QTimer`，`_apply_search` 才重排）；`_name_lower` 缓存 path → 小写 basename，`_on_scan_done()` 清空。
  - `_MEDIA_MAX_THREADS = 2` 专用 `_media_pool = QThreadPool(self)`，不再占满 globalInstance。
  - `_card_pool` + `_park_card()`（隐藏入池，超 `card_pool_max` 才 `deleteLater`）+ `_reuse_card()`（重绑 `file_path` / `_lazy_item` / `_source` / `nameLabel` / `metaLabel` / `badge` / `cover`，清掉上一文件 hover 状态）。
- **方案（`app/components/task_card.py`）**：`set_badge()` 增加 `(text, kind)` 早退，复用/重复刷新不再销毁重建 `InfoBadge`。
- **关键坑（实测）**：
  - 占位格高 64 与卡片行 stride 74 不等距 → 混合行 `[74, 64, ...]`，内容高度随物化漂移；统一 `_SPACER_H` 后实测 18490 → 18490 稳定。
  - `setParent(None)` 摘挂 116ms → 保留 parent 20.77ms（**5.6×**）。
  - cProfile 显示「滚到底后重排慢」不在 `_relayout()`（12.8–23ms），而是后续 `processEvents()` 中滚动条 range 变化触发 `_on_lazy_scroll()` 物化 43 张新卡（320ms）→ 卡片池解决。
  - offscreen 基准须把页面作顶层窗口 `resize(1200, 760)` + `show()` + 多轮 `processEvents()`，否则视口只有 98×28、滚动/动画数据失真。
- **验证（仅源码，未打包）**：py_compile 全量 13 文件通过；`_verify_listperf.py` 11 项 ALL PASS（首屏几何 / 滚到底回收 / 内容高度不漂移 / 滚回中部 / 搜索过滤 / 清空恢复 / 视图短路对象身份保持 / 切分类 / 刷新重建 / 即时页回归）；`_verify_perf_final.py` 11 项 ALL PASS（防抖 / 小写缓存 / 线程池限流 / 归类回归 / 错峰补发 / 动画取消 / 单动画批量淡入 / 滚动收敛 / 复用池）；清理后重跑复核仍 ALL PASS。
- **实测提速**：视图未变重排 97 → 0.38ms；连续输入 6 字符 @1000 526 → 3.38ms、@3000 861 → 10.31ms；滚到底常驻卡 876 → 约 60；滚到底后重排 2676 → 逻辑 9~23ms / 含事件循环 57~135ms；滚动全程真实建卡 956 → 32；在途动画峰值 28 → 2；A/B 复用池 5613ms vs 无池 10176ms（**1.81×**）。
- 注：offscreen 绝对耗时含事件循环、绘制、QTimer 与 Fluent 事件，波动较大（57.4~135.4ms），不作为用户态帧耗时的唯一指标；即时（非懒加载）页路径零改动并已单独回归。offscreen 启动 15s 无错误日志、`config.json` md5 未变；全局遗留符号 0、分层依赖违规 0；本轮未执行任何打包命令。临时脚本 5 个已清理。

### 统一：详情页全部值单行显示 + 溢出自动跑马灯（2026-11-19）

- 需求：详细信息全部单行显示，超过（溢出右列宽）的单行用跑马灯完整展示信息。
- 改动（`app/components/file_info_dialog.py`）：`_add_rows` 把原 12 行 `BodyLabel`（wordWrap 换行 + 可选中复制）统一改为 `MarqueeLabel(bold=False, auto=True)`；删除 `_MARQUEE_KEYS` 分支与 `BodyLabel` / `QSizePolicy` 导入；14 行值统一走 `AlignVCenter` 拉伸填满右列（跑马灯需拉伸才能检测溢出）。
- 复用 `MarqueeLabel(auto=True)` 固有语义：`_need_scroll = 文本宽 > 控件宽`，溢出才自动滚动、不溢出静态单行且定时器零开销；组件本身**零改动**，列表卡片仍「悬停才滚」不受影响。
- 路径行特殊交互完整保留（手型光标 / `setTextColor` 强调色 / Fluent `ToolTipFilter` / 点击定位），其余 13 行普通态（不染色、不可点击、无提示）。
- **配套修复 · 统一行高**：实测 Fluent `BodyLabel` 一旦被 `setStyleSheet()`（哪怕原样重设；7 种颜色写法全测过）`sizeHint().height()` 由 14 突变为 30，与写法无关 —— 路径行因染强调色会比其他 13 行高一截。在 `_add_rows` 给所有值行 `setFixedHeight(fontMetrics().height() + 4)`（实测 16px），14 行严格等高；不改组件、不影响卡片、不影响 2:3 列宽与水平滚动。
- 取舍：跑马灯子 label 对鼠标透明（`WA_TransparentForMouseEvents`），统一后各值行不再支持鼠标拖选复制（此前艺术家行已如此）；「完整显示信息」由自动滚动达成。
- 验证（仅源码，未打包）：py_compile 过；8 组断言全过 —— 14 行均为跑马灯 / 全部拉伸填满 186px 右列且等高 16px / 2:3 = 0.667 / 7 长值行自动滚且不换行 / 逐行独立判定（13 静态 + 修改时间自动滚）/ 路径交互保留其余普通 / 同框长短混排互不干扰 / 真实事件循环 400ms 推进 20.5px ≈ 55px/s；渲染截图 + offscreen 启动 15s 无错误。临时脚本与截图已清理。

### 调整：详情页键值表列宽占比 左 2/5 : 右 3/5（2026-11-19）

- 需求：左侧列占比五分之二、右侧列五分之三（同时兑现上一轮「左列往右来点」：左列变宽后右对齐键名自然右移）。
- 方案（`app/components/file_info_dialog.py`）：`setColumnStretch(0, 2)` + `setColumnStretch(1, 3)`，删除原 `setColumnStretch(1, 1)`。
- **关键坑（实测）**：`QGridLayout` 的 stretch 只分配「扣除每列最小宽度后的剩余空间」，而每列下限取该列所有 widget 的 `minimumSizeHint` 最大值。长文件名/标题等 `BodyLabel`（`Preferred` 策略，minW 可达 196px）会撑大右列下限，导致长元数据场景比例漂移为 114:196=0.582（短元数据恰好 124:186=0.667）。修复：给普通值 `BodyLabel` 设水平 `QSizePolicy.Ignored`（与跑马灯组件同策略），其 sizeHint 不再参与列下限计算，stretch 遂精确按 2:3 分配全部空间；wordWrap 仍在列宽内自动换行，且加 `AlignLeft` 也不会溢出列边界（已断言）。
- 验证：py_compile 通过；验证脚本全过（短/长元数据 × 900/1400 两种窗口宽度，四种组合均 124:186=0.667；键名右缘 72→148；右列收窄到 186 后路径/艺术家跑马灯仍填满并自动滚动；14 行无越界重叠；短艺术家静态不滚；值 label 宽度均 ≤ 列宽）；渲染截图确认；offscreen 启动 15s 无错误。未打包。

### 调整：艺术家值过长时自动跑马灯、不溢出则静态单行（2026-11-19）

- 需求：详情页「艺术家」值过长被覆盖/换行时自动跑马灯，不过长则不使用跑马灯。
- 方案（`app/components/file_info_dialog.py`）：新增类级常量 `_MARQUEE_KEYS = ("完整路径", "艺术家")` 统一判定；艺术家行值改 `MarqueeLabel(bold=False, auto=True)`——组件固有语义即「溢出才滚、不溢出静态单行零开销」，天然满足需求；`addWidget` 走 `AlignVCenter` 拉伸填满列宽（与路径一致，否则无法检测溢出）。艺术家保持默认样式：无手型光标、不染色、无点击与 ToolTip（区别于路径行）。其余 12 行仍 `BodyLabel` 可选中复制，范围未扩大。
- 验证：py_compile 通过；6 组断言全过（长艺术家 882>262 自动滚动 / 短艺术家 42<262 静态不滚且定时器不空转 / 其余行仍 BodyLabel / 路径行回归 / 默认样式 / 同框长路径滚短艺术家不滚互不干扰）；渲染截图确认艺术家长值单行无换行无重叠；offscreen 启动 15s 无错误。未打包。
- 注：验证脚本两处调试修正（局部 host 被 GC 连带销毁对话框子树须保活；ArrowCursor 断言值写错）均为测试脚本问题，非功能缺陷。

### 调整：详情页键值表左右对齐 + 宽度收窄（2026-11-19）

- 需求：文件信息详情页左列右对齐、右列左对齐，整体宽度窄一点。
- 方案（`app/components/file_info_dialog.py`）：键 `CaptionLabel` 与值 `BodyLabel` 的 `setAlignment` / `addWidget` 对齐标志改为 `AlignRight|AlignVCenter`（左列）与 `AlignLeft|AlignVCenter`（右列），值贴近键列起排、扫读更顺；路径跑马灯保持 `AlignVCenter` 拉伸（其内部文本本就左对齐，与右列一致，不能加水平对齐标志否则无法溢出滚动）。`widget` 宽度 460–560 → **380–430**（实测 380），去掉居中留白。
- 验证：py_compile 通过；6 组断言全过（宽度 380 / 14 键右对齐 / 值左缘对齐 / 两列间距 21px 无重叠 / 路径收窄后仍自动滚动 / 值行有效布局）；渲染截图确认对齐与紧凑度；offscreen 启动 15s 无错误。未打包。

### 完善：完整路径跑马灯改为自动滚动 + Fluent 风格悬停提示（2026-11-19）

- 需求：路径跑马灯需自动滚动（不再要求鼠标悬停）；路径的悬停提示改用 Fluent 组件，不用系统原生黑框。
- 方案（`marquee_label.py`）：新增 `auto` 开关，默认 `False` —— 列表卡片仍「悬停才滚、静止零开销」，**不破坏上一轮的性能优化**（几百张卡不会常驻定时器）；`auto=True` 时溢出即自动滚动、跳过起始延迟保留起步加速；补 `showEvent` 与既有 `hideEvent` 配对，重新显示可恢复滚动。
- 方案（`file_info_dialog.py`）：路径传 `auto=True`；原生 `setToolTip` 换成项目统一的 Fluent 提示范式 `ToolTipFilter(showDelay=300, position=BOTTOM)` + `setToolTipDuration(-1)`，富文本 `<b>完整路径</b>...`，过滤器由 `self._path_tip` 持有防 GC；`_PathClickFilter` 简化为只处理点击定位，hover 一律放行，保证与 `ToolTipFilter` 事件过滤器链互不干扰。
- 验证：py_compile 通过；8 组断言全过（卡片零开销/自动启动/offset 推进/短文本不空转/hide-show 恢复/两过滤器共存/对话框装配/渲染激活后自动滚动）；真实事件循环 400ms 推进 21.4px（≈55px/s，与既定速度一致）；offscreen 启动 15s 无错误；渲染截图确认路径单行无重叠。未打包。

### 修复：文件信息对话框「完整路径」改为单行跑马灯（2026-11-19）

- 问题：路径过长时 `BodyLabel` 自动换行，与其他字段行重叠遮挡。
- 方案：路径值改用 `MarqueeLabel`（单行、悬停首尾相连无缝滚动），不再换行。
  - `marquee_label.py`：新增 `bold` 参数（默认 True 兼容卡片），对话框传 False 用普通体；新增 `setTextColor()` 直接作用每份文本（Fluent 全局 QSS 会覆盖父控件 stylesheet），第二份文本继承颜色。
  - `file_info_dialog.py`：`_PathClickFilter` 扩展为 hover 启停 + 左键定位；路径行去掉水平居中改 `AlignVCenter`，让跑马灯拉伸填满列宽（Ignored 策略）才能检测溢出并滚动；颜色刷新改走 `MarqueeLabel.setTextColor()`。
  - 提示语更新为「过长可悬停滚动 · 点击打开文件所在位置」；其余字段行、右键菜单、主题切换均不受影响。
  - 验证：py_compile 通过；6 组断言（字体策略/颜色继承/单行/hover 启停/过滤器/对话框装配）全过；渲染激活后路径列宽 442px、need_scroll=True；offscreen 启动 15s 无错误。

### 优化：媒体探测性能——封面 + 标签合并为一次 ffmpeg（2026-11-19）

- **需求**：逐代码读取后提升性能 / 优化算法。
- **根因（逐行定位 + 实测）**：已解密页对同一文件起**两次** ffmpeg 进程——`_CoverRunnable`→`extract_cover_bytes`（封面）与 `_TagRunnable`→`probe_audio_info`（标签）各自读一遍。实测两次调用 2.972s/20 轮，一次调用 1.546s/20 轮（**约 1.92×**）。
- **方案（零新增依赖）**：
  - `app/common/media_info.py`：抽出 `_parse_media_text()` / `_run_ffmpeg()` 复用；新增 `probe_media(ffmpeg, path)`——**一次** ffmpeg（`-map 0:v:0? … pipe:1`）stdout 取封面 PNG（签名校验）、stderr 解析完整元数据（标签在 stderr 出现两次，正则取首次；不靠 returncode 判成败，无封面时非 0 属正常）。`probe_audio_info()` 保留（对话框用），改为复用解析函数；新增 `_PNG_SIGNATURE`。
  - `app/common/cover_loader.py`：`CoverCache.MISS` 类级别名（= 模块哨兵 `CACHE_MISS`）。
  - `app/view/decrypted_interface.py`：两个 runnable / 两个队列 / 两个信号 / 两个 pending 合并为一个 `_MediaRunnable` + `_media_results` + `mediaDone` + `_media_pending`；统一 `_ensure_media(item)`（封面懒加载与标签归类共用，按 item 去重——同文件只起一个进程，视口内文件的标签在提封面时顺便拿到）；`_on_media_done()` 一次回填封面 LRU + `_tags` + `_media_info`（完整 info）。新增 `_media_info` 缓存供 `_show_file_info()` 复用，命中免重复起进程。`_lazy_filter()` sort key 改为单次取标签值（原每元素调 2 次 `_tag_of`）。
- **验证（仅源码，未打包）**：py_compile 全过；8 组单元断言全 PASS（probe_media 三场景、probe_audio_info 完整字段、CoverCache.MISS、同 item 去重只提交一次、一次回填三缓存、归类排序、info 缓存复用、runnable 四元组产出）；实测 1.92× 提速；offscreen 启动 15s 无错误、配置值与默认一致（config.json 被 gitignore）。未执行任何打包命令。
- 注：`probe_media` 每次调用仍解析全套字段（对话框可能需要），归类只用 artist/album 但进程只起一次，解析开销相对进程启动可忽略；未合并封面 LRU 与标签缓存（前者有上限会淘汰、后者需全量，语义不同）。

### 新增：已解密页分类「歌手名 / 专辑名」归类（2026-11-19）

- **需求**：已解密页顶部分类下拉再加两项「歌手名」「专辑名」，匹配相应分类规则（用户选定：按歌手/专辑归类——同值相邻、无信息排末尾）。任务管理页零改变。
- **方案**：零新增依赖，复用内置 ffmpeg 元数据探测 + 后台批量 + 缓存。
  - `app/common/media_info.py`：新增 `guess_artist_from_name()`——无内嵌歌手标签时按文件名「歌名 - 歌手」回退解析（正则取最后一段分隔符，排除 `[]()` 等后缀噪声）；专辑名无法从文件名可靠推断，只依赖内嵌标签。
  - `app/view/decrypted_interface.py`：下拉扩为「全部/已解密/已添加/歌手名/专辑名」（宽度 104→112）；新增 `_TagRunnable`（后台单文件探测，数据走 queue + 无参信号，沿用避坑模式）+ `_tags` 缓存（item 含 mtime，刷新后失效）+ `_tag_pending` 去重 + 120ms 防抖重排；`_lazy_filter()` 在标签分类下按 `(有值=0/无值=1, 值.casefold())` 稳定排序——同值相邻、无值末尾、组内保持原 mtime 倒序。切换分类 / 首次扫描完成均触发 `_ensure_tags()`。
- **验证（仅源码，未打包）**：py_compile 全过；8 组单元断言全 PASS（文件名解析含多分隔符/噪声、下拉五项、歌手与专辑归类同值相邻+无值末尾+组内倒序、大小写不敏感、全部回归原顺序、回填触发防抖重排、非归类不无谓重排）；offscreen 启动 15s 无错误日志、配置未改动。
- 注：归类按 Unicode 码点升序（中文非拼音序，仅保证同值相邻）；千级文件首次切分类时后台逐个探测（几十 ms/个），列表随回填渐进归类。

### 调整：跑马灯滚动速度放慢（2026-11-19）

- **需求**：跑马灯效果慢一点。
- **改动**：`app/components/marquee_label.py` 的 `MarqueeLabel._SPEED` 由 85 → 55 像素/秒（约 65%），长文件名滚动更从容；起始延迟 `_START_DELAY`、起步加速 `_RAMP`、帧间隔 `_INTERVAL` 均不变，保留启动跟手性。滚动为时间驱动，帧率波动不影响观感速度。
- **验证（仅源码，未打包）**：py_compile 通过；单帧断言 55px/s 下 16ms 位移 0.88px（原 85px/s 为 1.36px），其余时序参数不变。

### 完善：信息对话框 label 居中 + 路径点击定位文件（2026-11-19）

- **需求**：文件信息对话框 label 居中；完整路径可点击，点击打开所在位置。
- **改动**：
  - `app/components/file_info_dialog.py`：标题 + 键值表所有 label（`CaptionLabel`/`BodyLabel`）改为 `Qt.AlignCenter`；完整路径值做成强调色手型可点击标签，`_PathClickFilter`（QObject 事件过滤器）捕获左键 → `_open_location()`；路径色随 `themeChanged`/`themeColorChanged` 刷新；失败 toast 提示。
  - `app/common/utils.py`：新增 `open_file_location(path)`——Windows `explorer /select,"path"` 定位并选中，macOS `open -R`，Linux `xdg-open` 打开目录；路径不存在/OSError 返回 False。
- **关键坑**：① Fluent 标签（BodyLabel）的 `__init__` 是 `singledispatchmethod`，子类化会触发重载递归崩溃 → 改用事件过滤器，不继承；② 过滤器须由 self 持有，否则被 GC 回收静默失效；③ 过滤器回调的 `path` 闭包须从 `_add_rows(path)` 参数传入（用 `__init__` 局部变量会 NameError）。
- **验证（仅源码，未打包）**：py_compile 全过；单元断言全 PASS（标题+28 label 全居中、路径手型/可点击、点击触发定位、主题色刷新、失败 toast、explorer 命令正确、不存在路径/OSError 返回 False）；端到端右键弹窗→点击路径→定位链路通过；offscreen 启动 12s 无错误、配置未改。

### 新增：已解密页右键「查看信息」（2026-11-19）

- **需求**：已解密列表右键增加查看信息功能，点击弹出对话框显示详细文件信息；适配主题切换。任务管理页零改变。
- **方案**：零新增依赖，复用内置 ffmpeg 探测元数据 + Fluent 对话框。
  - `app/common/media_info.py`（新）：`probe_audio_info()` 调用 `ffmpeg -i` 解析 stderr，提取时长/整体码率/编码/采样率/声道（中文化）/标题/艺术家/专辑；探测本质是读文件头、非 3s 超时即静默返回空字典；失败（文件不存在/损坏/ffmpeg 缺失）全静默，不打断调用方；遵循分层不依赖 UI。
  - `app/components/file_info_dialog.py`（新）：`FileInfoDialog(MessageBoxBase)` 键值表展示 14 字段（文件名/完整路径/大小/修改时间/来源/格式 + 音频参数 + 标签），值可选中复制、长路径自动换行；全 Fluent 控件随主题/强调色自动切换；仅保留「关闭」按钮。
  - `app/view/decrypted_interface.py`：右键菜单新增「查看信息」（`FluentIcon.INFO`，置于播放/删除之前）→ `_show_file_info()` 收集预取 stat + 来源缓存 + ffmpeg 元数据，弹出对话框；探测失败对缺失字段显示「—」。
- **验证（仅源码，未打包）**：py_compile 全过；单元断言——4 种格式（mp3/flac/m4a/wav）元数据解析准确含中文标签、无元数据/损坏/不存在/无 ffmpeg 路径全静默、对话框 14 字段双主题完整、空数据显示占位符、右键菜单三项顺序正确、点击槽端到端字段齐全；offscreen 启动 12s 无错误、配置未改动。
- 注：音频探测为用户主动点击时的同步单文件调用（几十毫秒），不进入列表主流程；ogg/ape/wv 等冷门格式的标签解析未逐一实测，缺失字段回退「—」。

### 新增：已解密列表内嵌专辑封面（仅已解密页）（2026-11-19）

- **需求**：已解密页卡片最左侧显示文件内嵌专辑封面缩略图；任务管理页零改变；适配主题 / 强调色切换。
- **方案**：零新增依赖，复用内置 ffmpeg + PySide6 QImage（可行性分析见 `docs/已解密列表-内嵌专辑封面可行性分析.md`）。
  - `app/common/cover_loader.py`（新）：`extract_cover_bytes()`（ffmpeg `-map 0:v:0?` 提取首张内嵌图为 PNG 字节流，无封面/损坏/超时静默返回 None，Windows 抑制黑框）+ 线程安全 LRU `CoverCache`（键 `(路径,mtime)`，`None` 亦缓存避免反复起进程）。
  - `app/components/task_card.py`：`cover=False` 可选参数——仅已解密页传 True 才创建 44×44 圆角封面位；任务页默认不创建，布局零改变。无封面显示主题强调色淡底 + 音符占位图；`set_cover()` / `refresh_cover_placeholder()`（后者只重绘仍为占位图的卡片，不覆盖真实封面）。
  - `app/view/decrypted_interface.py`：`_CoverRunnable`（后台提取 + 无参信号 + queue，避开跨线程封送坑）；`_make_card(cover=True)` → `_apply_cover()`（命中缓存直接设图，未命中提交后台、按 item 去重）；`_on_cover_done()` 按 `_card_cache` + `_lazy_item` 一致性回填、过时结果丢弃；`themeChanged`/`themeColorChanged` → 重绘占位图。
- **验证（仅源码，未打包）**：py_compile 全过；单元断言 6 组全 PASS（端到端提取/无封面静默、任务页零改变、真实封面主题切换保护、占位图随强调色重绘、缓存命中、异步回填+过时丢弃）；端到端实测带封面 mp3 提取 PNG 成功；offscreen 启动 12s 无错误、配置未改动。
- 注：ogg/ape/wv 等冷门格式封面未实测，回退占位图。

### 修复：任务列表显示顺序——未解密在上、已解密在下（2026-11-19）

- **现象**：任务管理页文件顺序杂乱，已解密与未解密混杂，不符合「未解密在上、已解密在下」的期望。
- **根因**：任务页已有 `_sort_cards()`（按 `pending→running→failed→skipped→success` 排序）但仅在 `_relayout()` 时调用。① 渐进填充路径 `_fill_next_chunk()` 按目录扫描顺序逐张补格，不经 `_sort_cards()`，首次加载 / 刷新重建后顺序即为扫描顺序；② 转换完成逐文件只更新卡片状态、不重排，已解密卡片停留在原位。
- **修复**：
  - `app/components/grid_card_container.py`：新增 `_sort_items(items)` 钩子（默认原样），在 `_replace_cards()` 重建入口统一调用，使渐进 / 非渐进 / 懒加载三条路径都按预排序顺序建卡；稳定排序保持组内相对次序。
  - `app/view/task_interface.py`：新增 `_item_status(path)`（已解密优先于在途快照，与建卡判定同源）与 `_sort_items()` 覆写（按状态优先级预判排序）；连接 `conversion_finished` → `_relayout()`，整批转换结束后一次性把已解密卡片沉底——转换过程中仍逐文件只更新状态，避免整页跳动。
  - 已解密页未覆写钩子，保持按修改时间倒序不变。
- **验证（仅源码，未打包）**：py_compile 通过；单元断言 5 组全 PASS（状态判定 / 稳定预排 / 渐进重建首次扫描顺序 / 转换完成沉底且逐文件阶段不重排 / 已解密页顺序不变）；offscreen 启动 10s 无错误、配置未改动。

### 修复：深色模式下列表浅底白字 + 外观设置组件统一（2026-11-19）

- **现象（用户截图报告）**：深色模式下「已解密」页文件卡片呈浅灰白底 + 白色文字，几乎看不清；同时外观设置用了与转换设置不同的组件（展开式单选 vs 下拉框）。
- **根因（实测定位）**：`GridCardContainer` 的 `scrollContent`（`QWidget`）被 `setWidgetResizable(True)`/`setWidget()` 置为 `autoFillBackground=True`，其 palette 的 Window 色不随主题切换（深色下仍是 `#efefef`）；`CardWidget` 背景是半透明白（深色 alpha=13）叠在该浅色底板上 → 浅底，`StrongBodyLabel` 文字却是 dark 版白色 → 白字。诊断截图与用户截图完全一致。
- **修复**：
  - `app/components/grid_card_container.py`：在 `scrollArea.setWidget(self.scrollContent)` **之后** `setAutoFillBackground(False)`（顺序关键：setWidget 会重置为 True），让内容区透明、透出 viewport 深色底。任务页 / 已解密页两页共用基类同时受益。
  - `app/view/setting_interface.py`：主题卡片由 `OptionsSettingCard` 改为 `ComboBoxSettingCard`（与转换设置一致），仍绑定枚举型 `qconfig.themeMode`；`comboBox.currentIndexChanged` → `_on_theme_changed(index)` 用 `itemData(index)`（Theme 枚举）调 `setTheme` 刷新全局 QSS。
- **验证（仅源码，未打包）**：py_compile 通过；单元断言全 PASS——两页内容区 autoFill=False、下拉三项文本正确、卡片类型为 ComboBoxSettingCard、三项切换写对 themeMode 且各触发一次 `themeChangedFinished`（QSS 刷新）、深色卡片背景 alpha=13；修复前/后深色截图对比确认「浅底白字」→「深底白字」；offscreen 启动 10s 无错误、配置未改动。

### 完善：跟随系统实时换肤（2026-11-19）

- **需求**：主题选「跟随系统」时，系统深浅色在运行中切换应实时生效（上一轮实现只在启动/手动切换时读取一次）。
- **依据**：QFluentWidgets 官方主题指南（`/pages/theme` → Follow system theme）+ 库源码 `theme_listener.py`。
- **方案**（`app/view/main_window.py`）：
  - `init_theme_listener()` 创建并 `start()` `SystemThemeListener`；`systemThemeChanged` → `_on_system_theme_changed` → `setTheme(Theme.AUTO)`。
  - **关键坑**：官方 listener 在系统主题变化时只改 `qconfig.theme` 并发 `themeChanged`/`systemThemeChanged`，**不刷新全局 QSS**；必须接 `setTheme()` 由其 `updateStyleSheet()` 才能全体换肤。
  - listener 内部自带门控——仅 `themeMode==AUTO` 时响应，手动浅/深色下系统切换不干扰（已实测确认）。
  - 生命周期：Windows 上 `darkdetect.listener` 为无限阻塞循环，只能 `terminate()`；抽出幂等 `_stop_theme_listener()`，`closeEvent` 与 `on_exit`（aboutToQuit）双路径调用，避免 QThread 运行中被销毁。
- **验证（仅源码，未打包）**：py_compile 通过；单元级 monkeypatch `darkdetect.theme` 全 PASS——LIGHT/DARK 模式门控不响应、AUTO 下解析为 DARK 且 `themeChangedFinished` 触发（确认全局刷新）、重复停止幂等；offscreen 启动 12s 无 QThread/异常日志，config.json 未改动。

### 新增：主题切换（跟随系统 / 浅色 / 深色）（2026-11-19）

- **需求**：设置页增加「外观设置」分组，提供三种主题模式——跟随系统、浅色模式、深色模式。
- **方案**：复用 QFluentWidgets 内置主题系统，不自建主题状态。
  - `app/common/config.py`：`qconfig.load` 后把 `qconfig.themeMode` 的选项顺序由库默认 `LIGHT/DARK/AUTO` 重排为 `AUTO/LIGHT/DARK`（只改 `validator.options` 顺序，`Theme` 枚举值不变），使界面按「跟随系统 / 浅色 / 深色」呈现。
  - `app/view/setting_interface.py`：新增 `OptionsSettingCard` 绑定 `qconfig.themeMode`（texts 与重排后 options 一一对应）；连接 `optionChanged` → `setTheme(qconfig.get(item))`。
  - **关键点**：`OptionsSettingCard` 点击仅经 `qconfig.set` 写入配置并发出 `themeChanged`，**不会**刷新全局 QSS；必须显式调用 `setTheme()`（内部 `updateStyleSheet`）才能让所有 Fluent 控件换肤。
  - 持久化沿用库 `themeMode`（已存在于 config.json 的 `QFluentWidgets.ThemeMode`），`setTheme` 写盘；「跟随系统」在 `qconfig.theme` setter 内由 `darkdetect` 解析为实际浅/深。
- **验证（仅源码，未打包）**：`py_compile` 4 个相关文件通过；offscreen 启动 `main.py` 持续 12s 无异常、config.json 未被启动流程改动；单元级断言全 PASS——选项顺序 `[AUTO,LIGHT,DARK]`、按钮文本 `跟随系统/浅色/深色`、逐项点击后 `themeMode`/`qconfig.theme` 正确（AUTO 解析为 LIGHT）、DARK↔AUTO 可来回切换；验证后 config.json 已还原。

### 修复：清空列表后刷新列表不显示文件（2026-11-17）

- **现象（用户 2026-11-17 报告）**：点「清空列表」→ 点「刷新列表」看不到文件；「删除完成」后再刷新同样看不到。
- **根因**：`TaskInterface.clear_files()` 直接调用基类 `_clear_cards()`，逐卡回调的 `_on_card_removed()` 把全部路径写进 `_excluded_paths`；此后 `scan_directory()` 用排除表过滤扫描结果，整批文件被剔除，刷新永远为空（重启、排除表清空后才恢复）。「删除完成」路径在 11-09 已加 `_view_only_removal` 保护，但若本次运行中先做过清空 / 移出，排除表已污染，后续任何刷新（含删除完成后）都显示为空。
- **修复**（`app/view/task_interface.py`）：`clear_files()` 复用 `_view_only_removal` 上下文标志（`try/finally`），只移除卡片、不登记排除。语义统一为 **清空列表 / 删除完成 = 只清视图，刷新重扫**；**移出列表 / 删除文件 = 主动排除，刷新不回来**（保持 #8 契约）。
- **验证**：`unclock_verify_clear_refresh.py` offscreen **6/6 PASS**——清空→刷新恢复、删除完成→刷新恢复、删除完成+清空→刷新恢复、移出列表不回来、磁盘删除不回来、清空后手工添加条目仍保留；用户真实目录（输入 323 文件 / 输出 176 文件、任务页 164 张卡）实测清空→刷新与删除完成→刷新均恢复 164 张。
- 注：随后按用户要求，工具栏「清空列表」按钮已改为「开始解密」，`clear_files()` 一并移除，见下一条。

### 修复：启动脚本控制台行首出现长串空白 / 中文注释被当命令执行（2026-11-17）

- 现象一：双击 [启动程序.bat](file:///c:/Users/luck/Desktop/unclock/启动程序.bat) 运行，程序退出后 `Press any key to continue . . .` 前面多出一长串空格。
- 现象二：脚本报 `'…着这串空格显示（行首空白）。' is not recognized as an internal or external command`，即注释片段被当成命令执行。
- 原因一：脚本用 `uv run` 启动后，uv 进度条结束时用一长串空格擦除自身且不换行，光标停在行中间；之后 `pause` 紧接光标位置输出，提示语就落在空格串之后（直接跑 `python main.py` 没有这一步）。
- 原因二：`chcp 65001` 切换到 UTF-8 后，cmd 按字符偏移续读批处理文件，文件中含中文注释时偏移会错位，导致半行注释被当作命令执行；注释越长越容易踩中（新增两行长注释后必现）。
- 修复：`uv run --no-progress main.py`（不再绘制/擦除进度条）+ 批处理内容全部改为纯 ASCII 注释（不依赖控制台编码，彻底避免错位）。
- 验证：同结构测试脚本（UTF-8 中文注释）复现两类报错；改为纯 ASCII 后执行 `uv run --no-progress python -c ...` 输出 `app-ok` / `bat-finished`，无任何报错或残留空格；正式脚本非 ASCII 字节数为 0。

### 变更：主页横幅高度改为窗口高度的三分之一（2026-11-17）

- `AutoResizeFlipView.sync_geometry()` 按 `窗口高度 // 3` 设定横幅高度并同步 `setItemSize`（宽度仍拉满整行，图片按“填满裁切”绘制）；页面与横幅自身的 `resizeEvent` 都会调用，窗口宽 / 高任一变化都实时跟随（1080×760 窗口下横幅为 947×253）。

### 变更：为所有按钮补齐 Fluent 工具提示（2026-11-17）

- 任务页「添加文件 / 刷新列表 / 删除完成 / 开始解密」、已解密页「刷新列表 / 打开目录」、配置页五个「选择目录 / 选择文件」按钮统一加 `ToolTipFilter`（`showDelay=300`、`ToolTipPosition.TOP`）+ `setToolTipDuration(-1)`，文案为「加粗标题 + 换行说明」，与主页 / 日志页既有提示一致；过滤器由各页面持有，避免被回收失效。

### 变更：任务页「清空列表」改为「开始解密」（2026-11-17）

- 工具栏按钮改为 `TransparentPushButton(FluentIcon.PLAY, "开始解密")`，与「添加文件 / 刷新列表」同一组件、图标沿用主页「开始解密」；点击改为发出 `signalBus.request_start`（走主页同一分发链路），不再清空列表。
- 随之移除 `TaskInterface.clear_files()`（原仅为该按钮服务）。

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
