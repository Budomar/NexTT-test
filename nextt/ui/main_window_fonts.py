"""
Управление масштабом шрифтов главного окна NexTT.

Вынесено из MainWindow:
    • _increase_font_scale / _decrease_font_scale — изменение масштаба
    • _refresh_all_fonts                          — полное обновление всех шрифтов
    • _update_all_cells_fonts                     — обновление шрифтов матрицы
    • _update_all_labels_fonts_recursive          — рекурсивное обновление ttk.Label
    • _update_checkbutton_fonts_recursive         — обновление чекбоксов
    • _update_tooltip_fonts                       — обновление шрифтов в подсказке
"""

from tkinter import ttk
import tkinter as tk

from nextt.events import bus, Events
from nextt.logger import get_logger

logger = get_logger(__name__)


# ======================================================================
# Изменение масштаба
# ======================================================================

def increase_font_scale(main_window) -> None:
    """Увеличивает масштаб шрифтов во всех окнах."""
    main_window.app.font_manager.increase()
    refresh_all_fonts(main_window)


def decrease_font_scale(main_window) -> None:
    """Уменьшает масштаб шрифтов во всех окнах."""
    main_window.app.font_manager.decrease()
    refresh_all_fonts(main_window)


# ======================================================================
# Полное обновление шрифтов
# ======================================================================

def refresh_all_fonts(main_window) -> None:
    """
    Обновляет шрифты во всех окнах приложения.
    Вызывается после изменения масштаба.
    """
    app = main_window.app

    # Обновляем значение в окошке
    if hasattr(main_window, 'font_scale_var'):
        main_window.font_scale_var.set(f"{app.font_manager.scale:.2f}")

    # Пересоздаём стили
    main_window._setup_styles()

    # Пересобираем UI
    from nextt.ui.main_window_state import rebuild_all_ui
    rebuild_all_ui(main_window)

    # Обновляем шрифты через FontManager
    app.font_manager.refresh_all_windows(main_window.root)

    # Обновляем шрифты в ячейках матрицы
    update_all_cells_fonts(main_window)

    # Обновляем шрифты в подсказке
    update_tooltip_fonts(main_window)

    # Перестраиваем матрицу
    main_window._build_matrix(
        main_window._conn_var.get(),
        main_window._type_var.get(),
    )

    # Отправляем событие об изменении масштаба
    bus.emit(Events.FONT_SCALE_CHANGED, scale=app.font_manager.scale)

    # Обновляем шрифт контекстного меню в предпросмотре (если открыт)
    if hasattr(main_window, '_preview_dialog') and main_window._preview_dialog:
        try:
            if hasattr(main_window._preview_dialog, '_update_context_menu_font'):
                main_window._preview_dialog._update_context_menu_font()
        except Exception as e:
            logger.debug(f"Ошибка обновления шрифта меню предпросмотра: {e}")


# ======================================================================
# Обновление шрифтов в ячейках матрицы
# ======================================================================

def update_all_cells_fonts(main_window) -> None:
    """Обновляет шрифты во всех ячейках матрицы."""
    default_font = main_window.app.font_manager.get_default_font()
    heading_font = main_window.app.font_manager.get_heading_font()

    # Обновляем ячейки
    for (row, col), entry in main_window._cell_entries.items():
        try:
            if entry and entry.winfo_exists():
                entry.configure(font=default_font)
        except (tk.TclError, AttributeError):
            pass

    # Обновляем заголовки столбцов
    for lbl in main_window._col_headers.values():
        try:
            if lbl and lbl.winfo_exists():
                lbl.configure(font=heading_font)
        except (tk.TclError, AttributeError):
            pass

    # Обновляем заголовки строк
    for lbl in main_window._row_headers.values():
        try:
            if lbl and lbl.winfo_exists():
                lbl.configure(font=heading_font)
        except (tk.TclError, AttributeError):
            pass


# ======================================================================
# Рекурсивное обновление ttk.Label и чекбоксов
# ======================================================================

def update_all_labels_fonts_recursive(main_window, widget, font) -> None:
    """
    Рекурсивно обходит виджеты и обновляет шрифт у всех ttk.Label.
    Также обновляет сохранённые ссылки на служебные метки.
    """
    try:
        if not widget.winfo_exists():
            return
    except (tk.TclError, AttributeError):
        return

    # Обновляем сам виджет
    try:
        if isinstance(widget, ttk.Label):
            widget.config(font=font)
    except (tk.TclError, AttributeError):
        pass

    # Рекурсивно обходим детей
    try:
        for child in widget.winfo_children():
            update_all_labels_fonts_recursive(main_window, child, font)
    except (tk.TclError, AttributeError):
        pass

    # Обновляем сохранённые ссылки на служебные метки
    _refresh_label_attr(main_window, '_scale_label', font)
    _refresh_label_attr(main_window, '_bracket_title_label', font)
    _refresh_label_attr(main_window, '_radiator_discount_label', font)
    _refresh_label_attr(main_window, '_bracket_discount_label', font)


def update_checkbutton_fonts_recursive(main_window, widget, font) -> None:
    """
    Рекурсивно обходит виджеты и обновляет шрифт у чекбокса
    «Показывать параметры и стоимость» (если такой есть).
    """
    try:
        if not widget.winfo_exists():
            return
    except (tk.TclError, AttributeError):
        return

    try:
        if isinstance(widget, ttk.Checkbutton):
            text = widget.cget('text')
            if text == "Показывать параметры и стоимость":
                widget.config(font=font)
    except (tk.TclError, AttributeError):
        pass

    try:
        for child in widget.winfo_children():
            update_checkbutton_fonts_recursive(main_window, child, font)
    except (tk.TclError, AttributeError):
        pass


def _refresh_label_attr(main_window, attr_name: str, font) -> None:
    """Пытается установить новый шрифт у метки по имени атрибута."""
    try:
        label = getattr(main_window, attr_name, None)
        if label and label.winfo_exists():
            label.config(font=font)
    except (tk.TclError, AttributeError):
        pass


# ======================================================================
# Обновление шрифтов в подсказке для ячеек
# ======================================================================

def update_tooltip_fonts(main_window) -> None:
    """Обновляет шрифты в существующей подсказке при изменении масштаба."""
    if not hasattr(main_window, '_tooltip_window') or not main_window._tooltip_window:
        return

    if not main_window._tooltip_window.winfo_exists():
        return

    font_manager = main_window.app.font_manager
    default_font = font_manager.get_default_font()
    bold_font = font_manager.get_bold_font()
    italic_font = font_manager.get_font(9)

    if hasattr(main_window, '_tip_name'):
        main_window._tip_name.config(font=bold_font)
    if hasattr(main_window, '_tip_art'):
        main_window._tip_art.config(font=default_font)
    if hasattr(main_window, '_tip_params'):
        main_window._tip_params.config(font=default_font)
    if hasattr(main_window, '_tip_price'):
        main_window._tip_price.config(font=bold_font)
    if hasattr(main_window, '_tip_bracket_info'):
        main_window._tip_bracket_info.config(font=italic_font)
    if hasattr(main_window, '_tip_bracket_lines'):
        for lbl in main_window._tip_bracket_lines:
            lbl.config(font=default_font)
    if hasattr(main_window, '_tip_total'):
        main_window._tip_total.config(font=bold_font)