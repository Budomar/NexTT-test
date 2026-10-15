"""
Сохранение и восстановление состояния UI главного окна NexTT.

Вынесено из MainWindow:
    • _save_ui_state     — снимок текущего состояния
    • _restore_ui_state  — восстановление состояния после перестройки
    • _rebuild_all_ui    — полная перестройка интерфейса

Все функции принимают `main_window` (экземпляр MainWindow).
"""

from nextt.logger import get_logger

logger = get_logger(__name__)


def save_ui_state(main_window) -> None:
    """
    Сохраняет текущее состояние UI перед перестройкой.

    Снимок складывается прямо в атрибуты main_window с префиксом '_saved_'.
    """
    if hasattr(main_window, '_conn_var'):
        main_window._saved_connection = main_window._conn_var.get()
    if hasattr(main_window, '_type_var'):
        main_window._saved_type = main_window._type_var.get()
    if hasattr(main_window, 'bracket_var'):
        main_window._saved_bracket_var = main_window.bracket_var.get()
    if hasattr(main_window, 'radiator_discount_var'):
        main_window._saved_radiator_discount = main_window.radiator_discount_var.get()
    if hasattr(main_window, 'bracket_discount_var'):
        main_window._saved_bracket_discount = main_window.bracket_discount_var.get()
    if hasattr(main_window, 'show_tooltips_var'):
        main_window._saved_show_tooltips = main_window.show_tooltips_var.get()
    if hasattr(main_window, 'project_var'):
        main_window._saved_project = main_window.project_var.get()
    if hasattr(main_window, '_last_type_per_connection'):
        main_window._saved_last_type_per_connection = (
            main_window._last_type_per_connection.copy()
        )


def restore_ui_state(main_window) -> None:
    """Восстанавливает состояние UI после перестройки."""
    if hasattr(main_window, '_saved_connection') and hasattr(main_window, '_conn_var'):
        main_window._conn_var.set(main_window._saved_connection)
    if hasattr(main_window, '_saved_type') and hasattr(main_window, '_type_var'):
        main_window._type_var.set(main_window._saved_type)
    if hasattr(main_window, '_saved_bracket_var') and hasattr(main_window, 'bracket_var'):
        main_window.bracket_var.set(main_window._saved_bracket_var)
    if hasattr(main_window, '_saved_radiator_discount') and hasattr(main_window, 'radiator_discount_var'):
        main_window.radiator_discount_var.set(main_window._saved_radiator_discount)
    if hasattr(main_window, '_saved_bracket_discount') and hasattr(main_window, 'bracket_discount_var'):
        main_window.bracket_discount_var.set(main_window._saved_bracket_discount)
    if hasattr(main_window, '_saved_show_tooltips') and hasattr(main_window, 'show_tooltips_var'):
        main_window.show_tooltips_var.set(main_window._saved_show_tooltips)
    if hasattr(main_window, '_saved_project') and hasattr(main_window, 'project_var'):
        main_window.project_var.set(main_window._saved_project)
    if hasattr(main_window, '_saved_last_type_per_connection') and hasattr(main_window, '_last_type_per_connection'):
        main_window._last_type_per_connection = (
            main_window._saved_last_type_per_connection.copy()
        )


def rebuild_all_ui(main_window) -> None:
    """
    Полностью перестраивает весь интерфейс с новыми шрифтами.
    Сохраняет и восстанавливает состояние.

    Логика:
        1. Снимок состояния.
        2. Удаление всех виджетов корневого окна.
        3. Пересоздание кешей и переменных.
        4. Пересоздание стилей.
        5. Перестройка интерфейса (main_window._build_ui).
        6. Восстановление состояния.
        7. Принудительное обновление матрицы.
    """
    # 1. Сохраняем текущее состояние
    save_ui_state(main_window)

    # 2. Очищаем все виджеты в корневом окне
    for widget in main_window.root.winfo_children():
        widget.destroy()

    # 3. Пересоздаём все кеши
    main_window._cell_entries = {}
    main_window._col_headers = {}
    main_window._row_headers = {}
    main_window._connection_radio_buttons = []
    main_window._type_radio_buttons = {}
    main_window._blink_after_id = None

    # Обнуляем переменные строки температурного графика
    main_window._graph_supply_var = None
    main_window._graph_return_var = None
    main_window._graph_room_var = None
    main_window._graph_supply_entry = None
    main_window._graph_return_entry = None
    main_window._graph_room_entry = None
    main_window._delta_t_label = None
    main_window._graph_reset_btn = None
    main_window._graph_show_btn = None
    main_window._project_entry = None

    # 4. Пересоздаём стили (они применятся с новыми шрифтами)
    main_window._setup_styles()

    # 5. Перестраиваем интерфейс
    main_window._build_ui()

    # 6. Восстанавливаем состояние
    restore_ui_state(main_window)

    # 7. Принудительно обновляем матрицу
    if hasattr(main_window, '_conn_var') and hasattr(main_window, '_type_var'):
        main_window._build_matrix(
            main_window._conn_var.get(),
            main_window._type_var.get(),
        )