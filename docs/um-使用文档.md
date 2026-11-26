# um（Unlock Music CLI）使用文档

> Go 版解锁核心，**本项目默认解密引擎**。一条命令完成解密、密钥库查询与输出，支持格式最广。
> 本机版本：`v0.2.20 (go1.27.2, windows/amd64)`；官方仓库：<https://git.um-react.app/um/cli>

---

## 1. 基本用法

```bash
um -i <加密文件或目录> [-o <输出目录>] [选项]
```

示例：

```bash
# 解密单个 NCM，输出到当前目录
um -i "D:/music/song.ncm"

# 批量解密到指定目录，覆盖同名输出
um -i "D:/music" -o "D:/music/out" --overwrite

# 查看支持格式 / 查看版本
um --supported-ext
um -v
```

> `-i` 可指向文件也可指向目录；目录模式会递归处理其中受支持的加密文件。

## 2. 全局选项（来自 `um --help` 实测）

| 选项 | 说明 | 默认 |
|---|---|---|
| `--input`, `-i <path>` | 输入文件或目录 | — |
| `--output`, `-o <dir>` | 输出目录 | 当前目录 |
| `--qmc-mmkv`, `--db <path>` | QQ 音乐 MMKV 数据库路径 | — |
| `--qmc-mmkv-key`, `--key <16 chars>` | MMKV 密钥（16 位 ASCII） | — |
| `--qmpc-mmkv-cli-exe <path>` | qmpc-mmkv-cli 路径（v0.1.1+，Windows 自动取 QMC 密钥） | `./qmpc-mmkv-cli.exe` |
| `--qmc-android-db <path>` | 安卓 QQ 音乐 `player_process_db` 路径 | — |
| `--kgg-db <path>` | 酷狗 v11 本地 `KGMusicV3.db` 路径 | — |
| `--remove-source`, `--rs` | 删除源文件 | `false` |
| `--skip-noop`, `-n` | 跳过无动作解码器 | `true` |
| `--ignore-known-non-music-ext` | 跳过无扩展名及已知非音乐扩展 | `true` |
| `--no-ignore-known-non-music-ext` | 反向选项 | `false` |
| `--verbose`, `-V` | 详细输出 | `false` |
| `--update-metadata` | 从网络更新元数据与专辑封面 | `false` |
| `--overwrite` | 覆盖同名输出而不询问 | `false` |
| `--watch` | 监听输入目录并处理新增文件（长驻） | `false` |
| `--supported-ext` | 打印支持的扩展名后退出 | `false` |
| `--help`, `-h` / `--version`, `-v` | 帮助 / 版本 | — |

**注意**：绝大多数开关**只有开启形式，没有 `--no-*` 关闭形式**。例如 `-n` 默认开启，传 `-n` 与默认行为一致；不传也无法关闭。

## 3. 支持格式（`um --supported-ext` 实测）

`flac`、`m4a`、`mp3`、`ogg`、`wav`、`aac`、`bkc ape/flac/m4a/mp3/ogg/wav/wma`、`kgg`、`kgm`、`kgm.flac`、`kgma`、`kwm`、`mflac` 及 `mflac0/1/2/a/h/l/m`、`mgg` 及 `mgg0/1/2/a/h/l/m`、`mmp4`、`ncm`、`qmc0/2/3/4/6/8`、`qmcflac`、`qmcogg`、`tkm`、`tm0/2/3/6` 等。

## 4. 在本项目（unclock）中的集成

- 设置页「解密工具」选择 **um（Go · 原链路）** 时使用本引擎；**默认值**，不改变既有行为。
- 六个三态选项与命令行参数一一对应：

| 设置项 | 参数 | um 默认 |
|---|---|---|
| 删除源文件 | `--rs` | 关闭 |
| 详细输出 | `-V` | 关闭 |
| 覆盖输出 | `--overwrite` | 关闭 |
| 监听输入目录 | `--watch` | 关闭 |
| 更新封面 | `--update-metadata` | 关闭 |
| 跳过无动作解码器 | `-n` | **开启（无关闭参数）** |

选「否」时因缺少关闭参数仍按默认执行，界面会给出明确提示。

- QMC 类文件会自动附加 `--qmpc-mmkv-cli-exe <路径>`，无需手工配置密钥。
- um 查找 ffmpeg 依赖 `PATH`，本项目把 `tools/ffmpeg.exe` 所在目录前置注入子进程环境，供 `--update-metadata` 使用。
- 调度层对需要密钥查询的 QMC 文件使用同一条串行 lane，避免并发争用密钥工具；同名输出基名也串行，防止撞名。

## 5. 常见问题

| 现象 | 原因 / 处理 |
|---|---|
| `qmpc-mmkv-cli.exe` 未生效 | 确认路径有效；默认相对路径 `./qmpc-mmkv-cli.exe` 基于工作目录，建议显式传绝对路径 |
| QQ 音乐文件仍提示缺密钥 | 确认已安装并登录过 QQ 音乐客户端，本机 MMKV 数据库存在；或显式指定 `--qmc-mmkv` + `--qmc-mmkv-key` |
| `--update-metadata` 很慢 | 该选项会联网获取封面与元数据，离线环境建议关闭 |
| `-v` 与 `-V` 混淆 | `-v` 是**版本**，`-V` 是**详细输出**；与 um-cli-rs 正好相反 |

更多 QQ 音乐密钥细节见 [qmpc-mmkv-使用教程.md](qmpc-mmkv-使用教程.md) 与 [qmpc-mmkv-cli-使用文档.md](qmpc-mmkv-cli-使用文档.md)。
