"""
Окно «Методика пересчёта мощностей радиаторов LaggarTT».

Открывается из меню «Информация» в главном окне.
Содержит подробное описание методики пересчёта мощности
по ГОСТ 31311-2022.

Поддерживает масштабирование шрифтов: подписан на событие
FONT_SCALE_CHANGED и при его получении пересоздаёт содержимое.
"""

import os
from typing import Optional

import tkinter as tk
from tkinter import ttk

from nextt.logger import get_logger
from nextt.events import bus, Events
from nextt.utils.window_manager import get_safe_geometry, setup_dialog_window

logger = get_logger(__name__)


# =========================================================================
# Цвета
# =========================================================================
COLOR_BG = "#f5f5f5"
COLOR_TITLE = "#263168"          # тёмно-синий для заголовков
COLOR_SUBTITLE = "#666666"       # серый для подзаголовков
COLOR_TEXT = "#2c3e50"           # основной текст
COLOR_DIVIDER_MAIN = "#263168"   # главный разделитель под заголовком окна
COLOR_DIVIDER_SECTION = "#cccccc"  # разделитель под заголовком раздела
COLOR_FORMULA = "#1a2456"        # формулы

# Моноширинный шрифт (для формул)
MONO_FAMILY = "Consolas"
MONO_FALLBACK = "Courier New"


class MethodologyDialog:
    """Окно с методикой пересчёта мощностей."""

    def __init__(self, app):
        self.app = app
        self.font_manager = app.font_manager

        self._dialog: Optional[tk.Toplevel] = None
        self._canvas: Optional[tk.Canvas] = None
        self._content_frame: Optional[ttk.Frame] = None
        self._scrollbar: Optional[ttk.Scrollbar] = None
        self._close_btn: Optional[ttk.Button] = None

        # Вычисляемая ширина для переноса текста
        self._wraplength: int = 1200

    # ==================================================================
    # Публичный метод
    # ==================================================================

    def show(self) -> None:
        """Открывает окно."""
        if self._dialog and self._dialog.winfo_exists():
            self._dialog.lift()
            self._dialog.focus_force()
            return

        self._create_dialog()
        self._build_content()

        # Подписка на изменение масштаба шрифтов
        bus.subscribe(Events.FONT_SCALE_CHANGED, self._on_font_scale_changed)

    # ==================================================================
    # Создание окна
    # ==================================================================

    def _create_dialog(self) -> None:
        """Создаёт окно с прокруткой."""
        self._dialog = tk.Toplevel(self.app.root)

        setup_dialog_window(self._dialog, "Методика пересчёта мощностей радиаторов LaggarTT")

        # Иконка
        try:
            from nextt.config import get_resource_path
            icon_path = get_resource_path("icon.ico")
            if icon_path and os.path.exists(icon_path):
                self._dialog.iconbitmap(icon_path)
        except Exception as e:
            logger.debug(f"Не удалось загрузить иконку: {e}")

        # Полноэкранный режим с учётом панели задач
        self._dialog.geometry(get_safe_geometry(self._dialog))
        self._dialog.configure(bg=COLOR_BG)

        # --- Внешний фрейм ---
        outer = tk.Frame(self._dialog, bg=COLOR_BG)
        outer.pack(fill="both", expand=True, padx=15, pady=15)

        # --- Canvas со скроллом ---
        canvas_frame = tk.Frame(outer, bg=COLOR_BG)
        canvas_frame.pack(fill="both", expand=True)

        self._canvas = tk.Canvas(
            canvas_frame,
            bg=COLOR_BG,
            highlightthickness=0,
            bd=0,
        )
        self._scrollbar = ttk.Scrollbar(
            canvas_frame,
            orient="vertical",
            command=self._canvas.yview,
        )
        self._canvas.configure(yscrollcommand=self._scrollbar.set)

        self._canvas.pack(side="left", fill="both", expand=True)
        self._scrollbar.pack(side="right", fill="y")

        # --- Внутренний фрейм для содержимого ---
        self._content_frame = tk.Frame(self._canvas, bg=COLOR_BG)
        self._content_window = self._canvas.create_window(
            (0, 0),
            window=self._content_frame,
            anchor="nw",
        )

        # Обновление scrollregion при изменении размеров содержимого
        self._content_frame.bind(
            "<Configure>",
            lambda e: self._canvas.configure(scrollregion=self._canvas.bbox("all")),
        )

        # Растягивание содержимого по ширине canvas
        self._canvas.bind("<Configure>", self._on_canvas_configure)

        # Прокрутка колёсиком мыши
        self._dialog.bind("<MouseWheel>", self._on_mousewheel)
        self._canvas.bind("<MouseWheel>", self._on_mousewheel)
        self._content_frame.bind("<MouseWheel>", self._on_mousewheel)

        # --- Кнопка «Закрыть» внизу ---
        bottom = tk.Frame(outer, bg="#dedede", relief="solid", borderwidth=1)
        bottom.pack(fill="x", pady=(10, 0))

        inner_bottom = tk.Frame(bottom, bg="#dedede")
        inner_bottom.pack(fill="x", pady=8)

        default_font = self.font_manager.get_default_font()
        self._close_btn = tk.Button(
            inner_bottom,
            text="Закрыть",
            font=default_font,
            bg=COLOR_TITLE, fg="white",
            activebackground="#7E1A2F", activeforeground="white",
            relief="flat", borderwidth=0,
            cursor="hand2",
            padx=32, pady=4,
            command=self._close,
        )
        self._close_btn.pack()

        # Обработка закрытия окна
        self._dialog.protocol("WM_DELETE_WINDOW", self._close)

    def _on_canvas_configure(self, event) -> None:
        """Растягивает содержимое и пересчитывает wraplength."""
        if not self._canvas or not self._content_frame:
            return
        self._canvas.itemconfigure(self._content_window, width=event.width)

        new_wraplength = max(400, event.width - 100)
        if new_wraplength != self._wraplength:
            self._wraplength = new_wraplength
            self._update_labels_wraplength()

    def _update_labels_wraplength(self) -> None:
        """Обновляет wraplength у всех текстовых меток."""
        if not self._content_frame:
            return
        self._apply_wraplength_recursive(self._content_frame)

    def _apply_wraplength_recursive(self, widget) -> None:
        """Рекурсивно применяет wraplength к ttk.Label и tk.Label."""
        try:
            if isinstance(widget, (tk.Label, ttk.Label)):
                try:
                    current = widget.cget("wraplength")
                    if current and int(current) > 0:
                        widget.configure(wraplength=self._wraplength)
                except (tk.TclError, ValueError):
                    pass
        except tk.TclError:
            pass

        try:
            for child in widget.winfo_children():
                self._apply_wraplength_recursive(child)
        except tk.TclError:
            pass

    def _on_mousewheel(self, event) -> None:
        """Прокрутка колёсиком мыши."""
        if self._canvas:
            self._canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    # ==================================================================
    # Масштабирование шрифтов
    # ==================================================================

    def _on_font_scale_changed(self, scale: float) -> None:
        """Пересоздаёт содержимое окна при изменении масштаба шрифтов."""
        if not self._dialog or not self._dialog.winfo_exists():
            return

        logger.debug(f"MethodologyDialog: пересоздаём содержимое (scale={scale:.2f})")

        try:
            scroll_pos = self._canvas.yview()[0] if self._canvas else 0.0
        except (tk.TclError, AttributeError):
            scroll_pos = 0.0

        self._rebuild_content()

        try:
            if self._canvas:
                self._canvas.yview_moveto(scroll_pos)
        except (tk.TclError, AttributeError):
            pass

    def _rebuild_content(self) -> None:
        """Очищает и заново создаёт содержимое."""
        if not self._content_frame:
            return

        try:
            for widget in self._content_frame.winfo_children():
                widget.destroy()
        except tk.TclError:
            pass

        self._build_content()

        try:
            self._content_frame.update_idletasks()
            if self._canvas:
                self._canvas.configure(scrollregion=self._canvas.bbox("all"))
        except tk.TclError:
            pass

    # ==================================================================
    # Стили шрифтов
    # ==================================================================

    def _font_default(self):
        return self.font_manager.get_default_font()

    def _font_bold(self, base_size: int = 9):
        return self.font_manager.get_bold_font(base_size)

    def _font_title(self):
        return self.font_manager.get_title_font()   # 12 pt bold

    def _font_formula(self, base_size: int = 10):
        """Моноширинный шрифт для формул с учётом масштаба."""
        try:
            scale = self.font_manager.scale
        except Exception:
            scale = 1.0
        size = max(8, int(base_size * scale))
        return (MONO_FAMILY, size)

    # ==================================================================
    # Построение содержимого
    # ==================================================================

    def _build_content(self) -> None:
        """Строит все блоки методики."""
        if not self._content_frame:
            return

        # --- Заголовок страницы ---
        self._build_page_header()

        # --- Разделы ---
        self._section_1()
        self._section_2()
        self._section_3()
        self._section_4()
        self._section_5()
        self._section_6()
        self._section_7()
        self._section_8()
        self._section_9()
        self._section_10()

    def _build_page_header(self) -> None:
        """Заголовок страницы с подзаголовком и главным разделителем."""
        wrap = self._wraplength

        title = tk.Label(
            self._content_frame,
            text="ПЕРЕСЧЁТ МОЩНОСТЕЙ РАДИАТОРОВ LAGGARTT",
            font=self._font_title(),
            fg=COLOR_TITLE,
            bg=COLOR_BG,
            anchor="w",
            justify="left",
        )
        title.pack(anchor="w", pady=(0, 2))

        subtitle = tk.Label(
            self._content_frame,
            text="Согласно ГОСТ 31311-2022",
            font=self._font_default(),
            fg=COLOR_SUBTITLE,
            bg=COLOR_BG,
            anchor="w",
        )
        subtitle.pack(anchor="w", pady=(0, 8))

        # Главный разделитель
        sep = tk.Frame(self._content_frame, height=2, bg=COLOR_DIVIDER_MAIN)
        sep.pack(fill="x", pady=(0, 28))

    def _section_header(self, number: int, text: str) -> None:
        """Заголовок раздела + тонкий разделитель под ним."""
        title = tk.Label(
            self._content_frame,
            text=f"{number}. {text}",
            font=self._font_bold(10),      # 10 pt bold
            fg=COLOR_TITLE,
            bg=COLOR_BG,
            anchor="w",
        )
        title.pack(anchor="w", pady=(0, 6))

        sep = tk.Frame(self._content_frame, height=1, bg=COLOR_DIVIDER_SECTION)
        sep.pack(fill="x", pady=(0, 14))

    def _paragraph(self, text: str) -> None:
        """Обычный параграф."""
        if not text:
            tk.Frame(self._content_frame, height=6, bg=COLOR_BG).pack(fill="x")
            return
        lbl = tk.Label(
            self._content_frame,
            text=text,
            font=self._font_default(),
            fg=COLOR_TEXT,
            bg=COLOR_BG,
            anchor="w",
            justify="left",
            wraplength=self._wraplength,
        )
        lbl.pack(anchor="w", pady=3)

    def _bullet_list(self, items: list) -> None:
        """Список с маркерами."""
        for item in items:
            row = tk.Frame(self._content_frame, bg=COLOR_BG)
            row.pack(fill="x", anchor="w", padx=(20, 0), pady=1)

            tk.Label(
                row,
                text="•",
                font=self._font_bold(10),
                fg=COLOR_TITLE,
                bg=COLOR_BG,
                anchor="nw",
            ).pack(side="left", padx=(0, 8))

            tk.Label(
                row,
                text=item,
                font=self._font_default(),
                fg=COLOR_TEXT,
                bg=COLOR_BG,
                anchor="w",
                justify="left",
                wraplength=max(300, self._wraplength - 40),
            ).pack(side="left", anchor="w")

    def _formula(self, text: str) -> None:
        """Формула — моноширинный шрифт, отступ слева, без фона."""
        lbl = tk.Label(
            self._content_frame,
            text=text,
            font=self._font_formula(10),
            fg=COLOR_FORMULA,
            bg=COLOR_BG,
            anchor="w",
            justify="left",
        )
        lbl.pack(anchor="w", padx=(24, 0), pady=(8, 10))

    def _table(self, columns: list, rows: list, column_widths: list) -> None:
        """Таблица Treeview с рамкой."""
        wrapper = tk.Frame(
            self._content_frame,
            bg=COLOR_BG,
            highlightbackground="#c8c8c8",
            highlightthickness=1,
            bd=0,
        )
        wrapper.pack(anchor="center", pady=(6, 14))

        style = ttk.Style()
        style.configure(
            "Methodology.Treeview",
            font=self._font_default(),
            rowheight=max(22, int(26 * self.font_manager.scale)),
            background="#ffffff",
            fieldbackground="#ffffff",
            borderwidth=0,
        )
        style.configure(
            "Methodology.Treeview.Heading",
            font=self._font_bold(9),
        )

        tree = ttk.Treeview(
            wrapper,
            columns=columns,
            show="headings",
            height=len(rows),
            selectmode="none",
            style="Methodology.Treeview",
        )

        for i, col in enumerate(columns):
            tree.heading(col, text=col)
            w = column_widths[i] if i < len(column_widths) else 100
            tree.column(col, width=w, anchor="center", minwidth=60)

        tree.tag_configure("even", background="#ffffff")
        tree.tag_configure("odd", background="#f7f7f7")

        for idx, row in enumerate(rows):
            tag = "even" if idx % 2 == 0 else "odd"
            tree.insert("", "end", values=row, tags=(tag,))

        tree.pack(padx=1, pady=1)

    def _spacer(self, height: int = 20) -> None:
        """Отступ между разделами."""
        tk.Frame(self._content_frame, height=height, bg=COLOR_BG).pack(fill="x")

    # ==================================================================
    # Разделы
    # ==================================================================

    def _section_1(self) -> None:
        self._section_header(1, "НАЗНАЧЕНИЕ ПЕРЕСЧЁТА")

        self._paragraph(
            "Паспортная мощность радиатора указывается производителем для эталонного "
            "температурного графика 95/85/20 °С:"
        )
        self._bullet_list([
            "подача — 95 °С",
            "обратка — 85 °С",
            "помещение — 20 °С",
        ])
        self._paragraph(
            "Температурный напор при этом: Δt = (95 + 85) / 2 − 20 = 70 °С."
        )
        self._paragraph(
            "В реальных проектах температурный график часто отличается. Типовые графики: "
            "90/70/20, 85/60/20, 80/60/20, 75/65/20, 70/55/20, 55/45/20."
        )
        self._paragraph(
            "При изменении графика фактическая тепловая мощность радиатора отличается "
            "от паспортной. NexTT автоматически пересчитывает её по ГОСТ 31311-2022."
        )
        self._spacer()

    def _section_2(self) -> None:
        self._section_header(2, "ФИЗИЧЕСКИЙ СМЫСЛ ФОРМУЛЫ")

        self._paragraph(
            "Тепловой поток от радиатора к воздуху помещения описывается законом "
            "Ньютона—Рихмана:"
        )
        self._formula("Q = k × F × Δt")
        self._paragraph(
            "где Q — тепловой поток (Вт), k — коэффициент теплопередачи (Вт/(м²·К)), "
            "F — площадь поверхности теплообмена (м²), Δt — температурный напор (°С)."
        )
        self._paragraph(
            "Для панельных радиаторов коэффициент k сам зависит от Δt (из-за изменения "
            "режима движения теплоносителя и условий конвекции). Поэтому зависимость "
            "Q от Δt имеет не линейный, а степенной характер:"
        )
        self._formula("Q = C × Δtⁿ")
        self._paragraph(
            "где C — константа, зависящая от модели радиатора, "
            "n — эмпирический показатель степени (экспонент)."
        )
        self._spacer()

    def _section_3(self) -> None:
        self._section_header(3, "ФОРМУЛА ПЕРЕСЧЁТА")

        self._paragraph(
            "Формула пересчёта мощности радиатора с эталонного графика (Δt = 70 °С) "
            "на произвольный:"
        )
        self._formula("Q = Qном × (Δt / 70)ⁿ")
        self._paragraph("где:")
        self._bullet_list([
            "Q — искомая мощность при фактическом графике, Вт",
            "Qном — паспортная мощность при эталонном графике 95/85/20, Вт",
            "Δt — фактический температурный напор, °С",
            "n — экспонент для данного типа радиатора",
        ])
        self._paragraph("Эквивалентная запись: Q = Qном / (70 / Δt)ⁿ.")
        self._paragraph("Свойства формулы:")
        self._bullet_list([
            "При Δt = 70 °С коэффициент равен 1, и Q = Qном.",
            "При Δt < 70 °С коэффициент меньше 1, и Q < Qном (мощность падает).",
            "При Δt > 70 °С коэффициент больше 1, и Q > Qном (мощность растёт).",
        ])
        self._spacer()

    def _section_4(self) -> None:
        self._section_header(4, "ТЕМПЕРАТУРНЫЙ НАПОР Δt")

        self._paragraph("Формула:")
        self._formula("Δt = (t_подача + t_обратка) / 2 − t_помещение")
        self._paragraph(
            "где t_подача — температура подающей линии (°С), "
            "t_обратка — температура обратной линии (°С), "
            "t_помещение — расчётная температура воздуха в помещении (°С)."
        )
        self._paragraph("Примеры для типовых графиков:")

        self._table(
            columns=["График", "t подачи, °С", "t обратки, °С", "t помещения, °С", "Δt, °С"],
            rows=[
                ["95/85/20 (эталон)", "95", "85", "20", "70.0"],
                ["90/70/20", "90", "70", "20", "60.0"],
                ["85/60/20", "85", "60", "20", "52.5"],
                ["80/60/20", "80", "60", "20", "50.0"],
                ["75/65/20", "75", "65", "20", "50.0"],
                ["70/55/20", "70", "55", "20", "42.5"],
                ["55/45/20", "55", "45", "20", "30.0"],
            ],
            column_widths=[180, 110, 110, 130, 90],
        )

        self._paragraph(
            "Обратите внимание: разные графики могут давать одинаковый Δt. "
            "Например, 80/60/20 и 75/65/20 — оба дают Δt = 50 °С. "
            "Мощность радиатора при этих двух графиках одинакова."
        )
        self._spacer()

    def _section_5(self) -> None:
        self._section_header(5, "ЭКСПОНЕНТ n")

        self._paragraph(
            "Экспонент n — безразмерный коэффициент, определяющий чувствительность "
            "мощности радиатора к изменению температурного напора. Значение n зависит "
            "только от типа радиатора и определено экспериментально."
        )

        self._table(
            columns=["Тип радиатора", "Экспонент n"],
            rows=[
                ["Тип 10", "1.14"],
                ["Тип 11", "1.14"],
                ["Тип 20", "1.18"],
                ["Тип 21", "1.16"],
                ["Тип 22", "1.14"],
                ["Тип 30", "1.19"],
                ["Тип 33", "1.15"],
            ],
            column_widths=[200, 150],
        )

        self._paragraph("Чем больше n, тем сильнее падает мощность при снижении Δt.")
        self._spacer()

    def _section_6(self) -> None:
        self._section_header(6, "ПРИМЕРЫ РАСЧЁТА")

        self._paragraph(
            "Пример 1. Радиатор LaggarTT Classic VK-Profil 10/500/1000 "
            "(Qном = 914 Вт), график 90/70/20:"
        )
        self._formula(
            "Δt = (90 + 70) / 2 − 20 = 60 °С\n"
            "n = 1.14 (тип 10)\n"
            "Q = 914 × (60 / 70)^1.14 = 914 × 0.833 ≈ 761 Вт"
        )

        self._paragraph(
            "Пример 2. Тот же радиатор, график 55/45/20:"
        )
        self._formula(
            "Δt = (55 + 45) / 2 − 20 = 30 °С\n"
            "Q = 914 × (30 / 70)^1.14 = 914 × 0.369 ≈ 337 Вт"
        )

        self._paragraph(
            "Пример 3. Сравнение графиков для радиатора 22/500/1000 "
            "(Qном = 2352 Вт, n = 1.14):"
        )

        self._table(
            columns=["График", "Δt, °С", "Коэффициент", "Мощность, Вт"],
            rows=[
                ["95/85/20", "70.0", "1.000", "2352"],
                ["90/70/20", "60.0", "0.833", "1959"],
                ["85/60/20", "52.5", "0.708", "1665"],
                ["80/60/20", "50.0", "0.664", "1562"],
                ["75/65/20", "50.0", "0.664", "1562"],
                ["70/55/20", "42.5", "0.542", "1275"],
                ["55/45/20", "30.0", "0.369", "868"],
            ],
            column_widths=[160, 100, 130, 130],
        )

        self._paragraph(
            "Из таблицы видно: чем ниже температурный график, тем больше радиаторов "
            "потребуется, чтобы обеспечить ту же теплоотдачу."
        )
        self._spacer()

    def _section_7(self) -> None:
        self._section_header(7, "КАК ПОЛЬЗОВАТЬСЯ ПЕРЕСЧЁТОМ В NEXTT")

        self._paragraph(
            "В главном окне программы, между матрицей радиаторов и нижней панелью, "
            "есть строка «Температурный график» с тремя полями:"
        )
        self._bullet_list([
            "Подача — температура подающей линии, °С",
            "Обратка — температура обратной линии, °С",
            "Помещение — температура воздуха в помещении, °С",
        ])
        self._paragraph(
            "Рядом отображается метка «Δt = …°С», которая мгновенно пересчитывается "
            "при изменении любого поля."
        )
        self._paragraph("Цвет метки Δt:")
        self._bullet_list([
            "Синий — эталонный график 95/85/20 (Δt = 70 °С), пересчёта нет",
            "Оранжевый — нестандартный график, мощности пересчитываются",
            "Красный — некорректный график (Δt ≤ 0), спецификация не создаётся",
        ])
        self._paragraph("Действия:")
        self._bullet_list([
            "Задать температурный график проекта в трёх полях.",
            "Проверить результат в подсказке при наведении на ячейку матрицы.",
            "Нажать кнопку «Показать» для открытия справочной таблицы мощностей.",
            "Нажать кнопку «Сброс 95/85/20» для возврата к эталонному графику.",
            "Нажать «Предпросмотр» или «Создать спецификацию» — документ будет "
            "с пересчитанными мощностями.",
        ])
        self._paragraph(
            "Важно: при запуске программа всегда начинает работу с эталонного "
            "графика 95/85/20, независимо от предыдущего сеанса."
        )
        self._spacer()

    def _section_8(self) -> None:
        self._section_header(8, "ОСОБЕННОСТИ ДЛЯ ОТДЕЛЬНЫХ ТИПОВ")

        self._paragraph(
            "Гигиенические радиаторы (HV, H) — модели с гладкой поверхностью "
            "без конвективного оребрения. По теплотехническим характеристикам "
            "близки к классическим. Для них используются те же экспоненты, что и для "
            "классических аналогов того же типа (10, 20, 30)."
        )
        self._paragraph(
            "Типы 20, 21, 22 — универсальные, не имеют левого/правого исполнения. "
            "Экспоненты одинаковы независимо от стороны подключения."
        )
        self._paragraph(
            "Тип 12 (Kermi) — в исходных спецификациях конкурентов иногда встречается "
            "тип 12, которого нет в базе LaggarTT. Программа автоматически заменяет "
            "его на тип 21 и использует соответствующие экспоненты."
        )
        self._paragraph(
            "Типы 30 и 33 — трёхпанельные радиаторы с наибольшей удельной мощностью. "
            "У них самые высокие экспоненты (до 1.19), то есть они наиболее "
            "чувствительны к изменению Δt. Это важно при низкотемпературных графиках."
        )
        self._spacer()

    def _section_9(self) -> None:
        self._section_header(9, "ИСТОЧНИК МЕТОДИКИ")

        self._paragraph(
            "Методика пересчёта мощности стальных панельных радиаторов основана на:"
        )
        self._bullet_list([
            "ГОСТ 31311-2022 «Приборы отопительные. Общие технические условия». "
            "Стандарт устанавливает требования к методике испытаний и определению "
            "номинальной мощности отопительных приборов.",
            "Данные производителя, предоставленные в файле 'Копия Meteor LaggarTT аудитор от 26.03.2026.xlsx', "
            "который содержит экспериментально определенные значения экспонентов n для каждого типа радиаторов.",
            "Технический каталог LaggarTT — источник паспортных значений мощности "
            "при эталонном графике 95/85/20.",
        ])
        self._paragraph(
            "Формула пересчёта Q = Qном × (Δt/70)ⁿ является стандартной в практике "
            "подбора стальных панельных радиаторов и используется всеми крупными "
            "производителями (Kermi, Purmo, Zehnder, Prado и др.) в их программных "
            "продуктах."
        )
        self._paragraph("Диапазон применимости формулы: Δt = 30…80 °С.")
        self._spacer()

    def _section_10(self) -> None:
        self._section_header(10, "ПРОВЕРКА РАСЧЁТА В NEXTT")

        self._paragraph(
            "Чтобы убедиться, что пересчёт работает корректно, можно выполнить "
            "простую проверку на радиаторе LaggarTT Classic VK-Profil 10/500/1000 "
            "(паспортная мощность 914 Вт):"
        )
        self._bullet_list([
            "Запустить программу. График по умолчанию 95/85/20. Открыть справочную "
            "таблицу «Показать» для высоты 500 мм. Найти в таблице строку «Тип 10», "
            "столбец «1000». Значение должно быть 914.",
            "Изменить график на 90/70/20 (Δt = 60 °С). Открыть таблицу снова. "
            "В той же ячейке должно быть 761 (Q = 914 × 0.833).",
            "Изменить график на 55/45/20 (Δt = 30 °С). В той же ячейке должно быть "
            "337 (Q = 914 × 0.369).",
            "Вернуться к 95/85/20. Значение снова 914.",
        ])
        self._paragraph("Если все три значения совпадают — методика работает корректно.")

    # ==================================================================
    # Закрытие
    # ==================================================================

    def _close(self) -> None:
        """Закрывает окно и отписывается от события масштабирования."""
        try:
            bus.unsubscribe(Events.FONT_SCALE_CHANGED, self._on_font_scale_changed)
        except Exception as e:
            logger.debug(f"Ошибка отписки от FONT_SCALE_CHANGED: {e}")

        if self._dialog:
            try:
                self._dialog.destroy()
            except tk.TclError:
                pass
            self._dialog = None
            self._canvas = None
            self._content_frame = None
            self._scrollbar = None
            self._close_btn = None