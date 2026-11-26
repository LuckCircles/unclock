# qmpc-mmkv-cli 使用文档

> QQ 音乐 MMKV 密钥提取工具（LSR@UnlockMusic）。本机 `tools/qmpc-mmkv-cli.exe -V` 输出 `1.0.4 <commit>`。
> 官方仓库：<https://git.um-react.app/um/qmpc-mmkv>
>
> 原理、HWID 推导与深度排错见同目录 [qmpc-mmkv-使用教程.md](qmpc-mmkv-使用教程.md)；本文聚焦命令行用法与本项目集成。

---

## 1. 基本用法

```bash
qmpc-mmkv-cli [options]
```

| 选项 | 说明 |
|---|---|
| `-h`, `--help` | 帮助 |
| `-v`, `--verbose` | 详细日志，等价于 `--level verbose` |
| `-V`, `--version` | 版本与提交号后退出 |
| `-l`, `--level <level>` | 日志级别：`trace / debug / verbose / info / warning / error / fatal`（默认 `info`） |
| `-c`, `--command <cmd>` | `dump`（默认）或 `system-id` |

`dump` 子命令选项：

| 选项 | 说明 |
|---|---|
| `-i`, `--input <file>` | 输入 MMKV 文件；默认由 `system-id` 推导 |
| `-k`, `--key <16 chars>` | 16 字符密钥；默认由 `system-id` 推导 |
| `-o`, `--output <file>` | 输出文件，默认 `qmpc-mmkv-v1.mmkv`；**`-` 表示 stdout** |
| `-f`, `--format <fmt>` | `raw`（默认）或 `plaintext` |
| `-F`, `--filter <name>` | 只输出指定 MMKV 键名（仅 `plaintext` 有效） |
| `-m`, `--method <m>` | `hwid`（默认）或 `rpc` |

**版本参数是 `-V`，不是 `-v`**：`-v` 是 verbose，会真实执行密钥提取并可能写出 `qmpc-mmkv-v1.mmkv`。

## 2. 常用命令

```bash
# 查看版本 / 系统标识
qmpc-mmkv-cli -V
qmpc-mmkv-cli -c system-id

# 导出全部键（plaintext 为 key\nvalue\n 交替行）
qmpc-mmkv-cli -o - -f plaintext

# 只取某一首歌的 ekey（本项目 um-cli-rs 引擎使用的形式）
qmpc-mmkv-cli -o - -f plaintext -F "<musicexMediaFilename>"

# 导出为文件（默认相对路径，注意会写盘）
qmpc-mmkv-cli -o qmpc-mmkv-v1.mmkv
```

`plaintext` 输出按两行一组解析：

```text
<键名>
<键值>
<键名>
<键值>
```

本项目 `_fetch_musicex_ekey()` 正是按「奇数行键 / 偶数行值」组成字典，再用媒体文件名查值。

## 3. 在本项目（unclock）中的两种调用路径

| 引擎 | 调用方式 | 时机 |
|---|---|---|
| `um`（Go，默认） | `um.exe ... --qmpc-mmkv-cli-exe <路径>`，由 um 自行调用 | 解密 QMC 类文件时自动附加 |
| `um-cli-rs`（Rust） | `um_cli_rs qmc2 -I` 得到 `metadataType=MusicEx` 且 `ekey` 为空时，直接执行 `qmpc-mmkv-cli -o - -f plaintext -F <文件名>` | 仅在确实缺 ekey 时调用 |

两种路径都把需要密钥查询的 QMC 文件归入同一条串行 lane，避免并发争用同一密钥工具。

## 4. 重试与错误码

| 退出码 | 含义 | 处理 |
|---|---|---|
| `0` | 成功 | 解析 stdout 键值表 |
| `5` | CRC 读取错误 / read-on-write 竞争 | 官方实现重试 5 次，本项目同样处理 |
| 其他 | 工具或环境错误 | 记录 stderr，该文件解密失败并跳过 |

当 `metadataType=MusicEx` 但 `-F <文件名>` 查不到键时，说明本机 MMKV 中没有这首歌的密钥；
可确认 QQ 音乐客户端是否已登录并播放过该歌曲，或切回 um 引擎并显式指定 `--qmc-mmkv` / `--qmc-mmkv-key`。

## 5. 注意事项

- 默认输出 `qmpc-mmkv-v1.mmkv` 会写在**当前工作目录**；只想读密钥时用 `-o -`。
- `-F` 要求**精确匹配** MMKV 键名，不是模糊搜索；`um-cli-rs` 的 `-I` 已给出 `musicexMediaFilename`，照抄即可。
- 版本探测请以首页工具卡片或 `-V` 为准；旧教程中「v0.1.1 / v1.0.0」是历史集成说明，与当前二进制版本可能不同。
- 该工具不含 ADB 取密钥能力；安卓侧密钥需要另行接入 ADB 方案。
