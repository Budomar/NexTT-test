"""
Диалог выбора аналога LaggarTT.
Полноценная версия — матрица высот и длин с плавающей кнопкой.
С поддержкой масштабирования шрифтов.
"""

import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional, Dict, Tuple

import numpy as np

from nextt.logger import get_logger

logger = get_logger(__name__)


class MeteorSelector:
    """Окно подбора аналога LaggarTT."""

    HEIGHTS = [300, 400, 500, 600, 900]
    LENGTHS = list(range(400, 3100, 100))

    def __init__(self, app):
        self.app = app
        self.font_manager = app.font_manager  # Сохраняем ссылку на FontManager
        self._dialog: Optional[tk.Toplevel] = None

        # Текущий выбор
        self._selected_connection = tk.StringVar(value="VK-правое")
        self._selected_type = tk.StringVar(value="10")

        # Для матрицы
        self._matrix_frame: Optional[ttk.Frame] = None
        self._matrix_cells: Dict[Tuple[int, int], tk.Label] = {}
        self._row_headers: Dict[int, tk.Label] = {}
        self._col_headers: Dict[int, tk.Label] = {}

        # Плавающая кнопка
        self._current_button: Optional[tk.Button] = None
        self._current_cell: Optional[Tuple[int, int]] = None

        # Предпросмотр
        self._preview_height: Optional[int] = None
        self._preview_length: Optional[int] = None

        # Переменные для отображения итогов
        self._analog_name_var = tk.StringVar(value="Выберите параметры")
        self._article_var = tk.StringVar(value="—")
        self._power_var = tk.StringVar(value="—")
        self._weight_var = tk.StringVar(value="—")
        self._volume_var = tk.StringVar(value="—")

        # Для обновления таблицы соответствия
        self._tree_reference: Optional[ttk.Treeview] = None
        self._current_item: Optional[str] = None
        self._original_name: str = ""

        # Callback для переподбора после обучения
        self._apply_patterns_callback: Optional[callable] = None
        # Callback для сохранения состояния после закрытия
        self._on_close_callback: Optional[callable] = None

    def set_apply_patterns_callback(self, callback: callable) -> None:
        """
        Устанавливает callback, который будет вызван после сохранения паттерна
        для автоматического переподбора всех строк таблицы соответствия.
        """
        self._apply_patterns_callback = callback

    def set_on_close_callback(self, callback: callable) -> None:
        """
        Устанавливает callback, который будет вызван при закрытии окна.
        Используется для сохранения состояния таблицы соответствия.
        """
        self._on_close_callback = callback

    def show(self, tree: ttk.Treeview, item: str, original_name: str) -> None:
        """Показывает диалог выбора аналога."""
        if self._dialog and self._dialog.winfo_exists():
            self._dialog.lift()
            self._dialog.focus_force()
            return

        self._tree_reference = tree
        self._current_item = item
        self._original_name = original_name
        
        # Запоминаем родительское окно (то, в котором находится tree)
        self._parent_window = tree.winfo_toplevel()

        self._create_dialog()

    def _create_dialog(self) -> None:
        """Создаёт окно диалога."""
        # Используем родительское окно таблицы соответствия, а не главное окно
        parent = self._parent_window if self._parent_window else self.app.root
        self._dialog = tk.Toplevel(parent)
        
        # Настройка окна (кнопки свернуть/развернуть/закрыть)
        from nextt.utils.window_manager import setup_dialog_window
        setup_dialog_window(self._dialog, f"Подбор аналога LaggarTT для: {self._original_name[:60]}...")

        # Полноэкранный режим
        from nextt.utils.window_manager import get_safe_geometry
        geom = get_safe_geometry(self._dialog)
        parts = geom.replace('x', '+').split('+')
        w = int(parts[0])
        h = int(parts[1]) - 35
        x = int(parts[2])
        y = int(parts[3])
        self._dialog.geometry(f"{w}x{h}+{x}+{y}")
        self._dialog.configure(bg='#f5f5f5')

        # Получаем масштабированные шрифты
        default_font = self.font_manager.get_default_font()
        heading_font = self.font_manager.get_heading_font()
        bold_font = self.font_manager.get_bold_font()

        main_container = ttk.Frame(self._dialog)
        main_container.pack(fill="both", expand=True, padx=20, pady=20)

        # --- Заголовок ---
        header = ttk.Frame(main_container)
        header.pack(fill="x", pady=(0, 15))

        title_text = tk.Text(
            header, font=heading_font, foreground="#2c3e50",
            background="#f5f5f5", wrap="word", height=2,
            padx=0, pady=0, borderwidth=0, highlightthickness=0, relief="flat"
        )
        title_text.pack(anchor="w", fill="x")
        title_text.insert("1.0", f"Подбор аналога LaggarTT для: {self._original_name}")
        title_text.config(state="disabled")

        # --- Блок настроек ---
        settings_frame = ttk.Frame(main_container)
        settings_frame.pack(fill="x", pady=(0, 20))

        settings_container = ttk.Frame(settings_frame)
        settings_container.pack(fill="x", expand=True)
        settings_container.columnconfigure(0, weight=30, minsize=200)
        settings_container.columnconfigure(1, weight=40, minsize=300)
        settings_container.columnconfigure(2, weight=30, minsize=200)

        # ШАГ 1: Подключение
        step1 = ttk.LabelFrame(settings_container, text="ШАГ 1: ПОДКЛЮЧЕНИЕ", padding=10)
        step1.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

        for conn in ["VK-правое", "VK-левое", "K-боковое"]:
            ttk.Radiobutton(
                step1, text=conn, variable=self._selected_connection, value=conn,
                command=self._on_connection_changed
            ).pack(side="left", padx=5)

        # ШАГ 2: Тип радиатора
        self._step2_frame = ttk.LabelFrame(settings_container, text="ШАГ 2: ТИП РАДИАТОРА", padding=10)
        self._step2_frame.grid(row=0, column=1, sticky="nsew", padx=(0, 10))
        self._step2_inner = ttk.Frame(self._step2_frame)
        self._step2_inner.pack(expand=True, fill="both")
        self._update_available_types()

        # ИТОГИ ВЫБОРА
        summary = ttk.LabelFrame(settings_container, text="ИТОГИ ВЫБОРА", padding=10)
        summary.grid(row=0, column=2, sticky="nsew")

        summary_grid = ttk.Frame(summary)
        summary_grid.pack(fill="both", expand=True)

        ttk.Label(summary_grid, textvariable=self._analog_name_var,
                  font=bold_font, foreground="#2c3e50").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 5))

        ttk.Label(summary_grid, text="Артикул:", font=bold_font).grid(row=1, column=0, sticky="w")
        ttk.Label(summary_grid, textvariable=self._article_var, font=default_font).grid(
            row=1, column=1, sticky="w", padx=(5, 0))

        ttk.Label(summary_grid, text="Мощность:", font=bold_font).grid(
            row=2, column=0, sticky="w", pady=(2, 0))
        ttk.Label(summary_grid, textvariable=self._power_var, font=default_font).grid(
            row=2, column=1, sticky="w", padx=(5, 0), pady=(2, 0))

        ttk.Label(summary_grid, text="Вес:", font=bold_font).grid(
            row=3, column=0, sticky="w", pady=(2, 0))
        ttk.Label(summary_grid, textvariable=self._weight_var, font=default_font).grid(
            row=3, column=1, sticky="w", padx=(5, 0), pady=(2, 0))

        ttk.Label(summary_grid, text="Объем:", font=bold_font).grid(
            row=4, column=0, sticky="w", pady=(2, 0))
        ttk.Label(summary_grid, textvariable=self._volume_var, font=default_font).grid(
            row=4, column=1, sticky="w", padx=(5, 0), pady=(2, 0))

        summary_grid.columnconfigure(1, weight=1)

        # --- Матрица ---
        matrix_container = ttk.LabelFrame(main_container, text="ШАГ 3: ВЫБОР РАЗМЕРА")
        matrix_container.pack(fill="both", expand=True, pady=(0, 20))

        self._matrix_frame = tk.Frame(matrix_container, bg='#f5f5f5')
        self._matrix_frame.pack(fill="both", expand=True, padx=5, pady=5)

        # Заглушка "Загрузка..."
        self._loading_label = tk.Label(
            self._matrix_frame, text="Загрузка матрицы...",
            font=default_font, bg="#f5f5f5", fg="#888888"
        )
        self._loading_label.pack(expand=True)

        self._dialog.after(50, self._create_adaptive_matrix)

        # --- Нижняя панель ---
        bottom = ttk.Frame(main_container)
        bottom.pack(fill="x", side="bottom", pady=(10, 0))
        bottom.columnconfigure(0, weight=7)
        bottom.columnconfigure(1, weight=3)

        # Инструкция
        instruction_text = (
            "1. ВЫБЕРИТЕ ПОДКЛЮЧЕНИЕ:\n"
            "• VK-правое/левое — нижнее подключение\n"
            "• K-боковое — боковое подключение\n\n"
            "2. ВЫБЕРИТЕ ТИП:\n"
            "• Для радиаторов с нижним правым: 10, 11, 20, 21, 22, 30, 33\n"
            "• Для радиаторов с нижним левым: 10, 11, 30, 33\n"
            "• Для радиаторов с боковым: 10, 11, 20, 21, 22, 30, 33\n\n"
            "3. ВЫБЕРИТЕ РАЗМЕР:\n"
            "• Горизонтально — ДЛИНА (мм)\n"
            "• Вертикально — ВЫСОТА (мм)\n"
            "• Наведите курсор на ячейку и нажмите «ВЫБРАТЬ»\n\n"
            "4. ИТОГИ ВЫБОРА:\n"
            "• При наведении отображаются фактические данные"
        )
        instr_label = tk.Label(
            bottom, text=instruction_text, bg="#f9f9f9", relief="solid",
            borderwidth=1, padx=10, pady=5, justify="left", anchor="nw",
            wraplength=600, font=default_font
        )
        instr_label.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

        # Кнопка Закрыть
        btn_container = ttk.Frame(bottom)
        btn_container.grid(row=0, column=1, sticky="nsew")
        btn_container.grid_rowconfigure(0, weight=1)
        btn_container.grid_rowconfigure(2, weight=1)
        btn_container.grid_columnconfigure(0, weight=1)
        btn_container.grid_columnconfigure(2, weight=1)

        ttk.Button(btn_container, text="Закрыть", command=self._close, width=15).grid(
            row=1, column=1, sticky="")

    def _update_available_types(self) -> None:
        """Обновляет доступные типы радиаторов."""
        for w in self._step2_inner.winfo_children():
            w.destroy()

        conn = self._selected_connection.get()
        if conn == "VK-левое":
            types = ["10", "11", "30", "33"]
        else:
            types = ["10", "11", "20", "21", "22", "30", "33"]

        for rt in types:
            ttk.Radiobutton(
                self._step2_inner, text=f"Тип {rt}",
                variable=self._selected_type, value=rt,
                command=self._update_preview
            ).pack(side="left", padx=5)

        if self._selected_type.get() not in types:
            self._selected_type.set(types[0])

    def _on_connection_changed(self) -> None:
        """Обработчик смены подключения."""
        self._update_available_types()
        self._update_preview()

    def _create_adaptive_matrix(self) -> None:
        """Создаёт адаптивную матрицу с плавающей кнопкой."""
        if hasattr(self, '_loading_label') and self._loading_label:
            self._loading_label.destroy()
            self._loading_label = None

        for w in self._matrix_frame.winfo_children():
            w.destroy()

        self._matrix_cells.clear()
        self._row_headers.clear()
        self._col_headers.clear()
        self._current_button = None
        self._current_cell = None

        # Получаем масштабированные шрифты
        default_font = self.font_manager.get_default_font()
        small_font = self.font_manager.get_font(7)
        bold_font = self.font_manager.get_bold_font()

        # Размеры
        num_cols = len(self.LENGTHS) + 1
        container_w = self._matrix_frame.winfo_width()
        if container_w < 100:
            container_w = self._dialog.winfo_width() - 100
        cell_w = max(50, container_w // num_cols)
        row_h = max(30, int(35 * self.font_manager.scale))

        # Уголок
        corner = tk.Label(
            self._matrix_frame, text="ДЛИНА →\nВЫСОТА ↓",
            font=bold_font, relief='ridge', borderwidth=1,
            bg='#e8e8e8', fg='#000000', anchor="center", justify="center",
            width=12, height=2
        )
        corner.grid(row=0, column=0, sticky="nsew", padx=1, pady=1)

        # Заголовки столбцов
        for j, length in enumerate(self.LENGTHS):
            lbl = tk.Label(
                self._matrix_frame, text=str(length),
                font=bold_font, relief='ridge', borderwidth=1,
                bg='#e8e8e8', fg='#000000', anchor="center", width=8, height=1
            )
            lbl.grid(row=0, column=j + 1, sticky="nsew", padx=1, pady=1)
            self._col_headers[length] = lbl

        # Строки
        for i, height in enumerate(self.HEIGHTS):
            lbl = tk.Label(
                self._matrix_frame, text=str(height),
                font=bold_font, relief='ridge', borderwidth=1,
                bg='#e8e8e8', fg='#000000', anchor="center", width=12, height=1
            )
            lbl.grid(row=i + 1, column=0, sticky="nsew", padx=1, pady=1)
            self._row_headers[height] = lbl

            for j, length in enumerate(self.LENGTHS):
                cell = tk.Label(
                    self._matrix_frame, text="",
                    font=small_font, relief='ridge', borderwidth=1,
                    bg='#faf7f4', fg='#999999', anchor="center"
                )
                cell.grid(row=i + 1, column=j + 1, sticky="nsew", padx=1, pady=1)
                self._matrix_cells[(height, length)] = cell

        # Размеры колонок
        for col in range(num_cols):
            self._matrix_frame.columnconfigure(col, weight=1, minsize=cell_w)
        for row in range(len(self.HEIGHTS) + 1):
            self._matrix_frame.rowconfigure(row, weight=0, minsize=row_h)

        # События
        self._matrix_frame.bind("<Motion>", self._on_matrix_motion)
        self._matrix_frame.bind("<Leave>", self._on_matrix_leave)

        for lbl in list(self._col_headers.values()) + list(self._row_headers.values()) + list(self._matrix_cells.values()):
            lbl.bind("<Motion>", self._on_matrix_motion)

    def _on_matrix_motion(self, event) -> None:
        """Движение мыши над матрицей."""
        if event.widget != self._matrix_frame:
            x = event.x_root - self._matrix_frame.winfo_rootx()
            y = event.y_root - self._matrix_frame.winfo_rooty()
        else:
            x, y = event.x, event.y

        grid_info = self._matrix_frame.grid_location(x, y)
        col, row = grid_info

        if row < 1 or row > len(self.HEIGHTS) or col < 1 or col > len(self.LENGTHS):
            self._remove_floating_button()
            self._current_cell = None
            return

        new_cell = (row, col)
        if new_cell == self._current_cell:
            return

        self._remove_floating_button()

        height = self.HEIGHTS[row - 1]
        length = self.LENGTHS[col - 1]

        # Получаем мелкий шрифт для кнопки
        small_font = self.font_manager.get_font(7)

        btn = tk.Button(
            self._matrix_frame, text="ВЫБРАТЬ", font=small_font,
            relief='raised', borderwidth=1, bg='#263168', fg='white',
            activebackground='#1a2456', activeforeground='white',
            cursor='hand2', command=lambda h=height, l=length: self._select_size(h, l)
        )
        btn.grid(row=row, column=col, sticky="nsew", padx=1, pady=1)
        btn.lift()

        self._current_button = btn
        self._current_cell = new_cell

        # Подсветка заголовков
        if row >= 1 and row <= len(self.HEIGHTS):
            h_key = self.HEIGHTS[row - 1]
            if h_key in self._row_headers:
                self._row_headers[h_key].config(bg='#c8c8c8')
        if col >= 1 and col <= len(self.LENGTHS):
            l_key = self.LENGTHS[col - 1]
            if l_key in self._col_headers:
                self._col_headers[l_key].config(bg='#c8c8c8')

        self._preview_height = height
        self._preview_length = length
        self._update_preview()

    def _on_matrix_leave(self, event=None) -> None:
        """Уход мыши с матрицы."""
        self._remove_floating_button()
        self._current_cell = None

    def _remove_floating_button(self) -> None:
        """Убирает плавающую кнопку."""
        if self._current_button:
            try:
                self._current_button.destroy()
            except tk.TclError:
                pass
            self._current_button = None

        for h in self._row_headers.values():
            h.config(bg='#e8e8e8')
        for h in self._col_headers.values():
            h.config(bg='#e8e8e8')

    def _select_size(self, height: int, length: int) -> None:
        """Выбор размера и применение аналога."""
        conn = self._selected_connection.get()
        rt = self._selected_type.get()

        # Исправление для универсальных типов
        search_conn = conn
        saved_conn = conn
        if conn == "VK-левое" and rt in ('20', '21', '22'):
            search_conn = "VK-правое"
            saved_conn = "VK-правое"

        art, name = self.app.data_provider.find_analog(search_conn, rt, height, length)

        if not art and search_conn == "VK-правое" and rt in ('20', '21', '22'):
            for alt_conn in ["VK-левое", "K-боковое"]:
                art, name = self.app.data_provider.find_analog(alt_conn, rt, height, length)
                if art:
                    break

        if not art:
            messagebox.showwarning(
                "Радиатор не найден",
                f"LaggarTT {conn} {rt} {height}×{length} не найден.\nВыберите другой размер."
            )
            return

        # Обновляем таблицу соответствия
        if self._tree_reference and self._current_item:
            values = list(self._tree_reference.item(self._current_item, "values"))
            if len(values) >= 5:
                values[2] = name
                values[3] = art
                values[4] = "Ручной ввод"
                self._tree_reference.item(self._current_item, values=values)

        logger.info("=" * 60)
        logger.info(f"ОБУЧЕНИЕ: оригинальное название = '{self._original_name[:80]}'")
        logger.info(f"  Пользователь выбрал: conn={saved_conn}, type={rt}, h={height}, l={length}")

        # ================================================================
        # СОЗДАНИЕ ШАБЛОНА
        # ================================================================
        try:
            from nextt.patterns.template_manager import TemplateManager
            template_manager = TemplateManager()
            template = template_manager.analyze_and_create_template(
                self._original_name,
                saved_conn,
                rt,
                height,
                length
            )
            if template:
                template_manager.save()
                logger.info(f"  Шаблон создан и сохранён: {template.name}")
                
                # ================================================================
                # ВАЖНО: перезагружаем шаблоны в SpecNormalizer
                # ================================================================
                if hasattr(self.app, 'normalizer'):
                    self.app.normalizer.reload_templates()
                    logger.info("  Шаблоны перезагружены в SpecNormalizer")
                # ================================================================
            else:
                logger.warning("  Не удалось создать шаблон")
        except Exception as e:
            logger.error(f"  Ошибка создания шаблона: {e}")

        logger.info("=" * 60)

        # Переподбор всех строк таблицы
        if self._apply_patterns_callback and self._tree_reference:
            try:
                updated_count = self._apply_patterns_callback(self._tree_reference)
                logger.info(f"Переподбор: обновлено {updated_count} строк")
            except Exception as e:
                logger.error(f"Ошибка переподбора: {e}")

        if self._on_close_callback:
            try:
                self._on_close_callback()
                logger.info("Вызван callback сохранения состояния")
            except Exception as e:
                logger.error(f"Ошибка в callback сохранения: {e}")

        # ================================================================
        # ВОССТАНОВЛЕНИЕ ФОКУСА
        # ================================================================
        # Сохраняем ссылку на родительское окно (CorrespondenceDialog)
        parent = self._tree_reference.winfo_toplevel() if self._tree_reference else None
        
        # Закрываем текущее окно выбора аналога
        if self._dialog:
            self._dialog.destroy()
            self._dialog = None
        
        # Восстанавливаем фокус на родительском окне
        if parent and parent.winfo_exists():
            parent.lift()
            parent.focus_force()
            # Если у родителя есть дерево, возвращаем фокус на него
            if self._tree_reference and self._tree_reference.winfo_exists():
                self._tree_reference.focus_set()
        
        logger.info("Фокус восстановлен на окне таблицы соответствия")
        
    def _update_preview(self) -> None:
        """Обновляет предпросмотр аналога."""
        conn = self._selected_connection.get()
        rt = self._selected_type.get()
        h = self._preview_height
        l = self._preview_length

        default_font = self.font_manager.get_default_font()

        if not all([conn, rt, h, l]):
            self._analog_name_var.set("Выберите параметры")
            self._article_var.set("—")
            self._power_var.set("—")
            self._weight_var.set("—")
            self._volume_var.set("—")
            return

        search_conn = conn
        if conn == "VK-левое" and rt in ('20', '21', '22'):
            search_conn = "VK-правое"

        art, name = self.app.data_provider.find_analog(search_conn, rt, h, l)

        if art:
            self._analog_name_var.set(f"LaggarTT {conn} {rt} {h}×{l}")
            self._article_var.set(art)

            found = self.app.data_provider.find_by_article(art)
            if found is not None:
                power = found.get('Мощность, Вт', '')
                weight = found.get('Вес, кг', '')
                volume = found.get('Объем, м3', '')

                self._power_var.set(f"{int(power)} Вт" if power else "—")
                self._weight_var.set(f"{float(weight):.1f} кг" if weight else "—")
                self._volume_var.set(f"{float(volume):.3f} м³" if volume else "—")
            else:
                self._power_var.set("—")
                self._weight_var.set("—")
                self._volume_var.set("—")
        else:
            self._analog_name_var.set(f"LaggarTT {conn} {rt} {h}×{l}")
            self._article_var.set("—")
            self._power_var.set("Не найден")
            self._weight_var.set("—")
            self._volume_var.set("—")

    def _close(self) -> None:
        """Закрывает диалог."""
        # Вызываем callback для сохранения состояния (если есть)
        if self._on_close_callback:
            try:
                self._on_close_callback()
                logger.info("Вызван callback сохранения состояния (при закрытии)")
            except Exception as e:
                logger.error(f"Ошибка в callback сохранения: {e}")
        
        if self._dialog:
            self._dialog.destroy()
            self._dialog = None