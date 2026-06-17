"""
Диалог отображения результатов подбора оборудования.
С разделителем между таблицей результатов и исходными данными.
"""

import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional, List, Dict

import pandas as pd

from nextt.logger import get_logger
from nextt.utils.window_manager import get_safe_geometry
from nextt.config import config

logger = get_logger(__name__)


class EquipmentDialog:
    """Диалог с результатами подбора оборудования."""

    def __init__(self, app, matches: List[Dict], original_text: str = ""):
        """
        Args:
            app: экземпляр App
            matches: список результатов подбора
            original_text: исходный текст из буфера обмена
        """
        self.app = app
        self.font_manager = app.font_manager
        self.matches = matches
        self.original_text = original_text
        self._dialog: Optional[tk.Toplevel] = None
        self._tree: Optional[ttk.Treeview] = None
        self._original_text_widget: Optional[tk.Text] = None
        self._paned_window: Optional[tk.PanedWindow] = None
        
        # Ключ для сохранения позиции разделителя
        self._settings_key = "equipment_dialog_pane_position"

    def show(self) -> None:
        """Показывает диалоговое окно."""
        self._create_dialog()

    def _copy_column_to_clipboard(self, col_index: int) -> None:
        """
        Копирует все значения из указанного столбца в буфер обмена.
        col_index: 0 - Артикул, 1 - Наименование, 2 - Количество
        """
        if not self._tree:
            return
        
        items = self._tree.get_children()
        values = []
        
        for item in items:
            row_values = self._tree.item(item, "values")
            if row_values and len(row_values) > col_index:
                val = str(row_values[col_index]).strip()
                if val and val != "0":
                    values.append(val)
        
        if not values:
            return
        
        try:
            import pyperclip
            pyperclip.copy('\n'.join(values))
        except ImportError:
            self._dialog.clipboard_clear()
            self._dialog.clipboard_append('\n'.join(values))
            self._dialog.update()
        
        self._focus_main_window()

    def _focus_main_window(self) -> None:
        """Переключает фокус на главное окно приложения."""
        if not self._dialog or not self._dialog.winfo_exists():
            return
        
        try:
            self._dialog.lower()
            self._dialog.grab_release()
            
            if hasattr(self.app, 'root') and self.app.root.winfo_exists():
                self.app.root.attributes('-topmost', True)
                self.app.root.focus_force()
                self.app.root.attributes('-topmost', False)
            
            self._dialog.after(100, self._regrab_dialog)
            
        except Exception as e:
            logger.debug(f"Ошибка при переключении фокуса: {e}")
    
    def _regrab_dialog(self) -> None:
        """Восстанавливает граб диалога."""
        if self._dialog and self._dialog.winfo_exists():
            try:
                self._dialog.grab_set()
            except Exception as e:
                logger.debug(f"Ошибка при восстановлении граба: {e}")

    def _copy_articles(self) -> None:
        """Копирует все артикулы в буфер."""
        self._copy_column_to_clipboard(0)

    def _copy_names(self) -> None:
        """Копирует все наименования в буфер."""
        self._copy_column_to_clipboard(1)

    def _copy_quantities(self) -> None:
        """Копирует все количества в буфер."""
        self._copy_column_to_clipboard(2)

    def _apply_window_style(self) -> None:
        """Применяет правильный стиль окна через Windows API (без мерцания)."""
        import platform
        if platform.system() != "Windows" or not self._dialog:
            return

        try:
            import ctypes

            winfo_id = self._dialog.winfo_id()
            hwnd = ctypes.windll.user32.GetParent(winfo_id)
            
            if hwnd == 0:
                hwnd = winfo_id
            
            GWL_STYLE = -16
            WS_SYSMENU = 0x80000
            WS_THICKFRAME = 0x40000
            WS_MINIMIZEBOX = 0x20000
            WS_MAXIMIZEBOX = 0x10000
            WS_CAPTION = 0xC00000
            
            current_style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_STYLE)
            new_style = current_style | WS_SYSMENU | WS_THICKFRAME | WS_MINIMIZEBOX | WS_MAXIMIZEBOX | WS_CAPTION
            
            if new_style != current_style:
                ctypes.windll.user32.SetWindowLongW(hwnd, GWL_STYLE, new_style)
                
                SWP_NOMOVE = 0x0002
                SWP_NOSIZE = 0x0001
                SWP_NOZORDER = 0x0004
                SWP_FRAMECHANGED = 0x0020
                flags = SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED
                
                ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, flags)
            
        except Exception as e:
            logger.debug(f"Не удалось применить стиль окна: {e}")

    def _get_saved_pane_position(self) -> Optional[int]:
        """Возвращает сохранённую позицию разделителя."""
        try:
            position = config.get(self._settings_key)
            if position and isinstance(position, int) and 100 < position < 800:
                return position
        except Exception as e:
            logger.debug(f"Ошибка загрузки позиции разделителя: {e}")
        return None

    def _save_pane_position(self) -> None:
        """Сохраняет позицию разделителя."""
        if self._paned_window and self._paned_window.winfo_exists():
            try:
                position = self._paned_window.sashpos(0)
                if position > 100:
                    config.set(self._settings_key, position)
                    config.save()
                    logger.debug(f"Сохранена позиция разделителя: {position}")
            except Exception as e:
                logger.debug(f"Ошибка сохранения позиции разделителя: {e}")

    def _create_dialog(self) -> None:
        """Создаёт окно диалога с разделителем."""
        self._dialog = tk.Toplevel(self.app.root)
        
        # ========== НАСТРОЙКА ОКНА ==========
        self._dialog.title("Подбор оборудования LaggarTT")
        self._dialog.attributes('-toolwindow', False)
        self._dialog.resizable(True, True)
        self._dialog.attributes('-topmost', False)

        self._apply_window_style()

        # Устанавливаем размер окна на весь экран, но с учётом панели задач
        screen_width = self._dialog.winfo_screenwidth()
        screen_height = self._dialog.winfo_screenheight()
        
        taskbar_height = 80
        window_height = screen_height - taskbar_height
        
        self._dialog.geometry(f"{screen_width}x{window_height}+0+0")
        self._dialog.update_idletasks()

        self._dialog.configure(bg='#f5f5f5')
        self._dialog.transient(self.app.root)
        self._dialog.grab_set()

        self._apply_window_style()
        self._dialog.configure(bg='#f5f5f5')
        self._dialog.transient(self.app.root)
        self._dialog.grab_set()

        # Получаем масштабированные шрифты
        if self.font_manager:
            default_font = self.font_manager.get_default_font()
            bold_font = self.font_manager.get_bold_font()
        else:
            default_font = ("Segoe UI", 9)
            bold_font = ("Segoe UI", 9, "bold")

        # Настраиваем стили ttk
        style = ttk.Style()
        style.configure("EqDlg.TFrame", background='#f5f5f5')
        style.configure("EqDlg.TLabel", background='#f5f5f5', font=default_font)
        style.configure("EqDlg.TButton", font=default_font)
        style.configure("EqDlg.Treeview", font=default_font, rowheight=25)
        style.configure("EqDlg.Treeview.Heading", font=bold_font)

        # ========== ИСПОЛЬЗУЕМ GRID ДЛЯ ГЛАВНОГО КОНТЕЙНЕРА ==========
        main_frame = ttk.Frame(self._dialog, padding="10", style="EqDlg.TFrame")
        main_frame.pack(fill="both", expand=True)
        
        main_frame.grid_rowconfigure(0, weight=1)
        main_frame.grid_rowconfigure(1, weight=0)
        main_frame.grid_rowconfigure(2, weight=0)
        main_frame.grid_columnconfigure(0, weight=1)

        # ========== PANED WINDOW (РАЗДЕЛИТЕЛЬ) ==========
        self._paned_window = tk.PanedWindow(
            main_frame, 
            orient=tk.VERTICAL, 
            sashrelief=tk.RAISED, 
            sashwidth=6,
            bg='#f5f5f5'
        )
        self._paned_window.grid(row=0, column=0, sticky="nsew", pady=(0, 5))

        # ========== ВЕРХНЯЯ ПАНЕЛЬ: ТАБЛИЦА РЕЗУЛЬТАТОВ ==========
        table_frame = ttk.Frame(self._paned_window, style="EqDlg.TFrame")
        
        columns = ("Артикул", "Наименование", "Количество")
        self._tree = ttk.Treeview(
            table_frame, 
            columns=columns, 
            show="headings", 
            height=12,
            selectmode="extended",
            style="EqDlg.Treeview"
        )

        self._tree.heading("Артикул", text="Артикул", command=self._copy_articles)
        self._tree.heading("Наименование", text="Наименование", command=self._copy_names)
        self._tree.heading("Количество", text="Количество", command=self._copy_quantities)
        
        self._tree.column("Артикул", width=180, anchor="center")
        self._tree.column("Наименование", width=500, anchor="w")
        self._tree.column("Количество", width=100, anchor="center")

        # ========== НАСТРАИВАЕМ ТЕГИ ДЛЯ ЦВЕТОВ ==========
        self._tree.tag_configure("found", background="#e8f5e9")
        self._tree.tag_configure("not_found", background="#ffebee")
        self._tree.tag_configure("doubtful", background="#fff3e0")
        # ===================================================

        # ========== ЗАПОЛНЯЕМ ТАБЛИЦУ И СОХРАНЯЕМ СОМНИТЕЛЬНЫЕ ИНДЕКСЫ ==========
        self._doubtful_indices = []

        for i, match in enumerate(self.matches):
            article = match.get('article', '')
            name = match.get('name', '')
            quantity = match.get('quantity', 0)
            success = match.get('success', False)
            source = match.get('source', '')
            confidence = match.get('confidence', 0.0)
            confidence_note = match.get('confidence_note', '')
            original_text = match.get('original_text', '')

            is_doubtful = False
            tag = "not_found"
            display_name = name
            
            if success and name:
                display_name = name
                
                if source == "нормализатор" and confidence < 1.0:
                    is_doubtful = True
                    tag = "doubtful"
                    if not confidence_note:
                        confidence_note = f"Подобран через нормализатор (уверенность {confidence:.0%})"
                elif source == "нормализатор" and confidence >= 1.0:
                    is_doubtful = True
                    tag = "doubtful"
                    if not confidence_note:
                        confidence_note = "Подобран через нормализатор"
                elif confidence > 0 and confidence < 0.95:
                    is_doubtful = True
                    tag = "doubtful"
                    if not confidence_note:
                        confidence_note = f"Низкая уверенность ({confidence:.0%})"
                elif source == "нормализатор" and confidence_note:
                    is_doubtful = True
                    tag = "doubtful"
                elif confidence_note:
                    is_doubtful = True
                    tag = "doubtful"
                else:
                    tag = "found"
            else:
                display_name = f"[НЕ НАЙДЕНО] {original_text[:80]}"
                tag = "not_found"
                if not confidence_note:
                    confidence_note = "Не найдено в базе"

            # Сохраняем индекс сомнительной строки
            if is_doubtful:
                self._doubtful_indices.append(i)

            self._tree.insert("", "end", values=[article, display_name, quantity], tags=(tag,))
        # ======================================================================

        # Скроллбары для таблицы
        vsb = ttk.Scrollbar(table_frame, orient="vertical", command=self._tree.yview)
        hsb = ttk.Scrollbar(table_frame, orient="horizontal", command=self._tree.xview)
        self._tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        
        self._tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        
        table_frame.grid_rowconfigure(0, weight=1)
        table_frame.grid_columnconfigure(0, weight=1)

        self._paned_window.add(table_frame, stretch="always")

        # ========== НИЖНЯЯ ПАНЕЛЬ: ИСХОДНЫЕ ДАННЫЕ ==========
        if self.original_text:
            original_frame = ttk.Frame(self._paned_window, style="EqDlg.TFrame")
            
            text_container = ttk.Frame(original_frame)
            text_container.pack(fill="both", expand=True, padx=5, pady=5)

            self._original_text_widget = tk.Text(
                text_container, 
                wrap="none", 
                font=default_font, 
                bg="#f9f9f9",
                relief="solid",
                borderwidth=1
            )
            self._original_text_widget.pack(side="left", fill="both", expand=True)
            
            # ========== НАСТРАИВАЕМ ТЕГ ДЛЯ ПОДСВЕТКИ ==========
            self._original_text_widget.tag_configure("doubtful_line", background="#fff3e0")
            # ===================================================

            # ========== ВСТАВЛЯЕМ ТЕКСТ С ПОДСВЕТКОЙ ==========
            lines = self.original_text.split('\n')
            
            # Проходим по строкам и проверяем, является ли строка сомнительной
            # Сопоставляем matches[i] со строкой i (порядок сохраняется)
            for i, line in enumerate(lines):
                # Проверяем, есть ли этот индекс в списке сомнительных
                if i in self._doubtful_indices:
                    # Добавляем красный восклицательный знак в конце
                    display_line = line.rstrip() + " ❗"
                    self._original_text_widget.insert(f"{i+1}.0", display_line + "\n", "doubtful_line")
                else:
                    self._original_text_widget.insert(f"{i+1}.0", line + "\n")
            # ===================================================
            
            self._original_text_widget.config(state="disabled")
            
            text_vsb = ttk.Scrollbar(text_container, orient="vertical", command=self._original_text_widget.yview)
            text_hsb = ttk.Scrollbar(original_frame, orient="horizontal", command=self._original_text_widget.xview)
            self._original_text_widget.configure(yscrollcommand=text_vsb.set, xscrollcommand=text_hsb.set)
            text_vsb.pack(side="right", fill="y")
            text_hsb.pack(side="bottom", fill="x")
            
            self._paned_window.add(original_frame, stretch="always")
            
            saved_position = self._get_saved_pane_position()
            if saved_position:
                self._dialog.after(100, lambda: self._paned_window.sashpos(0, saved_position))

        # ========== ОТСТУП МЕЖДУ PANEDWINDOW И КНОПКОЙ ==========
        separator = ttk.Frame(main_frame, height=5, style="EqDlg.TFrame")
        separator.grid(row=1, column=0, sticky="ew")

        # ========== КНОПКА ЗАКРЫТИЯ ==========
        control_frame = ttk.Frame(main_frame, style="EqDlg.TFrame")
        control_frame.grid(row=2, column=0, sticky="ew")
        
        ttk.Button(control_frame, text="Закрыть", command=self._close, 
                   width=15, style="EqDlg.TButton").pack(side="right", padx=5, pady=5)

        self._dialog.protocol("WM_DELETE_WINDOW", self._close)
        self._tree.focus_set()

    def _close(self) -> None:
        """Закрывает диалог и сохраняет позицию разделителя."""
        self._save_pane_position()
        if self._dialog:
            self._dialog.destroy()
            self._dialog = None
            self._tree = None
            self._original_text_widget = None
            self._paned_window = None