"""Nuitka standalone 打包脚本。

用法：.venv\\Scripts\\python.exe build.py
产物：releases\\音乐解锁工具.dist\\音乐解锁工具.exe（多文件目录，内嵌 um.exe / ffmpeg.exe / qmpc-mmkv-cli.exe）
"""

import os
import shutil
import subprocess
import sys
import time
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent

MAIN_SCRIPT = "main.py"
APP_NAME = "音乐解锁工具"
ICON_PATH = "app/resources/img/pwa.ico"
OUTPUT_DIR = "releases"
EXE_BASENAME = APP_NAME
DIST_SUFFIX = ".dist"


def load_version() -> str:
    """从 pyproject.toml 读取 [project].version。"""
    with open(ROOT / "pyproject.toml", "rb") as f:
        return tomllib.load(f)["project"]["version"]


def compile_qrc() -> None:
    """编译 app/resource.qrc -> app/resource_rc.py（图片资源注册）。"""
    rcc = ROOT / ".venv" / "Scripts" / "pyside6-rcc.exe"
    if not rcc.exists():
        found = shutil.which("pyside6-rcc")
        rcc = Path(found) if found else rcc
    if not rcc.exists():
        print("[预检失败] 未找到 pyside6-rcc")
        sys.exit(1)
    subprocess.run(
        [str(rcc), str(ROOT / "app" / "resource.qrc"),
         "-o", str(ROOT / "app" / "resource_rc.py")],
        check=True, cwd=str(ROOT),
    )


def preflight() -> None:
    """预检 Nuitka、入口脚本、resources 目录及内嵌可执行文件。"""
    compile_qrc()
    if (
        shutil.which("nuitka") is None
        and not (ROOT / ".venv" / "Scripts" / "nuitka.exe").exists()
    ):
        print("[预检失败] 未找到 Nuitka，请先安装：uv add nuitka")
        sys.exit(1)

    required = [
        ROOT / MAIN_SCRIPT,
        ROOT / "app" / "resources",
        ROOT / ICON_PATH,
        ROOT / "app" / "resources" / "um.exe",
        ROOT / "app" / "resources" / "ffmpeg.exe",
        ROOT / "app" / "resources" / "qmpc-mmkv-cli.exe",
    ]
    missing = [str(p) for p in required if not p.exists()]
    if missing:
        print(f"[预检失败] 文件不存在：{'、'.join(missing)}")
        sys.exit(1)


def build_command(version: str) -> list[str]:
    return [
        sys.executable, "-m", "nuitka",
        "--standalone",
        "--remove-output",
        f"--output-dir={OUTPUT_DIR}",
        f"--output-filename={EXE_BASENAME}.exe",
        "--msvc=latest",
        f"--jobs={os.cpu_count() or 8}",
        "--disable-ccache",
        "--assume-yes-for-downloads",
        "--follow-imports",
        "--enable-plugins=pyside6,anti-bloat",
        "--include-package-data=qfluentwidgets",
        "--include-data-dir=app/resources=app/resources",
        "--windows-console-mode=disable",
        f"--windows-icon-from-ico={ICON_PATH}",
        "--windows-company-name=unclock",
        f"--windows-product-name={APP_NAME}",
        "--file-description=Unlock Music GUI",
        f"--file-version={version}",
        f"--product-version={version}",
        f"--main={MAIN_SCRIPT}",
        "--include-windows-runtime-dlls=yes",
    ]


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

    dist_dir = ROOT / OUTPUT_DIR / f"{EXE_BASENAME}{DIST_SUFFIX}"
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
