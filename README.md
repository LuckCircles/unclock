# unclock

基于 PySide6 + QFluentWidgets 的 [Unlock Music](https://git.um-react.app/um/cli) (`um`) 图形化前端，提供文件管理、批量转换、实时日志与可视化配置，界面统一采用官方 Fluent 主题色。

## 功能

- **主界面**：Banner 轮播、`um` / `ffmpeg` / `qmpc-mmkv-cli` 工具检测卡片（版本 + 功能描述 + READY/MISS 状态徽章）、输入/输出目录快捷卡片、进度条 + 开始/停止合并按钮。
- **文件管理**：受支持格式列表（`ncm` / `qmc*` / `kgm` / `mgg` / `mflac*` / `vpr` / `x2m` 等加密音乐格式纳入解密；明文 `mp3/flac/ogg/wav/m4a` 等跳过），支持添加、拖入（文件或目录，目录取顶层）、刷新（仅当前目录，不遍历子目录）、删除完成后、清空列表；卡片状态徽章（待解密/解密中/已解密/失败/已跳过）与实时状态分布计数。
- **已解密页**：卡片网格展示输出目录全部音乐文件，来源徽章（本工具解密产生 →「已解密」绿；输出目录原有 →「已添加」黄）；分类下拉 + 搜索双重过滤；右键播放/删除；**懒加载**——仅视口内卡片真实创建，千级文件流畅滚动；扫描在后台线程执行（元数据一次取齐、代次号防过期）。
- **运行日志**：实时解析并展示 `um` 进程输出，按级别着色（INFO/WARN/ERROR/SUCCESS，明暗主题自适应），右上角图标按钮一键清空。
- **配置界面**：输入/输出目录、`um.exe` / `ffmpeg.exe` / `qmpc-mmkv-cli.exe` 路径，以及转换选项（删除源文件 `--rs`、详细输出 `-V`、覆盖输出 `--overwrite`、监听输入目录 `--watch`、更新封面 `--update-metadata`、跳过无动作解码器 `-n`），均以 Fluent `ComboBoxSettingCard` 呈现。

## 技术栈

| 依赖 | 版本 |
| --- | --- |
| Python | `>=3.12` |
| PySide6 | `>=6.11.0` |
| PySide6-Fluent-Widgets | `>=1.11.2` |
| loguru | `>=0.7.3` |
| Nuitka | standalone 打包 |
| 外部可执行 | `um.exe`、`ffmpeg.exe`、`qmpc-mmkv-cli.exe`（放置于项目根目录 `tools/` 目录） |

## 快速开始

```bash
# 安装依赖（推荐 uv）
uv sync

# 将 um.exe / ffmpeg.exe / qmpc-mmkv-cli.exe 放入项目根目录 tools/ 目录
# （程序会自动检测并填入默认路径）

# 启动
uv run python main.py
```

## 打包

```bash
# 预编译 qrc 资源 + standalone 多文件目录打包
uv run python build.py

# 产物：releases/音乐解锁工具.dist/音乐解锁工具.exe（内嵌三个 exe）
```

## 项目结构

参照 [Fluent-M3U8](https://github.com/zhiyiYo/Fluent-M3U8) 的分层设计，按 `common / components / service / view / resource` 五层组织：

```
unclock/
├── main.py                       # 薄入口：屏蔽推广输出 + 创建 Application + MainWindow
├── build.py                      # Nuitka standalone 打包脚本
├── tools/                        # 外部可执行工具（程序启动时自动探测）
│   ├── um.exe                     #   Unlock Music CLI
│   ├── ffmpeg.exe                 #   FFmpeg
│   └── qmpc-mmkv-cli.exe          #   QQ 音乐 MMKV 密钥提取
├── app/
│   ├── resource.qrc               # 图片资源清单（编译为 resource_rc.py）
│   ├── resource_rc.py             # qrc 编译产物（:/img/ 访问）
│   ├── common/                    # 基础设施层
│   │   ├── application.py          #   SingletonApplication 包装（Windows 命名互斥体单实例）
│   │   ├── config.py               #   QConfig + 全局 cfg（路径 / 转换选项）
│   │   ├── signal_bus.py           #   全局信号总线（解耦 view ↔ service）
│   │   ├── logger.py               #   loguru 配置
│   │   ├── resource.py             #   资源路径常量
│   │   ├── icon.py                 #   FluentIcon 别名
│   │   ├── decrypt_scanner.py      #   已解密判定（输入/输出目录「去后缀」比对）
│   │   └── utils.py                #   受支持格式 / 路径压缩 / 进程输出解析
│   ├── components/                # 可复用 UI 组件层（无自定义 QSS）
│   │   ├── interface.py            #   页面基类 Interface(ScrollArea)（sticky 工具栏）
│   │   ├── grid_card_container.py  #   卡片页骨架：固定工具栏 + 滚动网格（支持懒加载）
│   │   ├── version_card.py         #   工具版本卡片 + 流式容器
│   │   ├── path_card.py            #   主页目录快捷卡片
│   │   ├── task_card.py            #   转换任务卡片（InfoBadge 状态徽章、元数据预取）
│   │   ├── marquee_label.py        #   文件名悬停跑马灯（无缝循环）
│   │   └── empty_status.py         #   空状态提示（表情卡片 + 文案）
│   ├── service/                   # 业务服务层（封装外部进程，view 不直接碰 QProcess）
│   │   ├── tool_detector.py        #   检测 um / ffmpeg / qmpc-mmkv-cli 版本（后台线程）
│   │   └── converter.py            #   UnlockMusicConverter：批量队列 + QProcess + 超时 + 事件广播
│   ├── resources/                  # 图片资源（qrc 引用）
│   │   └── img/                    # 图标 / Banner
│   └── view/                      # 界面层
│       ├── main_window.py          #   MSFluentWindow 主窗口，持有 service 并装配页面
│       ├── home_interface.py       #   首页（banner + 工具检测 + 路径卡片 + 启动按钮）
│       ├── task_interface.py       #   任务管理（卡片式文件列表，拖入/右键/状态联动）
│       ├── decrypted_interface.py  #   已解密（懒加载卡片网格 + 后台扫描 + 条目级过滤）
│       ├── log_interface.py        #   运行日志（级别着色 + 清空）
│       └── setting_interface.py    #   配置界面
├── pyproject.toml
└── uv.lock
```

### 分层与通信

- **view ↔ service 解耦**：view 通过 `signalBus.request_start / request_stop` 驱动服务，service 反向经 `signalBus` 广播事件——`conversion_started`（含总数）、`file_started`、`file_finished`、`file_cancelled`（用户停止时标记被取消的文件）、`log_emitted`、`conversion_finished`、`tools_detected`（`ToolsReport` dataclass 载荷）；view 监听这些信号更新 UI，双方互不持有引用。
- **MainWindow 协调**：首页"开始"按钮 → `request_start` → MainWindow 从 TaskInterface 取文件列表交给 `UnlockMusicConverter.start(files)`；单文件超时（120s）自动 kill 并按失败收尾。
- **样式策略**：全部使用官方 Fluent 主题色与组件（`StrongBodyLabel / CaptionLabel / CardWidget / InfoBadge / PlainTextEdit`），无任何自定义 QSS。

### qmpc-mmkv-cli 集成

`qmpc-mmkv-cli.exe`（LSR@UnlockMusic, v0.1.1）用于从 QQ Music 的 MMKV 存储中自动提取解密密钥。`um.exe` 原生支持 `--qmpc-mmkv-cli-exe` 参数，转换时自动调用它获取 QQ Music 加密格式（`.mflac` / `.mgg` / `.qmc*`）的密钥，无需手动指定。程序在构建转换参数时自动传递该路径。

## 运行时文件

下列文件由程序运行时生成，已通过 `.gitignore` 忽略、**不纳入版本管理**：

| 文件 | 用途 |
| --- | --- |
| `config.json` | QFluentWidgets `QConfig` 持久化的路径与转换选项 |
| `app.log` | loguru 写入的运行日志（5MB 轮转） |
| `releases/` | Nuitka 打包产物目录 |

> 如需共享配置，请基于 `config.json` 自行另存为 `config.example.json`（`.gitignore` 已放行 `!*.example.json`）。

## 许可证

见 [LICENSE](LICENSE)。
