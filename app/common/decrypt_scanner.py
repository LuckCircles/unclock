# coding: utf-8
"""已解密文件判定 —— 基于输入/输出目录按「去后缀」规则比对。

思路：扫描输出目录，建立「已解密目标基名集合」；遍历输入文件，非加密文件跳过，
加密文件按去后缀规则算出目标基名并查集合——命中即已解密，未命中即待解密。
因 um 输出文件名与输入不一定一致，此处以「去后缀基名」在输出目录中匹配。
"""

import os
from pathlib import Path

from .utils import is_encrypted_file, is_music_file, target_basename


def list_encrypted_files(input_dir) -> list:
    """扫描输入目录顶层，返回加密文件路径列表（不递归、不含任何 UI 依赖）。

    common 层单点提供目录扫描，供 view（任务页刷新 / 启动兜底）复用，
    避免各层各自 os.listdir 产生规则漂移。
    """
    paths = []
    if not input_dir or not os.path.isdir(input_dir):
        return paths
    try:
        with os.scandir(input_dir) as it:
            for entry in it:
                try:
                    if entry.is_file() and is_encrypted_file(entry.path):
                        paths.append(entry.path)
                except OSError:
                    continue
    except OSError:
        return []
    return paths


def build_decrypted_basenames(output_dir) -> set:
    """扫描输出目录，返回已解密文件的目标基名集合（去后缀）。

    只纳入常见音乐文件：um 的解密结果一定是音频，输出目录里的
    ``song.txt`` / 封面图等同名基名文件不应让 ``song.kgm`` 被误判为已解密。
    """
    names: set = set()
    if not output_dir or not os.path.isdir(output_dir):
        return names
    try:
        for name in os.listdir(output_dir):
            full = os.path.join(output_dir, name)
            if os.path.isfile(full) and is_music_file(name):
                names.add(target_basename(name))
    except OSError:
        pass
    return names


def is_already_decrypted(file_path, decrypted_basenames) -> bool:
    """加密文件按去后缀规则算目标基名，查已解密集合，命中即已解密。"""
    return target_basename(Path(file_path).name) in decrypted_basenames


def build_input_basenames(input_dir) -> set:
    """扫描输入目录，返回加密文件的目标基名集合（用于判断输出文件来源）。"""
    names: set = set()
    if not input_dir or not os.path.isdir(input_dir):
        return names
    try:
        for name in os.listdir(input_dir):
            full = os.path.join(input_dir, name)
            if os.path.isfile(full) and is_encrypted_file(full):
                names.add(target_basename(name))
    except OSError:
        pass
    return names


def output_source_label(file_path, input_basenames) -> str:
    """判断输出目录音乐文件的来源标签：基名命中加密输入 → 已解密，否则 → 已添加。

    「已解密」= 由本工具从某个加密输入解密产生；「已添加」= 输出目录里原本就有、
    不对应任何加密输入的音乐文件。
    """
    return "已解密" if target_basename(Path(file_path).name) in input_basenames else "已添加"


def classify_files(paths, output_dir):
    """把输入文件分为（已解密, 待解密, 跳过的非加密）三组。

    返回 ``(decrypted, pending, skipped)``，均为路径列表并保持原顺序：
    - decrypted：加密且输出目录已有对应解密文件；
    - pending：加密但输出目录尚无对应解密文件；
    - skipped：非加密文件（明文音频或不受支持格式）。
    """
    decrypted_basenames = build_decrypted_basenames(output_dir)
    decrypted, pending, skipped = [], [], []
    for path in paths:
        if not is_encrypted_file(path):
            skipped.append(path)
        elif is_already_decrypted(path, decrypted_basenames):
            decrypted.append(path)
        else:
            pending.append(path)
    return decrypted, pending, skipped
