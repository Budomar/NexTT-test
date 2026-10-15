"""
Матрица радиаторов главного окна NexTT.

Вынесено из MainWindow:
    • _build_matrix                             — построение матрицы
    • _create_matrix_cell_adaptive_with_font    — создание ячейки
    • _on_cell_changed                          — обработка изменения количества
    • _highlight_headers                        — подсветка заголовков при наведении
    • _clear_highlights                         — снятие подсветки
    • _navigate_matrix                          — навигация стрелками
"""

import re
import tkinter as tk
from tkinter import ttk

from nextt.logger import get_logger

logger = get_logger(__name__)


# ======================================================================
# Построение матрицы
# ======================================================================

def build_matrix(main_window, connection: str, rad_type: str) -> None:
    """Строит матрицу радиаторов с адаптивной шириной."""
    # Очищаем старую матрицу
    for w in main_window._matrix_frame.winfo_children():
        w.destroy()
    main_window._cell_entries.clear()
    main_window._col_headers.clear()
    main_window._row_headers.clear()

    main_window._current_connection = connection
    main_window._current_type = rad_type

    # Получаем данные
    data = main_window.app.filter_radiators(connection, rad_type)
    if data.empty:
        ttk.Label(
            main_window._matrix_frame,
            text=f"Нет данных для {connection} тип {rad_type}",
            font=("Segoe UI", 12),
        ).pack(pady=50)
        return

    lengths = main_window.LENGTHS
    heights = main_window.HEIGHTS

    # --- Адаптивный расчёт размеров ---
    main_window.root.update_idletasks()
    available_width = main_window._matrix_frame.winfo_width()
    if available_width < 100:
        available_width = main_window.root.winfo_screenwidth() - 50

    num_cols = len(lengths) + 1
    cell_width = max(40, min(80, available_width // num_cols))

    base_cell_height = 28
    cell_height = max(20, int(base_cell_height * main_window.app.font_manager.scale))

    default_font = main_window.app.font_manager.get_default_font()
    heading_font = main_window.app.font_manager.get_heading_font()

    row_header_width = max(40, cell_width)

    # Заголовки столбцов (длины)
    for j, length in enumerate(lengths):
        lbl = tk.Label(
            main_window._matrix_frame,
            text=str(length),
            font=heading_font,
            relief="ridge",
            borderwidth=1,
            bg='#e8e8e8',
            fg='#000000',
            anchor="center",
            width=4,
        )
        lbl.grid(row=0, column=j + 1, sticky="nsew", padx=1, pady=1)
        main_window._col_headers[j + 1] = lbl

    # Строки матрицы
    for i, height in enumerate(heights):
        lbl = tk.Label(
            main_window._matrix_frame,
            text=str(height),
            font=heading_font,
            relief="ridge",
            borderwidth=1,
            bg='#e8e8e8',
            fg='#000000',
            anchor="center",
            width=4,
        )
        lbl.grid(row=i + 1, column=0, sticky="nsew", padx=1, pady=1)
        main_window._row_headers[i + 1] = lbl

        for j, length in enumerate(lengths):
            create_matrix_cell_adaptive_with_font(
                main_window, data, length, height, i + 1, j + 1, default_font
            )

    # Настройка размеров колонок и строк
    for col in range(len(lengths) + 1):
        if col == 0:
            main_window._matrix_frame.columnconfigure(
                col, minsize=row_header_width, weight=0
            )
        else:
            main_window._matrix_frame.columnconfigure(
                col, minsize=cell_width, weight=1
            )
    for row in range(len(heights) + 1):
        main_window._matrix_frame.rowconfigure(row, minsize=cell_height)

    if not main_window._first_build_done:
        main_window._first_build_done = True


# ======================================================================
# Создание ячейки матрицы
# ======================================================================

def create_matrix_cell_adaptive_with_font(main_window, data, length: int,
                                          height: int, row: int, col: int,
                                          font) -> None:
    """Создаёт ячейку матрицы с заданным шрифтом."""
    pattern = f"/{height}/{length}"
    match = data[data['Наименование'].str.contains(pattern, na=False, regex=False)]

    if not match.empty:
        product = match.iloc[0]
        art = str(product['Артикул']).strip()
        conn = product.get('Connection', '')
        rt = product.get('RadiatorType', '')
        key = (f"{conn} {rt}", art) if conn and rt else ("", art)
        current_value = main_window.app.entry_values.get(key, "")
        has_any = any(v for v in main_window.app.entry_values.values() if v)

        entry = tk.Entry(
            main_window._matrix_frame,
            width=5,
            justify="center",
            bg='#e6f3ff' if has_any else 'white',
            relief='solid',
            borderwidth=1,
            font=font,
            validate='key',
            validatecommand=(
                main_window.root.register(main_window._validate_input), '%P'
            ),
        )
        entry.insert(0, current_value)

        entry.bind("<FocusOut>",
                   lambda e, k=key, ent=entry: on_cell_changed(main_window, k, ent))
        entry.bind("<Return>",
                   lambda e, k=key, ent=entry: on_cell_changed(main_window, k, ent))
        entry.bind("<Enter>",
                   lambda e, r=row, c=col: highlight_headers(main_window, r, c))
        entry.bind("<Leave>",
                   lambda e: clear_highlights(main_window))
        entry.bind("<FocusIn>",
                   lambda e, r=row, c=col: highlight_headers(main_window, r, c), add="+")
        entry.bind("<FocusOut>",
                   lambda e: clear_highlights(main_window), add="+")
        entry.bind("<Up>",
                   lambda e, r=row, c=col: navigate_matrix(main_window, e, r, c, "up"))
        entry.bind("<Down>",
                   lambda e, r=row, c=col: navigate_matrix(main_window, e, r, c, "down"))
        entry.bind("<Left>",
                   lambda e, r=row, c=col: navigate_matrix(main_window, e, r, c, "left"))
        entry.bind("<Right>",
                   lambda e, r=row, c=col: navigate_matrix(main_window, e, r, c, "right"))
        entry.bind("<Enter>",
                   lambda e, p=product: on_show_tooltip(main_window, e, p), add="+")
        entry.bind("<Leave>",
                   lambda e: on_hide_tooltip(main_window), add="+")

        main_window._cell_entries[(row, col)] = entry
        entry.grid(row=row, column=col, sticky="nsew", padx=1, pady=1)
    else:
        entry = tk.Entry(
            main_window._matrix_frame,
            width=5,
            justify="center",
            bg='#f0f0f0',
            relief='solid',
            borderwidth=1,
            state='disabled',
            font=font,
        )
        entry.grid(row=row, column=col, sticky="nsew", padx=1, pady=1)


# ======================================================================
# Обёртки для tooltip (делегируют в main_window_matrix_tooltip)
# ======================================================================

def on_show_tooltip(main_window, event, product) -> None:
    """Обёртка вызова show_cell_tooltip."""
    from nextt.ui.main_window_matrix_tooltip import show_cell_tooltip
    show_cell_tooltip(main_window, event, product)


def on_hide_tooltip(main_window, event=None) -> None:
    """Обёртка вызова hide_cell_tooltip."""
    from nextt.ui.main_window_matrix_tooltip import hide_cell_tooltip
    hide_cell_tooltip(main_window, event)


# ======================================================================
# Обработка изменения количества
# ======================================================================

def on_cell_changed(main_window, key: tuple, entry: tk.Entry) -> None:
    """Обработчик изменения количества в ячейке."""
    value = entry.get().strip()
    if value:
        main_window.app.entry_values[key] = value
    else:
        main_window.app.entry_values.pop(key, None)

    has_any = any(v for v in main_window.app.entry_values.values() if v)
    color = '#e6f3ff' if has_any else 'white'

    for ent in main_window._cell_entries.values():
        try:
            if ent.winfo_exists() and ent['state'] != 'disabled':
                ent.config(bg=color)
        except tk.TclError:
            pass


# ======================================================================
# Подсветка заголовков
# ======================================================================

def highlight_headers(main_window, row: int, col: int) -> None:
    """Подсвечивает заголовки строки и столбца."""
    if col in main_window._col_headers:
        main_window._col_headers[col].config(bg='#c8c8c8')
    if row in main_window._row_headers:
        main_window._row_headers[row].config(bg='#c8c8c8')


def clear_highlights(main_window) -> None:
    """Снимает подсветку со всех заголовков."""
    for h in main_window._col_headers.values():
        h.config(bg='#e8e8e8')
    for h in main_window._row_headers.values():
        h.config(bg='#e8e8e8')


# ======================================================================
# Навигация стрелками
# ======================================================================

def navigate_matrix(main_window, event, current_row: int, current_col: int,
                    direction: str) -> str:
    """
    Навигация по матрице с помощью стрелок клавиатуры.
    С подсветкой заголовков для новой ячейки.
    """
    children = main_window._matrix_frame.grid_slaves()

    if direction == "up":
        target_row = current_row - 1
        target_col = current_col
    elif direction == "down":
        target_row = current_row + 1
        target_col = current_col
    elif direction == "left":
        target_row = current_row
        target_col = current_col - 1
    elif direction == "right":
        target_row = current_row
        target_col = current_col + 1
    else:
        return "break"

    target_entry = None
    for child in children:
        info = child.grid_info()
        if info:
            r = info.get('row', -1)
            c = info.get('column', -1)
            if r == target_row and c == target_col and isinstance(child, tk.Entry):
                if str(child['state']) != 'disabled':
                    target_entry = child
                    break

    if target_entry:
        target_entry.focus_set()
        target_entry.select_range(0, tk.END)
        highlight_headers(main_window, target_row, target_col)

    return "break"