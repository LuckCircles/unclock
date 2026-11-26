# coding: utf-8
"""从界面文案字典生成 Qt Linguist .ts 并编译 .qm。

用法：``.venv/Scripts/python.exe app/resource/i18n/build_i18n.py``

设计：所有界面文案统一挂在 ``UI`` 上下文下。运行时按配置只安装一个
翻译器：英文模式装 ``en_US.qm``（中文→英文），中文模式装 ``zh_CN.qm``
（英文→中文），因此两个 ts 互为反向映射。
"""

from __future__ import annotations

import itertools
import subprocess
from pathlib import Path
from xml.sax.saxutils import escape

HERE = Path(__file__).resolve().parent
# 从当前目录逐级向上找项目根（含 .venv），目录层级变化时依然可用
_VENV_LRELEASE = None
for _parent in HERE.parents:
    _candidate = _parent / ".venv" / "Scripts" / "pyside6-lrelease.exe"
    if _candidate.exists():
        _VENV_LRELEASE = _candidate
        break
VENV_LRELEASE = _VENV_LRELEASE if _VENV_LRELEASE else HERE.parents[2] / ".venv" / "Scripts" / "pyside6-lrelease.exe"

# 中文原文 → 英文译文。动态数字用 %1 占位，运行时按数字归一化后匹配。
TRANSLATIONS: dict[str, str] = {
    # ===== 通用 =====
    "开": "On",
    "关": "Off",
    "删除": "Delete",
    "取消": "Cancel",
    "关闭": "Close",
    "全部": "All",
    "添加文件": "Add files",
    "刷新列表": "Refresh list",
    "开始解密": "Start decryption",
    "停止解密": "Stop decryption",
    "删除文件": "Delete file",
    "查看信息": "View info",
    "播放音乐": "Play music",
    "打开路径": "Open location",
    "打开目录": "Open folder",
    "<b>输入目录</b><br/>点击在文件管理器中打开": (
        "<b>Input folder</b><br/>Click to open in File Explorer"
    ),
    "<b>输出目录</b><br/>点击在文件管理器中打开": (
        "<b>Output folder</b><br/>Click to open in File Explorer"
    ),
    "选择目录": "Choose folder",
    "选择文件": "Choose file",
    "输入目录": "Input folder",
    "输出目录": "Output folder",
    "已解密": "Decrypted",
    "已添加": "Added",
    "待解密": "Pending",
    "解密中": "Decrypting",
    "失败": "Failed",
    "已跳过": "Skipped",
    "歌手名": "Artist name",
    "专辑名": "Album name",
    "提示": "Notice",
    "目录": "Folders",
    "就绪": "Ready",
    "未配置": "not configured",
    "未设置": "Not set",
    "主界面": "Home",
    "任务管理": "Tasks",
    "运行日志": "Run log",
    "配置界面": "Settings",
    "音乐解锁工具": "Music Unlock Tool",
    "音乐解锁工具 启动": "Music Unlock Tool started",
    "程序已经在运行中。": "The program is already running.",
    "检测到已有实例在运行，退出本次启动": "Another instance is already running; exiting",
    "确定": "OK",
    "否": "No",
    "是": "Yes",
    "默认": "Default",
    "自动": "Auto",
    "自动选择": "Auto select",
    "中文": "Chinese",
    "英文": "English",
    "开启": "on",

    # ===== 首页 =====
    "工具检测": "Tool detection",
    "音乐解锁核心引擎": "Core music decryption engine",
    "音频转码 / 元数据写入": "Audio transcoding / metadata writing",
    "QQ 音乐密钥自动提取": "Automatic QQ Music key extraction",
    "Rust 离线解密引擎": "Rust offline decryption engine",
    "<b>开始解密</b><br/>扫描输入目录并批量转换加密音乐": (
        "<b>Start decryption</b><br/>Scan the input folder and batch-decrypt encrypted music"
    ),
    "未设置输入目录": "Input folder not set",
    "未设置输出目录": "Output folder not set",
    "未设置或路径不存在": "is not set or does not exist",
    "无法打开官方网站：": "Cannot open the official website: ",
    "<b>停止解密</b><br/>结束当前任务，已解密的文件会保留": (
        "<b>Stop decryption</b><br/>End the current task; decrypted files are kept"
    ),
    "正在收尾...": "Finishing...",
    "正在收尾，请稍候": "Finishing, please wait",

    # ===== 已解密页 =====
    "0 个音乐文件": "0 music files",
    "搜索音乐文件": "Search music files",
    "<b>刷新列表</b><br/>重新扫描输出目录并更新文件列表": (
        "<b>Refresh list</b><br/>Rescan the output folder and update the file list"
    ),
    "<b>打开目录</b><br/>在文件管理器中打开输出目录": (
        "<b>Open folder</b><br/>Open the output folder in File Explorer"
    ),
    "尚未设置输出目录，请到配置界面设置": "Output folder is not set. Please set it in Settings.",
    "输出目录不存在": "Output folder does not exist",
    "无法读取输出目录，请检查路径或权限（列表保持上次结果）": (
        "Cannot read the output folder. Check the path or permissions (previous list kept)."
    ),
    "输出目录暂无音乐文件": "No music files in the output folder",
    "输出目录暂无已解密文件": "No decrypted files in the output folder",
    "输出目录扫描失败：保留上次列表": "Output folder scan failed; previous list kept",
    "刷新失败：无法读取输出目录，列表保持上次结果。": (
        "Refresh failed: cannot read the output folder; previous list kept."
    ),
    "输出目录未设置或路径不存在。": "Output folder is not set or does not exist.",
    "扫描输出目录时出错": "Error scanning the output folder",
    "输出目录扫描失败: %1": "Output folder scan failed: %1",
    "已解密 %1": "Decrypted %1",
    "已添加 %1": "Added %1",
    "未找到与“%1”匹配的文件": "No files matching \"%1\" were found",
    "封面图片无法转换为 PNG，保存已取消": (
        "The cover image could not be converted to PNG; saving cancelled"
    ),
    "未能提取「%1」的内嵌封面（文件可能没有封面）": (
        "Could not extract the embedded cover from \"%1\" (the file may have none)"
    ),
    "保存封面失败: %1": "Failed to save cover: %1",
    "保存封面失败，请检查路径权限或文件是否被占用。": (
        "Failed to save the cover. Check permissions or whether the file is in use."
    ),
    "已保存封面: %1": "Cover saved: %1",
    "已保存到音乐文件同目录: %1": "Saved next to the music file: %1",
    "确定要删除「%1」吗？此操作不可恢复。": "Delete \"%1\"? This cannot be undone.",
    "已删除文件: %1": "File deleted: %1",
    "已删除 %1": "Deleted %1",
    "删除失败: %1": "Failed to delete: %1",

    # ===== 任务页 =====
    "共 0 个文件": "0 files",
    "暂无文件，点击“添加文件”、刷新列表，或直接拖入文件": (
        "No files yet. Click Add files, refresh the list, or drag files here"
    ),
    "松开鼠标，添加至任务列表": "Release to add to the task list",
    "共 %1 个文件": "%1 files",
    "待解密 %1": "Pending %1",
    "解密中 %1": "Decrypting %1",
    "失败 %1": "Failed %1",
    "未识别到本地文件或目录。": "No local file or folder recognized.",
    "已拖入添加 %1 个文件": "Added %1 dropped files",
    "重复 %1 个": "%1 duplicate(s)",
    "非加密 %1 个": "%1 non-encrypted",
    "拖入的文件已在列表中。": "The dropped file is already in the list.",
    "拖入的文件均不可解密或已在列表中。": "Dropped files cannot be decrypted or are already in the list.",
    "未选择可解密的加密音乐文件。": "No decryptable encrypted music file selected.",
    "未找到可解密的加密音乐文件。": "No decryptable encrypted music file found.",
    "选择待解密文件": "Select files to decrypt",
    "移出列表": "Remove from list",
    "已移出列表: %1（文件保留，刷新后不再出现在列表）": (
        "Removed from list: %1 (the file is kept and will not appear after refresh)"
    ),
    "<b>添加文件</b><br/>选择一个或多个加密音乐文件加入列表": (
        "<b>Add files</b><br/>Choose one or more encrypted music files to add to the list"
    ),
    "<b>刷新列表</b><br/>重新扫描输入目录并同步已解密状态": (
        "<b>Refresh list</b><br/>Rescan the input folder and sync decrypted status"
    ),
    "<b>删除完成</b><br/>从列表移除已解密卡片，文件仍在磁盘，刷新可恢复": (
        "<b>Remove completed</b><br/>Remove decrypted cards; files stay on disk and can be restored by refreshing"
    ),

    # ===== 设置页 =====
    "外观设置": "Appearance",
    "主题": "Theme",
    "跟随系统：自动采用系统浅色/深色偏好；也可手动指定。": (
        "Follow system: use the system light/dark preference automatically; you can also choose manually."
    ),
    "跟随系统": "Follow system",
    "浅色模式": "Light",
    "深色模式": "Dark",
    "语言": "Language",
    "中文：始终使用简体中文；英文：始终使用英文；自动：跟随系统语言。": (
        "Chinese: always use Simplified Chinese; English: always use English; Auto: follow the system language."
    ),
    "基础设置": "Basic",
    "解密工具": "Decryption tool",
    "默认使用 um 链路，可切换为官方 Rust 工具 um-cli-rs。": (
        "Uses the um pipeline by default; switch to the official Rust tool um-cli-rs if needed."
    ),
    "um 路径": "um path",
    "ffmpeg 路径": "ffmpeg path",
    "qmpc-mmkv-cli 路径": "qmpc-mmkv-cli path",
    "um-cli-rs 路径": "um-cli-rs path",
    "临时目录": "Temporary folder",
    "系统临时目录（未指定）": "System temporary folder (not specified)",
    "<b>选择目录</b><br/>设置加密音乐所在的输入目录": (
        "<b>Choose folder</b><br/>Set the folder containing encrypted music"
    ),
    "<b>选择目录</b><br/>设置解密结果的输出目录": (
        "<b>Choose folder</b><br/>Set the folder for decryption results"
    ),
    "<b>选择文件</b><br/>指定 um.exe 的路径": "<b>Choose file</b><br/>Specify the path to um.exe",
    "<b>选择文件</b><br/>指定 ffmpeg.exe 的路径": "<b>Choose file</b><br/>Specify the path to ffmpeg.exe",
    "<b>选择文件</b><br/>指定 qmpc-mmkv-cli.exe 的路径": (
        "<b>Choose file</b><br/>Specify the path to qmpc-mmkv-cli.exe"
    ),
    "<b>选择文件</b><br/>指定 um_cli_rs.exe 的路径（选择 Rust 引擎时使用）": (
        "<b>Choose file</b><br/>Specify the path to um_cli_rs.exe (used when the Rust engine is selected)"
    ),
    "<b>选择目录</b><br/>转换产生的中间文件会保存在这里；不选则使用系统临时目录": (
        "<b>Choose folder</b><br/>Intermediate files are saved here; if unset, the system temporary folder is used"
    ),
    "转换设置": "Conversion",
    "对应参数: ": "Argument: ",
    " · um 默认: ": " · um default: ",
    "（无关闭参数，选“否”仍按默认执行）": "(No disable argument; choosing \"No\" still follows the default.)",
    "任务行为": "Task behavior",
    "并行转换": "Parallel conversion",
    "开启后多个文件可同时解密；关闭则按顺序串行处理。": (
        "When enabled, multiple files are decrypted at once; when disabled, they are processed sequentially."
    ),
    "并行数量": "Parallel count",
    "0 或负数表示使用 CPU 核心数；实际执行时大于 256 按 256 计。": (
        "0 or a negative value uses the CPU core count; values above 256 are capped at 256."
    ),
    "覆盖已转换": "Overwrite converted files",
    "开启后重新解密已成功解密的文件；关闭则自动跳过已解密文件，仅处理待解密/失败项。": (
        "When enabled, successfully decrypted files are decrypted again; otherwise they are skipped "
        "and only pending/failed items are processed."
    ),
    "编码设置": "Encoding",
    "正在探测可用编码器...": "Detecting available encoders...",
    "AAC 编码器": "AAC encoder",
    "自动选择按 libfdk_aac → aac 降级；显式选择要求 ffmpeg 支持。": (
        "Auto falls back from libfdk_aac to aac; an explicit choice must be supported by ffmpeg."
    ),
    "FDK 编码器：使用动态码率 (VBR)": "FDK encoder: use variable bitrate (VBR)",
    "开启用 VBR 5，关闭用固定 192k；仅 libfdk_aac 生效。": (
        "Enabled uses VBR 5, disabled uses a fixed 192k. Only applies to libfdk_aac."
    ),
    "OGG 编码器": "OGG encoder",
    "自动选择按 libopus → libvorbis 降级；苹果设备原生不支持 ogg。": (
        "Auto falls back from libopus to libvorbis; Apple devices do not support ogg natively."
    ),
    "支持编码器：": "Available encoders: ",
    "选择输入目录": "Choose the input folder",
    "选择输出目录": "Choose the output folder",
    "选择 um.exe": "Select um.exe",
    "选择 ffmpeg.exe": "Select ffmpeg.exe",
    "选择 qmpc-mmkv-cli.exe": "Select qmpc-mmkv-cli.exe",
    "选择 um_cli_rs.exe": "Select um_cli_rs.exe",
    "选择临时目录": "Choose the temporary folder",
    "临时目录已设为: %1": "Temporary folder set to: %1",

    # ===== 组件 =====
    "清空日志": "Clear log",
    "<b>清空日志</b><br/>只清空本页显示，不影响日志文件": (
        "<b>Clear log</b><br/>Only clears this page; the log file is not affected"
    ),
    "封面预览": "Cover preview",
    "封面图片无法读取或已被移动": "The cover image cannot be read or has been moved",
    "暂无文件": "No files",
    "暂无内容": "Nothing here",
    "文件信息": "File info",
    "文件名：": "File name: ",
    "文件名": "File name",
    "完整路径": "Full path",
    "文件大小": "File size",
    "修改时间": "Modified",
    "来源": "Source",
    "文件格式": "Format",
    "时长": "Duration",
    "编码": "Codec",
    "采样率": "Sample rate",
    "声道": "Channels",
    "码率": "Bitrate",
    "标题": "Title",
    "艺术家": "Artist",
    "专辑": "Album",
    "保存封面": "Save cover",
    "关闭窗口": "Close window",
    "该文件没有内嵌封面，无法保存": "This file has no embedded cover to save",
    "当前页面不支持保存封面": "Saving covers is not supported on this page",
    "无法打开：文件已不存在或路径无效。": "Cannot open: the file no longer exists or the path is invalid.",
    "<b>完整路径</b><br/>自动滚动展示 · 点击打开文件所在位置": (
        "<b>Full path</b><br/>Auto-scrolling · Click to open the file location"
    ),
    "检测通过，可正常参与解密": "Detected successfully and ready for decryption",
    "请检查工具文件，或在设置界面重新指定路径": "Check the tool file or set a new path in Settings",
    "点击在默认浏览器中打开": "Click to open in the default browser",
    " 检测中...": " Checking...",

    # ===== 补全：任务页 / 已解密页 =====
    "删除完成": "Clear completed",

    # ===== 补全：转换设置（标签 + 参数提示词） =====
    "删除源文件": "Delete source file",
    "详细输出": "Verbose output",
    "覆盖输出": "Overwrite output",
    "监听输入目录": "Watch input folder",
    "更新封面": "Update cover art",
    "跳过无动作解码器": "Skip no-op decoders",
    "对应参数:": "Argument:",
    "默认开启": "on by default",
    "默认关闭": "off by default",

    # ===== 补全：首页工具卡提示 =====
    "已就绪": "Ready",
    "缺失": "Missing",
    "官方网站": "Official website",
    "版本未知": "unknown version",

    # ===== 补全：工具检测日志 =====
    "开始工具链自动检测": "Starting toolchain auto-check",
    "工具链检测完成:": "Toolchain check finished:",
    "工具监测": "Tool check",
    "文件属性": "file properties",
    "命令行": "CLI",

    # ===== 补全：解密流程日志与提示（数字归一模板） =====
    "已跳过 %1 个非加密文件。": "Skipped %1 non-encrypted file(s).",
    "检测到加密文件 %1 个：已解密 %1，待解密 %1。": (
        "Found %1 encrypted file(s): %1 decrypted, %1 pending."
    ),
    "已跳过 %1 个已解密文件（开启“覆盖已转换”可重新解密）。": (
        "Skipped %1 decrypted file(s) (turn on \"Overwrite output\" to decrypt them again)."
    ),
    "没有待解密的文件。": "No files to decrypt.",
    "全部解密完成：成功 %1 个文件。": "Decryption finished: %1 file(s) succeeded.",
    "已处理 %1/%1 个文件，成功 %1，跳过 %1，错误 %1，取消 %1。": (
        "Processed %1/%1 files: %1 succeeded, %1 skipped, %1 failed, %1 cancelled."
    ),
    "开始解密任务: %1 个文件": "Starting decryption of %1 file(s)",
    "解密失败，已跳过并继续。": "failed to decrypt; skipped and continuing.",
    "关闭": "Close",
}

# 计数组合模板：两页计数标签按状态词组合拼接（如「已解密 3 · 已添加 1 · 共 4」），
# 逐一手写会随状态数组合爆炸，这里按代码中的固定顺序程序化生成全部组合。
_WORD_EN = {
    "已解密": "Decrypted",
    "已添加": "Added",
    "待解密": "Pending",
    "解密中": "Decrypting",
    "失败": "Failed",
}
_COUNT_SUFFIXES = (
    (" · 共 %1", " · Total %1"),
    (" · 匹配 %1/%1", " · Matching %1/%1"),
)
for _seq in (("已解密", "已添加"), ("待解密", "解密中", "已解密", "失败")):
    for _r in range(1, len(_seq) + 1):
        for _combo in itertools.combinations(_seq, _r):
            _zh = " · ".join(f"{_w} %1" for _w in _combo)
            _en = " · ".join(f"{_WORD_EN[_w]} %1" for _w in _combo)
            TRANSLATIONS[_zh] = _en
            for _szh, _sen in _COUNT_SUFFIXES:
                TRANSLATIONS[_zh + _szh] = _en + _sen
# 空摘要（无任何状态时显示 0）的组合
TRANSLATIONS["%1 · 共 %1"] = "%1 · Total %1"
TRANSLATIONS["%1 · 匹配 %1/%1"] = "%1 · Matching %1/%1"


def _ts_bytes(entries: dict[str, str], language: str, source_language: str) -> bytes:
    lines = [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<!DOCTYPE TS>',
        f'<TS version="2.1" language="{language}" sourcelanguage="{source_language}">',
        '    <context>',
        '        <name>UI</name>',
    ]
    for source, target in entries.items():
        lines.extend((
            '        <message>',
            f'            <source>{escape(source)}</source>',
            f'            <translation>{escape(target)}</translation>',
            '        </message>',
        ))
    lines.extend(('    </context>', '</TS>', ''))
    return "\n".join(lines).encode("utf-8")


def main() -> None:
    zh_to_en = dict(TRANSLATIONS)
    en_to_zh = {v: k for k, v in zh_to_en.items()}

    (HERE / "en_US.ts").write_bytes(_ts_bytes(zh_to_en, "en_US", "zh_CN"))
    (HERE / "zh_CN.ts").write_bytes(_ts_bytes(en_to_zh, "zh_CN", "en_US"))

    lrelease = VENV_LRELEASE if VENV_LRELEASE.exists() else "pyside6-lrelease"
    for name in ("en_US", "zh_CN"):
        subprocess.run(
            [str(lrelease), str(HERE / f"{name}.ts"), "-qm", str(HERE / f"{name}.qm")],
            check=True,
        )
    print(f"generated {len(zh_to_en)} entries -> en_US.qm / zh_CN.qm")


if __name__ == "__main__":
    main()
