"""
Импорт данных из файлов в главное окно NexTT.

Вынесено из MainWindow:
    • _on_load_data                — открытие файла и запуск обработки
    • _ask_add_or_replace          — диалог «добавить или заменить»
    • _load_pdf_file               — обработка PDF
    • _load_laggar_file            — загрузка «своего» файла LaggarTT
    • _load_foreign_file           — загрузка чужой спецификации
    • _process_excel_foreign_data  — обработка Excel/CSV
    • _process_word_foreign_data   — обработка Word
    • _process_pdf_foreign_data    — обработка PDF
    • _process_laggar_pdf_data     — обработка LaggarTT PDF
    • _parse_page_range            — парсинг диапазона страниц
"""

import os
import re
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from typing import Optional, List

import pandas as pd

from nextt.logger import get_logger
from nextt.ui.main_window_utils import parse_qty, is_laggar_file

logger = get_logger(__name__)


# ======================================================================
# Точка входа: выбор файла и запуск обработки
# ======================================================================

def on_load_data(main_window) -> None:
    """Загружает данные из файла спецификации."""
    file_path = filedialog.askopenfilename(
        title="Выберите файл спецификации",
        filetypes=[
            ("Все поддерживаемые", "*.xlsx *.xls *.xlsm *.csv *.tsv *.txt *.pdf *.docx"),
            ("Excel файлы", "*.xlsx *.xls *.xlsm"),
            ("CSV/TSV файлы", "*.csv *.tsv *.txt"),
            ("Word файлы", "*.docx"),
            ("PDF файлы", "*.pdf"),
            ("Все файлы", "*.*"),
        ],
    )
    if not file_path:
        return

    has_existing_data = bool(main_window.app.entry_values)

    choice = None
    if has_existing_data:
        choice = _ask_add_or_replace(main_window)
        if choice is None:
            return
        elif choice == "replace":
            main_window.app.entry_values.clear()

            # Полная очистка данных таблицы соответствия
            if hasattr(main_window.app, '_all_correspondence_data'):
                main_window.app._all_correspondence_data = None
            if hasattr(main_window.app, '_all_correspondence_data_for_export'):
                main_window.app._all_correspondence_data_for_export = None
            if hasattr(main_window.app, '_last_correspondence_data'):
                main_window.app._last_correspondence_data = None
            if hasattr(main_window.app, '_last_correspondence_dialog'):
                main_window.app._last_correspondence_dialog = None

            main_window._build_matrix(
                main_window._conn_var.get(), main_window._type_var.get()
            )
            logger.info("Матрица и данные таблицы соответствия очищены (режим замены)")

    try:
        ext = os.path.splitext(file_path)[1].lower()

        # PDF обрабатываем отдельно
        if ext == '.pdf':
            _load_pdf_file(main_window, file_path, append_mode=(choice == "add"))
            return

        # Word обрабатываем отдельно
        if ext == '.docx':
            from nextt.parsing.word_parser import WordParser
            df = WordParser.parse(file_path)
            _load_foreign_file(main_window, df, file_path, append_mode=(choice == "add"))
            return

        # Всё остальное — через ExcelParser
        from nextt.parsing.excel_parser import ExcelParser
        df = ExcelParser.parse(file_path)

        # ========== ЧТЕНИЕ ПРОЕКТА ИЗ ЗАГРУЖАЕМОГО ФАЙЛА ==========
        _apply_loaded_project(main_window, file_path)
        # ============================================================

        # Проверяем: это артикулы LaggarTT?
        is_laggar = is_laggar_file(df)

        if is_laggar:
            success = _load_laggar_file(main_window, df)
            if not success:
                logger.info("Не удалось загрузить как файл LaggarTT, "
                            "переключаюсь на режим чужой спецификации")
                _load_foreign_file(main_window, df, file_path, append_mode=(choice == "add"))
        else:
            _load_foreign_file(main_window, df, file_path, append_mode=(choice == "add"))

    except ImportError as e:
        messagebox.showerror("Ошибка", str(e))
    except Exception as e:
        messagebox.showerror("Ошибка", f"Не удалось загрузить файл:\n{str(e)}")
        logger.error(f"Ошибка загрузки: {e}")


# ======================================================================
# Диалог «Добавить или заменить»
# ======================================================================

def _ask_add_or_replace(main_window) -> Optional[str]:
    """
    Показывает диалог выбора: добавить данные к существующим или заменить.
    Возвращает: "add", "replace" или None (отмена).
    """
    dialog = tk.Toplevel(main_window.root)
    dialog.title("Данные уже есть")
    dialog.transient(main_window.root)
    dialog.grab_set()
    dialog.resizable(False, False)
    dialog.configure(bg='#dedede')

    dialog.update_idletasks()
    w = 700
    h = 230
    screen_w = dialog.winfo_screenwidth()
    screen_h = dialog.winfo_screenheight()
    x = (screen_w - w) // 2
    y = (screen_h - h) // 2
    dialog.geometry(f"{w}x{h}+{x}+{y}")

    header_frame = tk.Frame(dialog, bg='#dedede')
    header_frame.pack(fill="x", padx=20, pady=(20, 0))

    tk.Label(
        header_frame, text="⚠️", font=("Segoe UI", 24),
        bg='#dedede', fg='#f39c12',
    ).pack(side="left", padx=(0, 10))

    tk.Label(
        header_frame, text="В матрице уже есть данные",
        font=("Segoe UI", 13, "bold"), bg='#dedede', fg='#444141',
    ).pack(side="left")

    tk.Label(
        dialog,
        text="Вы хотите добавить новые позиции к существующей спецификации\n"
             "или очистить матрицу и начать новую?",
        font=("Segoe UI", 10), bg='#dedede', fg='#444141',
        justify="center", wraplength=650,
    ).pack(pady=(15, 20))

    result = {"choice": None}

    def on_add():
        result["choice"] = "add"
        dialog.destroy()

    def on_replace():
        result["choice"] = "replace"
        dialog.destroy()

    def on_cancel():
        result["choice"] = None
        dialog.destroy()

    btn_frame = tk.Frame(dialog, bg='#dedede')
    btn_frame.pack(pady=(0, 20))

    for text, cmd, width in [
        ("Добавить к существующим", on_add, 30),
        ("Заменить (начать новую)", on_replace, 30),
        ("Отмена", on_cancel, 15),
    ]:
        tk.Button(
            btn_frame, text=text, command=cmd, width=width,
            bg='#263168', fg='white', font=("Segoe UI", 9),
            relief="flat", cursor="hand2",
            activebackground='#7E1A2F', activeforeground='white',
        ).pack(side="left", padx=5)

    dialog.wait_window()
    return result["choice"]


# ======================================================================
# Обработка PDF-файла
# ======================================================================

def _load_pdf_file(main_window, file_path: str, append_mode: bool = False) -> None:
    """Загружает данные из PDF-файла."""
    from nextt.parsing.pdf_parser import PDFParser, get_pdf_page_count

    try:
        total_pages = get_pdf_page_count(file_path)
        pages_to_parse = None

        if total_pages <= 5:
            pages_to_parse = list(range(1, total_pages + 1))
            logger.info(f"PDF содержит {total_pages} стр. (≤5) — читаем все страницы автоматически")
        else:
            from nextt.ui.dialogs.page_selector import PdfPageSelector
            selector = PdfPageSelector(
                main_window.root, total_pages, file_path,
                font_manager=main_window.app.font_manager,
            )
            main_window._page_selector = selector
            pages_to_parse = selector.show()
            main_window._page_selector = None

            if pages_to_parse is None:
                return

        if not pages_to_parse:
            messagebox.showwarning("Предупреждение", "Не выбрано ни одной страницы.")
            return

        # Прогресс-диалог
        progress = tk.Toplevel(main_window.root)
        progress.title("Обработка PDF")
        progress.transient(main_window.root)
        progress.grab_set()
        progress.geometry("400x120")
        screen_w = progress.winfo_screenwidth()
        screen_h = progress.winfo_screenheight()
        progress.geometry(f"+{(screen_w-400)//2}+{(screen_h-120)//2}")

        ttk.Label(progress, text="Обработка PDF-файла...",
                  font=("Segoe UI", 10)).pack(pady=10)
        prog_bar = ttk.Progressbar(progress, mode='determinate', length=350)
        prog_bar.pack(pady=5)
        prog_label = ttk.Label(progress, text="0%")
        prog_label.pack(pady=5)
        progress.update()

        def update_progress(current, total):
            pct = int((current / total) * 100)
            prog_bar['value'] = pct
            prog_label.config(text=f"{pct}% — страница {current} из {total}")
            progress.update()

        parser = PDFParser(progress_callback=update_progress)
        df = parser.parse_to_dataframe(file_path, pages=pages_to_parse)
        progress.destroy()

        if df.empty:
            messagebox.showwarning("PDF", "Не удалось извлечь данные из PDF.")
            return

        # Сохраняем исходные данные для повторного импорта
        main_window.app._last_raw_data = df.copy()
        main_window.app._last_file_path = file_path
        main_window.app._last_file_type = 'pdf'

        # ─── АВТОЗАПОЛНЕНИЕ ПОЛЯ «ПРОЕКТ» ИМЕНЕМ ФАЙЛА ───────────────
        _try_autofill_project_from_filename(main_window, file_path)
        # ─────────────────────────────────────────────────────────────

        # ========== ЧТЕНИЕ ПРОЕКТА ИЗ PDF ==========
        _apply_loaded_project_from_pdf(main_window, file_path)
        # ===========================================

        # Проверяем: содержит ли PDF артикулы LaggarTT?
        if is_laggar_file(df):
            logger.info("Автоопределение столбцов для LaggarTT PDF...")
            _load_laggar_pdf(main_window, df, file_path)
            return

        # Чужая спецификация — показываем ColumnSelector
        from nextt.parsing.column_selector import ColumnSelector
        strategy_data = {
            "По умолчанию": df,
            "Линии": df,
            "Сниппеты": df,
        }
        selector = ColumnSelector(
            main_window.root, strategy_data, file_path,
            main_window.app.font_manager,
        )
        result = selector.select()

        if result[0] is None:
            return

        pairs = result[0]
        for name_col, qty_col in pairs:
            _process_pdf_foreign_data(
                main_window, df, name_col, qty_col, file_path, append_mode
            )

    except ImportError as e:
        messagebox.showerror(
            "Ошибка",
            f"Для работы с PDF требуются библиотеки:\n"
            f"pip install pdfplumber PyMuPDF Pillow\n\n{str(e)}",
        )
    except Exception as e:
        messagebox.showerror("Ошибка", f"Не удалось обработать PDF:\n{str(e)}")
        logger.error(f"Ошибка загрузки PDF: {e}")
        import traceback
        logger.error(traceback.format_exc())


# ======================================================================
# ЧТЕНИЕ ПРОЕКТА ИЗ PDF
# ======================================================================

def _extract_project_from_pdf(file_path: str) -> Optional[str]:
    """
    Пытается прочитать название проекта из строки «Прочее:»
    на ПОСЛЕДНЕЙ странице PDF-файла.

    Логика:
        • Открываем PDF через fitz (PyMuPDF).
        • Берём только последнюю страницу.
        • Ищем строку, начинающуюся со слова «Прочее».
        • Значение берём:
            1) из ТОЙ ЖЕ строки — после разделителя «:», «—», «–», «-», «.»;
            2) если в этой строке значения нет — берём СЛЕДУЮЩУЮ
               непустую строку.

    Returns:
        Строка с названием проекта или None.
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        logger.debug("_extract_project_from_pdf: PyMuPDF (fitz) не установлен")
        return None

    try:
        doc = fitz.open(file_path)
    except Exception as e:
        logger.debug(f"_extract_project_from_pdf: не удалось открыть PDF: {e}")
        return None

    try:
        if doc.page_count == 0:
            return None

        # Только последняя страница
        page = doc[doc.page_count - 1]
        text = page.get_text("text")

        if not text:
            return None

        lines = text.splitlines()

        for i, line in enumerate(lines):
            line_stripped = line.strip()
            if not line_stripped:
                continue

            line_lower = line_stripped.lower()
            if not line_lower.startswith("прочее"):
                continue

            # Отрезаем слово «Прочее»
            rest = line_stripped[len("прочее"):].strip()

            # Убираем ведущий разделитель
            if rest and rest[0] in (':', '—', '–', '-', '.'):
                rest = rest[1:].strip()

            # Если значение в этой же строке — возвращаем
            if rest:
                return rest

            # Иначе — ищем следующую непустую строку
            for j in range(i + 1, len(lines)):
                next_line = lines[j].strip()
                if not next_line:
                    continue
                return next_line

            return None

        return None

    except Exception as e:
        logger.debug(f"_extract_project_from_pdf: ошибка чтения: {e}")
        return None
    finally:
        try:
            doc.close()
        except Exception:
            pass

# ======================================================================
# АВТОЗАПОЛНЕНИЕ ПОЛЯ «ПРОЕКТ» ИМЕНЕМ ФАЙЛА
# ======================================================================

def _try_autofill_project_from_filename(main_window, file_path: str) -> None:
    """
    Если поле «Проект» пустое — подставляет в него имя загруженного файла
    без расширения. Используется для «чужих» спецификаций (Excel/CSV/PDF/Word),
    в которых нет карточки «ПРОЕКТ» или строки «Прочее:».

    Логика:
        • Если поле «Проект» уже заполнено (вручную или ранее) — не трогаем.
        • Если файл не найден или путь пустой — выходим.
        • Имя файла очищается от недопустимых символов Windows
          (тот же алгоритм, что и в main_window_export._sanitize_filename_part)
          — чтобы при экспорте не было двойной очистки.
        • Результат обрезается до 120 символов (запас для суффикса «(1)»,
          «(2)» при сохранении).

    Вызывается ДО _apply_loaded_project / _apply_loaded_project_from_pdf —
    чтобы карточка «ПРОЕКТ» из файла, если она есть, имела приоритет
    и могла перебить имя файла с подтверждением пользователя.
    """
    import os
    import re
    from pathlib import Path

    if not file_path:
        return

    # Проверяем, что поле существует и пустое
    try:
        current = (main_window.project_var.get() or "").strip()
    except Exception:
        return

    if current:
        # Пользователь уже что-то ввёл — не перебиваем
        return

    # Берём имя файла без расширения
    try:
        stem = Path(file_path).stem
    except Exception:
        return

    if not stem:
        return

    # Очищаем имя: тот же набор замен, что в _sanitize_filename_part
    # (см. main_window_export.py)
    cleaned = re.sub(r'[\\/:*?"<>|\r\n\t]+', '_', str(stem))
    cleaned = re.sub(r'_+', '_', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned)
    cleaned = cleaned.strip('._ ')

    if not cleaned:
        return

    # Ограничиваем длину — чтобы при сохранении было место для «(1)», «(2)»
    MAX_LEN = 120
    if len(cleaned) > MAX_LEN:
        cleaned = cleaned[:MAX_LEN - 1].rstrip() + "…"

    try:
        main_window.project_var.set(cleaned)
        logger.info(
            f"Поле «Проект» автоматически заполнено именем файла: "
            f"'{cleaned}' (из '{os.path.basename(file_path)}')"
        )
    except Exception as e:
        logger.debug(f"Не удалось автозаполнить поле «Проект»: {e}")

def _apply_loaded_project_from_pdf(main_window, file_path: str) -> None:
    """
    Читает проект из последней страницы PDF («Прочее:») и,
    если нужно, применяет его к полю main_window.project_var.
    """
    from tkinter import messagebox

    file_project = _extract_project_from_pdf(file_path)
    if not file_project:
        return

    current_project = ""
    try:
        current_project = (main_window.project_var.get() or "").strip()
    except Exception:
        pass

    if not current_project:
        answer = messagebox.askyesno(
            "Информация о проекте",
            f"В загруженном PDF найден проект:\n\n"
            f"«{file_project}»\n\n"
            f"Подставить его в поле «Проект»?",
            parent=main_window.root,
        )
        if answer:
            try:
                main_window.project_var.set(file_project)
            except Exception:
                pass
        return

    if current_project == file_project:
        return

    answer = messagebox.askyesno(
        "Конфликт проектов",
        f"Текущий проект:\n"
        f"«{current_project}»\n\n"
        f"Проект из PDF:\n"
        f"«{file_project}»\n\n"
        f"Заменить текущий проект на проект из PDF?",
        parent=main_window.root,
    )
    if answer:
        try:
            main_window.project_var.set(file_project)
        except Exception:
            pass


# ======================================================================
# ЧТЕНИЕ ПРОЕКТА ИЗ EXCEL
# ======================================================================

def _extract_project_from_excel(file_path: str) -> Optional[str]:
    """Читает карточку «ПРОЕКТ» из шапки Excel-файла NexTT."""
    try:
        from openpyxl import load_workbook
    except ImportError:
        return None

    try:
        wb = load_workbook(file_path, read_only=True, data_only=True)
    except Exception as e:
        logger.debug(f"_extract_project_from_excel: не удалось открыть файл: {e}")
        return None

    try:
        if not wb.sheetnames:
            return None
        sheet = wb[wb.sheetnames[0]]

        max_row = min(10, sheet.max_row or 10)
        max_col = min(20, sheet.max_column or 20)

        for row_idx in range(1, max_row + 1):
            for col_idx in range(1, max_col + 1):
                cell = sheet.cell(row=row_idx, column=col_idx)
                value = cell.value

                if value is None:
                    continue

                key_text = str(value).strip().upper()
                if key_text == "ПРОЕКТ":
                    value_cell = sheet.cell(row=row_idx + 1, column=col_idx)
                    project_value = value_cell.value
                    if project_value is None:
                        return None
                    project_str = str(project_value).strip()
                    if not project_str:
                        return None
                    if project_str in ("—", "-", "–", "—"):
                        return None
                    return project_str

        return None

    except Exception as e:
        logger.debug(f"_extract_project_from_excel: ошибка чтения: {e}")
        return None
    finally:
        try:
            wb.close()
        except Exception:
            pass


def _extract_project_from_prochee(file_path: str) -> Optional[str]:
    """Читает строку «Прочее:» из Excel-файла."""
    try:
        from openpyxl import load_workbook
    except ImportError:
        return None

    try:
        wb = load_workbook(file_path, read_only=True, data_only=True)
    except Exception as e:
        logger.debug(f"_extract_project_from_prochee: не удалось открыть файл: {e}")
        return None

    try:
        for sheet_name in wb.sheetnames:
            sheet = wb[sheet_name]

            max_row = min(200, sheet.max_row or 200)
            max_col = min(20, sheet.max_column or 20)

            for row_idx in range(1, max_row + 1):
                for col_idx in range(1, max_col + 1):
                    cell = sheet.cell(row=row_idx, column=col_idx)
                    value = cell.value

                    if value is None:
                        continue

                    text = str(value).strip()
                    if not text:
                        continue

                    text_lower = text.lower()
                    if not text_lower.startswith("прочее"):
                        continue

                    rest = text[len("прочее"):].strip()

                    if rest and rest[0] in (':', '—', '–', '-', '.'):
                        rest = rest[1:].strip()

                    if rest:
                        return rest

        return None

    except Exception as e:
        logger.debug(f"_extract_project_from_prochee: ошибка чтения: {e}")
        return None
    finally:
        try:
            wb.close()
        except Exception:
            pass


def _apply_loaded_project(main_window, file_path: str) -> None:
    """
    Читает проект из Excel-файла: сначала карточка «ПРОЕКТ»,
    потом строка «Прочее:». Применяет с подтверждением пользователя.
    """
    from tkinter import messagebox

    file_project = _extract_project_from_excel(file_path)
    if not file_project:
        file_project = _extract_project_from_prochee(file_path)

    if not file_project:
        return

    current_project = ""
    try:
        current_project = (main_window.project_var.get() or "").strip()
    except Exception:
        pass

    if not current_project:
        answer = messagebox.askyesno(
            "Информация о проекте",
            f"В загруженном файле найден проект:\n\n"
            f"«{file_project}»\n\n"
            f"Подставить его в поле «Проект»?",
            parent=main_window.root,
        )
        if answer:
            try:
                main_window.project_var.set(file_project)
            except Exception:
                pass
        return

    if current_project == file_project:
        return

    answer = messagebox.askyesno(
        "Конфликт проектов",
        f"Текущий проект:\n"
        f"«{current_project}»\n\n"
        f"Проект из файла:\n"
        f"«{file_project}»\n\n"
        f"Заменить текущий проект на проект из файла?",
        parent=main_window.root,
    )
    if answer:
        try:
            main_window.project_var.set(file_project)
        except Exception:
            pass


# ======================================================================
# Загрузка LaggarTT PDF
# ======================================================================

def _load_laggar_pdf(main_window, df: pd.DataFrame, file_path: str) -> None:
    """Автоматически определяет столбцы артикулов и количества в LaggarTT PDF."""
    import re as _re

    art_col = None
    qty_col = None
    header_row = -1

    for row_idx in range(min(5, len(df))):
        has_article = False
        has_quantity = False
        art_col_candidate = -1
        qty_col_candidate = -1

        for col_idx in range(len(df.columns)):
            cell = str(df.iloc[row_idx, col_idx]).strip().lower()
            if len(cell) < 30:
                if not has_article and cell in ['артикул', 'article', 'art', 'код']:
                    has_article = True
                    art_col_candidate = col_idx
                if not has_quantity and any(kw in cell for kw in ['кол-во', 'количество', 'qty', 'quantity']):
                    has_quantity = True
                    qty_col_candidate = col_idx

        if has_article and has_quantity:
            header_row = row_idx
            art_col = art_col_candidate
            qty_col = qty_col_candidate
            break

    if art_col is None:
        pattern = _re.compile(r'7724[67]\d{5}')
        best_match_col = -1
        best_match_count = 0
        for col_idx in range(len(df.columns)):
            col_values = df.iloc[:, col_idx].astype(str)
            matches = sum(1 for v in col_values if pattern.search(str(v)))
            if matches > best_match_count:
                best_match_count = matches
                best_match_col = col_idx

        if best_match_count >= 2:
            art_col = best_match_col

    if qty_col is None:
        data_start_row = header_row + 1 if header_row >= 0 else 1
        best_qty_col = -1
        best_qty_count = 0
        for col_idx in range(len(df.columns)):
            if col_idx == art_col:
                continue
            numeric_count = 0
            for row_idx in range(data_start_row, min(data_start_row + 20, len(df))):
                try:
                    val = str(df.iloc[row_idx, col_idx]).strip()
                    num_match = _re.search(r'^(\d+)$', val.replace(' ', ''))
                    if num_match:
                        num = int(num_match.group(1))
                        if 1 <= num <= 10000:
                            numeric_count += 1
                except Exception:
                    pass
            if numeric_count > best_qty_count:
                best_qty_count = numeric_count
                best_qty_col = col_idx

        if best_qty_count >= 2:
            qty_col = best_qty_col

    if art_col is not None and qty_col is not None:
        _process_laggar_pdf_data(main_window, df, art_col, qty_col)
    else:
        logger.warning("Не удалось автоопределить столбцы. Показываем ColumnSelector.")
        from nextt.parsing.column_selector import ColumnSelector
        strategy_data = {"По умолчанию": df, "Линии": df, "Сниппеты": df}
        selector = ColumnSelector(
            main_window.root, strategy_data, file_path,
            main_window.app.font_manager,
        )
        result = selector.select()
        if result[0] is not None:
            pairs = result[0]
            art_col, qty_col = pairs[0]
            _process_laggar_pdf_data(main_window, df, art_col, qty_col)
        else:
            messagebox.showwarning("Предупреждение", "Не удалось определить столбцы.")


def _process_laggar_pdf_data(main_window, df: pd.DataFrame,
                             art_col: int, qty_col: int) -> None:
    """Заполняет матрицу радиаторов данными из распарсенного PDF."""
    import re as _re

    header_row = 0
    for i in range(min(10, len(df))):
        row_text = ' '.join(
            str(df.iloc[i, col]) for col in range(len(df.columns))
            if col < len(df.columns)
        )
        if any(kw in row_text.lower() for kw in ['артикул', 'наименование', 'товар']):
            header_row = i
            break

    main_window.app.entry_values.clear()
    total = 0
    total_qty = 0

    for i in range(header_row + 1, len(df)):
        if art_col >= len(df.columns) or qty_col >= len(df.columns):
            continue

        art = str(df.iloc[i, art_col]).strip()
        qty_str = str(df.iloc[i, qty_col]).strip()

        if not art or art.lower() in ('итого', 'всего'):
            continue

        art_clean = _re.sub(r'\D', '', art)
        if not art_clean:
            continue

        if not (art_clean.startswith('77246') or art_clean.startswith('77247') or
                art.startswith('К') or art.startswith('K')):
            continue

        try:
            cleaned_qty = _re.sub(r'\s+', '', str(qty_str))
            qty_match = _re.search(r'(\d+)', cleaned_qty.replace(',', '.'))
            if qty_match:
                qty = int(qty_match.group(1))
            else:
                qty = int(float(cleaned_qty.replace(',', '.')))
            if qty <= 0:
                continue
        except (ValueError, TypeError):
            continue

        meteor_art, _ = main_window.app.data_provider.convert_meteor_to_laggar(art)
        if meteor_art:
            found = main_window.app.data_provider.find_by_article(meteor_art)
            if found is not None:
                conn = found.get('Connection', '')
                rt = found.get('RadiatorType', '')
                if conn and rt:
                    key = (f"{conn} {rt}", meteor_art)
                    existing = main_window.app.entry_values.get(key, "")
                    if existing:
                        try:
                            new_val = str(int(existing) + qty)
                        except ValueError:
                            new_val = f"{existing}+{qty}"
                    else:
                        new_val = str(qty)
                    main_window.app.entry_values[key] = new_val
                    total += 1
                    total_qty += qty
        else:
            found = main_window.app.data_provider.find_by_article(art)
            if found is not None:
                conn = found.get('Connection', '')
                rt = found.get('RadiatorType', '')
                if conn and rt:
                    key = (f"{conn} {rt}", art)
                    existing = main_window.app.entry_values.get(key, "")
                    if existing:
                        try:
                            new_val = str(int(existing) + qty)
                        except ValueError:
                            new_val = f"{existing}+{qty}"
                    else:
                        new_val = str(qty)
                    main_window.app.entry_values[key] = new_val
                    total += 1
                    total_qty += qty

    main_window._build_matrix(
        main_window._conn_var.get(), main_window._type_var.get()
    )

    if total > 0:
        spec_data = main_window.app.spec_generator.prepare_spec_data(
            entry_values=main_window.app.entry_values,
            bracket_type=main_window.bracket_var.get(),
            radiator_discount=float(main_window.radiator_discount_var.get() or 0),
            bracket_discount=float(main_window.bracket_discount_var.get() or 0),
        )

        if spec_data is not None and not spec_data.empty:
            from nextt.ui.dialogs.preview import PreviewDialog
            preview = PreviewDialog(main_window.app)
            preview.show(spec_data)
        else:
            messagebox.showinfo(
                "Успех",
                f"Загружено позиций: {total}\n"
                f"Общее количество радиаторов: {total_qty}",
            )
    else:
        messagebox.showwarning(
            "Предупреждение",
            "Не найдено подходящих артикулов LaggarTT в файле.",
        )


# ======================================================================
# Загрузка LaggarTT Excel
# ======================================================================

def _load_laggar_file(main_window, df: pd.DataFrame) -> bool:
    """Загружает файл с артикулами LaggarTT. Возвращает True при успехе."""
    from nextt.parsing.excel_parser import ExcelParser

    art_col, qty_col = ExcelParser.find_columns(df)

    if art_col is None:
        logger.warning("Не удалось найти столбец с артикулами в файле LaggarTT")
        return False

    if qty_col is None:
        qty_col = ExcelParser.auto_detect_qty_column(df)
        if qty_col is None:
            logger.warning("Не удалось найти столбец с количеством в файле LaggarTT")
            return False

    header_row = 0
    for i in range(min(10, len(df))):
        row_text = ' '.join(
            str(df.iloc[i, col]) for col in range(len(df.columns))
            if col < len(df.columns)
        )
        if any(kw in row_text.lower() for kw in ['артикул', 'наименование', 'товар', 'код']):
            header_row = i
            break

    loaded_count = 0
    total_qty = 0

    for i in range(header_row + 1, len(df)):
        if art_col >= len(df.columns) or qty_col >= len(df.columns):
            continue

        art = str(df.iloc[i, art_col]).strip()
        qty_str = str(df.iloc[i, qty_col]).strip()

        if not art or art.lower() == 'итого':
            continue

        try:
            cleaned_qty = re.sub(r'\s+', '', str(qty_str))
            qty = int(float(cleaned_qty.replace(',', '.')))
            if qty <= 0:
                continue
        except (ValueError, TypeError):
            continue

        meteor_art, _ = main_window.app.data_provider.convert_meteor_to_laggar(art)
        if meteor_art:
            found = main_window.app.data_provider.find_by_article(meteor_art)
            if found is not None:
                conn = found.get('Connection', '')
                rt = found.get('RadiatorType', '')
                if conn and rt:
                    key = (f"{conn} {rt}", meteor_art)
                    existing = main_window.app.entry_values.get(key, "")
                    if existing:
                        try:
                            new_val = str(int(existing) + qty)
                        except ValueError:
                            new_val = f"{existing}+{qty}"
                    else:
                        new_val = str(qty)
                    main_window.app.entry_values[key] = new_val
                    loaded_count += 1
                    total_qty += qty

    if loaded_count == 0:
        logger.warning("Не найдено подходящих артикулов LaggarTT в файле")
        return False

    main_window._build_matrix(
        main_window._conn_var.get(), main_window._type_var.get()
    )

    spec_data = main_window.app.spec_generator.prepare_spec_data(
        entry_values=main_window.app.entry_values,
        bracket_type=main_window.bracket_var.get(),
        radiator_discount=float(main_window.radiator_discount_var.get() or 0),
        bracket_discount=float(main_window.bracket_discount_var.get() or 0),
    )

    if spec_data is not None and not spec_data.empty:
        from nextt.ui.dialogs.preview import PreviewDialog
        preview = PreviewDialog(main_window.app)
        preview.show(spec_data)
    else:
        messagebox.showinfo(
            "Успех",
            f"Загружено позиций: {loaded_count}\nОбщее количество: {total_qty}",
        )

    return True


# ======================================================================
# Загрузка чужой спецификации
# ======================================================================

def _load_foreign_file(main_window, df: pd.DataFrame, file_path: str,
                       append_mode: bool = False) -> None:
    """Загружает чужую спецификацию с парсингом названий."""
    main_window.app._last_raw_data = df.copy()
    main_window.app._last_file_path = file_path
    main_window.app._last_file_type = 'excel'

    main_window.app._last_active_scenario = "foreign"

    # ─── АВТОЗАПОЛНЕНИЕ ПОЛЯ «ПРОЕКТ» ИМЕНЕМ ФАЙЛА ───────────────────
    # Делаем это ДО чтения карточки «ПРОЕКТ» из файла — чтобы карточка,
    # если она есть, могла перебить имя файла с подтверждением пользователя.
    _try_autofill_project_from_filename(main_window, file_path)
    # ─────────────────────────────────────────────────────────────────

    from nextt.parsing.column_selector import ColumnSelector

    if hasattr(main_window.app, '_last_imported_file') and \
       main_window.app._last_imported_file == file_path:
        actual_append_mode = True
        logger.info(f"Повторный импорт Excel: объединяем данные (append_mode=True)")
    else:
        actual_append_mode = False
        logger.info(f"Первый импорт Excel: заменяем данные (append_mode=False)")
        main_window.app._last_imported_file = file_path

    selector = ColumnSelector(
        main_window.root, df, file_path, main_window.app.font_manager
    )
    result = selector.select()

    if result[0] is None:
        return

    pairs = result[0]
    for name_col, qty_col in pairs:
        _process_excel_foreign_data(
            main_window, df, name_col, qty_col, file_path,
            append_mode=actual_append_mode,
        )


# ======================================================================
# Обработка Excel/CSV «чужой» спецификации
# ======================================================================

def _process_excel_foreign_data(main_window, df, name_col_idx: int,
                                qty_col_idx: int, file_path: str,
                                append_mode: bool = False) -> None:
    """Обрабатывает данные из Excel/CSV."""
    logger.info("=" * 70)
    logger.info("НАЧАЛО ОБРАБОТКИ ДАННЫХ (Excel/CSV)")
    logger.info(f"Файл: {file_path}")
    logger.info(f"Столбец названий: {name_col_idx}, столбец количества: {qty_col_idx}")
    logger.info("=" * 70)

    logger.info(f"  [DF] Всего строк в DataFrame: {len(df)}")
    for dbg_idx in range(len(df)):
        dbg_row = df.iloc[dbg_idx]
        dbg_name = str(dbg_row.iloc[name_col_idx]).strip() if name_col_idx < len(dbg_row) else ""
        dbg_qty = str(dbg_row.iloc[qty_col_idx]).strip() if qty_col_idx < len(dbg_row) else ""
        logger.info(f"  [DF] Строка {dbg_idx}: name='{dbg_name}', qty='{dbg_qty}'")

    parsed_rows = []
    skipped_empty = 0
    skipped_zero_qty = 0

    for i, (_, row) in enumerate(df.iterrows()):
        if name_col_idx >= len(row) or qty_col_idx >= len(row):
            continue

        original = str(row.iloc[name_col_idx]).strip()
        qty_str = str(row.iloc[qty_col_idx]).strip()

        if not original:
            skipped_empty += 1
            continue

        try:
            qty = parse_qty(qty_str)
            if qty <= 0:
                skipped_zero_qty += 1
                continue
        except (ValueError, TypeError):
            skipped_zero_qty += 1
            continue

        logger.info(f"  [ВХОД] row={i}, qty_str='{qty_str}', original='{original}'")
        parsed = main_window.app.normalizer.normalize_and_extract(original)

        parsed_rows.append({
            "original": original,
            "qty": qty,
            "parsed": parsed,
        })

    total_rows = len(parsed_rows)

    if not parsed_rows:
        messagebox.showwarning("Предупреждение", "Не удалось извлечь данные.")
        return

    data_for_table = []
    total_found = 0
    total_not_found = 0

    from nextt.patterns.template_manager import TemplateManager
    _template_manager = TemplateManager()

    for idx, item in enumerate(parsed_rows, 1):
        original_name_str = item["original"]
        qty = item["qty"]
        parsed = item["parsed"]

        meteor_art = ""
        meteor_name = ""
        source = "Не подобрано"

        try:
            template_result = _template_manager.apply_templates(original_name_str)

            if template_result:
                art, name = main_window.app.data_provider.find_analog(
                    template_result['connection'],
                    template_result['rad_type'],
                    template_result['height'],
                    template_result['length'],
                )
                if art:
                    meteor_art = art
                    meteor_name = name
                    source = "По образцу (шаблон)"
                    total_found += 1
        except Exception as e:
            logger.error(f"Ошибка проверки шаблонов: {e}")

        if not meteor_art and parsed.recognized:
            connection_to_use = parsed.connection
            if parsed.connection == "VK-левое" and parsed.rad_type in ('20', '21', '22'):
                connection_to_use = "VK-правое"

            art, name = main_window.app.data_provider.find_analog(
                connection_to_use, parsed.rad_type,
                parsed.height, parsed.length,
            )
            if art:
                meteor_art = art
                meteor_name = name
                source = "Автоматически"
                total_found += 1

        if not meteor_art:
            total_not_found += 1

        data_for_table.append({
            "Наименование": original_name_str,
            "Кол-во": qty,
            "Наименование LaggarTT": meteor_name,
            "Артикул LaggarTT": meteor_art,
            "Источник": source,
        })

    from nextt.ui.dialogs.correspondence import CorrespondenceDialog
    dialog = CorrespondenceDialog(main_window.app)
    main_window.app._last_correspondence_dialog = dialog
    dialog.show(pd.DataFrame(data_for_table))


# ======================================================================
# Обработка Word «чужой» спецификации
# ======================================================================

def _process_word_foreign_data(main_window, df: pd.DataFrame,
                               file_path: str, append_mode: bool = False) -> None:
    """Обрабатывает данные из Word-файла."""
    _process_excel_foreign_data(
        main_window, df, 0, 1, file_path, append_mode
    )


# ======================================================================
# Обработка PDF «чужой» спецификации
# ======================================================================

def _process_pdf_foreign_data(main_window, df: pd.DataFrame,
                              name_col_idx: int, qty_col_idx: int,
                              file_path: str, append_mode: bool = False) -> None:
    """Обрабатывает данные из PDF-файла."""
    logger.info("=" * 70)
    logger.info("НАЧАЛО ОБРАБОТКИ ДАННЫХ (PDF)")
    logger.info(f"Файл: {file_path}")
    logger.info(f"Столбец названий: {name_col_idx}, столбец количества: {qty_col_idx}")
    logger.info(f"Всего столбцов в DataFrame: {len(df.columns)}")
    logger.info("=" * 70)

    logger.info("  [RAW] Первые 5 строк DataFrame целиком:")
    for dbg_idx in range(min(5, len(df))):
        dbg_row = df.iloc[dbg_idx]
        values_repr = [f"[{i}]='{str(v)}'" for i, v in enumerate(dbg_row.values)]
        logger.info(f"  [RAW] Строка {dbg_idx}: {' | '.join(values_repr)}")

    logger.info("  [RAW] Столбец наименования (name_col_idx=%d), первые 5 значений:", name_col_idx)
    if name_col_idx < len(df.columns):
        for dbg_idx in range(min(5, len(df))):
            dbg_val = df.iloc[dbg_idx, name_col_idx]
            logger.info(f"  [RAW]   [{dbg_idx}] = '{str(dbg_val)}'")
    else:
        logger.warning(f"  [RAW] name_col_idx={name_col_idx} вне диапазона столбцов!")

    logger.info("  [RAW] Столбец количества (qty_col_idx=%d), первые 5 значений:", qty_col_idx)
    if qty_col_idx < len(df.columns):
        for dbg_idx in range(min(5, len(df))):
            dbg_val = df.iloc[dbg_idx, qty_col_idx]
            logger.info(f"  [RAW]   [{dbg_idx}] = '{str(dbg_val)}'")
    else:
        logger.warning(f"  [RAW] qty_col_idx={qty_col_idx} вне диапазона столбцов!")

    name_to_qty = {}
    name_to_full_text = {}
    skipped_empty = 0
    skipped_zero_qty = 0

    for i, (_, row) in enumerate(df.iterrows()):
        if name_col_idx >= len(row) or qty_col_idx >= len(row):
            continue

        original_name = str(row.iloc[name_col_idx]).strip() if row.iloc[name_col_idx] is not None else ""
        qty_str = str(row.iloc[qty_col_idx]).strip() if row.iloc[qty_col_idx] is not None else ""

        if original_name:
            logger.info(f"  [ВХОД] row={i}, name='{original_name[:80]}', qty_raw='{qty_str}'")

        if not original_name:
            skipped_empty += 1
            continue

        try:
            qty = parse_qty(qty_str)
            if qty <= 0:
                skipped_zero_qty += 1
                continue
        except (ValueError, TypeError):
            skipped_zero_qty += 1
            continue

        if original_name in name_to_qty:
            name_to_qty[original_name] += qty
        else:
            name_to_qty[original_name] = qty
            name_to_full_text[original_name] = ' '.join(
                str(cell) for cell in row if pd.notna(cell)
            ).strip()

    logger.info(f"  [ИТОГ] Собрано уникальных позиций: {len(name_to_qty)}")
    logger.info(f"  [ИТОГ] Пропущено пустых: {skipped_empty}, нулевых: {skipped_zero_qty}")

    garbage_keywords = [
        'гост', 'труба', 'изоляция', 'k-flex', 'rockwool', 'isotec', 'кожух',
        'цилиндр', 'минеральная вата', 'краска', 'гильза',
        'кран', 'клапан', 'фильтр', 'воздухоотводчик', 'теплосчётчик', 'пульсар',
        'коллектор', 'насос', 'шаровой', 'балансировочный', 'термостатический',
        'монтаж', 'пуско-наладочные', 'итого', 'секция', 'статья', 'всего',
    ]
    radiator_keywords = [
        'радиатор', 'kermi', 'ftv', 'fk0', 'fko', 'profil-v', 'profil-k',
        'royal thermo', 'vc', 'vk-profil', 'k-profil', 'evra', 'oasis',
        'hv', 'fhv', 'cv', 'сv', 'c22', 'universal', 'compact', 'ventil',
        'конвектор', 'панельный', 'стальной', 'laggar', 'meteor', 'prado',
    ]

    filtered_names = {}
    for name, qty in name_to_qty.items():
        name_lower = name.lower()
        is_radiator = any(kw in name_lower for kw in radiator_keywords)
        has_triplet = len(re.findall(r'\d{2,4}', name)) >= 3
        has_size = re.search(r'\d{3,4}[xх]\d{3,4}', name_lower) is not None
        is_garbage = any(kw in name_lower for kw in garbage_keywords)

        if is_radiator or has_triplet or has_size:
            filtered_names[name] = qty
        elif not is_garbage:
            filtered_names[name] = qty

    if not filtered_names:
        messagebox.showwarning("Предупреждение", "После фильтрации не осталось данных.")
        return

    data_for_table = []

    from nextt.patterns.template_manager import TemplateManager
    _template_manager = TemplateManager()

    for idx, (original_name_str, qty) in enumerate(filtered_names.items(), 1):
        meteor_art = ""
        meteor_name = ""
        source = "Не подобрано"

        try:
            template_result = _template_manager.apply_templates(original_name_str)

            if template_result:
                art, name = main_window.app.data_provider.find_analog(
                    template_result['connection'],
                    template_result['rad_type'],
                    template_result['height'],
                    template_result['length'],
                )
                if art:
                    meteor_art = art
                    meteor_name = name
                    source = "По образцу (шаблон)"
        except Exception as e:
            logger.error(f"Ошибка проверки шаблонов: {e}")

        if not meteor_art:
            parsed = main_window.app.normalizer.normalize_and_extract(original_name_str)
            if parsed.recognized:
                connection_to_use = parsed.connection
                if parsed.connection == "VK-левое" and parsed.rad_type in ('20', '21', '22'):
                    connection_to_use = "VK-правое"

                art, name = main_window.app.data_provider.find_analog(
                    connection_to_use, parsed.rad_type,
                    parsed.height, parsed.length,
                )
                if art:
                    meteor_art = art
                    meteor_name = name
                    source = "Автоматически"

        data_for_table.append({
            "Наименование": original_name_str,
            "Кол-во": qty,
            "Наименование LaggarTT": meteor_name,
            "Артикул LaggarTT": meteor_art,
            "Источник": source,
        })

    from nextt.ui.dialogs.correspondence import CorrespondenceDialog
    dialog = CorrespondenceDialog(main_window.app)
    main_window.app._last_correspondence_dialog = dialog
    dialog.show(pd.DataFrame(data_for_table))


# ======================================================================
# Утилита: парсинг диапазона страниц
# ======================================================================

def _parse_page_range(range_str: str, total_pages: int) -> Optional[List[int]]:
    """Парсит строку диапазона страниц."""
    pages = []
    parts = range_str.split(',')

    for part in parts:
        part = part.strip()
        if not part:
            continue
        if '-' in part:
            try:
                start, end = part.split('-')
                start = int(start.strip())
                end = int(end.strip())
                if 1 <= start <= total_pages and 1 <= end <= total_pages and start <= end:
                    pages.extend(range(start, end + 1))
                else:
                    return None
            except ValueError:
                return None
        else:
            try:
                page = int(part)
                if 1 <= page <= total_pages:
                    pages.append(page)
                else:
                    return None
            except ValueError:
                return None

    return sorted(set(pages)) if pages else None