# coding: utf-8
"""音乐文件后缀 → 平台图标（纯后缀映射，不依赖 UI)。

图标以官方 ``FluentIconBase`` 枚举 ``PlatformIcon`` 表示，其 ``path()``
返回 ``:/img/<name>.png`` qrc 路径供组件使用。
平台归属依据：``um --supported-ext`` 输出 + um.exe 内置算法包
（ncm / qmc / kgm / xiami / ximalaya）与官方支持格式清单。

说明：
- ``vpr`` / ``vpr.flac`` 走 um 的 kgm 解码器（Viper 为酷狗品牌），归酷狗；
- um v0.2.20 无独立的汽水音乐解码器，QISHUI 图标暂预留、未绑定后缀；
- ``xm`` 由 xiami / ximalaya 共同支持，按用户约定（XM = 喜马拉雅）归喜马拉雅；
- 未命中任何平台（明文音频等）返回 None，由 TaskCard 画默认音乐图标。
"""

from .icon import PlatformIcon

# 平台图标（官方 FluentIconBase 枚举成员）
QQ_MUSIC = PlatformIcon.QQ_MUSIC
NETEASE_CLOUD = PlatformIcon.NETEASE_CLOUD
KUGOU = PlatformIcon.KUGOU
KUWO = PlatformIcon.KUWO
XIMALAYA = PlatformIcon.XIMALAYA
QISHUI = PlatformIcon.QISHUI  # 预留：um 当前无独立汽水格式

# 后缀（含前导点，小写）→ 图标资源名。
# 复合后缀（.kgm.flac / .vpr.flac）必须与短后缀共存，由最长匹配仲裁。
_SUFFIX_TO_ICON = {
    # ---------------- QQ 音乐（qmc 解码器） ----------------
    # QMCv1
    ".qmc0": QQ_MUSIC,
    ".qmc2": QQ_MUSIC,
    ".qmc3": QQ_MUSIC,
    ".qmc4": QQ_MUSIC,
    ".qmc6": QQ_MUSIC,
    ".qmc8": QQ_MUSIC,
    ".qmcflac": QQ_MUSIC,
    ".qmcogg": QQ_MUSIC,
    ".tkm": QQ_MUSIC,
    ".mmp4": QQ_MUSIC,
    # QMCv2 PC / Android / Mac 客户端
    ".mflac": QQ_MUSIC,
    ".mflac0": QQ_MUSIC,
    ".mflac1": QQ_MUSIC,
    ".mflac2": QQ_MUSIC,
    ".mflaca": QQ_MUSIC,
    ".mflach": QQ_MUSIC,
    ".mflacl": QQ_MUSIC,
    ".mflacm": QQ_MUSIC,
    ".mgg": QQ_MUSIC,
    ".mgg0": QQ_MUSIC,
    ".mgg1": QQ_MUSIC,
    ".mgg2": QQ_MUSIC,
    ".mgga": QQ_MUSIC,
    ".mggh": QQ_MUSIC,
    ".mggl": QQ_MUSIC,
    ".mggm": QQ_MUSIC,
    # Moo 音乐（bkc*，腾讯系，走 qmc 解码器）
    ".bkcape": QQ_MUSIC,
    ".bkcflac": QQ_MUSIC,
    ".bkcm4a": QQ_MUSIC,
    ".bkcmp3": QQ_MUSIC,
    ".bkcogg": QQ_MUSIC,
    ".bkcwav": QQ_MUSIC,
    ".bkcwma": QQ_MUSIC,
    # QQ 音乐 hex 伪装后缀（flac / m4a / mp3 / ogg / wav 的 ASCII hex）
    ".666c6163": QQ_MUSIC,
    ".6d3461": QQ_MUSIC,
    ".6d7033": QQ_MUSIC,
    ".6f6767": QQ_MUSIC,
    ".776176": QQ_MUSIC,
    # QQ 音乐 Tm 格式
    ".tm0": QQ_MUSIC,
    ".tm2": QQ_MUSIC,
    ".tm3": QQ_MUSIC,
    ".tm6": QQ_MUSIC,

    # ---------------- 网易云音乐（ncm 解码器） ----------------
    ".ncm": NETEASE_CLOUD,

    # ---------------- 酷狗音乐（kgm 解码器，含 Viper/vpr） ----------------
    ".kgm": KUGOU,
    ".kgma": KUGOU,
    ".kgg": KUGOU,
    ".kgm.flac": KUGOU,
    ".vpr": KUGOU,
    ".vpr.flac": KUGOU,

    # ---------------- 酷我音乐（kwm） ----------------
    ".kwm": KUWO,

    # ---------------- 喜马拉雅（ximalaya / xiami 解码器） ----------------
    ".x2m": XIMALAYA,
    ".x3m": XIMALAYA,
    ".xm": XIMALAYA,
}

# 按后缀长度降序：保证 .kgm.flac 先于 .flac、.mflac1 先于 .mflac 命中
_SORTED_SUFFIXES = sorted(_SUFFIX_TO_ICON, key=len, reverse=True)


def platform_icon(path) -> PlatformIcon | None:
    """返回文件对应的平台图标（``PlatformIcon`` 枚举）；无平台图标返回 None。

    仅做字符串后缀判定，不访问磁盘、不依赖 UI，可在任意层调用。
    返回值可直接传给接受 ``FluentIconBase`` 的组件，或用 ``.path()`` 取 ``:/`` 路径。
    """
    lower = str(path).lower()
    for suffix in _SORTED_SUFFIXES:
        if lower.endswith(suffix):
            return _SUFFIX_TO_ICON[suffix]
    return None
