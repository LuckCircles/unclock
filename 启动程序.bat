@echo off
chcp 65001 >nul

:: 获取 bat 文件所在目录
set "BAT_DIR=%~dp0"

:: 相对 bat 文件位置找到 .conda
uv run main.py

pause