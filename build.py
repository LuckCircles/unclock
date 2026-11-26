"""Nuitka standalone 打包脚本。

用法：.venv/Scripts/python.exe build.py
产物：releases/main.dist/音乐解锁工具.exe（多文件目录，内嵌 um.exe / ffmpeg.exe / qmpc-mmkv-cli.exe / um_cli_rs.exe）
"""

import importlib.util
import os
import shutil
import subprocess
import struct
import sys
import time
import tomllib
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

ROOT = Path(__file__).resolve().parent

MAIN_SCRIPT = "main.py"
APP_NAME = "音乐解锁工具"
ICON_SVG = "app/resource/img/icon.svg"
ICON_PATH = "app/resource/img/icon.ico"
OUTPUT_DIR = "releases"
EXE_BASENAME = APP_NAME
DIST_SUFFIX = ".dist"


def load_version() -> str:
    """从 pyproject.toml 读取 [project].version。"""
    with open(ROOT / "pyproject.toml", "rb") as f:
        return tomllib.load(f)["project"]["version"]


def compile_qrc() -> None:
    """编译 app/resource/resource.qrc -> app/resource/resource_rc.py（图片资源注册）。"""
    rcc = ROOT / ".venv" / "Scripts" / "pyside6-rcc.exe"
    if not rcc.exists():
        found = shutil.which("pyside6-rcc")
        rcc = Path(found) if found else rcc
    if not rcc.exists():
        print("[预检失败] 未找到 pyside6-rcc")
        sys.exit(1)
    subprocess.run(
        [str(rcc), str(ROOT / "app" / "resource" / "resource.qrc"),
         "-o", str(ROOT / "app" / "resource" / "resource_rc.py")],
        check=True, cwd=str(ROOT / "app" / "resource"),
    )


def build_windows_icon() -> None:
    """把 ``icon.svg`` 光栅化为多尺寸 ``icon.ico``，供 Nuitka 写 PE 资源。

    Nuitka 的 ``--windows-icon-from-ico`` 只接受 ICO；环境没有 imageio，
    因此用项目已有的 QtSvg 渲染 SVG，再手写 ICO 目录（PNG 压缩条目，
    Windows Vista+ 原生支持），不新增任何依赖。每次构建都从 SVG 重新生成，
    保证打包图标与窗口图标是同一张图。
    """
    svg_path = ROOT / ICON_SVG
    ico_path = ROOT / ICON_PATH
    if not svg_path.is_file():
        print(f"[预检失败] SVG 图标不存在：{svg_path}")
        sys.exit(1)

    # 构建脚本无 GUI 窗口：临时切 offscreen 创建 QGuiApplication 供 QPainter 用
    previous_platform = os.environ.get("QT_QPA_PLATFORM")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        # 局部变量保活：QPainter 渲染期间 QGuiApplication 不能被回收
        app = QGuiApplication.instance() or QGuiApplication([])
        renderer = QSvgRenderer(str(svg_path))
        if not renderer.isValid():
            print(f"[预检失败] SVG 图标无效：{svg_path}")
            sys.exit(1)
        entries: list[tuple[int, bytes]] = []
        for size in (16, 24, 32, 48, 64, 128, 256):
            image = QImage(size, size, QImage.Format_ARGB32)
            image.fill(Qt.transparent)
            painter = QPainter(image)
            painter.setRenderHint(QPainter.Antialiasing, True)
            renderer.render(painter)
            painter.end()
            # QBuffer 必须持有 QByteArray 实体：用临时对象会在 save 后失效
            byte_array = QByteArray()
            buffer = QBuffer(byte_array)
            buffer.open(QIODevice.WriteOnly)
            if not image.save(buffer, "PNG"):
                buffer.close()
                print(f"[预检失败] 图标 {size}×{size} 转 PNG 失败")
                sys.exit(1)
            buffer.close()
            entries.append((size, bytes(byte_array)))
        del app
    finally:
        if previous_platform is None:
            os.environ.pop("QT_QPA_PLATFORM", None)
        else:
            os.environ["QT_QPA_PLATFORM"] = previous_platform

    # ICONDIR + ICONDIRENTRY：256 在单字节宽高字段中记作 0
    directory = bytearray(struct.pack("<HHH", 0, 1, len(entries)))
    payload = bytearray()
    offset = 6 + 16 * len(entries)
    for size, png in entries:
        dimension = 0 if size == 256 else size
        directory.extend(struct.pack(
            "<BBBBHHII", dimension, dimension, 0, 0, 1, 32, len(png), offset
        ))
        payload.extend(png)
        offset += len(png)
    ico_path.write_bytes(bytes(directory) + bytes(payload))
    print(f"  图标已从 {ICON_SVG} 生成：{ICON_PATH}（{len(entries)} 个尺寸）")


def preflight() -> None:
    """预检 Nuitka、入口脚本、tools 目录及内嵌可执行文件。"""
    compile_qrc()
    build_windows_icon()
    # 构建命令走 `python -m nuitka`，以模块可导入为准；
    # 只看 Scripts/nuitka.exe 或 PATH 会在 Nuitka 仅作为库安装时误报缺失
    if importlib.util.find_spec("nuitka") is None:
        print("[预检失败] 未找到 Nuitka，请先安装：uv add nuitka")
        sys.exit(1)

    required = [
        ROOT / MAIN_SCRIPT,
        ROOT / "tools",
        ROOT / ICON_PATH,
        ROOT / "tools" / "um.exe",
        ROOT / "tools" / "ffmpeg.exe",
        ROOT / "tools" / "qmpc-mmkv-cli.exe",
        ROOT / "tools" / "um_cli_rs.exe",
        ROOT / "app" / "resource" / "i18n" / "en_US.qm",
        ROOT / "app" / "resource" / "i18n" / "zh_CN.qm",
    ]
    missing = [str(p) for p in required if not p.exists()]
    if missing:
        print(f"[预检失败] 文件不存在：{'、'.join(missing)}")
        sys.exit(1)


def build_command(version: str) -> list[str]:
    cmd = [
        sys.executable, "-m", "nuitka",
        "--standalone",
        "--remove-output",
        f"--output-dir={OUTPUT_DIR}",
        f"--output-filename={EXE_BASENAME}.exe",
        "--msvc=latest",
        f"--jobs={os.cpu_count() or 8}",
        #"--disable-ccache",
        "--assume-yes-for-downloads",
        "--follow-imports",
        "--enable-plugins=pyside6",
        "--include-package-data=qfluentwidgets",
        #"--windows-console-mode=disable",
        f"--windows-icon-from-ico={ICON_PATH}",
        "--windows-company-name=unclock",
        f"--windows-product-name={APP_NAME}",
        "--file-description=Unlock Music GUI",
        f"--file-version={version}",
        f"--product-version={version}",
        f"--main={MAIN_SCRIPT}",
        "--include-windows-runtime-dlls=yes",
        # 全量扫描 qfluentwidgets / qframelesswindow / app 的 PySide6 依赖：
        # 只用到 QtCore / QtGui / QtWidgets / QtSvg / QtSvgWidgets / QtXml，
        # 零 QtPdf / QtNetwork。这两个 DLL 是 imageformats/qpdf 与 tls
        # 插件的依赖闭包被 Nuitka 默认拖入；排除后减 ~10MB，无代码路径触发
        "--noinclude-dlls=Qt6Pdf*",
        "--noinclude-dlls=*Qt6Network*",
        # ---- 以下为 2026-11-05 main.dist 体积分析（~196MB）确认的二次排除 ----
        # OpenSSL（9.12MB）：仅 QtNetwork TLS 使用，应用零网络代码；
        # 2026-11-05 已实测启动 exe 通过（当前代码路径未 import ssl），
        # 但 _ssl.pyd 链接它们——若后续引入网络/HTTPS 代码，必须删这两条，
        # 否则 import ssl 会报 DLL load failed
        "--noinclude-dlls=libcrypto-3-x64.dll",
        "--noinclude-dlls=libssl-3-x64.dll",
        # TLS 插件后端（0.65MB）：随 QtNetwork 一并排除
        "--noinclude-dlls=**/tls/*",
        # QtNetwork 绑定：qfluentwidgets 与 app 全量扫描零 import；
        # PySide6/__init__.py:89 的探测有 try/except ImportError 保护，排除安全
        "--nofollow-import-to=PySide6.QtNetwork",
        # 【不可排除 PySide6.QtXml / Qt6Xml.dll】
        # qfluentwidgets/common/icon.py:6 顶层 from PySide6.QtXml import QDomDocument，
        # 用于 SVG 图标着色；common/__init__.py 是 qfluentwidgets 导入的必经路径
        # （qfluentwidgets/__init__ -> components/dialog_box/color_dialog
        #  -> common/__init__ -> icon.py）。排除会在启动时抛 ImportError：
        # "Module 'PySide6.QtXml' was actively excluded from Nuitka compilation"。
        # 故 QtXml.pyd 与 Qt6Xml.dll 必须随包，不再加入任何排除项。
        # 平台插件（1.2MB）：仅保留实际使用的 qwindows
        "--noinclude-dlls=**/qdirect2d.dll",
        "--noinclude-dlls=**/qminimal.dll",
        "--noinclude-dlls=**/qoffscreen.dll",
        # 图片格式插件：保留 png/ico/svg（qrc 与 FluentIcon）与 jpeg
        # 【不可排除 qjpeg.dll】封面标签直读拿到的是原始 JPEG（实测当前音乐库
        # 238/350 FLAC + 29/29 MP3 为 JPEG），QImage.fromData 解码必须靠它；
        # 排除后打包版所有 JPEG 封面显示为空且「保存封面」无法转 PNG。
        # 体积代价约 0.56MB，换取封面解析零 ffmpeg 进程。
        "--noinclude-dlls=**/imageformats/qwebp.dll",
        "--noinclude-dlls=**/imageformats/qtiff.dll",
        "--noinclude-dlls=**/imageformats/qicns.dll",
        "--noinclude-dlls=**/imageformats/qtga.dll",
        "--noinclude-dlls=**/imageformats/qgif.dll",
        "--noinclude-dlls=**/imageformats/qpdf.dll",
        # 【不可排除 pywin32】qframelesswindow 无边框窗口的硬依赖：
        # qframelesswindow/utils/win32_utils.py:9-12 与 windows/__init__.py:5-7
        # 无条件 import win32api / win32con / win32gui / win32print，
        # qfluentwidgets/components/widgets/frameless_window.py:8 亦 import win32con。
        # 排除任一模块都会在启动时抛 ImportError（"actively excluded"），
        # 且 win32api.pyd 依赖 pywintypes312.dll，该 DLL 同样必须随包。
        # 故下面不再对 pywin32 做任何排除。
    ]
    # 基于脚本所在目录扫描 tools/*.exe，不依赖调用方 cwd：
    # 先前 glob("tools/*.exe") 在其它工作目录运行时会静默漏打三个工具，
    # 而预检用的是 ROOT 绝对路径仍会通过，形成「预检通过但产物不全」
    exe_files = sorted((ROOT / "tools").glob("*.exe"))
    if not exe_files:
        print("[警告] tools/ 下未发现任何 .exe")
    for exe in exe_files:
        rel = f"tools/{exe.name}"
        cmd.append(f"--include-data-file={exe.as_posix()}={rel}")
        print(f"  包含 exe: {rel}")
    # 翻译文件（qm）已编入 qrc（:/i18n/...）并编译进 resource_rc.py，
    # 与图片资源同源，无需再作为运行时数据文件内嵌
    # 图片资源已编译进 resource_rc.py（qrc），无需包含 img 目录
    return cmd


def main() -> None:
    preflight()
    version = load_version()
    command = build_command(version)

    print(f"版本号：{version}（来源 pyproject.toml）")
    print("执行命令：")
    print(" ".join(command))
    print()

    start = time.perf_counter()
    try:
        subprocess.run(command, check=True, cwd=str(ROOT))
    except subprocess.CalledProcessError as e:
        print(f"\n编译过程中出现错误：{e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n已取消编译")
        sys.exit(130)

    # Nuitka standalone 的产物目录按入口脚本名命名（main.py -> main.dist），
    # --output-filename 只改 exe 文件名，不会改目录名
    dist_dir = ROOT / OUTPUT_DIR / f"{Path(MAIN_SCRIPT).stem}{DIST_SUFFIX}"
    exe_path = dist_dir / f"{EXE_BASENAME}.exe"
    elapsed = time.perf_counter() - start
    print(f"\n编译成功完成！耗时 {elapsed / 60:.1f} 分钟")
    print(f"产物目录：{dist_dir}")
    if exe_path.exists():
        size_mb = exe_path.stat().st_size / 1024 / 1024
        total_mb = sum(f.stat().st_size for f in dist_dir.rglob("*") if f.is_file()) / 1024 / 1024
        print(f"主程序大小：{size_mb:.1f} MB")
        print(f"整个目录大小：{total_mb:.1f} MB")
        print(f"入口：{exe_path}")


if __name__ == "__main__":
    main()
