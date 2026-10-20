# unclock

基于 PySide6 + QFluentWidgets 的 [Unlock Music](https://github.com/unlock-music/cli) (`um`) 图形化前端，提供文件管理、批量转换、实时日志与可视化配置，界面统一采用官方 Fluent 主题色。

## 功能

- **主界面**：Banner 轮播、`um` / `ffmpeg` 工具检测卡片（版本 + 路径 + READY/MISS 状态徽章）、输入/输出目录快捷卡片、开始/停止转换按钮。
- **文件管理**：受支持格式列表（`ncm` / `qmc*` / `kgm` / `mgg` / `mflac*` / `vpr` / `x2m` 等加密音乐格式及常见 `mp3/flac/ogg/wav/m4a`），支持全选、添加、刷新、移除勾选、清空列表。
- **运行日志**：实时解析并展示 `um` 进程输出，自动归类 INFO / WARN / ERROR / SUCCESS。
- **配置界面**：输入/输出目录、`um.exe` / `ffmpeg.exe` 路径，以及转换选项（删除源文件 `--rs`、详细输出 `-V`、覆盖输出 `--overwrite`、监听输入目录 `--watch`、更新封面 `--update-metadata`、跳过无动作解码器 `-n`），均以 Fluent `OptionsSettingCard` 呈现。

## 技术栈

| 依赖 | 版本 |
| --- | --- |
| Python | `>=3.12` |
| PySide6 | `>=6.11.0` |
| PySide6-Fluent-Widgets | `>=1.11.2` |
| loguru | `>=0.7.3` |
| 外部可执行 | `um.exe`、`ffmpeg.exe`（放置于项目 `um/` 目录） |

## 快速开始

```bash
# 安装依赖（推荐 uv）
uv sync

# 将 um.exe 与 ffmpeg.exe 放入项目 um/ 目录（程序会自动检测并填入默认路径）

# 启动
uv run python main.py
```

## 项目结构

```
unclock/
├── main.py              # 入口：屏蔽 QFluentWidgets 推广输出后启动 GUI
├── src/
│   ├── um.py            # 主窗口、配置管理、工具检测、转换流程、首页/配置页
│   ├── list_view.py     # 文件管理页面（受支持格式与表格操作）
│   └── log_view.py     # 运行日志页面
├── img/                 # Banner 与工具图标
├── um/                  # 外部可执行文件（um.exe / ffmpeg.exe）
├── pyproject.toml
└── uv.lock
```

## 运行时文件

下列文件由程序运行时生成，已通过 `.gitignore` 忽略、**不纳入版本管理**：

| 文件 | 用途 |
| --- | --- |
| `config.json` | QFluentWidgets `QConfig` 持久化的路径与转换选项 |
| `app.log` | loguru 写入的运行日志（5MB 轮转） |
| `debug.log` | 调试日志 |

> 如需共享配置，请基于 `config.json` 自行另存为 `config.example.json`（`.gitignore` 已放行 `!*.example.json`）。

## 许可证

见 [LICENSE](LICENSE)。
