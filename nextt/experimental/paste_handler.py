"""
Обработчик вставки из буфера обмена.
Изолирован от основного кода.
"""

import tkinter as tk
import re
import pandas as pd
from tkinter import messagebox
from typing import Optional, Dict
from nextt.logger import get_logger

logger = get_logger(__name__)

EXPERIMENTAL_ENABLED = False


def register_paste_button(main_window) -> None:
    if not EXPERIMENTAL_ENABLED:
        return
    register_paste_button.main_window = main_window


def show_paste_dialog(main_window) -> None:
    if not EXPERIMENTAL_ENABLED:
        messagebox.showinfo("Информация", "Функция временно недоступна")
        return
    
    try:
        from .paste_dialog import PasteDialog
        from .equipment_searcher import EquipmentSearcher
        
        # Контейнер для хранения исходного текста
        original_text_container = {"text": ""}
        
        def process_callback(df, selected_categories=None):
            if df is None or df.empty:
                return
            
            # Сохраняем исходный текст (он уже должен быть в контейнере)
            original_text = original_text_container["text"]
            
            searcher = EquipmentSearcher(main_window.app.data_provider, selected_categories)
            data_type = _determine_data_type_by_rows(df)
            logger.info(f"Определён тип данных: {data_type}")
            
            if data_type == 'radiators':
                _process_radiators_data(main_window, df)
            else:
                # Передаём исходный текст в обработчик оборудования
                _process_equipment_data(main_window, df, searcher, original_text)
        
        # Создаём диалог
        dialog = PasteDialog(
            parent=main_window.root,
            app=main_window.app,
            font_manager=main_window.font_manager,
            callback=process_callback
        )
        
        # Переопределяем метод _on_confirm, чтобы сохранить исходный текст
        original_on_confirm = dialog._on_confirm
        
        def new_on_confirm():
            # Сохраняем исходный текст из текстового поля
            original_text = dialog._text_area.get("1.0", tk.END).strip()
            original_text_container["text"] = original_text
            # Вызываем оригинальный _on_confirm
            original_on_confirm()
        
        dialog._on_confirm = new_on_confirm
        dialog.show()
        
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        import traceback
        logger.error(traceback.format_exc())
        messagebox.showerror("Ошибка", f"Не удалось открыть диалог:\n{str(e)}")


def _is_radiator_row(text: str) -> bool:
    """
    Определяет, является ли строка радиатором по наличию ключевых признаков.
    Возвращает True, если найдено 4 или более признаков из 5.
    """
    if not text or len(text.strip()) < 5:
        return False
    
    text_lower = text.lower()
    score = 0
    
    # ========== 1. ПРИЗНАК ТИПА (10-33) ==========
    type_patterns = [
        r'\b(10|11|12|20|21|22|30|33)\b',
        r'тип\s*(10|11|12|20|21|22|30|33)',
        r'(?:profil|тип)\s*(\d{2})',
        # ДОБАВЛЕНО: для формата "С 11- 400 - 600"
        r'[cс]\s*(\d{2})',  # C 11, C 22
    ]
    for pattern in type_patterns:
        if re.search(pattern, text_lower):
            score += 1
            logger.debug(f"  Признак радиатора: тип найден")
            break
    
    # ========== 2. ПРИЗНАК ВЫСОТЫ (300, 400, 500, 600, 900) ==========
    height_patterns = [
        r'\b(300|400|500|600|900)\b',
        r'высот[аой]*\s*(300|400|500|600|900)',
        r'[hх]\s*[=:]\s*(300|400|500|600|900)',
    ]
    for pattern in height_patterns:
        if re.search(pattern, text_lower):
            score += 1
            logger.debug(f"  Признак радиатора: высота найдена")
            break
    
    # ========== 3. ПРИЗНАК ДЛИНЫ (400-3000, кратно 100) ==========
    length_patterns = [
        r'\b(400|500|600|700|800|900|1000|1100|1200|1300|1400|1500|1600|1700|1800|1900|2000|2100|2200|2300|2400|2500|2600|2700|2800|2900|3000)\b',
        r'длин[аой]*\s*(\d{3,4})',
        r'[l]\s*[=:]\s*(\d{3,4})',
    ]
    for pattern in length_patterns:
        if re.search(pattern, text_lower):
            score += 1
            logger.debug(f"  Признак радиатора: длина найдена")
            break
    
    # ========== 4. ПРИЗНАК ПОДКЛЮЧЕНИЯ ==========
    connection_patterns = [
        r'\b(vk|k)\s*[-]?profil\b',
        r'\bнижн(?:ее|ем|им|ий)?\b',
        r'\bбоков(?:ое|ом|ым|ий)?\b',
        r'\bventil\b',
        r'\bclassic\b',
        r'\bcompact\b',
        r'\bдонн(?:ое|ом|ым)?\b',
        # ДОБАВЛЕНО: буквы C, V, K в начале могут указывать на тип подключения
        r'^\s*[cсvk]',  # начинается с C, V, K
    ]
    for pattern in connection_patterns:
        if re.search(pattern, text_lower):
            score += 1
            logger.debug(f"  Признак радиатора: подключение найдено")
            break
    
    # ========== 5. ПРИЗНАК СТОРОНЫ ==========
    side_patterns = [
        r'\b(лево|право)\w*\b',
        r'\b(l|r|la|ra|re|li)\b',
        r'\b(left|right)\b',
    ]
    for pattern in side_patterns:
        if re.search(pattern, text_lower):
            score += 1
            logger.debug(f"  Признак радиатора: сторона найдена")
            break
    
    # Дополнительные признаки (увеличивают вероятность)
    # Наличие слеша в формате "11/300/500"
    if re.search(r'\d{2}/\d{3,4}/\d{3,4}', text):
        score += 1
        logger.debug(f"  Признак радиатора: формат слэш")
    
    # Наличие дефисов в формате "11-300-500"
    if re.search(r'\d{2}-\d{3,4}-\d{3,4}', text):
        score += 1
        logger.debug(f"  Признак радиатора: формат дефис")
    
    # ДОБАВЛЕНО: наличие дефисов с пробелами "C 11- 400 - 600"
    if re.search(r'\d{2}\s*-\s*\d{3,4}\s*-\s*\d{3,4}', text):
        score += 1
        logger.debug(f"  Признак радиатора: формат с пробелами и дефисами")
    
    # Ключевые слова радиаторов
    radiator_keywords = ['радиатор', 'kermi', 'purmo', 'buderus', 'evra', 'oasis', 'laggar', 'meteor', 'profil']
    for kw in radiator_keywords:
        if kw in text_lower:
            score += 1
            logger.debug(f"  Признак радиатора: ключевое слово '{kw}'")
            break
    
    logger.debug(f"  ИТОГО баллов радиатора: {score}")
    
    # Если 3 и более баллов — это радиатор (снижаем порог для распознавания)
    return score >= 3


def _determine_data_type_by_rows(df: pd.DataFrame) -> str:
    """
    Определяет тип данных (радиаторы или оборудование) по анализу строк.
    Возвращает 'radiators' или 'equipment'.
    """
    if df is None or df.empty:
        return 'equipment'
    
    radiator_count = 0
    equipment_count = 0
    
    # Берем первые 10 строк для анализа
    for idx, row in df.head(10).iterrows():
        # Объединяем все значения строки в один текст
        text = ' '.join(str(v) for v in row.values).strip()
        if not text:
            continue
        
        # ПРОВЕРКА 1: есть ли артикул LaggarTT (начинается с 77246 или 77247)
        import re
        laggar_article_pattern = re.compile(r'\b(77246\d{5}|77247\d{5})\b')
        if laggar_article_pattern.search(text):
            radiator_count += 1
            logger.debug(f"  Признак радиатора: артикул LaggarTT найден")
            continue
        
        # ПРОВЕРКА 2: стандартная проверка на радиатор (по ключевым словам)
        if _is_radiator_row(text):
            radiator_count += 1
        else:
            equipment_count += 1
    
    logger.info(f"Анализ данных: радиаторов={radiator_count}, оборудование={equipment_count}")
    
    # Если есть хотя бы один радиатор — считаем всё радиаторами
    if radiator_count >= 1:
        return 'radiators'
    else:
        return 'equipment'


def _process_radiators_data(main_window, df) -> None:
    """Обрабатывает данные как радиаторы."""
    try:
        from .universal_parser import UniversalParser
        
        parsed_data = UniversalParser.parse_dataframe(df)
        
        # ========== ПОДРОБНЫЙ ЛОГ ДЛЯ ОТЛАДКИ ==========
        logger.info("=" * 60)
        logger.info("ПАРСИНГ ДАННЫХ ИЗ БУФЕРА:")
        logger.info(f"  Всего строк в df: {len(df)}")
        logger.info(f"  Столбцы df: {list(df.columns)}")
        
        # Выводим первые строки df
        for i in range(min(3, len(df))):
            logger.info(f"  Строка {i} (df): {list(df.iloc[i])}")
        
        # Выводим результаты парсинга
        logger.info("-" * 40)
        logger.info("РЕЗУЛЬТАТЫ UniversalParser:")
        for i, item in enumerate(parsed_data):
            logger.info(f"  Строка {i}:")
            logger.info(f"    original_text: {item.get('original_text', '')[:80]}")
            logger.info(f"    article: '{item.get('article', '')}'")
            logger.info(f"    quantity: {item.get('quantity', 0)}")
            logger.info(f"    clean_name: {item.get('clean_name', '')[:50]}")
        logger.info("=" * 60)
        
        # Проверяем наличие артикулов LaggarTT (77246 или 77247)
        has_laggar_articles = False
        for item in parsed_data:
            art = item.get('article', '')
            if art:
                art_str = str(art).strip()
                logger.info(f"Проверка артикула: '{art_str}'")
                # Проверяем, начинается ли с 77246 или 77247 (артикулы LaggarTT)
                if art_str.startswith('77246') or art_str.startswith('77247'):
                    has_laggar_articles = True
                    logger.info(f"  -> НАЙДЕН АРТИКУЛ LAGGARTT: {art_str}")
                    break
        
        logger.info(f"has_laggar_articles = {has_laggar_articles}")
        
        if has_laggar_articles:
            logger.info("Обнаружены артикулы LaggarTT, заполняем матрицу напрямую")
            _fill_matrix_direct(main_window, parsed_data)
        else:
            logger.info("Чужие радиаторы, запускаем подбор аналогов через ColumnSelector")
            _run_analog_matcher(main_window, df)
            
    except Exception as e:
        logger.error(f"Ошибка обработки радиаторов: {e}")
        import traceback
        logger.error(traceback.format_exc())
        messagebox.showerror("Ошибка", f"Не удалось обработать радиаторы:\n{str(e)}")


def _fill_matrix_direct(main_window, parsed_data) -> None:
    """Заполняет матрицу напрямую из распарсенных данных с артикулами LaggarTT."""
    loaded_count = 0
    total_qty = 0
    
    for item in parsed_data:
        article = item.get('article')
        qty = item.get('quantity')
        
        if not article:
            continue
        
        if qty <= 0:
            continue
        
        meteor_art, _ = main_window.app.data_provider.convert_meteor_to_laggar(article)
        search_art = meteor_art if meteor_art else article
        
        found = main_window.app.data_provider.find_by_article(search_art)
        if found is not None:
            conn = found.get('Connection', '')
            rt = found.get('RadiatorType', '')
            if conn and rt:
                key = (f"{conn} {rt}", search_art)
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
    
    if hasattr(main_window, '_build_matrix'):
        main_window._build_matrix(
            main_window._conn_var.get(),
            main_window._type_var.get()
        )
    
    if loaded_count > 0:
        messagebox.showinfo(
            "Успех",
            f"Загружено позиций: {loaded_count}\nОбщее количество: {total_qty}"
        )
    else:
        messagebox.showwarning("Предупреждение", "Не найдено подходящих артикулов LaggarTT")


def _run_analog_matcher(main_window, df) -> None:
    """Запускает стандартный подбор аналогов для чужих радиаторов."""
    try:
        from nextt.parsing.column_selector import ColumnSelector
        
        # ========== ВАЖНО: освобождаем захват, если он есть ==========
        # Проверяем, есть ли активный grab и освобождаем его
        try:
            # Находим окно, которое сейчас держит grab
            grab_window = main_window.root.grab_current()
            if grab_window:
                logger.info(f"Освобождаем захват у окна: {grab_window}")
                grab_window.grab_release()
        except Exception as e:
            logger.debug(f"Ошибка при освобождении grab: {e}")
        
        # Небольшая задержка перед открытием нового окна
        import time
        time.sleep(0.05)
        
        selector = ColumnSelector(
            main_window.root, 
            df, 
            "Данные из буфера обмена", 
            main_window.font_manager
        )
        result = selector.select()
        
        if result[0] is None:
            logger.info("Пользователь отменил выбор столбцов")
            return
        
        pairs = result[0]
        data_for_table = []
        normalizer = main_window.app.normalizer
        
        for name_col, qty_col in pairs:
            for _, row in df.iterrows():
                if name_col >= len(row) or qty_col >= len(row):
                    continue
                
                original_name = str(row.iloc[name_col]).strip()
                qty_str = str(row.iloc[qty_col]).strip()
                
                if not original_name:
                    continue
                
                qty = _parse_qty_simple(qty_str)
                if qty <= 0:
                    continue
                
                parsed = normalizer.normalize_and_extract(original_name)
                
                meteor_art = ""
                meteor_name = ""
                source = "Не подобрано"
                
                if parsed.recognized:
                    art, name = main_window.app.data_provider.find_analog(
                        parsed.connection, parsed.rad_type,
                        parsed.height, parsed.length
                    )
                    if art:
                        meteor_art = art
                        meteor_name = name
                        source = "Автоматически"
                
                if not meteor_art:
                    match = main_window.app.pattern_manager.find_match(original_name)
                    if match:
                        art, name = main_window.app.data_provider.find_analog(
                            match['connection'], match['rad_type'],
                            match['height'], match['length']
                        )
                        if art:
                            meteor_art = art
                            meteor_name = name
                            source = "По образцу"
                
                data_for_table.append({
                    "Наименование": original_name,
                    "Кол-во": qty,
                    "Наименование LaggarTT": meteor_name,
                    "Артикул LaggarTT": meteor_art,
                    "Источник": source,
                })
        
        if not data_for_table:
            messagebox.showwarning("Предупреждение", "Не удалось извлечь данные")
            return
        
        import pandas as pd
        correspondence_df = pd.DataFrame(data_for_table)
        
        from nextt.ui.dialogs.correspondence import CorrespondenceDialog
        dialog = CorrespondenceDialog(main_window.app)
        main_window.app._last_correspondence_dialog = dialog
        dialog.show(correspondence_df)
        
    except Exception as e:
        logger.error(f"Ошибка в подборе аналогов: {e}")
        import traceback
        logger.error(traceback.format_exc())
        messagebox.showerror("Ошибка", f"Не удалось запустить подбор аналогов:\n{str(e)}")


def _parse_qty_simple(value) -> int:
    """Простой парсер количества."""
    if not value or value == "":
        return 0
    str_value = str(value).strip()
    if '+' in str_value:
        parts = str_value.split('+')
        total = 0
        for p in parts:
            p = p.strip()
            if not p:
                continue
            match = re.search(r'(\d+)', p)
            if match:
                total += int(match.group(1))
        return total
    match = re.search(r'(\d+)', str_value)
    return int(match.group(1)) if match else 0


# ============================================================================
# НОВЫЕ ФУНКЦИИ ДЛЯ ПРЯМОГО ПОИСКА АРТИКУЛОВ
# ============================================================================

def _clean_article_text(text: str) -> str:
    """
    Очищает текст от префиксов типа "1) ", "2. ", "- " и т.д.
    Возвращает очищенный текст для проверки на артикул.
    """
    if not text:
        return text
    
    # Удаляем префиксы вида "1) ", "2) ", "1. ", "2. ", "- ", "* " и т.д.
    cleaned = re.sub(r'^\s*\d+[\)\.\]\-\_]\s*', '', text)
    cleaned = re.sub(r'^\s*[•\-*]\s*', '', cleaned)
    # Удаляем "шт" в конце
    cleaned = re.sub(r'\s*[-–—]?\s*\d*\s*шт\.?\w*\s*$', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\s*[xх]\s*\d+\s*$', '', cleaned, flags=re.IGNORECASE)
    
    return cleaned.strip()


def _is_article(text: str) -> bool:
    """
    Проверяет, является ли текст артикулом (а не названием).
    Возвращает True, если текст похож на артикул.
    """
    if not text:
        return False
    
    # Очищаем текст от префиксов
    cleaned = _clean_article_text(text)
    if not cleaned:
        return False
    
    cleaned_upper = cleaned.strip().upper()
    
    # Паттерны артикулов из базы Все_категории.xlsx
    patterns = [
        r'^\d{8,11}$',                          # 8732302139
        r'^[A-Z]{2}\d{6,8}$',                  # AA07000097
        r'^\d{3}[A-Z]{2}\d{8}$',               # 701AA04020177
        r'^[A-Z]+\d+-\d+[A-Z]*\d*$',           # WT60100-01LN
        r'^[A-Z]-\d{2}$',                      # B-01
        r'^[КK]\d{1,2}\.\d{1,4}[A-Z]?\d*$',    # К15.4300
        r'^[КK][А-ЯA-Z]{2}\d+$',               # КНС470
        r'^[А-ЯA-Z]{3,4}\d+$',                # PLN20
        r'^NEW\s+[A-Z]+\d+-\d+$',              # NEW WT60100-05
    ]
    
    for pattern in patterns:
        if re.match(pattern, cleaned_upper):
            logger.info(f"[_is_article] Распознан артикул: '{cleaned}'")
            return True
    
    return False


def _search_article_in_database(article: str, df: pd.DataFrame) -> Optional[Dict]:
    """
    Прямой поиск артикула в базе данных.
    Возвращает словарь с артикулом, наименованием, ценой и категорией.
    """
    if df.empty:
        return None
    
    # Очищаем артикул
    clean_article = _clean_article_text(article)
    article_upper = clean_article.strip().upper()
    
    # Точное совпадение
    mask = df['Артикул'].astype(str).str.strip().str.upper() == article_upper
    matches = df[mask]
    
    if not matches.empty:
        row = matches.iloc[0]
        return {
            'article': str(row['Артикул']),
            'name': str(row['Наименование']),
            'price': float(row['Цена']) if 'Цена' in row and pd.notna(row['Цена']) else 0,
            'category': str(row['Иерархия']) if 'Иерархия' in row and pd.notna(row['Иерархия']) else '',
        }
    
    # Нормализованное совпадение (удаляем все небуквенно-цифровые символы)
    article_normalized = re.sub(r'[^A-Z0-9]', '', article_upper)
    for idx, row in df.iterrows():
        db_art = str(row['Артикул']).strip().upper()
        db_art_normalized = re.sub(r'[^A-Z0-9]', '', db_art)
        if article_normalized == db_art_normalized and len(article_normalized) >= 4:
            return {
                'article': str(row['Артикул']),
                'name': str(row['Наименование']),
                'price': float(row['Цена']) if 'Цена' in row and pd.notna(row['Цена']) else 0,
                'category': str(row['Иерархия']) if 'Иерархия' in row and pd.notna(row['Иерархия']) else '',
            }
    
    # Поиск по вхождению
    for idx, row in df.iterrows():
        db_art = str(row['Артикул']).strip().upper()
        if article_upper in db_art or db_art in article_upper:
            return {
                'article': str(row['Артикул']),
                'name': str(row['Наименование']),
                'price': float(row['Цена']) if 'Цена' in row and pd.notna(row['Цена']) else 0,
                'category': str(row['Иерархия']) if 'Иерархия' in row and pd.notna(row['Иерархия']) else '',
            }
    
    return None


def _process_equipment_data(main_window, df, searcher, original_text="") -> None:
    """
    Обрабатывает данные как оборудование.
    Сначала пытается найти артикулы прямым поиском,
    если не получается — использует нормализатор.
    """
    try:
        from .equipment_dialog import EquipmentDialog
        
        if searcher.df.empty:
            messagebox.showwarning("Предупреждение", "База оборудования не загружена.")
            return
        
        # Получаем отфильтрованный DataFrame из searcher
        filtered_df = searcher._filter_by_categories(searcher.df)
        
        matches = []
        
        for idx, row in df.iterrows():
            # Первый столбец - название/артикул
            text = str(row.iloc[0]).strip() if len(row) > 0 else ""
            # Второй столбец - количество
            qty_str = str(row.iloc[1]).strip() if len(row) > 1 else ""
            qty = _parse_qty_simple(qty_str)
            
            if not text:
                continue
            
            # ШАГ 1: Проверяем, является ли текст артикулом
            if _is_article(text):
                logger.info(f"Поиск по артикулу: '{text}'")
                found = _search_article_in_database(text, filtered_df)
                if found:
                    matches.append({
                        'success': True,
                        'article': found['article'],
                        'name': found['name'],
                        'quantity': qty if qty > 0 else 1,
                        'original_text': text,
                        'price': found['price'],
                        'category': found['category'],
                        'source': 'артикул'
                    })
                    logger.info(f"  ✅ Найден артикул: {found['article']}")
                    continue
                else:
                    logger.warning(f"  ❌ Артикул не найден: '{text}'")
                    # Не добавляем в matches, пробуем нормализатор ниже
            
            # ШАГ 2: Если не артикул или не найден — используем нормализатор
            logger.info(f"Поиск через нормализатор: '{text[:80]}'")
            normalized = searcher.match_line(text, qty)
            
            if normalized['success']:
                matches.append({
                    'success': True,
                    'article': normalized['article'],
                    'name': normalized['name'],
                    'quantity': normalized['quantity'],
                    'original_text': text,
                    'price': 0,
                    'category': '',
                    'source': normalized.get('source', 'нормализатор')
                })
                logger.info(f"  ✅ Найдено через нормализатор: {normalized['article']}")
            else:
                matches.append({
                    'success': False,
                    'article': '',
                    'name': '',
                    'quantity': qty if qty > 0 else 1,
                    'original_text': text,
                    'price': 0,
                    'category': '',
                    'error': normalized.get('error', 'Не найдено'),
                    'source': 'не найдено'
                })
                logger.warning(f"  ❌ Не найдено: '{text[:80]}'")
        
        # Фильтруем только с положительным количеством
        matches = [m for m in matches if m.get('quantity', 0) > 0]
        
        if not matches:
            messagebox.showwarning("Предупреждение", "Не удалось сопоставить данные с базой оборудования.")
            return
        
        # Показываем диалог с результатами
        dialog = EquipmentDialog(main_window.app, matches, original_text)
        dialog.show()
        
    except Exception as e:
        logger.error(f"Ошибка обработки оборудования: {e}")
        import traceback
        logger.error(traceback.format_exc())
        messagebox.showerror("Ошибка", f"Не удалось обработать оборудование:\n{str(e)}")