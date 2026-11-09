# qmpc-mmkv 使用教程

> qmpc-mmkv（LSR@UnlockMusic）是一套 QQ 音乐 MMKV 工具，核心能力是从本机 QQ 音乐客户端的密钥数据库中**自动提取 QMCv2 解密密钥**。配合 `um.exe` 使用后，解密 `.mflac / .mgg / .qmc*` 等 QQ 音乐加密文件**无需再手动填密钥**。

- 官方仓库：<https://git.um-react.app/um/qmpc-mmkv>
- 当前版本：v1.0.0（Windows x64）
- 本项目（unclock）集成版本：qmpc-mmkv-cli v0.1.1

---

## 1. 它解决什么问题

QQ 音乐的加密方案 QMCv2 把每首歌的密钥存在客户端本地的 MMKV 数据库里，而不是文件内。以前解密有两种麻烦的办法：

| 老办法 | 缺点 |
| --- | --- |
| 从安卓客户端导出 `player_process_db` | 需要手机 root / 模拟器取库（um 的 `--qmc-android-db`） |
| 手动指定 MMKV 文件 + 16 位密钥 | 密钥难找，路径和密钥都跟机器绑定 |

`qmpc-mmkv-cli` 把这一步自动化了：它根据**本机硬件标识（HWID）**直接推算出 QQ 音乐 MMKV 数据库的文件名和密钥，一条命令拿到密钥库。

## 2. 工作原理（简述）

1. 采集本机硬件标识：**网卡 ID + 磁盘 ID**，加盐后做 MD5，得到 32 位大写十六进制的 `system-id`。
2. 由 `system-id` 推导出 MMKV 数据库文件名（存放在 `C:\Users\<用户名>\AppData\Roaming\Tencent\QQMusic\` 下）和 16 字符的解密密钥（`system-id` 前 16 字符）。
3. 读取并解密该 MMKV 文件，导出其中所有歌曲密钥。

这套逻辑复现了 QQ 音乐客户端 `CommonFunction.dll` 里 ordinal 12 号导出函数的行为，纯本地计算，**不注入、不运行 QQ 音乐也能取密钥**。

## 3. 下载与安装

1. 打开官方发布页：<https://git.um-react.app/um/qmpc-mmkv/releases>
2. 下载 `qmpc-mmkv-cli-v1.0.0-amd64.zip`（约 43 KiB）。
3. 解压得到 `qmpc-mmkv-cli.exe`。
4. 放入本项目的 `tools/` 目录（与 `app/` 同级），程序启动时会**自动检测**并填入默认路径。

> 也可以在配置界面「qmpc-mmkv-cli 路径」卡片中手动指定任意位置的 exe。

## 4. 在 unclock 中使用（推荐，零操作）

本工具已完整集成，正常情况下你**不需要做任何事**：

- 首页工具卡片会显示 `QMPC MMKV` 的版本号与 READY / MISS 状态；
- 解密 QQ 音乐格式文件时，程序自动附加 `--qmpc-mmkv-cli-exe` 参数调用它取密钥；
- 非 QQ 音乐格式（ncm / kgm 等）不会触发它，日志里不会有多余的 WARN。

若首页显示 MISS：检查 `tools/qmpc-mmkv-cli.exe` 是否存在，或在配置界面重新选择路径。

## 5. 命令行直接使用

```powershell
# 查看 CLI 帮助
.\qmpc-mmkv-cli.exe --help

# 不带参数运行：按本机 HWID 推导路径与密钥，写出 qmpc-mmkv-v1.mmkv
.\qmpc-mmkv-cli.exe

# 打印 system-id / MMKV 路径与密钥（排查问题时先跑这条）
.\qmpc-mmkv-cli.exe -c system-id

# 远程调用当前运行中的 QQ 音乐客户端获取路径与密钥
# hwid 失败时再试，但从运行中的客户端提取，可能被检测
.\qmpc-mmkv-cli.exe -m rpc

# 手动指定加密 MMKV 文件与 16 字符密钥
.\qmpc-mmkv-cli.exe -i path\to\file.dat -k 0123456789ABCDEF

# 解密并输出到终端：第一行文件名，第二行密钥
.\qmpc-mmkv-cli.exe -f plaintext -o -
```

常用参数速查：

| 参数 | 说明 |
| --- | --- |
| `-m, --method <hwid \| rpc>` | 密钥获取方式，默认 `hwid`（纯算、无检测风险）；`rpc` 为备选 |
| `-l, --level <trace…fatal>` | 日志等级，默认 `info`，排查失败用 `debug` / `trace` |
| `-c system-id` | 仅打印 system-id / MMKV 路径 / 密钥，不写文件 |
| `-i, --input <file>` | 手动指定加密 MMKV 文件 |
| `-k, --key <16字符>` | 与 `-i` 配套的手动密钥 |
| `-f, --format <raw \| plaintext>` | 输出格式，`plaintext` 为 `key\nvalue\n` 成对输出 |
| `-o, --output <file>` | 输出路径，`-o -` 写到标准输出 |

## 6. 配合 um.exe 使用

`um` 原生支持该参数，转换时自动调用：

```powershell
.\um.exe -i song.mflac2 -o output\ --qmpc-mmkv-cli-exe .\qmpc-mmkv-cli.exe
```

配合 um 的其他密钥来源（可叠加使用，按需选择）：

```powershell
# QQ 音乐安卓库导入密钥（root 设备 / 模拟器中的 player_process_db）
.\um.exe -i song.mgg2 --qmc-android-db player_process_db

# 手动指定 MMKV（Windows 平台已修正，不再跳过读取）
.\um.exe -i song.mflac --mmkv-file mmkv.dat --mmkv-key 0123456789ABCDEF
```

## 7. 故障排查

| 现象 | 处理 |
| --- | --- |
| hwid 模式取不到密钥 | 先跑 `-c system-id` 看路径与密钥是否为空；仍失败再试 `-m rpc`（需 QQ 音乐客户端正在运行） |
| 输出为空 / 路径不存在 | 确认本机 QQ 音乐客户端**下载过歌曲**（未下载过的歌密钥库里不会有） |
| 怀疑推导细节问题 | 加 `-l debug` 或 `-l trace` 查看硬件标识、MMKV 路径的中间日志 |
| 中文用户名取密钥出错 | v1.0.0 已修复，请从 v0.1.1 升级到 v1.0.0 |
| um 日志出现 qmpc 相关 WARN | 检查 `--qmpc-mmkv-cli-exe` 路径是否正确、文件是否存在 |

## 8. 注意事项

- 仅能提取**本机已登录、已下载过歌曲**的密钥；换机器需重新提取。
- `-m rpc` 模式要与运行中的客户端通信，理论上存在被客户端检测的风险，优先用默认 `hwid`。
- 本工具仅供学习研究，请在合法授权范围内使用。
