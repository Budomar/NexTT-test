"""
Информационные окна и внешние ссылки для главного окна NexTT.

Вынесено из MainWindow: обработчики меню «Информация», открытие
документов и внешних ресурсов, проверка обновлений по кнопке.

Все функции принимают `app` (экземпляр App) для доступа к root,
font_manager и другим менеджерам.
"""

import os
import subprocess
import platform
import webbrowser
import tkinter as tk
from tkinter import ttk, messagebox

from nextt.logger import get_logger
from nextt.config import get_resource_path

logger = get_logger(__name__)


# ======================================================================
# Открытие документов и ссылок
# ======================================================================

def open_file_native(path: str) -> bool:
    """
    Открывает файл средствами ОС (Windows/macOS/Linux).

    Returns:
        True — если удалось, False — если файл не найден или ошибка.
    """
    if not path or not os.path.exists(path):
        return False

    try:
        if platform.system() == "Windows":
            os.startfile(path)
        elif platform.system() == "Darwin":
            subprocess.call(["open", path])
        else:
            subprocess.call(["xdg-open", path])
        return True
    except Exception as e:
        logger.error(f"Не удалось открыть файл {path}: {e}")
        return False


# ======================================================================
# Обработчики пунктов меню «Информация»
# ======================================================================

def on_license(app) -> None:
    """Показывает лицензионное соглашение."""
    agreement_text = """ЛИЦЕНЗИОННОЕ СОГЛАШЕНИЕ
НА ИСПОЛЬЗОВАНИЕ ПРОГРАММНОГО ОБЕСПЕЧЕНИЯ "NexTT"

Настоящее Лицензионное соглашение (далее – «Соглашение») регулирует условия использования программного обеспечения «NexTT» (далее – «ПО»), распространяемого на безвозмездной основе.

1. Права на интеллектуальную собственность
1.1. Программное обеспечение, включая его исходный код, является интеллектуальной собственностью ООО «Термотехника Энгельс» (далее – «Правообладатель»).
1.2. Любое несанкционированное копирование, модификация или распространение ПО запрещено.

Реквизиты Правообладателя:
ООО «Термотехника Энгельс»
Россия, Саратовская область, г. Энгельс,
Проспект Ф. Энгельса, 139
Официальный сайт: https://laggartt.ru

2. Назначение ПО
2.1. Программное обеспечение предназначено для формирования спецификаций на радиаторы LaggarTT в соответствии с программой поставки ООО «Термотехника Энгельс».

3. Условия использования результатов работы ПО
3.1. Результаты, полученные с использованием ПО, носят оценочный характер и не могут рассматриваться как точные данные.
3.2. ПО предназначено исключительно для предварительной оценки оборудования и не может служить основанием для проектных решений без дополнительной проверки.
3.3. Использование ПО не освобождает Пользователя от соблюдения действующих отраслевых стандартов (DIN, ГОСТ), а также территориальных норм и правил.
3.4. Пользователь самостоятельно несет ответственность за:
- корректность подбора оборудования;
- соответствие материалов и компонентов требованиям проекта;
- последствия, вызванные некорректным использованием ПО.
3.5. ООО «Термотехника Энгельс» не несет ответственности за ущерб, возникший в результате применения данных, полученных с использованием ПО.

4. Условия распространения и использования ПО
4.1. Пользователь вправе устанавливать и использовать ПО на любом количестве компьютеров, в том числе в локальной сети организации.
4.2. Использование ПО разрешено несколькими сотрудниками при условии соблюдения настоящего Соглашения.

5. Срок действия и изменения
5.1. Действие настоящего Соглашения распространяется на версию ПО, актуальную на дату его выпуска.
5.2. ООО «Термотехника Энгельс» оставляет за собой право вносить изменения в номенклатуру оборудования без дополнительного уведомления Пользователей.

ООО «Термотехника Энгельс»
(01.2026)"""

    from nextt.utils.window_manager import get_safe_geometry

    license_window = tk.Toplevel(app.root)
    license_window.title("Лицензионное соглашение")
    license_window.transient(app.root)
    license_window.grab_set()
    license_window.geometry(get_safe_geometry(license_window))

    main_frame = ttk.Frame(license_window)
    main_frame.pack(fill="both", expand=True, padx=15, pady=15)

    text_widget = tk.Text(main_frame, wrap="word", font=("Segoe UI", 10),
                          padx=10, pady=10)
    text_widget.pack(fill="both", expand=True)
    text_widget.insert("1.0", agreement_text)
    text_widget.config(state="disabled")

    scrollbar = ttk.Scrollbar(text_widget, command=text_widget.yview)
    scrollbar.pack(side="right", fill="y")
    text_widget.config(yscrollcommand=scrollbar.set)

    ttk.Button(main_frame, text="Закрыть",
               command=license_window.destroy).pack(pady=(10, 0))


def on_instruction(app) -> None:
    """Открывает файл инструкции PDF."""
    try:
        pdf_path = get_resource_path("Инструкция.pdf")
        if not open_file_native(pdf_path):
            messagebox.showerror(
                "Ошибка",
                "Файл инструкции не найден.\n"
                "Поместите файл 'Инструкция.pdf' рядом с программой."
            )
    except Exception as e:
        messagebox.showerror("Ошибка", f"Не удалось открыть файл инструкции:\n{str(e)}")


def on_power_method(app) -> None:
    """Открывает окно с методикой пересчёта мощностей."""
    from nextt.ui.dialogs.methodology import MethodologyDialog
    dialog = MethodologyDialog(app)
    dialog.show()


def on_price_list(app) -> None:
    """Открывает прайс-лист."""
    try:
        path = get_resource_path("Прайс-лист.xlsx")
        if not open_file_native(path):
            messagebox.showerror("Ошибка", "Файл не найден")
    except Exception as e:
        messagebox.showerror("Ошибка", str(e))


def on_formulyar(app) -> None:
    """Открывает формуляр для регистрации проектов."""
    try:
        path = get_resource_path("Формуляр для регистрации проектов.xlsm")
        if not open_file_native(path):
            messagebox.showerror("Ошибка", "Файл не найден")
    except Exception as e:
        messagebox.showerror("Ошибка", str(e))


def on_catalog(app) -> None:
    """Открывает каталог оборудования на сайте."""
    webbrowser.open("https://laggartt.ru/catalogs/laggartt/")


def on_passport(app) -> None:
    """Открывает паспорт на радиатор."""
    webbrowser.open("https://b24.ez.meteor.ru/~yKwOz")


def on_certificate(app) -> None:
    """Открывает сертификат соответствия."""
    webbrowser.open("https://b24.ez.meteor.ru/~jXmyC")


def on_hygienic_certificate(app) -> None:
    """Открывает гигиенический сертификат."""
    webbrowser.open("https://b24.engpx.ru/~IPOCe")


def on_bim_models(app) -> None:
    """Открывает страницу с BIM-моделями."""
    webbrowser.open("https://b24.engpx.ru/~QQD8Z")


def on_check_update(app) -> None:
    """Проверяет наличие обновлений по кнопке."""
    from nextt.utils.update_checker import UpdateChecker
    checker = UpdateChecker(app.root, app.font_manager)
    update_data = checker.check_for_updates(show_no_update_message=True)
    if update_data:
        checker.show_update_dialog(update_data)