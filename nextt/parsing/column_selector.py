"""
Диалог выбора столбцов для импорта спецификации.
С поддержкой масштабирования шрифтов.
Поддерживает выбор нескольких пар столбцов (Наименование + Количество).
"""

import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional, Tuple, List, Dict
import os
import pandas as pd
import re


class ColumnSelector:
    """Диалог выбора столбцов наименования и количества с вкладками стратегий."""

    def __init__(self, parent, data_source, file_path: str, font_manager=None):
        """
        Args:
            parent: родительское окно
            data_source: Dict[str, pd.DataFrame] — словарь с DataFrame'ами по стратегиям
                         или pd.DataFrame — один DataFrame (для обратной совместимости)
            file_path: путь к файлу
            font_manager: экземпляр FontManager для масштабирования шрифтов
        """
        self.parent = parent
        self.file_path = file_path
        self.font_manager = font_manager
        
        # Поддерживаем и старый формат (один DataFrame), и новый (словарь)
        if isinstance(data_source, dict):
            strategy_name_map = {
                "По умолчанию": "📋 Стандартная",
                "Линии": "📏 Линейная",
                "Сниппеты": "📝 Текстовая",
            }
            self.strategy_data = {}
            for old_name, df in data_source.items():
                new_name = strategy_name_map.get(old_name, old_name)
                self.strategy_data[new_name] = df
        else:
            self.strategy_data = {"📋 Данные": data_source}
        
        self._result: Tuple[Optional[List[Tuple[int, int]]], Optional[str]] = (None, None)

        # Для каждой вкладки храним свой выбор
        self.tab_state: Dict[str, dict] = {}
        for strategy_name in self.strategy_data.keys():
            self.tab_state[strategy_name] = {
                "selected_columns": [],
                "selected_name_cols": [],
                "selected_qty_cols": [],
                "tree": None,
                "full_data": [],
                "filtered_columns": [],
                "visible_columns": [],
                "column_widths": {},
                "bg_color": "#FFFFFF",
            }

        # Виджеты
        self._dialog: Optional[tk.Toplevel] = None
        self._notebook: Optional[ttk.Notebook] = None
        self._tab_frames: Dict[str, tk.Frame] = {}
        self._current_strategy: Optional[str] = None
        self._pairs_listbox: Optional[tk.Listbox] = None
        self._pairs_frame: Optional[ttk.Frame] = None

    def select(self) -> Tuple[Optional[List[Tuple[int, int]]], Optional[str]]:
        """Показывает диалог и возвращает (список_пар, strategy_name)."""
        self._create_dialog()
        if self._dialog:
            self._dialog.wait_window()
        return self._result

    # ==================================================================
    # ЦВЕТА ДЛЯ ФОНА ВКЛАДОК
    # ==================================================================
    
    TAB_BG_COLORS = {
        "📋 Стандартная": "#E3F2FD",
        "📏 Линейная":   "#E8F5E9",
        "📝 Текстовая":  "#FFF3E0",
    }

    # ==================================================================
    # ДИАЛОГ
    # ==================================================================

    def _create_dialog(self) -> None:
        """Создаёт окно диалога (без вкладок)."""
        self._dialog = tk.Toplevel(self.parent)
        
        from nextt.utils.window_manager import setup_dialog_window
        setup_dialog_window(self._dialog, f"Мастер импорта спецификации — {os.path.basename(self.file_path)}")

        screen_w = self._dialog.winfo_screenwidth()
        screen_h = self._dialog.winfo_screenheight()
        self._dialog.geometry(f"{screen_w}x{screen_h - 70}+0+0")
        self._dialog.configure(bg='#f5f5f5')

        if self.font_manager:
            default_font = self.font_manager.get_default_font()
            heading_font = self.font_manager.get_heading_font()
            bold_font = self.font_manager.get_bold_font()
        else:
            default_font = ("Segoe UI", 9)
            heading_font = ("Segoe UI", 9, "bold")
            bold_font = ("Segoe UI", 9, "bold")

        style = ttk.Style()
        style.configure("ColumnSelector.Treeview", rowheight=25, font=default_font)
        style.configure("ColumnSelector.Treeview.Heading", font=heading_font)

        main_frame = ttk.Frame(self._dialog)
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # --- Заголовок ---
        header = ttk.Frame(main_frame)
        header.pack(fill="x", pady=(0, 12))

        ttk.Label(header, text="📋 ШАГ 1: ВЫБОР СТОЛБЦОВ ДЛЯ ИМПОРТА",
                  font=heading_font, foreground="#2c3e50",
                  background="#f5f5f5").pack(anchor="w", pady=(0, 8))

        instruction = (
            "1. Нажмите на заголовок столбца с названиями радиаторов — столбец станет «Наименование»\n"
            "2. Нажмите на заголовок столбца с количеством — столбец станет «Количество»\n"
            "3. Вы можете выбрать несколько пар (Наименование + Количество) последовательно\n"
            "4. Цвет фона таблицы показывает состояние: красный — ничего не выбрано, "
            "жёлтый — выбран Наименование, зелёный — выбрана полная пара\n"
            "5. Кнопка «Продолжить» активна только когда выбрана чётная пара (зелёный фон)\n"
            "6. Для отмены выбора столбца — нажмите на него ещё раз"
        )
        ttk.Label(header, text=instruction, font=default_font,
                  foreground="#34495e", background="#f5f5f5",
                  justify="left").pack(anchor="w")

        # --- Таблица (без вкладок) ---
        strategy_names = list(self.strategy_data.keys())
        if strategy_names:
            self._current_strategy = strategy_names[0]
            df = self.strategy_data[self._current_strategy]
            bg_color = self.TAB_BG_COLORS.get(self._current_strategy, "#FFFFFF")
            
            table_container = tk.Frame(main_frame, bg=bg_color)
            table_container.pack(fill="both", expand=True, pady=(10, 15))
            
            self._create_tab_content(table_container, self._current_strategy, df, bg_color)
        else:
            ttk.Label(
                main_frame,
                text="Нет данных для отображения.\nПопробуйте другой файл.",
                font=default_font,
                foreground="#888888"
            ).pack(expand=True)

        # --- Панель управления ---
        control = ttk.Frame(main_frame)
        control.pack(fill="x")

        self._global_selection_info = ttk.Label(
            control,
            text="🔴 Ничего не выбрано. Нажмите на заголовок столбца для выбора...",
            font=default_font, foreground="#34495e", background="#f5f5f5"
        )
        self._global_selection_info.pack(side="left", anchor="w")

        btn_frame = ttk.Frame(control)
        btn_frame.pack(side="right")

        self._global_confirm_btn = ttk.Button(
            btn_frame, text="Продолжить", command=self._on_confirm,
            width=20, state="disabled"
        )
        self._global_confirm_btn.pack(side="left", padx=(0, 10))

        ttk.Button(btn_frame, text="Закрыть", command=self._on_cancel, width=15).pack(side="left")

        self._dialog.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self._dialog.bind("<Escape>", lambda e: self._on_cancel())
        
        self._update_global_info()

    def _create_tab_content(self, parent: tk.Frame, strategy_name: str, df: pd.DataFrame, bg_color: str) -> None:
        """Создаёт содержимое вкладки: таблицу с данными."""
        state = self.tab_state[strategy_name]
        
        if self.font_manager:
            default_font = self.font_manager.get_default_font()
            heading_font = self.font_manager.get_heading_font()
        else:
            default_font = ("Segoe UI", 9)
            heading_font = ("Segoe UI", 9, "bold")
        
        # Фильтруем столбцы
        filtered_columns = []
        for col_idx in range(len(df.columns)):
            col_data = df.iloc[:, col_idx]
            non_nan_values = col_data.dropna().astype(str)

            has_real_data = False
            for val in non_nan_values:
                val_clean = val.strip()
                if not val_clean:
                    continue
                if val_clean in ['0', '0.0', '0,0', '0.00', '0,00']:
                    continue
                if val_clean.startswith('='):
                    continue
                if not any(c.isalnum() for c in val_clean):
                    continue
                has_real_data = True
                break

            if has_real_data:
                filtered_columns.append(col_idx)

        if not filtered_columns:
            filtered_columns = [0]

        state["filtered_columns"] = filtered_columns
        visible_columns = list(range(len(filtered_columns)))
        state["visible_columns"] = visible_columns

        # Таблица
        table_container = tk.Frame(parent, bg=bg_color)
        table_container.pack(fill="both", expand=True, padx=5, pady=5)

        tree = ttk.Treeview(
            table_container,
            columns=visible_columns,
            show="headings",
            height=20,
            selectmode="none",
            style="ColumnSelector.Treeview"
        )
        state["tree"] = tree

        # Восстанавливаем сохранённые пользователем ширины
        for col in visible_columns:
            orig_col_num = filtered_columns[col] + 1
            tree.heading(col, text=str(orig_col_num))
            # ВАЖНО: используем сохранённую пользователем ширину, если она есть
            saved_width = state["column_widths"].get(col)
            if saved_width is None:
                saved_width = 150  # только если нет сохранённой ширины
            tree.column(col, width=saved_width, anchor="center", minwidth=50)

        # Данные
        full_data = []
        for r_idx in range(len(df)):
            row_data = []
            for orig_col_idx in filtered_columns:
                cell_value = df.iloc[r_idx, orig_col_idx]
                display_value = " " if pd.isna(cell_value) else str(cell_value)
                row_data.append(display_value)
            full_data.append(row_data)
        state["full_data"] = full_data

        self._fill_treeview(tree, full_data)
        self._update_table_color(tree, state)

        # Обработчики клика по заголовкам
        for col in visible_columns:
            tree.heading(col, command=lambda idx=col, s=strategy_name: self._on_header_click(s, idx))

        # ==================================================================
        # СОХРАНЕНИЕ ШИРИНЫ КОГДА ПОЛЬЗОВАТЕЛЬ МЕНЯЕТ СТОЛБЕЦ
        # ==================================================================
        def on_column_resize(event):
            """Сохраняет ширину столбца сразу после изменения."""
            # Сохраняем текущие ширины ВСЕХ столбцов
            try:
                for col in visible_columns:
                    current_width = tree.column(col, 'width')
                    if current_width is not None and current_width > 0:
                        state["column_widths"][col] = current_width
            except (tk.TclError, ValueError):
                pass
        
        # Привязываемся к событию изменения столбца
        tree.bind('<<TreeviewColumnResized>>', on_column_resize)

        # Скроллбары
        v_scrollbar = ttk.Scrollbar(table_container, orient="vertical", command=tree.yview)
        h_scrollbar = ttk.Scrollbar(table_container, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=v_scrollbar.set, xscrollcommand=h_scrollbar.set)

        tree.grid(row=0, column=0, sticky="nsew")
        v_scrollbar.grid(row=0, column=1, sticky="ns")
        h_scrollbar.grid(row=1, column=0, sticky="ew")
        table_container.grid_rowconfigure(0, weight=1)
        table_container.grid_columnconfigure(0, weight=1)

    # def _save_column_widths(self, strategy_name: str) -> None:
    #     """Сохраняет текущие ширины столбцов в state."""
    #     state = self.tab_state.get(strategy_name)
    #     if not state or state["tree"] is None:
    #         return

    #     tree = state["tree"]
    #     try:
    #         for col in state["visible_columns"]:
    #             current_width = tree.column(col, 'width')
    #             if current_width is not None and current_width > 0:
    #                 state["column_widths"][col] = current_width
    #     except (tk.TclError, ValueError):
    #         pass

    def _fill_treeview(self, tree: ttk.Treeview, full_data: List[List[str]]) -> None:
        """Заполняет Treeview данными."""
        for item in tree.get_children():
            tree.delete(item)

        for row_data in full_data:
            clean_row = []
            for cell in row_data:
                if pd.isna(cell) or cell is None:
                    clean_row.append("")
                else:
                    cell_str = str(cell)
                    clean_cell = cell_str.replace('\r', ' ').replace('\n', ' ')
                    clean_cell = ' '.join(clean_cell.split())
                    clean_row.append(clean_cell)
            tree.insert("", "end", values=clean_row)

    def _update_table_color(self, tree: ttk.Treeview, state: dict) -> None:
        """Обновляет цвет таблицы."""
        selected_count = len(state["selected_columns"])
        
        if selected_count == 0:
            color = "#ffe6e6"
        elif selected_count % 2 == 1:
            color = "#fff9e6"
        else:
            color = "#e6ffe6"

        tag_name = "table_highlight"
        tree.tag_configure(tag_name, background=color)

        for item in tree.get_children():
            tags = list(tree.item(item, "tags"))
            if tag_name in tags:
                tags.remove(tag_name)
            tags.append(tag_name)
            tree.item(item, tags=tags)

    def _on_header_click(self, strategy_name: str, col_idx: int) -> None:
        """Обрабатывает клик по заголовку столбца."""
        state = self.tab_state.get(strategy_name)
        if state is None:
            return
        
        tree = state["tree"]
        if tree is None:
            return
        
        filtered_columns = state["filtered_columns"]
        visible_columns = state["visible_columns"]
        
        if col_idx in state["selected_columns"]:
            pos = state["selected_columns"].index(col_idx)
            to_remove = state["selected_columns"][pos:]
            state["selected_columns"] = state["selected_columns"][:pos]
            
            for col in to_remove:
                for i, vis_col in enumerate(visible_columns):
                    if vis_col == col:
                        tree.heading(i, text=str(filtered_columns[i] + 1))
                        break
            
            new_name_cols = []
            new_qty_cols = []
            for i, col in enumerate(state["selected_columns"]):
                if i % 2 == 0:
                    new_name_cols.append(col)
                else:
                    new_qty_cols.append(col)
            state["selected_name_cols"] = new_name_cols
            state["selected_qty_cols"] = new_qty_cols
            
        else:
            state["selected_columns"].append(col_idx)
            
            if len(state["selected_columns"]) % 2 == 1:
                state["selected_name_cols"].append(col_idx)
                for i, vis_col in enumerate(visible_columns):
                    if vis_col == col_idx:
                        tree.heading(i, text="Наименование")
                        break
            else:
                state["selected_qty_cols"].append(col_idx)
                for i, vis_col in enumerate(visible_columns):
                    if vis_col == col_idx:
                        tree.heading(i, text="Количество")
                        break
        
        self._update_table_color(tree, state)
        self._update_global_info()

    def _update_global_info(self) -> None:
        """Обновляет статусную строку и кнопку Продолжить."""
        if self._current_strategy is None:
            return
        
        state = self.tab_state.get(self._current_strategy)
        if state is None:
            return
        
        selected_columns = state["selected_columns"]
        selected_count = len(selected_columns)
        tree = state["tree"]
        
        all_empty = all(s["tree"] is None for s in self.tab_state.values())
        if all_empty:
            self._global_selection_info.config(text="❌ Нет данных. Попробуйте другой PDF.")
            self._global_confirm_btn.config(state="disabled")
            return
        
        if tree is None:
            self._global_selection_info.config(
                text=f"ℹ️ Вкладка «{self._current_strategy}» не содержит данных. Переключитесь на другую."
            )
            self._global_confirm_btn.config(state="disabled")
            return
        
        if selected_count == 0:
            self._global_selection_info.config(
                text="🔴 Ничего не выбрано. Нажмите на заголовок столбца для выбора..."
            )
            self._global_confirm_btn.config(state="disabled")
        elif selected_count % 2 == 1:
            name_col = selected_columns[-1]
            name_num = state["filtered_columns"][name_col] + 1
            self._global_selection_info.config(
                text=f"🟡 Выбрано Наименование (столбец {name_num}). Теперь выберите столбец Количество"
            )
            self._global_confirm_btn.config(state="disabled")
        else:
            pairs_count = selected_count // 2
            self._global_selection_info.config(
                text=f"✅ Выбрано {pairs_count} пар столбцов. Нажмите «Продолжить» для импорта"
            )
            self._global_confirm_btn.config(state="normal")

    def _on_confirm(self) -> None:
        """Подтверждение выбора."""
        if self._current_strategy is None:
            messagebox.showwarning("Ошибка", "Нет активной вкладки.")
            return
        
        state = self.tab_state[self._current_strategy]
        
        if len(state["selected_columns"]) == 0:
            messagebox.showwarning("Ничего не выбрано", "Выберите хотя бы одну пару столбцов.")
            return
        
        if len(state["selected_columns"]) % 2 != 0:
            messagebox.showwarning(
                "Неполная пара",
                "Вы выбрали нечётное количество столбцов.\n"
                "Каждая пара должна состоять из столбца Наименование и столбца Количество."
            )
            return
        
        pairs = []
        for i in range(0, len(state["selected_columns"]), 2):
            name_col = state["selected_columns"][i]
            qty_col = state["selected_columns"][i + 1]
            
            if name_col == qty_col:
                messagebox.showwarning("Ошибка", "Столбец не может быть одновременно Наименованием и Количеством.")
                return
            
            name_col_original = state["filtered_columns"][name_col]
            qty_col_original = state["filtered_columns"][qty_col]
            pairs.append((name_col_original, qty_col_original))
        
        self._result = (pairs, self._current_strategy)
        self._dialog.destroy()

    def _on_cancel(self) -> None:
        """Отмена выбора."""
        self._result = (None, None)
        if self._dialog:
            self._dialog.destroy()