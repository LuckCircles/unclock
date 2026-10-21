# coding: utf-8
"""全局配置 — 基于 qfluentwidgets QConfig。"""

import sys
from pathlib import Path

from qfluentwidgets import (
    ConfigItem,
    OptionsConfigItem,
    OptionsValidator,
    QConfig,
    qconfig,
)


def _detect_project_root() -> Path:
    """运行时项目根目录：Nuitka standalone 用 exe 所在目录，开发模式用源码路径。"""
    main = sys.modules.get("__main__")
    if main is not None and getattr(main, "__compiled__", False):
        # 打包后 sys.executable = .dist/音乐解锁工具.exe，parent = .dist/
        return Path(sys.executable).resolve().parent
    # 开发模式: app/common/config.py → parents[2] = 项目根
    return Path(__file__).resolve().parents[2]


PROJECT_ROOT = _detect_project_root()

# 运行时配置文件（已 gitignore，不纳入版本管理）
CONFIG_PATH = str(PROJECT_ROOT / "config.json")


class Config(QConfig):
    """应用配置项集合。"""

    # ===== 基础路径 =====
    input_dir = ConfigItem("Basic", "input_dir", "")
    output_dir = ConfigItem("Basic", "output_dir", "")
    um_path = ConfigItem("Basic", "um_path", "")
    ffmpeg_path = ConfigItem("Basic", "ffmpeg_path", "")
    qmpc_path = ConfigItem("Basic", "qmpc_path", "")

    # ===== 转换选项（三态：否 / 是 / 默认） =====
    remove_source = OptionsConfigItem(
        "Conversion", "remove_source", "默认", OptionsValidator(["否", "是", "默认"])
    )
    verbose = OptionsConfigItem(
        "Conversion", "verbose", "默认", OptionsValidator(["否", "是", "默认"])
    )
    overwrite = OptionsConfigItem(
        "Conversion", "overwrite", "默认", OptionsValidator(["否", "是", "默认"])
    )
    watch = OptionsConfigItem(
        "Conversion", "watch", "默认", OptionsValidator(["否", "是", "默认"])
    )
    update_metadata = OptionsConfigItem(
        "Conversion", "update_metadata", "默认", OptionsValidator(["否", "是", "默认"])
    )
    skip_noop = OptionsConfigItem(
        "Conversion", "skip_noop", "默认", OptionsValidator(["否", "是", "默认"])
    )

    # ===== 任务行为 =====
    reconvert_done = ConfigItem(
        "Conversion", "reconvert_done", False
    )  # 覆盖已转换：重新处理已完成（成功）的文件，关闭则自动跳过已完成文件


cfg = Config()

# 默认可执行文件位于项目 app/resources/ 目录
_DEFAULT_UM = str(PROJECT_ROOT / "app" / "resources" / "um.exe")
_DEFAULT_FFMPEG = str(PROJECT_ROOT / "app" / "resources" / "ffmpeg.exe")
_DEFAULT_QMPC = str(PROJECT_ROOT / "app" / "resources" / "qmpc-mmkv-cli.exe")

qconfig.load(CONFIG_PATH, cfg)

# 记录加载前是否已存在配置文件，供下方「首次运行生成」判断
_config_existed = Path(CONFIG_PATH).exists()

# 自动检测：优先使用 app/resources 内置工具——内置 exe 存在则覆盖持久化路径，
# 这样打包后/开发模式下都能自动用内置工具；用户想改用外部路径需先移除内置 exe。
# 仅在内存中覆盖（save=False），是否落盘由下方「首次运行生成」统一决定，
# 避免启动时重复写盘、也避免覆盖用户已保存的目录等配置。
for item, default_path in (
    (cfg.um_path, _DEFAULT_UM),
    (cfg.ffmpeg_path, _DEFAULT_FFMPEG),
    (cfg.qmpc_path, _DEFAULT_QMPC),
):
    if Path(default_path).exists():
        qconfig.set(item, default_path, save=False)
    elif not item.value or not Path(item.value).exists():
        # 内置缺失时回退到默认占位路径（converter 启动时会报"未找到"）
        qconfig.set(item, default_path, save=False)

# 首次运行（无配置文件）：按当前值生成默认配置并落盘——
# 输入/输出目录为空；三个 exe 指向 app/resources（上方已探测）；其余取默认值。
if not _config_existed:
    try:
        qconfig.save()
    except OSError as exc:
        # 生成失败不致命：程序仍可以默认值运行
        print(f"[config] 生成默认配置文件失败: {exc}")
