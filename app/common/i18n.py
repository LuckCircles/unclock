# coding: utf-8
"""中英文切换 —— 基于 Qt Linguist 翻译文件。

设计要点：

* 翻译文件 ``en_US.qm`` / ``zh_CN.qm`` 编译进 qrc（``:/i18n/*.qm``），
  随 ``resource_rc.py`` 内嵌，无需在发行版中额外携带数据文件。
  ``en_US.qm``：中文原文 → 英文；``zh_CN.qm`` 为其反向表。
  任一时刻只安装其中一个翻译器：英文模式装 en_US，中文模式装 zh_CN。
  这样既覆盖「代码里写中文」的既有界面，也能在切回中文时把已显示的英文还原。
* 按 QFluentWidgets 官方 i18n 方案加装 :class:`FluentTranslator`，
  翻译库内置组件文案（日历、对话框等），语言跟随当前选择。
* 文案设置入口（setText / setToolTip / setWindowTitle / ComboBox 项）统一经
  :func:`translate_ui` 过滤，动态创建的卡片与弹窗无需改动源码即可被翻译。
* 切换语言时再遍历现有控件重翻译一次，保证已显示的文本立即变化。
"""

from __future__ import annotations

import re
from typing import Callable, Iterable

from PySide6.QtCore import QCoreApplication, QEvent, QLocale, QObject, QTimer, QTranslator
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QAbstractButton,
    QComboBox,
    QLabel,
    QLineEdit,
    QWidget,
)
from qfluentwidgets import ComboBox as FluentComboBox
from qfluentwidgets import FluentTranslator

from .config import PROJECT_ROOT, cfg

CONTEXT = "UI"
I18N_DIR = PROJECT_ROOT / "app" / "resource" / "i18n"  # ts/qm 源文件位置（开发期）
_QM_RESOURCE = ":/i18n/{}.qm"  # qrc 编译后的运行时加载路径
_DIGITS = re.compile(r"\d+")

_LANGUAGES = {"中文": "zh_CN", "英文": "en_US"}
_current_mode: str | None = None
_translator: QTranslator | None = None
_fluent_translator: QTranslator | None = None
_patched = False
# 语言切换后的重建回调：动态拼接文案（计数、参数提示等）无法靠查表还原，
# 由注册方在回调里用 translate_ui 按新语言重新拼装
_retranslate_hooks: list[Callable[[], None]] = []


def register_retranslate_hook(fn: Callable[[], None]) -> None:
    """注册语言切换后的重建回调（幂等；回调异常不影响其余切换流程）。"""
    if fn not in _retranslate_hooks:
        _retranslate_hooks.append(fn)


def resolve_language(value: str | None = None) -> str:
    """把配置值解析为 ``zh_CN`` / ``en_US``；自动跟随系统语言。"""
    choice = value if value is not None else str(cfg.language.value)
    if choice in _LANGUAGES:
        return _LANGUAGES[choice]
    if choice == "自动":
        return (
            "zh_CN"
            if QLocale.system().language() == QLocale.Language.Chinese
            else "en_US"
        )
    return "zh_CN"


def translate_ui(text: str) -> str:
    """翻译一段界面文案；未命中翻译表时原样返回。

    带数字的提示（如 ``已解密 3``）先把数字归一为 ``%1`` 再查表，
    命中后按出现顺序把数字填回，避免为每个计数写一条翻译。
    """
    if not isinstance(text, str) or not text:
        return text
    if QCoreApplication.instance() is None:
        return text

    translated = QCoreApplication.translate(CONTEXT, text)
    if translated != text or not _DIGITS.search(text):
        return translated

    template = _DIGITS.sub("%1", text)
    translated = QCoreApplication.translate(CONTEXT, template)
    if translated == template:
        return text
    for number in _DIGITS.findall(text):
        translated = translated.replace("%1", number, 1)
    return translated


def _wrap(cls, name: str, positions: Iterable[int] = (0,)) -> None:
    """把类的文案参数设置方法包一层翻译；原方法是 C++ 实现，不会递归。"""
    original = getattr(cls, name)
    positions = tuple(positions)

    def wrapper(self, *args, **kwargs):
        args = list(args)
        for index in positions:
            if index < len(args) and isinstance(args[index], str):
                args[index] = translate_ui(args[index])
        for key in ("text", "title"):
            if isinstance(kwargs.get(key), str):
                kwargs[key] = translate_ui(kwargs[key])
        return original(self, *args, **kwargs)

    wrapper.__name__ = name
    setattr(cls, name, wrapper)


def install_patches() -> None:
    """安装文案拦截（幂等）。模块导入时自动调用。"""
    global _patched
    if _patched:
        return

    for cls in (QLabel, QAbstractButton, QAction, QWidget):
        if hasattr(cls, "setText"):
            _wrap(cls, "setText")
    for cls in (QWidget,):
        _wrap(cls, "setToolTip")
        _wrap(cls, "setWindowTitle")
    _wrap(QLineEdit, "setPlaceholderText")

    for cls in (QComboBox, FluentComboBox):
        _wrap(cls, "addItem")
        _wrap(cls, "setCurrentText")
        _wrap(cls, "setItemText", positions=(1,))
        _wrap(cls, "insertItem", positions=(1,))
        if cls is FluentComboBox:
            # Fluent ComboBox 继承 QPushButton 并不走 QAbstractButton.setText
            _wrap(cls, "setText")

        original_add_items = cls.addItems

        def add_items_wrapper(self, texts, _original=original_add_items):
            return _original(self, [translate_ui(t) for t in texts])

        add_items_wrapper.__name__ = "addItems"
        setattr(cls, "addItems", add_items_wrapper)

    _patched = True


def install_language() -> str:
    """按当前配置安装/替换翻译器，返回实际使用的语言标识。

    同时安装两个翻译器：本项目 qm（qrc 内嵌）+ FluentTranslator
    （QFluentWidgets 官方 i18n 方案，翻译库内置组件文案）。
    """
    global _current_mode, _translator, _fluent_translator

    mode = resolve_language()
    if mode == _current_mode:
        return mode

    app = QCoreApplication.instance()
    if app is not None:
        if _translator is not None:
            app.removeTranslator(_translator)
        if _fluent_translator is not None:
            app.removeTranslator(_fluent_translator)

        translator = QTranslator(app)
        if translator.load(_QM_RESOURCE.format(mode)):
            app.installTranslator(translator)
            _translator = translator
        else:
            _translator = None

        locale = QLocale(QLocale.Chinese, QLocale.China) if mode == "zh_CN" \
            else QLocale(QLocale.English, QLocale.UnitedStates)
        _fluent_translator = FluentTranslator(locale, parent=app)
        app.installTranslator(_fluent_translator)
    _current_mode = mode
    return mode


def _retranslate_one(widget: QWidget) -> None:
    targets = (
        ("text", "setText"),
        ("windowTitle", "setWindowTitle"),
        ("toolTip", "setToolTip"),
        ("placeholderText", "setPlaceholderText"),
    )
    for getter_name, setter_name in targets:
        getter = getattr(widget, getter_name, None)
        setter = getattr(widget, setter_name, None)
        if not callable(getter) or not callable(setter):
            continue
        try:
            current = getter()
        except (RuntimeError, TypeError):
            continue  # 控件可能已在销毁过程中
        if not isinstance(current, str) or not current:
            continue
        updated = translate_ui(current)
        if updated != current:
            setter(updated)

    if isinstance(widget, (QComboBox, FluentComboBox)):
        for index in range(widget.count()):
            current = widget.itemText(index)
            updated = translate_ui(current)
            if updated != current:
                widget.setItemText(index, updated)


def retranslate_widgets(root: QWidget | None = None) -> None:
    """把已有控件文案按最新语言重翻译一遍；可限定在一棵控件树内。"""
    app = QCoreApplication.instance()
    if app is None:
        return
    if root is not None:
        widgets = [root, *root.findChildren(QWidget)]
    elif hasattr(app, "allWidgets"):
        widgets = list(app.allWidgets())
    else:
        return
    for widget in widgets:
        _retranslate_one(widget)


class _WindowShowFilter(QObject):
    """新建窗口显示时补翻译：构造参数传入的文本不会经过 setText 拦截。"""

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Show and isinstance(obj, QWidget) and obj.isWindow():
            QTimer.singleShot(0, lambda window=obj: retranslate_widgets(window))
        return False


_show_filter: _WindowShowFilter | None = None


def apply_language() -> str:
    """完整应用语言：安装翻译器 + 重翻译现有控件 + 重建动态文案。"""
    global _show_filter
    mode = install_language()
    retranslate_widgets()
    for fn in list(_retranslate_hooks):
        try:
            fn()
        except Exception:  # noqa: BLE001 单个重建失败不影响整体切换
            from .logger import logger

            logger.warning(f"语言重建回调失败: {fn.__qualname__}")
    app = QCoreApplication.instance()
    if app is not None and _show_filter is None:
        _show_filter = _WindowShowFilter(app)
        app.installEventFilter(_show_filter)
    return mode


install_patches()
