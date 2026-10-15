"""
Верхнее меню главного окна NexTT.

Вынесено из MainWindow: панель с кнопками
    • «Создать спецификацию»
    • «Загрузить данные»
    • «Вставить из буфера» (экспериментальная)
    • «Замена секционных»
    • «Информация» (выпадающее меню)
    • «Проверить обновление»
"""

from tkinter import ttk
import tkinter as tk

from nextt.logger import get_logger
from nextt.ui import main_window_info

logger = get_logger(__name__)


def create_top_menu(parent: ttk.Frame, main_window) -> None:
    """
    Создаёт верхнюю панель с кнопками.

    Args:
        parent: родительский ttk.Frame (main_frame из MainWindow)
        main_window: экземпляр MainWindow — нужен для привязки колбэков
                     и доступа к app (для информационных окон).
    """
    app = main_window.app

    top_panel = ttk.Frame(parent)
    top_panel.pack(fill="x", pady=(0, 10))

    menu_frame = ttk.Frame(top_panel)
    menu_frame.pack(fill="x", expand=True)

    # ==================================================================
    # СОЗДАЁМ КНОПКИ (но не размещаем сразу — сначала соберём список)
    # ==================================================================

    btn_create_spec = ttk.Button(
        menu_frame,
        text="Создать спецификацию",
        command=main_window._on_create_spec,
    )

    btn_load_data = ttk.Button(
        menu_frame,
        text="Загрузить данные",
        command=main_window._on_load_data,
    )

    # ==================================================================
    # ЭКСПЕРИМЕНТАЛЬНАЯ КНОПКА (условно)
    # ==================================================================
    experimental_btn = None
    try:
        from nextt.experimental.paste_handler import EXPERIMENTAL_ENABLED
        if EXPERIMENTAL_ENABLED:
            experimental_btn = ttk.Button(
                menu_frame,
                text="Вставить из буфера",
                command=main_window._on_paste_experimental,
            )
    except ImportError:
        pass
    except Exception:
        pass

    # ==================================================================
    # КНОПКА «ЗАМЕНА СЕКЦИОННЫХ» (новая)
    # ==================================================================
    btn_section_to_panel = ttk.Button(
        menu_frame,
        text="Замена секционных",
        command=main_window._on_section_to_panel,
    )

    # ==================================================================
    # КНОПКА «ИНФОРМАЦИЯ» (Menubutton с выпадающим меню)
    # ==================================================================
    info_btn = ttk.Menubutton(menu_frame, text="Информация")
    info_menu = tk.Menu(info_btn, tearoff=0)

    info_menu.add_command(
        label="Лицензионное соглашение",
        command=lambda: main_window_info.on_license(app),
    )
    info_menu.add_command(
        label="Инструкция по использованию",
        command=lambda: main_window_info.on_instruction(app),
    )
    info_menu.add_command(
        label="Методика пересчёта мощностей",
        command=lambda: main_window_info.on_power_method(app),
    )
    info_menu.add_separator()
    info_menu.add_command(
        label="Каталог оборудования",
        command=lambda: main_window_info.on_catalog(app),
    )
    info_menu.add_command(
        label="BIM-модели радиаторов",
        command=lambda: main_window_info.on_bim_models(app),
    )
    info_menu.add_separator()
    info_menu.add_command(
        label="Паспорт на радиатор",
        command=lambda: main_window_info.on_passport(app),
    )
    info_menu.add_command(
        label="Сертификат соответствия",
        command=lambda: main_window_info.on_certificate(app),
    )
    info_menu.add_command(
        label="Гигиенический сертификат",
        command=lambda: main_window_info.on_hygienic_certificate(app),
    )
    info_menu.add_command(
        label="Формуляр для регистрации проектов",
        command=lambda: main_window_info.on_formulyar(app),
    )
    info_btn["menu"] = info_menu

    # ==================================================================
    # КНОПКА «ПРОВЕРИТЬ ОБНОВЛЕНИЕ»
    # ==================================================================
    btn_check_update = ttk.Button(
        menu_frame,
        text="Проверить обновление",
        command=lambda: main_window_info.on_check_update(app),
    )

    # ==================================================================
    # РАЗМЕЩАЕМ КНОПКИ В GRID
    # ==================================================================
    visible_buttons = []
    visible_buttons.append(btn_create_spec)
    visible_buttons.append(btn_load_data)

    if experimental_btn is not None:
        visible_buttons.append(experimental_btn)

    # НОВОЕ: кнопка «Замена секционных» — левее «Информация»
    visible_buttons.append(btn_section_to_panel)

    visible_buttons.append(info_btn)
    visible_buttons.append(btn_check_update)

    for col, btn in enumerate(visible_buttons):
        btn.grid(row=0, column=col, sticky="ew", padx=5)
        menu_frame.grid_columnconfigure(col, weight=1)

    # На случай, если раньше было больше колонок — очищаем их
    for col in range(len(visible_buttons), 10):
        try:
            menu_frame.grid_columnconfigure(col, weight=0)
        except Exception:
            pass