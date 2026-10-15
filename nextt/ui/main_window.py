"""
Главное окно приложения с матрицей радиаторов и панелью управления.

Это тонкий фасад — вся логика вынесена в модули:
    • main_window_styles         — настройка ttk-стилей
    • main_window_info           — информационные окна
    • main_window_utils          — валидация, парсинг, утилиты
    • main_window_top_menu       — верхнее меню
    • main_window_bottom         — нижняя панель
    • main_window_state          — сохранение/восстановление UI
    • main_window_fonts          — масштабирование шрифтов
    • main_window_temperature    — температурный график
    • main_window_settings       — панель настроек
    • main_window_matrix_tooltip — tooltip ячеек
    • main_window_matrix         — матрица радиаторов
    • main_window_import         — импорт файлов
    • main_window_export         — экспорт спецификации
"""

import tkinter as tk
from tkinter import ttk
from typing import Dict, List, Optional, Tuple

from nextt.logger import get_logger
from nextt.events import bus, Events

# Локальные модули MainWindow
from nextt.ui import main_window_styles
from nextt.ui import main_window_info
from nextt.ui import main_window_utils
from nextt.ui import main_window_top_menu
from nextt.ui import main_window_bottom
from nextt.ui import main_window_state
from nextt.ui import main_window_fonts
from nextt.ui import main_window_temperature
from nextt.ui import main_window_settings
from nextt.ui import main_window_matrix
from nextt.ui import main_window_matrix_tooltip
from nextt.ui import main_window_import
from nextt.ui import main_window_export

logger = get_logger(__name__)


class MainWindow:
    """Главное окно приложения."""

    HEIGHTS = [300, 400, 500, 600, 900]
    LENGTHS = list(range(400, 3100, 100))

    def __init__(self, app):
        self.app = app
        self.root = app.root

        self.font_manager = app.font_manager

        # Кеш виджетов
        self._cell_entries: Dict[Tuple[int, int], tk.Entry] = {}
        self._col_headers: Dict[int, tk.Label] = {}
        self._row_headers: Dict[int, tk.Label] = {}

        # Радиокнопки подключения (для подсветки)
        self._connection_radio_buttons: List[ttk.Radiobutton] = []
        # Радиокнопки типов (ключ: значение типа)
        self._type_radio_buttons: Dict[str, ttk.Radiobutton] = {}

        # Подсказки с картинками
        self._vk_right_tooltip: Optional[tk.Toplevel] = None
        self._vk_left_tooltip: Optional[tk.Toplevel] = None
        self._k_side_tooltip: Optional[tk.Toplevel] = None

        # Запоминание последнего типа для каждого подключения
        self._last_type_per_connection: Dict[str, str] = {
            "VK-правое": "10",
            "VK-левое": "10",
            "K-боковое": "10",
            "HV-правое": "10",
            "HV-левое": "10",
            "H-боковое": "10",
        }

        # Переменные
        self.bracket_var = tk.StringVar(value="Настенные кронштейны")
        self.radiator_discount_var = tk.StringVar(value="0")
        self.bracket_discount_var = tk.StringVar(value="0")
        self.show_tooltips_var = tk.BooleanVar(value=False)
        self.project_var = tk.StringVar(value="")

        # Ссылки на диалоги для закрытия при сбросе
        self._preview_dialog: Optional[object] = None
        self._meteor_selector: Optional[object] = None
        self._page_selector: Optional[object] = None

        # Флаг для предотвращения лишней перестройки матрицы при старте
        self._first_build_done = False

        # Настройка стилей
        self._setup_styles()

        # Строим интерфейс
        self._build_ui()

        # Состояние для восстановления
        self._saved_bracket_var = None
        self._saved_radiator_discount = None
        self._saved_bracket_discount = None
        self._saved_show_tooltips = None

        bus.subscribe(Events.DATA_LOADED, self._on_data_loaded)

        # ========== ПРОВЕРКА ОБНОВЛЕНИЙ ПРИ ЗАПУСКЕ ==========
        from nextt.utils.update_checker import check_updates_on_startup
        self.root.after(1000, lambda: check_updates_on_startup(
            self.root, self.font_manager
        ))
        # =====================================================

    # ==================================================================
    # СТИЛИ
    # ==================================================================

    def _setup_styles(self) -> None:
        """Настройка стилей ttk (делегируется в main_window_styles)."""
        main_window_styles.setup_styles(self.app.font_manager)

    # ==================================================================
    # СОХРАНЕНИЕ/ВОССТАНОВЛЕНИЕ UI
    # ==================================================================

    def _save_ui_state(self) -> None:
        """Сохраняет текущее состояние UI перед перестройкой."""
        main_window_state.save_ui_state(self)

    def _restore_ui_state(self) -> None:
        """Восстанавливает состояние UI после перестройки."""
        main_window_state.restore_ui_state(self)

    def _rebuild_all_ui(self) -> None:
        """Полностью перестраивает весь интерфейс."""
        main_window_state.rebuild_all_ui(self)

    # ==================================================================
    # ПОСТРОЕНИЕ ИНТЕРФЕЙСА
    # ==================================================================

    def _build_ui(self) -> None:
        """Создаёт интерфейс."""
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill="both", expand=True, padx=2, pady=2)

        # --- ВЕРХНЕЕ МЕНЮ ---
        main_window_top_menu.create_top_menu(main_frame, self)

        # Загружаем подсказки с картинками ДО настроек
        self._create_image_tooltips()

        # --- ПАНЕЛЬ НАСТРОЕК ---
        main_window_settings.create_settings_row(main_frame, self)

        # --- МАТРИЦА ---
        matrix_container = ttk.Frame(main_frame)
        matrix_container.pack(fill="both", expand=True, padx=2, pady=2)
        self._matrix_frame = ttk.Frame(matrix_container)
        self._matrix_frame.pack(fill="both", expand=True)

        # --- СТРОКА ТЕМПЕРАТУРНОГО ГРАФИКА ---
        main_window_temperature.create_temperature_graph_row(main_frame, self)

        # --- НИЖНЯЯ ПАНЕЛЬ ---
        main_window_bottom.create_bottom_panel(main_frame, self)

        # Показываем матрицу
        self._build_matrix("VK-правое", "10")

        # Принудительно обновляем геометрию
        self.root.update_idletasks()

    # ==================================================================
    # ПОДСКАЗКИ С КАРТИНКАМИ (VK/HV/K)
    # ==================================================================

    def _create_image_tooltips(self) -> None:
        """Создаёт подсказки с картинками."""
        import os
        from nextt.config import get_resource_path

        for attr, filename in [
            ('_vk_right_tooltip', "1.png"),
            ('_vk_left_tooltip', "2.png"),
            ('_k_side_tooltip', "3.png"),
        ]:
            try:
                path = get_resource_path(filename)
                if os.path.exists(path):
                    tooltip = tk.Toplevel(self.root)
                    tooltip.wm_overrideredirect(True)
                    tooltip.withdraw()
                    img = tk.PhotoImage(file=path)
                    label = ttk.Label(tooltip, image=img)
                    label.image = img
                    label.pack()
                    setattr(self, attr, tooltip)
                else:
                    setattr(self, attr, None)
            except Exception as e:
                logger.debug(f"Не удалось загрузить {filename}: {e}")
                setattr(self, attr, None)

    def _show_image_tooltip(self, tooltip: Optional[tk.Toplevel],
                            widget: tk.Widget) -> None:
        """Показывает подсказку с картинкой."""
        if tooltip and tooltip.winfo_exists():
            x = widget.winfo_rootx() + widget.winfo_width() + 5
            y = widget.winfo_rooty() - 50
            tooltip.wm_geometry(f"+{x}+{y}")
            tooltip.deiconify()

    def _hide_image_tooltip(self, tooltip: Optional[tk.Toplevel]) -> None:
        """Скрывает подсказку."""
        if tooltip and tooltip.winfo_exists():
            tooltip.withdraw()

    # ==================================================================
    # УПРАВЛЕНИЕ ШРИФТОМ
    # ==================================================================

    def _increase_font_scale(self) -> None:
        """Увеличивает масштаб шрифтов."""
        main_window_fonts.increase_font_scale(self)

    def _decrease_font_scale(self) -> None:
        """Уменьшает масштаб шрифтов."""
        main_window_fonts.decrease_font_scale(self)

    def _refresh_all_fonts(self) -> None:
        """Обновляет шрифты во всех окнах."""
        main_window_fonts.refresh_all_fonts(self)

    def _update_all_cells_fonts(self) -> None:
        """Обновляет шрифты в ячейках матрицы."""
        main_window_fonts.update_all_cells_fonts(self)

    def _update_all_labels_fonts_recursive(self, widget, font) -> None:
        """Рекурсивно обновляет ttk.Label."""
        main_window_fonts.update_all_labels_fonts_recursive(self, widget, font)

    def _update_checkbutton_fonts_recursive(self, widget, font) -> None:
        """Рекурсивно обновляет чекбоксы."""
        main_window_fonts.update_checkbutton_fonts_recursive(self, widget, font)

    def _update_tooltip_fonts(self) -> None:
        """Обновляет шрифты в подсказке."""
        main_window_fonts.update_tooltip_fonts(self)

    # ==================================================================
    # МАТРИЦА
    # ==================================================================

    def _build_matrix(self, connection: str, rad_type: str) -> None:
        """Строит матрицу радиаторов."""
        main_window_matrix.build_matrix(self, connection, rad_type)

    def _create_matrix_cell_adaptive_with_font(self, data, length: int,
                                               height: int, row: int, col: int,
                                               font) -> None:
        """Создаёт ячейку матрицы."""
        main_window_matrix.create_matrix_cell_adaptive_with_font(
            self, data, length, height, row, col, font
        )

    def _on_cell_changed(self, key: tuple, entry: tk.Entry) -> None:
        """Обработчик изменения количества в ячейке."""
        main_window_matrix.on_cell_changed(self, key, entry)

    def _highlight_headers(self, row: int, col: int) -> None:
        """Подсветка заголовков."""
        main_window_matrix.highlight_headers(self, row, col)

    def _clear_highlights(self) -> None:
        """Снятие подсветки."""
        main_window_matrix.clear_highlights(self)

    def _navigate_matrix(self, event, current_row: int, current_col: int,
                         direction: str) -> str:
        """Навигация по матрице."""
        return main_window_matrix.navigate_matrix(
            self, event, current_row, current_col, direction
        )

    # ==================================================================
    # TOOLTIP ЯЧЕЕК
    # ==================================================================

    def _create_tooltip_window(self) -> None:
        """Создаёт окно подсказки."""
        main_window_matrix_tooltip.create_tooltip_window(self)

    def _show_cell_tooltip(self, event, product) -> None:
        """Показывает подсказку."""
        main_window_matrix_tooltip.show_cell_tooltip(self, event, product)

    def _hide_cell_tooltip(self, event=None) -> None:
        """Скрывает подсказку."""
        main_window_matrix_tooltip.hide_cell_tooltip(self, event)

    # ==================================================================
    # ТЕМПЕРАТУРНЫЙ ГРАФИК
    # ==================================================================

    def _validate_temperature(self, value: str) -> bool:
        """Валидация температурного графика."""
        return main_window_temperature.validate_temperature(value)

    def _on_graph_changed(self, *args) -> None:
        """Реакция на изменение графика."""
        main_window_temperature.on_graph_changed(self)

    def _on_graph_reset(self) -> None:
        """Сброс графика."""
        main_window_temperature.on_graph_reset(self)

    def _on_graph_show(self) -> None:
        """Показ справочного окна."""
        main_window_temperature.on_graph_show(self)

    def _current_delta_t(self) -> float:
        """Возвращает текущий Δt."""
        return main_window_temperature.current_delta_t(self)

    # ==================================================================
    # НАСТРОЙКИ (подключение, типы, подсветка)
    # ==================================================================

    def _update_type_buttons_visibility(self) -> None:
        """Обновляет видимость кнопок типов."""
        main_window_settings.update_type_buttons_visibility(self)

    def _update_type_block_highlight(self) -> None:
        """Подсветка активного типа."""
        main_window_settings.update_type_block_highlight(self)

    def _update_connection_block_highlight(self) -> None:
        """Подсветка активного блока."""
        main_window_settings.update_connection_block_highlight(self)

    def _set_frame_bg_recursive(self, widget, color: str) -> None:
        """Рекурсивно устанавливает фон."""
        main_window_settings.set_frame_bg_recursive(widget, color)

    def _on_connection_changed(self) -> None:
        """Обработчик смены подключения."""
        main_window_settings.on_connection_changed(self)

    def _on_type_changed(self) -> None:
        """Обработчик смены типа."""
        main_window_settings.on_type_changed(self)

    # ==================================================================
    # УТИЛИТЫ
    # ==================================================================

    def _validate_input(self, value: str) -> bool:
        """Валидация ячейки матрицы."""
        return main_window_utils.validate_input(value)

    def _validate_number(self, value: str) -> bool:
        """Валидация числа (скидки)."""
        return main_window_utils.validate_number(value)

    def _parse_qty(self, value) -> int:
        """Парсинг количества."""
        return main_window_utils.parse_qty(value)

    def _normalize_radiator_name(self, name: str) -> str:
        """Нормализация названия."""
        return main_window_utils.normalize_radiator_name(name)

    def _is_laggar_file(self, df) -> bool:
        """Определение LaggarTT файла."""
        return main_window_utils.is_laggar_file(df)

    # ==================================================================
    # ИМПОРТ
    # ==================================================================

    def _on_load_data(self) -> None:
        """Загружает данные из файла."""
        main_window_import.on_load_data(self)

    def _ask_add_or_replace(self) -> Optional[str]:
        """Диалог добавления/замены."""
        return main_window_import._ask_add_or_replace(self)

    def _load_pdf_file(self, file_path: str, append_mode: bool = False) -> None:
        """Загрузка PDF."""
        main_window_import._load_pdf_file(self, file_path, append_mode)

    def _load_laggar_file(self, df) -> bool:
        """Загрузка LaggarTT файла."""
        return main_window_import._load_laggar_file(self, df)

    def _load_foreign_file(self, df, file_path: str,
                           append_mode: bool = False) -> None:
        """Загрузка чужой спецификации."""
        main_window_import._load_foreign_file(self, df, file_path, append_mode)

    def _process_excel_foreign_data(self, df, name_col_idx: int,
                                    qty_col_idx: int, file_path: str,
                                    append_mode: bool = False) -> None:
        """Обработка Excel."""
        main_window_import._process_excel_foreign_data(
            self, df, name_col_idx, qty_col_idx, file_path, append_mode
        )

    def _process_word_foreign_data(self, df, file_path: str,
                                   append_mode: bool = False) -> None:
        """Обработка Word."""
        main_window_import._process_word_foreign_data(
            self, df, file_path, append_mode
        )

    def _process_pdf_foreign_data(self, df, name_col_idx: int,
                                  qty_col_idx: int, file_path: str,
                                  append_mode: bool = False) -> None:
        """Обработка PDF."""
        main_window_import._process_pdf_foreign_data(
            self, df, name_col_idx, qty_col_idx, file_path, append_mode
        )

    def _process_laggar_pdf_data(self, df, art_col: int, qty_col: int) -> None:
        """Обработка LaggarTT PDF."""
        main_window_import._process_laggar_pdf_data(self, df, art_col, qty_col)

    def _parse_page_range(self, range_str: str, total_pages: int):
        """Парсинг диапазона страниц."""
        return main_window_import._parse_page_range(range_str, total_pages)

    # ==================================================================
    # ЭКСПОРТ
    # ==================================================================

    def _on_create_spec(self) -> None:
        """Создаёт спецификацию."""
        main_window_export.on_create_spec(self)

    def _get_spec_file_path(self, base_name: str = "Расчёт стоимости") -> str:
        """Формирует путь спецификации."""
        return main_window_export.get_spec_file_path(self, base_name)

    # ==================================================================
    # ПРЕДПРОСМОТР И ДИАЛОГИ
    # ==================================================================

    def _on_preview(self, source: Optional[str] = None) -> None:
        """Открывает предпросмотр спецификации."""
        from nextt.core.power_recalculator import PowerRecalculator
        from nextt.ui import main_window_utils

        delta_t = self._current_delta_t()

        if not PowerRecalculator.is_valid_delta(delta_t):
            from tkinter import messagebox
            messagebox.showwarning(
                "Некорректный температурный график",
                "Температурный напор Δt ≤ 0.\n\n"
                "Проверьте значения подачи, обратки и температуры помещения "
                "в строке «Температурный график».\n\n"
                "Спецификация не может быть создана.",
            )
            return

        # ================================================================
        # ОПРЕДЕЛЯЕМ ТИП МОНТАЖА
        # Если предпросмотр открыт из окна «Замена секционных» —
        # берём выбор из его радиокнопок (app._last_mount_type_from_section).
        # Иначе — из радиокнопок главного окна (self.bracket_var).
        # ================================================================
        if source == "section_to_panel":
            mount_from_section = getattr(
                self.app, '_last_mount_type_from_section', None
            )
            if mount_from_section == "напольный":
                bracket_type_for_spec = "Напольные кронштейны"
            elif mount_from_section == "без":
                bracket_type_for_spec = "Без кронштейнов"
            else:
                bracket_type_for_spec = "Настенные кронштейны"
        else:
            bracket_type_for_spec = self.bracket_var.get()
        # ================================================================

        spec_data = self.app.spec_generator.prepare_spec_data(
            entry_values=self.app.entry_values,
            bracket_type=bracket_type_for_spec,
            radiator_discount=main_window_utils.parse_discount(
                self.radiator_discount_var.get()
            ),
            bracket_discount=main_window_utils.parse_discount(
                self.bracket_discount_var.get()
            ),
            delta_t=delta_t,
        )

        from tkinter import messagebox
        if spec_data is None or spec_data.empty:
            messagebox.showwarning(
                "Предпросмотр",
                "Нет данных для спецификации.\nЗаполните матрицу радиаторов.",
            )
            return

        # Если source не передан явно — берём его из последнего
        # активного сценария приложения.
        if source is None:
            source = getattr(self.app, '_last_active_scenario', None)

        from nextt.ui.dialogs.preview import PreviewDialog
        preview = PreviewDialog(self.app)
        self._preview_dialog = preview
        preview.show(spec_data, delta_t=delta_t, source=source)

    def _on_edit_correspondence(self) -> None:
        """Открывает окно редактирования таблицы соответствия."""
        from tkinter import messagebox

        if (hasattr(self.app, '_last_correspondence_data')
                and self.app._last_correspondence_data is not None):
            if not self.app._last_correspondence_data.empty:
                from nextt.ui.dialogs.correspondence import CorrespondenceDialog
                dialog = CorrespondenceDialog(self.app)
                self.app._last_correspondence_dialog = dialog
                dialog.show(self.app._last_correspondence_data)
                return

        if (hasattr(self.app, '_all_correspondence_data')
                and self.app._all_correspondence_data is not None):
            if not self.app._all_correspondence_data.empty:
                from nextt.ui.dialogs.correspondence import CorrespondenceDialog
                dialog = CorrespondenceDialog(self.app)
                self.app._last_correspondence_dialog = dialog
                dialog.show(self.app._all_correspondence_data)
                return

        messagebox.showinfo(
            "Информация",
            "Нет данных для редактирования.\nСначала загрузите спецификацию.",
        )

    # ==================================================================
    # ЭКСПЕРИМЕНТАЛЬНЫЕ ФУНКЦИИ
    # ==================================================================

    def _on_paste_experimental(self) -> None:
        """Обработчик экспериментальной кнопки «Вставить из буфера»."""
        from tkinter import messagebox
        try:
            from nextt.experimental.paste_handler import show_paste_dialog
            show_paste_dialog(self)
        except ImportError as e:
            messagebox.showwarning(
                "Функция недоступна",
                "Экспериментальный модуль не установлен.\n"
                "Для использования функции требуется установка "
                "дополнительных компонентов.",
            )
            logger.warning(f"Экспериментальный модуль не загружен: {e}")
        except Exception as e:
            logger.error(f"Ошибка в экспериментальной функции: {e}")
            messagebox.showerror(
                "Ошибка",
                f"Произошла ошибка при вызове экспериментальной функции:\n"
                f"{str(e)}\n\nФункция временно недоступна.",
            )

    def _on_section_to_panel(self) -> None:
        """Открывает диалог «Замена секционных радиаторов»."""
        from nextt.ui.dialogs.section_to_panel import SectionToPanelDialog

        # Устанавливаем флаг сценария — что пользователь сейчас работает
        # именно с заменой секционных. Этот флаг потом используется
        # в окне предпросмотра для правильного набора кнопок «Назад…».
        self.app._last_active_scenario = "section_to_panel"

        dialog = SectionToPanelDialog(self.app)
        self.app._last_section_to_panel_dialog = dialog
        dialog.show()

    # ==================================================================
    # СБРОС
    # ==================================================================

    def _on_reset(self) -> None:
        """Сброс всего: матрица, кэш, вспомогательные окна."""
        # 1. Очистка матрицы
        self.app.entry_values.clear()

        # 2. Сброс настроек
        self.radiator_discount_var.set("0")
        self.bracket_discount_var.set("0")
        self.bracket_var.set("Настенные кронштейны")
        # 2.1. Сброс поля «Проект»
        self.project_var.set("")
        # 3. Сброс температурного графика
        self._on_graph_reset()

        # 4. Очистка данных таблицы соответствия
        if hasattr(self.app, '_all_correspondence_data'):
            self.app._all_correspondence_data = None
        if hasattr(self.app, '_all_correspondence_data_for_export'):
            self.app._all_correspondence_data_for_export = None
        if hasattr(self.app, '_last_correspondence_data'):
            self.app._last_correspondence_data = None
        if hasattr(self.app, '_last_correspondence_dialog'):
            self.app._last_correspondence_dialog = None

        # 5. Очистка признаков загруженного внешнего файла
        if hasattr(self.app, '_last_file_path'):
            self.app._last_file_path = None
        if hasattr(self.app, '_last_raw_data'):
            self.app._last_raw_data = None
        if hasattr(self.app, '_last_file_type'):
            self.app._last_file_type = None
        if hasattr(self.app, '_last_imported_file'):
            self.app._last_imported_file = None

        # 6. Сброс активного сценария
        if hasattr(self.app, '_last_active_scenario'):
            self.app._last_active_scenario = None

        # 7. Уничтожение окна «Замена секционных» (если оно было создано)
        existing = getattr(self.app, '_last_section_to_panel_dialog', None)
        if existing is not None:
            try:
                existing.destroy()
            except Exception as e:
                logger.debug(f"Ошибка уничтожения окна «Замена секционных»: {e}")
            self.app._last_section_to_panel_dialog = None

        # 8. Закрытие всех вспомогательных окон
        self._close_all_child_windows()

        # 9. Перестроение матрицы
        self._build_matrix(self._conn_var.get(), self._type_var.get())

        logger.info(
            "Сброс выполнен: матрица очищена, кэш сброшен, окна закрыты, "
            "данные таблицы соответствия и признаки внешнего файла удалены, "
            "активный сценарий сброшен, окно «Замена секционных» уничтожено"
        )

    def _clear_cache(self) -> None:
        """Очищает кэш данных таблицы соответствия и экспорта."""
        if hasattr(self.app, '_all_correspondence_data'):
            self.app._all_correspondence_data = None
        if hasattr(self.app, '_all_correspondence_data_for_export'):
            self.app._all_correspondence_data_for_export = None
        if hasattr(self.app, '_last_correspondence_data'):
            self.app._last_correspondence_data = None
        if hasattr(self.app, '_last_correspondence_dialog'):
            self.app._last_correspondence_dialog = None
        if hasattr(self, '_saved_correspondence_data'):
            self._saved_correspondence_data = None

        logger.info("Кэш данных таблицы соответствия полностью очищен")

    def _close_all_child_windows(self) -> None:
        """Закрывает все дочерние окна приложения."""
        closed_count = 0

        for window in self.root.winfo_children():
            if isinstance(window, tk.Toplevel):
                try:
                    if window.winfo_exists():
                        window.destroy()
                        closed_count += 1
                except tk.TclError:
                    closed_count += 1
                except Exception as e:
                    logger.debug(f"Ошибка закрытия окна: {e}")

        # Проверяем атрибуты приложения
        if hasattr(self.app, '_last_correspondence_dialog'):
            try:
                dialog = self.app._last_correspondence_dialog
                if (hasattr(dialog, '_dialog') and dialog._dialog
                        and dialog._dialog.winfo_exists()):
                    dialog._close()
                    closed_count += 1
            except Exception as e:
                logger.debug(f"Ошибка закрытия CorrespondenceDialog: {e}")

        # MeteorSelector
        if hasattr(self, '_meteor_selector') and self._meteor_selector:
            try:
                if (hasattr(self._meteor_selector, '_dialog')
                        and self._meteor_selector._dialog
                        and self._meteor_selector._dialog.winfo_exists()):
                    self._meteor_selector._close()
                    closed_count += 1
            except Exception as e:
                logger.debug(f"Ошибка закрытия MeteorSelector: {e}")
            finally:
                self._meteor_selector = None

        # PreviewDialog
        if hasattr(self, '_preview_dialog') and self._preview_dialog:
            try:
                if (hasattr(self._preview_dialog, '_dialog')
                        and self._preview_dialog._dialog
                        and self._preview_dialog._dialog.winfo_exists()):
                    self._preview_dialog._close()
                    closed_count += 1
            except Exception as e:
                logger.debug(f"Ошибка закрытия PreviewDialog: {e}")
            finally:
                self._preview_dialog = None

        # Подсказки
        self._hide_cell_tooltip()
        if (hasattr(self, '_header_tooltip')
                and self._header_tooltip
                and self._header_tooltip.winfo_exists()):
            self._header_tooltip.destroy()

        if closed_count > 0:
            logger.info(f"Закрыто дочерних окон: {closed_count}")
        else:
            logger.debug("Нет открытых дочерних окон для закрытия")

    # ==================================================================
    # СОБЫТИЯ
    # ==================================================================

    def _on_data_loaded(self, count: int) -> None:
        """Обработчик события загрузки данных."""
        logger.info(f"Данные загружены: {count} радиаторов")