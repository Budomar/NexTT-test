"""
PDF-парсер для извлечения таблиц с радиаторами.
Поддерживает три стратегии извлечения, объединение многострочных ячеек,
быструю проверку страниц и выбор страниц для обработки.
"""

import os
import re
from typing import Optional, List, Callable, Tuple, Dict, Any
from datetime import datetime

import pandas as pd

from nextt.logger import get_logger

logger = get_logger(__name__)

# Пытаемся импортировать pdfplumber
try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False
    logger.warning("pdfplumber не установлен. Установите: pip install pdfplumber")


class PDFParser:
    """
    УНИВЕРСАЛЬНЫЙ ВСЕЯДНЫЙ ПАРСЕР PDF
    Автоматизирует чтение, парсинг и переподбор данных из PDF в DataFrame
    С поддержкой выбора страниц, быстрой проверкой и тремя стратегиями
    """

    # Ключевые слова для быстрой проверки страниц
    RADIATOR_KEYWORDS = [
        # Основные термины
        'радиатор', 'радиаторный', 'радиаторная', 'радиаторное', 'радиаторные',
        'стальной', 'панельный', 'панельная', 'панельное', 'панельные',
        'отопление', 'отопительный', 'отопительная', 'отопительное',
        'конвектор', 'конвекторный',

        # Типы и серии
        'тип 11', 'тип 22', 'тип 33', 'тип 21', 'тип 23', 'тип 10', 'тип 20',
        'h33', 'h22', 'h21', 'c21', 'c22', 'h33-', 'h22-', 'h21-', 'c11',
        'compact', 'ventil', 'гигиенический', 'hygiene', 'универсал',

        # Бренды
        'royal', 'thermo', 'royal thermo', 'buderus', 'kermi', 'purmo',
        'evra', 'hiterm', 'cv', 'ftv', 'fto', 'ftk',

        # Подключение
        'нижним подключением', 'боковым подключением',
        'нижнее подключение', 'боковое подключение',
        'универсальное подключение',

        # Размеры
        'высотой', 'длиной', 'l=', 'высота', 'длина', 'ширина', 'глубина',

        # Английские термины
        'radiator', 'panel', 'heater', 'steel', 'radiators', 'convector',
        'panel radiator', 'steel panel',

        # Для спецификаций
        'спецификация', 'ведомость', 'оборудование', 'материалы',
        'позиция', 'наименование', 'марка', 'тип',

        # Единицы измерения
        'шт', 'шт.', 'ед', 'ед.', 'pcs', 'pc', 'qty', 'quantity',
        'кол-во', 'количество', 'единиц',

        # Мощность
        'вт', 'ватт', 'watt', 'qn', 'qp', 'мощность', 'теплоотдача',
    ]

    def __init__(self, progress_callback: Optional[Callable[[int, int], None]] = None):
        """
        Инициализация парсера

        Args:
            progress_callback: Функция обратного вызова для отслеживания прогресса: callback(current_page, total_pages)
        """
        self.progress_callback = progress_callback
        self.debug = True

    def _log(self, message: str, level: str = "INFO") -> None:
        """Логирование"""
        timestamp = datetime.now().strftime('%H:%M:%S')
        if level == "ERROR":
            logger.error(f"[{timestamp}][PDF] {message}")
        elif level == "WARNING":
            logger.warning(f"[{timestamp}][PDF] {message}")
        else:
            logger.info(f"[{timestamp}][PDF] {message}")

    # ==================================================================
    # БЫСТРАЯ ПРОВЕРКА СТРАНИЦЫ
    # ==================================================================

    def _should_process_page(self, page, page_num: int) -> bool:
        """
        Быстрая проверка, стоит ли обрабатывать страницу
        Возвращает True если на странице есть признаки таблиц с радиаторами
        """
        if not HAS_PDFPLUMBER:
            return True

        try:
            text = page.extract_text()
            if not text or len(text.strip()) < 50:
                self._log(f"📄 Страница {page_num}: ПРОПУСК (мало текста)", "WARNING")
                return False

            text_lower = text.lower()

            # Проверяем наличие ключевых слов
            found_keywords = [kw for kw in self.RADIATOR_KEYWORDS if kw in text_lower]

            # Проверяем паттерны радиаторов
            radiator_patterns = [
                r'\b[HСCКK]\d{1,2}[-\s]*\d{3,4}[-\s]*\d{3,4}\b',
                r'\bPURMO\s+[CHK]\s*\d{1,2}',
                r'\bтип\s*\d+\s*[Ll]\s*[=:]\s*\d+\s*мм',
                r'\bвысотой\s*\d+\s*мм',
                r'\bдлин[аой]\s*\d+\s*мм',
                r'\b\d{3,4}\s*[xх×]\s*\d{3,4}\s*Вт\b',
                r'\b[Qq][нp]\s*[=:]\s*\d+\s*Вт\b',
                r'\b(?:радиатор|конвектор)\s*[^.]{0,50}\d+\s*шт\b',
            ]

            found_patterns = []
            for pattern in radiator_patterns:
                if re.search(pattern, text_lower, re.IGNORECASE):
                    found_patterns.append(pattern)

            # Проверяем наличие столбца количества
            has_quantity_column = re.search(
                r'коли[ -]?чество|кол[ -]?во|ед\.|шт\.|pcs|pc|qty|единиц|штук',
                text_lower
            )

            # Проверяем наличие заголовка спецификации
            has_spec_header = re.search(
                r'спецификация|ведомость|оборудован[иея]|материал[ыов]|позиция|наименование',
                text_lower
            )

            # Критерии для обработки страницы
            should_process = (
                (len(found_keywords) >= 1 or len(found_patterns) >= 1) and
                (has_quantity_column or has_spec_header)
            )

            # Дополнительный критерий для PURMO
            if not should_process and re.search(r'PURMO\s+[CHK]\s*\d{1,2}', text_lower):
                should_process = True

            if not should_process:
                self._log(f"📄 Страница {page_num}: ПРОПУСК (нет признаков таблиц)", "WARNING")

            return should_process

        except Exception as e:
            self._log(f"⚠️ Ошибка при проверке страницы {page_num}: {e}", "WARNING")
            return True

    # ==================================================================
    # ИЗВЛЕЧЕНИЕ ТАБЛИЦ
    # ==================================================================

    def _extract_tables_universal(self, page, page_num: int) -> List[pd.DataFrame]:
        """Извлекает таблицы со страницы тремя стратегиями"""
        tables_df = []

        strategies = [
            {"name": "СТРАТЕГИЯ ПО УМОЛЧАНИЮ", "params": {}},
            {"name": "ЛИНИИ+ЛИНИИ", "params": {"vertical_strategy": "lines", "horizontal_strategy": "lines"}},
            {"name": "СНИППЕТЫ", "params": {"snap_tolerance": 5, "join_tolerance": 5}},
        ]

        for strategy in strategies:
            strategy_name = strategy["name"]
            strategy_params = strategy["params"]

            try:
                tables = page.extract_tables(strategy_params)
                if tables:
                    for table_idx, table in enumerate(tables):
                        if table and self._is_valid_table(table):
                            df = self._table_to_dataframe(table, page_num, strategy_name, table_idx)
                            if not df.empty:
                                # Фильтрация мусорных таблиц
                                if df.shape[0] < 2 or df.shape[1] < 2:
                                    continue

                                text_flat = ' '.join(df.astype(str).values.flatten())
                                radiator_keywords = (
                                    r'радиатор|стальной|панельный|отопительн|'
                                    r'radiator|heater|panel\s+heater|convector|'
                                    r'шт|шт\.|ед|ед\.|pcs|pc|qty|кол-?во|количество|'
                                    r'U\d{2}-\d{3,4}-\d{3,4}|C\d{2}-\d{3,4}-\d{3,4}|'
                                    r'[VK]\d{2}|VK-\d{2}|K-\d{2}|type\s*\d+|тип\s*\d+|'
                                    r'compact|classic|ventil|prado|purmo|kermi|royal|ftv|fto|ftk|'
                                    r'нижн(?:ее|ий)\s+подключ|боков\w+\s+подключ|universal'
                                )
                                if not re.search(radiator_keywords, text_flat, re.IGNORECASE):
                                    continue

                                tables_df.append(df)
                                self._log(f"✅ Таблица добавлена ({strategy_name})")
            except Exception as e:
                self._log(f"❌ Ошибка стратегии {strategy_name}: {e}", "ERROR")
                continue

        self._log(f"📊 ИТОГО со страницы {page_num}: {len(tables_df)} валидных таблиц")
        return tables_df

    def _is_valid_table(self, table: List) -> bool:
        """Проверяет, что таблица содержит данные"""
        if not table or len(table) == 0:
            return False
        total_cells = sum(len(row) for row in table)
        non_empty_cells = sum(1 for row in table for cell in row if cell and str(cell).strip())
        fill_ratio = non_empty_cells / total_cells if total_cells > 0 else 0
        return non_empty_cells >= 2 and fill_ratio > 0.1 and len(table) >= 1

    def _table_to_dataframe(self, table: List, page_num: int, strategy_name: str, table_idx: int) -> pd.DataFrame:
        """Конвертирует таблицу в DataFrame с объединением многострочных ячеек"""
        try:
            # --- ОБЪЕДИНЕНИЕ МНОГОСТРОЧНЫХ ЯЧЕЕК ---
            merged_rows = []
            i = 0
            while i < len(table):
                current_row = [str(cell).strip() if cell and str(cell).strip() else "" for cell in table[i]]

                def is_continuation(row_text: str) -> bool:
                    text_lower = row_text.lower()
                    if re.search(r'(k-profil|vk-profil|/\d{3,4}/|\d{1,2}/\d{3,4}/\d{3,4})', text_lower):
                        return True
                    if len(text_lower) < 50 and re.fullmatch(r'[\w\s\-/]+', text_lower):
                        return True
                    return False

                def is_radiator_start(row_text: str) -> bool:
                    text_lower = row_text.lower()
                    radiator_keywords = ['радиатор', 'radiator', 'meteor', 'classic', 'compact', 'k-profil', 'vk-profil']
                    return any(kw in text_lower for kw in radiator_keywords)

                if i + 1 < len(table):
                    next_row = [str(cell).strip() if cell and str(cell).strip() else "" for cell in table[i + 1]]
                    current_full = " ".join(current_row).strip()
                    next_full = " ".join(next_row).strip()

                    if (current_full and is_radiator_start(current_full)) and \
                       (next_full and is_continuation(next_full)) and \
                       not re.search(r'(шт|ед|qty|кол-во|цена|price|сумма|\d+\s*шт)', next_full.lower()):

                        merged_row = []
                        max_cols = max(len(current_row), len(next_row))
                        for j in range(max_cols):
                            val1 = current_row[j] if j < len(current_row) else ""
                            val2 = next_row[j] if j < len(next_row) else ""
                            if val1 and val2:
                                merged_row.append(f"{val1} {val2}")
                            else:
                                merged_row.append(val1 or val2)
                        merged_rows.append(merged_row)
                        i += 2
                        continue

                merged_rows.append(current_row)
                i += 1

            # Создаём DataFrame
            df = pd.DataFrame(merged_rows)
            original_shape = df.shape
            df = self._clean_table_dataframe(df)
            if df.empty:
                return pd.DataFrame()

            df['_source_page'] = page_num
            df['_source_strategy'] = strategy_name
            df['_source_table_index'] = table_idx
            df['_row_index_original'] = range(len(df))

            return df

        except Exception as e:
            self._log(f"❌ Ошибка конвертации таблицы: {e}", "ERROR")
            return pd.DataFrame()

    def _clean_table_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """Очищает DataFrame от пустых строк и столбцов"""
        if df.empty:
            return df

        df = df.astype(str)
        df = df.apply(lambda x: x.str.strip())
        df = df.replace({
            '': '', 'nan': '', 'None': '', '<NA>': '', 'NaT': '',
            'NULL': '', 'null': '', 'NaN': '', 'N/A': '', 'n/a': ''
        })

        # Удаляем полностью пустые строки
        mask_rows = df.astype(str).apply(lambda x: (x != '').any(), axis=1)
        df = df[mask_rows]

        # Удаляем полностью пустые столбцы
        mask_cols = df.astype(str).apply(lambda x: (x != '').any(), axis=0)
        df = df.loc[:, mask_cols]

        if not df.empty:
            df = df.reset_index(drop=True)
            df.columns = [f"Col_{i}" for i in range(len(df.columns))]

        return df

    # ==================================================================
    # ОСНОВНОЙ МЕТОД ПАРСИНГА
    # ==================================================================

    def parse_to_dataframe(self, file_path: str,
                           pages: Optional[List[int]] = None,
                           start_page: int = 1,
                           end_page: Optional[int] = None,
                           max_pages: Optional[int] = None) -> pd.DataFrame:
        """
        ГЛАВНЫЙ МЕТОД - парсит PDF в DataFrame
        Обрабатывает ВСЕ переданные страницы (без фильтрации)
        
        :param file_path: Путь к PDF файлу
        :param pages: Список конкретных страниц для обработки (номера с 1)
        :param start_page: Номер первой страницы (используется если pages=None)
        :param end_page: Номер последней страницы (используется если pages=None)
        :param max_pages: Максимальное количество страниц
        :return: DataFrame с результатами парсинга
        """
        if not HAS_PDFPLUMBER:
            raise RuntimeError("❌ БИБЛИОТЕКА PDFPLUMBER НЕ УСТАНОВЛЕНА! Выполните: pip install pdfplumber")

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"❌ ФАЙЛ НЕ НАЙДЕН: {file_path}")

        self._log("🚀" * 50)
        self._log(f"🚀 ЗАПУСК ПАРСИНГА PDF: {os.path.basename(file_path)}")
        self._log(f"📁 Полный путь: {file_path}")
        self._log(f"📏 Размер файла: {os.path.getsize(file_path) / 1024 / 1024:.2f} MB")
        self._log("🚀" * 50)

        try:
            all_tables = []
            total_pages_processed = 0

            with pdfplumber.open(file_path) as pdf:
                total_pages_in_pdf = len(pdf.pages)
                self._log(f"📄 ОБНАРУЖЕНО СТРАНИЦ В PDF: {total_pages_in_pdf}")

                # Подготавливаем список страниц для обработки
                if pages is not None:
                    pages_to_process = sorted(set(p for p in pages if 1 <= p <= total_pages_in_pdf))
                    if not pages_to_process:
                        raise ValueError(f"Нет корректных страниц для обработки. Диапазон: 1-{total_pages_in_pdf}")
                    self._log(f"📄 Будет обработано страниц: {len(pages_to_process)}")
                else:
                    if start_page < 1:
                        start_page = 1
                    if end_page is None:
                        end_page = total_pages_in_pdf
                    elif end_page > total_pages_in_pdf:
                        end_page = total_pages_in_pdf

                    if start_page > end_page:
                        raise ValueError(f"Некорректный диапазон страниц: {start_page}-{end_page}")

                    pages_in_range = end_page - start_page + 1
                    if max_pages and max_pages > 0 and pages_in_range > max_pages:
                        end_page = start_page + max_pages - 1
                        if end_page > total_pages_in_pdf:
                            end_page = total_pages_in_pdf

                    pages_to_process = list(range(start_page, end_page + 1))
                    self._log(f"📄 ДИАПАЗОН ОБРАБОТКИ: {start_page}-{end_page}")

                self._log(f"📄 ВСЕГО ДЛЯ ОБРАБОТКИ: {len(pages_to_process)} стр.")
                self._log("📄 ВНИМАНИЕ: Обрабатываются ВСЕ выбранные страницы (фильтрация отключена)")

                # ========== ОТЛАДОЧНЫЙ КОД: анализ координат столбцов ==========
                self._log("\n🔍 ОТЛАДКА: АНАЛИЗ КООРДИНАТ СТОЛБЦОВ")
                self._log("=" * 60)
                
                for analyze_page_num in pages_to_process[:2]:  # Анализируем первые 2 страницы
                    analyze_page = pdf.pages[analyze_page_num - 1]
                    self._log(f"\n📄 СТРАНИЦА {analyze_page_num}:")
                    
                    # Получаем все слова на странице
                    words = analyze_page.extract_words(
                        keep_blank_chars=False,
                        use_text_flow=False
                    )
                    
                    if not words:
                        self._log(f"  ⚠️ Нет слов на странице {analyze_page_num}")
                        continue
                    
                    # Собираем уникальные x-координаты (левые границы слов)
                    x_coords = sorted(set([round(w['x0'], 1) for w in words]))
                    
                    self._log(f"  Количество слов: {len(words)}")
                    self._log(f"  Уникальные x-координаты (левые границы): {x_coords[:20]}{'...' if len(x_coords) > 20 else ''}")
                    
                    # Группируем слова по x-координатам (создаём виртуальные столбцы)
                    tolerance = 5  # Допуск ±5 точек
                    columns = []
                    for x in x_coords:
                        if not columns or abs(x - columns[-1]) > tolerance:
                            columns.append(x)
                    
                    self._log(f"  Виртуальных столбцов: {len(columns)}")
                    
                    # Показываем первые 15 слов с их координатами
                    self._log(f"  Первые 15 слов с координатами:")
                    for i, word in enumerate(words[:15]):
                        self._log(f"    {i+1:2d}. x={word['x0']:6.1f}-{word['x1']:6.1f} | text='{word['text'][:40]}'")
                    
                    # Пытаемся определить, есть ли заголовки на странице
                    first_words = words[:20]
                    has_header = False
                    header_keywords = ['№', 'артикул', 'наименование', 'кол-во', 'цена', 'сумма', 
                                       'количество', 'код', 'ед', 'шт']
                    for word in first_words:
                        word_lower = word['text'].lower()
                        if any(kw in word_lower for kw in header_keywords):
                            has_header = True
                            break
                    
                    self._log(f"  Есть заголовки: {'✅ ДА' if has_header else '❌ НЕТ'}")
                    
                    # Если есть заголовки, показываем их координаты
                    if has_header:
                        self._log(f"  Заголовки на странице {analyze_page_num}:")
                        for word in first_words:
                            word_lower = word['text'].lower()
                            if any(kw in word_lower for kw in header_keywords):
                                self._log(f"    '{word['text']}' → x={word['x0']:.1f}-{word['x1']:.1f}")
                
                self._log("\n" + "=" * 60)
                self._log("🔍 ОТЛАДКА: ЗАВЕРШЕНА")
                self._log("=" * 60 + "\n")
                # ========== КОНЕЦ ОТЛАДОЧНОГО КОДА ==========

                for idx, page_num in enumerate(pages_to_process):
                    if self.progress_callback:
                        self.progress_callback(idx + 1, len(pages_to_process))

                    page = pdf.pages[page_num - 1]
                    
                    # ========== НИКАКОЙ ФИЛЬТРАЦИИ ==========
                    # Обрабатываем ВСЕ страницы, которые выбрал пользователь
                    # ==========

                    self._log(f"\n📖 ОБРАБОТКА СТРАНИЦЫ {page_num}/{total_pages_in_pdf}")
                    self._log(f"📖 Прогресс: {idx + 1}/{len(pages_to_process)}")

                    page_tables = self._extract_tables_universal(page, page_num)
                    if page_tables:
                        all_tables.extend(page_tables)
                        total_pages_processed += 1
                        self._log(f"📊 Найдено таблиц на странице {page_num}: {len(page_tables)}")
                    else:
                        self._log(f"⚠️ На странице {page_num} не найдено таблиц", "WARNING")

            # Сводка по обработке
            self._log(f"\n📊 СВОДКА ПО ПАРСИНГУ:")
            self._log(f"📊 Обработано страниц: {total_pages_processed} из {len(pages_to_process)}")
            self._log(f"📊 Найдено таблиц (всего): {len(all_tables)}")

            if not all_tables:
                self._log("⚠️ ВНИМАНИЕ: В PDF НЕ НАЙДЕНО ТАБЛИЦ")
                return pd.DataFrame()

            # Выбираем только лучшие таблицы (без дублирования страниц)
            best_tables = []
            pages_processed = set()
            for table in all_tables:
                page = table['_source_page'].iloc[0] if '_source_page' in table.columns else 0
                if page not in pages_processed:
                    best_tables.append(table)
                    pages_processed.add(page)

            self._log(f"📊 Выбрано {len(best_tables)} таблиц (по одной на страницу)")

            # Объединяем выбранные таблицы
            result_df = pd.concat(best_tables, ignore_index=True)
            result_df = self._replace_na_values(result_df)

            self._log(f"✅ УСПЕХ! СОЗДАН DATAFRAME: {result_df.shape}")
            return result_df

        except Exception as e:
            error_msg = f"❌ КРИТИЧЕСКАЯ ОШИБКА ПАРСИНГА {file_path}:\n{str(e)}"
            self._log(error_msg, "ERROR")
            raise RuntimeError(error_msg)

    def _replace_na_values(self, df: pd.DataFrame) -> pd.DataFrame:
        """Заменяет pd.NA и другие null-значения на пустые строки"""
        if df.empty:
            return df

        df = df.fillna('')
        na_patterns = ['nan', 'None', 'NoneType', '<NA>', 'NaT', 'NULL', 'null', 'NaN', 'N/A', 'n/a']
        df = df.replace(na_patterns, '')

        for col in df.columns:
            df[col] = df[col].astype(str).str.strip()

        return df

def get_pdf_page_count(file_path: str) -> int:
    """
    Возвращает количество страниц в PDF файле.
    
    Args:
        file_path: путь к PDF файлу
        
    Returns:
        int: количество страниц
        
    Raises:
        RuntimeError: если pdfplumber не установлен
        FileNotFoundError: если файл не найден
    """
    if not HAS_PDFPLUMBER:
        raise RuntimeError("pdfplumber не установлен. Выполните: pip install pdfplumber")
    
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Файл не найден: {file_path}")
    
    with pdfplumber.open(file_path) as pdf:

        return len(pdf.pages)