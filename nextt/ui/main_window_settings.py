"""
Панель настроек главного окна NexTT.

Вынесено из MainWindow:
    • _create_settings_row                  — вся строка настроек
    • _update_type_buttons_visibility       — показ/скрытие кнопок типов
    • _update_type_block_highlight          — подсветка активного типа
    • _update_connection_block_highlight    — подсветка активного блока
    • _set_frame_bg_recursive               — рекурсивная установка фона
    • _on_connection_changed                — смена подключения
    • _on_type_changed                      — смена типа

Строка содержит:
    • Заголовок «Classic:» + блок из 3 радиокнопок подключения
    • Заголовок «Hygiene:» + блок из 3 радиокнопок подключения
    • Заголовок «Тип радиатора:» + блок из 7 радиокнопок типов
    • Чекбокс «Подсказки»
"""

import tkinter as tk
from tkinter import ttk
import tkinter.font as tkfont

from nextt.events import bus, Events
from nextt.logger import get_logger

logger = get_logger(__name__)


# ======================================================================
# Построение строки настроек
# ======================================================================

def create_settings_row(parent: ttk.Frame, main_window) -> None:
    """
    Строка настроек: подключение + тип + чекбокс (всё в одной строке).

    Args:
        parent: родительский ttk.Frame (main_frame из MainWindow).
        main_window: экземпляр MainWindow.
    """
    app = main_window.app
    font_manager = app.font_manager

    settings_frame = ttk.Frame(parent)
    settings_frame.pack(fill="x", padx=5, pady=5)

    top_row = ttk.Frame(settings_frame)
    top_row.pack(fill="x")

    # Получаем масштабированные шрифты
    default_font = font_manager.get_default_font()
    bold_font = font_manager.get_bold_font()

    # ================================================================
    # РАСЧЁТ ШИРИНЫ НА ОСНОВЕ МАСШТАБА
    # ================================================================
    font_obj = tkfont.Font(font=default_font)

    # Ширина для подписей
    label_width = max(
        font_obj.measure("Classic:"),
        font_obj.measure("Hygiene:"),
        font_obj.measure("Тип радиатора:"),
    ) + 10

    # Ширина для каждой радиокнопки подключения
    conn_first_lines = ["VK-нижнее", "VK-нижнее", "K-боковое", "HV нижнее", "HV нижнее", "H-боковое"]
    conn_second_lines = ["правое", "левое", "", "правое", "левое", ""]
    max_conn_line = max(
        max(font_obj.measure(line) for line in conn_first_lines if line),
        max(font_obj.measure(line) for line in conn_second_lines if line),
    )
    conn_btn_width = max_conn_line + 40

    # Ширина для каждой радиокнопки типа
    type_texts = ["10", "11", "20", "21", "22", "30", "33"]
    type_btn_width = max(font_obj.measure(text) for text in type_texts) + 25

    # Ширина для чекбокса
    checkbox_text = "Подсказки"
    checkbox_width = font_obj.measure(checkbox_text) + 35

    # ================================================================
    # НАСТРОЙКА 18 КОЛОНОК
    # ================================================================
    # Колонки:
    # 0 - Classic:
    # 1-3 - рамка Classic
    # 4 - Hygiene:
    # 5-7 - рамка Hygiene
    # 8 - Тип радиатора:
    # 9-15 - рамка типов
    # 16 - растягиваемый промежуток
    # 17 - чекбокс

    for col in range(18):
        top_row.columnconfigure(col, weight=0)

    top_row.columnconfigure(16, weight=1)
    top_row.columnconfigure(17, weight=0, minsize=checkbox_width)

    # ================================================================
    # ПОДПИСЬ «Classic:» (колонка 0)
    # ================================================================
    ttk.Label(
        top_row,
        text="Classic:",
        font=bold_font,
        foreground='#000000',
    ).grid(row=0, column=0, padx=(0, 5), pady=5, sticky="ns")

    # ================================================================
    # БЛОК 1: КЛАССИЧЕСКИЕ РАДИАТОРЫ (VK-правое, VK-левое, K-боковое)
    # ================================================================
    classic_frame = tk.Frame(top_row, relief="solid", borderwidth=1, bg='#dedede')
    classic_frame.grid(row=0, column=1, columnspan=3, sticky="nsew", padx=2, pady=2)
    classic_frame.grid_rowconfigure(0, weight=1)

    main_window._classic_frame = classic_frame

    classic_connections = [
        ("VK-правое", "VK-нижнее\n   правое"),
        ("VK-левое", "VK-нижнее\n   левое"),
        ("K-боковое", "K-боковое"),
    ]

    main_window._conn_var = tk.StringVar(value="VK-правое")
    main_window._connection_radio_buttons.clear()
    main_window._classic_radio_buttons = []

    for col, (value, text) in enumerate(classic_connections):
        cell_frame = tk.Frame(classic_frame, bg='#dedede')
        cell_frame.grid(row=0, column=col, sticky="nsew", padx=2, pady=2)
        cell_frame.grid_rowconfigure(0, weight=1)
        cell_frame.grid_columnconfigure(0, weight=1)
        classic_frame.columnconfigure(col, weight=1)

        rb = ttk.Radiobutton(
            cell_frame,
            text=text,
            variable=main_window._conn_var,
            value=value,
            style="TRadiobutton",
            command=lambda: on_connection_changed(main_window),
        )
        rb.grid(row=0, column=0, sticky="nsew")
        main_window._connection_radio_buttons.append(rb)
        main_window._classic_radio_buttons.append(rb)

    # ================================================================
    # ПОДПИСЬ «Hygiene:» (колонка 4)
    # ================================================================
    ttk.Label(
        top_row,
        text="Hygiene:",
        font=bold_font,
        foreground='#008000',
    ).grid(row=0, column=4, padx=(10, 5), pady=5, sticky="ns")

    # ================================================================
    # БЛОК 2: ГИГИЕНИЧЕСКИЕ РАДИАТОРЫ (HV-правое, HV-левое, H-боковое)
    # ================================================================
    hygiene_frame = tk.Frame(top_row, relief="solid", borderwidth=1, bg='#dedede')
    hygiene_frame.grid(row=0, column=5, columnspan=3, sticky="nsew", padx=2, pady=2)
    hygiene_frame.grid_rowconfigure(0, weight=1)

    main_window._hygiene_frame = hygiene_frame

    hygiene_connections = [
        ("HV-правое", "HV нижнее\n   правое"),
        ("HV-левое", "HV нижнее\n   левое"),
        ("H-боковое", "H-боковое"),
    ]

    main_window._hygiene_radio_buttons = []

    for col, (value, text) in enumerate(hygiene_connections):
        cell_frame = tk.Frame(hygiene_frame, bg='#dedede')
        cell_frame.grid(row=0, column=col, sticky="nsew", padx=2, pady=2)
        cell_frame.grid_rowconfigure(0, weight=1)
        cell_frame.grid_columnconfigure(0, weight=1)
        hygiene_frame.columnconfigure(col, weight=1)

        rb = ttk.Radiobutton(
            cell_frame,
            text=text,
            variable=main_window._conn_var,
            value=value,
            style="Green.TRadiobutton",
            command=lambda: on_connection_changed(main_window),
        )
        rb.grid(row=0, column=0, sticky="nsew")
        main_window._connection_radio_buttons.append(rb)
        main_window._hygiene_radio_buttons.append(rb)

    # ================================================================
    # ЗАГОЛОВОК «Тип радиатора:» (колонка 8)
    # ================================================================
    ttk.Label(
        top_row, text="Тип радиатора:", font=default_font
    ).grid(row=0, column=8, padx=(20, 5), pady=5, sticky="ns")

    # ================================================================
    # БЛОК 3: ТИПЫ РАДИАТОРОВ (10, 11, 20, 21, 22, 30, 33)
    # ================================================================
    type_frame = tk.Frame(top_row, relief="solid", borderwidth=1, bg='#dedede')
    type_frame.grid(row=0, column=9, columnspan=7, sticky="nsew", padx=2, pady=2)
    type_frame.grid_rowconfigure(0, weight=1)

    main_window._type_var = tk.StringVar(value="10")
    main_window._type_radio_buttons.clear()
    main_window._type_cell_frames = {}

    type_cols = {
        "10": 0,
        "11": 1,
        "20": 2,
        "21": 3,
        "22": 4,
        "30": 5,
        "33": 6,
    }

    for rt, col in type_cols.items():
        cell_frame = tk.Frame(type_frame, bg='#dedede')
        cell_frame.grid(row=0, column=col, sticky="nsew", padx=2, pady=2)
        cell_frame.grid_rowconfigure(0, weight=1)
        cell_frame.grid_columnconfigure(0, weight=1)
        type_frame.columnconfigure(col, weight=1)

        rb = ttk.Radiobutton(
            cell_frame,
            text=rt,
            variable=main_window._type_var,
            value=rt,
            style="Type.TRadiobutton",
            command=lambda: on_type_changed(main_window),
        )
        rb.grid(row=0, column=0, sticky="nsew")
        main_window._type_radio_buttons[rt] = rb
        main_window._type_cell_frames[rt] = cell_frame

    # ================================================================
    # Чекбокс «Подсказки» (колонка 17)
    # ================================================================
    cell_frame = tk.Frame(top_row, bg='#dedede')
    cell_frame.grid(row=0, column=17, sticky="nsew", padx=(5, 5), pady=2)
    cell_frame.grid_rowconfigure(0, weight=1)
    cell_frame.grid_columnconfigure(0, weight=1)

    cb_frame = tk.Frame(cell_frame, relief="solid", borderwidth=1, bg='#dedede')
    cb_frame.grid(row=0, column=0, sticky="e")
    cb_frame.grid_rowconfigure(0, weight=1)
    cb_frame.grid_columnconfigure(0, weight=1)

    cb_inner = tk.Frame(cb_frame, bg='#dedede')
    cb_inner.grid(row=0, column=0, sticky="nsew")
    cb_inner.grid_rowconfigure(0, weight=1)
    cb_inner.grid_columnconfigure(0, weight=1)

    ttk.Checkbutton(
        cb_inner,
        text="Подсказки",
        variable=main_window.show_tooltips_var,
    ).grid(row=0, column=0, padx=8, pady=5, sticky="nsew")

    main_window._checkbox_frame = cb_frame

    # ================================================================
    # ПЕРВИЧНАЯ ПОДСВЕТКА АКТИВНЫХ БЛОКОВ
    # ================================================================
    update_type_buttons_visibility(main_window)
    update_connection_block_highlight(main_window)


# ======================================================================
# Обновление видимости кнопок типов
# ======================================================================

def update_type_buttons_visibility(main_window) -> None:
    """Обновляет видимость кнопок типов в зависимости от подключения."""
    conn = main_window._conn_var.get()

    # Определяем, какие типы должны быть видны
    if conn == "VK-левое":
        visible_types = ["10", "11", "30", "33"]
    elif conn == "HV-левое":
        visible_types = ["10", "30"]
    elif conn == "HV-правое":
        visible_types = ["10", "20", "30"]
    elif conn == "H-боковое":
        visible_types = ["10", "20", "30"]
    else:  # VK-правое, K-боковое
        visible_types = ["10", "11", "20", "21", "22", "30", "33"]

    # Показываем/скрываем кнопки (используем grid_remove, чтобы позиции не менялись)
    for rt, rb in main_window._type_radio_buttons.items():
        parent = rb.master
        if rt in visible_types:
            parent.grid()
        else:
            parent.grid_remove()

    # Восстанавливаем последний тип для этого подключения
    last_type = main_window._last_type_per_connection.get(conn, "10")
    if last_type in visible_types:
        main_window._type_var.set(last_type)
    else:
        main_window._type_var.set(visible_types[0])

    # Обновляем подсветку активного типа
    update_type_block_highlight(main_window)


# ======================================================================
# Подсветка активного типа радиатора
# ======================================================================

def update_type_block_highlight(main_window) -> None:
    """
    Подсвечивает ячейку активной радиокнопки типа радиатора.
    Активная ячейка получает фон #c8c8c8, остальные — #dedede.
    """
    if not hasattr(main_window, '_type_cell_frames') or not hasattr(main_window, '_type_radio_buttons'):
        return

    active_type = main_window._type_var.get()

    for rt, cell_frame in main_window._type_cell_frames.items():
        try:
            if not cell_frame.winfo_exists():
                continue
        except tk.TclError:
            continue

        rb = main_window._type_radio_buttons.get(rt)
        if rb is None:
            continue

        if rt == active_type:
            try:
                cell_frame.configure(bg='#c8c8c8')
            except tk.TclError:
                pass
            try:
                rb.configure(style="Active.Type.TRadiobutton")
            except tk.TclError:
                pass
        else:
            try:
                cell_frame.configure(bg='#dedede')
            except tk.TclError:
                pass
            try:
                rb.configure(style="Type.TRadiobutton")
            except tk.TclError:
                pass


# ======================================================================
# Подсветка активного блока (Classic / Hygiene)
# ======================================================================

def update_connection_block_highlight(main_window) -> None:
    """
    Подсвечивает блок (Classic или Hygiene), в котором активна радиокнопка.
    Активный блок получает фон #c8c8c8, неактивный — #dedede.
    """
    if not hasattr(main_window, '_classic_frame') or not hasattr(main_window, '_hygiene_frame'):
        return

    conn = main_window._conn_var.get()

    classic_connections = ("VK-правое", "VK-левое", "K-боковое")
    hygiene_connections = ("HV-правое", "HV-левое", "H-боковое")

    if conn in classic_connections:
        active_frame = main_window._classic_frame
        inactive_frame = main_window._hygiene_frame
        active_radios = main_window._classic_radio_buttons
        inactive_radios = main_window._hygiene_radio_buttons
        active_style = "Active.TRadiobutton"
    elif conn in hygiene_connections:
        active_frame = main_window._hygiene_frame
        inactive_frame = main_window._classic_frame
        active_radios = main_window._hygiene_radio_buttons
        inactive_radios = main_window._classic_radio_buttons
        active_style = "Active.Green.TRadiobutton"
    else:
        return

    # Меняем фон активного блока
    set_frame_bg_recursive(active_frame, '#c8c8c8')
    # Возвращаем фон неактивного блока
    set_frame_bg_recursive(inactive_frame, '#dedede')

    # Переключаем стиль радиокнопок в активном блоке
    for rb in active_radios:
        try:
            rb.configure(style=active_style)
        except tk.TclError:
            pass

    # Переключаем стиль радиокнопок в неактивном блоке на базовый
    if active_frame is main_window._classic_frame:
        for rb in inactive_radios:
            try:
                rb.configure(style="Green.TRadiobutton")
            except tk.TclError:
                pass
    else:
        for rb in inactive_radios:
            try:
                rb.configure(style="TRadiobutton")
            except tk.TclError:
                pass


def set_frame_bg_recursive(widget, color: str) -> None:
    """
    Рекурсивно устанавливает фон color у всех tk.Frame внутри widget,
    а также у самого widget. Виджеты ttk и tk.Entry не трогает.
    """
    try:
        if not widget.winfo_exists():
            return
    except (tk.TclError, AttributeError):
        return

    if isinstance(widget, tk.Frame):
        try:
            widget.configure(bg=color)
        except tk.TclError:
            pass

    try:
        for child in widget.winfo_children():
            set_frame_bg_recursive(child, color)
    except (tk.TclError, AttributeError):
        pass


# ======================================================================
# Обработчики событий
# ======================================================================

def on_connection_changed(main_window) -> None:
    """Обработчик смены подключения."""
    conn = main_window._conn_var.get()
    update_type_buttons_visibility(main_window)
    update_connection_block_highlight(main_window)
    main_window._build_matrix(conn, main_window._type_var.get())
    bus.emit(Events.CONNECTION_CHANGED, connection=conn)


def on_type_changed(main_window) -> None:
    """Обработчик смены типа — запоминает выбор."""
    conn = main_window._conn_var.get()
    rt = main_window._type_var.get()
    main_window._last_type_per_connection[conn] = rt
    update_type_block_highlight(main_window)
    main_window._build_matrix(conn, rt)
    bus.emit(Events.TYPE_CHANGED, rad_type=rt)