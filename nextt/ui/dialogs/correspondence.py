"""
Диалог таблицы соответствия для подбора аналогов LaggarTT.
Полноценная версия — как в оригинальном CorrespondenceManager.
С поддержкой масштабирования шрифтов.
"""

import tkinter as tk
from tkinter import ttk, messagebox
import re
from typing import Dict, List, Optional, Tuple

import pandas as pd

from nextt.logger import get_logger
from nextt.events import bus, Events

logger = get_logger(__name__)


class CorrespondenceDialog:
    """Диалог таблицы соответствия — Мастер подбора аналогов LaggarTT."""

    def __init__(self, app):
        self.app = app
        self.font_manager = app.font_manager
        self._dialog: Optional[tk.Toplevel] = None
        self._tree: Optional[ttk.Treeview] = None
        self._data: Optional[pd.DataFrame] = None
        self._selection_info: Optional[ttk.Label] = None
        self._instruction_panel: Optional[ttk.Frame] = None
        self._instruction_visible: bool = False
        self._toggle_btn: Optional[ttk.Button] = None
        self._last_selected_item: Optional[str] = None

    def _save_current_state(self) -> None:
        """Сохраняет текущее состояние таблицы соответствия в app."""
        if not self._tree:
            return
        
        try:
            data = []
            for item in self._tree.get_children():
                values = self._tree.item(item, "values")
                if values and len(values) >= 5:
                    data.append({
                        "Наименование": values[0],
                        "Кол-во": values[1],
                        "Наименование LaggarTT": values[2],
                        "Артикул LaggarTT": values[3],
                        "Источник": values[4],
                    })
            
            if data:
                self.app._last_correspondence_data = pd.DataFrame(data)
                logger.info(f"Сохранено состояние таблицы соответствия: {len(data)} строк")
                # Отладочный вывод первых 3 строк
                for i, row in enumerate(data[:3]):
                    logger.info(f"  Строка {i}: Источник={row.get('Источник', '')}")
        except Exception as e:
            logger.error(f"Ошибка сохранения состояния: {e}")

    def show(self, correspondence_df: pd.DataFrame) -> None:
        """Показывает диалог."""
        if self._dialog and self._dialog.winfo_exists():
            self._dialog.lift()
            self._dialog.focus_force()
            return

        self._data = correspondence_df.copy()
        
        # ... остальной код ...
        
        self._create_dialog()
        
        # ========== ДОБАВИТЬ: поднимаем окно наверх ==========
        if self._dialog:
            self._dialog.lift()
            self._dialog.focus_force()

    def _create_dialog(self) -> None:
        """Создаёт окно диалога."""
        self._dialog = tk.Toplevel(self.app.root)
        
        from nextt.utils.window_manager import setup_dialog_window
        setup_dialog_window(self._dialog, "Мастер подбора аналогов LaggarTT")

        screen_w = self._dialog.winfo_screenwidth()
        screen_h = self._dialog.winfo_screenheight()
        self._dialog.geometry(f"{screen_w}x{screen_h - 70}+0+0")
        self._dialog.configure(bg='#f5f5f5')

        default_font = self.font_manager.get_default_font()
        heading_font = self.font_manager.get_heading_font()
        bold_font = self.font_manager.get_bold_font()

        self._dialog.protocol("WM_DELETE_WINDOW", self._close)

        header = ttk.Frame(self._dialog)
        header.pack(fill="x", padx=20, pady=20)

        ttk.Label(header, text="🔍 ШАГ 2: ПРОВЕРКА И УТОЧНЕНИЕ АНАЛОГОВ",
                  font=heading_font, foreground="#2c3e50",
                  background="#f5f5f5").pack(anchor="w", pady=(0, 12))

        ttk.Label(header, text="Программа обработала вашу спецификацию. Вот что получилось:",
                  font=default_font, foreground="#34495e",
                  background="#f5f5f5").pack(anchor="w", pady=(0, 12))

        auto_matched = len(self._data[self._data["Артикул LaggarTT"] != ""])
        manual_needed = len(self._data) - auto_matched

        stats_frame = ttk.Frame(header)
        stats_frame.pack(fill="x", pady=(0, 12))

        stats_data = [
            ("✅ Автоматически подобрано:", auto_matched, "#27ae60"),
            ("⏳ Ожидает ручного выбора:", manual_needed, "#f39c12"),
            ("📋 Всего строк с радиаторами:", len(self._data), "#3498db"),
        ]
        for text, count, color in stats_data:
            card = ttk.Frame(stats_frame, relief="solid", borderwidth=1)
            card.pack(side="left", padx=(0, 20))
            ttk.Label(card, text=text, font=bold_font,
                      foreground=color, background="white", padding=(10, 6)).pack(side="left")
            ttk.Label(card, text=str(count), font=bold_font,
                      foreground="white", background=color, padding=(10, 6)).pack(side="left")

        instruction = (
            "Что делать дальше:\n"
            "1. Просмотрите таблицу ниже и сравните правильность автоматического подбора\n"
            "2. Для любой строки можно выбрать/изменить аналог — выделите строку и нажмите «Выбрать аналог LaggarTT»\n"
            "3. Для удаления строки — нажмите правой кнопкой мыши по строке\n"
            "4. После проверки всех аналогов нажмите «Перенести в матрицу»"
        )
        ttk.Label(header, text=instruction, font=default_font,
                  foreground="#2c3e50", background="#f5f5f5", justify="left").pack(anchor="w")

        main_container = ttk.Frame(self._dialog)
        main_container.pack(fill="both", expand=True, padx=20, pady=(0, 20))

        content = ttk.Frame(main_container)
        content.pack(fill="both", expand=True)

        table_frame = ttk.Frame(content)
        table_frame.pack(side="left", fill="both", expand=True)

        self._instruction_panel = ttk.Frame(content, width=400)
        self._instruction_panel.place(x=2000, y=0, relheight=1)
        self._instruction_panel.pack_propagate(False)

        self._create_instruction_content()
        self._create_data_table(table_frame)

        self._create_control_panel(main_container)

        self._dialog.after(100, self._select_first_row)

    def _create_control_panel(self, parent: ttk.Frame) -> None:
        """Создаёт панель управления."""
        default_font = self.font_manager.get_default_font()
        
        control = ttk.Frame(parent)
        control.pack(fill="x", pady=(10, 0))

        control.columnconfigure(0, weight=1)
        control.columnconfigure(1, weight=0)
        control.rowconfigure(0, weight=0)
        control.rowconfigure(1, weight=0)

        self._selection_info = tk.Message(
            control,
            text="Выделите строку для просмотра деталей...",
            font=default_font,
            foreground="#7f8c8d",
            background="#f5f5f5",
            anchor="w",
            width=800,
            justify="left"
        )
        self._selection_info.grid(row=0, column=0, rowspan=2, sticky="ew", padx=(0, 10))

        btn_frame = ttk.Frame(control)
        btn_frame.grid(row=0, column=1, sticky="e")

        ttk.Button(
            btn_frame,
            text="Выбрать аналог LaggarTT",
            command=self._select_analog_manually,
            width=25
        ).pack(side="left", padx=(0, 10))

        ttk.Button(
            btn_frame,
            text="Перенести в матрицу",
            command=self._transfer_to_matrix,
            width=20
        ).pack(side="left", padx=10)

        ttk.Button(
            btn_frame,
            text="Закрыть",
            command=self._close,
            width=15
        ).pack(side="left", padx=10)

        self._toggle_btn = ttk.Button(
            control,
            text="📚 Показать инструкцию",
            command=self._toggle_instruction,
            width=25
        )
        self._toggle_btn.grid(row=1, column=1, sticky="e", pady=(5, 0))

    def _create_instruction_content(self) -> None:
        """Создаёт содержимое панели инструкции."""
        for w in self._instruction_panel.winfo_children():
            w.destroy()

        heading_font = self.font_manager.get_heading_font()
        default_font = self.font_manager.get_default_font()

        ttk.Label(self._instruction_panel, text="📚 ИНСТРУКЦИЯ ПО РАБОТЕ",
                  font=heading_font, foreground="#2c3e50",
                  background="#f9f9f9").pack(anchor="w", pady=(15, 10), padx=15)

        text_widget = tk.Text(
            self._instruction_panel, wrap="word", font=default_font,
            background="#f9f9f9", relief="flat", padx=15, pady=10, height=40
        )
        text_widget.insert("1.0", """Это окно предназначено для проверки и уточнения
автоматически подобранных аналогов LaggarTT.

🎨 ЦВЕТОВАЯ ИНДИКАЦИЯ СТРОК:

Строки сгруппированы по оригинальному названию
радиатора конкурента (тип радиатора и значимые
слова в названии).

• Одинаковый цвет — одинаковые модели конкурента
• Смена цвета — изменился тип радиатора или
  другие важные характеристики оригинального
  названия

🛠️ ОСНОВНЫЕ ДЕЙСТВИЯ:

1. ВЫБОР АНАЛОГА:
- Выделите строку в таблице
- Нажмите кнопку «Выбрать аналог LaggarTT»
- В открывшемся окне выберите нужный аналог

2. УДАЛЕНИЕ СТРОК:
- Выделите одну или несколько строк
- Правый клик → «Удалить выделенные строки»

3. ЗАВЕРШЕНИЕ РАБОТЫ:
- После проверки всех аналогов нажмите
  «Перенести в матрицу»

💡 ПОДСКАЗКИ:

• Для выделения нескольких строк:
  Ctrl+клик — отдельные строки
  Shift+клик — диапазон строк
  Ctrl+A — выделить всё

• Столбец «Метод подбора» показывает, каким
  способом был найден аналог:
  - «Типовая модель» — распознан парсером
  - «По образцу» — применён сохранённый шаблон
  - «Ручной ввод» — выбран пользователем
  - «Не подобрано» — требуется ручной выбор
""")
        text_widget.config(state="disabled")
        text_widget.pack(fill="both", expand=True, padx=5, pady=5)

        ttk.Button(self._instruction_panel, text="📚 Скрыть инструкцию",
                   command=self._toggle_instruction, width=25).pack(pady=10)

    def _create_data_table(self, parent: ttk.Frame) -> None:
        """Создаёт таблицу с данными."""
        table_container = ttk.Frame(parent)
        table_container.pack(fill="both", expand=True)

        style = ttk.Style()
        style.configure("Correspondence.Treeview", rowheight=25, font=self.font_manager.get_default_font())
        style.configure("Correspondence.Treeview.Heading", font=self.font_manager.get_heading_font())

        columns = ("Оригинальное название", "Кол-во", "Наименование LaggarTT", "Артикул", "Метод подбора")
        self._tree = ttk.Treeview(
            table_container, columns=columns, show="headings",
            height=18, selectmode="extended", style="Correspondence.Treeview"
        )

        col_config = {
            "Оригинальное название": {"width": 855, "anchor": "e"},
            "Кол-во": {"width": 10, "anchor": "center"},
            "Наименование LaggarTT": {"width": 220, "anchor": "w"},
            "Артикул": {"width": 20, "anchor": "center"},
            "Метод подбора": {"width": 40, "anchor": "center"}
        }
        for col in columns:
            self._tree.heading(col, text=col)
            self._tree.column(
                col,
                width=col_config[col]["width"],
                anchor=col_config[col]["anchor"]
            )

        color_palette = ["#FFFFFF", "#F0F0F0"]
        color_idx = 0
        prev_key = None

        for _, row in self._data.iterrows():
            original = str(row.get("Наименование", "")).replace('\r', ' ').replace('\n', ' ').strip()
            qty = row.get("Кол-во", 0)
            meteor_name = str(row.get("Наименование LaggarTT", ""))
            meteor_art = str(row.get("Артикул LaggarTT", ""))
            source = self._get_method_name(str(row.get("Источник", "")))

            key = self._extract_group_key(original)

            if key != prev_key:
                color_idx = (color_idx + 1) % len(color_palette)
                prev_key = key

            tag = f"group_{color_idx}"
            self._tree.tag_configure(tag, background=color_palette[color_idx])

            self._tree.insert("", "end", values=[
                original, qty, meteor_name, meteor_art, source
            ], tags=(tag,))

        vsb = ttk.Scrollbar(table_container, orient="vertical", command=self._tree.yview)
        hsb = ttk.Scrollbar(table_container, orient="horizontal", command=self._tree.xview)
        self._tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self._tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        table_container.grid_rowconfigure(0, weight=1)
        table_container.grid_columnconfigure(0, weight=1)

        self._context_menu = tk.Menu(self._tree, tearoff=0)
        self._context_menu.add_command(label="🗑️ Удалить выделенные строки", command=self._delete_selected)
        self._context_menu.add_separator()
        self._context_menu.add_command(label="📋 Выделить все (Ctrl+A)", command=self._select_all)

        self._tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self._tree.bind("<Button-3>", self._show_context_menu)
        self._tree.bind("<Delete>", lambda e: self._delete_selected())
        self._tree.bind("<Control-a>", lambda e: self._select_all())
        self._tree.bind("<Control-A>", lambda e: self._select_all())
        
        # Привязка клавиш навигации
        self._tree.bind("<Up>", self._on_key_up)
        self._tree.bind("<Down>", self._on_key_down)
        self._tree.bind("<Shift-Up>", self._on_key_shift_up)
        self._tree.bind("<Shift-Down>", self._on_key_shift_down)
        self._tree.bind("<Shift-Home>", self._on_key_shift_home)
        self._tree.bind("<Shift-End>", self._on_key_shift_end)

    # ==================================================================
    # НАВИГАЦИЯ И ВЫДЕЛЕНИЕ С КЛАВИАТУРЫ
    # ==================================================================

    def _get_all_items(self) -> List[str]:
        """Возвращает список всех ID элементов в дереве."""
        if not self._tree:
            return []
        return self._tree.get_children()

    def _get_item_index(self, item: str) -> int:
        """Возвращает индекс элемента в дереве."""
        all_items = self._get_all_items()
        try:
            return all_items.index(item)
        except ValueError:
            return -1

    def _update_selection(self, anchor_item: str, current_item: str) -> None:
        """
        Обновляет выделение между якорем (anchor) и текущим элементом.
        Выделяет весь диапазон inclusively.
        """
        if not anchor_item or not current_item:
            return

        all_items = self._get_all_items()
        if not all_items:
            return

        anchor_idx = self._get_item_index(anchor_item)
        current_idx = self._get_item_index(current_item)

        if anchor_idx == -1 or current_idx == -1:
            return

        start_idx = min(anchor_idx, current_idx)
        end_idx = max(anchor_idx, current_idx)

        items_to_select = all_items[start_idx : end_idx + 1]
        
        # Устанавливаем выделение
        self._tree.selection_set(items_to_select)
        # Фокус остается на текущем элементе (конце диапазона)
        self._tree.focus(current_item)
        # Прокручиваем к текущему элементу, чтобы он был виден
        self._tree.see(current_item)

    def _on_key_up(self, event):
        """Стрелка вверх: перемещаем фокус и выделение на одну строку вверх."""
        items = self._get_all_items()
        if not items:
            return "break"

        current = self._tree.focus()
        
        if not current:
            new_item = items[-1]
        else:
            idx = self._get_item_index(current)
            if idx > 0:
                new_item = items[idx - 1]
            else:
                return "break"

        self._last_selected_item = new_item
        self._tree.selection_set(new_item)
        self._tree.focus(new_item)
        self._tree.see(new_item)
        
        return "break"

    def _on_key_down(self, event):
        """Стрелка вниз: перемещаем фокус и выделение на одну строку вниз."""
        items = self._get_all_items()
        if not items:
            return "break"

        current = self._tree.focus()
        
        if not current:
            new_item = items[0]
        else:
            idx = self._get_item_index(current)
            if idx < len(items) - 1:
                new_item = items[idx + 1]
            else:
                return "break"

        self._last_selected_item = new_item
        self._tree.selection_set(new_item)
        self._tree.focus(new_item)
        self._tree.see(new_item)
        
        return "break"

    def _on_key_shift_up(self, event):
        """Shift+Стрелка вверх: расширяем выделение вверх."""
        items = self._get_all_items()
        if not items:
            return "break"

        current = self._tree.focus()
        
        if not current:
            current = items[-1]
            self._tree.focus(current)
            self._tree.selection_set(current)
            self._last_selected_item = current
            return "break"

        if self._last_selected_item is None:
            self._last_selected_item = current
        
        idx = self._get_item_index(current)
        if idx > 0:
            new_item = items[idx - 1]
            self._tree.focus(new_item)
            self._update_selection(self._last_selected_item, new_item)
            
        return "break"

    def _on_key_shift_down(self, event):
        """Shift+Стрелка вниз: расширяем выделение вниз."""
        items = self._get_all_items()
        if not items:
            return "break"

        current = self._tree.focus()
        
        if not current:
            current = items[0]
            self._tree.focus(current)
            self._tree.selection_set(current)
            self._last_selected_item = current
            return "break"

        if self._last_selected_item is None:
            self._last_selected_item = current

        idx = self._get_item_index(current)
        if idx < len(items) - 1:
            new_item = items[idx + 1]
            self._tree.focus(new_item)
            self._update_selection(self._last_selected_item, new_item)
            
        return "break"

    def _on_key_shift_home(self, event) -> None:
        """Shift+Home: выделяем от текущей строки до первой."""
        items = self._get_all_items()
        if not items:
            return "break"

        current = self._tree.focus()
        if not current:
            current = items[0]
            self._tree.focus(current)
            
        if self._last_selected_item is None:
            self._last_selected_item = current

        first_item = items[0]
        self._tree.focus(first_item)
        self._update_selection(self._last_selected_item, first_item)
        return "break"

    def _on_key_shift_end(self, event) -> None:
        """Shift+End: выделяем от текущей строки до последней."""
        items = self._get_all_items()
        if not items:
            return "break"

        current = self._tree.focus()
        if not current:
            current = items[-1]
            self._tree.focus(current)
            
        if self._last_selected_item is None:
            self._last_selected_item = current

        last_item = items[-1]
        self._tree.focus(last_item)
        self._update_selection(self._last_selected_item, last_item)
        return "break"

    def _select_all(self, event=None) -> None:
        """Выделяет все строки."""
        all_items = self._get_all_items()
        if all_items:
            self._tree.selection_set(all_items)
            self._tree.focus(all_items[0])
            self._last_selected_item = all_items[0]
            self._tree.see(all_items[0])

    # ==================================================================
    # ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ
    # ==================================================================

    def _extract_group_key(self, text: str) -> Tuple[Optional[str], str]:
        """Извлекает ключ группировки: (тип, нормализованное название)."""
        lower = text.lower().strip()
        rad_type = None

        type_match = re.search(r'(?:тип|type)\s*(\d{1,2})', lower)
        if type_match and type_match.group(1) in {'10', '11', '12', '20', '21', '22', '30', '33'}:
            rad_type = type_match.group(1)

        if not rad_type:
            trip_match = re.search(r'(?<!\d)(\d{2})\s*[-–/xх]\s*\d{3,4}\s*[-–/xх]\s*\d{3,4}', lower)
            if trip_match and trip_match.group(1) in {'10', '11', '12', '20', '21', '22', '30', '33'}:
                rad_type = trip_match.group(1)

        normalized = re.sub(r'\d+', '#', lower)
        normalized = re.sub(r'\s+', ' ', normalized).strip()

        return (rad_type, normalized)

    def _get_method_name(self, source: str) -> str:
        """Возвращает читаемое название метода подбора."""
        src = source.lower().strip()
        
        # Пустые или отсутствующие
        if not src or src == '':
            return "Не подобрано"
        
        # Ожидает подбора
        if 'ожидает' in src:
            return "Не подобрано"
        
        # Не подобрано
        if 'не подобрано' in src:
            return "Не подобрано"
        
        # Ручной ввод
        if 'вручную' in src or 'ручной ввод' in src or 'ручной' in src:
            return "Ручной ввод"
        
        # По образцу (паттерны)
        if 'образцу' in src or 'learned' in src or 'паттерн' in src:
            return "По образцу"
        
        # Типовые модели (Лидея, Oasis, и т.д.)
        if any(kw in src for kw in ['лидея', 'lidea', 'oasis', 'compact', 'типовая', 'kermi', 'evra']):
            return "Типовая модель"
        
        # Структурный / Автоматический
        if any(kw in src for kw in ['структурный', 'автоматически', 'авто', 'числовые', 'universal', 'laggar_format']):
            return "Структурный"
        
        # Если ничего не подошло
        logger.warning(f"Неизвестный источник: '{source}'")
        return "Не подобрано"

    def _toggle_instruction(self) -> None:
        """Показывает/скрывает панель инструкции."""
        if self._instruction_visible:
            self._instruction_panel.place(x=2000, y=0, relheight=1)
            self._toggle_btn.config(text="📚 Показать инструкцию")
            self._instruction_visible = False
        else:
            container_w = self._instruction_panel.master.winfo_width()
            self._instruction_panel.place(x=container_w - 400, y=0, relheight=1)
            self._toggle_btn.config(text="📚 Скрыть инструкцию")
            self._instruction_visible = True

    def _on_tree_select(self, event) -> None:
        """Обработчик выбора строки."""
        selected = self._tree.selection()
        if selected:
            if len(selected) == 1:
                values = self._tree.item(selected[0], "values")
                name = values[0] if len(values) > 0 else ""
                self._selection_info.configure(text=f"Выделено: {name}")
            else:
                self._selection_info.configure(text=f"Выделено строк: {len(selected)}")
        else:
            self._selection_info.configure(text="Выделите строку для просмотра деталей...")

    def _show_context_menu(self, event) -> None:
        """Показывает контекстное меню."""
        item = self._tree.identify_row(event.y)
        if item:
            if item not in self._tree.selection():
                self._tree.selection_set(item)
            self._context_menu.post(event.x_root, event.y_root)

    def _delete_selected(self) -> None:
        """Удаляет выбранные строки и сохраняет состояние."""
        selected = self._tree.selection()
        if selected:
            count = len(selected)
            msg = f"Удалить {count} строк?" if count > 1 else "Удалить строку?"
            if messagebox.askyesno("Подтверждение", msg):
                for item in selected:
                    self._tree.delete(item)
                remaining = len(self._tree.get_children())
                self._selection_info.configure(
                    text=f"Удалено: {count} строк. Осталось: {remaining}"
                )
                # СОХРАНЯЕМ СОСТОЯНИЕ ПОСЛЕ УДАЛЕНИЯ
                self._save_current_state()

    def _select_first_row(self) -> None:
        """Выделяет первую строку."""
        items = self._tree.get_children()
        if items:
            self._tree.selection_set(items[0])
            self._tree.focus(items[0])
            self._last_selected_item = items[0]

    def _apply_patterns(self) -> None:
        """Применяет сохранённые паттерны к таблице."""
        if not self._tree:
            return

        updated = 0
        for item in self._tree.get_children():
            values = list(self._tree.item(item, "values"))
            if len(values) < 5:
                continue

            original = values[0]
            current_art = values[3].strip()

            if current_art:
                continue

            match = self.app.pattern_manager.find_match(original)
            if match:
                art, name = self.app.data_provider.find_analog(
                    match['connection'], match['rad_type'],
                    match['height'], match['length']
                )
                if art:
                    values[2] = name
                    values[3] = art
                    values[4] = "По образцу"
                    self._tree.item(item, values=values)
                    updated += 1

        if updated > 0:
            messagebox.showinfo("Успех", f"Обновлено строк: {updated}")
            # СОХРАНЯЕМ СОСТОЯНИЕ ПОСЛЕ ПРИМЕНЕНИЯ ПАТТЕРНОВ
            self._save_current_state()
        else:
            messagebox.showinfo("Информация", "Нет новых совпадений")

    def _apply_patterns_to_all_rows(self, tree: ttk.Treeview) -> int:
        """
        Применяет шаблоны ко всем строкам таблицы.
        """
        updated = 0
        
        if not tree or not tree.winfo_exists():
            return 0
            
        all_items = tree.get_children()
        logger.info(f"Переподбор: строк в таблице={len(all_items)}")
        
        # Загружаем шаблоны один раз
        from nextt.patterns.template_manager import TemplateManager
        template_manager = TemplateManager()
        
        for item in all_items:
            try:
                values = list(tree.item(item, "values"))
            except Exception:
                continue
                
            if len(values) < 5:
                continue
            
            original_name = values[0]
            current_art = str(values[3]).strip() if len(values) > 3 else ""
            current_source = str(values[4]) if len(values) > 4 else ""
            
            if "Ручной ввод" in current_source:
                logger.info(f"  ⏭ Пропущено (ручной ввод): '{original_name[:40]}'")
                continue
            
            # Применяем шаблоны
            result = template_manager.apply_templates(original_name)
            
            if result:
                logger.info(f"  ✅ Найден шаблон для '{original_name[:40]}': "
                           f"conn={result.get('connection')}, type={result.get('rad_type')}, "
                           f"h={result.get('height')}, l={result.get('length')}")
                
                art, name = self.app.data_provider.find_analog(
                    result['connection'], result['rad_type'],
                    result['height'], result['length']
                )
                
                if art and current_art != art:
                    values[2] = name
                    values[3] = art
                    values[4] = "По образцу (шаблон)"
                    tree.item(item, values=values)
                    updated += 1
                    logger.info(f"    ✅ Обновлено по шаблону: '{original_name[:40]}' → {art}")
                elif art and current_art == art:
                    logger.info(f"    ⏭ Уже подобрано: '{original_name[:40]}' → {art}")
                else:
                    logger.info(f"    ❌ Аналог не найден в базе: '{original_name[:40]}'")
            else:
                logger.info(f"  ❌ Нет шаблона для: '{original_name[:60]}'")
        
        logger.info(f"Переподбор завершён: обновлено {updated} строк")
        
        if updated > 0:
            messagebox.showinfo("Успех", f"Автоматически обновлено строк: {updated}")
            self._save_current_state()
        
        return updated
        
    def _select_analog_manually(self) -> None:
        """Ручной выбор аналога через MeteorSelector."""
        selected = self._tree.selection()
        if not selected:
            messagebox.showwarning("Ошибка", "Выберите строку для подбора аналога")
            return

        item = selected[0]
        values = list(self._tree.item(item, "values"))
        original_name = values[0]

        from nextt.ui.dialogs.meteor_selector import MeteorSelector
        selector = MeteorSelector(self.app)
        
        # Передаём колбэк для обновления состояния после выбора аналога
        def on_analog_selected():
            self._save_current_state()
        
        selector.set_apply_patterns_callback(self._apply_patterns_to_all_rows)
        selector.set_on_close_callback(on_analog_selected)
        selector.show(self._tree, item, original_name)

    def _transfer_to_matrix(self) -> None:
        """Переносит все подобранные позиции в матрицу."""
        if not self._tree:
            return

        # ========== СОХРАНЯЕМ СОСТОЯНИЕ ПЕРЕД ПЕРЕНОСОМ ==========
        self._save_current_state()
        # ========================================================

        all_items = self._tree.get_children()
        transferred = 0

        correspondence_data = []

        for item in all_items:
            values = list(self._tree.item(item, "values"))
            if len(values) < 5:
                continue

            art = values[3].strip()
            qty_str = str(values[1]).strip()
            original_name = values[0]
            meteor_name = values[2]
            source = values[4]

            if not art:
                logger.info(f"Пропущена строка без артикула: {original_name[:50]}... (статус: {source})")
                continue

            try:
                qty = int(float(qty_str.replace(',', '.')))
            except (ValueError, TypeError):
                qty = 0

            if qty <= 0:
                logger.info(f"Пропущена строка с нулевым количеством: {original_name[:50]}...")
                continue

            correspondence_data.append({
                'Наименование': original_name,
                'Кол-во': qty,
                'Наименование LaggarTT': meteor_name,
                'Артикул LaggarTT': art,
                'Источник': source,
            })

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
                    transferred += 1

        if correspondence_data:
            import pandas as pd
            self._saved_correspondence_data = pd.DataFrame(correspondence_data)
            
            # Обновляем _last_correspondence_data из текущего состояния Treeview
            updated_data = []
            for item in self._tree.get_children():
                values = list(self._tree.item(item, "values"))
                if len(values) >= 5:
                    updated_data.append({
                        "Наименование": values[0],
                        "Кол-во": values[1],
                        "Наименование LaggarTT": values[2],
                        "Артикул LaggarTT": values[3],
                        "Источник": values[4],
                    })
            self.app._last_correspondence_data = pd.DataFrame(updated_data)
            
            logger.info(f"Перенесено в матрицу: {transferred} позиций")
            logger.info(f"Данные таблицы соответствия сохранены: {len(correspondence_data)} строк (только с артикулами)")

        if hasattr(self.app, 'main_window') and self.app.main_window:
            self.app.main_window._build_matrix(
                self.app.main_window._conn_var.get(),
                self.app.main_window._type_var.get()
            )

        self._close()

        if transferred > 0:
            spec_data = self.app.spec_generator.prepare_spec_data(
                entry_values=self.app.entry_values,
                bracket_type=self.app.main_window.bracket_var.get(),
                radiator_discount=float(self.app.main_window.radiator_discount_var.get() or 0),
                bracket_discount=float(self.app.main_window.bracket_discount_var.get() or 0),
            )

            if spec_data is not None and not spec_data.empty:
                from nextt.ui.dialogs.preview import PreviewDialog
                preview = PreviewDialog(self.app)
                preview.show(spec_data)
            else:
                messagebox.showinfo(
                    "Перенос завершён",
                    f"Перенесено {transferred} позиций в матрицу.\n"
                    "Заполните матрицу и нажмите «Предпросмотр» для формирования спецификации."
                )
        else:
            messagebox.showinfo(
                "Информация",
                "Нет данных для переноса.\n"
                "Убедитесь, что для всех позиций подобраны аналоги LaggarTT."
            )

    def get_correspondence_data(self):
        """Возвращает сохранённые данные таблицы соответствия."""
        if hasattr(self.app, '_all_correspondence_data') and self.app._all_correspondence_data is not None:
            return self.app._all_correspondence_data.copy()
        if hasattr(self, '_saved_correspondence_data') and self._saved_correspondence_data is not None:
            return self._saved_correspondence_data.copy()
        return None

    def _close(self) -> None:
        """Закрывает диалог."""
        # Сохраняем состояние перед закрытием
        self._save_current_state()
        
        if self._dialog:
            self._dialog.destroy()
            self._dialog = None
            self._tree = None
        
        if hasattr(self, '_root_was_visible') and self._root_was_visible:
            if hasattr(self.app, 'root') and self.app.root.winfo_exists():
                self.app.root.deiconify()
                self.app.root.focus_force()