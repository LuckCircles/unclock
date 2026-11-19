# coding: utf-8
"""音频文件元数据探测（纯逻辑层，不依赖任何 UI）。

调用内置 ffmpeg 的 ``-i`` 探测模式解析文件元数据：时长、整体码率、编码、
采样率、声道，以及 id3/vorbis 标签中的标题/艺术家/专辑。ffmpeg 探测只读取
文件头、不解码整轨，单文件通常几十毫秒；任何失败（文件不存在、损坏、超时、
ffmpeg 缺失）都静默返回空字典，绝不抛异常打断调用方（信息查看是附加能力，
不应影响列表主流程）。

与 ``cover_loader`` 同源的注意点：Windows 下必须用 CREATE_NO_WINDOW 抑制
控制台黑框；stderr 需按多编码解码（中文标签在 GBK 系统上可能是 cp936）。
"""

import os
import re
import subprocess

from .utils import decode_process_output

# 单文件探测超时（秒）：本地进程通常几十毫秒，超时多为损坏文件或慢速设备
_PROBE_TIMEOUT = 3.0

# 缺失值占位：对话框统一用它显示「—」
UNKNOWN = "—"

# PNG 文件头签名：校验 ffmpeg stdout 确实是封面图而非报错文本
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

# ffmpeg -i 输出解析正则（基于实测输出格式，mp3/flac/m4a/wav 均验证）
#   Duration: 00:00:03.50, start: 0.025057, bitrate: 195 kb/s
_RE_DURATION = re.compile(r"Duration:\s*(\d+):(\d+):([\d.]+)")
_RE_BITRATE = re.compile(r"bitrate:\s*(\d+)\s*kb/s")
#   Stream #0:0: Audio: mp3 (mp3float), 44100 Hz, mono, fltp, 192 kb/s
#   Stream #0:0: Audio: flac, 44100 Hz, mono, s32 (24 bit)
_RE_AUDIO_STREAM = re.compile(
    r"Stream #\d+:\d+[^\n]*?Audio:\s*([^\n]+)", re.IGNORECASE
)
_RE_SAMPLE_RATE = re.compile(r"(\d+)\s*Hz")
_RE_STREAM_BITRATE = re.compile(r"(\d+)\s*kb/s")
# 元数据块中的 key : value（title/artist/album），key 前的空白 + 冒号对齐
#   title           : 测试标题
_RE_TAG = re.compile(r"^\s*(title|artist|album)\s*:\s*(.+?)\s*$",
                     re.IGNORECASE | re.MULTILINE)

# 声道英文 → 中文友好名（ffmpeg 输出 mono / stereo / 5.1 等）
_CHANNELS = {"mono": "单声道", "stereo": "立体声", "5.1": "5.1 声道",
             "7.1": "7.1 声道"}


def _parse_media_text(text: str) -> dict:
    """从 ffmpeg 探测输出文本解析元数据字典（不含封面）。

    ffmpeg 探测信息写在 stderr；无封面时可能以非 0 退出但文本仍完整，
    故调用方只凭文本是否有效判断，不看 returncode。
    """
    info = {}
    if "Input #" not in text and "Duration:" not in text:
        return info

    # 时长：转为 mm:ss / h:mm:ss（去掉百分秒，展示层更清爽）
    m = _RE_DURATION.search(text)
    if m:
        h, minute, sec = int(m.group(1)), int(m.group(2)), float(m.group(3))
        sec_i = int(sec)
        info["duration"] = (
            f"{h}:{minute:02d}:{sec_i:02d}" if h else f"{minute}:{sec_i:02d}"
        )
    # 整体码率
    m = _RE_BITRATE.search(text)
    if m:
        info["bitrate"] = f"{m.group(1)} kb/s"
    # 音频流：编码 / 采样率 / 声道 / 流码率（取第一个 Audio 流）
    m = _RE_AUDIO_STREAM.search(text)
    if m:
        stream = m.group(1)
        codec = stream.split(",", 1)[0].strip()
        # 去掉括号内的实现别名，如 "mp3 (mp3float)" → "mp3"
        codec = re.sub(r"\s*\([^)]*\)", "", codec).strip()
        if codec:
            info["codec"] = codec.upper()
        mh = _RE_SAMPLE_RATE.search(stream)
        if mh:
            info["sample_rate"] = f"{mh.group(1)} Hz"
        # 声道可能是 "mono" / "stereo" / "5.1"，出现在采样率之后的逗号段
        for seg in stream.split(",")[1:]:
            key = seg.strip().lower()
            if key in _CHANNELS:
                info["channels"] = _CHANNELS[key]
                break
        mb = _RE_STREAM_BITRATE.search(stream)
        if mb:
            info["codec_bitrate"] = f"{mb.group(1)} kb/s"
    # id3/vorbis 标签
    for key, value in _RE_TAG.findall(text):
        field = key.lower()
        if value.strip() and field not in info:
            info[field] = value.strip()
    return info


def _run_ffmpeg(ffmpeg_path: str, cmd_suffix: list) -> "subprocess.CompletedProcess | None":
    """执行 ffmpeg 探测并返回结果；路径无效 / 超时 / 系统错误返回 None。"""
    if not ffmpeg_path or not os.path.isfile(ffmpeg_path):
        return None
    cmd = [ffmpeg_path, "-hide_banner", "-i", cmd_suffix[0]] + cmd_suffix[1:]
    kwargs = {
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "timeout": _PROBE_TIMEOUT,
    }
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        return subprocess.run(cmd, **kwargs)
    except (OSError, subprocess.SubprocessError):
        return None


def probe_audio_info(ffmpeg_path: str, audio_path: str) -> dict:
    """探测单个音频文件的元数据（不含封面），失败返回空 dict。

    供「查看信息」对话框同步调用。返回字段见 ``_parse_media_text``。
    """
    if not audio_path or not os.path.isfile(audio_path):
        return {}
    result = _run_ffmpeg(ffmpeg_path, [audio_path])
    if result is None:
        return {}
    return _parse_media_text(decode_process_output(result.stderr or b""))


def probe_media(ffmpeg_path: str, audio_path: str) -> tuple:
    """一次 ffmpeg 调用同时返回 ``(cover_bytes | None, info_dict)``。

    相比「先 extract_cover_bytes 再 probe_audio_info」的两次进程，本函数只起
    一个 ffmpeg：stdout 输出首张内嵌封面 PNG，stderr 仍含完整探测元数据。
    实测两种场景（有/无封面）均可同时拿到标签，耗时约为两次调用的 1/2。

    封面以 PNG 签名校验（无封面时 stdout 为空、returncode 非 0，均属正常）；
    元数据解析不依赖 returncode——与 ``probe_audio_info`` 同理。任何失败
    返回 ``(None, {})``，绝不抛异常。
    """
    if not audio_path or not os.path.isfile(audio_path):
        return None, {}
    result = _run_ffmpeg(ffmpeg_path, [
        audio_path,
        "-map", "0:v:0?", "-frames:v", "1",
        "-f", "image2pipe", "-vcodec", "png", "pipe:1",
    ])
    if result is None:
        return None, {}
    stdout = result.stdout or b""
    cover = stdout if stdout.startswith(_PNG_SIGNATURE) else None
    # 标签信息全部在 stderr（stdout 是二进制 PNG，不参与文本解析）
    info = _parse_media_text(decode_process_output(result.stderr or b""))
    return cover, info


# 文件名回退解析歌手：网络下载常见「歌名 - 歌手.ext」格式，无内嵌标签时
# 用它兜底，让「按歌手归类」也能覆盖这类文件。专辑名无法从文件名可靠推断，
# 只依赖内嵌标签。
_RE_FILENAME_ARTIST = re.compile(r"\s*[-–—]\s*([^-–—\[\](),，]+?)\s*$")


def guess_artist_from_name(file_name: str) -> str:
    """从文件名推断歌手名（「歌名 - 歌手」取最后一段），无法判断返回空串。"""
    stem = os.path.splitext(os.path.basename(file_name))[0]
    m = _RE_FILENAME_ARTIST.search(stem)
    return m.group(1).strip() if m else ""
