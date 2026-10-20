# coding: utf-8
"""全局配置 — 基于 qfluentwidgets QConfig。"""

from pathlib import Path

from qfluentwidgets import (
    ConfigItem,
    OptionsConfigItem,
    OptionsValidator,
    QConfig,
    qconfig,
)

# 项目根目录（app/common/config.py → parents[2] = unclock/）
PROJECT_ROOT = Path(__file__).resolve().parents[2]

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


cfg = Config()

# 默认可执行文件位于项目 app/resources/ 目录
_DEFAULT_UM = str(PROJECT_ROOT / "app" / "resources" / "um.exe")
_DEFAULT_FFMPEG = str(PROJECT_ROOT / "app" / "resources" / "ffmpeg.exe")
_DEFAULT_QMPC = str(PROJECT_ROOT / "app" / "resources" / "qmpc-mmkv-cli.exe")

qconfig.load(CONFIG_PATH, cfg)

# 迁移兼容：若持久化路径为空或已失效（如 um/ → app/resources/ 迁移后），回退默认值
if not cfg.um_path.value or not Path(cfg.um_path.value).exists():
    qconfig.set(cfg.um_path, _DEFAULT_UM)
if not cfg.ffmpeg_path.value or not Path(cfg.ffmpeg_path.value).exists():
    qconfig.set(cfg.ffmpeg_path, _DEFAULT_FFMPEG)
if not cfg.qmpc_path.value or not Path(cfg.qmpc_path.value).exists():
    qconfig.set(cfg.qmpc_path, _DEFAULT_QMPC)
