# coding: utf-8
"""um-cli-rs 解密流程的纯逻辑层（不依赖 UI / Qt）。

借鉴官方 um-conv 的分工，但按本项目实际收敛：

- 只用 um-cli-rs 官方支持的四类源：NCM、KGM/KGG/VPR、KWM、QMC2
  （`.mflac*` / `.mgg*` / `.mmp4`）。其余加密后缀请切换回 um 引擎。
- ``-I / --info-only`` 先探测 JSON，再决定是否需要外部密钥，避免把 ekey
  打进运行日志；探测与执行分离是官方实现的核心优化。
- QMC2 的 MusicEx 类型在无内嵌 ekey 时才调用 qmpc-mmkv-cli，exit=5 重试 5 次；
  PCv1 要求 ekey ≥100 字符；QTag 必须内嵌；STag 需要 ADB（本项目未接入）。
- KGM v5 从本机 KGMusicV3.db 取密钥；数据库若加密，借 um-cli-rs 解到临时
  SQLite 后用标准库 sqlite3 只读查询。KWM v2 需要 ADB，暂不支持。
- 解密产物先写临时目录，再用 ffmpeg 探测真实 demuxer 决定扩展名并原子落盘，
  避免「.flac 后缀装 mp3 内容」的错命名。
"""

import json
import os
import re
import shutil
import sqlite3
import subprocess
import tempfile
from pathlib import Path

from .task_planner import QMC_SUFFIXES
from .utils import decode_process_output

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_TIMEOUT_S = 30

_KGM_SUFFIXES = (".kgm", ".vpr", ".kgg", ".kgma", ".kgm.flac", ".kgg.flac")
_QMC2_SUFFIXES = tuple(
    s for s in QMC_SUFFIXES
    if s.startswith((".mflac", ".mgg")) or s == ".mmp4"
)
_QMC1_SUFFIXES = tuple(s for s in QMC_SUFFIXES if s not in _QMC2_SUFFIXES)

# ffmpeg demuxer 名 → 输出扩展名（与官方 avconv/detect.go 一致）
_DEMUXER_EXT = {
    "flac": ".flac", "wav": ".wav", "ogg": ".ogg", "mp4": ".m4a",
    "aac": ".aac", "mp3": ".mp3", "matroska": ".mkv", "webm": ".webm",
    "asf": ".wma",
}
_RE_INPUT = re.compile(r"(?m)^Input #0, ([^,\r\n]+)")


class RustEngineError(RuntimeError):
    """um-cli-rs 引擎无法继续解密当前文件。"""


def subcommand_for(path: str) -> str | None:
    """按后缀选择 um-cli-rs 子命令；返回 None 表示该格式不在 Rust 引擎范围。"""
    lower = str(path).lower()
    if lower.endswith(".ncm"):
        return "ncm"
    if any(lower.endswith(s) for s in _KGM_SUFFIXES):
        return "kgm"
    if lower.endswith(".kwm"):
        return "kuwo"
    if any(lower.endswith(s) for s in _QMC2_SUFFIXES):
        return "qmc2"
    if any(lower.endswith(s) for s in _QMC1_SUFFIXES):
        raise RustEngineError(
            "该 QQ 音乐格式属于 QMCv1，um-cli-rs 官方流程未覆盖；请切换回 um 引擎"
        )
    return None


def supported_formats() -> tuple[str, ...]:
    """用于设置页提示 / 文档，列出 Rust 引擎实际可处理的后缀。"""
    return (".ncm", *_KGM_SUFFIXES, ".kwm", *_QMC2_SUFFIXES)


def prepare_rust_job(path: str, basename: str) -> dict:
    """为一个任务准备临时目录、输出路径与首阶段命令。

    返回的 ``stage`` 为 ``decrypt``（NCM 可直接解密）或 ``probe``（先 ``-I``）。
    """
    subcmd = subcommand_for(path)
    if subcmd is None:
        raise RustEngineError(f"um-cli-rs 不支持该文件格式：{Path(path).name}")

    tmp_dir = Path(tempfile.mkdtemp(prefix="umrs-"))
    dest = tmp_dir / f"{basename}.decrypted"
    sidecars: tuple[str, ...] = ()
    if subcmd == "ncm":
        # 官方参数：同时导出封面与原始 JSON 元信息，随后由本模块清理旁路文件。
        cover = tmp_dir / f"{basename}.cover"
        meta = tmp_dir / f"{basename}.metadata.json"
        args = [
            "ncm", "--output", str(dest),
            "-c", str(cover), "-m", str(meta), "--", path,
        ]
        sidecars = (str(cover), str(meta))
        stage = "decrypt"
    else:
        args = [subcmd, "-I", "--", path]
        stage = "probe"
    return {
        "subcommand": subcmd,
        "args": args,
        "stage": stage,
        "dest": str(dest),
        "sidecars": sidecars,
        "tmp_dir": str(tmp_dir),
    }


def parse_probe(subcommand: str, text: str) -> dict:
    """解析 ``-I`` 的 JSON 输出；失败时抛 RustEngineError。"""
    try:
        info = json.loads(text.strip())
    except (ValueError, TypeError) as exc:
        raise RustEngineError(
            f"无法解析 {subcommand} 的探测输出（不是合法 JSON）：{exc}"
        ) from exc
    if not isinstance(info, dict):
        raise RustEngineError(f"{subcommand} 的探测结果不是 JSON 对象")
    return info


def decrypt_args_for(
    subcommand: str,
    path: str,
    dest: str,
    info: dict,
    qmpc_path: str,
    rust_path: str,
) -> list[str]:
    """根据探测结果构造第二阶段解密命令（官方 -I → --ekey → --output）。"""
    if subcommand == "qmc2":
        ekey = _qmc2_ekey(info, path, qmpc_path)
        return ["qmc2", "--ekey", ekey, "--output", dest, "--", path]

    if subcommand == "kgm":
        try:
            version = int(info.get("cryptoVersion", 0))
        except (TypeError, ValueError) as exc:
            raise RustEngineError("酷狗音频信息缺少 cryptoVersion") from exc
        key = ""
        if version in (2, 3):
            pass
        elif version == 5:
            audio_hash = str(info.get("audioHash") or "")
            if not audio_hash:
                raise RustEngineError("酷狗 v5 音频信息缺少 audioHash")
            key = _kgm_v5_key(audio_hash, rust_path)
        else:
            raise RustEngineError(f"不支持酷狗加密版本 {version}")
        args = ["kgm", "--output", dest]
        if key:
            args.extend(["--ekey", key])
        return args + ["--", path]

    if subcommand == "kuwo":
        try:
            version = int(info.get("version", 0))
        except (TypeError, ValueError) as exc:
            raise RustEngineError("酷我音频信息缺少 version") from exc
        if version == 1:
            key = ""
        elif version == 2:
            raise RustEngineError(
                "酷我 v2 需要 ADB 从设备读取密钥，本项目尚未接入 ADB；请切换回 um 引擎"
            )
        else:
            raise RustEngineError(f"不支持酷我加密版本 {version}")
        args = ["kuwo", "--output", dest]
        if key:
            args.extend(["--ekey", key])
        return args + ["--", path]

    raise RustEngineError(f"未知的子命令：{subcommand}")


def _qmc2_ekey(info: dict, path: str, qmpc_path: str) -> str:
    """QMC2 ekey 分流：PCv1/QTag 用内嵌值，MusicEx 缺值时查 qmpc。"""
    metadata_type = str(info.get("metadataType") or "")
    ekey = str(info.get("ekey") or "")
    if metadata_type == "STag":
        raise RustEngineError(
            "QMC2 STag 需要 ADB 从设备读取密钥，本项目尚未接入 ADB；请切换回 um 引擎"
        )
    if metadata_type == "PCv1" and len(ekey) < 100:
        raise RustEngineError(f"PCv1 ekey 缺失或过短（len={len(ekey)}，需 ≥100）")
    if metadata_type == "MusicEx" and not ekey:
        if not qmpc_path or not os.path.isfile(qmpc_path):
            raise RustEngineError(
                "MusicEx 文件未内嵌 ekey，且 qmpc-mmkv-cli 不可用"
            )
        media_name = str(
            info.get("musicexMediaFilename") or Path(path).name
        )
        return _fetch_musicex_ekey(qmpc_path, media_name, retries=5)
    if not ekey:
        raise RustEngineError(
            f"QMC2 探测结果中没有 ekey（metadataType={metadata_type or '未知'}）"
        )
    return ekey


def _fetch_musicex_ekey(qmpc_path: str, media_filename: str, retries: int = 5) -> str:
    """调用 qmpc 取 MusicEx ekey；stdout 为 key/value 交替行，exit=5 重试。"""
    for attempt in range(retries + 1):
        try:
            result = subprocess.run(
                [qmpc_path, "-o", "-", "-f", "plaintext", "-F", media_filename],
                capture_output=True, creationflags=_NO_WINDOW, timeout=_TIMEOUT_S,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise RustEngineError(f"调用 qmpc-mmkv-cli 失败：{exc}") from exc
        lines = [
            line.strip()
            for line in decode_process_output(result.stdout).splitlines()
            if line.strip()
        ]
        pairs = dict(zip(lines[0::2], lines[1::2]))
        value = pairs.get(media_filename, "")
        if result.returncode == 0 and value:
            return value
        if result.returncode == 5 and attempt < retries:
            continue  # CRC read error / read-on-write，官方同样重试
        detail = decode_process_output(result.stderr).strip()
        raise RustEngineError(
            f"qmpc 未能提取 {media_filename} 的 ekey（exit={result.returncode}）"
            + (f"：{detail}" if detail else "")
        )
    raise RustEngineError("qmpc 重试后仍未取得 ekey")


def _kgm_v5_key(audio_hash: str, rust_path: str) -> str:
    """从酷狗本地 KGMusicV3.db 读取 audioHash → EncryptionKey。"""
    appdata = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    db_path = Path(appdata) / "Kugou8" / "KGMusicV3.db"
    if not db_path.is_file():
        raise RustEngineError(f"未找到酷狗本地密钥库：{db_path}")

    read_path = db_path
    temp_db: Path | None = None
    try:
        probe = subprocess.run(
            [rust_path, "kgm", "-I", "--file-mode", "db", "--", str(db_path)],
            capture_output=True, creationflags=_NO_WINDOW, timeout=_TIMEOUT_S,
        )
        if probe.returncode == 0:
            try:
                db_info = json.loads(decode_process_output(probe.stdout).strip())
            except ValueError:
                db_info = {}
            if db_info.get("encrypted"):
                fd, name = tempfile.mkstemp(prefix="umrs-kgm-", suffix=".db")
                os.close(fd)
                temp_db = Path(name)
                decoded = subprocess.run(
                    [rust_path, "kgm", "--file-mode", "db",
                     "--output", str(temp_db), "--", str(db_path)],
                    capture_output=True, creationflags=_NO_WINDOW, timeout=_TIMEOUT_S,
                )
                if decoded.returncode != 0:
                    raise RustEngineError("um-cli-rs 无法解密酷狗密钥数据库")
                read_path = temp_db

        conn = sqlite3.connect(f"file:{read_path.as_posix()}?mode=ro", uri=True)
        try:
            rows = conn.execute(
                "SELECT EncryptionKeyId, EncryptionKey FROM ShareFileItems "
                "WHERE EncryptionKey IS NOT NULL AND EncryptionKey != ''"
            ).fetchall()
        finally:
            conn.close()
    except RustEngineError:
        raise
    except (OSError, sqlite3.Error, subprocess.SubprocessError, ValueError) as exc:
        raise RustEngineError(f"读取酷狗密钥库失败：{exc}") from exc
    finally:
        if temp_db is not None:
            temp_db.unlink(missing_ok=True)

    for key_id, value in rows:
        if str(key_id) == audio_hash and value:
            return str(value)
    raise RustEngineError(f"酷狗密钥库中找不到 audioHash={audio_hash} 对应的密钥")


def detect_output_extension(ffmpeg_path: str, decrypted: str, path: str) -> str:
    """用 ffmpeg 探测解密产物的真实 demuxer；失败时按源后缀兜底。"""
    if ffmpeg_path and os.path.isfile(ffmpeg_path):
        try:
            result = subprocess.run(
                [ffmpeg_path, "-hide_banner", "-nostdin", "-i", "file:" + decrypted],
                capture_output=True, creationflags=_NO_WINDOW, timeout=_TIMEOUT_S,
            )
        except (OSError, subprocess.SubprocessError):
            result = None
        if result is not None:
            text = "\n".join(filter(None, (
                decode_process_output(result.stderr),
                decode_process_output(result.stdout),
            )))
            match = _RE_INPUT.search(text)
            if match:
                demuxers = match.group(1)
                is_webm = "webm" in demuxers.lower() and str(path).lower().endswith(".webm")
                for demuxer in demuxers.split(","):
                    key = demuxer.strip().lower()
                    if is_webm and key == "matroska":
                        continue
                    if key in _DEMUXER_EXT:
                        return _DEMUXER_EXT[key]
    lower = str(path).lower()
    if lower.endswith(".ogg") or lower.endswith(".qmcogg"):
        return ".ogg"
    if lower.endswith(".m4a") or lower.endswith(".mgg"):
        return ".m4a"
    if any(lower.endswith(s) for s in (
        ".qmc0", ".qmc3", ".tkm", ".tm0", ".tm2", ".tm3", ".tm6"
    )):
        return ".mp3"
    return ".flac"


def finalize_output(
    decrypted: str,
    basename: str,
    output_dir: str,
    fallback_dir: str,
    ffmpeg_path: str,
    reconvert: bool,
    source_path: str,
) -> tuple[str | None, bool]:
    """把临时产物落到目标目录，返回 ``(最终路径, 是否跳过)``。"""
    src = Path(decrypted)
    if not src.is_file() or src.stat().st_size == 0:
        return None, False
    ext = detect_output_extension(ffmpeg_path, decrypted, source_path)
    target_dir = Path(output_dir or fallback_dir)
    target = target_dir / f"{basename}{ext}"
    if target.exists() and not reconvert:
        src.unlink(missing_ok=True)
        return None, True
    target_dir.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(target))
    return str(target), False


def cleanup_temp(tmp_dir: str) -> None:
    """清理临时目录（含旁路封面 / 元信息），支持重复调用。"""
    if not tmp_dir:
        return
    shutil.rmtree(tmp_dir, ignore_errors=True)
