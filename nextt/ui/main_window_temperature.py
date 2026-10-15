"""
Строка температурного графика главного окна NexTT.

Вынесено из MainWindow:
    • _create_temperature_graph_row  — построение строки
    • _validate_temperature          — валидация полей
    • _on_graph_changed              — реакция на изменение графика
    • _on_graph_reset                — сброс к 95/85/20
    • _on_graph_show                 — открытие справочного окна
    • _current_delta_t               — вычисление текущего Δt
"""

import tkinter as tk
from tkinter import ttk, messagebox

from nextt.core.power_recalculator import PowerRecalculator
from nextt.logger import get_logger

logger = get_logger(__name__)


# ======================================================================
# Построение строки температурного графика
# ======================================================================

def create_temperature_graph_row(parent: ttk.Frame, main_window) -> None:
    """
    Строка ввода температурного графика и проекта между матрицей
    и нижней панелью.

    Слева — поле «Проект:», справа — температурный график
    (Подача / Обратка / Помещение) с меткой Δt.

    Подписи «Проект:» и «Температурный график:» — жирные, чёрные.
    Остальные подписи (Подача/Обратка/Помещение/°С) — обычные, чёрные.
    Метка Δt — обычная, синяя.
    """
    font_manager = main_window.app.font_manager
    default_font = font_manager.get_default_font()
    bold_font = font_manager.get_bold_font()

    # При старте приложения всегда используем эталонный график 95/85/20
    graph = main_window.app.temperature_graph

    # Внешняя рамка строки
    outer = tk.Frame(parent, relief="solid", borderwidth=1, bg='#dedede')
    outer.pack(fill="x", padx=2, pady=(2, 4))

    inner = tk.Frame(outer, bg='#dedede')
    inner.pack(fill="x", padx=10, pady=6)

    # ================================================================
    # СЛЕВА — ПРОЕКТ
    # ================================================================
    tk.Label(
        inner, text="Проект:",
        font=bold_font, bg='#dedede', fg='#000000',
    ).pack(side="left", padx=(0, 6))

    main_window._project_entry = tk.Entry(
        inner,
        textvariable=main_window.project_var,
        font=default_font,
        width=45,
        justify="left",
    )
    main_window._project_entry.pack(
        side="left", fill="x", expand=True, padx=(0, 20),
    )

    _bind_entry_shortcuts(main_window._project_entry)

    # ================================================================
    # СПРАВА — КНОПКИ
    # ================================================================
    main_window._graph_show_btn = ttk.Button(
        inner, text="Показать",
        command=lambda: on_graph_show(main_window),
    )
    main_window._graph_show_btn.pack(side="right", padx=(6, 0))

    main_window._graph_reset_btn = ttk.Button(
        inner, text="Сброс до 95/85/20",
        command=lambda: on_graph_reset(main_window),
    )
    main_window._graph_reset_btn.pack(side="right")

    # ================================================================
    # СПРАВА — ГРАФИК (пакуем справа налево)
    # ================================================================
    # Δt (правый край графической группы) — обычный, синий
    main_window._delta_t_label = tk.Label(
        inner, text="Δt = 70,00 °С",
        font=default_font, bg='#dedede', fg='#263168',
    )
    main_window._delta_t_label.pack(side="right", padx=(12, 0))

    # Помещение
    tk.Label(
        inner, text="°С",
        font=default_font, bg='#dedede', fg='#000000',
    ).pack(side="right", padx=(2, 0))

    main_window._graph_room_var = tk.StringVar(value=str(graph.get("room", 20)))
    main_window._graph_room_entry = tk.Entry(
        inner,
        textvariable=main_window._graph_room_var,
        width=5,
        font=default_font,
        justify="center",
        validate="key",
        validatecommand=(main_window.root.register(validate_temperature), '%P'),
    )
    main_window._graph_room_entry.pack(side="right", padx=(2, 2))

    tk.Label(
        inner, text="Помещение:",
        font=default_font, bg='#dedede', fg='#000000',
    ).pack(side="right", padx=(0, 2))

    # Обратка
    tk.Label(
        inner, text="°С",
        font=default_font, bg='#dedede', fg='#000000',
    ).pack(side="right", padx=(2, 0))

    main_window._graph_return_var = tk.StringVar(value=str(graph.get("return", 85)))
    main_window._graph_return_entry = tk.Entry(
        inner,
        textvariable=main_window._graph_return_var,
        width=5,
        font=default_font,
        justify="center",
        validate="key",
        validatecommand=(main_window.root.register(validate_temperature), '%P'),
    )
    main_window._graph_return_entry.pack(side="right", padx=(2, 2))

    tk.Label(
        inner, text="Обратка:",
        font=default_font, bg='#dedede', fg='#000000',
    ).pack(side="right", padx=(0, 2))

    # Подача
    tk.Label(
        inner, text="°С",
        font=default_font, bg='#dedede', fg='#000000',
    ).pack(side="right", padx=(2, 0))

    main_window._graph_supply_var = tk.StringVar(value=str(graph.get("supply", 95)))
    main_window._graph_supply_entry = tk.Entry(
        inner,
        textvariable=main_window._graph_supply_var,
        width=5,
        font=default_font,
        justify="center",
        validate="key",
        validatecommand=(main_window.root.register(validate_temperature), '%P'),
    )
    main_window._graph_supply_entry.pack(side="right", padx=(2, 2))

    tk.Label(
        inner, text="Подача:",
        font=default_font, bg='#dedede', fg='#000000',
    ).pack(side="right", padx=(0, 2))

    # Заголовок «Температурный график:» — жирный, чёрный
    tk.Label(
        inner, text="Температурный график:",
        font=bold_font, bg='#dedede', fg='#000000',
    ).pack(side="right", padx=(0, 12))

    # ================================================================
    # Подписка на изменения полей графика
    # ================================================================
    for var in (
        main_window._graph_supply_var,
        main_window._graph_return_var,
        main_window._graph_room_var,
    ):
        var.trace_add("write", lambda *args: on_graph_changed(main_window))

    # Первичное обновление метки Δt
    on_graph_changed(main_window)
    # ================================================================
    # Подписка на изменения полей графика
    # ================================================================
    for var in (
        main_window._graph_supply_var,
        main_window._graph_return_var,
        main_window._graph_room_var,
    ):
        var.trace_add("write", lambda *args: on_graph_changed(main_window))

    # Первичное обновление метки Δt
    on_graph_changed(main_window)

def _bind_entry_shortcuts(entry: tk.Entry) -> None:
    """
    Привязывает стандартные горячие клавиши к полю tk.Entry.

    Работает при любой раскладке клавиатуры (русской/английской),
    потому что использует физические keycode клавиш, а не символы.

    Поддерживаются:
        Ctrl+A  — выделить всё
        Ctrl+C  — копировать выделенное
        Ctrl+V  — вставить из буфера
        Ctrl+X  — вырезать выделенное
    """
    # Физические коды клавиш (Windows virtual-key codes)
    # Работают одинаково для любой раскладки.
    VK_A = 65
    VK_C = 67
    VK_V = 86
    VK_X = 88

    def select_all(event=None):
        entry.select_range(0, tk.END)
        entry.icursor(tk.END)
        return "break"

    def copy(event=None):
        try:
            text = entry.selection_get()
        except tk.TclError:
            return "break"
        entry.clipboard_clear()
        entry.clipboard_append(text)
        return "break"

    def paste(event=None):
        try:
            text = entry.clipboard_get()
        except tk.TclError:
            return "break"

        # Если есть выделение — удаляем его и вставляем поверх
        try:
            if entry.selection_present():
                entry.delete(tk.SEL_FIRST, tk.SEL_LAST)
        except tk.TclError:
            pass

        entry.insert(tk.INSERT, text)
        return "break"

    def cut(event=None):
        try:
            text = entry.selection_get()
        except tk.TclError:
            return "break"
        entry.clipboard_clear()
        entry.clipboard_append(text)
        try:
            entry.delete(tk.SEL_FIRST, tk.SEL_LAST)
        except tk.TclError:
            pass
        return "break"

    def on_ctrl_key(event):
        """
        Универсальный обработчик Ctrl+<клавиша>.
        Смотрит на физический keycode — работает при любой раскладке.
        """
        # Проверяем, что действительно зажат Ctrl (а не Alt, не Shift+Ctrl).
        # Маска Ctrl в Tkinter: 0x0004.
        if not (event.state & 0x0004):
            return None

        keycode = event.keycode

        if keycode == VK_A:
            return select_all(event)
        elif keycode == VK_C:
            return copy(event)
        elif keycode == VK_V:
            return paste(event)
        elif keycode == VK_X:
            return cut(event)

        return None

    # Привязываем универсальный обработчик к событию KeyPress
    # с модификатором Control. Tkinter сам вызовет его для любой клавиши.
    entry.bind("<Control-KeyPress>", on_ctrl_key, add="+")

# ======================================================================
# Валидация
# ======================================================================

def validate_temperature(value: str) -> bool:
    """Валидация поля температуры: пусто или целое 0..150."""
    if value == "":
        return True
    return value.isdigit() and 0 <= int(value) <= 150


# ======================================================================
# Реакция на изменение графика
# ======================================================================

def on_graph_changed(main_window) -> None:
    """
    Реакция на изменение температурного графика.
    НЕ перестраивает матрицу и НЕ трогает entry_values.
    Сохраняет график только в памяти приложения (без записи на диск).
    """
    # Защита: метод может быть вызван до создания виджетов
    if not hasattr(main_window, '_delta_t_label') or main_window._delta_t_label is None:
        return
    if not hasattr(main_window, '_graph_reset_btn') or main_window._graph_reset_btn is None:
        return
    if not hasattr(main_window, '_graph_supply_var') or main_window._graph_supply_var is None:
        return

    try:
        supply = int(main_window._graph_supply_var.get() or 95)
        ret = int(main_window._graph_return_var.get() or 85)
        room = int(main_window._graph_room_var.get() or 20)
    except (ValueError, AttributeError):
        return  # незавершённый ввод

    delta_t = PowerRecalculator.delta_t_from(supply, ret, room)

    # --- Обновление метки Δt ---
    try:
        main_window._delta_t_label.config(
            text=f"Δt = {delta_t:.2f} °С".replace('.', ',')
        )
    except tk.TclError:
        return

    if PowerRecalculator.is_reference(delta_t):
        # Эталонный график — синий цвет
        try:
            main_window._delta_t_label.config(fg='#263168')
            main_window._graph_reset_btn.config(state='disabled')
        except tk.TclError:
            pass
    elif delta_t > 0:
        # Нестандартный график — оранжевый цвет
        try:
            main_window._delta_t_label.config(fg='#d35400')
            main_window._graph_reset_btn.config(state='normal')
        except tk.TclError:
            pass
    else:
        # Некорректный график — красный цвет
        try:
            main_window._delta_t_label.config(fg='#c0392b')
            main_window._graph_reset_btn.config(state='normal')
        except tk.TclError:
            pass

    # --- Сохранение графика в памяти приложения (без записи на диск) ---
    main_window.app.temperature_graph = {
        "supply": supply,
        "return": ret,
        "room": room,
    }


# ======================================================================
# Сброс и показ
# ======================================================================

def on_graph_reset(main_window) -> None:
    """Сброс к эталонному графику 95/85/20."""
    if not hasattr(main_window, '_graph_supply_var') or main_window._graph_supply_var is None:
        return
    main_window._graph_supply_var.set("95")
    main_window._graph_return_var.set("85")
    main_window._graph_room_var.set("20")
    # trace_add автоматически вызовет on_graph_changed


def on_graph_show(main_window) -> None:
    """Открывает справочное окно «Пересчёт мощностей» при текущем графике."""
    try:
        from nextt.ui.dialogs.power_reference import PowerReferenceDialog
    except ImportError as e:
        logger.error(f"Не удалось загрузить окно пересчёта: {e}")
        return

    delta_t = current_delta_t(main_window)

    if delta_t <= 0:
        messagebox.showwarning(
            "Некорректный температурный график",
            "Температурный напор Δt ≤ 0.\n"
            "Проверьте значения подачи, обратки и температуры помещения.",
        )
        return

    graph = main_window.app.temperature_graph
    dialog = PowerReferenceDialog(main_window.app, graph, delta_t)
    dialog.show()


# ======================================================================
# Вычисление текущего Δt
# ======================================================================

def current_delta_t(main_window) -> float:
    """
    Возвращает текущий температурный напор.
    Если график некорректен — возвращает 70.0 (безопасный fallback).
    """
    try:
        if not hasattr(main_window, '_graph_supply_var') or main_window._graph_supply_var is None:
            # Строка ещё не создана — читаем из app
            graph = main_window.app.temperature_graph
            return PowerRecalculator.delta_t_from(
                graph.get("supply", 95),
                graph.get("return", 85),
                graph.get("room", 20),
            )

        supply = int(main_window._graph_supply_var.get() or 95)
        ret = int(main_window._graph_return_var.get() or 85)
        room = int(main_window._graph_room_var.get() or 20)
        delta_t = PowerRecalculator.delta_t_from(supply, ret, room)
        return delta_t if delta_t > 0 else 70.0
    except (ValueError, AttributeError):
        return 70.0