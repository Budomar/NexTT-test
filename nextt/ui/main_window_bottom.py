"""
Нижняя панель главного окна NexTT.

Вынесено из MainWindow: строка с кнопками и блоками
    • кнопка «Предпросмотр»
    • сегментированный контрол масштаба шрифта (+, −, значение)
    • блок «Кронштейны и скидки»
    • логотип PBO (или текст)
    • кнопка «Сброс»

Всё создаётся относительно переданного `main_window` — потому что
нужны доступ к app (font_manager, root) и к переменным MainWindow
(bracket_var, radiator_discount_var, bracket_discount_var, font_scale_var).
"""

import os
import tkinter as tk
from tkinter import ttk

from nextt.config import get_resource_path
from nextt.logger import get_logger

logger = get_logger(__name__)


def create_bottom_panel(parent: ttk.Frame, main_window) -> None:
    """
    Создаёт нижнюю панель.

    Args:
        parent: родительский ttk.Frame (main_frame из MainWindow).
        main_window: экземпляр MainWindow.
    """
    app = main_window.app
    font_manager = app.font_manager

    bottom = ttk.Frame(parent)
    bottom.pack(fill="x", pady=(5, 0))

    default_font = font_manager.get_default_font()

    # Отступ слева
    ttk.Frame(bottom, width=50).pack(side="left")

    # ------------------------------------------------------------------
    # Кнопка «Предпросмотр»
    # ------------------------------------------------------------------
    ttk.Button(
        bottom,
        text="Предпросмотр",
        command=main_window._on_preview,
        width=15,
    ).pack(side="left", padx=5)

    # ------------------------------------------------------------------
    # Сегментированный контрол масштаба
    # ------------------------------------------------------------------
    _create_font_scale_control(bottom, main_window, default_font)

    ttk.Frame(bottom).pack(side="left", expand=True, fill="x")

    # ------------------------------------------------------------------
    # Блок «Кронштейны и скидки»
    # ------------------------------------------------------------------
    _create_bracket_discount_row(bottom, main_window, default_font)

    ttk.Frame(bottom).pack(side="left", expand=True, fill="x")

    # ------------------------------------------------------------------
    # Правый блок: логотип + кнопка «Сброс»
    # ------------------------------------------------------------------
    _create_right_block(bottom, main_window, default_font)


# ======================================================================
# Сегментированный контрол масштаба шрифта
# ======================================================================

def _create_font_scale_control(parent: tk.Widget, main_window, default_font) -> None:
    """Создаёт сегментированный контрол масштаба шрифта."""
    app = main_window.app

    scale_container = ttk.Frame(parent)
    scale_container.pack(side="left", padx=5)

    # Метка «Масштаб:» — сохраняем ссылку, чтобы обновлять шрифт
    main_window._scale_label = ttk.Label(
        scale_container, text="Масштаб:", font=default_font
    )
    main_window._scale_label.pack(side="left", padx=(6, 6), pady=3)

    # Единый фрейм с рамкой — визуально объединяет кнопки и поле
    segment = tk.Frame(
        scale_container,
        relief="solid",
        borderwidth=1,
        bg='#263168',
    )
    segment.pack(side="left", pady=3)

    # Кнопка «−»
    btn_minus = tk.Button(
        segment,
        text="−",
        width=2,
        font=default_font,
        bg='#263168',
        fg='white',
        activebackground='#7E1A2F',
        activeforeground='white',
        relief='flat',
        borderwidth=0,
        highlightthickness=0,
        cursor='hand2',
        command=main_window._decrease_font_scale,
    )
    btn_minus.pack(side="left")

    # Поле со значением
    main_window.font_scale_var = tk.StringVar(
        value=f"{app.font_manager.scale:.2f}"
    )

    scale_value_label = tk.Label(
        segment,
        textvariable=main_window.font_scale_var,
        width=5,
        bg='white',
        fg='#263168',
        font=default_font,
        anchor="center",
        relief='flat',
        borderwidth=0,
        highlightthickness=0,
    )
    scale_value_label.pack(side="left", padx=0, pady=0, ipady=2)

    # Кнопка «+»
    btn_plus = tk.Button(
        segment,
        text="+",
        width=2,
        font=default_font,
        bg='#263168',
        fg='white',
        activebackground='#7E1A2F',
        activeforeground='white',
        relief='flat',
        borderwidth=0,
        highlightthickness=0,
        cursor='hand2',
        command=main_window._increase_font_scale,
    )
    btn_plus.pack(side="left")


# ======================================================================
# Блок «Кронштейны и скидки»
# ======================================================================

def _create_bracket_discount_row(parent: tk.Widget, main_window, default_font) -> None:
    """Создаёт блок кронштейнов и скидок."""
    # Сохраняем ссылку на заголовок — нужна для обновления шрифтов
    main_window._bracket_title_label = ttk.Label(
        parent, text="Кронштейны и скидки:", font=default_font
    )
    main_window._bracket_title_label.pack(side="left", padx=(0, 5), pady=5)

    bracket_frame = tk.Frame(parent, relief="solid", borderwidth=1, bg='#dedede')
    bracket_frame.pack(side="left", padx=0, pady=0)

    # Варианты кронштейнов (сокращённые названия для UI)
    bracket_options = [
        ("Настенные", "Настенные кронштейны"),
        ("Напольные", "Напольные кронштейны"),
        ("Без", "Без кронштейнов"),
    ]

    for display_text, full_value in bracket_options:
        ttk.Radiobutton(
            bracket_frame,
            text=display_text,
            variable=main_window.bracket_var,
            value=full_value,
        ).pack(side="left", padx=5, pady=3)

    # Метка «Радиаторы, %:» + поле ввода
    main_window._radiator_discount_label = ttk.Label(
        bracket_frame, text="Радиаторы, %:", width=12, font=default_font
    )
    main_window._radiator_discount_label.pack(side="left", padx=(10, 0), pady=3)

    ttk.Entry(
        bracket_frame,
        textvariable=main_window.radiator_discount_var,
        width=5,
        validate="key",
        validatecommand=(
            main_window.root.register(
                lambda v: _validate_discount(v, main_window)
            ),
            '%P',
        ),
    ).pack(side="left", padx=2, pady=3)

    # Метка «Кронштейны, %:» + поле ввода
    main_window._bracket_discount_label = ttk.Label(
        bracket_frame, text="Кронштейны, %:", width=12, font=default_font
    )
    main_window._bracket_discount_label.pack(side="left", padx=(5, 0), pady=3)

    ttk.Entry(
        bracket_frame,
        textvariable=main_window.bracket_discount_var,
        width=5,
        validate="key",
        validatecommand=(
            main_window.root.register(
                lambda v: _validate_discount(v, main_window)
            ),
            '%P',
        ),
    ).pack(side="left", padx=2, pady=3)


def _validate_discount(value: str, main_window) -> bool:
    """Обёртка над main_window_utils.validate_number (для register)."""
    from nextt.ui.main_window_utils import validate_number
    return validate_number(value)


# ======================================================================
# Правый блок: логотип + кнопка «Сброс»
# ======================================================================

def _create_right_block(parent: tk.Widget, main_window, default_font) -> None:
    """Создаёт правый блок с логотипом и кнопкой «Сброс»."""
    right_container = ttk.Frame(parent)
    right_container.pack(side="right", fill="y")

    ttk.Frame(right_container, width=10).pack(side="right")

    # Логотип PBO3.png (или текст «PBO», если файла нет)
    try:
        logo_path = get_resource_path("PBO3.png")
        if os.path.exists(logo_path):
            main_window._logo_img = tk.PhotoImage(file=logo_path)
            tk.Label(
                right_container,
                image=main_window._logo_img,
                bg='#dedede',
                bd=0,
                padx=0,
                pady=0,
            ).pack(side="right")
        else:
            tk.Label(
                right_container,
                text="PBO",
                bg='#dedede',
                fg='#444141',
                font=default_font,
                bd=0,
                padx=8,
                pady=4,
            ).pack(side="right")
    except Exception:
        tk.Label(
            right_container,
            text="PBO",
            bg='#dedede',
            fg='#444141',
            font=default_font,
            bd=0,
            padx=8,
            pady=4,
        ).pack(side="right")

    # Кнопка «Сброс»
    ttk.Button(
        right_container,
        text="Сброс",
        command=main_window._on_reset,
        width=15,
    ).pack(side="right", padx=(5, 40))