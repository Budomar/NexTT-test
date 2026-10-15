"""
Экспорт спецификации из главного окна NexTT.

Вынесено из MainWindow:
    • _on_create_spec      — создание и сохранение спецификации в Excel
    • _get_spec_file_path  — формирование пути сохранения

Логика:
    • Проверка температурного графика
    • Генерация данных спецификации через SpecGenerator
    • Сохранение через ExcelWriter с метаданными графика
    • Открытие готового файла средствами ОС
"""

import os
import re
import subprocess
import platform
from pathlib import Path
from datetime import datetime

from tkinter import messagebox

from nextt.core.power_recalculator import PowerRecalculator
from nextt.logger import get_logger

logger = get_logger(__name__)


# ======================================================================
# Создание спецификации
# ======================================================================

def on_create_spec(main_window) -> None:
    """Создаёт и сразу открывает спецификацию в Excel."""
    from nextt.export.excel_writer import ExcelWriter
    from nextt.ui.main_window_utils import parse_discount

    delta_t = main_window._current_delta_t()

    # Проверка корректности графика
    if not PowerRecalculator.is_valid_delta(delta_t):
        messagebox.showwarning(
            "Некорректный температурный график",
            "Температурный напор Δt ≤ 0.\n\n"
            "Проверьте значения подачи, обратки и температуры помещения "
            "в строке «Температурный график».\n\n"
            "Спецификация не может быть создана.",
        )
        return

    # ================================================================
    # Определяем тип монтажа: если последний активный сценарий —
    # «Замена секционных», берём сохранённый оттуда выбор.
    # ================================================================
    source = getattr(main_window.app, '_last_active_scenario', None)
    if source == "section_to_panel":
        mount_from_section = getattr(
            main_window.app, '_last_mount_type_from_section', None
        )
        if mount_from_section == "напольный":
            bracket_type_for_spec = "Напольные кронштейны"
        elif mount_from_section == "без":
            bracket_type_for_spec = "Без кронштейнов"
        else:
            bracket_type_for_spec = "Настенные кронштейны"
    else:
        bracket_type_for_spec = main_window.bracket_var.get()
    # ================================================================

    spec_data = main_window.app.spec_generator.prepare_spec_data(
        entry_values=main_window.app.entry_values,
        bracket_type=bracket_type_for_spec,
        radiator_discount=parse_discount(
            main_window.radiator_discount_var.get()
        ),
        bracket_discount=parse_discount(
            main_window.bracket_discount_var.get()
        ),
        delta_t=delta_t,
    )

    if spec_data is None or spec_data.empty:
        messagebox.showwarning(
            "Пусто",
            "Нет данных для спецификации.\nЗаполните матрицу радиаторов.",
        )
        return

    try:
        file_path = get_spec_file_path(main_window)
        logger.info(f"Сохранение спецификации в: {file_path}")

        writer = ExcelWriter(data_provider=main_window.app.data_provider)

        # Получаем данные таблицы соответствия
        correspondence_df = None

        if (hasattr(main_window.app, '_all_correspondence_data')
                and main_window.app._all_correspondence_data is not None):
            correspondence_df = main_window.app._all_correspondence_data.copy()
            logger.info(
                f"Экспорт: используем _all_correspondence_data, "
                f"{len(correspondence_df)} строк"
            )
            correspondence_df = correspondence_df.rename(columns={
                'Наименование': 'Оригинальное наименование',
                'Кол-во': 'Количество',
                'Источник': 'Источник подбора',
            })
        else:
            if hasattr(main_window.app, '_last_correspondence_dialog'):
                dialog = main_window.app._last_correspondence_dialog
                if hasattr(dialog, 'get_correspondence_data'):
                    correspondence_df = dialog.get_correspondence_data()
                    logger.info(
                        f"Экспорт: используем данные из диалога, "
                        f"{len(correspondence_df) if correspondence_df is not None else 0} строк"
                    )

        # Название программы из заголовка окна
        program_name = main_window.root.title()

        # Метаданные температурного графика для шапки
        graph = main_window.app.temperature_graph
        graph_meta = {
            "supply": graph.get("supply", 95),
            "return": graph.get("return", 85),
            "room": graph.get("room", 20),
            "delta_t": delta_t,
            "is_reference": PowerRecalculator.is_reference(delta_t),
        }

        writer.save(
            spec_data,
            file_path,
            correspondence_data=correspondence_df,
            program_name=program_name,
            graph_meta=graph_meta,
            project_name=main_window.project_var.get(),
            radiator_discount=parse_discount(main_window.radiator_discount_var.get()),
            bracket_discount=parse_discount(main_window.bracket_discount_var.get()),
        )
        # Открываем файл средствами ОС
        _open_file_native(file_path)

    except Exception as e:
        messagebox.showerror("Ошибка", f"Не удалось создать спецификацию:\n{str(e)}")
        logger.error(f"Ошибка создания спецификации: {e}")
        import traceback
        logger.error(traceback.format_exc())


# ======================================================================
# Формирование пути сохранения
# ======================================================================

def get_spec_file_path(main_window, base_name: str = "Расчёт стоимости") -> str:
    """
    Формирует путь для сохранения спецификации.

    Логика (в порядке приоритета имени):
        • Папка: ~/Downloads/NexTT/ (или ~/Загрузки/NexTT, или ~/NexTT)
        • Если поле «Проект» заполнено:
            имя: {base_name}_{Проект}
        • Иначе, если был загружен внешний файл (app._last_file_path):
            имя: {base_name}_{имя_исходного_файла_без_расширения}
        • Иначе:
            имя: {base_name}_{ДД.ММ.ГГ}
        • При конфликте имён добавляется суффикс " (1)", " (2)" и т.д.

    Дополнительно:
        • Все недопустимые символы (\\ / : * ? " < > | и переносы строк)
          заменяются на подчёркивание.
        • Итоговое имя файла обрезается, если превышает лимит Windows
          (260 символов для полного пути). Обрезаем с запасом — до 150
          символов для «хвоста» имени.
    """
    # --- Папка ---
    downloads = Path.home() / "Downloads"
    if not downloads.exists():
        downloads = Path.home() / "Загрузки"
    if not downloads.exists():
        downloads = Path.home()

    nextt_folder = downloads / "NexTT"
    nextt_folder.mkdir(exist_ok=True)

    # --- Приоритет 1: проект ---
    project_name = ""
    try:
        if hasattr(main_window, 'project_var'):
            project_name = (main_window.project_var.get() or "").strip()
    except Exception:
        project_name = ""

    file_base = None

    if project_name:
        file_base = f"{base_name}_{_sanitize_filename_part(project_name)}"

    # --- Приоритет 2: имя исходного файла ---
    if file_base is None:
        source_name = None
        if hasattr(main_window.app, '_last_file_path') and main_window.app._last_file_path:
            try:
                stem = Path(main_window.app._last_file_path).stem
                source_name = _sanitize_filename_part(stem)
            except Exception:
                source_name = None

        if source_name:
            file_base = f"{base_name}_{source_name}"

    # --- Приоритет 3: дата ---
    if file_base is None:
        date_str = datetime.now().strftime("%d.%m.%y")
        file_base = f"{base_name}_{date_str}"

    # --- Ограничение длины базового имени (без расширения) ---
    # Полный путь = папка + имя + .xlsx + возможный суффикс " (1)"
    # Ограничим базовое имя так, чтобы оставить запас.
    MAX_BASE_NAME_LEN = 120
    if len(file_base) > MAX_BASE_NAME_LEN:
        # Обрезаем и добавляем "…" (один символ), чтобы было видно обрезку
        file_base = file_base[:MAX_BASE_NAME_LEN - 1].rstrip() + "…"

    # --- Защита от перезаписи ---
    file_path = nextt_folder / f"{file_base}.xlsx"
    counter = 1
    while file_path.exists():
        file_path = nextt_folder / f"{file_base} ({counter}).xlsx"
        counter += 1
        if counter > 100000:
            raise Exception("Не удалось создать уникальное имя файла")

    return str(file_path)


def _sanitize_filename_part(value: str) -> str:
    """
    Очищает строку для использования в имени файла.

    • Заменяет все недопустимые символы Windows
      (\\ / : * ? " < > | и переносы строк) на подчёркивание.
    • Схлопывает множественные подчёркивания и пробелы.
    • Обрезает ведущие и хвостовые точки, пробелы, подчёркивания.
    """
    if not value:
        return ""

    # Заменяем недопустимые символы и переносы строк
    result = re.sub(r'[\\/:*?"<>|\r\n\t]+', '_', str(value))

    # Схлопываем множественные подчёркивания в одно
    result = re.sub(r'_+', '_', result)

    # Схлопываем множественные пробелы в один
    result = re.sub(r'\s+', ' ', result)

    # Убираем ведущие/хвостовые точки, пробелы, подчёркивания
    result = result.strip('._ ')

    return result


# ======================================================================
# Открытие файла
# ======================================================================

def _open_file_native(file_path: str) -> None:
    """Открывает файл средствами ОС."""
    try:
        if platform.system() == "Windows":
            os.startfile(file_path)
        elif platform.system() == "Darwin":
            subprocess.call(["open", file_path])
        else:
            subprocess.call(["xdg-open", file_path])
    except Exception as e:
        logger.error(f"Не удалось открыть файл {file_path}: {e}")