"""
Диалог «Замена секционных радиаторов» — подбор панельных LaggarTT
под секционные радиаторы. Открывается из главного окна.

Структура окна:
    • Левая колонка — параметры и кнопки:
        - Мощность секции, Вт
        - Цена секции, руб (с НДС)
        - Отклонение, %
        - Тип подключения (VK / K)
        - Вид монтажа (Настенный / Напольный / Без)
        - Режим подбора (По мощности / По габаритам)
        - [Создать спецификацию]
        - [Предпросмотр]
        - [Сброс полей]

    • Правая часть — таблица с двумя зонами:
        - Зелёная (секционные): Секций | Введите кол-во | Мощность |
                                Суммарная | Цена радиатора | Сумма
        - Голубая (панельные):  Наименование | Мощность | Суммарная |
                                Отклонение | Кол-во | Цена | Сумма
        - Одна общая итоговая строка внизу

    • Внизу справа — кнопка [Закрыть].

Логика поля «Введите кол-во»:
    • Пока ни одно поле активной высоты не заполнено — вся колонка
      бледно-красная (привлекает внимание).
    • Как только заполнено хотя бы одно поле — вся колонка голубая.
    • По умолчанию пусто, не «0».

Всё масштабируется через FontManager.
"""

import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional, Dict, List, Tuple
import pandas as pd
from nextt.logger import get_logger
from nextt.events import bus, Events
from nextt.core.radiator_selector import (
    SECTION_POWER as _SECTION_POWER_BASE,
    MIN_SECTIONS as _MIN_SECTIONS_BASE,
    MAX_SECTIONS,
)
from nextt.core.dimension_selector import DimensionSelector, SelectedByDimension
from nextt.core.power_selector import PowerSelector, SelectedByPower
from nextt.core.power_recalculator import PowerRecalculator
logger = get_logger(__name__)


# Задержка debounce при вводе в поле количества (мс)
DEBOUNCE_MS = 120

# Режимы подбора
MODE_POWER = "power"
MODE_DIMENSION = "dimension"

# Минимальное количество секций (3 убираем)
MIN_SECTIONS = 4

# Локальный словарь мощностей секции. Дополняет базовый ключом 350.
SECTION_POWER: Dict[int, int] = dict(_SECTION_POWER_BASE)
SECTION_POWER.setdefault(350, 160)

# Цена секции по умолчанию (руб, с НДС) для каждой высоты.
DEFAULT_SECTION_PRICE: Dict[int, int] = {
    300: 1300,
    350: 1400,
    500: 1700,
}

# Маппинг высот секционного → высоты панельного
HEIGHT_TO_PANEL: Dict[int, int] = {
    300: 300,
    350: 400,
    500: 500,
}

# Сколько строк показывать в popup-списке
POPUP_VISIBLE_ROWS = 4

# Базовые ширины колонок (при scale = 1.0), в пикселях.
BASE_COL_WIDTHS = [
    70,   # 0: Секций в радиаторе
    65,   # 1: Введите кол-во (две строки)
    70,   # 2: Мощность, Вт
    110,  # 3: Суммарная мощность, Вт
    120,  # 4: Цена радиатора, руб (с НДС)
    110,  # 5: Сумма, руб (с НДС)
    6,    # 6: разделитель
    220,  # 7: Наименование
    70,   # 8: Мощность, Вт
    110,  # 9: Суммарная мощность, Вт
    90,   # 10: Отклонение, %
    45,   # 11: Кол-во
    110,  # 12: Цена, руб (с НДС)
    120,  # 13: Сумма, руб (с НДС)
]

# Базовые высоты строк
BASE_HEADER_HEIGHT = 60
BASE_ROW_HEIGHT = 24
BASE_TOTAL_HEIGHT = 28

# Базовая ширина левой колонки
BASE_LEFT_COLUMN_WIDTH = 260

def _plural_sections(n: int) -> str:
    """
    Правильное склонение слова «секция» по числу n.

    1, 21, 31, ...      → «секция»
    2, 3, 4, 22, ...    → «секции»
    5, 6, ..., 20, 25   → «секций»
    """
    n_abs = abs(int(n))
    last_two = n_abs % 100
    last_one = n_abs % 10

    # 11–14 — всегда «секций» (исключение из правил)
    if 11 <= last_two <= 14:
        return "секций"
    if last_one == 1:
        return "секция"
    if 2 <= last_one <= 4:
        return "секции"
    return "секций"

class SectionToPanelDialog:
    """Диалог переподбора секционных радиаторов на панельные LaggarTT."""

    # ---------- цвета ----------
    BG = "#dedede"
    BG_LEFT = "#d4d4d4"
    BG_TITLE = "#d0d0d0"
    BG_HEADING_SRC = "#d8ead8"
    BG_HEADING_PNL = "#d8e4f5"
    BG_SRC_FILLED = "#eef7ee"
    BG_SRC_EMPTY = "#f8fcf8"
    BG_PNL_FILLED = "#eef4ff"
    BG_PNL_EMPTY = "#f8faff"
    BG_PNL_WARNING = "#f8d7d7"
    BG_PNL_MANUAL = "#fffacd"
    BG_TOTAL_SRC = "#c8dcc8"
    BG_TOTAL_PNL = "#c8d4e8"
    BG_INPUT = "#eef6ff"
    BG_INPUT_EMPTY = "#f8d7d7"
    FG_ACCENT = "#263168"
    FG_SRC = "#2c5c2c"
    FG_PNL = "#1e3a6c"
    FG_EMPTY = "#c0c0c0"
    FG_NEGATIVE = "#a02626"
    DIVIDER = "#a0a0a0"

    TAB_ACTIVE_BG = "#263168"
    TAB_ACTIVE_FG = "white"
    TAB_FILLED_BG = "#d8e4f5"
    TAB_EMPTY_BG = "#e8e8e8"
    TAB_FILLED_FG = "#1e3a6c"
    TAB_EMPTY_FG = "#444141"

    HEIGHTS = (300, 350, 500)

    def __init__(self, app):
        self.app = app
        self.font_manager = app.font_manager

        self._dialog: Optional[tk.Toplevel] = None

        self._selector_power = PowerSelector(app.data_provider)
        self._selector_dimension = DimensionSelector(app.data_provider)

        self._current_height = 500

        self._deviation_var = tk.StringVar(value="5")
        self._conn_mode_var = tk.StringVar(value="K")
        self._mount_var = tk.StringVar(value="настенный")
        self._mode_var = tk.StringVar(value=MODE_POWER)

        self._power_vars: Dict[int, tk.StringVar] = {
            h: tk.StringVar(value=str(SECTION_POWER[h])) for h in self.HEIGHTS
        }
        self._price_vars: Dict[int, tk.StringVar] = {
            h: tk.StringVar(value=str(DEFAULT_SECTION_PRICE[h]))
            for h in self.HEIGHTS
        }

        self._qty_vars: Dict[int, Dict[int, tk.StringVar]] = {h: {} for h in self.HEIGHTS}
        self._qty_entries: Dict[int, Dict[int, tk.Entry]] = {h: {} for h in self.HEIGHTS}
        self._row_widgets: Dict[int, Dict[int, Dict]] = {h: {} for h in self.HEIGHTS}
        self._selected: Dict[int, Dict[int, Optional[object]]] = {h: {} for h in self.HEIGHTS}

        self._manual_choice: Dict[Tuple[int, int], Dict] = {}

        self._height_buttons: Dict[int, tk.Label] = {}
        self._height_var = tk.IntVar(value=self._current_height)

        self._power_entry: Optional[tk.Entry] = None
        self._price_entry: Optional[tk.Entry] = None

        self._total_src_qty_lbl: Optional[tk.Label] = None
        self._total_src_power_lbl: Optional[tk.Label] = None
        self._total_src_sum_lbl: Optional[tk.Label] = None
        self._total_pnl_power_lbl: Optional[tk.Label] = None
        self._total_pnl_dev_lbl: Optional[tk.Label] = None
        self._total_pnl_qty_lbl: Optional[tk.Label] = None
        self._total_pnl_sum_lbl: Optional[tk.Label] = None

        self._create_spec_btn: Optional[ttk.Button] = None
        self._preview_btn: Optional[ttk.Button] = None
        self._reset_btn: Optional[ttk.Button] = None

        self._debounce_timers: Dict[tuple, str] = {}
        self._focus_height: Dict[int, int] = {}

        self._row_tooltip: Optional[tk.Toplevel] = None
        self._popup: Optional[tk.Toplevel] = None
        self._popup_listbox: Optional[tk.Listbox] = None
        self._popup_candidates: List[Dict] = []
        self._popup_height: int = 0
        self._popup_sections: int = 0
        # ========== ПОДСКАЗКИ (только для этого окна) ==========
        from nextt.config import config as _config
        _saved_tooltips = _config.get("section_to_panel_show_tooltips", True)
        self._show_tooltips_var = tk.BooleanVar(value=bool(_saved_tooltips))
        self._tooltip_window: Optional[tk.Toplevel] = None
        self._tooltip_after_id: Optional[str] = None

        self._canvas: Optional[tk.Canvas] = None
        self._canvas_frame: Optional[tk.Frame] = None

    # ==================================================================
    # Открытие / закрытие
    # ==================================================================
    def show(self) -> None:
        """
        Показывает окно «Замена секционных».
        Если окно уже создано — просто делает его видимым и даёт фокус,
        сохраняя все введённые данные.
        """
        if self._dialog and self._dialog.winfo_exists():
            # Окно уже создано — показываем и даём фокус
            try:
                self._dialog.deiconify()
                self._dialog.lift()
                self._dialog.focus_force()
            except Exception:
                pass
            return

        # --- Первое открытие: создаём окно с нуля ---
        self._dialog = tk.Toplevel(self.app.root)

        try:
            from nextt.config import get_resource_path
            import os
            icon_path = get_resource_path("icon.ico")
            if icon_path and os.path.exists(icon_path):
                self._dialog.iconbitmap(icon_path)
        except Exception:
            pass

        from nextt.utils.window_manager import (
            setup_dialog_window, get_safe_geometry,
            fix_window_buttons_after_geometry,
        )
        setup_dialog_window(self._dialog, "Замена секционных радиаторов — NexTT")
        self._dialog.geometry(get_safe_geometry(self._dialog))
        fix_window_buttons_after_geometry(self._dialog)

        scale = self.font_manager.scale
        screen_w = self._dialog.winfo_screenwidth()
        screen_h = self._dialog.winfo_screenheight()
        min_w = min(int(1400 * scale), screen_w - 20)
        min_h = min(int(700 * scale), screen_h - 60)
        try:
            self._dialog.minsize(min_w, min_h)
        except Exception:
            pass

        self._dialog.configure(bg=self.BG)
        self._dialog.protocol("WM_DELETE_WINDOW", self._close)
        self._dialog.bind("<Escape>", lambda e: self._close_popup_or_dialog())

        bus.subscribe(Events.FONT_SCALE_CHANGED, self._on_font_scale_changed)

        self._build_ui()

    def destroy(self) -> None:
        """
        Полностью уничтожает окно «Замена секционных»,
        снимая все подписки и трассы. Вызывается только при
        сбросе данных в главном окне.
        """
        # Отписки от событий
        try:
            bus.unsubscribe(Events.FONT_SCALE_CHANGED, self._on_font_scale_changed)
        except Exception:
            pass

        # Отписки от трасс переменных графика
        try:
            main_window = self.app.main_window
            if getattr(self, '_graph_supply_var_trace', None):
                main_window._graph_supply_var.trace_remove(
                    "write", self._graph_supply_var_trace
                )
            if getattr(self, '_graph_return_var_trace', None):
                main_window._graph_return_var.trace_remove(
                    "write", self._graph_return_var_trace
                )
            if getattr(self, '_graph_room_var_trace', None):
                main_window._graph_room_var.trace_remove(
                    "write", self._graph_room_var_trace
                )
        except Exception as e:
            logger.debug(f"Ошибка отписки от трасс графика: {e}")

        # Отписки от трасс скидок
        try:
            main_window = self.app.main_window
            if getattr(self, '_radiator_discount_trace', None):
                main_window.radiator_discount_var.trace_remove(
                    "write", self._radiator_discount_trace
                )
            if getattr(self, '_bracket_discount_trace', None):
                main_window.bracket_discount_var.trace_remove(
                    "write", self._bracket_discount_trace
                )
        except Exception as e:
            logger.debug(f"Ошибка отписки от трасс скидок: {e}")

        # Остановка таймеров debounce
        for tid in self._debounce_timers.values():
            try:
                if self._dialog and self._dialog.winfo_exists():
                    self._dialog.after_cancel(tid)
            except Exception:
                pass
        self._debounce_timers.clear()

        # Скрываем подсказки и попап
        self._cancel_tooltip()
        self._hide_row_tooltip()
        self._hide_candidate_popup()

        # Уничтожаем окно
        if self._dialog and self._dialog.winfo_exists():
            try:
                self._dialog.destroy()
            except Exception:
                pass
        self._dialog = None

    def _close_popup_or_dialog(self) -> None:
        if self._popup and self._popup.winfo_exists():
            self._hide_candidate_popup()
            return
        self._close()

    def _close(self) -> None:
        """
        Скрывает окно «Замена секционных», сохраняя всё его состояние
        в памяти. Окно можно снова показать методом show() — данные
        останутся нетронутыми.
        """
        # Скрываем подсказки и popup, чтобы они не висели поверх
        self._cancel_tooltip()
        self._hide_row_tooltip()
        self._hide_candidate_popup()

        # Скрываем окно, но НЕ уничтожаем — все данные сохраняются
        if self._dialog and self._dialog.winfo_exists():
            try:
                self._dialog.withdraw()
            except Exception:
                pass

    def _on_font_scale_changed(self, scale: float) -> None:
        if not self._dialog or not self._dialog.winfo_exists():
            return

        current_height = self._current_height
        manual_choice = dict(self._manual_choice)
        qty_values = {
            h: {s: self._qty_vars[h][s].get() for s in self._qty_vars[h]}
            for h in self.HEIGHTS
        }

        for w in self._dialog.winfo_children():
            w.destroy()

        self._height_buttons.clear()
        self._qty_vars = {h: {} for h in self.HEIGHTS}
        self._qty_entries = {h: {} for h in self.HEIGHTS}
        self._row_widgets = {h: {} for h in self.HEIGHTS}
        self._selected = {h: {} for h in self.HEIGHTS}
        self._debounce_timers.clear()
        self._focus_height.clear()

        self._manual_choice = manual_choice
        self._current_height = current_height

        self._build_ui()

        for h in self.HEIGHTS:
            for s, val in qty_values.get(h, {}).items():
                if s in self._qty_vars[h]:
                    self._qty_vars[h][s].set(val)

        self._update_height_tabs_visual()
        self._refresh_table_for_height()
        self._update_qty_entries_bg()
        self._update_total_row()

    # ==================================================================
    # Масштабирование
    # ==================================================================
    def _s(self, value: int) -> int:
        try:
            scale = self.font_manager.scale
        except Exception:
            scale = 1.0
        return max(1, int(round(value * scale)))

    # ==================================================================
    # Построение интерфейса
    # ==================================================================
    def _build_ui(self) -> None:
        container = tk.Frame(self._dialog, bg=self.BG)
        container.pack(fill="both", expand=True)
        container.rowconfigure(0, weight=1)
        container.rowconfigure(1, weight=0)
        container.columnconfigure(0, weight=1)

        grid = tk.Frame(container, bg=self.BG)
        grid.grid(row=0, column=0, sticky="nsew",
                  padx=self._s(4), pady=self._s(4))
        grid.columnconfigure(0, weight=0,
                            minsize=self._s(BASE_LEFT_COLUMN_WIDTH))
        grid.columnconfigure(1, weight=1)
        grid.rowconfigure(0, weight=1)

        self._build_left(grid)
        self._build_right(grid)
        self._build_bottom_bar(container)

        self._switch_height(self._current_height)

    # ------------------------------------------------------------------
    # Левая колонка
    # ------------------------------------------------------------------
    def _build_left(self, parent: tk.Frame) -> None:
        left = tk.Frame(parent, bg=self.BG_LEFT,
                        padx=self._s(14), pady=self._s(12))
        left.grid(row=0, column=0, sticky="nsew")

        default_font = self.font_manager.get_default_font()
        bold_font = self.font_manager.get_bold_font(9)

        def section_title(text: str) -> None:
            tk.Label(
                left, text=text.upper(),
                bg=self.BG_LEFT, fg=self.FG_ACCENT,
                font=bold_font, anchor="w",
            ).pack(fill="x", pady=(self._s(10), self._s(4)))

        def field_row(label, var, is_power=False, is_price=False):
            row = tk.Frame(left, bg=self.BG_LEFT)
            row.pack(fill="x", pady=self._s(2))
            label_widget = tk.Label(row, text=label, bg=self.BG_LEFT,
                                    font=default_font)
            label_widget.pack(side="left")
            entry = tk.Entry(
                row, textvariable=var, width=6, justify="center",
                font=default_font,
            )
            entry.pack(side="right")
            if is_power:
                self._power_entry = entry
            if is_price:
                self._price_entry = entry
            return label_widget, entry

        section_title("Мощность и отклонение")

        lbl_power, entry_power = field_row(
            "Мощность секции, Вт",
            self._power_vars[self._current_height],
            is_power=True,
        )
        self._bind_tooltip(
            lbl_power,
            "Паспортная мощность одной секции радиатора при Δt = 70 °С "
            "(эталонный график 95/85/20). Возьмите значение из паспорта "
            "секционного радиатора. Если у вас есть мощность при другом "
            "температурном напоре, пересчитайте её к Δt = 70 по формуле "
            "Q₇₀ = Q × (70 / Δt)ⁿ, где n — экспонент секционного радиатора.",
        )
        self._bind_tooltip(
            entry_power,
            "Паспортная мощность одной секции радиатора при Δt = 70 °С "
            "(эталонный график 95/85/20).",
        )

        lbl_price, entry_price = field_row(
            "Цена секции, руб",
            self._price_vars[self._current_height],
            is_price=True,
        )
        self._bind_tooltip(
            lbl_price,
            "Стоимость одной секции секционного радиатора с НДС, руб. "
            "Используется для расчёта стоимости и сравнения с ценой "
            "панельного аналога.",
        )
        self._bind_tooltip(
            entry_price,
            "Стоимость одной секции секционного радиатора с НДС, руб.",
        )

        for h in self.HEIGHTS:
            self._power_vars[h].trace_add(
                "write", lambda *args, hh=h: self._on_power_changed(hh))
            self._price_vars[h].trace_add(
                "write", lambda *args, hh=h: self._on_price_changed(hh))

        lbl_dev, entry_dev = field_row("Отклонение, %", self._deviation_var)
        self._bind_tooltip(
            lbl_dev,
            "Допустимое отклонение мощности панельного аналога от "
            "мощности секционного радиатора. Например, 5 означает, "
            "что подойдут панельные радиаторы с отклонением в пределах "
            "±5 % от мощности секционного.",
        )
        self._bind_tooltip(
            entry_dev,
            "Допустимое отклонение мощности в процентах. "
            "Например, 5 — это ±5 %.",
        )
        self._deviation_var.trace_add(
            "write", lambda *args: self._on_param_changed())

        section_title("Тип подключения")

        rb_vk = tk.Radiobutton(
            left, text="VK (нижнее)", variable=self._conn_mode_var, value="VK",
            bg=self.BG_LEFT, anchor="w", font=default_font,
            activebackground=self.BG_LEFT, command=self._on_param_changed,
        )
        rb_vk.pack(fill="x", pady=self._s(2))
        self._bind_tooltip(
            rb_vk,
            "Нижнее подключение (VK, Ventil-Kompakt). Подводка снизу, "
            "встроенный термостатический клапан. Используется для "
            "классических панельных радиаторов.",
        )

        rb_k = tk.Radiobutton(
            left, text="K (боковое)", variable=self._conn_mode_var, value="K",
            bg=self.BG_LEFT, anchor="w", font=default_font,
            activebackground=self.BG_LEFT, command=self._on_param_changed,
        )
        rb_k.pack(fill="x", pady=self._s(2))
        self._bind_tooltip(
            rb_k,
            "Боковое подключение (K). Подводка сбоку, с торца радиатора. "
            "Используется для классических панельных радиаторов с боковым "
            "подключением.",
        )

        section_title("Вид монтажа")

        rb_wall = tk.Radiobutton(
            left, text="Настенный", variable=self._mount_var, value="настенный",
            bg=self.BG_LEFT, anchor="w", font=default_font,
            activebackground=self.BG_LEFT, command=self._on_param_changed,
        )
        rb_wall.pack(fill="x", pady=self._s(2))
        self._bind_tooltip(
            rb_wall,
            "Радиатор крепится на стену с помощью настенных кронштейнов. "
            "Стандартный вариант для большинства систем отопления.",
        )

        rb_floor = tk.Radiobutton(
            left, text="Напольный", variable=self._mount_var, value="напольный",
            bg=self.BG_LEFT, anchor="w", font=default_font,
            activebackground=self.BG_LEFT, command=self._on_param_changed,
        )
        rb_floor.pack(fill="x", pady=self._s(2))
        self._bind_tooltip(
            rb_floor,
            "Радиатор устанавливается на пол с помощью напольных "
            "кронштейнов. Используется для панорамного остекления "
            "или когда настенный монтаж невозможен.",
        )

        rb_no_br = tk.Radiobutton(
            left, text="Без кронштейнов", variable=self._mount_var, value="без",
            bg=self.BG_LEFT, anchor="w", font=default_font,
            activebackground=self.BG_LEFT, command=self._on_param_changed,
        )
        rb_no_br.pack(fill="x", pady=self._s(2))
        self._bind_tooltip(
            rb_no_br,
            "Кронштейны не подбираются и не учитываются в спецификации. "
            "Используйте, если кронштейны закупаются отдельно или уже есть.",
        )

        section_title("Режим подбора")

        rb_power = tk.Radiobutton(
            left, text="По мощности", variable=self._mode_var, value=MODE_POWER,
            bg=self.BG_LEFT, anchor="w", font=default_font,
            activebackground=self.BG_LEFT, command=self._on_mode_changed,
        )
        rb_power.pack(fill="x", pady=self._s(2))
        self._bind_tooltip(
            rb_power,
            "Фиксируется: высота, подключение.\n"
            "Ищется: самая компактная панель, длина которой не превышает "
            "длину секционного (секции × 100 мм), а мощность близка к исходной.\n"
            "Приоритет при выборе: короткая длина → тонкая панель → "
            "близкая мощность.\n\n"
            "Используйте, когда точные габариты не критичны.",
        )

        rb_dim = tk.Radiobutton(
            left, text="По габаритам", variable=self._mode_var, value=MODE_DIMENSION,
            bg=self.BG_LEFT, anchor="w", font=default_font,
            activebackground=self.BG_LEFT, command=self._on_mode_changed,
        )
        rb_dim.pack(fill="x", pady=self._s(2))
        self._bind_tooltip(
            rb_dim,
            "Фиксируется: высота, длина (секции × 100 мм), подключение.\n"
            "Ищется: панель с такими же габаритами, у которой мощность "
            "ближе всего к исходной.\n"
            "Если мощность вне допуска: предлагается более тонкая панель — "
            "при условии, что её мощность укладывается в допуск.\n\n"
            "Используйте, когда посадочное место зафиксировано.",
        )

        buttons_block = tk.Frame(left, bg=self.BG_LEFT)
        buttons_block.pack(side="bottom", fill="x", pady=(self._s(20), 0))

        ttk.Button(
            buttons_block, text="Создать спецификацию",
            command=self._on_create_spec,
        ).pack(fill="x", pady=self._s(3))

        ttk.Button(
            buttons_block, text="Предпросмотр",
            command=self._on_preview,
        ).pack(fill="x", pady=self._s(3))

        ttk.Button(
            buttons_block, text="Сброс полей",
            command=self._on_reset,
        ).pack(fill="x", pady=self._s(3))

    # ------------------------------------------------------------------
    # Правая часть
    # ------------------------------------------------------------------
    def _build_right(self, parent: tk.Frame) -> None:
        wrap = tk.Frame(parent, bg=self.BG)
        wrap.grid(row=0, column=1, sticky="nsew")
        wrap.rowconfigure(1, weight=1)
        wrap.columnconfigure(0, weight=1)

        selector = tk.Frame(wrap, bg=self.BG_TITLE,
                            padx=self._s(10), pady=self._s(6))
        selector.grid(row=0, column=0, sticky="ew", pady=(0, self._s(4)))

        tk.Label(
            selector, text="Высота секции:",
            bg=self.BG_TITLE, fg=self.FG_ACCENT,
            font=self.font_manager.get_bold_font(9),
        ).pack(side="left", padx=(0, self._s(8)))

        for h in self.HEIGHTS:
            lbl = tk.Label(
                selector,
                text=f"{h} мм",
                font=self.font_manager.get_bold_font(10),
                bg=self.TAB_EMPTY_BG,
                fg=self.TAB_EMPTY_FG,
                padx=self._s(14), pady=self._s(6),
                cursor="hand2",
                relief="flat",
                borderwidth=1,
            )
            lbl.pack(side="left", padx=self._s(2))
            lbl.bind("<Button-1>", lambda ev, hh=h: self._switch_height(hh))
            self._height_buttons[h] = lbl

        # ================================================================
        # Блок температурного графика (справа от вкладок высоты)
        # ================================================================
        graph_frame = tk.Frame(selector, bg=self.BG_TITLE)
        graph_frame.pack(side="right")

        default_font = self.font_manager.get_default_font()
        bold_font = self.font_manager.get_bold_font(9)

        tk.Label(
            graph_frame, text="Температурный график:",
            bg=self.BG_TITLE, fg="#000000",
            font=bold_font,
        ).pack(side="left", padx=(0, self._s(8)))

        main_window = self.app.main_window

        # Подача
        tk.Label(
            graph_frame, text="Подача:",
            bg=self.BG_TITLE, fg="#444141",
            font=default_font,
        ).pack(side="left")
        self._graph_supply_entry = tk.Entry(
            graph_frame,
            textvariable=main_window._graph_supply_var,
            width=5,
            justify="center",
            font=default_font,
            validate="key",
            validatecommand=(self._dialog.register(self._validate_temperature), '%P'),
        )
        self._graph_supply_entry.pack(side="left", padx=(self._s(4), self._s(4)))
        tk.Label(
            graph_frame, text="°С",
            bg=self.BG_TITLE, fg="#444141",
            font=default_font,
        ).pack(side="left", padx=(0, self._s(10)))

        # Обратка
        tk.Label(
            graph_frame, text="Обратка:",
            bg=self.BG_TITLE, fg="#444141",
            font=default_font,
        ).pack(side="left")
        self._graph_return_entry = tk.Entry(
            graph_frame,
            textvariable=main_window._graph_return_var,
            width=5,
            justify="center",
            font=default_font,
            validate="key",
            validatecommand=(self._dialog.register(self._validate_temperature), '%P'),
        )
        self._graph_return_entry.pack(side="left", padx=(self._s(4), self._s(4)))
        tk.Label(
            graph_frame, text="°С",
            bg=self.BG_TITLE, fg="#444141",
            font=default_font,
        ).pack(side="left", padx=(0, self._s(10)))

        # Помещение
        tk.Label(
            graph_frame, text="Помещение:",
            bg=self.BG_TITLE, fg="#444141",
            font=default_font,
        ).pack(side="left")
        self._graph_room_entry = tk.Entry(
            graph_frame,
            textvariable=main_window._graph_room_var,
            width=5,
            justify="center",
            font=default_font,
            validate="key",
            validatecommand=(self._dialog.register(self._validate_temperature), '%P'),
        )
        self._graph_room_entry.pack(side="left", padx=(self._s(4), self._s(4)))
        tk.Label(
            graph_frame, text="°С",
            bg=self.BG_TITLE, fg="#444141",
            font=default_font,
        ).pack(side="left", padx=(0, self._s(12)))

        # Метка Δt
        self._delta_t_label = tk.Label(
            graph_frame, text="Δt = 70,00 °С",
            bg=self.BG_TITLE, fg=self.FG_ACCENT,
            font=bold_font,
        )
        self._delta_t_label.pack(side="left")

        # ================================================================
        # Подписка на изменения переменных графика — для синхронизации
        # метки Δt и app.temperature_graph.
        # ================================================================
        self._graph_supply_var_trace = main_window._graph_supply_var.trace_add(
            "write", lambda *a: self._on_graph_changed_local()
        )
        self._graph_return_var_trace = main_window._graph_return_var.trace_add(
            "write", lambda *a: self._on_graph_changed_local()
        )
        self._graph_room_var_trace = main_window._graph_room_var.trace_add(
            "write", lambda *a: self._on_graph_changed_local()
        )

        # Первичное обновление метки Δt
        self._on_graph_changed_local()

        # ================================================================
        # Canvas с таблицей — как было
        # ================================================================
        canvas_container = tk.Frame(wrap, bg=self.BG)
        canvas_container.grid(row=1, column=0, sticky="nsew")

        self._canvas = tk.Canvas(
            canvas_container, bg=self.BG,
            highlightthickness=0, bd=0,
        )
        hsb = ttk.Scrollbar(
            canvas_container, orient="horizontal",
            command=self._canvas.xview,
        )
        vsb = ttk.Scrollbar(
            canvas_container, orient="vertical",
            command=self._canvas.yview,
        )
        self._canvas.configure(
            xscrollcommand=hsb.set,
            yscrollcommand=vsb.set,
        )

        self._canvas.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        canvas_container.grid_rowconfigure(0, weight=1)
        canvas_container.grid_columnconfigure(0, weight=1)

        self._canvas_frame = tk.Frame(self._canvas, bg=self.BG)
        self._canvas_window = self._canvas.create_window(
            (0, 0), window=self._canvas_frame, anchor="nw",
        )

        # Обновление scrollregion при изменении размеров содержимого.
        # Отложенный вызов (after) нужен, чтобы scrollregion пересчитался
        # уже после того, как все дочерние виджеты отрисованы.
        def _update_scrollregion(event=None):
            if not self._canvas or not self._canvas.winfo_exists():
                return
            try:
                bbox = self._canvas.bbox("all")
                if bbox:
                    self._canvas.configure(scrollregion=bbox)
            except Exception:
                pass

        self._canvas_frame.bind("<Configure>", _update_scrollregion)
        self._canvas.after(100, _update_scrollregion)
        self._canvas.after(400, _update_scrollregion)

        # Привязываем прокрутку колесом к самому canvas и его содержимому —
        # но НЕ через bind_all. Так колесо работает только тогда, когда
        # курсор находится над таблицей, и не мешает другим виджетам.
        self._canvas.bind("<MouseWheel>", self._on_canvas_mousewheel)
        self._canvas_frame.bind("<MouseWheel>", self._on_canvas_mousewheel)
        self._canvas.bind("<Shift-MouseWheel>", self._on_canvas_mousewheel)
        self._canvas_frame.bind("<Shift-MouseWheel>", self._on_canvas_mousewheel)

        self._build_table(self._canvas_frame)

        # После построения таблицы — ещё раз обновим scrollregion
        self._canvas.after(150, _update_scrollregion)
        self._canvas.after(500, _update_scrollregion)

    def _on_canvas_mousewheel(self, event) -> None:
        # Если открыт popup — не прокручиваем таблицу
        if self._popup is not None and self._popup.winfo_exists():
            return

        if not self._canvas or not self._canvas.winfo_exists():
            return

        # Если scrollregion не установлен — не прокручиваем,
        # иначе canvas «сбросится» в начало.
        try:
            bbox = self._canvas.bbox("all")
            if not bbox or bbox[3] <= bbox[1]:
                return
        except Exception:
            return

        # Проверяем, что курсор физически над canvas
        try:
            px = self._canvas.winfo_pointerx()
            py = self._canvas.winfo_pointery()
            cx = self._canvas.winfo_rootx()
            cy = self._canvas.winfo_rooty()
            cw = self._canvas.winfo_width()
            ch = self._canvas.winfo_height()
            if not (cx <= px <= cx + cw and cy <= py <= cy + ch):
                return
        except Exception:
            pass

        try:
            if event.state & 0x0001:  # Shift зажат — горизонтальная прокрутка
                self._canvas.xview_scroll(
                    int(-1 * (event.delta / 120)), "units")
            else:
                self._canvas.yview_scroll(
                    int(-1 * (event.delta / 120)), "units")
        except Exception:
            pass


    # ------------------------------------------------------------------
    # Таблица
    # ------------------------------------------------------------------
    def _build_table(self, parent: tk.Frame) -> None:
        table = tk.Frame(parent, bg=self.BG)
        table.pack(fill="both", expand=True)

        default_font = self.font_manager.get_default_font()
        bold_small = self.font_manager.get_bold_font(9)

        widths = [self._s(w) for w in BASE_COL_WIDTHS]

        for col, w in enumerate(widths):
            weight = 1 if col == 7 else 0
            table.columnconfigure(col, minsize=w, weight=weight)

        headers = [
            (0, "Секций в\nрадиаторе", self.BG_HEADING_SRC, self.FG_SRC),
            (1, "Введите\nнеобходимое\nколичество", self.BG_HEADING_SRC, self.FG_SRC),
            (2, "Мощность,\nВт", self.BG_HEADING_SRC, self.FG_SRC),
            (3, "Суммарная\nмощность, Вт", self.BG_HEADING_SRC, self.FG_SRC),
            (4, "Цена\nрадиатора,\nруб (с НДС)", self.BG_HEADING_SRC, self.FG_SRC),
            (5, "Сумма, руб\n(с НДС)", self.BG_HEADING_SRC, self.FG_SRC),
            (7, "Наименование", self.BG_HEADING_PNL, self.FG_PNL),
            (8, "Мощность,\nВт", self.BG_HEADING_PNL, self.FG_PNL),
            (9, "Суммарная\nмощность, Вт", self.BG_HEADING_PNL, self.FG_PNL),
            (10, "Отклонение,\n%", self.BG_HEADING_PNL, self.FG_PNL),
            (11, "Кол-во", self.BG_HEADING_PNL, self.FG_PNL),
            (12, "Цена, руб\n(с НДС)", self.BG_HEADING_PNL, self.FG_PNL),
            (13, "Сумма, руб\n(с НДС)", self.BG_HEADING_PNL, self.FG_PNL),
        ]
        for col, text, bg, fg in headers:
            lbl = tk.Label(
                table, text=text, bg=bg, fg=fg,
                font=bold_small, justify="center",
                relief="ridge", borderwidth=1,
                padx=self._s(4), pady=self._s(3),
            )
            lbl.grid(row=0, column=col, sticky="nsew")

            # Подсказки на заголовках столбцов
            if col == 0:
                self._bind_tooltip(
                    lbl,
                    "Количество секций в исходном секционном радиаторе. "
                    "Длина секционного радиатора = количество секций × 100 мм.",
                )
            elif col == 1:
                self._bind_tooltip(
                    lbl,
                    "Введите количество таких секционных радиаторов "
                    "в спецификации. Например, если в проекте 5 одинаковых "
                    "радиаторов по 10 секций — введите 5 в строке «10 секций». "
                    "Поле активно только для тех строк, количество которых "
                    "вы указали.",
                )
            elif col == 2:
                self._bind_tooltip(
                    lbl,
                    "Мощность одной секции, Вт (при Δt = 70 °С).",
                )
            elif col == 7:
                self._bind_tooltip(
                    lbl,
                    "Подобранный панельный радиатор LaggarTT. "
                    "Отображается наименование, включая тип, высоту и длину. "
                    "Если подобранный радиатор вне допуска по отклонению, "
                    "строка подсвечена красным, а вместо наименования "
                    "показан знак «*» — наведите курсор, чтобы увидеть "
                    "ближайших кандидатов.",
                )

        tk.Frame(table, bg=self.DIVIDER, width=self._s(2)).grid(
            row=0, column=6, sticky="ns",
            padx=(self._s(1), self._s(1)),
        )

        table.rowconfigure(0, minsize=self._s(BASE_HEADER_HEIGHT))

        vcmd = (self._dialog.register(self._validate_qty_input), '%P')

        for i, sections in enumerate(
            range(MIN_SECTIONS, MAX_SECTIONS + 1), start=1
        ):
            table.rowconfigure(i, minsize=self._s(BASE_ROW_HEIGHT))

            tk.Label(
                table, text=str(sections),
                bg=self.BG_SRC_EMPTY, fg="#555",
                font=bold_small, relief="ridge", borderwidth=1,
            ).grid(row=i, column=0, sticky="nsew")

            entry = tk.Entry(
                table, justify="center",
                bg=self.BG_INPUT_EMPTY,
                fg=self.FG_ACCENT,
                font=bold_small, relief="ridge", borderwidth=1,
                validate="key",
                validatecommand=vcmd,
            )
            entry.grid(row=i, column=1, sticky="nsew")
            entry.bind("<FocusIn>",
                       lambda ev, s=sections: self._on_qty_focus_in(s))
            entry.bind("<FocusOut>",
                       lambda ev, s=sections: self._on_qty_focus_out(s))
            entry.bind("<Return>",
                       lambda ev, s=sections: self._on_qty_return(s))
            entry.bind("<KeyRelease>",
                       lambda ev, s=sections: self._on_qty_key_release(s))
            entry.bind("<Up>",
                       lambda ev, s=sections: self._focus_qty_prev(s))
            entry.bind("<Down>",
                       lambda ev, s=sections: self._focus_qty_next(s))

            lbl_src_power = tk.Label(
                table, text="", bg=self.BG_SRC_EMPTY, fg="#333",
                font=default_font, relief="ridge", borderwidth=1,
            )
            lbl_src_power.grid(row=i, column=2, sticky="nsew")

            lbl_src_total = tk.Label(
                table, text="", bg=self.BG_SRC_EMPTY, fg="#333",
                font=default_font, relief="ridge", borderwidth=1,
            )
            lbl_src_total.grid(row=i, column=3, sticky="nsew")

            lbl_src_price = tk.Label(
                table, text="", bg=self.BG_SRC_EMPTY, fg="#333",
                font=default_font, relief="ridge", borderwidth=1,
            )
            lbl_src_price.grid(row=i, column=4, sticky="nsew")

            lbl_src_sum = tk.Label(
                table, text="", bg=self.BG_SRC_EMPTY, fg="#333",
                font=default_font, relief="ridge", borderwidth=1,
            )
            lbl_src_sum.grid(row=i, column=5, sticky="nsew")

            div = tk.Frame(table, bg=self.BG)
            div.grid(row=i, column=6, sticky="nsew")
            tk.Frame(div, bg=self.DIVIDER, width=1).pack(side="left", fill="y")
            tk.Frame(div, bg=self.BG, width=2).pack(side="left", fill="y")
            tk.Frame(div, bg=self.DIVIDER, width=1).pack(side="left", fill="y")

            lbl_pnl_name = tk.Label(
                table, text="", bg=self.BG_PNL_EMPTY, fg=self.FG_EMPTY,
                font=default_font, relief="ridge", borderwidth=1,
                anchor="w", padx=self._s(4),
            )
            lbl_pnl_name.grid(row=i, column=7, sticky="nsew")

            lbl_pnl_power = tk.Label(
                table, text="", bg=self.BG_PNL_EMPTY, fg=self.FG_EMPTY,
                font=default_font, relief="ridge", borderwidth=1,
            )
            lbl_pnl_power.grid(row=i, column=8, sticky="nsew")

            lbl_pnl_total = tk.Label(
                table, text="", bg=self.BG_PNL_EMPTY, fg=self.FG_EMPTY,
                font=default_font, relief="ridge", borderwidth=1,
            )
            lbl_pnl_total.grid(row=i, column=9, sticky="nsew")

            lbl_pnl_dev = tk.Label(
                table, text="", bg=self.BG_PNL_EMPTY, fg=self.FG_EMPTY,
                font=default_font, relief="ridge", borderwidth=1,
            )
            lbl_pnl_dev.grid(row=i, column=10, sticky="nsew")

            lbl_pnl_qty = tk.Label(
                table, text="", bg=self.BG_PNL_EMPTY, fg=self.FG_EMPTY,
                font=default_font, relief="ridge", borderwidth=1,
            )
            lbl_pnl_qty.grid(row=i, column=11, sticky="nsew")

            lbl_pnl_price = tk.Label(
                table, text="", bg=self.BG_PNL_EMPTY, fg=self.FG_EMPTY,
                font=default_font, relief="ridge", borderwidth=1,
            )
            lbl_pnl_price.grid(row=i, column=12, sticky="nsew")

            lbl_pnl_sum = tk.Label(
                table, text="", bg=self.BG_PNL_EMPTY, fg=self.FG_EMPTY,
                font=default_font, relief="ridge", borderwidth=1,
            )
            lbl_pnl_sum.grid(row=i, column=13, sticky="nsew")

            for h in self.HEIGHTS:
                var = tk.StringVar(value="")
                self._qty_vars[h][sections] = var
                self._qty_entries[h][sections] = entry
                self._row_widgets[h][sections] = {
                    "src_power": lbl_src_power,
                    "src_total": lbl_src_total,
                    "src_price": lbl_src_price,
                    "src_sum": lbl_src_sum,
                    "pnl_name": lbl_pnl_name,
                    "pnl_power": lbl_pnl_power,
                    "pnl_total": lbl_pnl_total,
                    "pnl_dev": lbl_pnl_dev,
                    "pnl_qty": lbl_pnl_qty,
                    "pnl_price": lbl_pnl_price,
                    "pnl_sum": lbl_pnl_sum,
                }

            for w in (lbl_pnl_name, lbl_pnl_power, lbl_pnl_total,
                      lbl_pnl_dev, lbl_pnl_qty, lbl_pnl_price, lbl_pnl_sum):
                w.bind("<Enter>",
                       lambda ev, s=sections: self._on_row_enter(s))
                w.bind("<Leave>", lambda ev: self._hide_row_tooltip())
                w.bind("<Double-Button-1>",
                       lambda ev, s=sections: self._on_cell_double_click(s))

        total_row = MAX_SECTIONS - MIN_SECTIONS + 2
        table.rowconfigure(total_row, minsize=self._s(BASE_TOTAL_HEIGHT))

        tk.Label(
            table, text="ИТОГО", bg=self.BG_TOTAL_SRC, fg=self.FG_SRC,
            font=bold_small, relief="ridge", borderwidth=1,
        ).grid(row=total_row, column=0, sticky="nsew")

        self._total_src_qty_lbl = tk.Label(
            table, text="0", bg=self.BG_TOTAL_SRC, fg=self.FG_SRC,
            font=bold_small, relief="ridge", borderwidth=1,
        )
        self._total_src_qty_lbl.grid(row=total_row, column=1, sticky="nsew")

        tk.Label(
            table, text="—", bg=self.BG_TOTAL_SRC, fg=self.FG_SRC,
            font=bold_small, relief="ridge", borderwidth=1,
        ).grid(row=total_row, column=2, sticky="nsew")

        self._total_src_power_lbl = tk.Label(
            table, text="0", bg=self.BG_TOTAL_SRC, fg=self.FG_SRC,
            font=bold_small, relief="ridge", borderwidth=1,
        )
        self._total_src_power_lbl.grid(row=total_row, column=3, sticky="nsew")

        tk.Label(
            table, text="—", bg=self.BG_TOTAL_SRC, fg=self.FG_SRC,
            font=bold_small, relief="ridge", borderwidth=1,
        ).grid(row=total_row, column=4, sticky="nsew")

        self._total_src_sum_lbl = tk.Label(
            table, text="0", bg=self.BG_TOTAL_SRC, fg=self.FG_SRC,
            font=bold_small, relief="ridge", borderwidth=1,
        )
        self._total_src_sum_lbl.grid(row=total_row, column=5, sticky="nsew")

        div_total = tk.Frame(table, bg=self.BG_TOTAL_SRC)
        div_total.grid(row=total_row, column=6, sticky="nsew")
        tk.Frame(div_total, bg=self.DIVIDER, width=self._s(2)).pack(
            fill="both", expand=True
        )

        tk.Label(
            table, text="ИТОГО", bg=self.BG_TOTAL_PNL, fg=self.FG_PNL,
            font=bold_small, relief="ridge", borderwidth=1,
        ).grid(row=total_row, column=7, sticky="nsew")

        tk.Label(
            table, text="—", bg=self.BG_TOTAL_PNL, fg=self.FG_PNL,
            font=bold_small, relief="ridge", borderwidth=1,
        ).grid(row=total_row, column=8, sticky="nsew")

        self._total_pnl_power_lbl = tk.Label(
            table, text="0", bg=self.BG_TOTAL_PNL, fg=self.FG_PNL,
            font=bold_small, relief="ridge", borderwidth=1,
        )
        self._total_pnl_power_lbl.grid(row=total_row, column=9, sticky="nsew")

        self._total_pnl_dev_lbl = tk.Label(
            table, text="—", bg=self.BG_TOTAL_PNL, fg=self.FG_PNL,
            font=bold_small, relief="ridge", borderwidth=1,
        )
        self._total_pnl_dev_lbl.grid(row=total_row, column=10, sticky="nsew")

        self._total_pnl_qty_lbl = tk.Label(
            table, text="0", bg=self.BG_TOTAL_PNL, fg=self.FG_PNL,
            font=bold_small, relief="ridge", borderwidth=1,
        )
        self._total_pnl_qty_lbl.grid(row=total_row, column=11, sticky="nsew")

        tk.Label(
            table, text="—", bg=self.BG_TOTAL_PNL, fg=self.FG_PNL,
            font=bold_small, relief="ridge", borderwidth=1,
        ).grid(row=total_row, column=12, sticky="nsew")

        self._total_pnl_sum_lbl = tk.Label(
            table, text="0", bg=self.BG_TOTAL_PNL, fg=self.FG_PNL,
            font=bold_small, relief="ridge", borderwidth=1,
        )
        self._total_pnl_sum_lbl.grid(row=total_row, column=13, sticky="nsew")

    # ==================================================================
    # Подсказки (tooltip) для полей окна «Замена секционных»
    # ==================================================================
    def _bind_tooltip(self, widget: tk.Widget, text: str) -> None:
        """
        Привязывает всплывающую подсказку к виджету.
        Показ — через 500 мс после наведения, если чекбокс «Подсказки» включён.
        """
        def on_enter(event, w=widget, t=text):
            self._schedule_tooltip(w, t)

        def on_leave(event):
            self._cancel_tooltip()

        widget.bind("<Enter>", on_enter, add="+")
        widget.bind("<Leave>", on_leave, add="+")
        # Также скрываем подсказку при клике — чтобы не висела
        widget.bind("<Button-1>", lambda e: self._cancel_tooltip(), add="+")

    def _schedule_tooltip(self, widget: tk.Widget, text: str) -> None:
        """Планирует показ подсказки через 500 мс."""
        # Отменяем предыдущий таймер, если был
        if self._tooltip_after_id is not None:
            try:
                if self._dialog and self._dialog.winfo_exists():
                    self._dialog.after_cancel(self._tooltip_after_id)
            except Exception:
                pass
            self._tooltip_after_id = None

        # Проверяем, включён ли чекбокс «Подсказки»
        try:
            if not self._show_tooltips_var.get():
                return
        except Exception:
            return

        if self._dialog and self._dialog.winfo_exists():
            self._tooltip_after_id = self._dialog.after(
                500, lambda: self._show_tooltip_now(widget, text)
            )

    def _show_tooltip_now(self, widget: tk.Widget, text: str) -> None:
        """Создаёт и показывает окно подсказки рядом с курсором."""
        self._tooltip_after_id = None

        # Ещё раз проверяем чекбокс — вдруг его сняли за эти 500 мс
        try:
            if not self._show_tooltips_var.get():
                return
        except Exception:
            return

        # Закрываем старую подсказку, если есть
        self._hide_tooltip_immediate()

        try:
            if not widget.winfo_exists():
                return
        except tk.TclError:
            return

        # Создаём окно подсказки
        try:
            self._tooltip_window = tk.Toplevel(self._dialog)
            self._tooltip_window.wm_overrideredirect(True)

            # Позиция — рядом с курсором мыши
            x = self._dialog.winfo_pointerx() + self._s(15)
            y = self._dialog.winfo_pointery() + self._s(15)

            # Учитываем границы экрана
            screen_w = self._tooltip_window.winfo_screenwidth()
            screen_h = self._tooltip_window.winfo_screenheight()

            font = self.font_manager.get_default_font()

            frame = tk.Frame(
                self._tooltip_window,
                bg="#ffffe0",
                relief="solid",
                borderwidth=1,
                padx=self._s(8),
                pady=self._s(6),
            )
            frame.pack()

            tk.Label(
                frame,
                text=text,
                font=font,
                bg="#ffffe0",
                fg="#000000",
                justify="left",
                anchor="w",
                wraplength=self._s(360),
            ).pack()

            self._tooltip_window.update_idletasks()

            tw = self._tooltip_window.winfo_reqwidth()
            th = self._tooltip_window.winfo_reqheight()

            if x + tw > screen_w - 10:
                x = screen_w - tw - 10
            if y + th > screen_h - 60:  # 60 — запас на панель задач
                y = y - th - self._s(30)
            if x < 10:
                x = 10
            if y < 10:
                y = 10

            self._tooltip_window.wm_geometry(f"+{x}+{y}")
            self._tooltip_window.deiconify()

        except Exception as e:
            logger.debug(f"Ошибка показа подсказки: {e}")
            self._hide_tooltip_immediate()

    def _cancel_tooltip(self, event=None) -> None:
        """Отменяет запланированный показ и скрывает уже показанную подсказку."""
        if self._tooltip_after_id is not None:
            try:
                if self._dialog and self._dialog.winfo_exists():
                    self._dialog.after_cancel(self._tooltip_after_id)
            except Exception:
                pass
            self._tooltip_after_id = None

        self._hide_tooltip_immediate()

    def _hide_tooltip_immediate(self) -> None:
        """Скрывает окно подсказки (если открыто)."""
        if self._tooltip_window is not None:
            try:
                if self._tooltip_window.winfo_exists():
                    self._tooltip_window.destroy()
            except Exception:
                pass
            self._tooltip_window = None

    # ------------------------------------------------------------------
    # Нижняя панель
    # ------------------------------------------------------------------
    def _build_bottom_bar(self, parent: tk.Frame) -> None:
        bar = tk.Frame(parent, bg=self.BG)
        bar.grid(row=1, column=0, sticky="ew",
                 padx=self._s(4), pady=(self._s(2), self._s(4)))

        # Распорка слева — занимает всё свободное место,
        # чтобы весь блок справа прижался к правому краю.
        tk.Frame(bar, bg=self.BG).pack(side="left", fill="x", expand=True)

        default_font = self.font_manager.get_default_font()
        main_window = self.app.main_window

        # Сначала пакуем кнопку «Закрыть» — она окажется самой правой.
        ttk.Button(
            bar, text="Закрыть",
            command=self._close,
            width=15,
        ).pack(side="right", padx=(self._s(10), 0))

        # Затем пакуем блок со скидками — он окажется левее кнопки «Закрыть».
        discount_frame = tk.Frame(bar, bg=self.BG)
        discount_frame.pack(side="right")

        # Скидка на радиаторы
        tk.Label(
            discount_frame,
            text="Скидка на радиаторы, %:",
            font=default_font,
            bg=self.BG,
            fg="#444141",
        ).pack(side="left", padx=(0, self._s(2)))

        self._radiator_discount_entry = tk.Entry(
            discount_frame,
            textvariable=main_window.radiator_discount_var,
            width=5,
            justify="center",
            font=default_font,
            validate="key",
            validatecommand=(
                self._dialog.register(self._validate_discount), '%P'
            ),
        )
        self._radiator_discount_entry.pack(side="left", padx=self._s(2))

        # Скидка на кронштейны
        tk.Label(
            discount_frame,
            text="кронштейны, %:",
            font=default_font,
            bg=self.BG,
            fg="#444141",
        ).pack(side="left", padx=(self._s(10), self._s(2)))

        self._bracket_discount_entry = tk.Entry(
            discount_frame,
            textvariable=main_window.bracket_discount_var,
            width=5,
            justify="center",
            font=default_font,
            validate="key",
            validatecommand=(
                self._dialog.register(self._validate_discount), '%P'
            ),
        )
        self._bracket_discount_entry.pack(side="left", padx=self._s(2))

        # ================================================================
        # Чекбокс «Подсказки» — левее блока скидок
        # ================================================================
        self._tooltips_checkbox = ttk.Checkbutton(
            bar,
            text="Подсказки",
            variable=self._show_tooltips_var,
            command=self._on_tooltips_toggled,
        )
        self._tooltips_checkbox.pack(side="right", padx=(0, self._s(20)))

        # ================================================================
        # Подписка на изменения скидок — для мгновенного пересчёта цен.
        # ================================================================
        self._radiator_discount_trace = main_window.radiator_discount_var.trace_add(
            "write", lambda *a: self._on_discount_changed_local()
        )
        self._bracket_discount_trace = main_window.bracket_discount_var.trace_add(
            "write", lambda *a: self._on_discount_changed_local()
        )
        # ================================================================

        # Подсказка на чекбокс «Подсказки» (сама себя объясняет)
        self._bind_tooltip(
            self._tooltips_checkbox,
            "Включить или отключить всплывающие подсказки для полей "
            "этого окна. Положение чекбокса сохраняется между запусками "
            "программы.",
        )

    def _on_tooltips_toggled(self) -> None:
        """Сохраняет состояние чекбокса «Подсказки» и скрывает текущую подсказку."""
        try:
            from nextt.config import config as _config
            _config.set(
                "section_to_panel_show_tooltips",
                bool(self._show_tooltips_var.get())
            )
        except Exception as e:
            logger.debug(f"Не удалось сохранить состояние подсказок: {e}")

        # Если чекбокс сняли — сразу прячем уже показанную подсказку
        if not self._show_tooltips_var.get():
            self._cancel_tooltip()

    # ==================================================================
    # Обновление подсветки вкладок
    # ==================================================================
    def _height_has_data(self, height: int) -> bool:
        for s in range(MIN_SECTIONS, MAX_SECTIONS + 1):
            qty = self._parse_int(self._qty_vars[height][s].get())
            if qty > 0:
                return True
        return False

    def _update_height_tabs_visual(self) -> None:
        for h, lbl in self._height_buttons.items():
            try:
                if h == self._current_height:
                    lbl.config(bg=self.TAB_ACTIVE_BG, fg=self.TAB_ACTIVE_FG)
                elif self._height_has_data(h):
                    lbl.config(bg=self.TAB_FILLED_BG, fg=self.TAB_FILLED_FG)
                else:
                    lbl.config(bg=self.TAB_EMPTY_BG, fg=self.TAB_EMPTY_FG)
            except tk.TclError:
                pass

    # ==================================================================
    # Фон полей ввода количества — весь столбец
    # ==================================================================
    def _update_qty_entries_bg(self) -> None:
        """
        Обновляет фон всех полей ввода активной высоты.

        Если хотя бы одно поле заполнено — все поля голубые.
        Если ни одно — все бледно-красные.
        """
        h = self._current_height
        has_any = False
        for s in range(MIN_SECTIONS, MAX_SECTIONS + 1):
            if self._parse_int(self._qty_vars[h][s].get()) > 0:
                has_any = True
                break

        color = self.BG_INPUT if has_any else self.BG_INPUT_EMPTY
        for s in range(MIN_SECTIONS, MAX_SECTIONS + 1):
            try:
                self._qty_entries[h][s].config(bg=color)
            except tk.TclError:
                pass

    # ==================================================================
    # Тултип
    # ==================================================================
    def _on_row_enter(self, sections: int) -> None:
        rad = self._selected[self._current_height].get(sections)
        if rad is None:
            return
        if getattr(rad, "in_tolerance", True):
            return
        candidates = getattr(rad, "all_candidates", []) or []
        if not candidates:
            return
        self._hide_row_tooltip()
        self._show_row_tooltip(sections, rad, candidates)

    def _show_row_tooltip(self, sections, rad, candidates) -> None:
        try:
            dev_pct = float(self._deviation_var.get().replace(",", "."))
        except (ValueError, TypeError):
            dev_pct = 5.0

        sorted_c = sorted(candidates, key=lambda c: abs(c["deviation"]))
        in_tol = [
            c for c in sorted_c
            if -abs(dev_pct) <= c["deviation"] <= abs(dev_pct)
        ]
        short_list = in_tol[:3] if in_tol else sorted_c[:3]

        best_in_list = any(
            c["type"] == rad.radiator_type and c["length"] == rad.length
            for c in short_list
        )
        if not best_in_list:
            best_c = next(
                (c for c in candidates
                 if c["type"] == rad.radiator_type and c["length"] == rad.length),
                None,
            )
            if best_c is not None:
                short_list.append(best_c)

        self._row_tooltip = tk.Toplevel(self._dialog)
        self._row_tooltip.wm_overrideredirect(True)

        frame = tk.Frame(
            self._row_tooltip, bg="#ffffe0",
            relief="solid", borderwidth=1,
            padx=self._s(10), pady=self._s(8),
        )
        frame.pack()

        if in_tol:
            header = f"Ближайшие (допуск ±{dev_pct}%):"
        else:
            header = f"Ближайшие (в допуск ±{dev_pct}% никто не попал):"

        tk.Label(
            frame, text=header, bg="#ffffe0",
            font=self.font_manager.get_bold_font(9), anchor="w",
        ).pack(anchor="w")

        tk.Frame(frame, height=1, bg="#cccccc").pack(
            fill="x", pady=self._s(4))

        # Шрифт подсказки — как в таблице
        table_font = self.font_manager.get_default_font()

        # Префикс подключения — общий для всего окна
        conn_prefix = "VK" if self._conn_mode_var.get() == "VK" else "K"

        for c in short_list:
            in_t = -abs(dev_pct) <= c["deviation"] <= abs(dev_pct)
            is_best = (c["type"] == rad.radiator_type and c["length"] == rad.length)

            if is_best:
                color = "#a02626"
                prefix = "★ "
            elif in_t:
                color = "#2c5c2c"
                prefix = "• "
            else:
                color = "#000000"
                prefix = "• "

            name_text = (
                f"{prefix}{conn_prefix}-Profil "
                f"{c['type']}/{rad.height}/{c['length']}"
            )
            details_text = (
                f"    {int(round(c['power']))} Вт    "
                f"{c['deviation']:+7.2f}%".replace(".", ",")
            )

            tk.Label(
                frame, text=name_text + details_text, bg="#ffffe0", fg=color,
                font=table_font, anchor="w", justify="left",
                wraplength=self._s(900),
            ).pack(anchor="w", pady=(0, self._s(2)))

        x = self._dialog.winfo_pointerx() + self._s(15)
        y = self._dialog.winfo_pointery() + self._s(15)

        # Проверка границ экрана
        self._row_tooltip.update_idletasks()
        tw = self._row_tooltip.winfo_reqwidth()
        th = self._row_tooltip.winfo_reqheight()
        screen_w = self._row_tooltip.winfo_screenwidth()
        screen_h = self._row_tooltip.winfo_screenheight()

        if x + tw > screen_w - 10:
            x = screen_w - tw - 10
        if y + th > screen_h - 60:
            y = y - th - self._s(30)
        if x < 10:
            x = 10
        if y < 10:
            y = 10

        self._row_tooltip.wm_geometry(f"+{x}+{y}")

    def _hide_row_tooltip(self, event=None) -> None:
        if self._row_tooltip:
            try:
                self._row_tooltip.destroy()
            except Exception:
                pass
            self._row_tooltip = None

    # ==================================================================
    # Popup
    # ==================================================================
    def _on_cell_double_click(self, sections: int) -> None:
        self._hide_row_tooltip()
        h = self._current_height
        rad = self._selected[h].get(sections)
        if rad is None:
            return

        # Пересобираем полный список кандидатов заново — чтобы список
        # открывался и при повторном выборе (когда rad был выбран вручную
        # и all_candidates пуст).
        candidates = self._collect_candidates_for_row(sections, h)
        if not candidates:
            return

        widgets = self._row_widgets[h][sections]
        anchor = widgets["pnl_name"]
        self._show_candidate_popup(h, sections, anchor, rad, candidates)

    def _collect_candidates_for_row(self, sections: int, height: int):
        """
        Пересобирает список кандидатов для указанной строки — так же,
        как это делается при автоматическом подборе. Нужно для того,
        чтобы повторный двойной клик снова открывал список кандидатов,
        даже если предыдущий выбор был сделан вручную.
        """
        try:
            power_per_section = float(
                self._power_vars[height].get().replace(",", "."))
        except (ValueError, TypeError):
            power_per_section = 0.0

        if power_per_section <= 0:
            return []

        try:
            deviation_pct = float(
                self._deviation_var.get().replace(",", "."))
        except (ValueError, TypeError):
            deviation_pct = 5.0

        conn_mode = self._conn_mode_var.get()
        mode = self._mode_var.get()
        panel_height = HEIGHT_TO_PANEL.get(height, height)

        if conn_mode == "VK":
            conn_str = "VK-правое"
        else:
            conn_str = "K-боковое"

        try:
            if mode == MODE_DIMENSION:
                selector = self._selector_dimension
                source_length = sections * 100
                return selector._collect_candidates(
                    height=panel_height,
                    length=source_length,
                    connection=conn_str,
                    Q_target=power_per_section * sections,
                )
            else:
                selector = self._selector_power
                L_max = sections * 100
                allowed_lengths = list(range(400, L_max + 1, 100))
                return selector._collect_candidates(
                    height=panel_height,
                    allowed_lengths=allowed_lengths,
                    connection=conn_str,
                    Q_target=power_per_section * sections,
                )
        except Exception as e:
            logger.debug(f"Ошибка пересбора кандидатов: {e}")
            return []

    def _show_candidate_popup(self, height, sections, anchor_widget,
                              rad, candidates) -> None:
        self._hide_candidate_popup()

        try:
            dev_pct = float(self._deviation_var.get().replace(",", "."))
        except (ValueError, TypeError):
            dev_pct = 5.0

        in_tol = sorted(
            [c for c in candidates
             if -abs(dev_pct) <= c["deviation"] <= abs(dev_pct)],
            key=lambda c: abs(c["deviation"]),
        )
        out_tol = sorted(
            [c for c in candidates
             if not (-abs(dev_pct) <= c["deviation"] <= abs(dev_pct))],
            key=lambda c: abs(c["deviation"]),
        )
        ordered = in_tol + out_tol

        self._popup_candidates = ordered
        self._popup_height = height
        self._popup_sections = sections

        self._popup = tk.Toplevel(self._dialog)
        self._popup.wm_overrideredirect(True)

        frame = tk.Frame(self._popup, bg="#ffffff",
                         relief="solid", borderwidth=1)
        frame.pack()

        header = tk.Frame(frame, bg="#ffffe0",
                          padx=self._s(8), pady=self._s(4))
        header.pack(fill="x")
        tk.Label(
            header,
            text=f"Выбор аналога для {sections} секций (допуск ±{dev_pct}%) — кликните по нужной строке",
            bg="#ffffe0", font=self.font_manager.get_bold_font(9),
            anchor="w",
        ).pack(anchor="w")

        list_frame = tk.Frame(frame, bg="#ffffff")
        list_frame.pack(fill="both", expand=True,
                        padx=self._s(2), pady=self._s(2))

        table_font = self.font_manager.get_default_font()

        self._popup_listbox = tk.Listbox(
            list_frame,
            height=POPUP_VISIBLE_ROWS,
            width=75,
            font=table_font,
            activestyle="none",
            selectmode="single",
            exportselection=False,
        )
        self._popup_listbox.pack(side="left", fill="both", expand=True)

        vsb = ttk.Scrollbar(list_frame, orient="vertical",
                            command=self._popup_listbox.yview)
        vsb.pack(side="right", fill="y")
        self._popup_listbox.configure(yscrollcommand=vsb.set)

        conn_prefix = "VK" if self._conn_mode_var.get() == "VK" else "K"
        manual = self._manual_choice.get((height, sections))

        current_index = None
        for i, c in enumerate(ordered):
            in_t = -abs(dev_pct) <= c["deviation"] <= abs(dev_pct)

            is_current = (
                manual is not None
                and c["article"] == manual.get("article")
                and c["length"] == manual.get("length")
            )
            if manual is None:
                is_current = (
                    c["type"] == rad.radiator_type
                    and c["length"] == rad.length
                )

            name_text = (
                f"{conn_prefix}-Profil "
                f"{c['type']}/{rad.height}/{c['length']}"
            )
            details_text = (
                f"    {int(round(c['power']))} Вт    "
                f"{c['deviation']:+7.2f}%".replace(".", ",")
            )

            if is_current:
                text = f"★ {name_text}{details_text}  ← выбран"
                current_index = i
            elif in_t:
                text = f"• {name_text}{details_text}  (в допуске)"
            else:
                text = f"• {name_text}{details_text}"

            self._popup_listbox.insert("end", text)

            if in_t:
                self._popup_listbox.itemconfig(i, bg="#eef7ee")
            else:
                self._popup_listbox.itemconfig(i, bg="#f8d7d7")
            if is_current:
                self._popup_listbox.itemconfig(i, bg="#ffeaa7")

        if current_index is not None:
            self._popup_listbox.selection_clear(0, "end")
            self._popup_listbox.selection_set(current_index)
            self._popup_listbox.activate(current_index)
            self._popup_listbox.see(current_index)

        # ================================================================
        # ТОЛЬКО МЫШЬ: одинарный клик по элементу = выбор
        # ================================================================
        # Отпускание левой кнопки мыши — самый надёжный момент для
        # обработки выбора. Привязываемся на Listbox.
        self._popup_listbox.bind("<ButtonRelease-1>", self._on_popup_mouse_release)

        # Escape — на всякий случай (закрыть без выбора)
        self._popup.bind("<Escape>", lambda e: self._hide_candidate_popup())

        self._popup.update_idletasks()
        x = anchor_widget.winfo_rootx()
        y = anchor_widget.winfo_rooty() + anchor_widget.winfo_height()
        self._popup.wm_geometry(f"+{x}+{y}")

        self._popup.after(100, self._setup_global_click_handler)

    def _on_popup_mouse_release(self, event=None) -> str:
        """
        Обрабатывает клик мышью по элементу списка.
        Определяет строку по координате клика (nearest), затем применяет.
        """
        if not self._popup_listbox or not self._popup_listbox.winfo_exists():
            return "break"

        if event is not None:
            try:
                idx = self._popup_listbox.nearest(event.y)
            except Exception:
                idx = None
        else:
            try:
                sel = self._popup_listbox.curselection()
                idx = sel[0] if sel else None
            except Exception:
                idx = None

        if idx is None or idx < 0 or idx >= len(self._popup_candidates):
            return "break"

        candidate = self._popup_candidates[idx]
        self._apply_manual_choice(
            self._popup_height, self._popup_sections, candidate
        )
        self._hide_candidate_popup()
        return "break"

    def _setup_global_click_handler(self) -> None:
        if not self._popup or not self._popup.winfo_exists():
            return
        try:
            self._dialog.bind_all("<Button-1>",
                                  self._on_global_click, add="+")
        except Exception:
            pass

    def _on_global_click(self, event) -> None:
        if not self._popup or not self._popup.winfo_exists():
            return

        # Клик внутри Listbox — не закрываем popup.
        # Listbox сам обработает клик через <ButtonRelease-1>.
        try:
            if self._popup_listbox and self._popup_listbox.winfo_exists():
                widget_at = self._popup_listbox.winfo_containing(
                    event.x_root, event.y_root
                )
                if widget_at is self._popup_listbox:
                    return
        except Exception:
            pass

        # Клик в области popup — тоже не закрываем
        px = self._popup.winfo_rootx()
        py = self._popup.winfo_rooty()
        pw = self._popup.winfo_width()
        ph = self._popup.winfo_height()
        if px <= event.x_root <= px + pw and py <= event.y_root <= py + ph:
            return

        # Клик вне popup — закрываем
        self._hide_candidate_popup()

    def _hide_candidate_popup(self, event=None) -> None:
        try:
            self._dialog.unbind_all("<Button-1>")
        except Exception:
            pass
        if self._popup:
            try:
                self._popup.destroy()
            except Exception:
                pass
            self._popup = None
            self._popup_listbox = None
            self._popup_candidates = []

    def _apply_manual_choice(self, height, sections, candidate) -> None:
        self._manual_choice[(height, sections)] = dict(candidate)
        self._on_qty_changed(sections, height)

    # ==================================================================
    # Переключение высоты
    # ==================================================================
    def _switch_height(self, height: int) -> None:
        if height not in self.HEIGHTS:
            return
        self._current_height = height

        for sections in range(MIN_SECTIONS, MAX_SECTIONS + 1):
            entry = self._qty_entries[height][sections]
            var = self._qty_vars[height][sections]
            entry.config(textvariable=var)
            var.set(var.get())

        if self._power_entry is not None:
            self._power_entry.config(textvariable=self._power_vars[height])
            self._power_vars[height].set(self._power_vars[height].get())

        if self._price_entry is not None:
            self._price_entry.config(textvariable=self._price_vars[height])
            self._price_vars[height].set(self._price_vars[height].get())

        self._hide_row_tooltip()
        self._hide_candidate_popup()
        self._update_height_tabs_visual()
        self._refresh_table_for_height()
        self._update_qty_entries_bg()
        self._update_total_row()

        if self._dialog and self._dialog.winfo_exists():
            self._dialog.update_idletasks()

    def _refresh_table_for_height(self) -> None:
        h = self._current_height
        try:
            power_per_section = float(
                self._power_vars[h].get().replace(",", "."))
        except (ValueError, TypeError):
            power_per_section = 0.0

        try:
            price_per_section = float(
                self._price_vars[h].get().replace(",", "."))
        except (ValueError, TypeError):
            price_per_section = 0.0

        # ================================================================
        # Скидка на радиаторы применяется ТОЛЬКО к панельным радиаторам.
        # Секционные считаются по цене секции без скидки.
        # Берём из общей переменной главного окна.
        # ================================================================
        try:
            rad_disc = float(
                self.app.main_window.radiator_discount_var.get().replace(",", ".")
                or 0
            )
        except (ValueError, TypeError):
            rad_disc = 0.0
        rad_disc = max(0.0, min(100.0, rad_disc))
        discount_factor = 1.0 - rad_disc / 100.0

        has_price = price_per_section > 0

        for sections in range(MIN_SECTIONS, MAX_SECTIONS + 1):
            widgets = self._row_widgets[h][sections]
            qty = self._parse_int(self._qty_vars[h][sections].get())

            power_row = power_per_section * sections
            total_power = power_row * qty

            if qty > 0:
                widgets["src_power"].config(
                    text=str(int(round(power_row))),
                    bg=self.BG_SRC_FILLED, fg=self.FG_SRC)
                widgets["src_total"].config(
                    text=str(int(round(total_power))),
                    bg=self.BG_SRC_FILLED, fg=self.FG_SRC)

                if has_price:
                    # Секционный радиатор — БЕЗ скидки
                    price_radiator = price_per_section * sections
                    sum_radiator = price_radiator * qty
                    widgets["src_price"].config(
                        text=self._fmt_money(price_radiator),
                        bg=self.BG_SRC_FILLED, fg=self.FG_SRC)
                    widgets["src_sum"].config(
                        text=self._fmt_money(sum_radiator),
                        bg=self.BG_SRC_FILLED, fg=self.FG_SRC)
                else:
                    widgets["src_price"].config(
                        text="—", bg=self.BG_SRC_FILLED, fg=self.FG_SRC)
                    widgets["src_sum"].config(
                        text="—", bg=self.BG_SRC_FILLED, fg=self.FG_SRC)
            else:
                widgets["src_power"].config(text="", bg=self.BG_SRC_EMPTY, fg="#333")
                widgets["src_total"].config(text="", bg=self.BG_SRC_EMPTY, fg="#333")
                widgets["src_price"].config(text="", bg=self.BG_SRC_EMPTY, fg="#333")
                widgets["src_sum"].config(text="", bg=self.BG_SRC_EMPTY, fg="#333")

            rad = self._selected[h].get(sections)
            if rad is None:
                for key in ("pnl_name", "pnl_power", "pnl_total",
                            "pnl_dev", "pnl_qty", "pnl_price", "pnl_sum"):
                    widgets[key].config(
                        text="", bg=self.BG_PNL_EMPTY, fg=self.FG_EMPTY)
            else:
                is_manual = (h, sections) in self._manual_choice
                prefix = "* " if is_manual else ""
                name_text = (
                    f"{prefix}{rad.connection.split('-')[0]}-Profil "
                    f"{rad.radiator_type}/{rad.height}/{rad.length}"
                )

                if is_manual:
                    bg = self.BG_PNL_MANUAL
                elif rad.in_tolerance:
                    bg = self.BG_PNL_FILLED
                else:
                    bg = self.BG_PNL_WARNING

                # Панельный радиатор — СО скидкой
                price_pnl_base = self._get_panel_price(rad.article)
                if price_pnl_base is not None:
                    price_pnl = price_pnl_base * discount_factor
                    price_text = self._fmt_money(price_pnl)
                    sum_text = self._fmt_money(price_pnl * qty)
                else:
                    price_text = "—"
                    sum_text = "—"

                widgets["pnl_name"].config(text=name_text, bg=bg, fg=self.FG_PNL)
                widgets["pnl_power"].config(
                    text=str(int(round(rad.power))), bg=bg, fg=self.FG_PNL)
                widgets["pnl_total"].config(
                    text=str(int(round(rad.power_total_panel))),
                    bg=bg, fg=self.FG_PNL)
                widgets["pnl_dev"].config(
                    text=f"{rad.deviation_pct:+.2f}".replace(".", ","),
                    bg=bg,
                    fg=(self.FG_PNL if rad.in_tolerance else self.FG_NEGATIVE))
                widgets["pnl_qty"].config(text=str(qty), bg=bg, fg=self.FG_PNL)
                widgets["pnl_price"].config(text=price_text, bg=bg, fg=self.FG_PNL)
                widgets["pnl_sum"].config(text=sum_text, bg=bg, fg=self.FG_PNL)

        self._update_qty_entries_bg()
        self._update_total_row()

    # ==================================================================
    # Итоги
    # ==================================================================
    def _update_total_row(self) -> None:
        # ================================================================
        # Скидка на радиаторы применяется ТОЛЬКО к панельным радиаторам.
        # Секционные считаются по цене секции без скидки.
        # ================================================================
        try:
            rad_disc = float(
                self.app.main_window.radiator_discount_var.get().replace(",", ".")
                or 0
            )
        except (ValueError, TypeError):
            rad_disc = 0.0
        rad_disc = max(0.0, min(100.0, rad_disc))
        discount_factor = 1.0 - rad_disc / 100.0

        total_src_qty = 0
        total_src_power = 0
        total_src_sum = 0.0
        has_src_sum = False

        total_pnl_power = 0
        total_pnl_qty = 0
        total_pnl_sum = 0.0

        for h in self.HEIGHTS:
            try:
                p_per_sec = float(self._power_vars[h].get().replace(",", "."))
            except (ValueError, TypeError):
                p_per_sec = 0.0
            try:
                price_per_sec = float(self._price_vars[h].get().replace(",", "."))
            except (ValueError, TypeError):
                price_per_sec = 0.0

            for s in range(MIN_SECTIONS, MAX_SECTIONS + 1):
                qty = self._parse_int(self._qty_vars[h][s].get())
                if qty <= 0:
                    continue
                total_src_qty += qty
                total_src_power += p_per_sec * s * qty
                if price_per_sec > 0:
                    # Секционный — БЕЗ скидки
                    total_src_sum += price_per_sec * s * qty
                    has_src_sum = True
                rad = self._selected[h].get(s)
                if rad is not None:
                    total_pnl_power += rad.power_total_panel
                    total_pnl_qty += qty
                    price_pnl = self._get_panel_price(rad.article)
                    if price_pnl is not None:
                        # Панельный — СО скидкой
                        total_pnl_sum += price_pnl * qty * discount_factor

        if self._total_src_qty_lbl:
            self._total_src_qty_lbl.config(text=str(total_src_qty))
        if self._total_src_power_lbl:
            self._total_src_power_lbl.config(text=str(int(round(total_src_power))))
        if self._total_src_sum_lbl:
            self._total_src_sum_lbl.config(
                text=self._fmt_money(total_src_sum) if has_src_sum else "—")
        if self._total_pnl_power_lbl:
            self._total_pnl_power_lbl.config(text=str(int(round(total_pnl_power))))
        if self._total_pnl_qty_lbl:
            self._total_pnl_qty_lbl.config(text=str(total_pnl_qty))
        if self._total_pnl_sum_lbl:
            self._total_pnl_sum_lbl.config(text=self._fmt_money(total_pnl_sum))
        if self._total_pnl_dev_lbl:
            if total_src_power > 0:
                dev = (total_pnl_power - total_src_power) / total_src_power * 100
                self._total_pnl_dev_lbl.config(
                    text=f"{dev:+.2f}".replace(".", ","))
            else:
                self._total_pnl_dev_lbl.config(text="—")

    def _on_discount_changed_local(self) -> None:
        """
        Пересчитывает таблицу при изменении скидок.
        Вызывается через trace_add на общих переменных скидок главного окна.
        """
        try:
            self._refresh_table_for_height()
        except Exception as e:
            logger.debug(f"Ошибка пересчёта таблицы при смене скидки: {e}")

    # ==================================================================
    # Вспомогательные
    # ==================================================================
    @staticmethod
    def _fmt_money(value) -> str:
        try:
            v = float(value)
            return f"{v:,.2f}".replace(",", " ").replace(".", ",")
        except (ValueError, TypeError):
            return "—"

    def _get_panel_price(self, article: str) -> Optional[float]:
        try:
            df = self.app.data_provider.radiators_df
            mask = df['Артикул'].astype(str).str.strip() == str(article).strip()
            matches = df[mask]
            if not matches.empty:
                return float(matches.iloc[0].get('Цена, руб', 0))
        except Exception as e:
            logger.debug(f"Ошибка получения цены для {article}: {e}")
        return None

    @staticmethod
    def _parse_int(value) -> int:
        if not value:
            return 0
        s = str(value).strip().replace(",", ".").replace(" ", "")
        if not s:
            return 0
        try:
            return int(float(s))
        except ValueError:
            return 0

    @staticmethod
    def _validate_qty_input(value: str) -> bool:
        """
        Валидация поля количества секционных радиаторов.
        Разрешает пустую строку и целые неотрицательные числа.
        Ограничивает длину 4 знаками (до 9999).
        """
        if value == "":
            return True
        if not value.isdigit():
            return False
        if len(value) > 4:
            return False
        return True

    @staticmethod
    def _validate_discount(value: str) -> bool:
        """
        Валидация поля скидки: пусто или число 0..100.
        Разрешает запятую и точку как десятичный разделитель.
        """
        if value == "":
            return True
        try:
            v = float(value.replace(',', '.'))
            return 0 <= v <= 100
        except ValueError:
            return False

    @staticmethod
    def _validate_temperature(value: str) -> bool:
        """
        Валидация поля температуры: пусто или целое 0..150.
        Та же логика, что и в главном окне.
        """
        if value == "":
            return True
        return value.isdigit() and 0 <= int(value) <= 150

    # ==================================================================
    # Обработчики
    # ==================================================================
    def _on_power_changed(self, height: int) -> None:
        self._reset_manual_choices(height=height)

        # Пересчитываем только заполненные строки этой высоты.
        for s in range(MIN_SECTIONS, MAX_SECTIONS + 1):
            qty = self._parse_int(self._qty_vars[height][s].get())
            if qty > 0:
                self._on_qty_changed(s, height)

        if height == self._current_height:
            self._refresh_table_for_height()
        self._update_total_row()

    def _on_price_changed(self, height: int) -> None:
        if height == self._current_height:
            self._refresh_table_for_height()
        self._update_total_row()

    def _on_param_changed(self) -> None:
        self._reset_manual_choices()

        # Пересчитываем только активную высоту и только те строки,
        # у которых введено количество. Остальные не трогаем —
        # там и так пусто, а подтянутся они при переключении вкладки.
        h = self._current_height
        for s in range(MIN_SECTIONS, MAX_SECTIONS + 1):
            qty = self._parse_int(self._qty_vars[h][s].get())
            if qty > 0:
                self._on_qty_changed(s, h)

        self._refresh_table_for_height()
        self._update_total_row()

    def _on_mode_changed(self) -> None:
        self._hide_row_tooltip()
        self._hide_candidate_popup()
        self._reset_manual_choices()

        # Пересчитываем только активную высоту и только заполненные строки.
        h = self._current_height
        for s in range(MIN_SECTIONS, MAX_SECTIONS + 1):
            qty = self._parse_int(self._qty_vars[h][s].get())
            if qty > 0:
                self._on_qty_changed(s, h)

        self._refresh_table_for_height()
        self._update_total_row()

    def _reset_manual_choices(self, height: Optional[int] = None) -> None:
        if height is None:
            self._manual_choice.clear()
        else:
            keys = [k for k in self._manual_choice if k[0] == height]
            for k in keys:
                del self._manual_choice[k]

    def _on_reset(self) -> None:
        for tid in self._debounce_timers.values():
            try:
                if self._dialog and self._dialog.winfo_exists():
                    self._dialog.after_cancel(tid)
            except Exception:
                pass
        self._debounce_timers.clear()
        self._hide_row_tooltip()
        self._hide_candidate_popup()
        self._reset_manual_choices()

        for h in self.HEIGHTS:
            self._power_vars[h].set(str(SECTION_POWER[h]))
            self._price_vars[h].set(str(DEFAULT_SECTION_PRICE[h]))
            for s in range(MIN_SECTIONS, MAX_SECTIONS + 1):
                self._qty_vars[h][s].set("")
                w = self._row_widgets[h][s]
                for key in ("src_power", "src_total", "src_price", "src_sum"):
                    w[key].config(text="", bg=self.BG_SRC_EMPTY, fg="#333")
                for key in ("pnl_name", "pnl_power", "pnl_total",
                            "pnl_dev", "pnl_qty", "pnl_price", "pnl_sum"):
                    w[key].config(text="", bg=self.BG_PNL_EMPTY, fg=self.FG_EMPTY)
            self._selected[h].clear()

        self._deviation_var.set("5")
        self._conn_mode_var.set("K")
        self._mount_var.set("настенный")
        self._mode_var.set(MODE_POWER)

        # ================================================================
        # Сброс температурного графика к эталонному 95/85/20.
        # Переменные общие с главным окном — изменение мгновенно
        # отразится и там, и в метке Δt этого окна.
        # ================================================================
        try:
            main_window = self.app.main_window
            main_window._graph_supply_var.set("95")
            main_window._graph_return_var.set("85")
            main_window._graph_room_var.set("20")
        except Exception as e:
            logger.debug(f"Не удалось сбросить температурный график: {e}")
        # ================================================================

        self._update_height_tabs_visual()
        self._refresh_table_for_height()
        self._update_qty_entries_bg()
        self._update_total_row()

    def _on_graph_changed_local(self) -> None:
        """
        Пересчитывает метку Δt при изменении любой из переменных графика.
        Обновляет app.temperature_graph, чтобы экспорт и предпросмотр
        использовали актуальный график.
        """
        if not hasattr(self, '_delta_t_label') or self._delta_t_label is None:
            return

        main_window = self.app.main_window

        try:
            supply = int(main_window._graph_supply_var.get() or 95)
            ret = int(main_window._graph_return_var.get() or 85)
            room = int(main_window._graph_room_var.get() or 20)
        except (ValueError, AttributeError):
            return  # незавершённый ввод

        delta_t = PowerRecalculator.delta_t_from(supply, ret, room)

        try:
            self._delta_t_label.config(
                text=f"Δt = {delta_t:.2f} °С".replace('.', ',')
            )
        except tk.TclError:
            return

        if PowerRecalculator.is_reference(delta_t):
            try:
                self._delta_t_label.config(fg=self.FG_ACCENT)
            except tk.TclError:
                pass
        elif delta_t > 0:
            try:
                self._delta_t_label.config(fg="#d35400")
            except tk.TclError:
                pass
        else:
            try:
                self._delta_t_label.config(fg="#c0392b")
            except tk.TclError:
                pass

        # Синхронизируем app.temperature_graph
        self.app.temperature_graph = {
            "supply": supply,
            "return": ret,
            "room": room,
        }

    def _on_qty_focus_in(self, sections: int) -> None:
        self._focus_height[sections] = self._current_height
        var = self._qty_vars[self._current_height][sections]
        if var.get().strip() in ("", "0"):
            var.set("")

    def _on_qty_focus_out(self, sections: int) -> None:
        h = self._focus_height.get(sections, self._current_height)
        self._on_qty_changed(sections, h)
        self._focus_height.pop(sections, None)

    def _on_qty_return(self, sections: int) -> None:
        h = self._focus_height.get(sections, self._current_height)
        self._on_qty_changed(sections, h)

    def _focus_qty_prev(self, sections: int) -> str:
        """Переводит фокус на поле количества строкой выше."""
        prev_sections = sections - 1
        if prev_sections < MIN_SECTIONS:
            return "break"
        h = self._current_height
        entry = self._qty_entries.get(h, {}).get(prev_sections)
        if entry is None:
            return "break"
        try:
            if entry.winfo_exists():
                entry.focus_set()
                entry.select_range(0, tk.END)
        except tk.TclError:
            pass
        return "break"

    def _focus_qty_next(self, sections: int) -> str:
        """Переводит фокус на поле количества строкой ниже."""
        next_sections = sections + 1
        if next_sections > MAX_SECTIONS:
            return "break"
        h = self._current_height
        entry = self._qty_entries.get(h, {}).get(next_sections)
        if entry is None:
            return "break"
        try:
            if entry.winfo_exists():
                entry.focus_set()
                entry.select_range(0, tk.END)
        except tk.TclError:
            pass
        return "break"

    def _on_qty_key_release(self, sections: int) -> None:
        h = self._focus_height.get(sections, self._current_height)
        key = (h, sections)

        tid = self._debounce_timers.pop(key, None)
        if tid is not None:
            try:
                if self._dialog and self._dialog.winfo_exists():
                    self._dialog.after_cancel(tid)
            except Exception:
                pass

        if self._dialog and self._dialog.winfo_exists():
            tid_new = self._dialog.after(
                DEBOUNCE_MS,
                lambda hh=h, ss=sections: self._on_qty_debounced(hh, ss),
            )
            self._debounce_timers[key] = tid_new

    def _on_qty_debounced(self, height: int, sections: int) -> None:
        self._debounce_timers.pop((height, sections), None)
        self._on_qty_changed(sections, height)

    def _on_qty_changed(self, sections: int, height: int) -> None:
        try:
            qty = self._parse_int(self._qty_vars[height][sections].get())
        except Exception:
            qty = 0
        if qty < 0:
            qty = 0

        self._select_for_row(sections, qty, height)

        if height == self._current_height:
            self._refresh_table_for_height()

        self._update_height_tabs_visual()
        self._update_qty_entries_bg()
        self._update_total_row()

    def _select_for_row(self, sections: int, qty: int, height: int) -> None:
        try:
            power_per_section = float(
                self._power_vars[height].get().replace(",", "."))
        except (ValueError, TypeError):
            power_per_section = 0.0

        if qty <= 0:
            self._selected[height].pop(sections, None)
            self._manual_choice.pop((height, sections), None)
            return

        manual = self._manual_choice.get((height, sections))
        if manual is not None:
            panel_height = HEIGHT_TO_PANEL.get(height, height)
            if self._mode_var.get() == MODE_DIMENSION:
                rad = self._build_manual_dimension(
                    manual, sections, power_per_section, qty, panel_height)
            else:
                rad = self._build_manual_power(
                    manual, sections, power_per_section, qty, panel_height)
            self._selected[height][sections] = rad
            return

        try:
            deviation_pct = float(self._deviation_var.get().replace(",", "."))
        except (ValueError, TypeError):
            deviation_pct = 5.0

        conn_mode = self._conn_mode_var.get()
        mode = self._mode_var.get()
        panel_height = HEIGHT_TO_PANEL.get(height, height)

        if conn_mode == "VK":
            conn_str = "VK-правое"
        else:
            conn_str = "K-боковое"

        if mode == MODE_DIMENSION:
            rad = self._selector_dimension.select(
                height=panel_height,
                sections=sections,
                power_per_section=power_per_section,
                deviation_pct=deviation_pct,
                connection_mode=conn_str,
                quantity=qty,
            )
        else:
            rad = self._selector_power.select(
                height=panel_height,
                sections=sections,
                power_per_section=power_per_section,
                deviation_pct=deviation_pct,
                connection_mode=conn_str,
                quantity=qty,
            )

        self._selected[height][sections] = rad

    def _build_manual_dimension(self, manual, sections, power_per_section,
                                qty, panel_height) -> SelectedByDimension:
        power_total_source = power_per_section * sections
        return SelectedByDimension(
            article=manual["article"],
            name=manual["name"],
            radiator_type=manual["type"],
            height=panel_height,
            length=manual["length"],
            power=manual["power"],
            sections_source=sections,
            quantity=qty,
            power_section_source=power_per_section,
            power_total_source=power_total_source * qty,
            power_total_panel=manual["power"] * qty,
            deviation_pct=manual["deviation"],
            in_tolerance=False,
            connection=self._conn_mode_var.get(),
            all_candidates=[],
        )

    def _build_manual_power(self, manual, sections, power_per_section,
                            qty, panel_height) -> SelectedByPower:
        power_total_source = power_per_section * sections
        return SelectedByPower(
            article=manual["article"],
            name=manual["name"],
            radiator_type=manual["type"],
            height=panel_height,
            length=manual["length"],
            power=manual["power"],
            sections_source=sections,
            quantity=qty,
            power_section_source=power_per_section,
            power_total_source=power_total_source * qty,
            power_total_panel=manual["power"] * qty,
            deviation_pct=manual["deviation"],
            in_tolerance=False,
            connection=self._conn_mode_var.get(),
            all_candidates=[],
        )

    # ==================================================================
    # Кнопки
    # ==================================================================

    def _on_create_spec(self) -> None:
        if not self._transfer_to_matrix():
            return
        # Сохраняем выбранный вид монтажа для main_window.on_create_spec.
        self.app._last_mount_type_from_section = self._mount_var.get()
        try:
            self.app.main_window._on_create_spec()
        except Exception as e:
            logger.error(f"Ошибка создания спецификации: {e}")

        try:
            if self._dialog and self._dialog.winfo_exists():
                self._dialog.lower()
        except Exception:
            pass
        
    def _on_preview(self) -> None:
        if not self._transfer_to_matrix():
            return
        # Сохраняем выбранный вид монтажа, чтобы main_window._on_preview
        # использовал его при формировании спецификации.
        self.app._last_mount_type_from_section = self._mount_var.get()
        try:
            self.app.main_window._on_preview(source="section_to_panel")
        except Exception as e:
            logger.error(f"Ошибка предпросмотра: {e}")

    def _transfer_to_matrix(self) -> bool:
        for tid in self._debounce_timers.values():
            try:
                if self._dialog and self._dialog.winfo_exists():
                    self._dialog.after_cancel(tid)
            except Exception:
                pass
        self._debounce_timers.clear()
        self._hide_row_tooltip()
        self._hide_candidate_popup()

        all_active = []
        for h in self.HEIGHTS:
            for sections, rad in self._selected[h].items():
                if rad is None:
                    continue
                all_active.append((h, sections, rad))

        if not all_active:
            messagebox.showinfo(
                "Нет данных",
                "Введите количество хотя бы для одной позиции "
                "(на любой высоте).",
            )
            return False

        main_window = self.app.main_window
        has_data = bool(self.app.entry_values)

        if has_data:
            choice = main_window._ask_add_or_replace()
            if choice is None:
                return False
            if choice == "replace":
                self.app.entry_values.clear()

                # Заменяем таблицу соответствия — очищаем накопленные данные
                if hasattr(self.app, '_all_correspondence_data'):
                    self.app._all_correspondence_data = None
                if hasattr(self.app, '_all_correspondence_data_for_export'):
                    self.app._all_correspondence_data_for_export = None

        added = 0
        new_correspondence_rows = []

        for h, sections, rad in all_active:
            rt = rad.radiator_type
            key = (f"{rad.connection} {rt}", rad.article)
            existing = self.app.entry_values.get(key, "")
            if existing:
                try:
                    new_val = str(int(existing) + rad.quantity)
                except ValueError:
                    new_val = f"{existing}+{rad.quantity}"
            else:
                new_val = str(rad.quantity)
            self.app.entry_values[key] = new_val
            added += 1

            # ============================================================
            # Формируем строку для листа «Таблица соответствия»
            # ============================================================
            # Подключение — понятное название: «нижнее» или «боковое»
            if self._conn_mode_var.get() == "VK":
                conn_label = "нижнее подключение"
            else:
                conn_label = "боковое подключение"

            sections_word = _plural_sections(sections)
            original_name = (
                f"Секционный радиатор {h} мм, {sections} {sections_word}, "
                f"{conn_label}"
            )

            new_correspondence_rows.append({
                "Наименование": original_name,
                "Кол-во": rad.quantity,
                "Наименование LaggarTT": rad.name,
                "Артикул LaggarTT": rad.article,
                "Источник": "Замена секционных",
            })

        # ================================================================
        # Сохраняем таблицу соответствия (с накоплением или заменой)
        # ================================================================
        if new_correspondence_rows:
            new_df = pd.DataFrame(new_correspondence_rows)

            old_df = None
            if (hasattr(self.app, '_all_correspondence_data')
                    and self.app._all_correspondence_data is not None
                    and not self.app._all_correspondence_data.empty):
                old_df = self.app._all_correspondence_data.copy()

            if old_df is not None:
                combined_df = pd.concat([old_df, new_df], ignore_index=True)
            else:
                combined_df = new_df

            self.app._all_correspondence_data = combined_df.copy()
            self.app._all_correspondence_data_for_export = combined_df.copy()
            self.app._last_correspondence_data = new_df.copy()

            logger.info(
                f"Таблица соответствия обновлена из окна «Замена секционных»: "
                f"добавлено {len(new_df)} строк, всего {len(combined_df)}"
            )
        # ================================================================

        main_window._build_matrix(
            main_window._conn_var.get(),
            main_window._type_var.get(),
        )
        logger.info(f"Перенесено в матрицу: {added} позиций")
        return True