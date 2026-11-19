# coding: utf-8
"""全局配置 — 基于 qfluentwidgets QConfig。"""

import sys
from pathlib import Path

from qfluentwidgets import (
    ConfigItem,
    OptionsConfigItem,
    OptionsValidator,
    QConfig,
    Theme,
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

# 转换选项元数据：service 据此构建 um 参数、view 据此生成设置卡片，
# 避免两层各自硬编码。`um_default_on` 为该参数在 um v0.2.20 中的默认值
# （见 `um.exe --help`）；um 未提供这些参数的关闭形式，故「否」只能不传参。
CONVERSION_OPTIONS = (
    (cfg.remove_source, "删除源文件", "--rs", False),
    (cfg.verbose, "详细输出", "-V", False),
    (cfg.overwrite, "覆盖输出", "--overwrite", False),
    (cfg.watch, "监听输入目录", "--watch", False),
    (cfg.update_metadata, "更新封面", "--update-metadata", False),
    (cfg.skip_noop, "跳过无动作解码器", "-n", True),
)

# 默认可执行文件位于项目根目录 tools/ 目录（与 app/ 同级）
_DEFAULT_UM = str(PROJECT_ROOT / "tools" / "um.exe")
_DEFAULT_FFMPEG = str(PROJECT_ROOT / "tools" / "ffmpeg.exe")
_DEFAULT_QMPC = str(PROJECT_ROOT / "tools" / "qmpc-mmkv-cli.exe")

# 加载前先记录配置文件是否存在（不依赖 qconfig.load 是否创建文件的实现细节），
# 供下方「首次运行生成」判断
_config_existed = Path(CONFIG_PATH).exists()
qconfig.load(CONFIG_PATH, cfg)

# 主题切换选项顺序：跟随系统 / 浅色 / 深色
# 库默认顺序为 LIGHT/DARK/AUTO，这里重排为 AUTO/LIGHT/DARK 以匹配界面呈现；
# OptionsSettingCard 依据 themeMode.options 顺序配对文本，值本身是 Theme 枚举不受影响。
qconfig.themeMode.validator.options = [Theme.AUTO, Theme.LIGHT, Theme.DARK]

# 自动检测：仅在「尚未配置」或「已配置路径失效」时回退到内置工具。
# 用户显式设置且当前有效的外部路径必须保留——此前无条件覆盖会让设置页
# 选的 um/ffmpeg/qmpc 路径在重启后失效（打包产物里用户也无法移除内置 exe）。
# 仅在内存中覆盖（save=False），是否落盘由下方「首次运行生成」统一决定，
# 避免启动时重复写盘、也避免覆盖用户已保存的目录等配置。
for item, default_path in (
    (cfg.um_path, _DEFAULT_UM),
    (cfg.ffmpeg_path, _DEFAULT_FFMPEG),
    (cfg.qmpc_path, _DEFAULT_QMPC),
):
    current = item.value if isinstance(item.value, str) else ""
    if current and Path(current).is_file():
        continue  # 尊重用户已配置且有效的路径
    if Path(default_path).exists():
        qconfig.set(item, default_path, save=False)
    elif not current:
        # 内置也缺失时回退到默认占位路径（converter 启动时会报"未找到"）
        qconfig.set(item, default_path, save=False)

# 首次运行（无配置文件）：按当前值生成默认配置并落盘——
# 输入/输出目录为空；三个 exe 指向项目根 tools/（上方已探测）；其余取默认值。
if not _config_existed:
    try:
        qconfig.save()
    except OSError as exc:
        # 生成失败不致命：程序仍可以默认值运行
        print(f"[config] 生成默认配置文件失败: {exc}")
