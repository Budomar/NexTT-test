"""
Окно предпросмотра спецификации.
Полная версия — как в оригинале: подсказки, копирование в буфер, жирные заголовки,
скидки, правильное добавление кронштейнов.
С поддержкой масштабирования шрифтов.
ДОБАВЛЕНО: редактирование количества кронштейнов (двойной клик),
           удаление строк с кронштейнами (Delete и контекстное меню).
"""

import tkinter as tk
from tkinter import ttk, messagebox
import os
import tempfile
import subprocess
import platform
from typing import Optional

import pandas as pd

from nextt.logger import get_logger
from nextt.utils.window_manager import get_safe_geometry

logger = get_logger(__name__)


class PreviewDialog:
    """Диалог предпросмотра спецификации."""

    def __init__(self, app):
        """
        Args:
            app: экземпляр App (координатор)
        """
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
        self._create_dialog()

    def _create_dialog(self) -> None:
        """Создаёт окно предпросмотра."""
        self._dialog = tk.Toplevel(self.app.root)
        
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
            "№", "Артикул", "Наименование", "Мощность, Вт",
            "Цена, руб (с НДС)", "Скидка, %",
            "Цена со скидкой, руб (с НДС)", "Кол-во",
            "Сумма, руб (с НДС)"
        ]
        self._tree = ttk.Treeview(tree_frame, columns=columns, show="headings", height=15)

        col_widths = {
            "№": 50, "Артикул": 100, "Наименование": 370, "Мощность, Вт": 100,
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
            else:
                self._tree.heading(col, text=col)
            anchor = "e" if col in money_cols else ("w" if col == "Наименование" else "center")
            self._tree.column(col, width=col_widths.get(col, 100), anchor=anchor)

        self._tree.tag_configure("radiator", background="#fafafa")
        self._tree.tag_configure("bracket", background="#ededed")
        self._tree.tag_configure("total", background="#d9d9d9", font=bold_font)

        self._fill_tree()

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
        # Двойной клик для редактирования количества (только для кронштейнов)
        self._tree.bind("<Double-1>", self._on_double_click)
        # Клавиша Delete для удаления выделенной строки (только для кронштейнов)
        self._tree.bind("<Delete>", self._on_delete_key)
        # Контекстное меню (правой кнопкой)
        self._context_menu = tk.Menu(self._tree, tearoff=0)
        self._context_menu.add_command(label="🗑️ Удалить строку", command=self._delete_selected_row)
        self._tree.bind("<Button-3>", self._show_context_menu)

        # --- Итоги ---
        totals_frame = ttk.Frame(main_frame)
        totals_frame.pack(fill="x", pady=10)

        tp, tw, tv = self.app.spec_generator.calculate_totals(self._spec_data)
        self._power_label = ttk.Label(
            totals_frame,
            text=f"Суммарная мощность: {self.app.spec_generator.format_power(tp)}",
            font=bold_font
        )
        self._power_label.grid(row=0, column=0, padx=15, sticky="w")
        self._weight_label = ttk.Label(
            totals_frame,
            text=f"Общий вес: {self.app.spec_generator.format_weight(tw)}",
            font=bold_font
        )
        self._weight_label.grid(row=0, column=1, padx=15, sticky="w")
        self._volume_label = ttk.Label(
            totals_frame,
            text=f"Общий объём: {tv:.5f} м³",
            font=bold_font
        )
        self._volume_label.grid(row=0, column=2, padx=15, sticky="w")

        # --- Блок скидок ---
        discount_frame = ttk.Frame(totals_frame)
        discount_frame.grid(row=0, column=3, padx=(50, 0), sticky="e")

        ttk.Label(discount_frame, text="Скидка на радиаторы, %:", font=default_font).pack(side="left")
        self._radiator_discount_var = tk.StringVar(
            value=self.app.main_window.radiator_discount_var.get()
        )
        rad_entry = ttk.Entry(
            discount_frame,
            textvariable=self._radiator_discount_var,
            width=5,
            font=default_font,
            validate="key",
            validatecommand=(discount_frame.register(self._validate_discount), '%P')
        )
        rad_entry.pack(side="left", padx=2)
        self._radiator_discount_var.trace_add("write", self._on_discount_changed)

        ttk.Label(discount_frame, text="кронштейны, %:", font=default_font).pack(side="left", padx=(10, 0))
        self._bracket_discount_var = tk.StringVar(
            value=self.app.main_window.bracket_discount_var.get()
        )
        br_entry = ttk.Entry(
            discount_frame,
            textvariable=self._bracket_discount_var,
            width=5,
            font=default_font,
            validate="key",
            validatecommand=(discount_frame.register(self._validate_discount), '%P')
        )
        br_entry.pack(side="left", padx=2)
        self._bracket_discount_var.trace_add("write", self._on_discount_changed)

        totals_frame.columnconfigure(3, weight=1)

        # --- Кнопки ---
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill="x", pady=10)

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

        # ========== КНОПКИ СПРАВА (ПРАВИЛЬНЫЙ ПОРЯДОК) ==========
        # При side="right" порядок добавления обратный видимому:
        # добавляем Закрыть (будет справа), потом Экспорт, потом Назад, потом К выбору столбцов
        
        # 1. Самая правая кнопка — Закрыть
        ttk.Button(btn_frame, text="Закрыть",
                   command=self._close).pack(side="right", padx=5)
        
        # 2. Кнопка "Экспорт в Excel"
        ttk.Button(btn_frame, text="Экспорт в Excel",
                   command=self._export).pack(side="right", padx=5)
        
        # 3. Кнопка "Назад к подбору аналогов"
        ttk.Button(btn_frame, text="← Назад к подбору аналогов",
                   command=self._back_to_correspondence).pack(side="right", padx=5)
        
        # 4. НОВАЯ КНОПКА — самая левая в группе — К выбору столбцов
        ttk.Button(btn_frame, text="← Назад к выбору столбцов",
                   command=self._back_to_column_selector).pack(side="right", padx=5)
        # =========================================================

        self._dialog.protocol("WM_DELETE_WINDOW", self._close)
    # ==================================================================
    # РЕДАКТИРОВАНИЕ КОЛИЧЕСТВА КРОНШТЕЙНОВ (ДВОЙНОЙ КЛИК)
    # ==================================================================

    def _on_double_click(self, event) -> None:
        """Обработчик двойного клика — редактирование количества только для кронштейнов."""
        region = self._tree.identify("region", event.x, event.y)
        if region != "cell":
            return

        column = self._tree.identify_column(event.x)
        item = self._tree.identify_row(event.y)

        if not item or not column:
            return

        if column != "#8":
            return

        values = self._tree.item(item, "values")
        if not values or len(values) < 3:
            return

        name = values[2] if len(values) > 2 else ""
        if values[0] == "Итого" or "Кронштейн" not in name:
            return

        current_qty = values[7] if len(values) > 7 else "0"

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
        """Завершает редактирование."""
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
            if len(values) < 9:
                return

            # Сохраняем старые значения для проверки изменений
            old_qty = int(values[7]) if values[7] else 0
            if old_qty == new_qty:
                # Количество не изменилось — ничего не делаем
                return

            values[7] = str(new_qty)

            try:
                price_disc = float(values[6].replace(',', '.').replace(' ', '')) if values[6] else 0.0
                new_total = round(price_disc * new_qty, 2)
                values[8] = f"{new_total:,.2f}".replace(',', ' ') + "   "
            except (ValueError, TypeError):
                pass

            self._tree.item(self._edit_item, values=values)

            # Обновляем _spec_data
            art = values[1] if len(values) > 1 else ""
            name = values[2] if len(values) > 2 else ""

            for idx in self._spec_data.index:
                if (str(self._spec_data.at[idx, "Артикул"]) == str(art) and
                    str(self._spec_data.at[idx, "Наименование"]) == str(name)):
                    self._spec_data.at[idx, "Кол-во"] = new_qty
                    self._spec_data.at[idx, "Сумма, руб (с НДС)"] = new_total
                    break

            # ========== ОПТИМАЛЬНОЕ РЕШЕНИЕ: пересчитываем таблицу ==========
            # Вызываем _recalculate_table, который обновит все строки и итоги
            self._recalculate_table()

        except Exception as e:
            logger.error(f"Ошибка при редактировании: {e}")

        finally:
            if self._edit_entry:
                self._edit_entry.destroy()
                self._edit_entry = None
            self._edit_item = None

    def _cancel_editing(self, event=None) -> None:
        """Отменяет редактирование."""
        if self._edit_entry:
            self._edit_entry.destroy()
            self._edit_entry = None
        self._edit_item = None

    # ==================================================================
    # УДАЛЕНИЕ СТРОКИ (DELETE ИЛИ КОНТЕКСТНОЕ МЕНЮ)
    # ==================================================================

    def _on_delete_key(self, event=None) -> None:
        """Обработчик клавиши Delete — удаляет выделенную строку (только кронштейны)."""
        self._delete_selected_row()

    def _show_context_menu(self, event) -> None:
        """Показывает контекстное меню."""
        item = self._tree.identify_row(event.y)
        if item:
            values = self._tree.item(item, "values")
            if values and values[0] != "Итого" and "Кронштейн" in str(values[2]):
                self._tree.selection_set(item)
                self._context_menu.post(event.x_root, event.y_root)

    def _delete_selected_row(self) -> None:
        """Удаляет выделенную строку (только если это кронштейн)."""
        selected = self._tree.selection()
        if not selected:
            return

        item = selected[0]
        values = self._tree.item(item, "values")

        if not values:
            return

        if values[0] == "Итого":
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

        # Удаляем из Treeview
        self._tree.delete(item)

        # Удаляем из _spec_data
        art = values[1] if len(values) > 1 else ""
        name = values[2] if len(values) > 2 else ""

        for idx in self._spec_data.index:
            if (str(self._spec_data.at[idx, "Артикул"]) == str(art) and
                str(self._spec_data.at[idx, "Наименование"]) == str(name)):
                self._spec_data = self._spec_data.drop(idx)
                break

        self._spec_data = self._spec_data.reset_index(drop=True)

        # Обновляем нумерацию
        for new_idx, idx in enumerate(self._spec_data.index):
            self._spec_data.at[idx, "№"] = new_idx + 1

        # Перестраиваем таблицу
        self._fill_tree()

        # Обновляем итоги
        self._update_totals()

        logger.info(f"Удалена строка с кронштейном: {name}")

    def _update_totals(self) -> None:
        """Обновляет итоговые метки."""
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
        """Пересчитывает цены и суммы с учётом скидок."""
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
            if values[0] == "Итого":
                continue

            if len(values) < 9:
                continue

            name = values[2] if len(values) > 2 else ""
            is_bracket = "Кронштейн" in str(name)

            try:
                base_price = float(values[4].replace(',', '.').replace(' ', '')) if values[4] else 0.0
            except (ValueError, TypeError):
                base_price = 0.0

            try:
                qty = int(values[7]) if values[7] else 0
            except (ValueError, TypeError):
                qty = 0

            disc = br_disc if is_bracket else rad_disc
            new_price = round(base_price * (1 - disc / 100), 2)
            new_total = round(new_price * qty, 2)

            values[5] = f"{disc:.2f}".replace('.', ',')
            values[6] = fmt_money(new_price)
            values[8] = fmt_money(new_total)

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
            if last_values and last_values[0] == "Итого":
                last_values[7] = f"{total_rad_qty} / {total_br_qty}"
                last_values[8] = fmt_money(total_sum)
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
        items = self._tree.get_children()
        articles = []
        for item in items:
            values = self._tree.item(item, "values")
            if values and values[0] != "Итого":
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
        items = self._tree.get_children()
        quantities = []
        for item in items:
            values = self._tree.item(item, "values")
            if values and values[0] != "Итого":
                qty = values[7].strip() if len(values) > 7 else ""
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
        for item in self._tree.get_children():
            self._tree.delete(item)

        def fmt_money(v):
            try:
                return f"{float(v):,.2f}".replace(',', ' ') + "   "
            except (ValueError, TypeError):
                return ""

        for _, row in self._spec_data.iterrows():
            is_bracket = "Кронштейн" in str(row["Наименование"])
            power = "" if is_bracket else (
                str(round(float(row["Мощность, Вт"]))) if row["Мощность, Вт"] else ""
            )
            self._tree.insert("", "end", values=[
                row["№"], row["Артикул"], row["Наименование"], power,
                fmt_money(row["Цена, руб (с НДС)"]),
                f"{float(row['Скидка, %']):.2f}".replace('.', ','),
                fmt_money(row["Цена со скидкой, руб (с НДС)"]),
                row["Кол-во"],
                fmt_money(row["Сумма, руб (с НДС)"])
            ], tags=("bracket" if is_bracket else "radiator",))

        total_qty_rad = sum(
            int(row["Кол-во"]) for _, row in self._spec_data.iterrows()
            if "Кронштейн" not in str(row["Наименование"])
        )
        total_qty_br = sum(
            int(row["Кол-во"]) for _, row in self._spec_data.iterrows()
            if "Кронштейн" in str(row["Наименование"])
        )
        total_sum = self._spec_data["Сумма, руб (с НДС)"].sum()
        self._tree.insert("", "end", values=[
            "Итого", "", "", "", "", "", "",
            f"{total_qty_rad} / {total_qty_br}", fmt_money(total_sum)
        ], tags=("total",))

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
        if mask.any():
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

            def fmt(v):
                return f"{float(v):,.2f}".replace(',', ' ') + "   "

            new_row_num = len(self._spec_data) + 1
            new_row = {
                "№": new_row_num,
                "Артикул": bracket['article'],
                "Наименование": bracket['name'],
                "Мощность, Вт": 0.0,
                "Цена, руб (с НДС)": price,
                "Скидка, %": br_disc,
                "Цена со скидкой, руб (с НДС)": disc_price,
                "Кол-во": qty,
                "Сумма, руб (с НДС)": total,
            }

            self._spec_data = pd.concat([self._spec_data, pd.DataFrame([new_row])], ignore_index=True)
            self._fill_tree()
            self._qty_entry.delete(0, tk.END)
            self._update_totals()

    def _back_to_column_selector(self) -> None:
        """Возврат к окну выбора столбцов для переназначения."""
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
            # Для PDF перезапускаем весь процесс загрузки с append_mode=True
            # Вызываем метод _load_pdf_file из main_window с append_mode=True
            if hasattr(self.app, 'main_window'):
                self.app.main_window._load_pdf_file(file_path, append_mode=True)
        else:
            # Для Excel/Word используем словарь стратегий
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

    # ==================================================================
    # ЭКСПОРТ
    # ==================================================================

    def _export(self) -> None:
        try:
            if self._spec_data is None or self._spec_data.empty:
                messagebox.showwarning("Экспорт", "Нет данных для экспорта")
                return

            temp_dir = tempfile.gettempdir()
            base_name = "Расчёт стоимости"
            file_path = os.path.join(temp_dir, f"{base_name}.xlsx")
            counter = 1
            while os.path.exists(file_path):
                file_path = os.path.join(temp_dir, f"{base_name}_{counter}.xlsx")
                counter += 1
                if counter > 1000000000:
                    raise Exception("Не удалось создать уникальное имя файла")

            from nextt.export.excel_writer import ExcelWriter
            writer = ExcelWriter(data_provider=self.app.data_provider)

            correspondence_df = None
            # Сначала проверяем сохранённые данные для экспорта (все строки)
            if hasattr(self.app, '_all_correspondence_data_for_export') and self.app._all_correspondence_data_for_export is not None:
                if not self.app._all_correspondence_data_for_export.empty:
                    correspondence_df = self.app._all_correspondence_data_for_export.copy()
                    # Переименовываем столбцы для ExcelWriter
                    correspondence_df = correspondence_df.rename(columns={
                        'Наименование': 'Оригинальное наименование',
                        'Кол-во': 'Количество',
                        'Источник': 'Источник подбора',
                    })
                    logger.info(f"Экспорт: используем _all_correspondence_data_for_export, {len(correspondence_df)} строк")
            
            # Если нет, пробуем _all_correspondence_data
            if correspondence_df is None and hasattr(self.app, '_all_correspondence_data') and self.app._all_correspondence_data is not None:
                if not self.app._all_correspondence_data.empty:
                    correspondence_df = self.app._all_correspondence_data.copy()
                    correspondence_df = correspondence_df.rename(columns={
                        'Наименование': 'Оригинальное наименование',
                        'Кол-во': 'Количество',
                        'Источник': 'Источник подбора',
                    })
                    logger.info(f"Экспорт: используем _all_correspondence_data, {len(correspondence_df)} строк")
            
            # Если нет, пробуем диалог
            if correspondence_df is None and hasattr(self.app, '_last_correspondence_dialog'):
                dialog = self.app._last_correspondence_dialog
                if hasattr(dialog, 'get_correspondence_data'):
                    correspondence_df = dialog.get_correspondence_data()
                    logger.info(f"Экспорт: используем данные из диалога, {len(correspondence_df) if correspondence_df is not None else 0} строк")

            writer.save(self._spec_data, file_path, correspondence_data=correspondence_df, program_name=self.app.root.title())

            if platform.system() == "Windows":
                os.startfile(file_path)
            elif platform.system() == "Darwin":
                subprocess.call(["open", file_path])
            else:
                subprocess.call(["xdg-open", file_path])

        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось сохранить:\n{str(e)}")
            logger.error(f"Ошибка экспорта: {e}")

    def _back_to_correspondence(self) -> None:
        """Возврат к окну Мастера подбора аналогов."""
        # Закрываем текущее окно предпросмотра
        self._close()

        # Проверяем, есть ли сохранённые данные таблицы соответствия
        if hasattr(self.app, '_last_correspondence_data') and self.app._last_correspondence_data is not None:
            if not self.app._last_correspondence_data.empty:
                from nextt.ui.dialogs.correspondence import CorrespondenceDialog
                dialog = CorrespondenceDialog(self.app)
                self.app._last_correspondence_dialog = dialog
                dialog.show(self.app._last_correspondence_data)
                return

        messagebox.showinfo("Информация", "Нет данных для редактирования.\nСначала загрузите спецификацию.")

    # def _back_to_column_selector(self) -> None:
    #     """Возврат к окну выбора столбцов для переназначения."""
    #     # Проверяем, есть ли сохранённые исходные данные
    #     if not hasattr(self.app, '_last_raw_data') or self.app._last_raw_data is None:
    #         messagebox.showwarning(
    #             "Ошибка",
    #             "Исходные данные не сохранены.\n"
    #             "Повторный импорт возможен только сразу после загрузки файла."
    #         )
    #         return
        
    #     # Закрываем текущее окно предпросмотра
    #     self._close()
        
    #     # Открываем ColumnSelector с сохранёнными исходными данными
    #     from nextt.parsing.column_selector import ColumnSelector
        
    #     file_path = getattr(self.app, '_last_file_path', '')
    #     file_type = getattr(self.app, '_last_file_type', 'excel')
        
    #     # Определяем стратегии в зависимости от типа исходных данных
    #     if file_type == 'pdf':
    #         # Для PDF используем словарь стратегий
    #         strategy_data = {
    #             "По умолчанию": self.app._last_raw_data,
    #             "Линии": self.app._last_raw_data,
    #             "Сниппеты": self.app._last_raw_data,
    #         }
    #         selector = ColumnSelector(self.app.root, strategy_data, file_path, self.font_manager)
    #     else:
    #         # Для Excel/Word используем один DataFrame
    #         selector = ColumnSelector(self.app.root, self.app._last_raw_data, file_path, self.font_manager)
        
    #     result = selector.select()
        
    #     if result[0] is None:
    #         # Пользователь отменил выбор — ничего не делаем
    #         return
        
    #     pairs = result[0]  # список пар (name_col, qty_col)
    #     strategy_name = result[1]
        
    #     # Получаем выбранный DataFrame из стратегии
    #     if strategy_name in ["📋 Стандартная", "📏 Линейная", "📝 Текстовая"]:
    #         df = self.app._last_raw_data
    #     else:
    #         df = self.app._last_raw_data
        
    #     # Обрабатываем ВСЕ пары столбцов
    #     for name_col, qty_col in pairs:
    #         # Используем метод обработки из MainWindow
    #         if hasattr(self.app, 'main_window'):
    #             if file_type == 'pdf':
    #                 self.app.main_window._process_pdf_foreign_data(df, name_col, qty_col, file_path, append_mode=False)
    #             else:
    #                 self.app.main_window._process_excel_foreign_data(df, name_col, qty_col, file_path, append_mode=False)

    # ==================================================================
    # ЗАКРЫТИЕ
    # ==================================================================

    def _close(self) -> None:
        self._hide_header_tooltip()
        if self._dialog:
            self._dialog.destroy()
            self._dialog = None
            self._tree = None