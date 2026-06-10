"""
Диалог выбора страниц PDF с миниатюрами.
Полноценная версия — как в оригинальном PdfPageSelector.
С поддержкой масштабирования шрифтов.
"""

import tkinter as tk
from tkinter import ttk
import os
import queue
import threading
from typing import Optional, List, Set, Dict, Any

from nextt.logger import get_logger

logger = get_logger(__name__)

try:
    import fitz  # PyMuPDF
    from PIL import Image, ImageTk
    from io import BytesIO
    HAS_PDF_LIBS = True
except ImportError:
    HAS_PDF_LIBS = False
    logger.warning("PyMuPDF или Pillow не установлены. Миниатюры недоступны.")


class PdfPageSelector:
    """
    Окно для выбора страниц PDF с миниатюрами и ручным вводом диапазонов.
    Полный аналог оригинального PdfPageSelector из next1.71.py.
    С поддержкой масштабирования шрифтов.
    """

    def __init__(self, parent, total_pages: int, pdf_path: str,
                 title: str = "Выбор страниц PDF", initial_selection: List[int] = None,
                 font_manager=None):
        self.parent = parent
        self.total_pages = total_pages
        self.pdf_path = pdf_path
        self.title = title
        self.initial_selection = initial_selection or []
        self.font_manager = font_manager

        # Результат
        self.result = {"pages": None, "confirmed": False}

        # Выбранные страницы
        self.selected_pages: Set[int] = set(self.initial_selection)

        # Миниатюры
        self.thumbnail_images: Dict[int, Any] = {}
        self.thumbnail_widgets: Dict[int, Dict[str, Any]] = {}

        # Окно
        self.dialog = None
        self.thumbnail_progress_label = None

        # Элементы интерфейса
        self.range_entry = None
        self.range_var = None
        self.stats_label = None
        self.canvas = None
        self.thumbnails_frame = None
        
    def show(self) -> Optional[List[int]]:
        """Показывает диалог и возвращает список выбранных страниц."""
        self._create_dialog()
        self._initialize_dialog()
        self.dialog.wait_window()

        if self.result["confirmed"]:
            logger.info(f"Выбрано {len(self.result['pages'])} страниц")
            return self.result["pages"]
        return None

    def _create_dialog(self):
        """Создаёт диалоговое окно."""
        self.dialog = tk.Toplevel(self.parent)
        
        # Настройка окна (кнопки свернуть/развернуть/закрыть)
        from nextt.utils.window_manager import setup_dialog_window
        setup_dialog_window(self.dialog, f"{self.title} (всего: {self.total_pages})")

        # Полноэкранный режим с учётом панели задач
        from nextt.utils.window_manager import get_safe_geometry
        self.dialog.geometry(get_safe_geometry(self.dialog))
        self.dialog.minsize(1000, 600)

    def _initialize_dialog(self):
        """Инициализирует диалог с загрузкой миниатюр."""
        self._create_widgets()

        # Скрываем маленький счётчик в углу
        if self.thumbnail_progress_label:
            self.thumbnail_progress_label.pack_forget()

        # Создаём крупный счётчик по центру
        large_font = ("Segoe UI", 16, "bold")
        if self.font_manager:
            large_font = self.font_manager.get_title_font()
        
        self._loading_label = tk.Label(
            self.dialog,
            text="Загрузка миниатюр...",
            font=large_font,
            bg="#f5f5f5",
            fg="#2c3e50"
        )
        self._loading_label.place(relx=0.5, rely=0.5, anchor="center")

        self.dialog.update()

        # Загружаем миниатюры
        self._load_thumbnails_async()

    def _get_default_font(self):
        """Возвращает масштабированный шрифт по умолчанию."""
        if self.font_manager:
            return self.font_manager.get_default_font()
        return ("Segoe UI", 9)

    def _get_heading_font(self):
        """Возвращает масштабированный шрифт для заголовков."""
        if self.font_manager:
            return self.font_manager.get_heading_font()
        return ("Segoe UI", 9, "bold")

    def _get_bold_font(self):
        """Возвращает масштабированный жирный шрифт."""
        if self.font_manager:
            return self.font_manager.get_bold_font()
        return ("Segoe UI", 9, "bold")

    def _create_widgets(self):
        """Создаёт все виджеты окна."""
        default_font = self._get_default_font()
        heading_font = self._get_heading_font()
        bold_font = self._get_bold_font()

        main_frame = ttk.Frame(self.dialog)
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # Верхняя часть — заголовок и инструкция
        top_frame = ttk.Frame(main_frame)
        top_frame.pack(fill="x", pady=(0, 15))

        ttk.Label(top_frame, text=f"PDF содержит {self.total_pages} страниц",
                  font=heading_font).pack(anchor="w", pady=(0, 8))

        instruction_text = (
            "Выберите страницы с таблицами (клик по миниатюре или ввод диапазона). "
            "Чертежи, схемы и приложения пропускайте."
        )
        ttk.Label(top_frame, text=instruction_text,
                  wraplength=1400, font=default_font).pack(anchor="w", pady=(0, 15))

        # Фрейм для ручного ввода диапазона
        input_frame = ttk.Frame(main_frame)
        input_frame.pack(fill="x", pady=(0, 15))

        ttk.Label(input_frame, text="Введите диапазон страниц:",
                  font=default_font).pack(side="left", padx=(0, 10))

        self.range_var = tk.StringVar()
        self.range_entry = ttk.Entry(input_frame, textvariable=self.range_var,
                                     width=50, font=default_font)
        self.range_entry.pack(side="left", padx=(0, 10))
        
        # Enter — сразу применить
        self.range_entry.bind("<Return>", lambda e: self._apply_range_from_entry())
        
        # ========== ИСПРАВЛЕНИЕ: Убираем задержку 1 секунду ==========
        # Применяем выбор сразу при изменении текста (без таймера)
        self.range_var.trace_add("write", lambda *args: self._apply_range_from_entry())

        ttk.Label(input_frame, text="Формат: 1-5, 7, 10-15",
                  font=default_font, foreground="gray").pack(side="left", padx=(20, 0))

        # Средняя часть — фрейм с миниатюрами
        preview_container = ttk.Frame(main_frame)
        preview_container.pack(fill="both", expand=True, pady=(0, 15))

        # Заголовок для секции миниатюр
        preview_header_frame = ttk.Frame(preview_container)
        preview_header_frame.pack(fill="x", pady=(0, 10))

        ttk.Label(preview_header_frame, text="Миниатюры страниц",
                  font=bold_font).pack(side="left")

        self.thumbnail_progress_label = ttk.Label(preview_header_frame, text="",
                                                  font=default_font)
        self.thumbnail_progress_label.pack(side="right", padx=(0, 10))

        # Фрейм для миниатюр с бордюром
        preview_frame = ttk.Frame(preview_container, relief="solid", borderwidth=1)
        preview_frame.pack(fill="both", expand=True, padx=0, pady=0)

        # Canvas для миниатюр с прокруткой
        canvas_frame = ttk.Frame(preview_frame)
        canvas_frame.pack(fill="both", expand=True, padx=10, pady=10)

        self.canvas = tk.Canvas(canvas_frame, bg="#f0f0f0", highlightthickness=0)
        vsb = ttk.Scrollbar(canvas_frame, orient="vertical", command=self.canvas.yview)
        hsb = ttk.Scrollbar(canvas_frame, orient="horizontal", command=self.canvas.xview)

        self.canvas.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.canvas.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        canvas_frame.grid_rowconfigure(0, weight=1)
        canvas_frame.grid_columnconfigure(0, weight=1)

        self.thumbnails_frame = ttk.Frame(self.canvas)
        self.canvas.create_window((0, 0), window=self.thumbnails_frame, anchor="nw")

        # Настройка скролла колёсиком мыши
        self._setup_mousewheel_scroll()

        # Нижняя часть — статистика и кнопки
        bottom_frame = ttk.Frame(main_frame)
        bottom_frame.pack(side="bottom", fill="x", pady=(0, 0))

        ttk.Separator(bottom_frame, orient="horizontal").pack(fill="x", pady=(0, 15))

        stats_frame = ttk.Frame(bottom_frame)
        stats_frame.pack(fill="x", pady=(0, 15))

        self.stats_label = ttk.Label(stats_frame,
                                     text=f"Выбрано страниц: 0 из {self.total_pages}",
                                     font=bold_font)
        self.stats_label.pack()

        # Кнопки действий
        button_frame = ttk.Frame(bottom_frame)
        button_frame.pack(fill="x", pady=(0, 5))

        ttk.Button(button_frame, text="Выбрать все",
                   command=self._select_all, width=18).pack(side="left", padx=(40, 10), expand=True)
        ttk.Button(button_frame, text="Очистить все",
                   command=self._clear_all, width=18).pack(side="left", padx=10, expand=True)
        ttk.Button(button_frame, text="Обработать выбранные",
                   command=self._confirm_selection, width=22).pack(side="left", padx=10, expand=True)
        ttk.Button(button_frame, text="Отмена",
                   command=self._cancel, width=18).pack(side="left", padx=(10, 40), expand=True)

    def _setup_mousewheel_scroll(self) -> None:
        """Настраивает прокрутку колёсиком мыши для Canvas с миниатюрами."""
        def on_mousewheel(event):
            if self.canvas and self.canvas.winfo_exists():
                # На Windows event.delta — положительное при прокрутке вверх
                # Делим на 120 чтобы получить количество «шагов»
                self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        
        # Привязываем событие ко всем виджетам
        self.canvas.bind("<MouseWheel>", on_mousewheel)
        # Также привязываем к самому dialog для надёжности
        self.dialog.bind("<MouseWheel>", on_mousewheel)

    def _load_thumbnails_async(self):
        """Загружает миниатюры в отдельном потоке с обновлением прогресса по центру."""
        result_queue = queue.Queue()

        def worker():
            try:
                success = self._load_thumbnails_with_progress(result_queue)
                result_queue.put(("success", success))
            except Exception as e:
                result_queue.put(("error", str(e)))

        def check_result():
            # ========== ПРОВЕРЯЕМ, СУЩЕСТВУЕТ ЛИ ЕЩЁ ДИАЛОГ ==========
            if not self.dialog or not self.dialog.winfo_exists():
                return
            
            try:
                status, data = result_queue.get_nowait()
                # ========== ПРОВЕРЯЕМ СУЩЕСТВОВАНИЕ ДИАЛОГА ПЕРЕД УДАЛЕНИЕМ ==========
                if self.dialog and self.dialog.winfo_exists():
                    if hasattr(self, '_loading_label') and self._loading_label:
                        try:
                            self._loading_label.destroy()
                        except (tk.TclError, RuntimeError):
                            pass
                        self._loading_label = None

                if status == "success":
                    logger.info(f"Загружено {len(self.thumbnail_images)} миниатюр")
                    self._create_thumbnail_widgets()
                    if self.dialog and self.dialog.winfo_exists():
                        self.dialog.after(100, lambda: self.canvas.config(
                            scrollregion=self.canvas.bbox("all")))
                        self.dialog.after(200, lambda: self.dialog.focus_set())
                else:
                    logger.error(f"Ошибка загрузки миниатюр: {data}")
                    for page_num in range(1, self.total_pages + 1):
                        self.thumbnail_images[page_num] = None
                    self._create_thumbnail_widgets()

            except queue.Empty:
                if self.dialog and self.dialog.winfo_exists():
                    self.dialog.after(100, check_result)

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        if self.dialog and self.dialog.winfo_exists():
            self.dialog.after(100, check_result)

    def _load_thumbnails_with_progress(self, progress_queue) -> bool:
        """
        Загружает миниатюры страниц PDF и обновляет прогресс через queue.
        """
        if not HAS_PDF_LIBS:
            return False

        try:
            doc = fitz.open(self.pdf_path)

            for page_num in range(1, self.total_pages + 1):
                try:
                    # Обновляем прогресс в основном потоке
                    self.dialog.after(0, lambda p=page_num, t=self.total_pages: self._update_loading_progress(p, t))

                    page = doc[page_num - 1]
                    pix = page.get_pixmap(matrix=fitz.Matrix(0.25, 0.25))
                    img_data = pix.tobytes("ppm")
                    img = Image.open(BytesIO(img_data))
                    img.thumbnail((140, 180), Image.Resampling.LANCZOS)
                    photo = ImageTk.PhotoImage(img)
                    self.thumbnail_images[page_num] = photo

                except Exception as e:
                    logger.debug(f"Ошибка миниатюры стр.{page_num}: {e}")
                    self.thumbnail_images[page_num] = None

            doc.close()
            return True

        except Exception as e:
            logger.error(f"Ошибка загрузки PDF: {e}")
            return False

    def _update_loading_progress(self, current: int, total: int) -> None:
        """
        Обновляет текст на центральной надписи с прогрессом загрузки.
        """
        # ========== ПРОВЕРЯЕМ, СУЩЕСТВУЕТ ЛИ ЕЩЁ ДИАЛОГ И ВИДЖЕТ ==========
        if not self.dialog or not self.dialog.winfo_exists():
            return
        if not hasattr(self, '_loading_label') or not self._loading_label:
            return
        try:
            if self._loading_label and self._loading_label.winfo_exists():
                self._loading_label.config(
                    text=f"Загрузка миниатюр...\n{current} из {total} страниц"
                )
                self.dialog.update()
        except (tk.TclError, RuntimeError, AttributeError):
            # Виджет уже уничтожен, игнорируем
            pass

    def _load_thumbnails(self) -> bool:
        """Загружает миниатюры страниц PDF."""
        if not HAS_PDF_LIBS:
            return False

        try:
            doc = fitz.open(self.pdf_path)

            for page_num in range(1, self.total_pages + 1):
                try:
                    # Обновляем прогресс
                    self.thumbnail_progress_label.config(
                        text=f"Загружено: {page_num}/{self.total_pages} страниц"
                    )

                    page = doc[page_num - 1]
                    pix = page.get_pixmap(matrix=fitz.Matrix(0.25, 0.25))
                    img_data = pix.tobytes("ppm")
                    img = Image.open(BytesIO(img_data))
                    img.thumbnail((140, 180), Image.Resampling.LANCZOS)
                    photo = ImageTk.PhotoImage(img)
                    self.thumbnail_images[page_num] = photo

                except Exception as e:
                    logger.debug(f"Ошибка миниатюры стр.{page_num}: {e}")
                    self.thumbnail_images[page_num] = None

            doc.close()
            self.thumbnail_progress_label.config(text="")
            return True

        except Exception as e:
            logger.error(f"Ошибка загрузки PDF: {e}")
            return False

    def _create_thumbnail_widgets(self):
        """Создаёт все виджеты миниатюр."""
        cols = 10
        default_font = self._get_default_font()
        bold_font = self._get_bold_font()

        for i, page_num in enumerate(range(1, self.total_pages + 1)):
            thumb_data = self._create_single_thumbnail(page_num, default_font, bold_font)
            row = i // cols
            col = i % cols
            thumb_data["frame"].grid(row=row, column=col, padx=10, pady=10, sticky="nw")
            self.thumbnail_widgets[page_num] = thumb_data

        self.thumbnails_frame.update_idletasks()
        self.canvas.config(scrollregion=self.canvas.bbox("all"))
        self._update_stats()

    def _create_single_thumbnail(self, page_num, default_font, bold_font):
        """Создаёт один виджет миниатюры."""
        is_selected = page_num in self.selected_pages

        thumb_frame = tk.Frame(self.thumbnails_frame, relief="solid", borderwidth=2,
                               bg="white")

        # Номер страницы
        page_label = tk.Label(thumb_frame, text=f"Страница {page_num}",
                              font=bold_font, bg="white")
        page_label.pack(pady=(8, 0))

        # Область миниатюры
        thumb_canvas = tk.Canvas(thumb_frame, width=140, height=180,
                                 bg="white", highlightthickness=0)
        thumb_canvas.pack(pady=8)

        if page_num in self.thumbnail_images and self.thumbnail_images[page_num] is not None:
            photo = self.thumbnail_images[page_num]
            thumb_canvas.create_image(70, 90, image=photo)
            thumb_canvas.image = photo
        else:
            # Заглушка
            if page_num % 3 == 0:
                bg_color = "#ffe6e6"
                text = "📐 Чертеж"
            elif page_num % 4 == 0:
                bg_color = "#fff0e6"
                text = "📋 Приложение"
            else:
                bg_color = "#e6ffe6"
                text = "📊 Таблица"

            thumb_canvas.config(bg=bg_color)
            thumb_canvas.create_text(70, 60, text=text,
                                     font=bold_font, fill="#333333")
            thumb_canvas.create_text(70, 90, text=f"Страница {page_num}",
                                     font=default_font, fill="#666666")

        # Индикатор выбора
        selection_rect = thumb_canvas.create_rectangle(5, 5, 135, 175,
                                                      outline="#cccccc", width=1)
        checkmark = thumb_canvas.create_text(130, 20, text="",
                                           font=bold_font, fill="#0066cc")

        # Статус
        status_text = "⏸ Пропустить" if not is_selected else "✅ Выбрана"
        status_label = tk.Label(thumb_frame, text=status_text,
                                font=default_font, bg="white")
        status_label.pack(pady=(0, 8))

        # Обработчик клика
        def on_click(event, p=page_num):
            self._toggle_page_selection(p)

        thumb_frame.bind("<Button-1>", on_click)
        thumb_canvas.bind("<Button-1>", on_click)
        page_label.bind("<Button-1>", on_click)
        status_label.bind("<Button-1>", on_click)

        # Визуальное состояние
        self._update_thumbnail_visual(thumb_canvas, selection_rect, checkmark, status_label, is_selected)

        return {
            "frame": thumb_frame,
            "canvas": thumb_canvas,
            "selection_rect": selection_rect,
            "checkmark": checkmark,
            "status_label": status_label,
            "page_num": page_num,
        }

    def _update_thumbnail_visual(self, canvas, selection_rect, checkmark, status_label, is_selected):
        """Обновляет визуальное состояние миниатюры."""
        if is_selected:
            canvas.itemconfig(selection_rect, outline="#0066cc", width=3)
            canvas.itemconfig(checkmark, text="✓")
            status_label.config(text="✅ Выбрана", fg="#0066cc")
        else:
            canvas.itemconfig(selection_rect, outline="#cccccc", width=1)
            canvas.itemconfig(checkmark, text="")
            status_label.config(text="⏸ Пропустить", fg="#666666")

    def _toggle_page_selection(self, page_num):
        """Переключает выбор страницы."""
        if page_num in self.selected_pages:
            self.selected_pages.discard(page_num)
        else:
            self.selected_pages.add(page_num)

        if page_num in self.thumbnail_widgets:
            w = self.thumbnail_widgets[page_num]
            self._update_thumbnail_visual(
                w["canvas"], w["selection_rect"],
                w["checkmark"], w["status_label"],
                page_num in self.selected_pages
            )

        self._update_stats()
        self._update_range_entry()

    def _update_stats(self):
        """Обновляет статистику."""
        if self.stats_label:
            self.stats_label.config(
                text=f"Выбрано страниц: {len(self.selected_pages)} из {self.total_pages}"
            )

    def _update_range_entry(self):
        """Обновляет поле ввода."""
        if not self.range_entry:
            return
        if not self.selected_pages:
            self.range_entry.delete(0, tk.END)
            return

        sorted_pages = sorted(self.selected_pages)
        ranges = []
        start = sorted_pages[0]
        end = start

        for p in sorted_pages[1:]:
            if p == end + 1:
                end = p
            else:
                ranges.append(str(start) if start == end else f"{start}-{end}")
                start = p
                end = p
        ranges.append(str(start) if start == end else f"{start}-{end}")

        self.range_entry.delete(0, tk.END)
        self.range_entry.insert(0, ", ".join(ranges))

    def _apply_range_from_entry(self):
        """Применяет диапазон из поля ввода."""
        if not self.range_entry:
            return

        range_str = self.range_entry.get().strip()
        if not range_str:
            self._clear_all()
            return

        pages = self._parse_range(range_str)
        if pages is None:
            return

        self.selected_pages = set(pages)
        for p, w in self.thumbnail_widgets.items():
            self._update_thumbnail_visual(
                w["canvas"], w["selection_rect"],
                w["checkmark"], w["status_label"],
                p in self.selected_pages
            )
        self._update_stats()

    def _parse_range(self, range_str: str) -> Optional[List[int]]:
        """
        Парсит строку диапазона страниц.
        Поддерживает:
        - Отдельные числа: 5, 7, 12
        - Диапазоны через тире: 10-18 (от 10 до 18)
        - Ведущее тире: -18 (от последнего числа до 18)
        - Замыкающее тире: 50- (от 50 до следующего числа)
        - Смешанные форматы с запятыми и пробелами: "6,10,50-,60"
        - Ведущее тире в начале: "-10" (от первой страницы до 10)
        """
        if not range_str or not range_str.strip():
            return None
        
        pages = set()
        numbers_buffer = []  # Временное хранение чисел для обработки диапазонов с замыкающим тире
        i = 0
        length = len(range_str)
        
        while i < length:
            ch = range_str[i]
            
            if ch.isdigit():
                # Собираем число
                start = i
                while i < length and range_str[i].isdigit():
                    i += 1
                num = int(range_str[start:i])
                numbers_buffer.append(num)
            
            elif ch == '-':
                i += 1
                # Пропускаем пробелы после тире
                while i < length and range_str[i] == ' ':
                    i += 1
                
                # Смотрим, есть ли число после тире
                if i < length and range_str[i].isdigit():
                    # Обычный диапазон: число-число (например, 10-18)
                    start = i
                    while i < length and range_str[i].isdigit():
                        i += 1
                    end_num = int(range_str[start:i])
                    
                    if numbers_buffer:
                        start_num = numbers_buffer[-1]
                        if start_num <= end_num:
                            for p in range(start_num, end_num + 1):
                                pages.add(p)
                        # Убираем последнее число из буфера, так как оно уже включено в диапазон
                        if numbers_buffer:
                            numbers_buffer.pop()
                        numbers_buffer.append(end_num)
                    else:
                        # Ведущее тире: -10 (от первой страницы до 10)
                        if end_num >= 1:
                            for p in range(1, end_num + 1):
                                pages.add(p)
                            numbers_buffer.append(end_num)
                
                else:
                    # Замыкающее тире: 50- (от последнего числа до следующего)
                    # Сохраняем маркер, что нужно будет закрыть диапазон при следующем числе
                    numbers_buffer.append("PENDING_RANGE")
            
            elif ch == ',':
                i += 1
                # Запятая — просто разделитель, ничего не делаем
            
            else:
                # Любой другой символ (пробел и т.д.) — пропускаем
                i += 1
        
        # Обрабатываем оставшиеся числа в буфере
        temp_buffer = []
        pending_start = None
        
        for item in numbers_buffer:
            if item == "PENDING_RANGE":
                pending_start = temp_buffer[-1] if temp_buffer else None
            else:
                if pending_start is not None:
                    # Закрываем висящий диапазон: от pending_start до текущего числа
                    if pending_start <= item:
                        for p in range(pending_start, item + 1):
                            pages.add(p)
                    pending_start = None
                else:
                    temp_buffer.append(item)
        
        # Добавляем все обычные числа
        for num in temp_buffer:
            if 1 <= num <= self.total_pages:
                pages.add(num)
        
        # Проверяем, что все страницы в допустимом диапазоне
        for p in pages:
            if p < 1 or p > self.total_pages:
                return None
        
        return sorted(pages)

    def _select_all(self):
        """Выбрать все страницы."""
        self.selected_pages = set(range(1, self.total_pages + 1))
        for p, w in self.thumbnail_widgets.items():
            self._update_thumbnail_visual(
                w["canvas"], w["selection_rect"],
                w["checkmark"], w["status_label"], True
            )
        self._update_stats()
        self._update_range_entry()

    def _clear_all(self):
        """Очистить все выборы."""
        self.selected_pages.clear()
        for p, w in self.thumbnail_widgets.items():
            self._update_thumbnail_visual(
                w["canvas"], w["selection_rect"],
                w["checkmark"], w["status_label"], False
            )
        self._update_stats()
        self._update_range_entry()

    def _confirm_selection(self):
        """Обработать выбранные страницы."""
        if not self.selected_pages:
            from tkinter import messagebox
            messagebox.showwarning(
                "Предупреждение",
                "Вы не выбрали ни одной страницы для обработки.\n"
                "Нажмите на миниатюры таблиц, введите диапазон или нажмите 'Выбрать все'."
            )
            return

        self.result["pages"] = sorted(self.selected_pages)
        self.result["confirmed"] = True
        self.dialog.destroy()

    def _cancel(self):
        """Отмена выбора."""
        self.result["confirmed"] = False
        self.dialog.destroy()