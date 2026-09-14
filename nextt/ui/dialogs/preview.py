"""
Окно предпросмотра спецификации.

"""

import tkinter as tk
from tkinter import ttk, messagebox
import os
import subprocess
import platform
import re
from typing import Dict, List, Optional
from pathlib import Path

import pandas as pd

from nextt.logger import get_logger
from nextt.utils.window_manager import get_safe_geometry
from nextt.core.brackets import BracketsCalculator

logger = get_logger(__name__)


class PreviewDialog:
    """Диалог предпросмотра спецификации."""

    def __init__(self, app):

        self.app = app
        self.font_manager = app.font_manager
        self._dialog: Optional[tk.Toplevel] = None
        self._tree: Optional[ttk.Treeview] = None
        self._spec_data: Optional[pd.DataFrame] = None

        # Ссылки на метки итогов
        self._power_label: Optional[ttk.Label] = None
        self._weight_label: Optional[ttk.Label] = None
        self._volume_label: Optional[ttk.Label] = None

        # Подсказка для заголовков
        self._header_tooltip: Optional[tk.Toplevel] = None
        self._header_tooltip_label: Optional[tk.Label] = None

        # Переменные для скидок
        self._radiator_discount_var: Optional[tk.StringVar] = None
        self._bracket_discount_var: Optional[tk.StringVar] = None

        # Для редактирования ячейки
        self._edit_entry: Optional[tk.Entry] = None
        self._edit_item: Optional[str] = None

        # Состояние кнопки конвертации: True = в Метеор, False = в LaggarTT
        self._is_meteor_mode: bool = True

        # ========== ДЛЯ КАРТИНОК КРОНШТЕЙНОВ ==========
        self._bracket_image_window: Optional[tk.Toplevel] = None
        self._bracket_image_label: Optional[tk.Label] = None
        self._bracket_photo_image: Optional[tk.PhotoImage] = None
        self._bracket_image_after_id: Optional[str] = None
        self._last_hover_item: Optional[str] = None

        # ========== ЧЕКБОКС ДЛЯ УПРАВЛЕНИЯ КАРТИНКАМИ ==========
        # Загружаем сохранённое значение из settings.json
        # (по умолчанию True, если ключа ещё нет)
        from nextt.config import config
        saved_show_images = config.get("preview_show_images", True)
        self._show_images_var = tk.BooleanVar(value=bool(saved_show_images))

        # ========== ФЛАГ ПЕРЕВОРОТА БЛОКА РАДИАТОРОВ ==========
        self._radiators_reversed = False

        # ========== СЛОВАРЬ СВЯЗЕЙ КРОНШТЕЙН → РАДИАТОРЫ ==========
        self._bracket_to_radiators: Dict[str, List[str]] = {}
        # ========== АРТИКУЛЫ РУЧНЫХ КРОНШТЕЙНОВ ==========
        # Приложение само запоминает, какие кронштейны добавлены вручную
        self._manual_bracket_articles: set = set()

    def show(self, spec_data: pd.DataFrame) -> None:
        """Показывает окно предпросмотра."""
        if self._dialog and self._dialog.winfo_exists():
            self._dialog.lift()
            self._dialog.focus_force()
            return

        if spec_data is None or spec_data.empty:
            messagebox.showwarning("Предпросмотр", "Нет данных для спецификации.")
            return

        self._spec_data = spec_data.copy()
        self._ensure_mount_type_column()
        self._create_dialog()

    def _create_dialog(self) -> None:
        """Создаёт окно предпросмотра."""
        self._dialog = tk.Toplevel(self.app.root)

        # ========== ЯВНАЯ УСТАНОВКА ИКОНКИ ==========
        try:
            from nextt.config import get_resource_path
            icon_path = get_resource_path("icon.ico")
            if icon_path and os.path.exists(icon_path):
                self._dialog.iconbitmap(icon_path)
        except Exception as e:
            logger.debug(f"Не удалось загрузить иконку для окна предпросмотра: {e}")

        from nextt.utils.window_manager import setup_dialog_window, fix_window_buttons_after_geometry
        setup_dialog_window(self._dialog, "Предпросмотр спецификации")

        self._dialog.geometry(get_safe_geometry(self._dialog))
        fix_window_buttons_after_geometry(self._dialog)

        default_font = self.font_manager.get_default_font()
        heading_font = self.font_manager.get_heading_font()
        bold_font = self.font_manager.get_bold_font()

        main_frame = ttk.Frame(self._dialog)
        main_frame.pack(fill="both", expand=True, padx=15, pady=15)

        # --- Таблица ---
        tree_frame = ttk.Frame(main_frame)
        tree_frame.pack(fill="both", expand=True)

        columns = [
            "№", "Артикул", "Наименование", "Мощность, Вт", "Вид монтажа",
            "Цена, руб (с НДС)", "Скидка, %",
            "Цена со скидкой, руб (с НДС)", "Кол-во",
            "Сумма, руб (с НДС)"
        ]
        self._tree = ttk.Treeview(tree_frame, columns=columns, show="headings", height=15)

        col_widths = {
            "№": 50, "Артикул": 100, "Наименование": 370, "Мощность, Вт": 100,
            "Вид монтажа": 110,
            "Цена, руб (с НДС)": 150, "Скидка, %": 80,
            "Цена со скидкой, руб (с НДС)": 250, "Кол-во": 120,
            "Сумма, руб (с НДС)": 150,
        }
        money_cols = {"Цена, руб (с НДС)", "Цена со скидкой, руб (с НДС)", "Сумма, руб (с НДС)"}

        style = ttk.Style()
        style.configure("Treeview.Heading", font=heading_font)

        for col in columns:
            if col == "Артикул":
                self._tree.heading(col, text=col, command=self._copy_articles)
            elif col == "Кол-во":
                self._tree.heading(col, text=col, command=self._copy_quantities)
            elif col == "Наименование":
                self._tree.heading(col, text="Наименование ▼",
                                   command=self._toggle_radiators_order)
            else:
                self._tree.heading(col, text=col)
            anchor = "e" if col in money_cols else ("w" if col == "Наименование" else "center")
            self._tree.column(col, width=col_widths.get(col, 100), anchor=anchor)

        # ========== ТЕГИ С ЯВНЫМ УКАЗАНИЕМ ШРИФТА ==========
        self._tree.tag_configure("radiator", background="#fafafa", font=default_font)
        # ========== НОВЫЙ ТЕГ ДЛЯ ГИГИЕНИЧЕСКИХ РАДИАТОРОВ (ЗЕЛЁНЫЙ ТЕКСТ) ==========
        self._tree.tag_configure("hygiene", background="#fafafa", font=default_font, foreground="#008000")
        self._tree.tag_configure("bracket", background="#ededed", font=default_font)
        self._tree.tag_configure("bracket_hover", background="#c8c8c8", font=bold_font)
        self._tree.tag_configure("total", background="#d9d9d9", font=bold_font)
        # ========== НОВЫЕ ТЕГИ ДЛЯ ПОДСВЕТКИ СВЯЗАННЫХ РАДИАТОРОВ ==========
        self._tree.tag_configure("radiator_related", background="#c8c8c8", font=default_font)
        self._tree.tag_configure("hygiene_related", background="#c8c8c8", font=default_font, foreground="#008000")

        # ========== ТАЙМЕР ДЛЯ ОТСЛЕЖИВАНИЯ КУРСОРА ==========
        def check_hover():
            try:
                if not self._dialog or not self._dialog.winfo_exists():
                    return

                # ========== ИСПРАВЛЕНИЕ: проверяем, что окно в фокусе и активно ==========
                # Если окно свёрнуто, скрыто или не активно — не показываем картинки
                if not self._dialog.winfo_viewable() or self._dialog.state() == 'withdrawn' or self._dialog.state() == 'iconic':
                    self._hide_bracket_image_immediate()
                    if self._dialog and self._dialog.winfo_exists():
                        self._dialog.after(200, check_hover)
                    return

                # Проверяем, что окно имеет фокус (активно)
                if not self._dialog.focus_get():
                    self._hide_bracket_image_immediate()
                    if self._dialog and self._dialog.winfo_exists():
                        self._dialog.after(200, check_hover)
                    return
                # =====================================================================

                # Получаем положение мыши относительно Treeview
                tree_x = self._tree.winfo_rootx()
                tree_y = self._tree.winfo_rooty()
                tree_w = self._tree.winfo_width()
                tree_h = self._tree.winfo_height()

                mouse_x = self._tree.winfo_pointerx()
                mouse_y = self._tree.winfo_pointery()

                # Проверяем, находится ли мышь внутри Treeview
                if (tree_x <= mouse_x <= tree_x + tree_w and
                    tree_y <= mouse_y <= tree_y + tree_h):

                    rel_x = mouse_x - tree_x
                    rel_y = mouse_y - tree_y

                    item = self._tree.identify_row(rel_y)

                    if item != self._last_hover_item:
                        previous_item = self._last_hover_item
                        self._last_hover_item = item

                        if previous_item and previous_item != item:
                            self._unhighlight_bracket_row(previous_item)

                        if item:
                            values = self._tree.item(item, "values")
                            if values and len(values) >= 3:
                                if str(values[2]).startswith("Итого"):
                                    self._hide_bracket_image(50)
                                    self._dialog.after(200, check_hover)
                                    return
                                if "Кронштейн" in str(values[2]):
                                    fake_event = FakeEvent()
                                    fake_event.x_root = mouse_x
                                    fake_event.y_root = mouse_y
                                    fake_event.x = rel_x
                                    fake_event.y = rel_y
                                    self._show_bracket_image(fake_event, item)
                                    self._dialog.after(200, check_hover)
                                    return

                        self._hide_bracket_image(50)
                else:
                    if self._last_hover_item is not None:
                        previous_item = self._last_hover_item
                        self._last_hover_item = None
                        self._unhighlight_bracket_row(previous_item)
                        self._hide_bracket_image(50)
            except Exception as e:
                logger.debug(f"[BRACKET TIMER] Ошибка: {e}")

            try:
                if self._dialog and self._dialog.winfo_exists():
                    self._dialog.after(200, check_hover)
            except:
                pass

        class FakeEvent:
            pass

        self._dialog.after(500, check_hover)

        self._fill_tree()
        self._build_bracket_radiator_links()

        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self._tree.yview)
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal", command=self._tree.xview)
        self._tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self._tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)

        # --- Подсказки ---
        self._header_tooltip = None
        self._tree.bind("<Motion>", self._on_tree_motion)
        self._tree.bind("<Leave>", self._hide_header_tooltip)

        # ========== НОВЫЕ ОБРАБОТЧИКИ ==========
        self._tree.bind("<Double-1>", self._on_double_click)
        self._tree.bind("<Delete>", self._on_delete_key)
        default_font = self.font_manager.get_default_font()
        self._context_menu = tk.Menu(self._tree, tearoff=0, font=default_font)
        self._tree.bind("<Button-3>", self._show_context_menu)

        # --- НИЖНЯЯ ПАНЕЛЬ (ПЕРЕКОМПОНОВАНА) ---
        # ========== СОЗДАЁМ ЕДИНЫЙ ФРЕЙМ С РАМКОЙ ==========
        bottom_frame = tk.Frame(main_frame, relief="solid", borderwidth=1, bg='#dedede')
        bottom_frame.pack(fill="x", pady=10)

        # Внутренний фрейм для содержимого (с отступами)
        inner_frame = tk.Frame(bottom_frame, bg='#dedede')
        inner_frame.pack(fill="x", padx=10, pady=8)

        # ---- ЛЕВЫЙ БЛОК: ИТОГИ ----
        totals_frame = tk.Frame(inner_frame, bg='#dedede')
        totals_frame.pack(side="left", fill="x")

        tp, tw, tv = self.app.spec_generator.calculate_totals(self._spec_data)
        self._power_label = tk.Label(
            totals_frame,
            text=f"Суммарная мощность: {self.app.spec_generator.format_power(tp)}",
            font=bold_font,
            bg='#dedede'
        )
        self._power_label.pack(side="left", padx=15)

        self._weight_label = tk.Label(
            totals_frame,
            text=f"Общий вес: {self.app.spec_generator.format_weight(tw)}",
            font=bold_font,
            bg='#dedede'
        )
        self._weight_label.pack(side="left", padx=15)

        self._volume_label = tk.Label(
            totals_frame,
            text=f"Общий объём: {tv:.5f} м³",
            font=bold_font,
            bg='#dedede'
        )
        self._volume_label.pack(side="left", padx=15)

        # ---- ЦЕНТРАЛЬНЫЙ БЛОК: ЧЕКБОКС ----
        checkbox_frame = tk.Frame(inner_frame, bg='#dedede')
        checkbox_frame.pack(side="left", expand=True, fill="x")

        tk.Checkbutton(
            checkbox_frame,
            text="Подсказка",
            variable=self._show_images_var,
            bg='#dedede',
            font=default_font
        ).pack(pady=5)

        # ---- ПРАВЫЙ БЛОК: СКИДКИ ----
        discount_frame = tk.Frame(inner_frame, bg='#dedede')
        discount_frame.pack(side="right", fill="x")

        tk.Label(discount_frame, text="Скидка на радиаторы, %:", font=default_font, bg='#dedede').pack(
            side="left", padx=(0, 2), pady=3
        )
        self._radiator_discount_var = tk.StringVar(
            value=self.app.main_window.radiator_discount_var.get()
        )
        rad_entry = tk.Entry(
            discount_frame,
            textvariable=self._radiator_discount_var,
            width=5,
            font=default_font,
            validate="key",
            validatecommand=(discount_frame.register(self._validate_discount), '%P'),
            bg='white'
        )
        rad_entry.pack(side="left", padx=2, pady=3)
        self._radiator_discount_var.trace_add("write", self._on_discount_changed)

        tk.Label(discount_frame, text="кронштейны, %:", font=default_font, bg='#dedede').pack(
            side="left", padx=(10, 2), pady=3
        )
        self._bracket_discount_var = tk.StringVar(
            value=self.app.main_window.bracket_discount_var.get()
        )
        br_entry = tk.Entry(
            discount_frame,
            textvariable=self._bracket_discount_var,
            width=5,
            font=default_font,
            validate="key",
            validatecommand=(discount_frame.register(self._validate_discount), '%P'),
            bg='white'
        )
        br_entry.pack(side="left", padx=2, pady=3)
        self._bracket_discount_var.trace_add("write", self._on_discount_changed)

        # ========== НИЖНЯЯ ПАНЕЛЬ С КНОПКАМИ ==========
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill="x", pady=10)

        # ========== ЛЕВЫЙ БЛОК (Добавить кронштейн + Конв-ть в Метеор/LaggarTT) ==========
        add_frame = ttk.Frame(btn_frame)
        add_frame.pack(side="left", fill="x", expand=True)

        brackets_list = self.app.data_provider.get_brackets_list()
        if brackets_list:
            ttk.Label(add_frame, text="Добавить кронштейн:", font=default_font).pack(side="left", padx=5)
            bracket_names = [b['name'] for b in brackets_list]
            self._bracket_combo = ttk.Combobox(
                add_frame, values=bracket_names, state="readonly", width=40
            )
            self._bracket_combo.pack(side="left", padx=5)
            if bracket_names:
                self._bracket_combo.current(0)
            ttk.Label(add_frame, text="Количество:", font=default_font).pack(side="left", padx=5)
            self._qty_entry = ttk.Entry(add_frame, width=5, font=default_font)
            self._qty_entry.pack(side="left", padx=5)
            ttk.Button(add_frame, text="Добавить",
                       command=self._add_bracket).pack(side="left", padx=5)

        # ========== НОВАЯ КНОПКА "Конв-ть в Метеор" / "Конв-ть в LaggarTT" ==========
        self._convert_btn_frame = tk.Frame(add_frame, bg='#7E1A2F', relief='raised', borderwidth=2)
        self._convert_btn_frame.pack(side="left", padx=5)

        self._convert_btn = tk.Label(
            self._convert_btn_frame,
            text="Конвертировать в Метеор",
            font=default_font,
            bg='#7E1A2F',
            fg='white',
            padx=10,
            pady=3,
            cursor='hand2'
        )
        self._convert_btn.pack()

        self._convert_btn_frame.bind("<Enter>", self._on_enter_convert_button)
        self._convert_btn.bind("<Enter>", self._on_enter_convert_button)
        self._convert_btn_frame.bind("<Leave>", self._on_leave_convert_button)
        self._convert_btn.bind("<Leave>", self._on_leave_convert_button)
        self._convert_btn_frame.bind("<Button-1>", lambda e: self._convert_to_meteor())
        self._convert_btn.bind("<Button-1>", lambda e: self._convert_to_meteor())

        # ========== ПРАВЫЙ БЛОК ==========
        ttk.Button(btn_frame, text="Закрыть",
                   command=self._close).pack(side="right", padx=5)

        ttk.Button(btn_frame, text="Экспорт в Excel",
                   command=self._export).pack(side="right", padx=5)

        ttk.Button(btn_frame, text="Назад к подбору аналогов",
                   command=self._back_to_correspondence).pack(side="right", padx=5)

        ttk.Button(btn_frame, text="Назад к выбору столбцов",
                   command=self._back_to_column_selector).pack(side="right", padx=5)

        # ========== ГОРЯЧАЯ КЛАВИША ==========
        self._dialog.bind("<Control-Shift-C>", lambda e: self._change_connection())

        self._dialog.protocol("WM_DELETE_WINDOW", self._close)

    def _toggle_radiators_order(self) -> None:
        """
        Переключает порядок отображения блока радиаторов.
        Кронштейны и строка «Итого» остаются на своих местах.
        """
        self._radiators_reversed = not self._radiators_reversed

        if self._radiators_reversed:
            self._tree.heading("Наименование", text="Наименование ▲")
        else:
            self._tree.heading("Наименование", text="Наименование ▼")

        self._fill_tree()

    # ==================================================================
    # ПОДСВЕТКА СТРОКИ КРОНШТЕЙНА
    # ==================================================================

    def _highlight_bracket_row(self, item: str) -> None:
        """Делает шрифт строки жирным и подсвечивает связанные радиаторы (ТОЛЬКО для кронштейнов)."""
        try:
            if not self._tree or not self._tree.winfo_exists():
                return
            values = self._tree.item(item, "values")
            if not values or len(values) < 3:
                return
            # Проверяем «Итого» по столбцу «Наименование»
            if str(values[2]).startswith("Итого"):
                return
            if "Кронштейн" not in str(values[2]):
                return

            self._tree.item(item, tags=("bracket_hover",))
            self._tree.item(item, values=values)

            # ========== ПОДСВЕТКА СВЯЗАННЫХ РАДИАТОРОВ ==========
            art_bracket = str(values[1]).strip() if len(values) > 1 else ""
            if art_bracket:
                self._highlight_related_radiators(art_bracket)

        except (tk.TclError, Exception) as e:
            logger.debug(f"Ошибка подсветки строки: {e}")

    def _unhighlight_bracket_row(self, item: str) -> None:
        """Возвращает обычный шрифт и снимает подсветку с радиаторов (ТОЛЬКО для кронштейнов)."""
        try:
            if not self._tree or not self._tree.winfo_exists():
                return
            values = self._tree.item(item, "values")
            if not values or len(values) < 3:
                return
            # Проверяем «Итого» по столбцу «Наименование»
            if str(values[2]).startswith("Итого"):
                return
            if "Кронштейн" not in str(values[2]):
                return

            self._tree.item(item, tags=("bracket",))
            self._tree.item(item, values=values)

            # ========== СНЯТИЕ ПОДСВЕТКИ С РАДИАТОРОВ ==========
            self._unhighlight_related_radiators()

        except (tk.TclError, Exception) as e:
            logger.debug(f"Ошибка снятия подсветки: {e}")

    def _get_radiator_tag(self, item: str) -> str:
        """
        Возвращает исходный тег для строки радиатора:
        'radiator' — обычный, 'hygiene' — гигиенический.
        Используется при снятии подсветки.
        """
        try:
            values = self._tree.item(item, "values")
            if not values or len(values) < 3:
                return "radiator"

            # Проверяем по названию
            name = str(values[2])
            name_lower = name.lower()
            if any(kw in name_lower for kw in ['ventil hygiene (hv)', 'hygiene (h)']):
                return "hygiene"

            # Проверяем по артикулу через базу
            art = str(values[1]).strip() if len(values) > 1 else ""
            if art and art.startswith("7724"):
                # Конвертируем Метеор → LaggarTT для поиска
                art_for_search = art
                if len(art) >= 5 and art[4] == '6':
                    art_for_search = art[:4] + '7' + art[5:]

                found = self.app.data_provider.find_by_article(art_for_search)
                if found is not None:
                    conn = str(found.get('Connection', ''))
                    if conn in ['HV-правое', 'HV-левое', 'H-боковое']:
                        return "hygiene"
        except Exception:
            pass
        return "radiator"

    def _highlight_related_radiators(self, art_bracket: str) -> None:
        """Подсвечивает строки радиаторов, для которых подобран указанный кронштейн."""
        try:
            if not self._tree or not self._tree.winfo_exists():
                return

            related_articles = self._bracket_to_radiators.get(art_bracket, [])
            if not related_articles:
                return

            related_set = set(related_articles)

            for item in self._tree.get_children():
                values = self._tree.item(item, "values")
                if not values or len(values) < 3:
                    continue

                name = str(values[2])
                # Пропускаем кронштейны и итоговую строку
                if "Кронштейн" in name or name.startswith("Итого"):
                    continue

                art_rad = str(values[1]).strip() if len(values) > 1 else ""
                if art_rad not in related_set:
                    continue

                # Определяем, гигиенический ли это радиатор
                base_tag = self._get_radiator_tag(item)
                if base_tag == "hygiene":
                    self._tree.item(item, tags=("hygiene_related",))
                else:
                    self._tree.item(item, tags=("radiator_related",))
                self._tree.item(item, values=values)

        except (tk.TclError, Exception) as e:
            logger.debug(f"Ошибка подсветки связанных радиаторов: {e}")

    def _unhighlight_related_radiators(self) -> None:
        """Снимает подсветку со всех радиаторов, возвращая им исходные теги."""
        try:
            if not self._tree or not self._tree.winfo_exists():
                return

            for item in self._tree.get_children():
                values = self._tree.item(item, "values")
                if not values or len(values) < 3:
                    continue

                name = str(values[2])
                # Пропускаем кронштейны и итоговую строку
                if "Кронштейн" in name or name.startswith("Итого"):
                    continue

                base_tag = self._get_radiator_tag(item)
                self._tree.item(item, tags=(base_tag,))
                self._tree.item(item, values=values)

        except (tk.TclError, Exception) as e:
            logger.debug(f"Ошибка снятия подсветки с радиаторов: {e}")

    # ==================================================================
    # ОБРАБОТЧИКИ ДЛЯ КНОПКИ "Конв-ть в Метеор" / "Конв-ть в LaggarTT"
    # ==================================================================

    def _update_convert_button_state(self) -> None:
        """Обновляет внешний вид кнопки в зависимости от текущего состояния."""
        if hasattr(self, '_convert_btn') and hasattr(self, '_convert_btn_frame'):
            if self._is_meteor_mode:
                self._convert_btn.config(text="Конвертировать в Метеор", bg='#7E1A2F', fg='white')
                self._convert_btn_frame.config(bg='#7E1A2F')
            else:
                self._convert_btn.config(text="Конвертировать в LaggarTT", bg='#263168', fg='white')
                self._convert_btn_frame.config(bg='#263168')

    def _on_enter_convert_button(self, event) -> None:
        if hasattr(self, '_convert_btn_frame') and self._convert_btn_frame:
            if self._is_meteor_mode:
                self._convert_btn_frame.config(bg='#263168')
            else:
                self._convert_btn_frame.config(bg='#7E1A2F')
        if hasattr(self, '_convert_btn') and self._convert_btn:
            if self._is_meteor_mode:
                self._convert_btn.config(bg='#263168')
            else:
                self._convert_btn.config(bg='#7E1A2F')

    def _on_leave_convert_button(self, event) -> None:
        if hasattr(self, '_convert_btn_frame') and self._convert_btn_frame:
            if self._is_meteor_mode:
                self._convert_btn_frame.config(bg='#7E1A2F')
            else:
                self._convert_btn_frame.config(bg='#263168')
        if hasattr(self, '_convert_btn') and self._convert_btn:
            if self._is_meteor_mode:
                self._convert_btn.config(bg='#7E1A2F')
            else:
                self._convert_btn.config(bg='#263168')

    def _ensure_mount_type_column(self) -> None:
        """Гарантирует, что в _spec_data есть столбец «Тип монтажа»."""
        if self._spec_data is None or self._spec_data.empty:
            return
        if "Тип монтажа" in self._spec_data.columns:
            return

        # Определяем значение по умолчанию из главного окна
        current = self.app.main_window.bracket_var.get()
        if current == "Настенные кронштейны":
            default_value = "настенный"
        elif current == "Напольные кронштейны":
            default_value = "напольный"
        else:
            default_value = "без"

        self._spec_data["Тип монтажа"] = default_value

        # У кронштейнов — пусто
        mask_brackets = self._spec_data['Наименование'].str.contains('Кронштейн', na=False)
        self._spec_data.loc[mask_brackets, "Тип монтажа"] = ""

    def _get_bracket_type_for_radiator(self, row) -> str:
        """
        Возвращает тип кронштейнов («Настенные кронштейны» / «Напольные кронштейны» /
        «Без кронштейнов») для конкретной строки радиатора.
        """
        mount = str(row.get("Тип монтажа", "")).strip().lower()
        if mount == "настенный":
            return "Настенные кронштейны"
        elif mount == "напольный":
            return "Напольные кронштейны"
        elif mount == "без":
            return "Без кронштейнов"
        else:
            # Fallback: берём из главного окна
            return self.app.main_window.bracket_var.get()

    def _extract_manual_brackets(self):
        """Извлекает из _spec_data ручные кронштейны (по списку артикулов)."""
        if self._spec_data is None or self._spec_data.empty:
            return None
        if not self._manual_bracket_articles:
            return None

        mask = (
            self._spec_data['Наименование'].str.contains('Кронштейн', na=False) &
            self._spec_data['Артикул'].astype(str).str.strip().isin(self._manual_bracket_articles)
        )
        manual = self._spec_data[mask].copy()
        if manual.empty:
            return None
        return manual

    def _restore_manual_brackets(self, manual_brackets) -> None:
        """Возвращает ручные кронштейны в _spec_data и пересчитывает их связи."""
        if manual_brackets is None or manual_brackets.empty:
            return

        # Добавляем ручные кронштейны в конец _spec_data
        self._spec_data = pd.concat([self._spec_data, manual_brackets], ignore_index=True)

        # Пересчитываем связи ручных кронштейнов по текущим радиаторам
        bracket_type_from_main = self.app.main_window.bracket_var.get()

        for art_bracket in self._manual_bracket_articles:
            # Определяем тип монтажа по базе
            bracket_df = self.app.data_provider.brackets_df
            mask_b = bracket_df['Артикул'].astype(str).str.strip() == str(art_bracket).strip()
            if not mask_b.any():
                continue
            b_info = bracket_df[mask_b].iloc[0]
            bracket_mount = str(b_info.get('Тип монтажа', '')).strip().lower()

            if 'настен' in bracket_mount:
                bracket_type_for_calc = "Настенные кронштейны"
            elif 'напольн' in bracket_mount:
                bracket_type_for_calc = "Напольные кронштейны"
            else:
                bracket_type_for_calc = bracket_type_from_main

            matching = []
            for _, row in self._spec_data.iterrows():
                row_name = str(row.get('Наименование', ''))
                if "Кронштейн" in row_name:
                    continue
                art_rad = str(row.get('Артикул', '')).strip()
                if not art_rad or not art_rad.startswith("7724"):
                    continue

                rad_type = None
                height = None
                length = None
                connection = None

                art_for_search = art_rad
                if len(art_rad) >= 5 and art_rad[4] == '6':
                    art_for_search = art_rad[:4] + '7' + art_rad[5:]

                found = self.app.data_provider.find_by_article(art_for_search)
                if found is not None:
                    connection = str(found.get('Connection', ''))
                    rad_type = str(found.get('RadiatorType', ''))
                    size_match = re.search(r'/(\d{3,4})/(\d{3,4})', row_name)
                    if size_match:
                        height = int(size_match.group(1))
                        length = int(size_match.group(2))

                if rad_type is None:
                    type_match = re.search(r'/(\d{2})/', row_name)
                    if type_match:
                        rad_type = type_match.group(1)
                if height is None:
                    height_match = re.search(r'/(\d{3,4})/', row_name)
                    if height_match:
                        height = int(height_match.group(1))
                if length is None:
                    length_match = re.search(r'/(\d{3,4})$', row_name)
                    if length_match:
                        length = int(length_match.group(1))
                if connection is None:
                    name_lower = row_name.lower()
                    if 'ventil hygiene (hv)' in name_lower:
                        connection = 'HV-левое' if (' la' in name_lower or name_lower.endswith(' la')) else 'HV-правое'
                    elif 'hygiene (h)' in name_lower:
                        connection = 'H-боковое'
                    elif 'vk-profil' in name_lower:
                        connection = 'VK-левое' if (' la' in name_lower or name_lower.endswith(' la')) else 'VK-правое'
                    elif 'k-profil' in name_lower:
                        connection = 'K-боковое'
                    else:
                        connection = 'VK-правое'

                if rad_type in ['20', '21', '22'] and connection in ['VK-левое', 'HV-левое']:
                    connection = 'HV-правое' if 'HV' in connection else 'VK-правое'

                if not (rad_type and height and length and connection):
                    continue

                from nextt.core.brackets import BracketsCalculator
                brackets_for_rad = BracketsCalculator.calculate_for_manual(
                    radiator_type=rad_type,
                    length=length,
                    height=height,
                    bracket_type=bracket_type_for_calc,
                    connection=connection,
                    quantity=1,
                )
                for art_candidate, _ in brackets_for_rad:
                    if art_candidate == art_bracket:
                        if art_rad not in matching:
                            matching.append(art_rad)
                        break

            if matching:
                self._bracket_to_radiators[art_bracket] = matching
            else:
                self._bracket_to_radiators.pop(art_bracket, None)

    def _convert_to_meteor(self) -> None:
        if self._spec_data is None or self._spec_data.empty:
            return

        manual_brackets = self._extract_manual_brackets()

        converted_count = 0

        for idx in self._spec_data.index:
            row = self._spec_data.loc[idx]
            if "Кронштейн" in str(row.get("Наименование", "")):
                continue

            art = str(row.get("Артикул", "")).strip()
            if len(art) != 10 or not art.isdigit():
                continue

            if self._is_meteor_mode:
                if art[4] != '7':
                    continue
                meteor_art = art[:4] + '6' + art[5:]
                meteor_data = self.app.data_provider.find_meteor_by_article(meteor_art)
                if meteor_data is None:
                    continue
                meteor_name = str(meteor_data.get('Наименование', ''))
                self._spec_data.at[idx, 'Артикул'] = meteor_art
                self._spec_data.at[idx, 'Наименование'] = meteor_name
                converted_count += 1
            else:
                if art[4] != '6':
                    continue
                laggar_art = art[:4] + '7' + art[5:]
                laggar_data = self.app.data_provider.find_by_article(laggar_art)
                if laggar_data is None:
                    continue
                laggar_name = str(laggar_data.get('Наименование', ''))
                self._spec_data.at[idx, 'Артикул'] = laggar_art
                self._spec_data.at[idx, 'Наименование'] = laggar_name
                converted_count += 1

        if converted_count > 0:
            self._is_meteor_mode = not self._is_meteor_mode
            self._update_convert_button_state()
            # ========== УДАЛЯЕМ СТАРЫЕ КРОНШТЕЙНЫ ПЕРЕД ПЕРЕСЧЁТОМ ==========
            if self._spec_data is not None and not self._spec_data.empty:
                self._spec_data = self._spec_data[
                    ~self._spec_data['Наименование'].str.contains('Кронштейн', na=False)
                ]
            # =================================================================
            # Пересчитываем кронштейны после конвертации
            self._recalculate_all_brackets()
            self._restore_manual_brackets(manual_brackets)
            self._fill_tree()
            self._update_totals()

    # ==================================================================
    # РЕДАКТИРОВАНИЕ КОЛИЧЕСТВА КРОНШТЕЙНОВ
    # ==================================================================

    def _on_double_click(self, event) -> None:
        region = self._tree.identify("region", event.x, event.y)
        if region != "cell":
            return

        column = self._tree.identify_column(event.x)
        item = self._tree.identify_row(event.y)

        if not item or not column:
            return

        if column != "#9":
            return

        values = self._tree.item(item, "values")
        if not values or len(values) < 3:
            return

        name = values[2] if len(values) > 2 else ""
        # Проверяем «Итого» по столбцу «Наименование»
        if str(name).startswith("Итого") or "Кронштейн" not in name:
            return

        current_qty = values[8] if len(values) > 8 else "0"

        x, y, width, height = self._tree.bbox(item, column)

        self._edit_entry = tk.Entry(self._tree, font=self.font_manager.get_default_font())
        self._edit_entry.insert(0, str(current_qty))
        self._edit_entry.place(x=x, y=y, width=width, height=height)
        self._edit_entry.focus_set()
        self._edit_entry.select_range(0, tk.END)

        self._edit_item = item

        self._edit_entry.bind("<Return>", self._finish_editing)
        self._edit_entry.bind("<FocusOut>", self._finish_editing)
        self._edit_entry.bind("<Escape>", self._cancel_editing)

    def _finish_editing(self, event=None) -> None:
        if not self._edit_entry or not self._edit_item:
            return

        try:
            new_qty_str = self._edit_entry.get().strip()
            if not new_qty_str:
                new_qty_str = "0"

            try:
                new_qty = int(float(new_qty_str.replace(',', '.')))
                if new_qty < 0:
                    new_qty = 0
            except ValueError:
                new_qty = 0

            values = list(self._tree.item(self._edit_item, "values"))
            if len(values) < 10:
                return

            old_qty = int(values[8]) if values[8] else 0
            if old_qty == new_qty:
                return

            values[8] = str(new_qty)

            try:
                price_disc = float(values[7].replace(',', '.').replace(' ', '')) if values[7] else 0.0
                new_total = round(price_disc * new_qty, 2)
                values[9] = f"{new_total:,.2f}".replace(',', ' ') + "   "
            except (ValueError, TypeError):
                pass

            self._tree.item(self._edit_item, values=values)

            art = values[1] if len(values) > 1 else ""
            name = values[2] if len(values) > 2 else ""

            for idx in self._spec_data.index:
                if (str(self._spec_data.at[idx, "Артикул"]) == str(art) and
                    str(self._spec_data.at[idx, "Наименование"]) == str(name)):
                    self._spec_data.at[idx, "Кол-во"] = new_qty
                    self._spec_data.at[idx, "Сумма, руб (с НДС)"] = new_total
                    break

            self._recalculate_table()

        except Exception as e:
            logger.error(f"Ошибка при редактировании: {e}")

        finally:
            if self._edit_entry:
                self._edit_entry.destroy()
                self._edit_entry = None
            self._edit_item = None

    def _cancel_editing(self, event=None) -> None:
        if self._edit_entry:
            self._edit_entry.destroy()
            self._edit_entry = None
        self._edit_item = None

    # ==================================================================
    # УДАЛЕНИЕ СТРОКИ
    # ==================================================================

    def _on_delete_key(self, event=None) -> None:
        self._delete_selected_row()

    def _show_context_menu(self, event) -> None:
        """Показывает контекстное меню с возможностью переключения на гигиенические радиаторы."""
        item = self._tree.identify_row(event.y)
        if not item:
            return

        values = self._tree.item(item, "values")
        if not values:
            return

        if len(values) > 2 and str(values[2]).startswith("Итого"):
            return

        current_selection = self._tree.selection()

        if item not in current_selection:
            new_selection = list(current_selection) + [item]
            self._tree.selection_set(new_selection)

        self._context_menu.delete(0, tk.END)

        has_radiators = False
        has_brackets = False
        has_hygiene_toggle = False
        selected_items_data = []

        for sel_item in self._tree.selection():
            sel_values = self._tree.item(sel_item, "values")
            if sel_values and len(sel_values) >= 3:
                sel_name = sel_values[2] if len(sel_values) > 2 else ""
                if "Кронштейн" in str(sel_name):
                    has_brackets = True
                else:
                    has_radiators = True
                    # Собираем данные для переключения гигиены
                    art = sel_values[1].strip() if len(sel_values) > 1 else ""
                    # ========== ИСПРАВЛЕНИЕ 4: ПРОВЕРЯЕМ И 10, И 11 ЗНАКОВ ==========
                    # Артикулы 30 типа имеют 11 знаков (77247...30... или 77246...30...)
                    # Артикулы других типов имеют 10 знаков
                    if art.startswith("7724") and len(art) >= 10:
                        # Находим радиатор в базе
                        found = self.app.data_provider.find_by_article(art)
                        if found is not None:
                            conn = str(found.get('Connection', ''))
                            rad_type = str(found.get('RadiatorType', ''))
                            # Только для типов 10, 20, 30
                            if rad_type in ['10', '20', '30']:
                                # Определяем, гигиенический ли это радиатор
                                is_hygiene = conn in ['HV-правое', 'HV-левое', 'H-боковое']
                                selected_items_data.append({
                                    'item': sel_item,
                                    'article': art,
                                    'name': sel_name,
                                    'connection': conn,
                                    'rad_type': rad_type,
                                    'is_hygiene': is_hygiene,
                                    'values': sel_values
                                })
                                has_hygiene_toggle = True

        if has_radiators:
            self._context_menu.add_command(label="🔄 Сменить подключение", command=self._change_connection)

            # ========== НОВЫЙ ПУНКТ: СМЕНА ТИПА МОНТАЖА ==========
            self._context_menu.add_command(
                label="🔄 Сменить тип монтажа (настенный ↔ напольный)",
                command=self._toggle_bracket_type
            )
            # ====================================================
        # ========== НОВЫЙ ПУНКТ: ПЕРЕКЛЮЧЕНИЕ ГИГИЕНЫ ==========
        if has_hygiene_toggle and selected_items_data:
            # Проверяем, все ли выделенные радиаторы имеют одинаковый статус (все гигиенические или все обычные)
            all_hygiene = all(d['is_hygiene'] for d in selected_items_data)
            all_normal = all(not d['is_hygiene'] for d in selected_items_data)

            if all_hygiene:
                self._context_menu.add_command(
                    label="🔄 Сменить на Classic",
                    command=lambda: self._toggle_hygiene(selected_items_data, to_hygiene=False)
                )
            elif all_normal:
                self._context_menu.add_command(
                    label="🔄 Сменить на Hygiene",
                    command=lambda: self._toggle_hygiene(selected_items_data, to_hygiene=True)
                )
            else:
                # Смешанные типы — показываем оба пункта
                self._context_menu.add_command(
                    label="🔄 Сменить на Hygiene",
                    command=lambda: self._toggle_hygiene(selected_items_data, to_hygiene=True)
                )
                self._context_menu.add_command(
                    label="🔄 Сменить на Classic",
                    command=lambda: self._toggle_hygiene(selected_items_data, to_hygiene=False)
                )

        if has_brackets:
            if has_radiators:
                self._context_menu.add_separator()
            self._context_menu.add_command(label="🗑️ Удалить строку", command=self._delete_selected_row)

        if not has_radiators and not has_brackets:
            return

        self._context_menu.post(event.x_root, event.y_root)

    def _toggle_hygiene(self, items_data: list, to_hygiene: bool) -> None:
        """
        Переключает радиаторы между обычными и гигиеническими.
        При переключении:
        1. Заменяет радиаторы на новые (гигиенические или обычные)
        2. Удаляет ВСЕ кронштейны
        3. Пересчитывает кронштейны заново для всех радиаторов

        Args:
            items_data: список словарей с данными радиаторов
            to_hygiene: True — переключить на гигиенические, False — на обычные
        """
        if not items_data:
            return

        manual_brackets = self._extract_manual_brackets()

        # Маппинг подключений для переключения
        if to_hygiene:
            # Обычный → Гигиенический
            connection_map = {
                'VK-правое': 'HV-правое',
                'VK-левое': 'HV-левое',
                'K-боковое': 'H-боковое',
            }
        else:
            # Гигиенический → Обычный
            connection_map = {
                'HV-правое': 'VK-правое',
                'HV-левое': 'VK-левое',
                'H-боковое': 'K-боковое',
            }

        changed_count = 0
        skipped_count = 0

        # ================================================================
        # ШАГ 1: Заменяем радиаторы на новые
        # ================================================================
        for data in items_data:
            old_connection = data['connection']
            rad_type = data['rad_type']
            old_art = data['article']
            old_name = data['name']
            item = data['item']

            # Проверяем, есть ли маппинг для этого подключения
            if old_connection not in connection_map:
                skipped_count += 1
                continue

            new_connection = connection_map[old_connection]

            # Получаем высоту и длину из названия
            height = None
            length = None

            # Ищем размеры в названии: /300/400, /500/800, и т.д.
            size_match = re.search(r'/(\d{3,4})/(\d{3,4})', old_name)
            if size_match:
                height = int(size_match.group(1))
                length = int(size_match.group(2))
            else:
                # Пробуем другие форматы: 300x400, 300-400
                size_match2 = re.search(r'(\d{3,4})[xх\-](\d{3,4})', old_name)
                if size_match2:
                    height = int(size_match2.group(1))
                    length = int(size_match2.group(2))

            if height is None or length is None:
                skipped_count += 1
                continue

            # Ищем аналог с новым подключением
            art, name = self.app.data_provider.find_analog(new_connection, rad_type, height, length)

            if not art:
                skipped_count += 1
                continue

            # Обновляем данные в _spec_data
            for idx in self._spec_data.index:
                if (str(self._spec_data.at[idx, "Артикул"]) == old_art and
                    str(self._spec_data.at[idx, "Наименование"]) == old_name):
                    self._spec_data.at[idx, "Артикул"] = art
                    self._spec_data.at[idx, "Наименование"] = name
                    break

            # Обновляем дерево
            values = list(self._tree.item(item, "values"))
            values[1] = art
            values[2] = name
            self._tree.item(item, values=values)

            changed_count += 1

        if changed_count == 0:
            messagebox.showwarning(
                "Переключение гигиены",
                "Не удалось найти аналоги для выбранных радиаторов."
            )
            return

        # ================================================================
        # ШАГ 2: Удаляем ВСЕ кронштейны из _spec_data
        # ================================================================
        if self._spec_data is not None and not self._spec_data.empty:
            # Сохраняем только строки без "Кронштейн" в названии
            self._spec_data = self._spec_data[
                ~self._spec_data['Наименование'].str.contains('Кронштейн', na=False)
            ]
            logger.info(f"Кронштейны удалены, осталось радиаторов: {len(self._spec_data)}")

        # ================================================================
        # ШАГ 3: Пересчитываем кронштейны заново для всех радиаторов
        # ================================================================
        self._recalculate_all_brackets()
        self._restore_manual_brackets(manual_brackets)

        # ================================================================
        # ШАГ 4: Обновляем дерево и итоги
        # ================================================================
        self._fill_tree()
        self._recalculate_table()
        self._update_totals()

        # ========== ИСПРАВЛЕНИЕ: УБИРАЕМ ОКНО УСПЕХА ==========
        # Показываем предупреждение только если были пропущены строки
        if skipped_count > 0:
            messagebox.showwarning(
                "Переключение гигиены",
                f"Обновлено: {changed_count} радиаторов\n"
                f"Пропущено (не найдены аналоги): {skipped_count}"
            )
        # Если всё успешно — ничего не показываем
    def _recalculate_all_brackets(self) -> None:
        """
        Пересчитывает кронштейны для всех радиаторов в _spec_data.
        Использует индивидуальный тип монтажа для каждого радиатора.
        Также строит словарь связей кронштейн → радиаторы.
        """
        if self._spec_data is None or self._spec_data.empty:
            return

        # Убеждаемся, что столбец «Тип монтажа» есть
        self._ensure_mount_type_column()

        # Получаем скидку на кронштейны
        try:
            br_disc = float(self.app.main_window.bracket_discount_var.get() or 0)
        except:
            br_disc = 0.0
        br_disc = max(0.0, min(100.0, br_disc))

        # Проходим по всем радиаторам и собираем данные для расчёта кронштейнов
        bracket_items = []
        bracket_to_radiators: Dict[str, List[str]] = {}

        for idx, row in self._spec_data.iterrows():
            name = str(row.get('Наименование', ''))

            if "Кронштейн" in name:
                continue

            # Индивидуальный тип монтажа для этого радиатора
            bracket_type = self._get_bracket_type_for_radiator(row)

            if bracket_type == "Без кронштейнов":
                continue

            # Извлекаем параметры из названия
            rad_type = None
            height = None
            length = None
            connection = None

            art = str(row.get('Артикул', '')).strip()
            if art and len(art) >= 10 and art.startswith('7724'):
                art_for_search = art
                if len(art) >= 5 and art[4] == '6':
                    art_for_search = art[:4] + '7' + art[5:]

                found = self.app.data_provider.find_by_article(art_for_search)
                if found is not None:
                    connection = str(found.get('Connection', ''))
                    rad_type = str(found.get('RadiatorType', ''))
                    size_match = re.search(r'/(\d{3,4})/(\d{3,4})', name)
                    if size_match:
                        height = int(size_match.group(1))
                        length = int(size_match.group(2))

            if rad_type is None:
                type_match = re.search(r'/(\d{2})/', name)
                if type_match:
                    rad_type = type_match.group(1)

            if height is None:
                height_match = re.search(r'/(\d{3,4})/', name)
                if height_match:
                    height = int(height_match.group(1))

            if length is None:
                length_match = re.search(r'/(\d{3,4})$', name)
                if length_match:
                    length = int(length_match.group(1))

            if connection is None:
                name_lower = name.lower()
                if 'ventil hygiene (hv)' in name_lower:
                    if ' la' in name_lower or ' l ' in name_lower or name_lower.endswith(' la'):
                        connection = 'HV-левое'
                    else:
                        connection = 'HV-правое'
                elif 'hygiene (h)' in name_lower:
                    connection = 'H-боковое'
                elif 'vk-profil' in name_lower:
                    if ' la' in name_lower or ' l ' in name_lower or name_lower.endswith(' la'):
                        connection = 'VK-левое'
                    else:
                        connection = 'VK-правое'
                elif 'k-profil' in name_lower:
                    connection = 'K-боковое'
                else:
                    if 'k-profil' in name_lower or 'боков' in name_lower:
                        connection = 'K-боковое'
                    elif 'vk' in name_lower or 'нижн' in name_lower or 'донн' in name_lower:
                        if 'левое' in name_lower or 'лев ' in name_lower or ' l ' in name_lower:
                            connection = 'VK-левое'
                        else:
                            connection = 'VK-правое'
                    else:
                        connection = 'VK-правое'

            # Корректировка универсальных типов
            if rad_type in ['20', '21', '22'] and connection in ['VK-левое', 'HV-левое']:
                if 'HV' in connection:
                    connection = 'HV-правое'
                else:
                    connection = 'VK-правое'

            if rad_type and height and length and connection:
                qty = int(row.get('Кол-во', 0))
                if qty > 0:
                    bracket_items.append({
                        'rad_type': rad_type,
                        'height': height,
                        'length': length,
                        'connection': connection,
                        'qty': qty,
                        'bracket_type': bracket_type,
                    })

                    single_brackets = BracketsCalculator.calculate(
                        radiator_type=rad_type,
                        length=length,
                        height=height,
                        bracket_type=bracket_type,
                        connection=connection,
                        quantity=qty,
                    )
                    for art_bracket, _ in single_brackets:
                        if art_bracket not in bracket_to_radiators:
                            bracket_to_radiators[art_bracket] = []
                        if art not in bracket_to_radiators[art_bracket]:
                            bracket_to_radiators[art_bracket].append(art)

        # Сохраняем словарь связей
        self._bracket_to_radiators = bracket_to_radiators

        if not bracket_items:
            return

        # Суммируем кронштейны вручную (по каждому радиатору отдельно)
        totals: Dict[str, int] = {}
        for item in bracket_items:
            single_brackets = BracketsCalculator.calculate(
                radiator_type=item['rad_type'],
                length=item['length'],
                height=item['height'],
                bracket_type=item['bracket_type'],
                connection=item['connection'],
                quantity=item['qty'],
            )
            for art_bracket, qty_bracket in single_brackets:
                if art_bracket not in totals:
                    totals[art_bracket] = 0
                totals[art_bracket] += qty_bracket

        if not totals:
            return

        # Добавляем кронштейны в _spec_data
        next_num = self._spec_data["№"].max() + 1 if "№" in self._spec_data.columns else len(self._spec_data) + 1

        bracket_rows = []
        for art_bracket, qty in totals.items():
            if qty <= 0:
                continue

            bracket_info = self.app.data_provider.find_bracket_by_article(art_bracket)
            if bracket_info is None:
                continue

            name_bracket = str(bracket_info.get('Наименование', ''))
            price = float(bracket_info.get('Цена, руб', 0))

            disc_price = round(price * (1 - br_disc / 100), 2)
            total = round(disc_price * qty, 2)

            bracket_rows.append({
                "№": next_num,
                "Артикул": art_bracket,
                "Наименование": name_bracket,
                "Мощность, Вт": 0.0,
                "Тип монтажа": "",  # у кронштейнов пусто
                "Цена, руб (с НДС)": price,
                "Скидка, %": br_disc,
                "Цена со скидкой, руб (с НДС)": disc_price,
                "Кол-во": qty,
                "Сумма, руб (с НДС)": total,
            })
            next_num += 1

        if bracket_rows:
            brackets_df = pd.DataFrame(bracket_rows)
            self._spec_data = pd.concat([self._spec_data, brackets_df], ignore_index=True)
            logger.info(f"Добавлено кронштейнов: {len(bracket_rows)}")

    def _build_bracket_radiator_links(self) -> None:
        """
        Строит словарь связей кронштейн → радиаторы.
        Использует индивидуальный тип монтажа для каждого радиатора.
        НЕ изменяет _spec_data.
        """
        if self._spec_data is None or self._spec_data.empty:
            self._bracket_to_radiators = {}
            return

        # Убеждаемся, что столбец «Тип монтажа» есть
        self._ensure_mount_type_column()

        # Собираем множество существующих артикулов кронштейнов
        existing_bracket_articles = set()
        for _, row in self._spec_data.iterrows():
            name = str(row.get('Наименование', ''))
            if "Кронштейн" in name:
                art_bracket = str(row.get('Артикул', '')).strip()
                if art_bracket:
                    existing_bracket_articles.add(art_bracket)

        if not existing_bracket_articles:
            self._bracket_to_radiators = {}
            return

        bracket_to_radiators: Dict[str, List[str]] = {}

        for idx, row in self._spec_data.iterrows():
            name = str(row.get('Наименование', ''))

            if "Кронштейн" in name:
                continue

            # Индивидуальный тип монтажа для этого радиатора
            bracket_type = self._get_bracket_type_for_radiator(row)
            if bracket_type == "Без кронштейнов":
                continue

            # Извлекаем параметры
            rad_type = None
            height = None
            length = None
            connection = None

            art = str(row.get('Артикул', '')).strip()
            if art and len(art) >= 10 and art.startswith('7724'):
                art_for_search = art
                if len(art) >= 5 and art[4] == '6':
                    art_for_search = art[:4] + '7' + art[5:]

                found = self.app.data_provider.find_by_article(art_for_search)
                if found is not None:
                    connection = str(found.get('Connection', ''))
                    rad_type = str(found.get('RadiatorType', ''))
                    size_match = re.search(r'/(\d{3,4})/(\d{3,4})', name)
                    if size_match:
                        height = int(size_match.group(1))
                        length = int(size_match.group(2))

            if rad_type is None:
                type_match = re.search(r'/(\d{2})/', name)
                if type_match:
                    rad_type = type_match.group(1)

            if height is None:
                height_match = re.search(r'/(\d{3,4})/', name)
                if height_match:
                    height = int(height_match.group(1))

            if length is None:
                length_match = re.search(r'/(\d{3,4})$', name)
                if length_match:
                    length = int(length_match.group(1))

            if connection is None:
                name_lower = name.lower()
                if 'ventil hygiene (hv)' in name_lower:
                    if ' la' in name_lower or ' l ' in name_lower or name_lower.endswith(' la'):
                        connection = 'HV-левое'
                    else:
                        connection = 'HV-правое'
                elif 'hygiene (h)' in name_lower:
                    connection = 'H-боковое'
                elif 'vk-profil' in name_lower:
                    if ' la' in name_lower or ' l ' in name_lower or name_lower.endswith(' la'):
                        connection = 'VK-левое'
                    else:
                        connection = 'VK-правое'
                elif 'k-profil' in name_lower:
                    connection = 'K-боковое'
                else:
                    if 'k-profil' in name_lower or 'боков' in name_lower:
                        connection = 'K-боковое'
                    elif 'vk' in name_lower or 'нижн' in name_lower or 'донн' in name_lower:
                        if 'левое' in name_lower or 'лев ' in name_lower or ' l ' in name_lower:
                            connection = 'VK-левое'
                        else:
                            connection = 'VK-правое'
                    else:
                        connection = 'VK-правое'

            if rad_type in ['20', '21', '22'] and connection in ['VK-левое', 'HV-левое']:
                if 'HV' in connection:
                    connection = 'HV-правое'
                else:
                    connection = 'VK-правое'

            if not (rad_type and height and length and connection):
                continue

            qty = int(row.get('Кол-во', 0))
            if qty <= 0:
                continue

            single_brackets = BracketsCalculator.calculate(
                radiator_type=rad_type,
                length=length,
                height=height,
                bracket_type=bracket_type,
                connection=connection,
                quantity=qty,
            )

            for art_bracket, _ in single_brackets:
                if art_bracket not in existing_bracket_articles:
                    continue
                if art_bracket not in bracket_to_radiators:
                    bracket_to_radiators[art_bracket] = []
                if art not in bracket_to_radiators[art_bracket]:
                    bracket_to_radiators[art_bracket].append(art)

        self._bracket_to_radiators = bracket_to_radiators

    def _delete_selected_row(self) -> None:
        selected = self._tree.selection()
        if not selected:
            return

        item = selected[0]
        values = self._tree.item(item, "values")

        if not values:
            return

        # Проверяем «Итого» по столбцу «Наименование» (индекс 2)
        if len(values) > 2 and str(values[2]).startswith("Итого"):
            messagebox.showwarning("Удаление невозможно", "Нельзя удалить итоговую строку.")
            return

        if "Кронштейн" not in str(values[2]):
            messagebox.showwarning(
                "Удаление невозможно",
                "Можно удалять только строки с кронштейнами.\nРадиаторы удаляются только из главной матрицы."
            )
            return

        if not messagebox.askyesno("Подтверждение", "Удалить строку с кронштейном?"):
            return

        # Если удаляем ручной кронштейн — убираем его артикул из списка
        art_to_remove = values[1] if len(values) > 1 else ""
        if art_to_remove in self._manual_bracket_articles:
            self._manual_bracket_articles.discard(art_to_remove)

        self._tree.delete(item)

        art = values[1] if len(values) > 1 else ""
        name = values[2] if len(values) > 2 else ""

        for idx in self._spec_data.index:
            if (str(self._spec_data.at[idx, "Артикул"]) == str(art) and
                str(self._spec_data.at[idx, "Наименование"]) == str(name)):
                self._spec_data = self._spec_data.drop(idx)
                break

        self._spec_data = self._spec_data.reset_index(drop=True)

        for new_idx, idx in enumerate(self._spec_data.index):
            self._spec_data.at[idx, "№"] = new_idx + 1

        self._fill_tree()
        self._update_totals()

        logger.info(f"Удалена строка с кронштейном: {name}")

    def _update_totals(self) -> None:
        if self._spec_data is None or self._spec_data.empty:
            tp, tw, tv = 0, 0, 0
        else:
            tp, tw, tv = self.app.spec_generator.calculate_totals(self._spec_data)

        if self._power_label and self._power_label.winfo_exists():
            self._power_label.config(text=f"Суммарная мощность: {self.app.spec_generator.format_power(tp)}")
        if self._weight_label and self._weight_label.winfo_exists():
            self._weight_label.config(text=f"Общий вес: {self.app.spec_generator.format_weight(tw)}")
        if self._volume_label and self._volume_label.winfo_exists():
            self._volume_label.config(text=f"Общий объём: {tv:.5f} м³")

    # ==================================================================
    # ВАЛИДАЦИЯ СКИДОК
    # ==================================================================

    def _validate_discount(self, value: str) -> bool:
        if value == "":
            return True
        try:
            v = float(value.replace(',', '.'))
            return 0 <= v <= 100
        except ValueError:
            return False

    def _on_discount_changed(self, *args) -> None:
        if self._radiator_discount_var:
            self.app.main_window.radiator_discount_var.set(self._radiator_discount_var.get())
        if self._bracket_discount_var:
            self.app.main_window.bracket_discount_var.set(self._bracket_discount_var.get())
        self._recalculate_table()

    def _recalculate_table(self) -> None:
        if not self._tree:
            return

        try:
            rad_disc = float(self._radiator_discount_var.get() or "0")
            rad_disc = max(0.0, min(100.0, rad_disc))
        except (ValueError, TypeError):
            rad_disc = 0.0

        try:
            br_disc = float(self._bracket_discount_var.get() or "0")
            br_disc = max(0.0, min(100.0, br_disc))
        except (ValueError, TypeError):
            br_disc = 0.0

        def fmt_money(v):
            try:
                return f"{float(v):,.2f}".replace(',', ' ') + "   "
            except (ValueError, TypeError):
                return ""

        total_rad_qty = 0
        total_br_qty = 0
        total_sum = 0.0

        items = self._tree.get_children()
        for item in items:
            values = list(self._tree.item(item, "values"))
            # Проверяем «Итого» по столбцу «Наименование» (индекс 2)
            if len(values) > 2 and str(values[2]).startswith("Итого"):
                continue

            if len(values) < 10:
                continue

            name = values[2] if len(values) > 2 else ""
            is_bracket = "Кронштейн" in str(name)

            try:
                base_price = float(values[5].replace(',', '.').replace(' ', '')) if values[5] else 0.0
            except (ValueError, TypeError):
                base_price = 0.0

            try:
                qty = int(values[8]) if values[8] else 0
            except (ValueError, TypeError):
                qty = 0

            disc = br_disc if is_bracket else rad_disc
            new_price = round(base_price * (1 - disc / 100), 2)
            new_total = round(new_price * qty, 2)

            values[6] = f"{disc:.2f}".replace('.', ',')
            values[7] = fmt_money(new_price)
            values[9] = fmt_money(new_total)

            self._tree.item(item, values=values)

            total_sum += new_total
            if is_bracket:
                total_br_qty += qty
            else:
                total_rad_qty += qty

            art = values[1] if len(values) > 1 else ""
            for idx in self._spec_data.index:
                if (str(self._spec_data.at[idx, "Артикул"]) == str(art) and
                    str(self._spec_data.at[idx, "Наименование"]) == str(name)):
                    self._spec_data.at[idx, "Скидка, %"] = disc
                    self._spec_data.at[idx, "Цена со скидкой, руб (с НДС)"] = new_price
                    self._spec_data.at[idx, "Сумма, руб (с НДС)"] = new_total
                    break

        if items:
            last_item = items[-1]
            last_values = list(self._tree.item(last_item, "values"))
            if last_values and len(last_values) > 2 and str(last_values[2]).startswith("Итого"):
                last_values[8] = f"{total_rad_qty} / {total_br_qty}"
                last_values[9] = fmt_money(total_sum)
                self._tree.item(last_item, values=last_values)

        self._update_totals()
    # ==================================================================
    # ПОДСКАЗКИ ПРИ НАВЕДЕНИИ
    # ==================================================================

    def _on_tree_motion(self, event) -> None:
        x, y = event.x, event.y
        column_id = self._tree.identify_column(x)

        if column_id and y < 25:
            col_index = int(column_id.replace('#', '')) - 1
            columns = [self._tree.heading(c)["text"] for c in self._tree["columns"]]
            if 0 <= col_index < len(columns):
                col_name = columns[col_index]
                if col_name in ["Артикул", "Кол-во"]:
                    self._show_header_tooltip(col_name, event.x_root, event.y_root)
                    return
        self._hide_header_tooltip()

    def _show_header_tooltip(self, column_name: str, x: int, y: int) -> None:
        if not self._header_tooltip:
            self._header_tooltip = tk.Toplevel(self._dialog)
            self._header_tooltip.wm_overrideredirect(True)
            default_font = self.font_manager.get_default_font()
            self._header_tooltip_label = tk.Label(
                self._header_tooltip,
                text="Нажми для копирования в буфер",
                background="#ffffe0",
                relief="solid",
                padx=5,
                pady=5,
                font=default_font
            )
            self._header_tooltip_label.pack()

        self._header_tooltip.wm_geometry(f"+{x - 50}+{y - 40}")
        self._header_tooltip.deiconify()

    def _hide_header_tooltip(self, event=None) -> None:
        if self._header_tooltip and self._header_tooltip.winfo_exists():
            self._header_tooltip.withdraw()

    # ==================================================================
    # КОПИРОВАНИЕ В БУФЕР
    # ==================================================================

    def _copy_articles(self) -> None:
        """Копирует артикулы из столбца "Артикул" в буфер обмена, исключая итоговую строку."""
        items = self._tree.get_children()
        articles = []
        for item in items:
            values = self._tree.item(item, "values")
            # Проверяем столбец "Наименование" (индекс 2), так как "Итого" теперь там
            if values and not str(values[2]).startswith("Итого"):
                art = values[1].strip() if len(values) > 1 else ""
                if art:
                    articles.append(art)
        if articles:
            try:
                import pyperclip
                pyperclip.copy('\n'.join(articles))
            except ImportError:
                self._dialog.clipboard_clear()
                self._dialog.clipboard_append('\n'.join(articles))
                self._dialog.update()

            self._dialog.lower()
            if hasattr(self.app, 'root') and self.app.root.winfo_exists():
                self.app.root.attributes('-topmost', True)
                self.app.root.focus_force()
                self.app.root.attributes('-topmost', False)

    def _copy_quantities(self) -> None:
        """Копирует количества из столбца "Кол-во" в буфер обмена, исключая итоговую строку."""
        items = self._tree.get_children()
        quantities = []
        for item in items:
            values = self._tree.item(item, "values")
            # Проверяем столбец "Наименование" (индекс 2), так как "Итого" теперь там
            if values and not str(values[2]).startswith("Итого"):
                qty = values[8].strip() if len(values) > 8 else ""
                if qty:
                    quantities.append(qty)
        if quantities:
            try:
                import pyperclip
                pyperclip.copy('\n'.join(quantities))
            except ImportError:
                self._dialog.clipboard_clear()
                self._dialog.clipboard_append('\n'.join(quantities))
                self._dialog.update()

            self._dialog.lower()
            if hasattr(self.app, 'root') and self.app.root.winfo_exists():
                self.app.root.attributes('-topmost', True)
                self.app.root.focus_force()
                self.app.root.attributes('-topmost', False)
    # ==================================================================
    # ЗАПОЛНЕНИЕ ТАБЛИЦЫ
    # ==================================================================

    def _fill_tree(self) -> None:
        """Заполняет дерево данными из _spec_data."""
        # Очищаем дерево
        for item in self._tree.get_children():
            self._tree.delete(item)

        def fmt_money(v):
            try:
                return f"{float(v):,.2f}".replace(',', ' ') + "   "
            except (ValueError, TypeError):
                return ""

        # Проверяем, что _spec_data не пустой
        if self._spec_data is None or self._spec_data.empty:
            logger.warning("_spec_data пустой при вызове _fill_tree()")
            return

        # Убеждаемся, что столбец «Тип монтажа» есть
        self._ensure_mount_type_column()

        # ========== РАЗДЕЛЯЕМ СТРОКИ НА РАДИАТОРЫ И КРОНШТЕЙНЫ ==========
        radiators_rows = []
        brackets_rows = []

        for _, row in self._spec_data.iterrows():
            if "Кронштейн" in str(row.get("Наименование", "")):
                brackets_rows.append(row)
            else:
                radiators_rows.append(row)

        # Переворачиваем блок радиаторов, если включён обратный порядок
        if self._radiators_reversed:
            radiators_rows = list(reversed(radiators_rows))

        # Объединяем в нужном порядке: радиаторы → кронштейны
        ordered_rows = radiators_rows + brackets_rows
        # =================================================================

        # Добавляем строки с сквозной нумерацией 1, 2, 3, ...
        for row_number, row in enumerate(ordered_rows, start=1):
            is_bracket = "Кронштейн" in str(row.get("Наименование", ""))
            power = "" if is_bracket else (
                str(round(float(row.get("Мощность, Вт", 0)))) if row.get("Мощность, Вт") else ""
            )

            # ========== ВИД МОНТАЖА ==========
            if is_bracket:
                mount_display = ""
            else:
                raw_mount = str(row.get("Тип монтажа", "")).strip().lower()
                if raw_mount == "настенный":
                    mount_display = "На стену"
                elif raw_mount == "напольный":
                    mount_display = "На пол"
                else:
                    mount_display = ""

            # ========== ОПРЕДЕЛЯЕМ ГИГИЕНИЧЕСКИЙ РАДИАТОР ==========
            is_hygiene = False
            if not is_bracket:
                conn = row.get('Connection', '')
                if conn in ['HV-правое', 'HV-левое', 'H-боковое']:
                    is_hygiene = True
                else:
                    name = str(row.get('Наименование', ''))
                    name_lower = name.lower()
                    if any(kw in name_lower for kw in ['ventil hygiene (hv)', 'hygiene (h)']):
                        is_hygiene = True

            try:
                values = [
                    row_number,                            # №
                    row.get("Артикул", ""),
                    row.get("Наименование", ""),
                    power,
                    mount_display,                         # Вид монтажа
                    fmt_money(row.get("Цена, руб (с НДС)", 0)),
                    f"{float(row.get('Скидка, %', 0)):.2f}".replace('.', ','),
                    fmt_money(row.get("Цена со скидкой, руб (с НДС)", 0)),
                    row.get("Кол-во", 0),
                    fmt_money(row.get("Сумма, руб (с НДС)", 0))
                ]
                if is_bracket:
                    tag = "bracket"
                elif is_hygiene:
                    tag = "hygiene"
                else:
                    tag = "radiator"
                self._tree.insert("", "end", values=values, tags=(tag,))
            except Exception as e:
                logger.error(f"Ошибка добавления строки в дерево: {e}")
                continue

        try:
            total_qty_rad = sum(
                int(row.get("Кол-во", 0)) for _, row in self._spec_data.iterrows()
                if "Кронштейн" not in str(row.get("Наименование", ""))
            )
            total_qty_br = sum(
                int(row.get("Кол-во", 0)) for _, row in self._spec_data.iterrows()
                if "Кронштейн" in str(row.get("Наименование", ""))
            )
            total_sum = self._spec_data["Сумма, руб (с НДС)"].sum() if "Сумма, руб (с НДС)" in self._spec_data.columns else 0

            self._tree.insert("", "end", values=[
                "",                                    # №
                "",                                    # Артикул
                "Итого (радиаторы / кронштейны)",      # Наименование
                "",                                    # Мощность
                "",                                    # Вид монтажа
                "",                                    # Цена
                "",                                    # Скидка
                "",                                    # Цена со скидкой
                f"{total_qty_rad} / {total_qty_br}",   # Кол-во
                fmt_money(total_sum)                   # Сумма
            ], tags=("total",))
        except Exception as e:
            logger.error(f"Ошибка добавления итоговой строки: {e}")
    # ==================================================================
    # ДОБАВЛЕНИЕ КРОНШТЕЙНА
    # ==================================================================

    def _add_bracket(self) -> None:
        name = self._bracket_combo.get()
        qty_str = self._qty_entry.get().strip()

        if not name:
            messagebox.showwarning("Ошибка", "Выберите кронштейн")
            return
        if not qty_str:
            messagebox.showwarning("Ошибка", "Введите количество")
            return

        try:
            qty = int(qty_str)
            if qty <= 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning("Ошибка", "Количество должно быть целым положительным числом")
            return

        brackets = self.app.data_provider.get_brackets_list()
        bracket = next((b for b in brackets if b['name'] == name), None)
        if not bracket:
            return

        bracket_df = self.app.data_provider.brackets_df
        mask = bracket_df['Артикул'].astype(str).str.strip() == bracket['article'].strip()
        if not mask.any():
            messagebox.showwarning("Ошибка", "Кронштейн не найден в базе")
            return

        b_info = bracket_df[mask].iloc[0]
        price = float(b_info.get('Цена, руб', 0))

        br_disc = 0.0
        try:
            if self._bracket_discount_var and self._bracket_discount_var.get():
                br_disc = float(self._bracket_discount_var.get().replace(',', '.'))
            else:
                br_disc = float(self.app.main_window.bracket_discount_var.get() or 0)
        except:
            pass
        br_disc = max(0.0, min(100.0, br_disc))

        disc_price = round(price * (1 - br_disc / 100), 2)
        total = round(disc_price * qty, 2)

        # Определяем следующий номер строки
        if self._spec_data is not None and not self._spec_data.empty:
            next_num = self._spec_data["№"].max() + 1 if "№" in self._spec_data.columns else len(self._spec_data) + 1
        else:
            next_num = 1

        new_row = {
            "№": next_num,
            "Артикул": bracket['article'],
            "Наименование": bracket['name'],
            "Мощность, Вт": 0.0,
            "Тип монтажа": "",
            "Цена, руб (с НДС)": price,
            "Скидка, %": br_disc,
            "Цена со скидкой, руб (с НДС)": disc_price,
            "Кол-во": qty,
            "Сумма, руб (с НДС)": total,
        }

        # Добавляем в _spec_data
        if self._spec_data is None or self._spec_data.empty:
            self._spec_data = pd.DataFrame([new_row])
        else:
            self._spec_data = pd.concat([self._spec_data, pd.DataFrame([new_row])], ignore_index=True)

        # ========== СВЯЗЫВАЕМ КРОНШТЕЙН ТОЛЬКО С ПОДХОДЯЩИМИ РАДИАТОРАМИ ==========
        from nextt.core.brackets import BracketsCalculator

        art_bracket = bracket['article']

        # Запоминаем, что этот артикул добавлен вручную
        self._manual_bracket_articles.add(art_bracket)

        # ========== ОПРЕДЕЛЯЕМ ТИП МОНТАЖА ПО САМОМУ КРОНШТЕЙНУ ==========
        bracket_mount = str(b_info.get('Тип монтажа', '')).strip().lower()

        if 'настен' in bracket_mount:
            bracket_type_for_calc = "Настенные кронштейны"
        elif 'напольн' in bracket_mount:
            bracket_type_for_calc = "Напольные кронштейны"
        else:
            bracket_type_for_calc = self.app.main_window.bracket_var.get()
        # ===================================================================

        # Собираем артикулы радиаторов, к которым подходит этот кронштейн
        matching_radiator_articles = []

        if self._spec_data is not None and not self._spec_data.empty:
            for _, row in self._spec_data.iterrows():
                row_name = str(row.get('Наименование', ''))
                if "Кронштейн" in row_name:
                    continue

                art_rad = str(row.get('Артикул', '')).strip()
                if not art_rad or not art_rad.startswith("7724"):
                    continue

                # Определяем параметры радиатора
                rad_type = None
                height = None
                length = None
                connection = None

                # Пробуем найти радиатор в базе
                art_for_search = art_rad
                if len(art_rad) >= 5 and art_rad[4] == '6':
                    art_for_search = art_rad[:4] + '7' + art_rad[5:]

                found = self.app.data_provider.find_by_article(art_for_search)
                if found is not None:
                    connection = str(found.get('Connection', ''))
                    rad_type = str(found.get('RadiatorType', ''))
                    size_match = re.search(r'/(\d{3,4})/(\d{3,4})', row_name)
                    if size_match:
                        height = int(size_match.group(1))
                        length = int(size_match.group(2))

                # Если не нашли — пробуем извлечь из названия
                if rad_type is None:
                    type_match = re.search(r'/(\d{2})/', row_name)
                    if type_match:
                        rad_type = type_match.group(1)

                if height is None:
                    height_match = re.search(r'/(\d{3,4})/', row_name)
                    if height_match:
                        height = int(height_match.group(1))

                if length is None:
                    length_match = re.search(r'/(\d{3,4})$', row_name)
                    if length_match:
                        length = int(length_match.group(1))

                if connection is None:
                    name_lower = row_name.lower()
                    if 'ventil hygiene (hv)' in name_lower:
                        if ' la' in name_lower or ' l ' in name_lower or name_lower.endswith(' la'):
                            connection = 'HV-левое'
                        else:
                            connection = 'HV-правое'
                    elif 'hygiene (h)' in name_lower:
                        connection = 'H-боковое'
                    elif 'vk-profil' in name_lower:
                        if ' la' in name_lower or ' l ' in name_lower or name_lower.endswith(' la'):
                            connection = 'VK-левое'
                        else:
                            connection = 'VK-правое'
                    elif 'k-profil' in name_lower:
                        connection = 'K-боковое'
                    else:
                        connection = 'VK-правое'

                # Корректировка универсальных типов
                if rad_type in ['20', '21', '22'] and connection in ['VK-левое', 'HV-левое']:
                    if 'HV' in connection:
                        connection = 'HV-правое'
                    else:
                        connection = 'VK-правое'

                if not (rad_type and height and length and connection):
                    continue

                # Проверяем, подходит ли кронштейн к этому радиатору
                brackets_for_rad = BracketsCalculator.calculate_for_manual(
                    radiator_type=rad_type,
                    length=length,
                    height=height,
                    bracket_type=bracket_type_for_calc,
                    connection=connection,
                    quantity=1,
                )

                for art_candidate, _ in brackets_for_rad:
                    if art_candidate == art_bracket:
                        if art_rad not in matching_radiator_articles:
                            matching_radiator_articles.append(art_rad)
                        break

        # Записываем связи
        if matching_radiator_articles:
            if art_bracket not in self._bracket_to_radiators:
                self._bracket_to_radiators[art_bracket] = []
            for art_rad in matching_radiator_articles:
                if art_rad not in self._bracket_to_radiators[art_bracket]:
                    self._bracket_to_radiators[art_bracket].append(art_rad)

        # Обновляем дерево
        self._fill_tree()

        # Очищаем поле ввода
        self._qty_entry.delete(0, tk.END)

        # Обновляем итоги
        self._update_totals()

        logger.info(f"Добавлен кронштейн: {bracket['name']} x {qty}, связано радиаторов: {len(matching_radiator_articles)}")
    # ==================================================================
    # КАРТИНКИ КРОНШТЕЙНОВ
    # ==================================================================

    def _show_bracket_image(self, event, item: str) -> None:
        """
        Показывает PNG-картинку кронштейна при наведении на артикул.
        Картинка должна лежать в папке resources с именем {артикул}.png
        Картинка отображается в области столбца «Мощность, Вт» наведённой строки.
        """
        # ========== ПРОВЕРКА ЧЕКБОКСА ==========
        if not self._show_images_var.get():
            return

        # Проверяем, что это кронштейн
        values = self._tree.item(item, "values")
        if not values or len(values) < 3:
            return

        name = values[2] if len(values) > 2 else ""
        if "Кронштейн" not in str(name):
            return

        if values[0] == "Итого":
            return

        art = values[1].strip() if len(values) > 1 else ""
        if not art:
            return

        if not (art.startswith('К') or art.startswith('K')):
            return

        if self._bracket_image_after_id is not None:
            try:
                self._dialog.after_cancel(self._bracket_image_after_id)
            except:
                pass
            self._bracket_image_after_id = None

        if self._bracket_image_window and self._bracket_image_window.winfo_exists():
            self._bracket_image_window.destroy()
            self._bracket_image_window = None
        self._bracket_image_label = None
        if self._bracket_photo_image:
            self._bracket_photo_image = None

        self._last_hover_item = item
        self._highlight_bracket_row(item)

        try:
            from nextt.config import get_resource_path

            image_path = get_resource_path(f"{art}.png")
            if not image_path or not os.path.exists(image_path):
                image_path = get_resource_path(f"{art.upper()}.png")
                if not image_path or not os.path.exists(image_path):
                    art_latin = art.replace('К', 'K')
                    image_path = get_resource_path(f"{art_latin}.png")
                    if not image_path or not os.path.exists(image_path):
                        return

            self._bracket_photo_image = tk.PhotoImage(file=image_path)

            self._bracket_image_window = tk.Toplevel(self._dialog)
            self._bracket_image_window.wm_overrideredirect(True)

            frame = tk.Frame(
                self._bracket_image_window,
                bg='white',
                relief='solid',
                borderwidth=2,
                padx=5,
                pady=5
            )
            frame.pack()

            self._bracket_image_label = tk.Label(
                frame,
                image=self._bracket_photo_image,
                bg='white'
            )
            self._bracket_image_label.pack()

            # ========== Масштабирование через PIL ==========
            img_width = self._bracket_photo_image.width()
            img_height = self._bracket_photo_image.height()
            max_width = 300
            max_height = 300

            if img_width > max_width or img_height > max_height:
                try:
                    from PIL import Image, ImageTk
                    pil_image = Image.open(image_path)
                    pil_image.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
                    self._bracket_photo_image = ImageTk.PhotoImage(pil_image)
                    self._bracket_image_label.config(image=self._bracket_photo_image)
                except ImportError:
                    pass
                except Exception:
                    pass

            # ========== Принудительно обновляем окно ==========
            self._bracket_image_window.update_idletasks()
            self._bracket_image_window.update()

            # ========== ПОЗИЦИОНИРОВАНИЕ В ОБЛАСТИ СТОЛБЦА «МОЩНОСТЬ, ВТ» ==========
            # Размеры окна с картинкой (запрошенные, по содержимому)
            win_width = self._bracket_image_window.winfo_reqwidth()
            win_height = self._bracket_image_window.winfo_reqheight()

            # Если по какой-то причине размеры нулевые — берём размеры картинки + отступы
            if win_width < 10:
                win_width = self._bracket_photo_image.width() + 20
            if win_height < 10:
                win_height = self._bracket_photo_image.height() + 20

            screen_w = self._bracket_image_window.winfo_screenwidth()
            screen_h = self._bracket_image_window.winfo_screenheight()

            # Высота панели задач (снизу экрана)
            try:
                from nextt.utils.window_manager import get_taskbar_height
                taskbar_h = get_taskbar_height(self._bracket_image_window)
            except Exception:
                taskbar_h = 0

            # Получаем геометрию ячейки в столбце «Мощность, Вт» (#4)
            bbox = self._tree.bbox(item, "#4")

            if bbox is None:
                # Если bbox недоступен — показываем рядом с курсором
                x = event.x_root + 15
                y = event.y_root + 15
            else:
                # bbox = (x, y, width, height) относительно Treeview
                cell_x = self._tree.winfo_rootx() + bbox[0]
                cell_y = self._tree.winfo_rooty() + bbox[1]

                # Левый край картинки совмещаем с левым краем столбца
                x = cell_x
                y = cell_y

            # ========== ВЕРТИКАЛЬНАЯ КОРРЕКТИРОВКА ==========
            # Нижняя граница рабочей области (с учётом панели задач)
            bottom_limit = screen_h - taskbar_h - 10

            if y + win_height > bottom_limit:
                # Прижимаем к нижнему краю рабочей области
                y = bottom_limit - win_height

            if y < 10:
                y = 10
            # ==============================================

            self._bracket_image_window.wm_geometry(f"+{x}+{y}")
            self._bracket_image_window.deiconify()

        except Exception as e:
            logger.debug(f"Ошибка загрузки картинки кронштейна {art}: {e}")
            self._hide_bracket_image()
            
    def _hide_bracket_image(self, delay_ms: int = 100) -> None:
        if self._bracket_image_after_id is not None:
            try:
                self._dialog.after_cancel(self._bracket_image_after_id)
            except:
                pass
            self._bracket_image_after_id = None

        if delay_ms > 0:
            self._bracket_image_after_id = self._dialog.after(
                delay_ms,
                self._hide_bracket_image_immediate
            )
        else:
            self._hide_bracket_image_immediate()

    def _update_context_menu_font(self) -> None:
        """Обновляет шрифт контекстного меню при изменении масштаба."""
        if hasattr(self, '_context_menu') and self._context_menu:
            try:
                if self._context_menu.winfo_exists():
                    new_font = self.font_manager.get_default_font()
                    self._context_menu.configure(font=new_font)
            except (tk.TclError, AttributeError):
                pass

    def _hide_bracket_image_immediate(self) -> None:
        self._bracket_image_after_id = None

        if self._last_hover_item:
            self._unhighlight_bracket_row(self._last_hover_item)
            self._last_hover_item = None

        if self._bracket_image_window and self._bracket_image_window.winfo_exists():
            self._bracket_image_window.destroy()
            self._bracket_image_window = None

        self._bracket_image_label = None
        if self._bracket_photo_image:
            self._bracket_photo_image = None

    def _toggle_bracket_type(self) -> None:
        """Переключает тип монтажа у выделенных радиаторов и пересчитывает кронштейны."""
        manual_brackets = self._extract_manual_brackets()

        selected = self._tree.selection()
        if not selected:
            return

        # Убеждаемся, что столбец существует
        self._ensure_mount_type_column()

        changed_count = 0

        for item in selected:
            values = self._tree.item(item, "values")
            if not values or len(values) < 3:
                continue
            name = values[2] if len(values) > 2 else ""
            if "Кронштейн" in str(name):
                continue

            # Ищем строку в _spec_data по артикулу и наименованию
            art = values[1] if len(values) > 1 else ""
            for idx in self._spec_data.index:
                if (str(self._spec_data.at[idx, "Артикул"]) == str(art) and
                    str(self._spec_data.at[idx, "Наименование"]) == str(name)):
                    current = str(self._spec_data.at[idx, "Тип монтажа"]).strip().lower()
                    if current == "настенный":
                        self._spec_data.at[idx, "Тип монтажа"] = "напольный"
                    else:
                        self._spec_data.at[idx, "Тип монтажа"] = "настенный"
                    changed_count += 1
                    break

        if changed_count == 0:
            return

        # Удаляем старые автоматические кронштейны
        if self._spec_data is not None and not self._spec_data.empty:
            self._spec_data = self._spec_data[
                ~self._spec_data['Наименование'].str.contains('Кронштейн', na=False)
            ]

        # Пересчитываем автоматические, возвращаем ручные
        self._recalculate_all_brackets()
        self._restore_manual_brackets(manual_brackets)

        # Обновляем таблицу и итоги
        self._fill_tree()
        self._recalculate_table()
        self._update_totals()

        logger.info(f"Смена типа монтажа: обновлено {changed_count} радиаторов")
    # ==================================================================
    # СМЕНА ПОДКЛЮЧЕНИЯ
    # ==================================================================

    def _change_connection(self) -> None:
        import traceback
        logger.info("=" * 70)
        logger.info("СМЕНА ПОДКЛЮЧЕНИЯ: НАЧАЛО")
        logger.info("=" * 70)

        selected = self._tree.selection()
        logger.info(f"Выделено строк: {len(selected)}")

        if not selected:
            messagebox.showinfo("Смена подключения", "Выделите одну или несколько строк с радиаторами.")
            return

        items_data = []
        skipped_non_radiators = 0

        for item in selected:
            values = self._tree.item(item, "values")

            if not values or len(values) < 3:
                skipped_non_radiators += 1
                continue

            if len(values) > 2 and str(values[2]).startswith("Итого"):
                skipped_non_radiators += 1
                continue

            name = values[2] if len(values) > 2 else ""
            if "Кронштейн" in str(name):
                skipped_non_radiators += 1
                continue

            art = values[1].strip() if len(values) > 1 else ""

            if not (art.startswith("7724") and len(art) >= 10):
                skipped_non_radiators += 1
                continue

            try:
                qty = int(values[7]) if values[7] and values[7].isdigit() else 0
            except (ValueError, TypeError):
                qty = 0

            items_data.append({
                "item": item,
                "article": art,
                "name": name,
                "qty": qty,
                "values": values,
            })

        if not items_data:
            if skipped_non_radiators > 0:
                messagebox.showinfo(
                    "Смена подключения",
                    f"Выделено только {skipped_non_radiators} строк, которые не являются радиаторами.\n"
                    "Эта функция работает только с радиаторами (артикулы 7724...)."
                )
            else:
                messagebox.showinfo("Смена подключения", "Нет выделенных радиаторов для обработки.")
            return

        current_digits = set()
        for data in items_data:
            art = data["article"]
            if len(art) >= 10 and art.startswith("7724"):
                # У 30 типа артикул может быть 11 знаков, поэтому берём 6-й символ (индекс 5)
                if len(art) >= 11:
                    digit = art[5]  # 6-й символ
                else:
                    digit = art[5]  # 6-й символ
                current_digits.add(digit)

        has_side = any(d in ['5', '6'] for d in current_digits)
        has_bottom = '0' in current_digits

        if has_bottom and has_side:
            action = self._show_connection_dialog_mixed()
            if action is None:
                return
        elif has_bottom and not has_side:
            action = "to_bottom"
        elif has_side and not has_bottom:
            action = self._show_connection_dialog_side_only(items_data)
            if action is None:
                return
        else:
            messagebox.showinfo("Смена подключения", "Не удалось определить тип подключения выделенных радиаторов.")
            return

        manual_brackets = self._extract_manual_brackets()

        changed_count = 0
        skipped_count = 0
        skipped_due_to_type = 0

        for data in items_data:
            art = data["article"]
            name = data["name"]
            item = data["item"]

            if not (art.startswith("7724") and len(art) >= 10):
                skipped_count += 1
                continue

            rad_type = self._get_radiator_type_from_name(name)
            if not rad_type:
                skipped_count += 1
                continue

            current_digit = art[5]  # 6-й символ
            new_digit = None

            if action == "to_bottom":
                if current_digit == '0':
                    if rad_type in ['10', '11', '30', '33']:
                        side = self._ask_side_dialog()
                        if side is None:
                            skipped_count += 1
                            continue
                        new_digit = '5' if side == "right" else '6'
                    elif rad_type in ['20', '21', '22']:
                        new_digit = '5'
                    else:
                        skipped_count += 1
                        continue
                else:
                    skipped_count += 1
                    continue

            elif action == "to_side":
                if current_digit in ['5', '6']:
                    new_digit = '0'
                else:
                    skipped_count += 1
                    continue

            elif action == "swap_side":
                if current_digit == '5':
                    if rad_type in ['10', '11', '30', '33']:
                        new_digit = '6'
                    else:
                        skipped_due_to_type += 1
                        continue
                elif current_digit == '6':
                    new_digit = '5'
                else:
                    skipped_count += 1
                    continue

            if new_digit is None:
                skipped_count += 1
                continue

            # Формируем новый артикул
            if len(art) == 11:
                new_art = art[:5] + new_digit + art[6:]
            else:
                new_art = art[:5] + new_digit + art[6:]

            if art.startswith("77247"):
                found = self.app.data_provider.find_by_article(new_art)
            elif art.startswith("77246"):
                found = self.app.data_provider.find_meteor_by_article(new_art)
            else:
                found = None

            if found is None:
                skipped_count += 1
                continue

            new_name = str(found.get('Наименование', ''))

            for idx in self._spec_data.index:
                if (str(self._spec_data.at[idx, "Артикул"]) == art and
                    str(self._spec_data.at[idx, "Наименование"]) == name):
                    self._spec_data.at[idx, "Артикул"] = new_art
                    self._spec_data.at[idx, "Наименование"] = new_name
                    break

            values = list(self._tree.item(item, "values"))
            values[1] = new_art
            values[2] = new_name
            self._tree.item(item, values=values)

            changed_count += 1

        # ========== ИСПРАВЛЕНИЕ: УДАЛЯЕМ КРОНШТЕЙНЫ ПЕРЕД ПЕРЕСЧЁТОМ ==========
        # Удаляем все старые кронштейны из _spec_data
        if self._spec_data is not None and not self._spec_data.empty:
            self._spec_data = self._spec_data[
                ~self._spec_data['Наименование'].str.contains('Кронштейн', na=False)
            ]
            logger.info(f"Кронштейны удалены перед пересчётом, осталось радиаторов: {len(self._spec_data)}")

        # Пересчитываем кронштейны после смены подключения
        if changed_count > 0:
            self._recalculate_all_brackets()
            self._restore_manual_brackets(manual_brackets)
            self._fill_tree()
            self._recalculate_table()
            self._update_totals()

        # ========== ИСПРАВЛЕНИЕ: УБИРАЕМ ОКНО УСПЕХА ==========
        # Показываем предупреждение только если есть ошибки
        if changed_count == 0:
            msg_parts = []
            if skipped_count > 0:
                msg_parts.append(f"⚠️ Пропущено (не найдено в базе): {skipped_count}")
            if skipped_due_to_type > 0:
                msg_parts.append(f"⚠️ Пропущено (нет такого подключения для типа): {skipped_due_to_type}")
            if skipped_non_radiators > 0:
                msg_parts.append(f"ℹ️ Пропущено кронштейнов/не радиаторов: {skipped_non_radiators}")
            messagebox.showwarning("Смена подключения", "Ни один радиатор не был обновлён.\n\n" + "\n".join(msg_parts))
        else:
            # Если всё успешно — ничего не показываем
            logger.info(f"Смена подключения: обновлено {changed_count} радиаторов")

    def _get_radiator_type_from_name(self, name: str) -> Optional[str]:
        patterns = [
            r'/(\d{2})/',
            r'Profil\s*(\d{2})',
            r'тип\s*(\d{2})',
            r'(\d{2})\s*[/-]',
        ]
        for pattern in patterns:
            match = re.search(pattern, name, re.IGNORECASE)
            if match:
                t = match.group(1)
                if t in ['10', '11', '20', '21', '22', '30', '33']:
                    return t
        return None

    def _ask_side_dialog(self) -> Optional[str]:
        dialog = tk.Toplevel(self._dialog)
        dialog.title("Выбор стороны подключения")
        dialog.transient(self._dialog)
        dialog.grab_set()
        dialog.resizable(False, False)
        dialog.configure(bg='#f5f5f5')

        try:
            from nextt.config import get_resource_path
            icon_path = get_resource_path("icon.ico")
            if icon_path and os.path.exists(icon_path):
                dialog.iconbitmap(icon_path)
        except Exception as e:
            logger.debug(f"Не удалось загрузить иконку для диалога: {e}")

        dialog.update_idletasks()
        w, h = 350, 220
        x = (dialog.winfo_screenwidth() - w) // 2
        y = (dialog.winfo_screenheight() - h) // 2
        dialog.geometry(f"{w}x{h}+{x}+{y}")

        result = {"value": None}

        tk.Label(
            dialog,
            text="Выберите сторону для нижнего подключения:",
            font=self.font_manager.get_default_font(),
            bg='#f5f5f5'
        ).pack(pady=(20, 15))

        frame = tk.Frame(dialog, bg='#f5f5f5')
        frame.pack(pady=5)

        def on_right():
            result["value"] = "right"
            dialog.destroy()
            if self._dialog and self._dialog.winfo_exists():
                self._dialog.focus_force()
                self._dialog.grab_set()

        def on_left():
            result["value"] = "left"
            dialog.destroy()
            if self._dialog and self._dialog.winfo_exists():
                self._dialog.focus_force()
                self._dialog.grab_set()

        def on_cancel():
            result["value"] = None
            dialog.destroy()
            if self._dialog and self._dialog.winfo_exists():
                self._dialog.focus_force()
                self._dialog.grab_set()

        btn_right = tk.Button(
            frame,
            text="Правое (рекомендуется)",
            command=on_right,
            width=25,
            height=1,
            bg='#263168',
            fg='white',
            font=self.font_manager.get_default_font(),
            relief="flat",
            cursor="hand2",
            activebackground='#7E1A2F',
            activeforeground='white'
        )
        btn_right.pack(pady=5)

        btn_left = tk.Button(
            frame,
            text="Левое",
            command=on_left,
            width=25,
            height=1,
            bg='#263168',
            fg='white',
            font=self.font_manager.get_default_font(),
            relief="flat",
            cursor="hand2",
            activebackground='#7E1A2F',
            activeforeground='white'
        )
        btn_left.pack(pady=5)

        btn_cancel = tk.Button(
            frame,
            text="Отмена",
            command=on_cancel,
            width=25,
            height=1,
            bg='#888888',
            fg='white',
            font=self.font_manager.get_default_font(),
            relief="flat",
            cursor="hand2",
            activebackground='#7E1A2F',
            activeforeground='white'
        )
        btn_cancel.pack(pady=5)

        def on_dialog_close():
            result["value"] = None
            dialog.destroy()
            if self._dialog and self._dialog.winfo_exists():
                self._dialog.focus_force()
                self._dialog.grab_set()

        dialog.protocol("WM_DELETE_WINDOW", on_dialog_close)

        dialog.wait_window()
        return result["value"]

    def _show_connection_dialog_mixed(self) -> Optional[str]:
        dialog = tk.Toplevel(self._dialog)
        dialog.title("Смена подключения")
        dialog.transient(self._dialog)
        dialog.grab_set()
        dialog.resizable(False, False)
        dialog.configure(bg='#f5f5f5')

        try:
            from nextt.config import get_resource_path
            icon_path = get_resource_path("icon.ico")
            if icon_path and os.path.exists(icon_path):
                dialog.iconbitmap(icon_path)
        except Exception as e:
            logger.debug(f"Не удалось загрузить иконку для диалога: {e}")

        dialog.update_idletasks()
        w, h = 450, 230
        x = (dialog.winfo_screenwidth() - w) // 2
        y = (dialog.winfo_screenheight() - h) // 2
        dialog.geometry(f"{w}x{h}+{x}+{y}")

        result = {"value": None}

        tk.Label(
            dialog,
            text="В выделении есть радиаторы с разными подключениями.\nВыберите действие:",
            font=self.font_manager.get_default_font(),
            bg='#f5f5f5',
            justify="center"
        ).pack(pady=(20, 15))

        frame = tk.Frame(dialog, bg='#f5f5f5')
        frame.pack(pady=5)

        def on_bottom():
            result["value"] = "to_bottom"
            dialog.destroy()
            if self._dialog and self._dialog.winfo_exists():
                self._dialog.focus_force()
                self._dialog.grab_set()

        def on_side():
            result["value"] = "to_side"
            dialog.destroy()
            if self._dialog and self._dialog.winfo_exists():
                self._dialog.focus_force()
                self._dialog.grab_set()

        def on_swap():
            result["value"] = "swap_side"
            dialog.destroy()
            if self._dialog and self._dialog.winfo_exists():
                self._dialog.focus_force()
                self._dialog.grab_set()

        def on_cancel():
            result["value"] = None
            dialog.destroy()
            if self._dialog and self._dialog.winfo_exists():
                self._dialog.focus_force()
                self._dialog.grab_set()

        btn_bottom = tk.Button(
            frame,
            text="Переключить на нижнее",
            command=on_bottom,
            width=30,
            height=1,
            bg='#263168',
            fg='white',
            font=self.font_manager.get_default_font(),
            relief="flat",
            cursor="hand2",
            activebackground='#7E1A2F',
            activeforeground='white'
        )
        btn_bottom.pack(pady=5)

        btn_side = tk.Button(
            frame,
            text="Переключить на боковое",
            command=on_side,
            width=30,
            height=1,
            bg='#263168',
            fg='white',
            font=self.font_manager.get_default_font(),
            relief="flat",
            cursor="hand2",
            activebackground='#7E1A2F',
            activeforeground='white'
        )
        btn_side.pack(pady=5)

        btn_swap = tk.Button(
            frame,
            text="Сменить сторону",
            command=on_swap,
            width=30,
            height=1,
            bg='#263168',
            fg='white',
            font=self.font_manager.get_default_font(),
            relief="flat",
            cursor="hand2",
            activebackground='#7E1A2F',
            activeforeground='white'
        )
        btn_swap.pack(pady=5)

        btn_cancel = tk.Button(
            frame,
            text="Отмена",
            command=on_cancel,
            width=30,
            height=1,
            bg='#888888',
            fg='white',
            font=self.font_manager.get_default_font(),
            relief="flat",
            cursor="hand2",
            activebackground='#7E1A2F',
            activeforeground='white'
        )
        btn_cancel.pack(pady=5)

        def on_dialog_close():
            result["value"] = None
            dialog.destroy()
            if self._dialog and self._dialog.winfo_exists():
                self._dialog.focus_force()
                self._dialog.grab_set()

        dialog.protocol("WM_DELETE_WINDOW", on_dialog_close)

        dialog.wait_window()
        return result["value"]

    def _show_connection_dialog_side_only(self, items_data: list) -> Optional[str]:
        has_swappable = False
        for data in items_data:
            rad_type = self._get_radiator_type_from_name(data["name"])
            if rad_type in ['10', '11', '30', '33']:
                has_swappable = True
                break

        dialog = tk.Toplevel(self._dialog)
        dialog.title("Смена подключения")
        dialog.transient(self._dialog)
        dialog.grab_set()
        dialog.resizable(False, False)
        dialog.configure(bg='#f5f5f5')

        try:
            from nextt.config import get_resource_path
            icon_path = get_resource_path("icon.ico")
            if icon_path and os.path.exists(icon_path):
                dialog.iconbitmap(icon_path)
        except Exception as e:
            logger.debug(f"Не удалось загрузить иконку для диалога: {e}")

        dialog.update_idletasks()
        w = 350
        if has_swappable:
            h = 230
        else:
            h = 180
        x = (dialog.winfo_screenwidth() - w) // 2
        y = (dialog.winfo_screenheight() - h) // 2
        dialog.geometry(f"{w}x{h}+{x}+{y}")

        result = {"value": None}

        tk.Label(
            dialog,
            text="Выберите действие:",
            font=self.font_manager.get_default_font(),
            bg='#f5f5f5'
        ).pack(pady=(20, 15))

        frame = tk.Frame(dialog, bg='#f5f5f5')
        frame.pack(pady=5)

        def on_side():
            result["value"] = "to_side"
            dialog.destroy()
            if self._dialog and self._dialog.winfo_exists():
                self._dialog.focus_force()
                self._dialog.grab_set()

        def on_swap():
            result["value"] = "swap_side"
            dialog.destroy()
            if self._dialog and self._dialog.winfo_exists():
                self._dialog.focus_force()
                self._dialog.grab_set()

        def on_cancel():
            result["value"] = None
            dialog.destroy()
            if self._dialog and self._dialog.winfo_exists():
                self._dialog.focus_force()
                self._dialog.grab_set()

        btn_side = tk.Button(
            frame,
            text="Переключить на боковое",
            command=on_side,
            width=30,
            height=1,
            bg='#263168',
            fg='white',
            font=self.font_manager.get_default_font(),
            relief="flat",
            cursor="hand2",
            activebackground='#7E1A2F',
            activeforeground='white'
        )
        btn_side.pack(pady=5)

        if has_swappable:
            btn_swap = tk.Button(
                frame,
                text="Сменить сторону (правое ↔ левое)",
                command=on_swap,
                width=30,
                height=1,
                bg='#263168',
                fg='white',
                font=self.font_manager.get_default_font(),
                relief="flat",
                cursor="hand2",
                activebackground='#7E1A2F',
                activeforeground='white'
            )
            btn_swap.pack(pady=5)

        btn_cancel = tk.Button(
            frame,
            text="Отмена",
            command=on_cancel,
            width=30,
            height=1,
            bg='#888888',
            fg='white',
            font=self.font_manager.get_default_font(),
            relief="flat",
            cursor="hand2",
            activebackground='#7E1A2F',
            activeforeground='white'
        )
        btn_cancel.pack(pady=5)

        def on_dialog_close():
            result["value"] = None
            dialog.destroy()
            if self._dialog and self._dialog.winfo_exists():
                self._dialog.focus_force()
                self._dialog.grab_set()

        dialog.protocol("WM_DELETE_WINDOW", on_dialog_close)

        dialog.wait_window()
        return result["value"]

    def _back_to_column_selector(self) -> None:
        if not hasattr(self.app, '_last_raw_data') or self.app._last_raw_data is None:
            messagebox.showwarning(
                "Ошибка",
                "Исходные данные не сохранены.\n"
                "Повторный импорт возможен только сразу после загрузки файла."
            )
            return

        self._close()

        from nextt.parsing.column_selector import ColumnSelector

        file_path = getattr(self.app, '_last_file_path', '')
        file_type = getattr(self.app, '_last_file_type', 'excel')

        if file_type == 'pdf':
            if hasattr(self.app, 'main_window'):
                self.app.main_window._load_pdf_file(file_path, append_mode=True)
        else:
            strategy_data = {
                "По умолчанию": self.app._last_raw_data,
                "Линии": self.app._last_raw_data,
                "Сниппеты": self.app._last_raw_data,
            }
            selector = ColumnSelector(self.app.root, strategy_data, file_path, self.font_manager)
            result = selector.select()

            if result[0] is None:
                return

            pairs = result[0]
            for name_col, qty_col in pairs:
                if hasattr(self.app, 'main_window'):
                    self.app.main_window._process_excel_foreign_data(
                        self.app._last_raw_data, name_col, qty_col, file_path, append_mode=True
                    )

    def _export(self) -> None:
        try:
            if self._spec_data is None or self._spec_data.empty:
                messagebox.showwarning("Экспорт", "Нет данных для экспорта")
                return

            # Убеждаемся, что столбец «Тип монтажа» есть (его добавит ExcelWriter)
            self._ensure_mount_type_column()

            downloads_folder = Path.home() / "Downloads"
            if not downloads_folder.exists():
                downloads_folder = Path.home() / "Загрузки"
            if not downloads_folder.exists():
                downloads_folder = Path.home()

            nextt_folder = downloads_folder / "NexTT"
            nextt_folder.mkdir(exist_ok=True)

            logger.info(f"Папка для сохранения: {nextt_folder}")

            from datetime import datetime
            now = datetime.now()
            date_str = now.strftime("%Y-%m-%d")
            time_str = now.strftime("%H-%M")

            base_name = f"Расчёт стоимости_{date_str}_{time_str}"
            file_path = nextt_folder / f"{base_name}.xlsx"

            counter = 1
            while file_path.exists():
                file_path = nextt_folder / f"{base_name}_{counter}.xlsx"
                counter += 1

            logger.info(f"Сохраняем в: {file_path}")

            from nextt.export.excel_writer import ExcelWriter
            writer = ExcelWriter(data_provider=self.app.data_provider)

            correspondence_df = None
            if hasattr(self.app, '_all_correspondence_data_for_export') and self.app._all_correspondence_data_for_export is not None:
                if not self.app._all_correspondence_data_for_export.empty:
                    correspondence_df = self.app._all_correspondence_data_for_export.copy()
                    correspondence_df = correspondence_df.rename(columns={
                        'Наименование': 'Оригинальное наименование',
                        'Кол-во': 'Количество',
                        'Источник': 'Источник подбора',
                    })
                    logger.info(f"Экспорт: используем _all_correspondence_data_for_export, {len(correspondence_df)} строк")

            if correspondence_df is None and hasattr(self.app, '_all_correspondence_data') and self.app._all_correspondence_data is not None:
                if not self.app._all_correspondence_data.empty:
                    correspondence_df = self.app._all_correspondence_data.copy()
                    correspondence_df = correspondence_df.rename(columns={
                        'Наименование': 'Оригинальное наименование',
                        'Кол-во': 'Количество',
                        'Источник': 'Источник подбора',
                    })
                    logger.info(f"Экспорт: используем _all_correspondence_data, {len(correspondence_df)} строк")

            if correspondence_df is None and hasattr(self.app, '_last_correspondence_dialog'):
                dialog = self.app._last_correspondence_dialog
                if hasattr(dialog, 'get_correspondence_data'):
                    correspondence_df = dialog.get_correspondence_data()
                    logger.info(f"Экспорт: используем данные из диалога, {len(correspondence_df) if correspondence_df is not None else 0} строк")

            writer.save(self._spec_data, str(file_path), correspondence_data=correspondence_df, program_name=self.app.root.title())

            if platform.system() == "Windows":
                os.startfile(str(file_path))
            elif platform.system() == "Darwin":
                subprocess.call(["open", str(file_path)])
            else:
                subprocess.call(["xdg-open", str(file_path)])

        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось сохранить:\n{str(e)}")
            logger.error(f"Ошибка экспорта: {e}")
            import traceback
            logger.error(traceback.format_exc())

    def _back_to_correspondence(self) -> None:
        self._close()

        if hasattr(self.app, '_last_correspondence_data') and self.app._last_correspondence_data is not None:
            if not self.app._last_correspondence_data.empty:
                from nextt.ui.dialogs.correspondence import CorrespondenceDialog
                dialog = CorrespondenceDialog(self.app)
                self.app._last_correspondence_dialog = dialog
                dialog.show(self.app._last_correspondence_data)
                return

        messagebox.showinfo("Информация", "Нет данных для редактирования.\nСначала загрузите спецификацию.")

    def _close(self) -> None:
        # Сохраняем состояние чекбокса «Подсказка» в settings.json
        try:
            from nextt.config import config
            config.set("preview_show_images", bool(self._show_images_var.get()))
        except Exception as e:
            logger.debug(f"Не удалось сохранить состояние чекбокса «Подсказка»: {e}")

        self._hide_header_tooltip()
        self._hide_bracket_image_immediate()
        if self._dialog:
            self._dialog.destroy()
            self._dialog = None
            self._tree = None