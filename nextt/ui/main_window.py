"""
Главное окно приложения с матрицей радиаторов и панелью управления.
"""

import tkinter as tk
from tkinter import ttk, messagebox
import os
import re
from typing import Dict, Tuple, Optional, List
import tempfile
import subprocess
import platform
import webbrowser
import pandas as pd

from nextt.logger import get_logger
from nextt.events import bus, Events
from nextt.config import get_resource_path, config
from nextt.utils.dpi import get_cached_scale

logger = get_logger(__name__)


class MainWindow:
    """Главное окно приложения."""

    HEIGHTS = [300, 400, 500, 600, 900]
    LENGTHS = list(range(400, 3100, 100))

    def __init__(self, app):
        self.app = app
        self.root = app.root
        
        self.font_manager = app.font_manager
        
        # Кеш виджетов
        self._cell_entries: Dict[Tuple[int, int], tk.Entry] = {}
        self._col_headers: Dict[int, tk.Label] = {}
        self._row_headers: Dict[int, tk.Label] = {}

        # Радиокнопки подключения (для подсветки)
        self._connection_radio_buttons: List[ttk.Radiobutton] = []
        # Радиокнопки типов (ключ: значение типа)
        self._type_radio_buttons: Dict[str, ttk.Radiobutton] = {}

        # Подсказки с картинками
        self._vk_right_tooltip: Optional[tk.Toplevel] = None
        self._vk_left_tooltip: Optional[tk.Toplevel] = None
        self._k_side_tooltip: Optional[tk.Toplevel] = None

        # Запоминание последнего типа для каждого подключения
        self._last_type_per_connection: Dict[str, str] = {
            "VK-правое": "10",
            "VK-левое": "10",
            "K-боковое": "10",
        }

        # Переменные (всегда начинаются с значений по умолчанию)
        self.bracket_var = tk.StringVar(value="Настенные кронштейны")
        self.radiator_discount_var = tk.StringVar(value="0")
        self.bracket_discount_var = tk.StringVar(value="0")
        self.show_tooltips_var = tk.BooleanVar(value=False)

        # Таймер для мигания
        self._blink_after_id: Optional[str] = None

        # Ссылки на диалоги для закрытия при сбросе
        self._preview_dialog: Optional[object] = None
        self._meteor_selector: Optional[object] = None
        self._page_selector: Optional[object] = None

        # Флаг для предотвращения лишней перестройки матрицы при старте
        self._first_build_done = False

        # Настройка стилей
        self._setup_styles()

        # Строим интерфейс
        self._build_ui()
        
        # Сохраняем значения скидок и типа кронштейнов для восстановления
        self._saved_bracket_var = None
        self._saved_radiator_discount = None
        self._saved_bracket_discount = None
        self._saved_show_tooltips = None
        bus.subscribe(Events.DATA_LOADED, self._on_data_loaded)
        
        # ========== ПРОВЕРКА ОБНОВЛЕНИЙ ПРИ ЗАПУСКЕ ==========
        from nextt.utils.update_checker import check_updates_on_startup
        # Запускаем проверку обновлений через 1 секунду после старта
        self.root.after(1000, lambda: check_updates_on_startup(self.root, self.font_manager))
        # ===================================================

    # ==================================================================
    # СТИЛИ
    # ==================================================================
    def _save_ui_state(self) -> None:
        """Сохраняет текущее состояние UI перед перестройкой."""
        if hasattr(self, '_conn_var'):
            self._saved_connection = self._conn_var.get()
        if hasattr(self, '_type_var'):
            self._saved_type = self._type_var.get()
        if hasattr(self, 'bracket_var'):
            self._saved_bracket_var = self.bracket_var.get()
        if hasattr(self, 'radiator_discount_var'):
            self._saved_radiator_discount = self.radiator_discount_var.get()
        if hasattr(self, 'bracket_discount_var'):
            self._saved_bracket_discount = self.bracket_discount_var.get()
        if hasattr(self, 'show_tooltips_var'):
            self._saved_show_tooltips = self.show_tooltips_var.get()
        if hasattr(self, '_last_type_per_connection'):
            self._saved_last_type_per_connection = self._last_type_per_connection.copy()

    def _restore_ui_state(self) -> None:
        """Восстанавливает состояние UI после перестройки."""
        if hasattr(self, '_saved_connection') and hasattr(self, '_conn_var'):
            self._conn_var.set(self._saved_connection)
        if hasattr(self, '_saved_type') and hasattr(self, '_type_var'):
            self._type_var.set(self._saved_type)
        if hasattr(self, '_saved_bracket_var') and hasattr(self, 'bracket_var'):
            self.bracket_var.set(self._saved_bracket_var)
        if hasattr(self, '_saved_radiator_discount') and hasattr(self, 'radiator_discount_var'):
            self.radiator_discount_var.set(self._saved_radiator_discount)
        if hasattr(self, '_saved_bracket_discount') and hasattr(self, 'bracket_discount_var'):
            self.bracket_discount_var.set(self._saved_bracket_discount)
        if hasattr(self, '_saved_show_tooltips') and hasattr(self, 'show_tooltips_var'):
            self.show_tooltips_var.set(self._saved_show_tooltips)
        if hasattr(self, '_saved_last_type_per_connection') and hasattr(self, '_last_type_per_connection'):
            self._last_type_per_connection = self._saved_last_type_per_connection.copy()


    def _rebuild_all_ui(self) -> None:
        """
        Полностью перестраивает весь интерфейс с новыми шрифтами.
        Сохраняет и восстанавливает состояние.
        """
        # Сохраняем текущее состояние
        self._save_ui_state()
        
        # Очищаем все виджеты в корневом окне
        for widget in self.root.winfo_children():
            widget.destroy()
        
        # Пересоздаём все кеши
        self._cell_entries = {}
        self._col_headers = {}
        self._row_headers = {}
        self._connection_radio_buttons = []
        self._type_radio_buttons = {}
        self._blink_after_id = None
        
        # Пересоздаём стили (они применятся с новыми шрифтами)
        self._setup_styles()
        
        # Перестраиваем интерфейс
        self._build_ui()
        
        # Восстанавливаем состояние
        self._restore_ui_state()
        
        # Принудительно обновляем матрицу
        if hasattr(self, '_conn_var') and hasattr(self, '_type_var'):
            self._build_matrix(self._conn_var.get(), self._type_var.get())
        
        # Обновляем типы радиаторов
        self._update_type_buttons()

    def _setup_styles(self) -> None:
        """Настройка стилей ttk с учётом масштаба шрифта."""
        style = ttk.Style()
        style.theme_use('clam')

        style.configure('.', background="#dedede", foreground='#444141')
        style.configure('TFrame', background='#dedede')
        
        # Используем масштабируемые шрифты из FontManager
        default_font = self.app.font_manager.get_default_font()
        heading_font = self.app.font_manager.get_heading_font()
        
        style.configure('TLabel', background='#dedede', font=default_font)
        style.configure('TEntry', font=default_font, fieldbackground='white')
        style.configure('TRadiobutton', background='#dedede', font=default_font)
        style.configure('TCheckbutton', background='#dedede', font=default_font)

        # Подсвеченная радиокнопка (бордовая)
        style.configure('Highlighted.TRadiobutton',
                        background='#7E1A2F', foreground='white', font=default_font)

        # Кнопки
        style.configure('TButton', font=default_font,
                        background='#263168', foreground='white')
        style.map('TButton',
                  background=[('active', '#7E1A2F'), ('!disabled', '#263168')],
                  foreground=[('!disabled', 'white')])

        # Menubutton
        style.configure('TMenubutton', font=default_font,
                        background='#263168', foreground='white', arrowcolor='white')
        style.map('TMenubutton',
                  background=[('active', '#7E1A2F')],
                  foreground=[('!active', 'white')],
                  arrowcolor=[('!active', 'white')])

    # ==================================================================
    # ПОСТРОЕНИЕ ИНТЕРФЕЙСА
    # ==================================================================

    def _build_ui(self) -> None:
        """Создаёт интерфейс."""
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill="both", expand=True, padx=2, pady=2)

        # --- ВЕРХНЕЕ МЕНЮ ---
        self._create_top_menu(main_frame)

        # Загружаем подсказки с картинками ДО настроек (чтобы привязка событий работала)
        self._create_image_tooltips()

        # --- ПАНЕЛЬ НАСТРОЕК (подключение + тип + шрифт + чекбокс) ---
        self._create_settings_row(main_frame)

        # --- МАТРИЦА ---
        matrix_container = ttk.Frame(main_frame)
        matrix_container.pack(fill="both", expand=True, padx=2, pady=2)
        self._matrix_frame = ttk.Frame(matrix_container)
        self._matrix_frame.pack(fill="both", expand=True)

        # --- НИЖНЯЯ ПАНЕЛЬ ---
        self._create_bottom_panel(main_frame)

        # Показываем матрицу
        self._build_matrix("VK-правое", "10")

        # Принудительно обновляем геометрию чтобы матрица растянулась
        self.root.update_idletasks()

    # ==================================================================
    # ВЕРХНЕЕ МЕНЮ
    # ==================================================================

    def _create_top_menu(self, parent: ttk.Frame) -> None:
        """Верхняя панель с кнопками."""
        top_panel = ttk.Frame(parent)
        top_panel.pack(fill="x", pady=(0, 10))

        menu_frame = ttk.Frame(top_panel)
        menu_frame.pack(fill="x", expand=True)

        # ========== СОЗДАЁМ КНОПКИ ==========
        # Сначала создаём все кнопки, но не используем grid сразу
        btn_create_spec = ttk.Button(menu_frame, text="Создать спецификацию",
                                     command=self._on_create_spec)
        
        btn_load_data = ttk.Button(menu_frame, text="Загрузить данные",
                                   command=self._on_load_data)
        
        # ========== ЭКСПЕРИМЕНТАЛЬНАЯ КНОПКА (условно) ==========
        experimental_btn = None
        try:
            from nextt.experimental.paste_handler import EXPERIMENTAL_ENABLED
            if EXPERIMENTAL_ENABLED:
                experimental_btn = ttk.Button(menu_frame, text="Вставить из буфера",
                                              command=self._on_paste_experimental)
        except ImportError:
            pass
        except Exception:
            pass

        # Кнопка "Информация" (Menubutton)
        info_btn = ttk.Menubutton(menu_frame, text="Информация")
        info_menu = tk.Menu(info_btn, tearoff=0)
        info_menu.add_command(label="Лицензионное соглашение", command=self._on_license)
        info_menu.add_command(label="Инструкция по использованию", command=self._on_instruction)
        info_menu.add_separator()
        info_menu.add_command(label="Прайс-лист", command=self._on_price_list)
        info_menu.add_command(label="Каталог оборудования", command=self._on_catalog)
        info_menu.add_separator()
        info_menu.add_command(label="Паспорт на радиатор", command=self._on_passport)
        info_menu.add_command(label="Сертификат соответствия", command=self._on_certificate)
        info_menu.add_command(label="Гигиенический сертификат", command=lambda: webbrowser.open("https://b24.engpx.ru/~IPOCe"))  
        info_menu.add_separator()
        info_menu.add_command(label="BIM-модели радиаторов", command=lambda: webbrowser.open("https://b24.engpx.ru/~QQD8Z"))  
        info_btn["menu"] = info_menu

        btn_check_update = ttk.Button(menu_frame, text="Проверить обновление",
                                      command=self._on_check_update)

        # ========== РАЗМЕЩАЕМ КНОПКИ В GRID ==========
        # Собираем список всех видимых кнопок
        visible_buttons = []
        visible_buttons.append(btn_create_spec)
        visible_buttons.append(btn_load_data)
        
        if experimental_btn is not None:
            visible_buttons.append(experimental_btn)
        
        visible_buttons.append(info_btn)
        visible_buttons.append(btn_check_update)

        # Размещаем каждую кнопку в своей колонке
        for col, btn in enumerate(visible_buttons):
            btn.grid(row=0, column=col, sticky="ew", padx=5)
            # Настраиваем колонку с весом 1
            menu_frame.grid_columnconfigure(col, weight=1)

        # Если почему-то остались старые настройки колонок — очищаем их
        # (на случай, если раньше было больше колонок)
        for col in range(len(visible_buttons), 10):
            try:
                menu_frame.grid_columnconfigure(col, weight=0)
            except:
                pass
    # ==================================================================
    # ЭКСПЕРИМЕНТАЛЬНЫЙ ФУНКЦИОНАЛ (ВСТАВКА ИЗ БУФЕРА)
    # ==================================================================
    def _on_paste_experimental(self) -> None:
        """Обработчик экспериментальной кнопки «Вставить из буфера»."""
        try:
            from nextt.experimental.paste_handler import show_paste_dialog
            show_paste_dialog(self)
        except ImportError as e:
            messagebox.showwarning(
                "Функция недоступна",
                "Экспериментальный модуль не установлен.\n"
                "Для использования функции требуется установка дополнительных компонентов."
            )
            logger.warning(f"Экспериментальный модуль не загружен: {e}")
        except Exception as e:
            logger.error(f"Ошибка в экспериментальной функции: {e}")
            messagebox.showerror(
                "Ошибка",
                f"Произошла ошибка при вызове экспериментальной функции:\n{str(e)}\n\n"
                "Функция временно недоступна."
            )
    # ==================================================================
    # ПАНЕЛЬ НАСТРОЕК (с подсказками и миганием)
    # ==================================================================

    def _create_settings_row(self, parent: ttk.Frame) -> None:
        """Строка настроек: подключение, тип, шрифт, чекбокс."""
        settings_frame = ttk.Frame(parent)
        settings_frame.pack(fill="x", padx=5, pady=5)

        top_row = ttk.Frame(settings_frame)
        top_row.pack(fill="x")

        # Получаем масштабированные шрифты
        default_font = self.app.font_manager.get_default_font()
        small_font = self.app.font_manager.get_small_font()

        # --- Подключение ---
        ttk.Label(top_row, text="Вид подключения:", font=default_font).pack(
            side="left", padx=(0, 5), pady=5)

        conn_frame = tk.Frame(top_row, relief="solid", borderwidth=1, bg='#dedede')
        conn_frame.pack(side="left", padx=0, pady=0)

        self._conn_var = tk.StringVar(value="VK-правое")
        self._connection_radio_buttons.clear()

        connections = [
            ("VK-нижнее правое", "VK-правое"),
            ("VK-нижнее левое", "VK-левое"),
            ("K-боковое", "K-боковое"),
        ]
        for text, value in connections:
            rb = ttk.Radiobutton(
                conn_frame, text=text, variable=self._conn_var, value=value,
                command=self._on_connection_changed
            )
            rb.pack(side="left", padx=10, pady=5)
            self._connection_radio_buttons.append(rb)

            # # Привязываем подсказки с картинками(ЗАКОММЕНТИРОВАНО)
            # if value == "VK-правое" and self._vk_right_tooltip:
            #     rb.bind("<Enter>", lambda e, t=self._vk_right_tooltip, w=rb: self._show_image_tooltip(t, w))
            #     rb.bind("<Leave>", lambda e, t=self._vk_right_tooltip: self._hide_image_tooltip(t))
            # elif value == "VK-левое" and self._vk_left_tooltip:
            #     rb.bind("<Enter>", lambda e, t=self._vk_left_tooltip, w=rb: self._show_image_tooltip(t, w))
            #     rb.bind("<Leave>", lambda e, t=self._vk_left_tooltip: self._hide_image_tooltip(t))
            # elif value == "K-боковое" and self._k_side_tooltip:
            #     rb.bind("<Enter>", lambda e, t=self._k_side_tooltip, w=rb: self._show_image_tooltip(t, w))
            #     rb.bind("<Leave>", lambda e, t=self._k_side_tooltip: self._hide_image_tooltip(t))

        # --- Тип радиатора ---
        ttk.Label(top_row, text="Тип радиатора:", font=default_font).pack(
            side="left", padx=(20, 5), pady=5)

        self._type_frame_outer = tk.Frame(top_row, relief="solid", borderwidth=1, bg='#dedede')
        self._type_frame_outer.pack(side="left", padx=0, pady=0)

        self._type_var = tk.StringVar(value="10")
        self._type_buttons_frame = ttk.Frame(self._type_frame_outer)
        self._type_buttons_frame.pack(fill="x", padx=5, pady=5)
        self._update_type_buttons()

        # ========== КНОПКИ ШРИФТА (ФИКСИРОВАННЫЕ ЧЕРЕЗ place) ==========
        # Создаём контейнер, который будет служить "якорем" для абсолютного позиционирования
        font_anchor = ttk.Frame(top_row)
        font_anchor.pack(side="right", padx=(0, 10), pady=0)

        # Сам блок масштаба (без рамки)
        font_frame = tk.Frame(font_anchor, bg='#dedede')
        font_frame.pack()

        ttk.Label(font_frame, text="Масштаб:", font=default_font).pack(side="left", padx=(6, 3), pady=3)

        # Кнопка "-" (уменьшить) - синяя, как все остальные кнопки
        btn_minus = ttk.Button(
            font_frame,
            text="−",
            width=2,
            command=self._decrease_font_scale
        )
        btn_minus.pack(side="left", padx=1, pady=3)

        # Окошко с текущим значением масштаба
        self.font_scale_var = tk.StringVar(value=f"{self.app.font_manager.scale:.2f}")
        
        scale_label = tk.Label(
            font_frame,
            textvariable=self.font_scale_var,
            width=5,
            relief="solid",
            borderwidth=1,
            bg='white',
            font=default_font,
            anchor="center"
        )
        scale_label.pack(side="left", padx=1, pady=3)

        # Кнопка "+" (увеличить) - синяя, как все остальные кнопки
        btn_plus = ttk.Button(
            font_frame,
            text="+",
            width=2,
            command=self._increase_font_scale
        )
        btn_plus.pack(side="left", padx=1, pady=3)

        # --- Чекбокс ---
        cb_frame = tk.Frame(top_row, relief="solid", borderwidth=1, bg='#dedede')
        cb_frame.pack(side="right", padx=(0, 10), pady=0)

        ttk.Checkbutton(
            cb_frame,
            text="Показывать параметры и стоимость",
            variable=self.show_tooltips_var
        ).pack(side="right", padx=8, pady=5)

    def _create_image_tooltips(self) -> None:
        """Создаёт подсказки с картинками."""
        for attr, filename in [
            ('_vk_right_tooltip', "1.png"),
            ('_vk_left_tooltip', "2.png"),
            ('_k_side_tooltip', "3.png"),
        ]:
            try:
                path = get_resource_path(filename)
                if os.path.exists(path):
                    tooltip = tk.Toplevel(self.root)
                    tooltip.wm_overrideredirect(True)
                    tooltip.withdraw()
                    img = tk.PhotoImage(file=path)
                    label = ttk.Label(tooltip, image=img)
                    label.image = img
                    label.pack()
                    setattr(self, attr, tooltip)
                else:
                    setattr(self, attr, None)
            except Exception as e:
                logger.debug(f"Не удалось загрузить {filename}: {e}")
                setattr(self, attr, None)

    def _show_image_tooltip(self, tooltip: Optional[tk.Toplevel], widget: tk.Widget) -> None:
        """Показывает подсказку с картинкой."""
        if tooltip and tooltip.winfo_exists():
            x = widget.winfo_rootx() + widget.winfo_width() + 5
            y = widget.winfo_rooty() - 50
            tooltip.wm_geometry(f"+{x}+{y}")
            tooltip.deiconify()

    def _hide_image_tooltip(self, tooltip: Optional[tk.Toplevel]) -> None:
        """Скрывает подсказку."""
        if tooltip and tooltip.winfo_exists():
            tooltip.withdraw()

    # ==================================================================
    # УПРАВЛЕНИЕ ШРИФТОМ (НОВЫЕ МЕТОДЫ)
    # ==================================================================

    def _increase_font_scale(self) -> None:
        """Увеличивает масштаб шрифтов во всех окнах."""
        self.app.font_manager.increase()
        self._refresh_all_fonts()

    def _decrease_font_scale(self) -> None:
        """Уменьшает масштаб шрифтов во всех окнах."""
        self.app.font_manager.decrease()
        self._refresh_all_fonts()

    def _refresh_all_fonts(self) -> None:
        """
        Обновляет шрифты во всех окнах приложения.
        Вызывается после изменения масштаба.
        """
        # Обновляем значение в окошке (два знака после запятой)
        if hasattr(self, 'font_scale_var'):
            self.font_scale_var.set(f"{self.app.font_manager.scale:.2f}")
        
        # ========== ИСПРАВЛЕНИЕ: пересоздаём стили с новым масштабом ==========
        self._setup_styles()
        
        # Обновляем шрифты через FontManager
        self.app.font_manager.refresh_all_windows(self.root)

        # Обновляем шрифты в ячейках матрицы
        self._update_all_cells_fonts()

        # Обновляем шрифты в подсказке
        self._update_tooltip_fonts()

        # Перестраиваем матрицу, чтобы применить новые размеры ячеек
        self._build_matrix(self._conn_var.get(), self._type_var.get())

        # Отправляем событие об изменении масштаба
        bus.emit(Events.FONT_SCALE_CHANGED, scale=self.app.font_manager.scale)

    def _update_tooltip_fonts(self) -> None:
        """Обновляет шрифты в существующей подсказке при изменении масштаба."""
        if not hasattr(self, '_tooltip_window') or not self._tooltip_window:
            return
        
        if not self._tooltip_window.winfo_exists():
            return
        
        # Получаем актуальные шрифты
        default_font = self.font_manager.get_default_font()
        bold_font = self.font_manager.get_bold_font()
        italic_font = self.font_manager.get_font(9)
        
        # Обновляем шрифты у всех виджетов подсказки
        if hasattr(self, '_tip_name'):
            self._tip_name.config(font=bold_font)
        if hasattr(self, '_tip_art'):
            self._tip_art.config(font=default_font)
        if hasattr(self, '_tip_params'):
            self._tip_params.config(font=default_font)
        if hasattr(self, '_tip_price'):
            self._tip_price.config(font=bold_font)
        if hasattr(self, '_tip_bracket_info'):
            self._tip_bracket_info.config(font=italic_font)
        if hasattr(self, '_tip_bracket_lines'):
            for lbl in self._tip_bracket_lines:
                lbl.config(font=default_font)
        if hasattr(self, '_tip_total'):
            self._tip_total.config(font=bold_font)
    # ==================================================================
    # ТИПЫ РАДИАТОРОВ (с запоминанием и миганием)
    # ==================================================================

    def _update_type_buttons(self) -> None:
        """Обновляет радиокнопки типов."""
        for w in self._type_buttons_frame.winfo_children():
            w.destroy()
        self._type_radio_buttons.clear()

        conn = self._conn_var.get()
        if conn == "VK-левое":
            types = ["10", "11", "30", "33"]
        else:
            types = ["10", "11", "20", "21", "22", "30", "33"]

        # Восстанавливаем последний тип для этого подключения
        last_type = self._last_type_per_connection.get(conn, "10")
        if last_type in types:
            self._type_var.set(last_type)
        else:
            self._type_var.set(types[0])

        for rt in types:
            rb = ttk.Radiobutton(
                self._type_buttons_frame, text=rt, variable=self._type_var, value=rt,
                command=self._on_type_changed
            )
            rb.pack(side="left", padx=5, pady=0)
            self._type_radio_buttons[rt] = rb

    def _on_connection_changed(self) -> None:
        """Обработчик смены подключения."""
        self._update_type_buttons()
        self._build_matrix(self._conn_var.get(), self._type_var.get())
        # Запускаем мигающую подсветку для ОБЕИХ радиокнопок (подключение + тип)
        self._start_blinking_both()
        bus.emit(Events.CONNECTION_CHANGED, connection=self._conn_var.get())

    def _on_type_changed(self) -> None:
        """Обработчик смены типа — запоминает выбор."""
        conn = self._conn_var.get()
        rt = self._type_var.get()
        self._last_type_per_connection[conn] = rt
        self._build_matrix(conn, rt)
        # Запускаем мигающую подсветку для ОБЕИХ радиокнопок (подключение + тип)
        self._start_blinking_both()
        bus.emit(Events.TYPE_CHANGED, rad_type=rt)

    def _start_blinking_both(self) -> None:
        """Собирает активные радиокнопки подключения и типа и запускает единое мигание."""
        active_buttons = []

        # 1. Активная радиокнопка подключения
        active_conn = self._conn_var.get()
        for rb in self._connection_radio_buttons:
            try:
                if rb.winfo_exists() and rb.cget("value") == active_conn:
                    active_buttons.append(rb)
            except tk.TclError:
                pass

        # 2. Активная радиокнопка типа
        active_type = self._type_var.get()
        for rt, rb in self._type_radio_buttons.items():
            try:
                if rb.winfo_exists() and rt == active_type:
                    active_buttons.append(rb)
            except tk.TclError:
                pass

        # Запускаем мигание для всех собранных кнопок
        if active_buttons:
            self._start_blinking(active_buttons, 'Highlighted.TRadiobutton', 'TRadiobutton', 1200)
    
    # ==================================================================
    # МИГАЮЩАЯ ПОДСВЕТКА
    # ==================================================================

    def _start_blinking(self, widgets: List[ttk.Radiobutton],
                        on_style: str, off_style: str, duration_ms: int) -> None:
        """Мигает список виджетов, переключая стили."""
        # ========== ИСПРАВЛЕНИЕ: сначала сбрасываем стиль ВСЕХ радиокнопок ==========
        # Находим все радиокнопки подключения и типа и возвращаем им обычный стиль
        all_radio_buttons = []
        
        # Добавляем все кнопки подключения
        if hasattr(self, '_connection_radio_buttons'):
            for rb in self._connection_radio_buttons:
                try:
                    if rb.winfo_exists():
                        all_radio_buttons.append(rb)
                except tk.TclError:
                    pass
        
        # Добавляем все кнопки типа
        if hasattr(self, '_type_radio_buttons'):
            for rb in self._type_radio_buttons.values():
                try:
                    if rb.winfo_exists():
                        all_radio_buttons.append(rb)
                except tk.TclError:
                    pass
        
        # Сбрасываем стиль всех кнопок на обычный
        for rb in all_radio_buttons:
            try:
                if rb.winfo_exists():
                    rb.config(style=off_style)
            except tk.TclError:
                pass
        
        # ========== ОСНОВНАЯ ЛОГИКА МИГАНИЯ ==========
        blink_interval = 200  # миллисекунды между переключениями
        num_cycles = (duration_ms // blink_interval) // 2  # количество полных циклов вкл/выкл
        cycle_count = 0

        def blink_on():
            nonlocal cycle_count
            if cycle_count >= num_cycles:
                # Возвращаем обычный стиль всем кнопкам
                for w in widgets:
                    try:
                        if w.winfo_exists():
                            w.config(style=off_style)
                    except tk.TclError:
                        pass
                return

            # Включаем подсветку
            for w in widgets:
                try:
                    if w.winfo_exists():
                        w.config(style=on_style)
                except tk.TclError:
                    pass

            self._blink_after_id = self.root.after(blink_interval, blink_off)

        def blink_off():
            nonlocal cycle_count
            # Выключаем подсветку
            for w in widgets:
                try:
                    if w.winfo_exists():
                        w.config(style=off_style)
                except tk.TclError:
                    pass
            cycle_count += 1
            self._blink_after_id = self.root.after(blink_interval, blink_on)

        # Отменяем предыдущее мигание, если было
        if self._blink_after_id is not None:
            try:
                self.root.after_cancel(self._blink_after_id)
            except ValueError:
                pass
            self._blink_after_id = None

        # Запускаем новый цикл
        blink_on()

    # ==================================================================
    # МАТРИЦА
    # ==================================================================

    def _build_matrix(self, connection: str, rad_type: str) -> None:
        """Строит матрицу радиаторов с адаптивной шириной."""
        # Очищаем старую матрицу
        for w in self._matrix_frame.winfo_children():
            w.destroy()
        self._cell_entries.clear()
        self._col_headers.clear()
        self._row_headers.clear()

        self._current_connection = connection
        self._current_type = rad_type

        # Получаем данные
        data = self.app.filter_radiators(connection, rad_type)
        if data.empty:
            ttk.Label(
                self._matrix_frame,
                text=f"Нет данных для {connection} тип {rad_type}",
                font=("Segoe UI", 12)
            ).pack(pady=50)
            return

        lengths = self.LENGTHS
        heights = self.HEIGHTS

        # --- Адаптивный расчёт размеров ---
        self.root.update_idletasks()
        available_width = self._matrix_frame.winfo_width()
        if available_width < 100:
            available_width = self.root.winfo_screenwidth() - 50

        num_cols = len(lengths) + 1
        cell_width = max(40, min(80, available_width // num_cols))
        
        # ИСПРАВЛЕНИЕ: используем масштабированную высоту строки
        base_cell_height = 28
        cell_height = max(20, int(base_cell_height * self.app.font_manager.scale))

        # ИСПРАВЛЕНИЕ: используем масштабированные шрифты из FontManager
        default_font = self.app.font_manager.get_default_font()
        heading_font = self.app.font_manager.get_heading_font()

        row_header_width = max(40, cell_width)

        # Заголовки столбцов (длины)
        for j, length in enumerate(lengths):
            lbl = tk.Label(
                self._matrix_frame,
                text=str(length),
                font=heading_font,  # ИСПРАВЛЕНО: используем масштабированный шрифт
                relief="ridge",
                borderwidth=1,
                bg='#e8e8e8',
                fg='#000000',
                anchor="center",
                width=4,
            )
            lbl.grid(row=0, column=j + 1, sticky="nsew", padx=1, pady=1)
            self._col_headers[j + 1] = lbl

        # Строки матрицы
        for i, height in enumerate(heights):
            # Заголовок строки
            lbl = tk.Label(
                self._matrix_frame,
                text=str(height),
                font=heading_font,  # ИСПРАВЛЕНО: используем масштабированный шрифт
                relief="ridge",
                borderwidth=1,
                bg='#e8e8e8',
                fg='#000000',
                anchor="center",
                width=4,
            )
            lbl.grid(row=i + 1, column=0, sticky="nsew", padx=1, pady=1)
            self._row_headers[i + 1] = lbl

            # Ячейки
            for j, length in enumerate(lengths):
                # ИСПРАВЛЕНО: передаём масштабированный шрифт
                self._create_matrix_cell_adaptive_with_font(
                    data, length, height, i + 1, j + 1, default_font
                )

        # Настройка размеров колонок и строк
        for col in range(len(lengths) + 1):
            if col == 0:
                self._matrix_frame.columnconfigure(col, minsize=row_header_width, weight=0)
            else:
                self._matrix_frame.columnconfigure(col, minsize=cell_width, weight=1)
        for row in range(len(heights) + 1):
            self._matrix_frame.rowconfigure(row, minsize=cell_height)
        
        if not self._first_build_done:
            self._first_build_done = True

    def _create_matrix_cell_adaptive_with_font(self, data, length: int, height: int, row: int, col: int, font) -> None:
        """Создаёт ячейку матрицы с заданным шрифтом."""
        pattern = f"/{height}/{length}"
        match = data[data['Наименование'].str.contains(pattern, na=False, regex=False)]

        if not match.empty:
            product = match.iloc[0]
            art = str(product['Артикул']).strip()
            conn = product.get('Connection', '')
            rt = product.get('RadiatorType', '')
            key = (f"{conn} {rt}", art) if conn and rt else ("", art)
            current_value = self.app.entry_values.get(key, "")
            has_any = any(v for v in self.app.entry_values.values() if v)

            entry = tk.Entry(
                self._matrix_frame,
                width=5,
                justify="center",
                bg='#e6f3ff' if has_any else 'white',
                relief='solid',
                borderwidth=1,
                font=font,  # ИСПРАВЛЕНО: используем переданный масштабированный шрифт
                validate='key',
                validatecommand=(self.root.register(self._validate_input), '%P'),
            )
            entry.insert(0, current_value)

            # ... остальные bindings (без изменений)
            entry.bind("<FocusOut>", lambda e, k=key, ent=entry: self._on_cell_changed(k, ent))
            entry.bind("<Return>", lambda e, k=key, ent=entry: self._on_cell_changed(k, ent))
            entry.bind("<Enter>", lambda e, r=row, c=col: self._highlight_headers(r, c))
            entry.bind("<Leave>", lambda e: self._clear_highlights())
            entry.bind("<FocusIn>", lambda e, r=row, c=col: self._highlight_headers(r, c), add="+")
            entry.bind("<FocusOut>", lambda e: self._clear_highlights(), add="+")
            entry.bind("<Up>", lambda e, r=row, c=col: self._navigate_matrix(e, r, c, "up"))
            entry.bind("<Down>", lambda e, r=row, c=col: self._navigate_matrix(e, r, c, "down"))
            entry.bind("<Left>", lambda e, r=row, c=col: self._navigate_matrix(e, r, c, "left"))
            entry.bind("<Right>", lambda e, r=row, c=col: self._navigate_matrix(e, r, c, "right"))
            entry.bind("<Enter>", lambda e, p=product: self._show_cell_tooltip(e, p), add="+")
            entry.bind("<Leave>", self._hide_cell_tooltip, add="+")

            self._cell_entries[(row, col)] = entry
            entry.grid(row=row, column=col, sticky="nsew", padx=1, pady=1)
        else:
            entry = tk.Entry(
                self._matrix_frame,
                width=5,
                justify="center",
                bg='#f0f0f0',
                relief='solid',
                borderwidth=1,
                state='disabled',
                font=font,
            )
            entry.grid(row=row, column=col, sticky="nsew", padx=1, pady=1)
            
    def _update_all_cells_fonts(self) -> None:
        """Обновляет шрифты во всех ячейках матрицы."""
        default_font = self.app.font_manager.get_default_font()
        heading_font = self.app.font_manager.get_heading_font()
        
        # Обновляем ячейки
        for (row, col), entry in self._cell_entries.items():
            try:
                if entry and entry.winfo_exists():
                    entry.configure(font=default_font)
            except (tk.TclError, AttributeError):
                pass
        
        # Обновляем заголовки столбцов
        for lbl in self._col_headers.values():
            try:
                if lbl and lbl.winfo_exists():
                    lbl.configure(font=heading_font)
            except (tk.TclError, AttributeError):
                pass
        
        # Обновляем заголовки строк
        for lbl in self._row_headers.values():
            try:
                if lbl and lbl.winfo_exists():
                    lbl.configure(font=heading_font)
            except (tk.TclError, AttributeError):
                pass

    # ==================================================================
    # НИЖНЯЯ ПАНЕЛЬ
    # ==================================================================

    def _create_bottom_panel(self, parent: ttk.Frame) -> None:
        """Нижняя панель."""
        bottom = ttk.Frame(parent)
        bottom.pack(fill="x", pady=(5, 0))

        default_font = self.app.font_manager.get_default_font()

        # Отступ слева
        ttk.Frame(bottom, width=50).pack(side="left")

        ttk.Button(bottom, text="Предпросмотр", command=self._on_preview, width=15).pack(
            side="left", padx=5)

        # ========== НОВАЯ КНОПКА "АНАЛОГИ" ==========
        self._edit_correspondence_btn = ttk.Button(
            bottom, 
            text="Аналоги", 
            command=self._on_edit_correspondence,
            width=15,
            state="disabled"
        )
        self._edit_correspondence_btn.pack(side="left", padx=5)
        # ============================================

        ttk.Frame(bottom).pack(side="left", expand=True, fill="x")

        self._create_bracket_discount_row(bottom)

        ttk.Frame(bottom).pack(side="left", expand=True, fill="x")

        right_container = ttk.Frame(bottom)
        right_container.pack(side="right", fill="y")

        ttk.Frame(right_container, width=10).pack(side="right")

        try:
            logo_path = get_resource_path("PBO3.png")
            if os.path.exists(logo_path):
                self._logo_img = tk.PhotoImage(file=logo_path)
                tk.Label(right_container, image=self._logo_img, bg='#dedede',
                         bd=0, padx=0, pady=0).pack(side="right")
            else:
                tk.Label(right_container, text="PBO", bg='#dedede', fg='#444141',
                         font=default_font, bd=0, padx=8, pady=4).pack(side="right")
        except Exception:
            tk.Label(right_container, text="PBO", bg='#dedede', fg='#444141',
                     font=default_font, bd=0, padx=8, pady=4).pack(side="right")

        ttk.Button(right_container, text="Сброс", command=self._on_reset, width=15).pack(
            side="right", padx=(5, 40))

    def _create_bracket_discount_row(self, parent: ttk.Frame) -> None:
        """Блок кронштейнов и скидок."""
        default_font = self.app.font_manager.get_default_font()
        
        ttk.Label(parent, text="Кронштейны и скидки:", font=default_font).pack(
            side="left", padx=(0, 5), pady=5)

        bracket_frame = tk.Frame(parent, relief="solid", borderwidth=1, bg='#dedede')
        bracket_frame.pack(side="left", padx=0, pady=0)

        for b in ["Настенные", "Напольные", "Без"]:
            full_text = f"{b} кронштейны" if b != "Без" else "Без кронштейнов"
            ttk.Radiobutton(bracket_frame, text=full_text,
                            variable=self.bracket_var, value=full_text
                            ).pack(side="left", padx=5, pady=3)

        ttk.Label(bracket_frame, text="Радиаторы, %:", width=12, font=default_font).pack(
            side="left", padx=(10, 0), pady=3)
        ttk.Entry(bracket_frame, textvariable=self.radiator_discount_var, width=5,
                  validate="key",
                  validatecommand=(self.root.register(self._validate_number), '%P')
                  ).pack(side="left", padx=2, pady=3)

        ttk.Label(bracket_frame, text="Кронштейны, %:", width=12, font=default_font).pack(
            side="left", padx=(5, 0), pady=3)
        ttk.Entry(bracket_frame, textvariable=self.bracket_discount_var, width=5,
                  validate="key",
                  validatecommand=(self.root.register(self._validate_number), '%P')
                  ).pack(side="left", padx=2, pady=3)

    # ==================================================================
    # ОБРАБОТЧИКИ
    # ==================================================================

    def _validate_input(self, value: str) -> bool:
        if value == "": return True
        return all(c.isdigit() or c == '+' for c in value)

    def _validate_number(self, value: str) -> bool:
        if value == "": return True
        try:
            v = float(value.replace(',', '.'))
            return 0 <= v <= 100
        except ValueError:
            return False

    def _on_cell_changed(self, key: tuple, entry: tk.Entry) -> None:
        value = entry.get().strip()
        if value:
            self.app.entry_values[key] = value
        else:
            self.app.entry_values.pop(key, None)
        has_any = any(v for v in self.app.entry_values.values() if v)
        color = '#e6f3ff' if has_any else 'white'
        for ent in self._cell_entries.values():
            try:
                if ent.winfo_exists() and ent['state'] != 'disabled':
                    ent.config(bg=color)
            except tk.TclError:
                pass

    def _highlight_headers(self, row: int, col: int) -> None:
        if col in self._col_headers:
            self._col_headers[col].config(bg='#c8c8c8')
        if row in self._row_headers:
            self._row_headers[row].config(bg='#c8c8c8')

    def _clear_highlights(self) -> None:
        for h in self._col_headers.values():
            h.config(bg='#e8e8e8')
        for h in self._row_headers.values():
            h.config(bg='#e8e8e8')

    def _navigate_matrix(self, event, current_row: int, current_col: int, direction: str) -> str:
        """
        Навигация по матрице с помощью стрелок клавиатуры.
        С подсветкой заголовков для новой ячейки.
        """
        # Получаем все дочерние виджеты матрицы
        children = self._matrix_frame.grid_slaves()

        # Находим следующую ячейку в зависимости от направления
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

        # Ищем Entry виджет на нужной позиции
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

        # Если нашли Entry — переходим к нему и подсвечиваем заголовки
        if target_entry:
            target_entry.focus_set()
            # Выделяем текст в ячейке для удобства редактирования
            target_entry.select_range(0, tk.END)
            # Подсвечиваем заголовки для новой ячейки
            self._highlight_headers(target_row, target_col)

        # Всегда возвращаем "break" чтобы предотвратить стандартную обработку Tab
        return "break"

    def _on_data_loaded(self, count: int) -> None:
        logger.info(f"Данные загружены: {count} радиаторов")

    # ==================================================================
    # ДЕЙСТВИЯ
    # ==================================================================

    def _parse_qty(self, value) -> int:
        """Парсит количество из строки (поддерживает 1+2)."""
        if not value or value == "":
            return 0
        import re
        str_value = str(value).strip()
        if '+' in str_value:
            parts = str_value.split('+')
            total = 0
            for p in parts:
                p = p.strip()
                if not p:
                    continue
                match = re.search(r'(\d+)', p)
                if match:
                    total += int(match.group(1))
            return total
        match = re.search(r'(\d+)', str_value)
        return int(match.group(1)) if match else 0



    def _on_reset(self) -> None:
        """
        Сброс всего: матрица, кэш, вспомогательные окна, данные таблицы соответствия.
        Вызывается при нажатии кнопки «Сброс».
        """
        # 1. Очистка матрицы (количества радиаторов)
        self.app.entry_values.clear()
        
        # 2. Сброс настроек (скидки, тип кронштейнов)
        self.radiator_discount_var.set("0")
        self.bracket_discount_var.set("0")
        self.bracket_var.set("Настенные кронштейны")
        
        # 3. Очистка кэша данных таблицы соответствия
        self._clear_cache()
        
        # 4. Закрытие всех вспомогательных окон
        self._close_all_child_windows()
        
        # 5. Перестроение матрицы
        self._build_matrix(self._conn_var.get(), self._type_var.get())
        
        logger.info("Сброс выполнен: матрица очищена, кэш сброшен, окна закрыты, данные таблицы соответствия удалены")
        

    def _clear_cache(self) -> None:
        """
        Очищает кэш данных таблицы соответствия и экспорта.
        """
        # Очистка данных таблицы соответствия (основное хранилище)
        if hasattr(self.app, '_all_correspondence_data'):
            self.app._all_correspondence_data = None
        
        # Очистка данных для экспорта в Excel
        if hasattr(self.app, '_all_correspondence_data_for_export'):
            self.app._all_correspondence_data_for_export = None
        
        # Очистка последних данных таблицы соответствия
        if hasattr(self.app, '_last_correspondence_data'):
            self.app._last_correspondence_data = None
        
        # Очистка ссылки на диалог
        if hasattr(self.app, '_last_correspondence_dialog'):
            self.app._last_correspondence_dialog = None
        
        # Очистка сохранённых данных в диалоге (если есть)
        if hasattr(self, '_saved_correspondence_data'):
            self._saved_correspondence_data = None
        
        # Деактивируем кнопку "Аналоги"
        if hasattr(self, '_edit_correspondence_btn'):
            self._edit_correspondence_btn.config(state="disabled")
        
        logger.info("Кэш данных таблицы соответствия полностью очищен")
    
    def _close_all_child_windows(self) -> None:
        """
        Закрывает все дочерние окна приложения.
        """
        closed_count = 0
        
        # Перебираем все Toplevel окна
        for window in self.root.winfo_children():
            if isinstance(window, tk.Toplevel):
                try:
                    if window.winfo_exists():
                        window.destroy()
                        closed_count += 1
                except tk.TclError:
                    closed_count += 1
                    pass
                except Exception as e:
                    logger.debug(f"Ошибка закрытия окна: {e}")

        # Закрываем известные окна (если они не были закрыты через Toplevel)
        windows_to_close = [
            ('_dialog', 'MeteorSelector'),
            ('_dialog', 'PreviewDialog'),
            ('dialog', 'PdfPageSelector'),
            ('_dialog', 'ColumnSelector'),
        ]
        
        # Проверяем атрибуты приложения
        if hasattr(self.app, '_last_correspondence_dialog'):
            try:
                dialog = self.app._last_correspondence_dialog
                if hasattr(dialog, '_dialog') and dialog._dialog and dialog._dialog.winfo_exists():
                    dialog._close()
                    closed_count += 1
                    logger.debug("Закрыт CorrespondenceDialog")
            except Exception as e:
                logger.debug(f"Ошибка закрытия CorrespondenceDialog: {e}")

        # Проверяем MeteorSelector (может быть в атрибутах main_window)
        if hasattr(self, '_meteor_selector') and self._meteor_selector:
            try:
                if hasattr(self._meteor_selector, '_dialog') and \
                self._meteor_selector._dialog and \
                self._meteor_selector._dialog.winfo_exists():
                    self._meteor_selector._close()
                    closed_count += 1
                    logger.debug("Закрыт MeteorSelector")
            except Exception as e:
                logger.debug(f"Ошибка закрытия MeteorSelector: {e}")
            finally:
                self._meteor_selector = None

        # Проверяем PreviewDialog
        if hasattr(self, '_preview_dialog') and self._preview_dialog:
            try:
                if hasattr(self._preview_dialog, '_dialog') and \
                self._preview_dialog._dialog and \
                self._preview_dialog._dialog.winfo_exists():
                    self._preview_dialog._close()
                    closed_count += 1
                    logger.debug("Закрыт PreviewDialog")
            except Exception as e:
                logger.debug(f"Ошибка закрытия PreviewDialog: {e}")
            finally:
                self._preview_dialog = None

        # Убираем подсказки
        self._hide_cell_tooltip()
        if hasattr(self, '_header_tooltip') and self._header_tooltip and \
        self._header_tooltip.winfo_exists():
            self._header_tooltip.destroy()

        if closed_count > 0:
            logger.info(f"Закрыто дочерних окон: {closed_count}")
        else:
            logger.debug("Нет открытых дочерних окон для закрытия")

    def _on_preview(self) -> None:
        """Открывает предпросмотр спецификации."""
        spec_data = self.app.spec_generator.prepare_spec_data(
            entry_values=self.app.entry_values,
            bracket_type=self.bracket_var.get(),
            radiator_discount=float(self.radiator_discount_var.get() or 0),
            bracket_discount=float(self.bracket_discount_var.get() or 0),
        )

        if spec_data is None or spec_data.empty:
            messagebox.showwarning("Предпросмотр", "Нет данных для спецификации.\nЗаполните матрицу радиаторов.")
            return

        from nextt.ui.dialogs.preview import PreviewDialog
        preview = PreviewDialog(self.app)
        self._preview_dialog = preview
        preview.show(spec_data)

    def _on_edit_correspondence(self) -> None:
        """Открывает окно Мастера подбора аналогов с сохранёнными данными."""
        # Проверяем, есть ли сохранённые данные
        if hasattr(self.app, '_last_correspondence_data') and self.app._last_correspondence_data is not None:
            if not self.app._last_correspondence_data.empty:
                from nextt.ui.dialogs.correspondence import CorrespondenceDialog
                dialog = CorrespondenceDialog(self.app)
                self.app._last_correspondence_dialog = dialog
                dialog.show(self.app._last_correspondence_data)
                return
        
        # Если сохранённых данных нет, проверяем _all_correspondence_data
        if hasattr(self.app, '_all_correspondence_data') and self.app._all_correspondence_data is not None:
            if not self.app._all_correspondence_data.empty:
                from nextt.ui.dialogs.correspondence import CorrespondenceDialog
                dialog = CorrespondenceDialog(self.app)
                self.app._last_correspondence_dialog = dialog
                dialog.show(self.app._all_correspondence_data)
                return
        
        messagebox.showinfo("Информация", "Нет данных для редактирования.\nСначала загрузите спецификацию.")

    def _on_create_spec(self) -> None:
        """Создаёт и сразу открывает спецификацию в Excel."""
        from nextt.export.spec_generator import SpecGenerator
        from nextt.export.excel_writer import ExcelWriter
        import subprocess
        import platform
        import tempfile

        spec_data = self.app.spec_generator.prepare_spec_data(
            entry_values=self.app.entry_values,
            bracket_type=self.bracket_var.get(),
            radiator_discount=float(self.radiator_discount_var.get() or 0),
            bracket_discount=float(self.bracket_discount_var.get() or 0),
        )

        if spec_data is None or spec_data.empty:
            messagebox.showwarning("Пусто", "Нет данных для спецификации.\nЗаполните матрицу радиаторов.")
            return

        try:
            temp_dir = tempfile.gettempdir()

            # Генерируем уникальное имя файла
            base_name = "Расчёт стоимости"
            file_path = os.path.join(temp_dir, f"{base_name}.xlsx")
            counter = 1
            while os.path.exists(file_path):
                file_path = os.path.join(temp_dir, f"{base_name}_{counter}.xlsx")
                counter += 1
                if counter > 1000000000:
                    raise Exception("Не удалось создать уникальное имя файла")

            writer = ExcelWriter(data_provider=self.app.data_provider)

            # Получаем данные таблицы соответствия
            # ГЛАВНЫЙ ИСТОЧНИК: _all_correspondence_data (накопительное хранилище)
            correspondence_df = None
            
            if hasattr(self.app, '_all_correspondence_data') and self.app._all_correspondence_data is not None:
                correspondence_df = self.app._all_correspondence_data.copy()
                logger.info(f"Экспорт: используем _all_correspondence_data, {len(correspondence_df)} строк")
                # Переименовываем столбцы под формат ExcelWriter
                correspondence_df = correspondence_df.rename(columns={
                    'Наименование': 'Оригинальное наименование',
                    'Кол-во': 'Количество',
                    'Источник': 'Источник подбора',
                })
            else:
                # Запасной вариант: если хранилище пустое, пробуем диалог
                if hasattr(self.app, '_last_correspondence_dialog'):
                    dialog = self.app._last_correspondence_dialog
                    if hasattr(dialog, 'get_correspondence_data'):
                        correspondence_df = dialog.get_correspondence_data()
                        logger.info(f"Экспорт: используем данные из диалога, {len(correspondence_df) if correspondence_df is not None else 0} строк")

            # Получаем название программы из заголовка окна
            program_name = self.root.title()
            writer.save(spec_data, file_path, correspondence_data=correspondence_df, program_name=program_name)

            if platform.system() == "Windows":
                os.startfile(file_path)
            elif platform.system() == "Darwin":
                subprocess.call(["open", file_path])
            else:
                subprocess.call(["xdg-open", file_path])

        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось создать спецификацию:\n{str(e)}")
            logger.error(f"Ошибка создания спецификации: {e}")

    def _on_load_data(self) -> None:
        """Загружает данные из файла спецификации."""
        from tkinter import filedialog
        import pandas as pd
        import re
        import os

        file_path = filedialog.askopenfilename(
            title="Выберите файл спецификации",
            filetypes=[
                ("Все поддерживаемые", "*.xlsx *.xls *.xlsm *.csv *.tsv *.txt *.pdf *.docx"),
                ("Excel файлы", "*.xlsx *.xls *.xlsm"),
                ("CSV/TSV файлы", "*.csv *.tsv *.txt"),
                ("Word файлы", "*.docx"),
                ("PDF файлы", "*.pdf"),
                ("Все файлы", "*.*"),
            ]
        )
        if not file_path:
            return

        # Проверяем, есть ли уже данные в матрице
        has_existing_data = bool(self.app.entry_values)
        
        choice = None
        if has_existing_data:
            # Показываем диалог выбора
            choice = self._ask_add_or_replace()
            if choice is None:
                return  # Отмена
            elif choice == "replace":
                # Очищаем матрицу
                self.app.entry_values.clear()
                # Очищаем данные таблицы соответствия
                if hasattr(self.app, '_last_correspondence_dialog'):
                    dialog = self.app._last_correspondence_dialog
                    if hasattr(dialog, '_saved_correspondence_data'):
                        dialog._saved_correspondence_data = None
                # Обновляем матрицу
                self._build_matrix(self._conn_var.get(), self._type_var.get())
            # Если choice == "add" — просто продолжаем, матрица не очищается
        
        try:
            # Читаем файл
            ext = os.path.splitext(file_path)[1].lower()

            # PDF обрабатываем отдельно
            if ext == '.pdf':
                self._load_pdf_file(file_path, append_mode=(choice == "add"))
                return

            # Word обрабатываем отдельно
            if ext == '.docx':
                from nextt.parsing.word_parser import WordParser
                df = WordParser.parse(file_path)
                # Word-файлы всегда обрабатываем как чужие спецификации
                self._load_foreign_file(df, file_path, append_mode=(choice == "add"))
                return

            # Всё остальное — через ExcelParser
            from nextt.parsing.excel_parser import ExcelParser
            df = ExcelParser.parse(file_path)

            # Проверяем: это артикулы LaggarTT?
            is_laggar = self._is_laggar_file(df)

            if is_laggar:
                # ПЫТАЕМСЯ ЗАГРУЗИТЬ КАК СВОЮ СПЕЦИФИКАЦИЮ
                success = self._load_laggar_file(df)
                if not success:
                    # Если не получилось — обрабатываем как чужую
                    logger.info("Не удалось загрузить как файл LaggarTT, переключаюсь на режим чужой спецификации")
                    self._load_foreign_file(df, file_path, append_mode=(choice == "add"))
            else:
                # Обрабатываем как чужую спецификацию
                self._load_foreign_file(df, file_path, append_mode=(choice == "add"))

        except ImportError as e:
            messagebox.showerror("Ошибка", str(e))
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось загрузить файл:\n{str(e)}")
            logger.error(f"Ошибка загрузки: {e}")

    def _ask_add_or_replace(self) -> Optional[str]:
        """
        Показывает диалог выбора: добавить данные к существующим или заменить.
        Возвращает:
            "add" — добавить к существующим
            "replace" — очистить и начать новую
            None — отмена
        """
        dialog = tk.Toplevel(self.root)
        dialog.title("Данные уже есть")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.resizable(False, False)
        dialog.configure(bg='#dedede')

        # Центрируем окно
        dialog.update_idletasks()
        w = 700
        h = 230
        screen_w = dialog.winfo_screenwidth()
        screen_h = dialog.winfo_screenheight()
        x = (screen_w - w) // 2
        y = (screen_h - h) // 2
        dialog.geometry(f"{w}x{h}+{x}+{y}")

        # Иконка и заголовок
        header_frame = tk.Frame(dialog, bg='#dedede')
        header_frame.pack(fill="x", padx=20, pady=(20, 0))

        tk.Label(
            header_frame,
            text="⚠️",
            font=("Segoe UI", 24),
            bg='#dedede',
            fg='#f39c12'
        ).pack(side="left", padx=(0, 10))

        tk.Label(
            header_frame,
            text="В матрице уже есть данные",
            font=("Segoe UI", 13, "bold"),
            bg='#dedede',
            fg='#444141'
        ).pack(side="left")

        # Описание
        tk.Label(
            dialog,
            text="Вы хотите добавить новые позиции к существующей спецификации\nили очистить матрицу и начать новую?",
            font=("Segoe UI", 10),
            bg='#dedede',
            fg='#444141',
            justify="center",
            wraplength=650
        ).pack(pady=(15, 20))

        # Контейнер для результата
        result = {"choice": None}

        def on_add():
            result["choice"] = "add"
            dialog.destroy()

        def on_replace():
            result["choice"] = "replace"
            dialog.destroy()

        def on_cancel():
            result["choice"] = None
            dialog.destroy()

        # Кнопки — используем tk.Button для точного контроля ширины
        btn_frame = tk.Frame(dialog, bg='#dedede')
        btn_frame.pack(pady=(0, 20))

        btn_add = tk.Button(
            btn_frame,
            text="Добавить к существующим",
            command=on_add,
            width=30,
            bg='#263168',
            fg='white',
            font=("Segoe UI", 9),
            relief="flat",
            cursor="hand2",
            activebackground='#7E1A2F',
            activeforeground='white'
        )
        btn_add.pack(side="left", padx=5)

        btn_replace = tk.Button(
            btn_frame,
            text="Заменить (начать новую)",
            command=on_replace,
            width=30,
            bg='#263168',
            fg='white',
            font=("Segoe UI", 9),
            relief="flat",
            cursor="hand2",
            activebackground='#7E1A2F',
            activeforeground='white'
        )
        btn_replace.pack(side="left", padx=5)

        btn_cancel = tk.Button(
            btn_frame,
            text="Отмена",
            command=on_cancel,
            width=15,
            bg='#263168',
            fg='white',
            font=("Segoe UI", 9),
            relief="flat",
            cursor="hand2",
            activebackground='#7E1A2F',
            activeforeground='white'
        )
        btn_cancel.pack(side="left", padx=5)

        # Ждём закрытия
        dialog.wait_window()
        return result["choice"]

    def _load_pdf_file(self, file_path: str, append_mode: bool = False) -> None:
        """Загружает данные из PDF-файла."""
        from nextt.parsing.pdf_parser import PDFParser, get_pdf_page_count
        import pandas as pd

        try:
            total_pages = get_pdf_page_count(file_path)
            pages_to_parse = None

            # ============================================================
            # Если страниц 5 или меньше — читаем все, окно не показываем 
            # ============================================================
            if total_pages <= 5:
                pages_to_parse = list(range(1, total_pages + 1))
                logger.info(f"PDF содержит {total_pages} стр. (≤5) — читаем все страницы автоматически")
            else:
                # Показываем диалог выбора страниц
                from nextt.ui.dialogs.page_selector import PdfPageSelector
                selector = PdfPageSelector(self.root, total_pages, file_path, font_manager=self.font_manager)
                self._page_selector = selector
                pages_to_parse = selector.show()
                self._page_selector = None

                if pages_to_parse is None:
                    return  # Отмена

            if not pages_to_parse:
                messagebox.showwarning("Предупреждение", "Не выбрано ни одной страницы.")
                return

            # Парсим PDF
            progress = tk.Toplevel(self.root)
            progress.title("Обработка PDF")
            progress.transient(self.root)
            progress.grab_set()
            progress.geometry("400x120")

            screen_w = progress.winfo_screenwidth()
            screen_h = progress.winfo_screenheight()
            progress.geometry(f"+{(screen_w-400)//2}+{(screen_h-120)//2}")

            ttk.Label(progress, text="Обработка PDF-файла...",
                      font=("Segoe UI", 10)).pack(pady=10)
            prog_bar = ttk.Progressbar(progress, mode='determinate', length=350)
            prog_bar.pack(pady=5)
            prog_label = ttk.Label(progress, text="0%")
            prog_label.pack(pady=5)

            progress.update()

            def update_progress(current, total):
                pct = int((current / total) * 100)
                prog_bar['value'] = pct
                prog_label.config(text=f"{pct}% — страница {current} из {total}")
                progress.update()

            parser = PDFParser(progress_callback=update_progress)
            
            df = parser.parse_to_dataframe(
                file_path,
                pages=pages_to_parse
            )

            progress.destroy()

            if df.empty:
                messagebox.showwarning("PDF", "Не удалось извлечь данные из PDF.")
                return

            # ========== СОХРАНЯЕМ ИСХОДНЫЕ ДАННЫЕ ДЛЯ ПОВТОРНОГО ИМПОРТА ==========
            self.app._last_raw_data = df.copy()
            self.app._last_file_path = file_path
            self.app._last_file_type = 'pdf'
            # ====================================================================

            # ============================================================
            # ПРОВЕРЯЕМ, ЕСТЬ ЛИ В ДАННЫХ АРТИКУЛЫ LAGGARTT/METEOR
            # ============================================================
            
            if self._is_laggar_file(df):
                logger.info("Автоопределение столбцов для LaggarTT PDF...")
                logger.info(f"DEBUG: df shape = {df.shape}")
                
                for row_idx in range(min(3, len(df))):
                    row_data = []
                    for col_idx in range(min(13, len(df.columns))):
                        val = str(df.iloc[row_idx, col_idx])[:60]
                        row_data.append(val)
                    logger.info(f"DEBUG: Строка {row_idx}: {row_data}")
                
                art_col = None
                qty_col = None
                
                header_row = -1
                for row_idx in range(min(5, len(df))):
                    has_article = False
                    has_quantity = False
                    art_col_candidate = -1
                    qty_col_candidate = -1
                    
                    for col_idx in range(len(df.columns)):
                        cell = str(df.iloc[row_idx, col_idx]).strip().lower()
                        if len(cell) < 30:
                            if not has_article and cell in ['артикул', 'article', 'art', 'код']:
                                has_article = True
                                art_col_candidate = col_idx
                            if not has_quantity and any(kw in cell for kw in ['кол-во', 'количество', 'qty', 'quantity']):
                                has_quantity = True
                                qty_col_candidate = col_idx
                    
                    if has_article and has_quantity:
                        header_row = row_idx
                        art_col = art_col_candidate
                        qty_col = qty_col_candidate
                        logger.info(f"DEBUG: Строка заголовков найдена: row={header_row}")
                        break
                
                if art_col is None:
                    import re
                    pattern = re.compile(r'7724[67]\d{5}')
                    best_match_col = -1
                    best_match_count = 0
                    for col_idx in range(len(df.columns)):
                        col_values = df.iloc[:, col_idx].astype(str)
                        matches = sum(1 for v in col_values if pattern.search(str(v)))
                        if matches > best_match_count:
                            best_match_count = matches
                            best_match_col = col_idx
                    
                    if best_match_count >= 2:
                        art_col = best_match_col
                        logger.info(f"Столбец артикулов найден по паттерну: {art_col}")
                
                if qty_col is None:
                    data_start_row = header_row + 1 if header_row >= 0 else 1
                    best_qty_col = -1
                    best_qty_count = 0
                    for col_idx in range(len(df.columns)):
                        if col_idx == art_col:
                            continue
                        numeric_count = 0
                        for row_idx in range(data_start_row, min(data_start_row + 20, len(df))):
                            try:
                                val = str(df.iloc[row_idx, col_idx]).strip()
                                import re
                                num_match = re.search(r'^(\d+)$', val.replace(' ', ''))
                                if num_match:
                                    num = int(num_match.group(1))
                                    if 1 <= num <= 10000:
                                        numeric_count += 1
                            except:
                                pass
                        if numeric_count > best_qty_count:
                            best_qty_count = numeric_count
                            best_qty_col = col_idx
                    
                    if best_qty_count >= 2:
                        qty_col = best_qty_col
                        logger.info(f"Столбец количества найден по числам: {qty_col}")
                
                if art_col is not None and qty_col is not None:
                    self._process_laggar_pdf_data(df, art_col, qty_col)
                else:
                    logger.warning("Не удалось автоопределить столбцы. Показываем ColumnSelector.")
                    from nextt.parsing.column_selector import ColumnSelector
                    strategy_data = {
                        "По умолчанию": df,
                        "Линии": df,
                        "Сниппеты": df,
                    }
                    selector = ColumnSelector(self.root, strategy_data, file_path, self.font_manager)
                    result = selector.select()
                    
                    if result[0] is not None:
                        pairs = result[0]
                        art_col, qty_col = pairs[0]
                        self._process_laggar_pdf_data(df, art_col, qty_col)
                    else:
                        messagebox.showwarning("Предупреждение", "Не удалось определить столбцы.")
                
                return
            
            # ============================================================
            # ЭТО ЧУЖАЯ СПЕЦИФИКАЦИЯ — ПОКАЗЫВАЕМ COLUMNSELECTOR
            # ============================================================
            
            from nextt.parsing.column_selector import ColumnSelector
            strategy_data = {
                "По умолчанию": df,
                "Линии": df,
                "Сниппеты": df,
            }
            selector = ColumnSelector(self.root, strategy_data, file_path, self.font_manager)
            result = selector.select()

            if result[0] is None:
                return

            pairs = result[0]
            
            # ========== ПЕРЕДАЁМ append_mode В process_pdf_foreign_data ==========
            logger.info(f"Вызов _process_pdf_foreign_data с append_mode={append_mode}")
            for name_col, qty_col in pairs:
                self._process_pdf_foreign_data(df, name_col, qty_col, file_path, append_mode)

        except ImportError as e:
            messagebox.showerror(
                "Ошибка",
                f"Для работы с PDF требуются библиотеки:\n"
                f"pip install pdfplumber PyMuPDF Pillow\n\n{str(e)}"
            )
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось обработать PDF:\n{str(e)}")
            logger.error(f"Ошибка загрузки PDF: {e}")
            import traceback
            logger.error(traceback.format_exc())

    def _parse_page_range(self, range_str: str, total_pages: int) -> Optional[List[int]]:
        """Парсит строку диапазона страниц."""
        pages = []
        parts = range_str.split(',')
        for part in parts:
            part = part.strip()
            if not part:
                continue
            if '-' in part:
                try:
                    start, end = part.split('-')
                    start = int(start.strip())
                    end = int(end.strip())
                    if 1 <= start <= total_pages and 1 <= end <= total_pages and start <= end:
                        pages.extend(range(start, end + 1))
                    else:
                        return None
                except ValueError:
                    return None
            else:
                try:
                    page = int(part)
                    if 1 <= page <= total_pages:
                        pages.append(page)
                    else:
                        return None
                except ValueError:
                    return None
        return sorted(set(pages)) if pages else None

    def _process_excel_foreign_data(self, df, name_col_idx, qty_col_idx, file_path, append_mode: bool = False) -> None:
        """
        Обрабатывает данные из Excel/CSV.
        """
        import pandas as pd
        
        logger.info("=" * 70)
        logger.info("НАЧАЛО ОБРАБОТКИ ДАННЫХ (Excel/CSV)")
        logger.info(f"Файл: {file_path}")
        logger.info(f"Столбец названий: {name_col_idx}, столбец количества: {qty_col_idx}")
        logger.info(f"DEBUG: df.shape = {df.shape} (строк: {len(df)}, столбцов: {len(df.columns)})")
        logger.info("=" * 70)
        
        # ========== ШАГ 1: Сбор названий + парсинг через SpecNormalizer ==========
        parsed_rows = []
        skipped_empty = 0
        skipped_zero_qty = 0
        
        logger.info("-" * 70)
        logger.info("ШАГ 1: СБОР И ПАРСИНГ НАЗВАНИЙ")
        logger.info("-" * 70)
        
        for i, (_, row) in enumerate(df.iterrows()):
            if name_col_idx >= len(row) or qty_col_idx >= len(row):
                continue
            
            original = str(row.iloc[name_col_idx]).strip()
            qty_str = str(row.iloc[qty_col_idx]).strip()
            
            if not original:
                skipped_empty += 1
                continue
            
            try:
                qty = self._parse_qty(qty_str)
                if qty <= 0:
                    skipped_zero_qty += 1
                    continue
            except (ValueError, TypeError):
                skipped_zero_qty += 1
                continue
            
            parsed = self.app.normalizer.normalize_and_extract(original)
            
            logger.info(f"\n[{len(parsed_rows) + 1}] Название: '{original[:80]}'")
            logger.info(f"  Количество: {qty}")
            
            if parsed.recognized:
                logger.info(f"  Распознано: type={parsed.rad_type}, h={parsed.height}, l={parsed.length}, "
                           f"conn={parsed.connection}, conf={parsed.confidence:.2f}, source={parsed.source}")
            else:
                logger.info(f"  ⚠️ НЕ РАСПОЗНАНО")
            
            parsed_rows.append({
                "original": original,
                "qty": qty,
                "parsed": parsed,
            })
        
        total_rows = len(parsed_rows)
        
        logger.info(f"\nШАГ 1: Собрано строк: {total_rows}")
        logger.info(f"  Пропущено пустых: {skipped_empty}")
        logger.info(f"  Пропущено с нулевым количеством: {skipped_zero_qty}")
        
        if not parsed_rows:
            messagebox.showwarning("Предупреждение", "Не удалось извлечь данные.")
            return
        
        # ========== ШАГ 2: Поиск аналогов ==========
        data_for_table = []
        total_found = 0
        total_not_found = 0
        found_by_template = 0
        found_by_normalizer = 0
        
        logger.info("-" * 70)
        logger.info("ШАГ 2: ПОИСК АНАЛОГОВ")
        logger.info("-" * 70)
        
        for idx, item in enumerate(parsed_rows, 1):
            original_name_str = item["original"]
            qty = item["qty"]
            parsed = item["parsed"]
            
            logger.info(f"\n[{idx}/{total_rows}] Название: '{original_name_str[:80]}'")
            logger.info(f"  Количество: {qty}")
            
            meteor_art = ""
            meteor_name = ""
            source = "Не подобрано"
            
            # ================================================================
            # ПРИОРИТЕТ 1: ПРОВЕРКА ШАБЛОНОВ
            # ================================================================
            logger.info("  [ПРИОРИТЕТ 1] Проверка шаблонов...")
            try:
                from nextt.patterns.template_manager import TemplateManager
                template_manager = TemplateManager()
                template_result = template_manager.apply_templates(original_name_str)
                
                if template_result:
                    logger.info(f"    ✅ Найден шаблон: connection={template_result.get('connection')}, "
                               f"type={template_result.get('rad_type')}, "
                               f"h={template_result.get('height')}, l={template_result.get('length')}")
                    
                    art, name = self.app.data_provider.find_analog(
                        template_result['connection'], template_result['rad_type'],
                        template_result['height'], template_result['length']
                    )
                    
                    if art:
                        meteor_art = art
                        meteor_name = name
                        source = "По образцу (шаблон)"
                        total_found += 1
                        found_by_template += 1
                        logger.info(f"    ✅ Найден аналог по шаблону: {art} - {name}")
                    else:
                        logger.info(f"    ❌ Аналог не найден в базе по параметрам шаблона")
                else:
                    logger.info(f"    ❌ Шаблон не найден")
            except Exception as e:
                logger.error(f"    ❌ Ошибка проверки шаблонов: {e}")
            
            # ================================================================
            # ПРИОРИТЕТ 2: SPECNORMALIZER
            # ================================================================
            if not meteor_art and parsed.recognized:
                logger.info("  [ПРИОРИТЕТ 2] Использую результат SpecNormalizer...")
                
                connection_to_use = parsed.connection
                if parsed.connection == "VK-левое" and parsed.rad_type in ('20', '21', '22'):
                    connection_to_use = "VK-правое"
                    logger.info(f"    Тип {parsed.rad_type} универсальный, VK-левое → VK-правое")
                
                art, name = self.app.data_provider.find_analog(
                    connection_to_use, parsed.rad_type,
                    parsed.height, parsed.length
                )
                
                if art:
                    meteor_art = art
                    meteor_name = name
                    source = "Автоматически"
                    total_found += 1
                    found_by_normalizer += 1
                    logger.info(f"    ✅ Найден аналог: {art} - {name}")
                else:
                    logger.info(f"    ❌ Аналог не найден в базе по параметрам из распознавания")
            
            if not meteor_art:
                total_not_found += 1
                logger.info(f"  ❌ ИТОГ: аналог НЕ НАЙДЕН")
            else:
                logger.info(f"  ✅ ИТОГ: {source} -> {meteor_art}")
            
            data_for_table.append({
                "Наименование": original_name_str,
                "Кол-во": qty,
                "Наименование LaggarTT": meteor_name,
                "Артикул LaggarTT": meteor_art,
                "Источник": source,
            })
        
        logger.info("\n" + "=" * 70)
        logger.info("ИТОГИ ПАРСИНГА:")
        logger.info(f"  Всего строк: {total_rows}")
        logger.info(f"  Найдено аналогов: {total_found}")
        logger.info(f"    - По шаблонам: {found_by_template}")
        logger.info(f"    - Через SpecNormalizer: {found_by_normalizer}")
        logger.info(f"  Не найдено аналогов: {total_not_found}")
        logger.info("=" * 70)
        
        # ========== ШАГ 3: Сохраняем данные ==========
        new_df = pd.DataFrame(data_for_table)
        
        if not new_df.empty:
            new_df = new_df[new_df["Артикул LaggarTT"] != ""]
            new_df = new_df[new_df["Артикул LaggarTT"].notna()]
            new_df = new_df[new_df["Источник"] != "Не подобрано"]
            logger.info(f"После фильтрации осталось {len(new_df)} строк (только с артикулами)")
        
        if append_mode and hasattr(self.app, '_all_correspondence_data') and self.app._all_correspondence_data is not None:
            old_df = self.app._all_correspondence_data.copy()
            if 'Оригинальное наименование' in old_df.columns:
                old_df = old_df.rename(columns={
                    'Оригинальное наименование': 'Наименование',
                    'Количество': 'Кол-во',
                    'Источник подбора': 'Источник',
                })
            needed_cols = ['Наименование', 'Кол-во', 'Наименование LaggarTT', 'Артикул LaggarTT', 'Источник']
            old_df = old_df[[c for c in needed_cols if c in old_df.columns]]
            combined_df = pd.concat([old_df, new_df], ignore_index=True)
            if not combined_df.empty:
                combined_df = combined_df[combined_df["Артикул LaggarTT"] != ""]
                combined_df = combined_df[combined_df["Артикул LaggarTT"].notna()]
                combined_df = combined_df[combined_df["Источник"] != "Не подобрано"]
            logger.info(f"DEBUG Данные объединены: было {len(old_df)} + новых {len(new_df)} = {len(combined_df)} строк")
        else:
            combined_df = new_df.copy()
            if not append_mode:
                logger.info("Данные Excel заменены (append_mode=False)")
        
        all_data_for_export = pd.DataFrame(data_for_table)
        if not all_data_for_export.empty:
            all_data_for_export = all_data_for_export[all_data_for_export["Артикул LaggarTT"] != ""]
            all_data_for_export = all_data_for_export[all_data_for_export["Артикул LaggarTT"].notna()]
        
        if append_mode and hasattr(self.app, '_all_correspondence_data_for_export') and self.app._all_correspondence_data_for_export is not None:
            old_export = self.app._all_correspondence_data_for_export.copy()
            combined_export = pd.concat([old_export, all_data_for_export], ignore_index=True)
            self.app._all_correspondence_data_for_export = combined_export
        else:
            self.app._all_correspondence_data_for_export = all_data_for_export.copy()
        
        self.app._all_correspondence_data = combined_df.copy()
        self.app._last_correspondence_data = pd.DataFrame(data_for_table).copy()
        
        logger.info(f"DEBUG _all_correspondence_data сохранён: {combined_df.shape[0]} строк")
        logger.info(f"DEBUG _all_correspondence_data_for_export сохранён: {self.app._all_correspondence_data_for_export.shape[0]} строк")
        
        if hasattr(self, '_edit_correspondence_btn'):
            self._edit_correspondence_btn.config(state="normal")
        
        from nextt.ui.dialogs.correspondence import CorrespondenceDialog
        dialog = CorrespondenceDialog(self.app)
        self.app._last_correspondence_dialog = dialog
        dialog.show(pd.DataFrame(data_for_table))

    def _process_word_foreign_data(self, df: pd.DataFrame, file_path: str, append_mode: bool = False) -> None:
        """
        Обрабатывает данные из Word-файла.
        Word-файлы похожи на Excel, но могут иметь разорванные строки в таблицах.
        """
        logger.info("=" * 70)
        logger.info("НАЧАЛО ОБРАБОТКИ ДАННЫХ (Word)")
        logger.info(f"Файл: {file_path}")
        logger.info(f"DEBUG: df.shape = {df.shape} (строк: {len(df)}, столбцов: {len(df.columns)})")
        logger.info("=" * 70)
        
        # ========== ШАГ 1: Объединение разорванных строк в Word-таблицах ==========
        merged_rows = []
        skip_next = False
        
        for i in range(len(df)):
            if skip_next:
                skip_next = False
                continue
            
            current_row = df.iloc[i].astype(str).tolist()
            current_text = ' '.join(current_row).strip()
            
            is_radiator_start = self._is_radiator_row_loose(current_text)
            
            if is_radiator_start and i + 1 < len(df):
                next_row = df.iloc[i + 1].astype(str).tolist()
                next_text = ' '.join(next_row).strip()
                
                if len(next_text) < 80 and not self._is_radiator_row_loose(next_text):
                    if not re.search(r'(шт|ед|qty|кол-во|\d+\s*шт)', next_text.lower()):
                        merged_row = []
                        max_cols = max(len(current_row), len(next_row))
                        for j in range(max_cols):
                            val1 = current_row[j] if j < len(current_row) else ""
                            val2 = next_row[j] if j < len(next_row) else ""
                            if val1 and val2:
                                merged_row.append(f"{val1} {val2}")
                            else:
                                merged_row.append(val1 or val2)
                        merged_rows.append(merged_row)
                        skip_next = True
                        continue
            
            merged_rows.append(current_row)
        
        if merged_rows:
            max_cols = max(len(row) for row in merged_rows)
            for row in merged_rows:
                while len(row) < max_cols:
                    row.append("")
            df_merged = pd.DataFrame(merged_rows)
            logger.info(f"ШАГ 1: Объединено строк: {len(df)} → {len(df_merged)}")
        else:
            df_merged = df.copy()
        
        # ========== ШАГ 2: Передаём в ColumnSelector ==========
        from nextt.parsing.column_selector import ColumnSelector
        selector = ColumnSelector(self.root, df_merged, file_path, self.font_manager)
        result = selector.select()
        
        if result[0] is None:
            return
        
        pairs = result[0]
        for name_col, qty_col in pairs:
            self._process_excel_foreign_data(df_merged, name_col, qty_col, file_path, append_mode)

    def _process_pdf_foreign_data(self, df: pd.DataFrame, name_col_idx: int, qty_col_idx: int, file_path: str, append_mode: bool = False) -> None:
        """
        Обрабатывает данные из PDF-файла.
        PDF имеет свои особенности: объединение строк, фильтрация страниц, три стратегии извлечения.
        """
        import pandas as pd
        import re
        
        logger.info("=" * 70)
        logger.info("НАЧАЛО ОБРАБОТКИ ДАННЫХ (PDF)")
        logger.info(f"Файл: {file_path}")
        logger.info(f"Столбец названий: {name_col_idx}, столбец количества: {qty_col_idx}")
        logger.info(f"DEBUG: df.shape = {df.shape} (строк: {len(df)}, столбцов: {len(df.columns)})")
        logger.info("=" * 70)
        
        # ========== ШАГ 1: Сбор названий с суммированием дубликатов ==========
        name_to_qty = {}
        name_to_full_text = {}
        skipped_empty = 0
        skipped_zero_qty = 0
        
        logger.info("-" * 70)
        logger.info("ШАГ 1: СБОР И СУММИРОВАНИЕ НАЗВАНИЙ (PDF)")
        logger.info("-" * 70)
        
        for i, (_, row) in enumerate(df.iterrows()):
            if name_col_idx >= len(row) or qty_col_idx >= len(row):
                continue
            
            original_name = str(row.iloc[name_col_idx]).strip() if row.iloc[name_col_idx] is not None else ""
            qty_str = str(row.iloc[qty_col_idx]).strip() if row.iloc[qty_col_idx] is not None else ""
            
            if not original_name:
                skipped_empty += 1
                continue
            
            try:
                qty = self._parse_qty(qty_str)
                if qty <= 0:
                    skipped_zero_qty += 1
                    continue
            except (ValueError, TypeError):
                skipped_zero_qty += 1
                continue
            
            if original_name in name_to_qty:
                name_to_qty[original_name] += qty
                logger.info(f"  ДУБЛИКАТ: '{original_name[:60]}...' +{qty} = {name_to_qty[original_name]}")
            else:
                name_to_qty[original_name] = qty
                name_to_full_text[original_name] = ' '.join(str(cell) for cell in row if pd.notna(cell)).strip()
                logger.info(f"  НОВЫЙ: '{original_name[:60]}...' qty={qty}")
        
        total_unique = len(name_to_qty)
        total_quantity = sum(name_to_qty.values())
        
        logger.info(f"\nШАГ 1: Уникальных названий: {total_unique}")
        logger.info(f"  Пропущено пустых: {skipped_empty}")
        logger.info(f"  Пропущено с нулевым количеством: {skipped_zero_qty}")
        logger.info(f"  Общее количество (суммированное): {total_quantity}")
        
        if total_unique == 0:
            messagebox.showwarning("Предупреждение", "Не удалось извлечь данные из PDF.")
            return
        
        # ========== ШАГ 1.5: ФИЛЬТРАЦИЯ МУСОРА ==========
        garbage_keywords = [
            'гост', 'труба', 'изоляция', 'k-flex', 'rockwool', 'isotec', 'кожух',
            'цилиндр', 'минеральная вата', 'краска', 'гильза',
            'кран', 'клапан', 'фильтр', 'воздухоотводчик', 'теплосчётчик', 'пульсар',
            'коллектор', 'насос', 'шаровой', 'балансировочный', 'термостатический',
            'дренажный', 'отсекающий', 'спускной', 'шаровый', 'латунный',
            'монтаж', 'пуско-наладочные', 'итого', 'секция', 'статья', 'всего',
            'rehau', 'valtec', 'sanext', 'usystems', 'ballu', 'ld pride', 'kzto',
            'ридан', 'teck', 'isotec shell',
            'bvr', 'mnt', 'mvt', 'apt', 'fvr', 'tr-n', 'lv-kb', 'lv-kv',
            'tr 9001', 'шрв', 'тр', 'электрический конвектор', 'ballu enzo',
            'шт', 'м', 'квт', 'вт', 'кг', 'м3', 'компл',
        ]
        
        radiator_keywords = [
            'радиатор', 'kermi', 'ftv', 'fk0', 'fko', 'profil-v', 'profil-k',
            'royal thermo', 'vc', 'vk-profil', 'k-profil', 'evra', 'oasis',
            'hv', 'fhv', 'cv', 'сv', 'c22', 'universal', 'compact', 'ventil',
            'конвектор', 'панельный', 'стальной', 'laggar', 'meteor',
            'pn', 'pb', 'oc', 'ov', 'рn', 'рb',
        ]
        
        radiator_patterns = [
            r'^[PNpnрnPBpbрbOСocOCОСосOVov]{2}-\d{2}-\d-\d{2}$',
            r'^[PNpnрnPBpbрbOСocOCОСосOVov]{2}-\d{2}-\d{2}-\d{2}$',
            r'^[PNpnрnPBpbрbOСocOCОСосOVov]{2}\s+\d{2}\s+\d\s+\d{2}$',
            r'\d{2}-\d-\d{2}$',
            r'\d{2}-\d{2}-\d{2}$',
            r'\d{1,2}/\d{3,4}/\d{3,4}',
            r'\d{3,4}x\d{3,4}',
        ]
        
        filtered_names = {}
        garbage_count = 0
        
        for name, qty in name_to_qty.items():
            name_lower = name.lower()
            
            is_radiator_by_keyword = any(kw in name_lower for kw in radiator_keywords)
            
            is_radiator_by_pattern = False
            for pattern in radiator_patterns:
                if re.search(pattern, name, re.IGNORECASE):
                    is_radiator_by_pattern = True
                    break
            
            has_triplet_numbers = len(re.findall(r'\d{2,4}', name)) >= 3
            has_size_format = re.search(r'\d{3,4}[xх]\d{3,4}', name_lower) is not None
            
            is_garbage = any(kw in name_lower for kw in garbage_keywords)
            
            if is_radiator_by_keyword or is_radiator_by_pattern or has_triplet_numbers or has_size_format:
                filtered_names[name] = qty
                logger.info(f"  ✅ ОСТАВЛЕНО (радиатор): '{name[:60]}'")
            elif is_garbage:
                garbage_count += 1
                logger.info(f"  🗑️ ПРОПУЩЕНО (мусор): '{name[:60]}'")
            else:
                filtered_names[name] = qty
                logger.info(f"  ⚠️ ОСТАВЛЕНО (неизвестный формат): '{name[:60]}'")
        
        name_to_qty = filtered_names
        total_unique = len(name_to_qty)
        
        logger.info(f"\nШАГ 1.5: После фильтрации осталось {total_unique} уникальных названий")
        logger.info(f"  Отфильтровано мусора: {garbage_count}")
        
        if total_unique == 0:
            messagebox.showwarning("Предупреждение", "После фильтрации не осталось данных для обработки.")
            return
        
        # ========== ШАГ 2: Поиск аналогов для каждого уникального названия ==========
        data_for_table = []
        total_found = 0
        total_not_found = 0
        
        logger.info("-" * 70)
        logger.info("ШАГ 2: ПОИСК АНАЛОГОВ (PDF)")
        logger.info("-" * 70)
        
        for idx, (original_name_str, qty) in enumerate(name_to_qty.items(), 1):
            full_text_for_parsing = original_name_str
            
            logger.info(f"\n[{idx}/{total_unique}] Название: '{original_name_str[:80]}'")
            logger.info(f"  Количество: {qty}")
            
            meteor_art = ""
            meteor_name = ""
            source = "Не подобрано"
            
            # ================================================================
            # ПРИОРИТЕТ 1: ПРОВЕРКА ШАБЛОНОВ
            # ================================================================
            logger.info("  [ПРИОРИТЕТ 1] Проверка шаблонов...")
            try:
                from nextt.patterns.template_manager import TemplateManager
                template_manager = TemplateManager()
                template_result = template_manager.apply_templates(original_name_str)
                
                if template_result:
                    logger.info(f"    ✅ Найден шаблон: connection={template_result.get('connection')}, "
                               f"type={template_result.get('rad_type')}, "
                               f"h={template_result.get('height')}, l={template_result.get('length')}")
                    
                    art, name = self.app.data_provider.find_analog(
                        template_result['connection'], template_result['rad_type'],
                        template_result['height'], template_result['length']
                    )
                    
                    if art:
                        meteor_art = art
                        meteor_name = name
                        source = "По образцу (шаблон)"
                        total_found += 1
                        logger.info(f"    ✅ Найден аналог по шаблону: {art} - {name}")
                    else:
                        logger.info(f"    ❌ Аналог не найден в базе по параметрам шаблона")
                else:
                    logger.info(f"    ❌ Шаблон не найден")
            except Exception as e:
                logger.error(f"    ❌ Ошибка проверки шаблонов: {e}")
            
            # ================================================================
            # ПРИОРИТЕТ 2: SPECNORMALIZER
            # ================================================================
            if not meteor_art:
                logger.info("  [ПРИОРИТЕТ 2] Использую SpecNormalizer...")
                parsed = self.app.normalizer.normalize_and_extract(full_text_for_parsing)
                
                if parsed.recognized:
                    logger.info(f"    Распознано: type={parsed.rad_type}, h={parsed.height}, l={parsed.length}, "
                               f"conn={parsed.connection}, conf={parsed.confidence:.2f}")
                    
                    connection_to_use = parsed.connection
                    if parsed.connection == "VK-левое" and parsed.rad_type in ('20', '21', '22'):
                        connection_to_use = "VK-правое"
                        logger.info(f"    Тип {parsed.rad_type} универсальный, VK-левое → VK-правое")
                    
                    art, name = self.app.data_provider.find_analog(
                        connection_to_use, parsed.rad_type,
                        parsed.height, parsed.length
                    )
                    
                    if art:
                        meteor_art = art
                        meteor_name = name
                        source = "Автоматически"
                        total_found += 1
                        logger.info(f"    ✅ Найден аналог: {art} - {name}")
                    else:
                        logger.info(f"    ❌ Аналог не найден в базе")
                else:
                    logger.info(f"    ❌ Не распознано")
            
            if not meteor_art:
                total_not_found += 1
                logger.info(f"  ❌ ИТОГ: аналог НЕ НАЙДЕН")
            else:
                logger.info(f"  ✅ ИТОГ: {source} -> {meteor_art}")
            
            data_for_table.append({
                "Наименование": original_name_str,
                "Кол-во": qty,
                "Наименование LaggarTT": meteor_name,
                "Артикул LaggarTT": meteor_art,
                "Источник": source,
            })
        
        logger.info("\n" + "=" * 70)
        logger.info("ИТОГИ ПАРСИНГА PDF:")
        logger.info(f"  Всего уникальных названий: {total_unique}")
        logger.info(f"  Найдено аналогов: {total_found}")
        logger.info(f"  Не найдено аналогов: {total_not_found}")
        logger.info("=" * 70)
        
        # ========== ШАГ 3: Сохраняем данные ==========
        new_df = pd.DataFrame(data_for_table)
        
        if not new_df.empty:
            new_df = new_df[new_df["Артикул LaggarTT"] != ""]
            new_df = new_df[new_df["Артикул LaggarTT"].notna()]
            new_df = new_df[new_df["Источник"] != "Не подобрано"]
            logger.info(f"После фильтрации осталось {len(new_df)} строк (только с артикулами)")
        
        all_data_for_export = pd.DataFrame(data_for_table)
        if not all_data_for_export.empty:
            all_data_for_export = all_data_for_export[all_data_for_export["Артикул LaggarTT"] != ""]
            all_data_for_export = all_data_for_export[all_data_for_export["Артикул LaggarTT"].notna()]
        
        if append_mode:
            if hasattr(self.app, '_all_correspondence_data') and self.app._all_correspondence_data is not None:
                old_df = self.app._all_correspondence_data.copy()
                needed_cols = ['Наименование', 'Кол-во', 'Наименование LaggarTT', 'Артикул LaggarTT', 'Источник']
                old_df = old_df[[c for c in needed_cols if c in old_df.columns]]
                combined_df = pd.concat([old_df, new_df], ignore_index=True)
                if not combined_df.empty:
                    combined_df = combined_df[combined_df["Артикул LaggarTT"] != ""]
                    combined_df = combined_df[combined_df["Артикул LaggarTT"].notna()]
                    combined_df = combined_df[combined_df["Источник"] != "Не подобрано"]
                logger.info(f"Данные PDF объединены: было {len(old_df)} + новых {len(new_df)} = {len(combined_df)} строк")
            else:
                combined_df = new_df.copy()
            
            if hasattr(self.app, '_all_correspondence_data_for_export') and self.app._all_correspondence_data_for_export is not None:
                old_export = self.app._all_correspondence_data_for_export.copy()
                combined_export = pd.concat([old_export, all_data_for_export], ignore_index=True)
                self.app._all_correspondence_data_for_export = combined_export
            else:
                self.app._all_correspondence_data_for_export = all_data_for_export.copy()
        else:
            combined_df = new_df.copy()
            self.app._all_correspondence_data_for_export = all_data_for_export.copy()
            logger.info("Данные PDF заменены (append_mode=False)")
        
        self.app._all_correspondence_data = combined_df.copy()
        self.app._last_correspondence_data = pd.DataFrame(data_for_table).copy()
        
        logger.info(f"DEBUG _all_correspondence_data сохранён: {combined_df.shape[0]} строк")
        logger.info(f"DEBUG _all_correspondence_data_for_export сохранён: {self.app._all_correspondence_data_for_export.shape[0]} строк")
        
        if hasattr(self, '_edit_correspondence_btn'):
            self._edit_correspondence_btn.config(state="normal")
        
        from nextt.ui.dialogs.correspondence import CorrespondenceDialog
        dialog = CorrespondenceDialog(self.app)
        self.app._last_correspondence_dialog = dialog
        dialog.show(pd.DataFrame(data_for_table))

    def _process_foreign_dataframe_direct(self, df: pd.DataFrame, append_mode: bool = False) -> None:
        """
        Обрабатывает DataFrame из буфера обмена как радиаторы.
        Использует существующую логику обработки.
        
        Args:
            df: DataFrame с колонками 'Наименование' и 'Кол-во'
            append_mode: True - добавить к существующим, False - заменить
        """
        import pandas as pd
        
        logger.info(f"Обработка DataFrame из буфера: {len(df)} строк")
        
        if df.empty:
            messagebox.showwarning("Предупреждение", "Нет данных для обработки")
            return
        
        # Проверяем, есть ли в данных артикулы LaggarTT
        is_laggar = self._is_laggar_file(df)
        
        if is_laggar:
            logger.info("Обнаружены артикулы LaggarTT, загружаем как свою спецификацию")
            self._load_laggar_dataframe(df, append_mode)
        else:
            logger.info("Чужие радиаторы, запускаем распознавание")
            # Показываем ColumnSelector для выбора столбцов
            from nextt.parsing.column_selector import ColumnSelector
            selector = ColumnSelector(self.root, df, "Данные из буфера обмена", self.font_manager)
            result = selector.select()
            
            if result[0] is None:
                logger.info("Пользователь отменил выбор столбцов")
                return
            
            pairs = result[0]
            # Обрабатываем все пары столбцов
            for name_col, qty_col in pairs:
                self._process_excel_foreign_data(df, name_col, qty_col, "данные из буфера", append_mode)

    def _load_laggar_dataframe(self, df: pd.DataFrame, append_mode: bool = False) -> None:
        """
        Загружает данные из DataFrame с артикулами LaggarTT.
        Заполняет матрицу напрямую, как при загрузке своего файла.
        """
        loaded_count = 0
        total_qty = 0
        
        # Если не append_mode, очищаем матрицу
        if not append_mode:
            self.app.entry_values.clear()
        
        for _, row in df.iterrows():
            # Первый столбец - артикул, второй - количество
            if len(row) < 2:
                continue
            
            art = str(row.iloc[0]).strip()
            qty_str = str(row.iloc[1]).strip()
            
            if not art or art.lower() == 'итого':
                continue
            
            try:
                qty = int(float(qty_str.replace(',', '.')))
                if qty <= 0:
                    continue
            except (ValueError, TypeError):
                continue
            
            # Конвертируем артикул если нужно (Meteor → LaggarTT)
            meteor_art, _ = self.app.data_provider.convert_meteor_to_laggar(art)
            if meteor_art:
                found = self.app.data_provider.find_by_article(meteor_art)
                if found is not None:
                    conn = found.get('Connection', '')
                    rt = found.get('RadiatorType', '')
                    if conn and rt:
                        key = (f"{conn} {rt}", meteor_art)
                        existing = self.app.entry_values.get(key, "")
                        if existing:
                            try:
                                new_val = str(int(existing) + qty)
                            except ValueError:
                                new_val = f"{existing}+{qty}"
                        else:
                            new_val = str(qty)
                        self.app.entry_values[key] = new_val
                        loaded_count += 1
                        total_qty += qty
            else:
                # Может быть кронштейн — пробуем найти в базе
                found = self.app.data_provider.find_by_article(art)
                if found is not None:
                    conn = found.get('Connection', '')
                    rt = found.get('RadiatorType', '')
                    if conn and rt:
                        key = (f"{conn} {rt}", art)
                        existing = self.app.entry_values.get(key, "")
                        if existing:
                            try:
                                new_val = str(int(existing) + qty)
                            except ValueError:
                                new_val = f"{existing}+{qty}"
                        else:
                            new_val = str(qty)
                        self.app.entry_values[key] = new_val
                        loaded_count += 1
                        total_qty += qty
        
        # Обновляем матрицу
        self._build_matrix(self._conn_var.get(), self._type_var.get())
        
        if loaded_count > 0:
            messagebox.showinfo(
                "Успех",
                f"Загружено позиций: {loaded_count}\nОбщее количество: {total_qty}"
            )
        else:
            messagebox.showwarning("Предупреждение", "Не найдено подходящих артикулов LaggarTT")

    def load_pdf_spec(self, file_path: str = None, append_mode: bool = False) -> None:
        """
        Загружает данные из PDF файла.
        Если PDF содержит более 5 страниц — показывает диалог выбора страниц.
        
        Args:
            file_path: путь к PDF файлу (если None — открывает диалог выбора)
            append_mode: True — добавить к существующим данным, False — заменить
        """
        if file_path is None:
            file_path = filedialog.askopenfilename(
                title="Выберите PDF файл",
                filetypes=[("PDF файлы", "*.pdf"), ("Все файлы", "*.*")]
            )
            if not file_path:
                return
        
        try:
            from nextt.parsing.pdf_parser import PDFParser, get_pdf_page_count
            
            # Получаем количество страниц
            total_pages = get_pdf_page_count(file_path)
            logger.info(f"PDF содержит {total_pages} страниц")
            
            pages_to_parse = None
            
            # Если страниц 5 или меньше — читаем все автоматически
            if total_pages <= 5:
                pages_to_parse = list(range(1, total_pages + 1))
                logger.info(f"PDF содержит {total_pages} стр. (≤5) — читаем все страницы автоматически")
            else:
                # Показываем диалог выбора страниц
                from nextt.ui.dialogs.page_selector import PdfPageSelector
                selector = PdfPageSelector(self.root, total_pages, file_path, font_manager=self.font_manager)
                pages_to_parse = selector.show()
                
                if pages_to_parse is None:
                    logger.info("Выбор страниц отменён пользователем")
                    return
            
            if not pages_to_parse:
                messagebox.showwarning("Предупреждение", "Не выбрано ни одной страницы.")
                return
            
            # Прогресс-диалог
            progress = tk.Toplevel(self.root)
            progress.title("Обработка PDF")
            progress.transient(self.root)
            progress.grab_set()
            progress.geometry("400x120")
            
            screen_w = progress.winfo_screenwidth()
            screen_h = progress.winfo_screenheight()
            progress.geometry(f"+{(screen_w-400)//2}+{(screen_h-120)//2}")
            
            ttk.Label(progress, text="Обработка PDF-файла...", font=("Segoe UI", 10)).pack(pady=10)
            prog_bar = ttk.Progressbar(progress, mode='determinate', length=350)
            prog_bar.pack(pady=5)
            prog_label = ttk.Label(progress, text="0%")
            prog_label.pack(pady=5)
            progress.update()
            
            def update_progress(current, total):
                pct = int((current / total) * 100)
                prog_bar['value'] = pct
                prog_label.config(text=f"{pct}% — страница {current} из {total}")
                progress.update()
            
            # Парсим PDF
            parser = PDFParser(progress_callback=update_progress)
            df = parser.parse_to_dataframe(file_path, pages=pages_to_parse)
            
            progress.destroy()
            
            if df.empty:
                messagebox.showwarning("PDF", "Не удалось извлечь данные из PDF.")
                return
            
            # Передаём в ColumnSelector
            from nextt.parsing.column_selector import ColumnSelector
            selector = ColumnSelector(self.root, df, file_path, self.font_manager)
            name_col, qty_col, _ = selector.select()
            
            if name_col is None or qty_col is None:
                return
            
            # Обрабатываем данные с передачей append_mode
            self._process_pdf_foreign_data(df, name_col, qty_col, file_path, append_mode)
            
        except ImportError as e:
            messagebox.showerror(
                "Ошибка",
                f"Для работы с PDF требуются библиотеки:\n"
                f"pip install pdfplumber\n\n{str(e)}"
            )
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось обработать PDF:\n{str(e)}")
            logger.error(f"Ошибка загрузки PDF: {e}")
            import traceback
            logger.error(traceback.format_exc())

    def _normalize_radiator_name(self, name: str) -> str:
        """
        Возвращает оригинальное название без изменений.
        Дедупликация не нужна — таблица соответствия должна совпадать с оригиналом.
        """
        return name.strip()

    def _is_laggar_file(self, df: pd.DataFrame) -> bool:
        """Проверяет, содержит ли файл артикулы LaggarTT/Meteor."""
        import re
        pattern = re.compile(r'7724[67]\d{5}')
        count = 0
        for row_idx in range(min(50, len(df))):
            for col_idx in range(len(df.columns)):
                cell = str(df.iloc[row_idx, col_idx])
                if pattern.search(cell):
                    count += 1
                    if count >= 2:
                        return True
        return False

    def _load_laggar_file(self, df: pd.DataFrame) -> bool:
        """
        Загружает файл с артикулами LaggarTT.
        Возвращает True если загрузка успешна, False если нет.
        """
        from nextt.parsing.excel_parser import ExcelParser

        # Автоопределение столбцов
        art_col, qty_col = ExcelParser.find_columns(df)

        if art_col is None:
            logger.warning("Не удалось найти столбец с артикулами в файле LaggarTT")
            return False
            
        if qty_col is None:
            qty_col = ExcelParser.auto_detect_qty_column(df)
            if qty_col is None:
                logger.warning("Не удалось найти столбец с количеством в файле LaggarTT")
                return False

        # Ищем строку с заголовками
        header_row = 0
        for i in range(min(10, len(df))):
            row_text = ' '.join(str(df.iloc[i, col]) for col in range(len(df.columns)) if col < len(df.columns))
            if any(kw in row_text.lower() for kw in ['артикул', 'наименование', 'товар', 'код']):
                header_row = i
                break

        loaded_count = 0
        total_qty = 0

        for i in range(header_row + 1, len(df)):
            if art_col >= len(df.columns) or qty_col >= len(df.columns):
                continue

            art = str(df.iloc[i, art_col]).strip()
            qty_str = str(df.iloc[i, qty_col]).strip()

            if not art or art.lower() == 'итого':
                continue

            try:
                qty = int(float(qty_str.replace(',', '.')))
                if qty <= 0:
                    continue
            except (ValueError, TypeError):
                continue

            # Конвертируем артикул если нужно (Meteor → LaggarTT)
            meteor_art, _ = self.app.data_provider.convert_meteor_to_laggar(art)
            if meteor_art:
                found = self.app.data_provider.find_by_article(meteor_art)
                if found is not None:
                    conn = found.get('Connection', '')
                    rt = found.get('RadiatorType', '')
                    if conn and rt:
                        key = (f"{conn} {rt}", meteor_art)
                        existing = self.app.entry_values.get(key, "")
                        if existing:
                            try:
                                new_val = str(int(existing) + qty)
                            except ValueError:
                                new_val = f"{existing}+{qty}"
                        else:
                            new_val = str(qty)
                        self.app.entry_values[key] = new_val
                        loaded_count += 1
                        total_qty += qty

        # Проверяем, удалось ли загрузить хотя бы одну позицию
        if loaded_count == 0:
            logger.warning("Не найдено подходящих артикулов LaggarTT в файле")
            return False

        # Обновляем матрицу
        self._build_matrix(self._conn_var.get(), self._type_var.get())

        # Автоматически открываем предпросмотр
        spec_data = self.app.spec_generator.prepare_spec_data(
            entry_values=self.app.entry_values,
            bracket_type=self.bracket_var.get(),
            radiator_discount=float(self.radiator_discount_var.get() or 0),
            bracket_discount=float(self.bracket_discount_var.get() or 0),
        )

        if spec_data is not None and not spec_data.empty:
            from nextt.ui.dialogs.preview import PreviewDialog
            preview = PreviewDialog(self.app)
            preview.show(spec_data)
        else:
            messagebox.showinfo(
                "Успех",
                f"Загружено позиций: {loaded_count}\nОбщее количество: {total_qty}"
            )

        return True
        
    def _process_laggar_pdf_data(self, df: pd.DataFrame, art_col: int, qty_col: int) -> None:
        """
        Заполняет матрицу радиаторов данными из распарсенного PDF
        с готовыми артикулами LaggarTT/Meteor.
        
        Args:
            df: DataFrame с данными
            art_col: индекс столбца с артикулами
            qty_col: индекс столбца с количеством
        """
        import re
        
        # Ищем строку с заголовками (пропускаем строки-заголовки)
        header_row = 0
        
        # Ищем строку, где есть "Артикул" или похожее
        for i in range(min(10, len(df))):
            row_text = ' '.join(str(df.iloc[i, col]) for col in range(len(df.columns)) if col < len(df.columns))
            if any(kw in row_text.lower() for kw in ['артикул', 'наименование', 'товар']):
                header_row = i
                break
        
        self.app.entry_values.clear()
        total = 0
        total_qty = 0
        
        for i in range(header_row + 1, len(df)):
            if art_col >= len(df.columns) or qty_col >= len(df.columns):
                continue
            
            art = str(df.iloc[i, art_col]).strip()
            qty_str = str(df.iloc[i, qty_col]).strip()
            
            # Пропускаем пустые артикулы и итоговые строки
            if not art or art.lower() == 'итого' or art.lower() == 'всего':
                continue
            
            # Проверяем, что артикул похож на LaggarTT/Meteor или кронштейн
            art_clean = re.sub(r'\D', '', art)
            if not art_clean:
                continue
            
            # Пропускаем, если артикул не LaggarTT/Meteor и не кронштейн
            if not (art_clean.startswith('77246') or art_clean.startswith('77247') or 
                    art.startswith('К') or art.startswith('K')):
                continue
            
            try:
                # Пробуем извлечь целое число из количества
                qty_match = re.search(r'(\d+)', str(qty_str).replace(',', '.'))
                if qty_match:
                    qty = int(qty_match.group(1))
                else:
                    qty = int(float(qty_str.replace(',', '.')))
                
                if qty <= 0:
                    continue
            except (ValueError, TypeError):
                continue
            
            # Конвертируем артикул если нужно (Meteor → LaggarTT)
            meteor_art, _ = self.app.data_provider.convert_meteor_to_laggar(art)
            if meteor_art:
                found = self.app.data_provider.find_by_article(meteor_art)
                if found is not None:
                    conn = found.get('Connection', '')
                    rt = found.get('RadiatorType', '')
                    if conn and rt:
                        key = (f"{conn} {rt}", meteor_art)
                        existing = self.app.entry_values.get(key, "")
                        if existing:
                            try:
                                new_val = str(int(existing) + qty)
                            except ValueError:
                                new_val = f"{existing}+{qty}"
                        else:
                            new_val = str(qty)
                        self.app.entry_values[key] = new_val
                        total += 1
                        total_qty += qty
            else:
                # Может быть кронштейн — пробуем найти в базе
                found = self.app.data_provider.find_by_article(art)
                if found is not None:
                    conn = found.get('Connection', '')
                    rt = found.get('RadiatorType', '')
                    if conn and rt:
                        key = (f"{conn} {rt}", art)
                        existing = self.app.entry_values.get(key, "")
                        if existing:
                            try:
                                new_val = str(int(existing) + qty)
                            except ValueError:
                                new_val = f"{existing}+{qty}"
                        else:
                            new_val = str(qty)
                        self.app.entry_values[key] = new_val
                        total += 1
                        total_qty += qty
        
        # Обновляем матрицу
        self._build_matrix(self._conn_var.get(), self._type_var.get())
        
        # ========== АВТОМАТИЧЕСКИ ОТКРЫВАЕМ ПРЕДПРОСМОТР ==========
        if total > 0:
            spec_data = self.app.spec_generator.prepare_spec_data(
                entry_values=self.app.entry_values,
                bracket_type=self.bracket_var.get(),
                radiator_discount=float(self.radiator_discount_var.get() or 0),
                bracket_discount=float(self.bracket_discount_var.get() or 0),
            )
            
            if spec_data is not None and not spec_data.empty:
                from nextt.ui.dialogs.preview import PreviewDialog
                preview = PreviewDialog(self.app)
                preview.show(spec_data)
            else:
                messagebox.showinfo(
                    "Успех",
                    f"Загружено позиций: {total}\nОбщее количество радиаторов: {total_qty}"
                )
        else:
            messagebox.showwarning(
                "Предупреждение",
                "Не найдено подходящих артикулов LaggarTT в файле."
            )

    def _load_foreign_file(self, df: pd.DataFrame, file_path: str, append_mode: bool = False) -> None:
        """Загружает чужую спецификацию с парсингом названий."""
        # Сохраняем исходные данные для повторного импорта
        self.app._last_raw_data = df.copy()
        self.app._last_file_path = file_path
        self.app._last_file_type = 'excel'
        
        from nextt.parsing.column_selector import ColumnSelector
        
        # ========== ВАЖНО: определяем append_mode ==========
        # Если это ПОВТОРНЫЙ импорт того же файла (кнопка "К выбору столбцов"),
        # то нужно ОБЪЕДИНЯТЬ данные, а не заменять
        # Проверяем, есть ли уже данные для этого файла
        if hasattr(self.app, '_last_imported_file') and self.app._last_imported_file == file_path:
            # Повторный импорт того же файла — объединяем
            actual_append_mode = True
            logger.info(f"Повторный импорт Excel: объединяем данные (append_mode=True)")
        else:
            # Первый импорт — заменяем
            actual_append_mode = False
            logger.info(f"Первый импорт Excel: заменяем данные (append_mode=False)")
            # Запоминаем, что этот файл уже импортировали
            self.app._last_imported_file = file_path
        
        selector = ColumnSelector(self.root, df, file_path, self.font_manager)
        result = selector.select()

        if result[0] is None:
            return

        pairs = result[0]  # список пар
        # Обрабатываем ВСЕ пары
        for name_col, qty_col in pairs:
            self._process_excel_foreign_data(df, name_col, qty_col, file_path, append_mode=actual_append_mode)

    def _create_tooltip_window(self) -> None:
        """Создаёт окно подсказки (один раз)."""
        if hasattr(self, '_tooltip_window') and self._tooltip_window and self._tooltip_window.winfo_exists():
            return

        self._tooltip_window = tk.Toplevel(self.root)
        self._tooltip_window.wm_overrideredirect(True)
        self._tooltip_window.withdraw()

        main_frame = tk.Frame(self._tooltip_window, bg='#ffffe0', padx=5, pady=5)
        main_frame.pack()

        self._tooltip_name = tk.Label(main_frame, font=("Segoe UI", 10, "bold"),
                                      bg='#ffffe0', fg='#000000',
                                      wraplength=300, justify="left")
        self._tooltip_name.pack(anchor="w")

        sep1 = tk.Frame(main_frame, height=1, bg='#cccccc', width=300)
        sep1.pack(fill="x", pady=3)

        self._tooltip_art = tk.Label(main_frame, font=("Segoe UI", 9),
                                     bg='#ffffe0', fg='#000000', justify="left")
        self._tooltip_art.pack(anchor="w")

        self._tooltip_params = tk.Label(main_frame, font=("Segoe UI", 9),
                                        bg='#ffffe0', fg='#000000', justify="left")
        self._tooltip_params.pack(anchor="w")

        sep2 = tk.Frame(main_frame, height=1, bg='#cccccc', width=300)
        sep2.pack(fill="x", pady=3)

        self._tooltip_price = tk.Label(main_frame, font=("Segoe UI", 9, "bold"),
                                       bg='#ffffe0', fg='#000000', justify="left")
        self._tooltip_price.pack(anchor="w")

    def _show_cell_tooltip(self, event, product) -> None:
        """Показывает подсказку с параметрами радиатора (как в оригинале)."""
        if not self.show_tooltips_var.get():
            return

        # Получаем актуальные шрифты
        default_font = self.font_manager.get_default_font()
        bold_font = self.font_manager.get_bold_font()
        italic_font = self.font_manager.get_font(9)

        # Создаём окно если ещё нет ИЛИ оно было уничтожено
        if not hasattr(self, '_tooltip_window') or not self._tooltip_window or not self._tooltip_window.winfo_exists():
            self._tooltip_window = tk.Toplevel(self.root)
            self._tooltip_window.wm_overrideredirect(True)
            self._tooltip_window.withdraw()

            main_frame = tk.Frame(self._tooltip_window, bg='#ffffe0', padx=5, pady=5)
            main_frame.pack()

            self._tip_name = tk.Label(main_frame, font=bold_font,
                                      bg='#ffffe0', fg='#000000', wraplength=300, justify="left")
            self._tip_name.pack(anchor="w")

            sep1 = tk.Frame(main_frame, height=1, bg='#cccccc', width=300)
            sep1.pack(fill="x", pady=3)

            self._tip_art = tk.Label(main_frame, font=default_font,
                                     bg='#ffffe0', fg='#000000', justify="left")
            self._tip_art.pack(anchor="w")

            self._tip_params = tk.Label(main_frame, font=default_font,
                                        bg='#ffffe0', fg='#000000', justify="left")
            self._tip_params.pack(anchor="w")

            sep2 = tk.Frame(main_frame, height=1, bg='#cccccc', width=300)
            sep2.pack(fill="x", pady=3)

            self._tip_price = tk.Label(main_frame, font=bold_font,
                                       bg='#ffffe0', fg='#000000', justify="left")
            self._tip_price.pack(anchor="w")

            # Кронштейны
            self._tip_bracket_info = tk.Label(main_frame, font=italic_font,
                                              bg='#ffffe0', fg='#000000', justify="left")
            self._tip_bracket_lines = []
            for _ in range(5):
                lbl = tk.Label(main_frame, font=default_font,
                              bg='#ffffe0', fg='#000000', justify="left")
                self._tip_bracket_lines.append(lbl)

            self._tip_sep3 = tk.Frame(main_frame, height=1, bg='#cccccc', width=300)
            self._tip_total = tk.Label(main_frame, font=bold_font,
                                       bg='#ffffe0', fg='#000000', justify="left")
        else:
            # Если окно уже существует — обновляем шрифты (на случай изменения масштаба)
            if hasattr(self, '_tip_name'):
                self._tip_name.config(font=bold_font)
            if hasattr(self, '_tip_art'):
                self._tip_art.config(font=default_font)
            if hasattr(self, '_tip_params'):
                self._tip_params.config(font=default_font)
            if hasattr(self, '_tip_price'):
                self._tip_price.config(font=bold_font)
            if hasattr(self, '_tip_bracket_info'):
                self._tip_bracket_info.config(font=italic_font)
            if hasattr(self, '_tip_bracket_lines'):
                for lbl in self._tip_bracket_lines:
                    lbl.config(font=default_font)
            if hasattr(self, '_tip_total'):
                self._tip_total.config(font=bold_font)

        if not self._tooltip_window.winfo_exists():
            return

        # === Извлечение данных ===
        import re
        name = str(product.get('Наименование', ''))
        art = str(product.get('Артикул', ''))
        power = product.get('Мощность, Вт', '')
        weight = product.get('Вес, кг', 0)
        volume = product.get('Объем, м3', 0)

        # Извлекаем параметры из названия для кронштейнов
        rad_type = None
        height = None
        length = None
        try:
            match = re.search(r'/(\d{2})/(\d{3,4})/(\d{3,4})', name)
            if match:
                rad_type, h, l = match.groups()
                height, length = int(h), int(l)
            else:
                parts = name.split('/')
                if len(parts) >= 3:
                    last_part = parts[-1].strip()
                    lm = re.search(r'(\d{3,4})', last_part)
                    if lm:
                        length = int(lm.group(1))
                    height_part = parts[-2].strip()
                    hm = re.search(r'(\d{3,4})', height_part)
                    if hm:
                        height = int(hm.group(1))
                    for p in reversed(parts[:-2]):
                        tm = re.search(r'(\d{2})', p)
                        if tm:
                            rad_type = tm.group(1)
                            break
        except Exception:
            pass

        # Количество радиаторов из ячейки
        qty_radiators = 1
        for (key, val) in self.app.entry_values.items():
            if isinstance(key, tuple) and len(key) >= 2 and key[1] == art:
                if val and val.strip():
                    qty_radiators = self._parse_qty(val) or 1
                break

        # Формат параметров
        power_text = f"Мощность: {power} Вт" if power else "Мощность: не указана"
        params_text = f"{power_text}  •  Вес: {weight} кг  •  Объём: {volume} м³"

        # Цена радиатора со скидкой
        base_price = product.get('Цена, руб (с НДС)', '') or product.get('Цена, руб', '')
        price_val = None
        price_disc = None
        price_total = None
        try:
            disc_rad = float(self.radiator_discount_var.get() or "0")
            disc_rad = max(0.0, min(100.0, disc_rad))
            price_val = float(base_price)
            price_disc = price_val * (1 - disc_rad / 100)
            price_total = price_disc * qty_radiators

            def fmt(val):
                return f"{val:,.2f}".replace(",", " ").replace(".", ",")

            price_str = (
                f"Цена с НДС: {fmt(price_disc)} руб × "
                f"{qty_radiators} шт = {fmt(price_total)} руб"
            )
        except:
            price_str = "Цена: не указана"

        # Обновляем основные строки
        self._tip_name.config(text=name)
        self._tip_art.config(text=f"Артикул: {art}")
        self._tip_params.config(text=params_text)
        self._tip_price.config(text=price_str)

        # Скрываем блок кронштейнов
        self._tip_bracket_info.pack_forget()
        for lbl in self._tip_bracket_lines:
            lbl.pack_forget()
        self._tip_sep3.pack_forget()
        self._tip_total.pack_forget()

        # Обработка кронштейнов
        bracket_choice = self.bracket_var.get()
        if bracket_choice != "Без кронштейнов" and rad_type and height and length:
            try:
                from nextt.core.brackets import BracketsCalculator
                brackets_list = BracketsCalculator.calculate(
                    radiator_type=rad_type,
                    length=length,
                    height=height,
                    bracket_type=bracket_choice,
                    quantity=qty_radiators,
                )
                if brackets_list:
                    self._tip_bracket_info.config(text="Кронштейны приобретаются отдельно")
                    self._tip_bracket_info.pack(anchor="w")

                    total_brackets_sum = 0.0
                    lines_used = 0

                    brackets_df = self.app.data_provider.brackets_df

                    for art_bracket, qty_bracket in brackets_list:
                        mask = brackets_df['Артикул'].astype(str).str.strip() == art_bracket
                        if not mask.any():
                            continue
                        bracket_info = brackets_df[mask].iloc[0]
                        full_name = str(bracket_info['Наименование'])

                        display_name = full_name
                        if display_name.startswith("Кронштейн "):
                            display_name = display_name[len("Кронштейн "):]
                        display_name = re.sub(r'\s*\(.*?\)', '', display_name).strip()

                        base_bracket_price = float(bracket_info.get('Цена, руб', 0))
                        try:
                            disc_br = float(self.bracket_discount_var.get() or "0")
                            disc_br = max(0.0, min(100.0, disc_br))
                        except:
                            disc_br = 0.0

                        bracket_price_disc = base_bracket_price * (1 - disc_br / 100)
                        line_total = bracket_price_disc * qty_bracket
                        total_brackets_sum += line_total

                        qty_per_rad = qty_bracket // qty_radiators if qty_radiators > 0 else qty_bracket

                        def fmt(val):
                            return f"{val:,.2f}".replace(",", " ").replace(".", ",")

                        line_text = (
                            f"{display_name} — "
                            f"{qty_per_rad} шт × {qty_radiators} рад × "
                            f"{fmt(bracket_price_disc)} руб = "
                            f"{fmt(line_total)} руб"
                        )

                        if lines_used < len(self._tip_bracket_lines):
                            self._tip_bracket_lines[lines_used].config(text=line_text)
                            self._tip_bracket_lines[lines_used].pack(anchor="w")
                            lines_used += 1

                    if price_val and price_total:
                        total_with = price_total + total_brackets_sum
                        self._tip_total.config(text=f"Итого с кронштейнами: {fmt(total_with)} руб")
                        self._tip_sep3.pack(fill="x", pady=3)
                        self._tip_total.pack(anchor="w")

            except Exception as e:
                logger.debug(f"Ошибка подбора кронштейнов: {e}")

        # Умное позиционирование
        pointer_x = self.root.winfo_pointerx()
        pointer_y = self.root.winfo_pointery()
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()

        self._tooltip_window.update_idletasks()
        tw = self._tooltip_window.winfo_reqwidth()
        th = self._tooltip_window.winfo_reqheight()

        x = pointer_x + 15
        y = pointer_y + 15

        if x + tw > screen_w:
            x = pointer_x - tw - 15
        if y + th > screen_h:
            y = pointer_y - th - 15
        if y < 0:
            y = 10

        self._tooltip_window.wm_geometry(f"+{x}+{y}")
        self._tooltip_window.deiconify()

    def _hide_cell_tooltip(self, event=None) -> None:
        """Скрывает подсказку."""
        if hasattr(self, '_tooltip_window') and self._tooltip_window and self._tooltip_window.winfo_exists():
            self._tooltip_window.withdraw()


    def _on_license(self) -> None:
        """Показывает лицензионное соглашение."""
        agreement_text = """ЛИЦЕНЗИОННОЕ СОГЛАШЕНИЕ
НА ИСПОЛЬЗОВАНИЕ ПРОГРАММНОГО ОБЕСПЕЧЕНИЯ "NexTT"

Настоящее Лицензионное соглашение (далее – «Соглашение») регулирует условия использования программного обеспечения «NexTT» (далее – «ПО»), распространяемого на безвозмездной основе.

1. Права на интеллектуальную собственность
1.1. Программное обеспечение, включая его исходный код, является интеллектуальной собственностью ООО «Термотехника Энгельс» (далее – «Правообладатель»).
1.2. Любое несанкционированное копирование, модификация или распространение ПО запрещено.

Реквизиты Правообладателя:
ООО «Термотехника Энгельс»
Россия, Саратовская область, г. Энгельс,
Проспект Ф. Энгельса, 139
Официальный сайт: https://laggartt.ru

2. Назначение ПО
2.1. Программное обеспечение предназначено для формирования спецификаций на радиаторы LaggarTT в соответствии с программой поставки ООО «Термотехника Энгельс».

3. Условия использования результатов работы ПО
3.1. Результаты, полученные с использованием ПО, носят оценочный характер и не могут рассматриваться как точные данные.
3.2. ПО предназначено исключительно для предварительной оценки оборудования и не может служить основанием для проектных решений без дополнительной проверки.
3.3. Использование ПО не освобождает Пользователя от соблюдения действующих отраслевых стандартов (DIN, ГОСТ), а также территориальных норм и правил.
3.4. Пользователь самостоятельно несет ответственность за:
- корректность подбора оборудования;
- соответствие материалов и компонентов требованиям проекта;
- последствия, вызванные некорректным использованием ПО.
3.5. ООО «Термотехника Энгельс» не несет ответственности за ущерб, возникший в результате применения данных, полученных с использованием ПО.

4. Условия распространения и использования ПО
4.1. Пользователь вправе устанавливать и использовать ПО на любом количестве компьютеров, в том числе в локальной сети организации.
4.2. Использование ПО разрешено несколькими сотрудниками при условии соблюдения настоящего Соглашения.

5. Срок действия и изменения
5.1. Действие настоящего Соглашения распространяется на версию ПО, актуальную на дату его выпуска.
5.2. ООО «Термотехника Энгельс» оставляет за собой право вносить изменения в номенклатуру оборудования без дополнительного уведомления Пользователей.

ООО «Термотехника Энгельс»
(01.2026)"""

        # Создаём окно с безопасной геометрией
        from nextt.utils.window_manager import get_safe_geometry
        
        license_window = tk.Toplevel(self.root)
        license_window.title("Лицензионное соглашение")
        license_window.transient(self.root)
        license_window.grab_set()
        license_window.geometry(get_safe_geometry(license_window))

        main_frame = ttk.Frame(license_window)
        main_frame.pack(fill="both", expand=True, padx=15, pady=15)

        text_widget = tk.Text(main_frame, wrap="word", font=("Segoe UI", 10),
                              padx=10, pady=10)
        text_widget.pack(fill="both", expand=True)
        text_widget.insert("1.0", agreement_text)
        text_widget.config(state="disabled")

        scrollbar = ttk.Scrollbar(text_widget, command=text_widget.yview)
        scrollbar.pack(side="right", fill="y")
        text_widget.config(yscrollcommand=scrollbar.set)

        ttk.Button(main_frame, text="Закрыть",
                   command=license_window.destroy).pack(pady=(10, 0))

    def _on_instruction(self) -> None:
        """Открывает файл инструкции PDF."""
        from nextt.config import get_resource_path
        try:
            pdf_path = get_resource_path("Инструкция.pdf")
            if os.path.exists(pdf_path):
                if platform.system() == "Windows":
                    os.startfile(pdf_path)
                elif platform.system() == "Darwin":
                    subprocess.call(["open", pdf_path])
                else:
                    subprocess.call(["xdg-open", pdf_path])
            else:
                messagebox.showerror("Ошибка", "Файл инструкции не найден.\nПоместите файл 'Инструкция.pdf' рядом с программой.")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось открыть файл инструкции:\n{str(e)}")

    def _on_price_list(self) -> None:
        try:
            path = get_resource_path("Прайс-лист.xlsx")
            if os.path.exists(path):
                os.startfile(path)
            else:
                messagebox.showerror("Ошибка", "Файл не найден")
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))

    def _on_catalog(self) -> None:
        import webbrowser
        webbrowser.open("https://laggartt.ru/catalogs/laggartt/")

    def _on_passport(self) -> None:
        import webbrowser
        webbrowser.open("https://b24.ez.meteor.ru/~yKwOz")

    def _on_certificate(self) -> None:
        import webbrowser
        webbrowser.open("https://b24.ez.meteor.ru/~jmXyC")

    def _on_check_update(self) -> None:
        """Проверяет наличие обновлений по кнопке."""
        from nextt.utils.update_checker import UpdateChecker
        checker = UpdateChecker(self.root, self.font_manager)
        update_data = checker.check_for_updates(show_no_update_message=True)
        if update_data:
            checker.show_update_dialog(update_data)