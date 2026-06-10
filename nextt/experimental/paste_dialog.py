"""
Диалог вставки данных из буфера обмена.
Экспериментальная версия — изолирована от основного кода.
"""

import tkinter as tk
from tkinter import ttk, messagebox
import re
from typing import Optional, List
import pandas as pd

from nextt.logger import get_logger
from nextt.utils.window_manager import setup_dialog_window, get_safe_geometry, fix_window_buttons_after_geometry

logger = get_logger(__name__)
try:
    import pyperclip
    HAS_PYPERCLIP = True
except ImportError:
    HAS_PYPERCLIP = False



class PasteDialog:
    """
    Диалог для вставки данных из буфера обмена.
    """

    def __init__(self, parent, app, font_manager=None, callback=None):
        self.parent = parent
        self.app = app
        self.font_manager = font_manager
        self.callback = callback

        self._dialog: Optional[tk.Toplevel] = None
        self._text_area: Optional[tk.Text] = None
        self._preview_tree: Optional[ttk.Treeview] = None
        self._df: Optional[pd.DataFrame] = None
        self._raw_text: str = ""

        self._name_col_var = tk.IntVar(value=-1)
        self._qty_col_var = tk.IntVar(value=-1)
        self._name_col_combo: Optional[ttk.Combobox] = None
        self._qty_col_combo: Optional[ttk.Combobox] = None
        self._confirm_btn: Optional[ttk.Button] = None
        self._format_var = tk.StringVar(value="auto")

    def _get_font(self):
        """Возвращает масштабированный шрифт."""
        if self.font_manager:
            return self.font_manager.get_default_font()
        return ("Segoe UI", 9)

    def _get_heading_font(self):
        """Возвращает масштабированный шрифт для заголовков."""
        if self.font_manager:
            return self.font_manager.get_heading_font()
        return ("Segoe UI", 10, "bold")

    def _get_bold_font(self):
        """Возвращает масштабированный жирный шрифт."""
        if self.font_manager:
            return self.font_manager.get_bold_font()
        return ("Segoe UI", 9, "bold")

    def show(self) -> None:
        self._create_dialog()
        self._auto_paste_from_clipboard()

    def _create_dialog(self) -> None:
        """Создаёт окно диалога с правильной геометрией и стилями."""
        self._dialog = tk.Toplevel(self.parent)
        
        # ========== НАСТРОЙКА ОКНА ЧЕРЕЗ window_manager ==========
        setup_dialog_window(self._dialog, "Вставка данных из буфера обмена (Экспериментально)")
        
        safe_geom = get_safe_geometry(self._dialog, maximized=True)
        self._dialog.geometry(safe_geom)
        fix_window_buttons_after_geometry(self._dialog)
        # =========================================================
        
        self._dialog.configure(bg='#f5f5f5')
        self._dialog.transient(self.parent)
        self._dialog.grab_set()

        # Получаем масштабированные шрифты
        default_font = self._get_font()
        heading_font = self._get_heading_font()
        bold_font = self._get_bold_font()

        # Настраиваем стили ttk
        style = ttk.Style()
        style.configure("PasteDialog.TFrame", background='#f5f5f5')
        style.configure("PasteDialog.TLabel", background='#f5f5f5', font=default_font)
        style.configure("PasteDialog.TButton", font=default_font)
        style.configure("PasteDialog.TCheckbutton", background='#f5f5f5', font=default_font)
        style.configure("PasteDialog.TRadiobutton", background='#f5f5f5', font=default_font)
        style.configure("PasteDialog.TLabelframe.Label", font=bold_font)
        style.configure("PasteDialog.Treeview", font=default_font, rowheight=25)
        style.configure("PasteDialog.Treeview.Heading", font=heading_font)

        main_frame = ttk.Frame(self._dialog, padding="15", style="PasteDialog.TFrame")
        main_frame.pack(fill="both", expand=True)

        # Предупреждение об экспериментальном статусе
        warn_frame = ttk.Frame(main_frame)
        warn_frame.pack(fill="x", pady=(0, 10))
        
        ttk.Label(
            warn_frame,
            text="⚠️ ЭКСПЕРИМЕНТАЛЬНАЯ ФУНКЦИЯ ⚠️",
            font=heading_font,
            foreground="#e74c3c",
            style="PasteDialog.TLabel"
        ).pack(anchor="w")

        ttk.Label(
            warn_frame,
            text="Данная функция находится в разработке. Результаты могут быть нестабильными.",
            font=default_font,
            foreground="#888888",
            style="PasteDialog.TLabel"
        ).pack(anchor="w")

        instr_label = ttk.Label(
            main_frame,
            text="Вставьте данные из буфера обмена (Ctrl+V) в поле ниже.\n"
                 "Поддерживаются: таблицы из Excel, списки с номерами.\n"
                 "Затем нажмите «Разобрать» для предпросмотра.",
            font=default_font,
            foreground="#555555",
            style="PasteDialog.TLabel"
        )
        instr_label.pack(anchor="w", pady=(0, 10))

        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill="x", pady=(0, 10))

        ttk.Button(btn_frame, text="Вставить из буфера", command=self._paste_from_clipboard, style="PasteDialog.TButton").pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Разобрать", command=self._parse_text, style="PasteDialog.TButton").pack(side="left", padx=5)
        ttk.Button(btn_frame, text="Очистить", command=self._clear_text, style="PasteDialog.TButton").pack(side="left", padx=5)

        format_frame = ttk.Frame(btn_frame)
        format_frame.pack(side="right", padx=10)
        
        ttk.Label(format_frame, text="Формат:", font=default_font, style="PasteDialog.TLabel").pack(side="left", padx=(0, 5))
        
        rb_auto = ttk.Radiobutton(format_frame, text="Авто", variable=self._format_var, value="auto", style="PasteDialog.TRadiobutton")
        rb_auto.pack(side="left", padx=2)
        
        rb_table = ttk.Radiobutton(format_frame, text="Таблица", variable=self._format_var, value="table", style="PasteDialog.TRadiobutton")
        rb_table.pack(side="left", padx=2)
        
        rb_list = ttk.Radiobutton(format_frame, text="Список", variable=self._format_var, value="list", style="PasteDialog.TRadiobutton")
        rb_list.pack(side="left", padx=2)

        # ========== ОСНОВНОЙ КОНТЕЙНЕР (ДВЕ КОЛОНКИ) ==========
        columns_frame = ttk.Frame(main_frame)
        columns_frame.pack(fill="both", expand=True)

        # Левая колонка — выбор столбцов и категорий
        left_frame = ttk.Frame(columns_frame, style="PasteDialog.TFrame")
        left_frame.pack(side="left", fill="both", expand=False, padx=(0, 15))

        select_frame = ttk.LabelFrame(left_frame, text="ВЫБОР СТОЛБЦОВ", 
                                      padding="15", style="PasteDialog.TLabelframe")
        select_frame.pack(fill="both", expand=True)

        ttk.Label(select_frame, text="Столбец с названием/артикулом:", 
                  font=default_font, style="PasteDialog.TLabel").pack(anchor="w", pady=(0, 5))
        self._name_col_combo = ttk.Combobox(select_frame, state="readonly", 
                                            width=35, font=default_font)
        self._name_col_combo.pack(fill="x", pady=(0, 15))
        self._name_col_combo.bind("<<ComboboxSelected>>", self._on_selection_changed)

        ttk.Label(select_frame, text="Столбец с количеством:", 
                  font=default_font, style="PasteDialog.TLabel").pack(anchor="w", pady=(0, 5))
        self._qty_col_combo = ttk.Combobox(select_frame, state="readonly", 
                                           width=35, font=default_font)
        self._qty_col_combo.pack(fill="x", pady=(0, 20))
        self._qty_col_combo.bind("<<ComboboxSelected>>", self._on_selection_changed)

        # ========== НОВЫЙ БЛОК: ВЫБОР КАТЕГОРИЙ ==========
        categories_frame = ttk.LabelFrame(left_frame, text="КАТЕГОРИИ ДЛЯ ПОИСКА", 
                                          padding="10", style="PasteDialog.TLabelframe")
        categories_frame.pack(fill="both", expand=True, pady=(10, 0))

        # Контейнер для чекбоксов с прокруткой (на случай, если категорий много)
        categories_canvas = tk.Canvas(categories_frame, bg='#f5f5f5', highlightthickness=0)
        categories_scrollbar = ttk.Scrollbar(categories_frame, orient="vertical", command=categories_canvas.yview)
        categories_inner = ttk.Frame(categories_canvas, style="PasteDialog.TFrame")
        
        categories_canvas.configure(yscrollcommand=categories_scrollbar.set)
        categories_canvas_window = categories_canvas.create_window((0, 0), window=categories_inner, anchor="nw", width=280)
        
        categories_scrollbar.pack(side="right", fill="y")
        categories_canvas.pack(side="left", fill="both", expand=True)

        # Функция обновления размера canvas
        def on_canvas_configure(event):
            categories_canvas.itemconfig(categories_canvas_window, width=event.width)
        
        def on_inner_configure(event):
            categories_canvas.configure(scrollregion=categories_canvas.bbox("all"))
        
        categories_canvas.bind("<Configure>", on_canvas_configure)
        categories_inner.bind("<Configure>", on_inner_configure)

        # Загружаем категории из базы данных
        self._category_vars = {}  # словарь для хранения переменных чекбоксов
        self._load_categories(categories_inner, default_font)

        # Кнопки в левой колонке
        button_frame = ttk.Frame(select_frame)
        button_frame.pack(fill="x", pady=(10, 0))

        self._confirm_btn = ttk.Button(
            button_frame,
            text="Продолжить",
            command=self._on_confirm,
            width=25,
            state="disabled",
            style="PasteDialog.TButton"
        )
        self._confirm_btn.pack(side="top", pady=5)

        ttk.Button(button_frame, text="Закрыть", command=self._on_cancel, 
                   width=25, style="PasteDialog.TButton").pack(side="top", pady=5)

        # Правая колонка — данные
        right_frame = ttk.Frame(columns_frame, style="PasteDialog.TFrame")
        right_frame.pack(side="left", fill="both", expand=True)

        # Исходные данные
        text_frame = ttk.LabelFrame(right_frame, text="Исходные данные", 
                                    padding="5", style="PasteDialog.TLabelframe")
        text_frame.pack(fill="both", expand=True, pady=(0, 15))

        text_container = ttk.Frame(text_frame)
        text_container.pack(fill="both", expand=True)

        self._text_area = tk.Text(text_container, wrap="none", font=default_font, height=12)
        self._text_area.pack(side="left", fill="both", expand=True)

        text_scroll_y = ttk.Scrollbar(text_container, orient="vertical", command=self._text_area.yview)
        text_scroll_x = ttk.Scrollbar(text_frame, orient="horizontal", command=self._text_area.xview)
        self._text_area.configure(yscrollcommand=text_scroll_y.set, xscrollcommand=text_scroll_x.set)
        text_scroll_y.pack(side="right", fill="y")
        text_scroll_x.pack(side="bottom", fill="x")

        # Информационная строка
        self._info_label = ttk.Label(right_frame, text="", font=default_font, 
                                     foreground="#666666", style="PasteDialog.TLabel")
        self._info_label.pack(anchor="w", pady=(0, 10))

        # Предпросмотр
        preview_frame = ttk.LabelFrame(right_frame, text="Предпросмотр", 
                                       padding="5", style="PasteDialog.TLabelframe")
        preview_frame.pack(fill="both", expand=True)

        preview_container = ttk.Frame(preview_frame)
        preview_container.pack(fill="both", expand=True)

        tree_frame = ttk.Frame(preview_container)
        tree_frame.pack(fill="both", expand=True)

        self._preview_tree = ttk.Treeview(
            tree_frame, 
            show="headings", 
            height=12,
            style="PasteDialog.Treeview"
        )
        tree_vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self._preview_tree.yview)
        tree_hsb = ttk.Scrollbar(tree_frame, orient="horizontal", command=self._preview_tree.xview)
        self._preview_tree.configure(yscrollcommand=tree_vsb.set, xscrollcommand=tree_hsb.set)

        self._preview_tree.grid(row=0, column=0, sticky="nsew")
        tree_vsb.grid(row=0, column=1, sticky="ns")
        tree_hsb.grid(row=1, column=0, sticky="ew")
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)

        self._dialog.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self._dialog.bind("<Escape>", lambda e: self._on_cancel())
        
        self._text_area.focus_set()
        self._dialog.grab_set()

    def _load_categories(self, parent_frame: ttk.Frame, default_font) -> None:
        """Загружает категории из базы данных и создаёт чекбоксы."""
        try:
            from nextt.config import get_resource_path
            from pathlib import Path
            import pandas as pd
            
            file_path = get_resource_path("Все_категории.xlsx")
            if not Path(file_path).exists():
                logger.warning(f"Файл Все_категории.xlsx не найден: {file_path}")
                # Создаём заглушку
                ttk.Label(parent_frame, text="Файл категорий не найден", 
                          font=default_font, style="PasteDialog.TLabel").pack(anchor="w")
                return
            
            df = pd.read_excel(file_path, sheet_name="Прайс", engine='openpyxl')
            
            # Ищем столбец с иерархией/категориями
            hierarchy_col = None
            for col in df.columns:
                col_lower = str(col).lower()
                if 'иерархия' in col_lower or 'категория' in col_lower or 'category' in col_lower:
                    hierarchy_col = col
                    break
            
            if hierarchy_col is None:
                logger.warning("Столбец с категориями не найден в файле Все_категории.xlsx")
                ttk.Label(parent_frame, text="Столбец категорий не найден", 
                          font=default_font, style="PasteDialog.TLabel").pack(anchor="w")
                return
            
            # Получаем уникальные категории (не пустые)
            categories = df[hierarchy_col].dropna().unique()
            categories = [str(c).strip() for c in categories if str(c).strip()]
            categories = sorted(set(categories))  # уникальные и отсортированные
            
            # Категории, которые должны быть включены по умолчанию
            default_categories = [
                'котлы METEOR', 
                'котлы LaggarTT', 
                'комплектующие к котлам', 
                'дымоходы', 
                'бойлеры'
            ]
            
            # Создаём чекбоксы
            for cat in categories:
                var = tk.BooleanVar(value=(cat in default_categories))
                self._category_vars[cat] = var
                
                cb = ttk.Checkbutton(
                    parent_frame, 
                    text=cat, 
                    variable=var,
                    style="PasteDialog.TCheckbutton"
                )
                cb.pack(anchor="w", pady=2)
            
            # Добавляем кнопки "Выбрать всё" и "Снять всё"
            btn_frame = ttk.Frame(parent_frame)
            btn_frame.pack(fill="x", pady=(10, 0))
            
            def select_all():
                for var in self._category_vars.values():
                    var.set(True)
            
            def deselect_all():
                for var in self._category_vars.values():
                    var.set(False)
            
            ttk.Button(btn_frame, text="Выбрать всё", command=select_all, 
                       width=12, style="PasteDialog.TButton").pack(side="left", padx=2)
            ttk.Button(btn_frame, text="Снять всё", command=deselect_all, 
                       width=12, style="PasteDialog.TButton").pack(side="left", padx=2)
            
            logger.info(f"Загружено категорий: {len(categories)}")
            
        except Exception as e:
            logger.error(f"Ошибка загрузки категорий: {e}")
            ttk.Label(parent_frame, text=f"Ошибка загрузки: {str(e)[:50]}", 
                      font=default_font, foreground="red", style="PasteDialog.TLabel").pack(anchor="w")

    def get_selected_categories(self) -> List[str]:
        """Возвращает список выбранных пользователем категорий."""
        return [cat for cat, var in self._category_vars.items() if var.get()]

    def _auto_paste_from_clipboard(self) -> None:
        self._paste_from_clipboard()
        if self._raw_text.strip():
            self._parse_text()

    def _paste_from_clipboard(self) -> None:
        """Вставляет данные из буфера обмена."""
        clipboard_text = None
        
        # ========== ПЫТАЕМСЯ ИСПОЛЬЗОВАТЬ PYPERCLIP ==========
        try:
            import pyperclip
            clipboard_text = pyperclip.paste()
            logger.info(f"Буфер обмена (pyperclip): {repr(clipboard_text[:200]) if clipboard_text else 'пуст'}")
        except ImportError:
            logger.info("pyperclip не установлен, используем Tkinter")
            pass
        except Exception as e:
            logger.warning(f"Ошибка pyperclip: {e}")
        
        # ========== FALLBACK: Tkinter ==========
        if not clipboard_text:
            try:
                clipboard_text = self._dialog.clipboard_get()
                logger.info(f"Буфер обмена (Tkinter): {repr(clipboard_text[:200]) if clipboard_text else 'пуст'}")
            except tk.TclError:
                messagebox.showwarning("Ошибка", "Не удалось получить данные из буфера обмена")
                return
        
        if not clipboard_text or not clipboard_text.strip():
            messagebox.showinfo("Информация", "Буфер обмена пуст")
            return
        
        # ========== НОРМАЛИЗАЦИЯ ТЕКСТА ==========
        # Заменяем возможные проблемы с кодировкой
        normalized_text = clipboard_text
        
        # Замена специфических символов, которые могут быть испорчены
        replacements = [
            ('­', '-'),   # мягкий перенос
            ('\u00ad', '-'),  # мягкий перенос (Unicode)
            ('\u2010', '-'),  # дефис
            ('\u2011', '-'),  # неразрывный дефис
            ('\u2012', '-'),  # цифровой дефис
            ('\u2013', '-'),  # en dash
            ('\u2014', '-'),  # em dash
            ('\u2212', '-'),  # знак минус
        ]
        for old, new in replacements:
            normalized_text = normalized_text.replace(old, new)
        
        # Восстановление потерянных пробелов между словом и дефисом
        # "Вайфай- 2" -> "Вайфай- 2" (оставляем как есть)
        # Но если дефис слит со словом, а после него пробел — это нормально
        
        # Логируем результат нормализации
        logger.info(f"Текст после нормализации: {repr(normalized_text[:200])}")
        
        # Вставляем в текстовое поле
        self._text_area.delete("1.0", tk.END)
        self._text_area.insert("1.0", normalized_text)
        self._raw_text = normalized_text
        
        # Подсчитываем строки для информации
        line_count = len(normalized_text.splitlines())
        self._info_label.config(text=f"Вставлено {line_count} строк")
        
        # Автоматически запускаем разбор, если текст не слишком большой
        if line_count <= 50:
            self._dialog.after(100, self._parse_text)

    def _clear_text(self) -> None:
        self._text_area.delete("1.0", tk.END)
        self._raw_text = ""
        self._clear_preview()
        self._info_label.config(text="")

    def _clear_preview(self) -> None:
        self._preview_tree.delete(*self._preview_tree.get_children())
        self._preview_tree["columns"] = []
        self._df = None
        self._name_col_combo.set("")
        self._name_col_combo["values"] = []
        self._qty_col_combo.set("")
        self._qty_col_combo["values"] = []
        self._confirm_btn.config(state="disabled")

    def _normalize_text_for_parsing(self, text: str) -> str:
        """Нормализует текст для парсинга: заменяет разные тире и исправляет опечатки."""
        if not text:
            return text
        
        # Замена всех видов тире на обычный дефис
        dash_patterns = ['–', '—', '‐', '‑', '‒']
        result = text
        for dash in dash_patterns:
            result = result.replace(dash, '-')
        
        # Исправляем опечатки в "штука"
        result = result.replace('щтука', 'штука')
        result = result.replace('щтук', 'штук')
        result = result.replace('штуки', 'штука')
        
        return result

    def _is_list_format(self, lines: List[str]) -> bool:
        """
        Определяет, является ли текст списком (а не таблицей).
        Признаки списка:
        - строка содержит "=" и число со словом "шт"/"штука" в конце
        - строка содержит тире/дефис и число со словом "шт"/"штука"
        - строка НЕ содержит табуляций (главный признак таблицы)
        - строка НЕ содержит нескольких запятых/пробелов как разделителей таблицы
        """
        for line in lines[:10]:
            line_stripped = line.strip()
            if not line_stripped:
                continue
            
            # ========== ГЛАВНАЯ ПРОВЕРКА: если есть табуляция — это таблица ==========
            if '\t' in line_stripped:
                return False
            
            # Нормализуем строку
            normalized = self._normalize_text_for_parsing(line_stripped)
            
            # ПРИЗНАК 1: строка содержит "=" и число + "шт" в конце (C 11- 400 - 600 = 1 шт.)
            if '=' in normalized and re.search(r'=\s*\d+\s*(?:шт|штук)', normalized, re.IGNORECASE):
                return True
            
            # ПРИЗНАК 2: строка содержит число + "шт" в конце
            if re.search(r'\d+\s*(?:шт|штук)\s*$', normalized, re.IGNORECASE):
                return True
            
            # ПРИЗНАК 3: строка содержит тире/дефис, затем число, затем "шт"/"штука"
            if re.search(r'-\s*\d+\s*(?:шт|штук)', normalized, re.IGNORECASE):
                return True
            
            # ПРИЗНАК 4: строка заканчивается числом (без "шт") — но только если нет признаков таблицы
            if re.search(r'\d+\s*$', normalized):
                # Если в строке несколько запятых — это таблица
                if line_stripped.count(',') >= 2:
                    continue
                # Если в строке несколько пробелов подряд — возможно таблица
                if len(re.findall(r'\s+', line_stripped)) >= 5:
                    continue
                return True
        
        return False

    def _parse_list_format(self, lines: List[str]) -> pd.DataFrame:
        """
        Парсит текст как список.
        Каждая строка = одна позиция.
        Извлекает: наименование и количество.
        Поддерживает форматы:
        - "C 11- 400 - 600 = 1 шт."
        - "B30-24H Вайфай- 2 штуки"
        """
        rows = []
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Нормализуем строку
            normalized = self._normalize_text_for_parsing(line)
            
            # Пытаемся извлечь количество
            qty = self._extract_quantity_from_line(normalized)
            
            # Извлекаем наименование (всё, что до количества)
            name = self._extract_name_from_line(normalized, qty)
            
            # Если наименование пустое, берём всю строку
            if not name:
                name = line
            
            rows.append([name, qty])
        
        if not rows:
            return pd.DataFrame()
        
        df = pd.DataFrame(rows, columns=['Наименование', 'Кол-во'])
        df = df[df['Кол-во'] > 0]
        return df

    def _extract_quantity_from_line(self, line: str) -> int:
        """Извлекает количество из строки."""
        if not line:
            return 0
        
        # Нормализуем строку для поиска
        normalized = line.replace('-', ' - ').replace('=', ' = ')
        normalized = re.sub(r'\s+', ' ', normalized)
        
        # ПАТТЕРН: слово + дефис + число + шт (газ- 8 штук)
        pattern1 = r'\w+\s*-\s*(\d+)\s*(?:шт|штук)'
        match = re.search(pattern1, normalized, re.IGNORECASE)
        if match:
            try:
                return int(match.group(1))
            except (ValueError, TypeError):
                pass
        
        # ПАТТЕРН: знак "=" + число + шт
        pattern2 = r'=\s*(\d+)\s*(?:шт|штук)'
        match = re.search(pattern2, normalized, re.IGNORECASE)
        if match:
            try:
                return int(match.group(1))
            except (ValueError, TypeError):
                pass
        
        # ПАТТЕРН: дефис + число + шт
        pattern3 = r'-\s*(\d+)\s*(?:шт|штук)'
        match = re.search(pattern3, normalized, re.IGNORECASE)
        if match:
            try:
                return int(match.group(1))
            except (ValueError, TypeError):
                pass
        
        # ПАТТЕРН: число + шт в конце
        pattern4 = r'(\d+)\s*(?:шт|штук)\s*$'
        match = re.search(pattern4, normalized, re.IGNORECASE)
        if match:
            try:
                return int(match.group(1))
            except (ValueError, TypeError):
                pass
        
        # ПАТТЕРН: число в конце
        pattern5 = r'(\d+)\s*$'
        match = re.search(pattern5, normalized)
        if match:
            try:
                qty = int(match.group(1))
                if 1 <= qty <= 10000:
                    return qty
            except (ValueError, TypeError):
                pass
        
        return 0

    def _extract_name_from_line(self, line: str, qty: int) -> str:
        """Извлекает наименование из строки (удаляет количество и служебные слова)."""
        if not line or qty <= 0:
            return line
        
        result = line
        
        # Ищем позицию, где начинается количество
        patterns = [
            r'-\s*' + str(qty) + r'\s*(?:шт|штук\w*)',   # - 8 штук
            r'=\s*' + str(qty) + r'\s*(?:шт|штук\w*)',   # = 8 штук
            r'\s*' + str(qty) + r'\s*(?:шт|штук\w*)\s*$', # 8 штук в конце
            r'\s*' + str(qty) + r'\s*$',                  # просто число в конце
        ]
        
        for pattern in patterns:
            match = re.search(pattern, result, re.IGNORECASE)
            if match:
                # Обрезаем строку до начала паттерна (не удаляем, а обрезаем)
                result = result[:match.start()].strip()
                break
        
        # Удаляем висячий дефис или знак равенства в конце
        result = re.sub(r'\s*[-=]\s*$', '', result)
        result = result.strip()
        
        return result

    def _parse_table_format(self, lines: List[str], delimiter: str) -> pd.DataFrame:
        """
        Парсит текст как таблицу с разделителями.
        """
        rows = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            if delimiter == '  ':
                parts = re.split(r'\s{2,}', line)
            elif delimiter == ' ':
                parts = line.split()
            else:
                parts = line.split(delimiter)
            
            clean_parts = [p.strip() for p in parts if p.strip()]
            if clean_parts:
                rows.append(clean_parts)
        
        if not rows:
            return pd.DataFrame()
        
        max_cols = max(len(row) for row in rows)
        for row in rows:
            while len(row) < max_cols:
                row.append("")
        
        df = pd.DataFrame(rows)
        df = df.replace(r'^\s*$', '', regex=True)
        df = df.fillna('')
        return df

    def _detect_delimiter(self, lines: List[str]) -> str:
        """Определяет разделитель в табличных данных."""
        if any('\t' in line for line in lines):
            return '\t'
        if any('|' in line for line in lines):
            return '|'
        if any(',' in line for line in lines):
            return ','
        if any(';' in line for line in lines):
            return ';'
        if any(re.search(r'\s{3,}', line) for line in lines):
            return '  '
        return ' '

    def _parse_text(self) -> None:
        """Основной метод разбора текста."""
        text = self._text_area.get("1.0", tk.END).strip()
        if not text:
            messagebox.showwarning("Предупреждение", "Нет данных для разбора")
            return

        self._raw_text = text
        lines = text.split('\n')
        format_mode = self._format_var.get()
        non_empty_lines = [l for l in lines if l.strip()]

        if not non_empty_lines:
            messagebox.showwarning("Предупреждение", "Нет данных для разбора")
            return

        df = None
        
        # Определяем формат
        is_list = False
        if format_mode == "list":
            is_list = True
        elif format_mode == "table":
            is_list = False
        else:  # auto
            is_list = self._is_list_format(non_empty_lines)
        
        if is_list:
            # Парсим как список
            df = self._parse_list_format(non_empty_lines)
            if df is not None and not df.empty:
                # Для списка автоматически определяем колонки
                self._df = df
                self._show_preview(df)
                
                # Устанавливаем колонки для выбора
                columns = ["Наименование", "Кол-во"]
                self._name_col_combo["values"] = columns
                self._qty_col_combo["values"] = columns
                self._name_col_combo.current(0)
                self._qty_col_combo.current(1)
                self._on_selection_changed()
                
                self._info_label.config(text=f"Разобрано: {len(df)} строк, 2 столбца (список)")
                return
        else:
            # Парсим как таблицу
            delimiter = self._detect_delimiter(non_empty_lines)
            df = self._parse_table_format(non_empty_lines, delimiter)
        
        if df is None or df.empty:
            messagebox.showwarning("Предупреждение", "Не удалось разобрать данные")
            return

        self._df = df
        self._show_preview(df)

        columns = [f"Col_{i}" for i in range(len(df.columns))]
        self._name_col_combo["values"] = columns
        self._qty_col_combo["values"] = columns
        self._auto_detect_columns(df)

        self._info_label.config(text=f"Разобрано: {len(df)} строк, {len(df.columns)} столбцов")

    def _show_preview(self, df: pd.DataFrame) -> None:
        """Показывает предпросмотр DataFrame в таблице."""
        self._preview_tree.delete(*self._preview_tree.get_children())
        columns = list(df.columns)
        self._preview_tree["columns"] = columns
        for i, col in enumerate(columns):
            self._preview_tree.heading(col, text=f"{col}")
            self._preview_tree.column(col, width=150, minwidth=80)
        for _, row in df.head(100).iterrows():
            values = [str(v)[:100] for v in row.values]
            self._preview_tree.insert("", "end", values=values)

    def _auto_detect_columns(self, df: pd.DataFrame) -> None:
        """Автоматически определяет столбцы для названия и количества."""
        if df.empty:
            return

        name_col = 0
        qty_col = 1 if len(df.columns) > 1 else 0

        for i, col in enumerate(df.columns):
            col_values = df[col].astype(str).str.strip()
            sample = col_values.head(10)
            
            # Проверяем, может ли это быть количество
            numeric_count = sum(1 for v in sample if v.isdigit())
            if numeric_count >= 2:
                qty_col = i
            
            # Проверяем, может ли это быть артикул или название
            article_count = sum(1 for v in sample if re.search(r'7724[67]\d{5}', v))
            if article_count >= 1:
                name_col = i
            
            # Длинный текст — скорее всего название
            if name_col == 0:
                long_text_count = sum(1 for v in sample if len(v) > 10)
                if long_text_count >= 2:
                    name_col = i

        if name_col == qty_col:
            qty_col = 1 if name_col != 1 else 0

        if name_col < len(df.columns) and qty_col < len(df.columns):
            self._name_col_combo.current(name_col)
            self._qty_col_combo.current(qty_col)
        self._on_selection_changed()

    def _on_selection_changed(self, event=None) -> None:
        """Обработчик изменения выбора столбцов."""
        name_col = self._name_col_combo.current()
        qty_col = self._qty_col_combo.current()
        if name_col >= 0 and qty_col >= 0 and name_col != qty_col:
            self._confirm_btn.config(state="normal")
        else:
            self._confirm_btn.config(state="disabled")

    def _parse_qty(self, value) -> int:
        """Парсит количество из значения."""
        if value is None:
            return 0
        str_value = str(value).strip()
        if not str_value:
            return 0
        
        # Удаляем "шт" и подобное
        cleaned = re.sub(r'\s*шт\.?\s*', '', str_value, flags=re.IGNORECASE)
        cleaned = cleaned.replace(' ', '').replace(',', '.')
        cleaned = re.sub(r'[^\d.]', '', cleaned)
        
        parts = cleaned.split('.')
        if len(parts) > 2:
            cleaned = parts[0] + '.' + ''.join(parts[1:])
        
        try:
            val = float(cleaned)
            return int(val) if abs(val - round(val)) < 0.001 else 0
        except (ValueError, TypeError):
            match = re.search(r'(\d+)', str_value)
            if match:
                return int(match.group(1))
            return 0

    def _on_confirm(self) -> None:
        """Подтверждение выбора столбцов."""
        if self._df is None or self._df.empty:
            messagebox.showwarning("Предупреждение", "Нет данных для обработки")
            return

        name_col_index = self._name_col_combo.current()
        qty_col_index = self._qty_col_combo.current()

        if name_col_index < 0 or qty_col_index < 0:
            messagebox.showwarning("Предупреждение", "Выберите столбцы")
            return

        if name_col_index == qty_col_index:
            messagebox.showwarning("Предупреждение", "Столбцы должны быть разными")
            return

        # Получаем имена выбранных столбцов
        name_col_name = self._name_col_combo.get()
        qty_col_name = self._qty_col_combo.get()
        
        # Определяем реальные индексы столбцов
        if name_col_name in self._df.columns:
            name_col = self._df.columns.get_loc(name_col_name)
        else:
            name_col = name_col_index
        
        if qty_col_name in self._df.columns:
            qty_col = self._df.columns.get_loc(qty_col_name)
        else:
            qty_col = qty_col_index

        # СОЗДАЁМ DataFrame ТОЛЬКО ИЗ ВЫБРАННЫХ СТОЛБЦОВ
        result_df = self._df[[self._df.columns[name_col], self._df.columns[qty_col]]].copy()
        result_df.columns = ['Наименование', 'Кол-во']
        
        # Парсим количество
        result_df['Кол-во'] = result_df['Кол-во'].apply(self._parse_qty)
        
        # Удаляем пустые строки
        result_df = result_df[result_df['Наименование'].astype(str).str.strip() != '']
        result_df = result_df[result_df['Кол-во'] > 0]

        if result_df.empty:
            messagebox.showwarning("Предупреждение", "Нет валидных данных после обработки")
            return

        # Получаем выбранные категории
        selected_categories = self.get_selected_categories()
        
        self._dialog.destroy()
        
        if self.callback:
            # Передаём DataFrame и выбранные категории
            self.callback(result_df, selected_categories)

    def _on_cancel(self) -> None:
        """Отмена и закрытие диалога."""
        self._dialog.destroy()