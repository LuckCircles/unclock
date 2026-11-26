# um-cli-rs 使用文档

> Rust 版离线解密工具（clap CLI），官方 GUI `um-conv` 的解密核心。本机版本 `um_cli_rs 0.1.13`；
> 发布来源：<https://git.um-react.app/um/lib_um_crypto_rust/releases/>
>
> 与 Go 版 `um` 的区别：`um` 是**单体编排器**（自己找密钥、写输出、可联网更新元数据、`--watch` 常驻）；
> `um-cli-rs` 是**纯离线单格式解密原语**，通过 `-I` 输出 JSON 先把决策权交给宿主程序。

---

## 1. 全局用法

```bash
um_cli_rs [全局选项] <子命令> [子命令选项] -- <输入文件>
```

| 全局选项 | 说明 |
|---|---|
| `-v`, `--verbose` | 输出更多过程信息（**注意**：不是版本） |
| `-B`, `--buffer-size <bytes>` | 读取缓冲，默认 `4194304`（4 MiB） |
| `-h`, `--help` | 帮助 |
| `-V`, `--version` | 版本（输出形如 `um_cli_rs 0.1.13`） |

子命令一览：`ncm`、`kgm`、`kuwo`、`mg3d`、`joox`、`qmc1`、`qmc2`、`qtfm`、`xiami`、`xmly`。

## 2. 常用子命令

### 2.1 NCM（网易云）

```bash
um_cli_rs ncm --output out.flac -c cover.jpg -m meta.json -- song.ncm
```

| 参数 | 说明 |
|---|---|
| `-o`, `--output <path>` | 输出音频路径 |
| `-c <path>` | 导出封面（JPG 或 PNG）；未找到则不会创建 |
| `-m <path>` | 导出原始元信息（JSON 字符串） |

### 2.2 QMC2（QQ 音乐 `.mflac*` / `.mgg*` / `.mmp4`）

```bash
# 第一步：只探测，不解密，输出 JSON（含 ekey，勿写入日志）
um_cli_rs qmc2 -I -- song.mflac

# 第二步：带 ekey 解密
um_cli_rs qmc2 --ekey "<ekey>" --output song.flac -- song.mflac
```

| 参数 | 说明 |
|---|---|
| `-o`, `--output <path>` | 输出文件路径 |
| `-K`, `--ekey <key>` | 指定 ekey；前缀 `decrypted:` 表示 base64 原始密钥，前缀 `@` 表示从文件读取 |
| `-I`, `--info-only` | 只打印信息 JSON，不解密 |

`-I` 输出字段：

| 字段 | 含义 |
|---|---|
| `footerLen` | 尾部元数据长度 |
| `ekey` | 内嵌密钥（可能为空） |
| `metadataType` | `PCv1` / `MusicEx` / `QTag` / `STag` |
| `musicexMediaFilename` | MusicEx 类型对应的媒体文件名（用于 qmpc 查询） |

分流规则（官方实现）：

| metadataType | 处理 |
|---|---|
| `PCv1` | 使用内嵌 ekey，长度须 ≥100 |
| `MusicEx` | 优先内嵌 ekey；为空则调用 `qmpc-mmkv-cli -o - -f plaintext -F <文件名>` |
| `QTag` | 必须内嵌 ekey |
| `STag` | 需从已 root 安卓设备取密钥（本项目未接入 ADB） |

### 2.3 KGM / KGG / VPR（酷狗）

```bash
um_cli_rs kgm -I -- song.kgm                      # 探测 cryptoVersion / audioHash
um_cli_rs kgm --output song.flac -- song.kgm       # v2/v3 直接解密
um_cli_rs kgm --ekey "<key>" --output song.flac -- song.kgm   # v5 需外部密钥
```

`--file-mode db` 用于本机密钥库：`um_cli_rs kgm -I --file-mode db -- KGMusicV3.db` 判断库是否加密；
加密时先 `um_cli_rs kgm --file-mode db --output <tmp.db> -- KGMusicV3.db` 解密到临时文件，再查询
`ShareFileItems(EncryptionKeyId, EncryptionKey)`，`EncryptionKeyId` 即音频的 `audioHash`。

### 2.4 KWM（酷我）

```bash
um_cli_rs kuwo -I -- song.kwm
um_cli_rs kuwo --output song.flac -- song.kwm
```

v1 可直接解密；v2 需要按 `resourceId` + `formatName` 从设备读取密钥，本项目未接入 ADB，会明确报错。

## 3. 官方工具链的分工

```text
加密文件
  └─ um_cli_rs <格式> -I -- <文件>       # 探测 JSON（不写日志，含 ekey）
       ├─ 内嵌 ekey → 直接解密
       ├─ MusicEx 缺 ekey → qmpc-mmkv-cli 取密钥 → 解密
       └─ STag / KWM v2 缺密钥 → ADB 取密钥（本项目未支持）
  └─ um_cli_rs <格式> --ekey <K> --output <dest> -- <文件>
  └─ ffmpeg 探测产物真实格式 → 改名落盘（本项目实现）
```

关键优化：**探测与执行分离**。先用一个极短的 `-I` 进程拿到结构化信息，再决定是否启动第二进程；
避免盲目调用密钥工具，也避免在日志里泄露密钥。

## 4. 在本项目（unclock）中的集成

- 设置页「解密工具」选择 **um-cli-rs（Rust · 官方流程）** 即启用本引擎。
- 支持范围：**NCM、KGM/KGG/VPR/KGMA、KWM、QMC2（`.mflac*` / `.mgg*` / `.mmp4`）**。
  其余加密后缀（如 QMCv1 `.qmc0/.qmc3/.tkm`、BKC 系列）请切回 um 引擎。
- um 的六个三态选项在 Rust 引擎下**不适用**，会被忽略并给出日志提示。
- 解密产物先写系统临时目录，再由 ffmpeg 探测真实 demuxer 决定扩展名后原子移动到输出目录，
  避免「`.flac` 后缀装 MP3 内容」。
- `reconvert_done=false` 时若目标文件已存在则跳过；`remove_source=是` 时成功后删除源文件。
- NCM 的 `-c` / `-m` 旁路文件在收尾时清理，不留在输出目录。
- ADB 相关能力（QMC `STag`、酷我 v2）暂未接入，遇到会给出明确错误并跳过该文件。

## 5. 与 um 引擎对照

| 维度 | um（Go） | um-cli-rs（Rust） |
|---|---|---|
| 定位 | 单体编排器 | 单格式离线原语 |
| 格式覆盖 | 最广（含 QMCv1 / BKC 等） | 官方支持的四类 |
| 密钥来源 | 内建 mmkv/db 参数 + qmpc | JSON 探测后由宿主决定（qmpc / ADB） |
| 版本参数 | `-v` | `-V` |
| 元数据联网 | `--update-metadata` | 无 |
| 目录监听 | `--watch` | 无 |
| 本项目默认 | ✅ 默认 | 设置页手动切换 |
