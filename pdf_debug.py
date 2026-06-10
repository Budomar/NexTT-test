"""
PDF DEBUG — песочница для отладки парсинга PDF.
Запускать из командной строки:
    python pdf_debug.py "путь/к/файлу.pdf"
    
Или прописать путь к файлу в переменной TEST_PDF ниже.
"""

import sys
import os
import re
from typing import Optional, List, Callable, Tuple
from datetime import datetime

# Добавляем путь к проекту
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd

# ======================================================================
# НАСТРОЙКИ
# ======================================================================
TEST_PDF = None  # Если None — берёт из аргументов командной строки
START_PAGE = 1
END_PAGE = None   # None = все страницы
MAX_PAGES = None  # None = без ограничения
PAGES = None      # Список конкретных страниц, например [1, 2, 5]
DEBUG = True      # Подробный вывод

# ======================================================================
# ЛОГГЕР
# ======================================================================
class Logger:
    def __init__(self, filepath: str):
        self.filepath = filepath
        self.lines = []
        self._start_time = datetime.now()
    
    def log(self, msg: str, level: str = "INFO"):
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        line = f"[{timestamp}] [{level}] {msg}"
        self.lines.append(line)
        print(line)
    
    def save(self):
        with open(self.filepath, 'w', encoding='utf-8') as f:
            f.write(f"Лог парсинга: {self.filepath}\n")
            f.write(f"Начало: {self._start_time}\n")
            f.write("=" * 80 + "\n\n")
            f.write('\n'.join(self.lines))
        print(f"\n📁 Лог сохранён: {self.filepath}")


# ======================================================================
# КОПИЯ PDFParser (упрощённая, без внешних зависимостей от nextt)
# ======================================================================
try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False
    print("❌ pdfplumber не установлен! Выполните: pip install pdfplumber")
    sys.exit(1)


class DebugPDFParser:
    """Парсер PDF с подробной отладкой."""
    
    RADIATOR_KEYWORDS = [
        'радиатор', 'радиаторный', 'стальной', 'панельный',
        'отопление', 'тип 11', 'тип 22', 'тип 33', 'тип 21', 'тип 10', 'тип 20',
        'compact', 'ventil', 'гигиенический', 'hygiene',
        'royal', 'thermo', 'buderus', 'kermi', 'purmo', 'prado',
        'evra', 'hiterm', 'valfex', 'korado', 'oasis',
        'нижним подключением', 'боковым подключением',
        'нижнее подключение', 'боковое подключение',
        'радиаторный', 'радиаторная', 'радиаторное',
        'radiator', 'panel', 'heater', 'steel',
        'спецификация', 'ведомость', 'оборудование',
        'позиция', 'наименование',
        'шт', 'шт.', 'ед', 'ед.', 'компл', 'pcs',
        'k-profil', 'vk-profil', 'profil',
    ]
    
    def __init__(self, logger: Logger):
        self.logger = logger
    
    def log(self, msg: str, level: str = "INFO"):
        self.logger.log(msg, level)
    
    # ==================================================================
    # ГЛАВНЫЙ МЕТОД — ТЕСТИРОВАНИЕ
    # ==================================================================
    
    def test_all_strategies(self, file_path: str) -> dict:
        """
        Тестирует ВСЕ стратегии на ВСЕХ страницах.
        Возвращает словарь с результатами.
        """
        self.log("=" * 80)
        self.log(f"📄 ТЕСТИРОВАНИЕ PDF: {os.path.basename(file_path)}")
        self.log(f"📏 Размер: {os.path.getsize(file_path) / 1024:.1f} КБ")
        self.log("=" * 80)
        
        results = {}
        
        with pdfplumber.open(file_path) as pdf:
            total_pages = len(pdf.pages)
            self.log(f"Всего страниц: {total_pages}")
            
            # Определяем страницы для обработки
            pages_to_process = list(range(START_PAGE, (END_PAGE or total_pages) + 1))
            if PAGES:
                pages_to_process = PAGES
            if MAX_PAGES:
                pages_to_process = pages_to_process[:MAX_PAGES]
            
            self.log(f"Тестируем страницы: {pages_to_process}")
            self.log("")
            
            # СТРАТЕГИИ
            strategies = [
                ("S1: по умолчанию", {}),
                ("S2: линии+линии", {"vertical_strategy": "lines", "horizontal_strategy": "lines"}),
                ("S3: текст+текст", {"vertical_strategy": "text", "horizontal_strategy": "text"}),
                ("S4: линии+текст", {"vertical_strategy": "lines", "horizontal_strategy": "text"}),
                ("S5: текст+линии", {"vertical_strategy": "text", "horizontal_strategy": "lines"}),
                ("S6: сниппеты", {"snap_tolerance": 5, "join_tolerance": 5}),
            ]
            
            for strategy_name, strategy_params in strategies:
                self.log(f"{'─' * 60}")
                self.log(f"🧪 ТЕСТИРУЕМ: {strategy_name}")
                self.log(f"{'─' * 60}")
                
                strategy_results = []
                total_radiators = 0
                
                for page_num in pages_to_process:
                    page = pdf.pages[page_num - 1]
                    text = page.extract_text() or ""
                    
                    if len(text.strip()) < 30:
                        self.log(f"  Стр.{page_num}: ⏭ пропущена (мало текста: {len(text.strip())} симв)")
                        continue
                    
                    # Проверяем есть ли радиаторы на странице
                    text_lower = text.lower()
                    has_radiators = any(kw in text_lower for kw in self.RADIATOR_KEYWORDS)
                    
                    if not has_radiators:
                        self.log(f"  Стр.{page_num}: ⏭ пропущена (нет ключевых слов радиаторов)")
                        continue
                    
                    try:
                        tables = page.extract_tables(strategy_params)
                        self.log(f"  Стр.{page_num}: извлечено таблиц — {len(tables)}")
                        
                        for t_idx, table in enumerate(tables):
                            if not table or len(table) < 2:
                                self.log(f"    Таблица #{t_idx + 1}: пустая или 1 строка — пропущена")
                                continue
                            
                            # Конвертируем в DataFrame
                            df = self._table_to_dataframe(table)
                            if df.empty or df.shape[0] < 2:
                                self.log(f"    Таблица #{t_idx + 1}: пустой DataFrame — пропущена")
                                continue
                            
                            self.log(f"    📊 Таблица #{t_idx + 1}: {df.shape[0]} строк × {df.shape[1]} столбцов")
                            
                            # Показываем первые 3 строки
                            for r in range(min(3, len(df))):
                                row_preview = " | ".join(
                                    str(df.iloc[r, c])[:30] for c in range(min(6, len(df.columns)))
                                )
                                self.log(f"      Строка {r}: {row_preview}")
                            
                            # Ищем столбцы с названием и количеством
                            name_col, qty_col = self._find_name_and_qty_columns(df)
                            
                            if name_col is None or qty_col is None:
                                self.log(f"      ❌ Не удалось найти столбцы (name={name_col}, qty={qty_col})")
                                continue
                            
                            self.log(f"      📋 Столбцы: название=Col_{name_col}, количество=Col_{qty_col}")
                            
                            # Извлекаем радиаторы
                            radiators = self._extract_radiators(df, name_col, qty_col)
                            
                            if radiators:
                                self.log(f"      ✅ Найдено радиаторов: {len(radiators)}")
                                for r in radiators[:5]:
                                    self.log(f"        • {r['name'][:60]}... — {r['qty']} шт.")
                                if len(radiators) > 5:
                                    self.log(f"        ... и ещё {len(radiators) - 5}")
                                
                                strategy_results.extend(radiators)
                                total_radiators += len(radiators)
                            else:
                                self.log(f"      ❌ Радиаторы не найдены в этой таблице")
                    
                    except Exception as e:
                        self.log(f"  Стр.{page_num}: ❌ ошибка — {e}")
                
                # Итоги по стратегии
                unique_names = set(r['name'] for r in strategy_results)
                total_qty = sum(r['qty'] for r in strategy_results)
                
                self.log(f"")
                self.log(f"  📈 ИТОГ {strategy_name}:")
                self.log(f"     Всего строк с радиаторами: {len(strategy_results)}")
                self.log(f"     Уникальных названий: {len(unique_names)}")
                self.log(f"     Суммарное количество: {total_qty}")
                self.log(f"     Дубликатов: {len(strategy_results) - len(unique_names)}")
                
                results[strategy_name] = {
                    'total_rows': len(strategy_results),
                    'unique_names': len(unique_names),
                    'total_qty': total_qty,
                    'duplicates': len(strategy_results) - len(unique_names),
                    'radiators': strategy_results,
                }
        
        return results
    
    # ==================================================================
    # ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ
    # ==================================================================
    
    def _table_to_dataframe(self, table: List) -> pd.DataFrame:
        """Конвертирует таблицу в DataFrame."""
        # Объединяем многострочные ячейки
        merged_rows = []
        i = 0
        while i < len(table):
            current = [str(c).strip() if c else "" for c in table[i]]
            
            # Проверяем, является ли следующая строка продолжением
            if i + 1 < len(table):
                next_row = [str(c).strip() if c else "" for c in table[i + 1]]
                current_full = " ".join(current).strip()
                next_full = " ".join(next_row).strip()
                
                if (current_full and next_full and
                    len(next_full) < 80 and
                    not re.search(r'(шт|ед|qty|кол-во|цена|price|\d+\s*шт)', next_full.lower()) and
                    not re.search(r'^\d+$', next_full.strip())):
                    
                    merged_row = []
                    max_cols = max(len(current), len(next_row))
                    for j in range(max_cols):
                        val1 = current[j] if j < len(current) else ""
                        val2 = next_row[j] if j < len(next_row) else ""
                        merged_row.append(f"{val1} {val2}" if val1 and val2 else (val1 or val2))
                    merged_rows.append(merged_row)
                    i += 2
                    continue
            
            merged_rows.append(current)
            i += 1
        
        df = pd.DataFrame(merged_rows)
        df = df.replace(r'^\s*$', '', regex=True).fillna('')
        df = df.loc[df.astype(str).apply(lambda x: (x != '').any(), axis=1)]
        df = df.loc[:, df.astype(str).apply(lambda x: (x != '').any(), axis=0)]
        
        if df.empty:
            return pd.DataFrame()
        
        df = df.reset_index(drop=True)
        df.columns = [f"Col_{i}" for i in range(len(df.columns))]
        return df
    
    def _find_name_and_qty_columns(self, df: pd.DataFrame) -> Tuple[Optional[int], Optional[int]]:
        """Автоопределение столбцов с названием и количеством."""
        name_scores = {}
        qty_scores = {}
        
        radiator_patterns = [
            r'(?:vc|cv|vk|k|с|c|v)\s*\d{2}\s*[-/]\s*\d{3,4}\s*[-/]\s*\d{3,4}',
            r'\b\d{2}\s*[-/]\s*\d{3,4}\s*[-/]\s*\d{3,4}\b',
            r'(?:k-profil|vk-profil|compact|ventil|hygiene|classic|universal)',
            r'(?:радиатор|radiator|конвектор|convector)',
        ]
        
        for col_idx in range(len(df.columns)):
            col_values = df.iloc[:, col_idx].dropna().astype(str)
            
            name_score = 0
            for val in col_values:
                val_lower = val.lower()
                for pattern in radiator_patterns:
                    if re.search(pattern, val_lower):
                        name_score += 1
                        break
            name_scores[col_idx] = name_score
            
            qty_score = 0
            for val in col_values:
                val_clean = val.strip()
                if re.match(r'^\d{1,4}$', val_clean):
                    qty_score += 1
                elif re.match(r'^\d{1,4}\s*(?:шт|компл|ед|pcs)', val_clean, re.IGNORECASE):
                    qty_score += 1
            qty_scores[col_idx] = qty_score
        
        best_name = max(name_scores, key=name_scores.get) if name_scores else None
        if best_name is not None and name_scores[best_name] == 0:
            best_name = None
        
        # Для количества исключаем столбец с названием
        filtered_qty = {c: s for c, s in qty_scores.items() if c != best_name}
        best_qty = max(filtered_qty, key=filtered_qty.get) if filtered_qty else None
        if best_qty is not None and qty_scores[best_qty] < 2:
            best_qty = None
        
        return best_name, best_qty
    
    def _extract_radiators(self, df: pd.DataFrame, name_col: int, qty_col: int) -> List[dict]:
        """Извлекает радиаторы из DataFrame."""
        radiators = []
        
        for idx in range(len(df)):
            try:
                name_val = str(df.iloc[idx, name_col]).strip()
                qty_val = str(df.iloc[idx, qty_col]).strip()
            except IndexError:
                continue
            
            if not name_val or len(name_val) < 3:
                continue
            
            # Пропускаем заголовки
            if self._is_header(name_val):
                continue
            
            # Проверяем что это радиатор
            if not self._is_radiator(name_val):
                continue
            
            # Извлекаем количество
            qty = self._extract_qty(qty_val)
            if qty <= 0:
                continue
            
            radiators.append({'name': name_val, 'qty': qty})
        
        return radiators
    
    def _is_header(self, text: str) -> bool:
        text_lower = text.lower().strip()
        headers = ['наименование', 'позиция', 'марка', 'тип', 'код', 'завод',
                   'единица', 'кол-во', 'количество', 'масса', 'примечание']
        if len(text_lower) < 60:
            for h in headers:
                if h in text_lower:
                    return True
        return False
    
    def _is_radiator(self, text: str) -> bool:
        """
        Проверяет, является ли текст названием радиатора.
        Возвращает True только для САМИХ радиаторов, не для арматуры.
        """
        if not text or len(text) < 5:
            return False
        
        text_lower = text.lower()
        
        # ================================================================
        # ЯВНЫЕ ИСКЛЮЧЕНИЯ — НЕ радиаторы (арматура, комплектующие и т.д.)
        # ================================================================
        exclusion_keywords = [
            # Арматура (даже если содержит слово «радиатор»)
            'клапан', 'кран', 'вентиль', 'задвижка', 'затвор',
            'фильтр', 'воздухоотводчик', 'воздушник', 'спускник',
            'балансировочный', 'термостатический', 'регулятор',
            'компенсатор', 'опора', 'крепление', 'кронштейн',
            
            # Комплектующие для подключения радиаторов
            'узел нижнего подключения', 'узел подключения',
            'трубка l-образная', 'трубка для подключения',
            'фитинг подключения', 'фитинг',
            'муфта', 'ниппель', 'евроконус', 'сгон', 'контргайка',
            'направляющая', 'гильза', 'заглушка', 'пробка',
            'соединитель', 'переходник',
            
            # Термостаты и головки (не радиаторы)
            'термостат', 'термоголовка', 'термостатическая головка',
            'термостатический элемент',
            
            # Трубы и фитинги
            'труба', 'трубка', 'трубопровод', 'отвод', 'тройник',
            'переход', 'фланец',
            
            # Изоляция и покрытия
            'изоляция', 'покрытие', 'эмаль', 'грунт', 'грунтовка',
            'лак', 'краска', 'мастика', 'стеклоткань', 'лента',
            'цилиндр', 'гофра',
            
            # Электрика
            'кабель', 'провод', 'щит', 'автомат', 'датчик',
            'преобразователь', 'термопреобразователь', 'счетчик',
            'теплосчетчик', 'расходомер', 'индикатор',
            'электрический', 'электро',
            
            # Вентиляция
            'насос', 'вентилятор', 'завеса', 'дефлектор',
            'воздуховод', 'решетка', 'диффузор', 'зонт',
            'шумо', 'вибро', 'сетка', 'стакан', 'конфузор',
            'вставка', 'рама', 'уголок', 'пластина',
            'шкаф', 'пульт', 'манометр', 'термометр',
            
            # Коллекторы и распределители
            'коллектор', 'распределитель', 'гребенка',
            
            # Регистры и трубчатые
            'регистр', 'полотенцесушитель',
            
            # Не панельные радиаторы
            'медно-алюминиевый', 'коралл', 'гольфстрим',
            'встраиваени', 'внутрипольный', 'напольный конвектор',
            'электрический конвектор', 'электроконвектор',
            'трубчатый',
            
            # Кронштейны (артикулы)
            'к9.2l', 'к9.2r', 'к9.3', 'к15.', 'кнс',
            'k9.2l', 'k9.2r', 'kns',
            
            # Прочее
            'грунт', 'эмаль', 'сталь разного профиля',
        ]
        
        for keyword in exclusion_keywords:
            if keyword in text_lower:
                # ВАЖНО: слово «радиатор» НЕ переопределяет исключение
                # для арматуры и комплектующих
                return False
        
        # ================================================================
        # ЯВНЫЕ ВКЛЮЧЕНИЯ — точно радиаторы
        # ================================================================
        inclusion_keywords = [
            # Базовые термины
            'радиатор', 'radiator',
            
            # Бренды панельных радиаторов
            'kermi', 'kermy', 'purmo', 'buderus', 'royal thermo',
            'royalthermo', 'evra', 'oasis', 'prado', 'korado',
            'valfex', 'rommer', 'lemax', 'stelrad', 'ferroli',
            'ruterm', 'forte', 'terma', 'korad', 'hiterm',
            'vogel', 'radson', 'hitachi', 'lidea',
            
            # Типы и серии
            'k-profil', 'vk-profil', 'profil-k', 'profil-v',
            'compact', 'ventil', 'hygiene', 'planar',
            'classic', 'universal',
            
            # Типы подключения
            'нижнее подключение', 'боковое подключение',
            'нижним подключением', 'боковым подключением',
            'донное подключение', 'донным подключением',
            
            # Панельный / стальной радиатор
            'панельный радиатор', 'стальной радиатор',
            'panel radiator', 'steel radiator',
        ]
        
        for keyword in inclusion_keywords:
            if keyword in text_lower:
                return True
        
        # ================================================================
        # ЧИСЛОВЫЕ ПАТТЕРНЫ РАДИАТОРОВ
        # ================================================================
        radiator_patterns = [
            # VC22-300-900, C21-400-400, V22-300-700
            r'(?:vc|cv|vk|k|c|v)\s*\d{2}\s*[-/]\s*\d{3,4}\s*[-/]\s*\d{3,4}',
            # 22-400-800, 33/500/1200
            r'\b\d{2}\s*[-/]\s*\d{3,4}\s*[-/]\s*\d{3,4}\b',
            # 500x800
            r'\b\d{3,4}\s*[xх]\s*\d{3,4}\b',
            # PN 22-4-04, PB 33-5-09
            r'\b(?:pn|pb)\s+\d{1,2}\s*[-]\s*\d{1,2}\s*[-]\s*\d{1,2}\b',
            # K-PROF-10-500-400, VK-Profil 22 500 1200
            r'(?:k-profil|vk-profil)[- ]\d{2}[- ]\d{3,4}[- ]\d{3,4}',
            # CV22/500/1000, VC21/300/900
            r'(?:cv|vc)\s*\d{2}\s*/\s*\d{3,4}\s*/\s*\d{3,4}',
        ]
        
        for pattern in radiator_patterns:
            if re.search(pattern, text_lower):
                return True
        
        return False
    
    def _extract_qty(self, qty_str: str) -> int:
        if not qty_str:
            return 0
        match = re.match(r'^\s*(\d+)\s*$', qty_str)
        if match:
            return int(match.group(1))
        match = re.match(r'^\s*(\d+)\s*(?:шт|компл|ед|pcs)?', qty_str, re.IGNORECASE)
        if match:
            return int(match.group(1))
        return 0


# ======================================================================
# АНАЛИЗ РЕЗУЛЬТАТОВ
# ======================================================================

def analyze_results(results: dict, logger: Logger):
    """Анализирует и сравнивает результаты всех стратегий."""
    logger.log("")
    logger.log("=" * 80)
    logger.log("📊 СВОДНЫЙ АНАЛИЗ ВСЕХ СТРАТЕГИЙ")
    logger.log("=" * 80)
    logger.log("")
    
    # Таблица сравнения
    logger.log(f"{'Стратегия':<25} {'Строк':<8} {'Уник.назв':<12} {'Сумм.qty':<12} {'Дубликатов':<12}")
    logger.log("-" * 70)
    
    best_strategy = None
    best_score = 0
    
    for name, data in results.items():
        total = data['total_rows']
        unique = data['unique_names']
        qty = data['total_qty']
        dups = data['duplicates']
        
        logger.log(f"{name:<25} {total:<8} {unique:<12} {qty:<12} {dups:<12}")
        
        # Оценка качества: больше уникальных названий + меньше дубликатов
        score = unique - dups * 0.5
        if score > best_score:
            best_score = score
            best_strategy = name
    
    logger.log("")
    logger.log(f"🏆 ЛУЧШАЯ СТРАТЕГИЯ: {best_strategy} (score={best_score:.1f})")
    logger.log(f"   Критерий: максимум уникальных названий при минимуме дубликатов")
    
    # Показываем пересечения между стратегиями
    logger.log("")
    logger.log("🔍 ПЕРЕСЕЧЕНИЯ МЕЖДУ СТРАТЕГИЯМИ:")
    
    strategy_names = list(results.keys())
    for i in range(len(strategy_names)):
        for j in range(i + 1, len(strategy_names)):
            s1 = strategy_names[i]
            s2 = strategy_names[j]
            
            names1 = set(r['name'] for r in results[s1]['radiators'])
            names2 = set(r['name'] for r in results[s2]['radiators'])
            
            common = names1 & names2
            only1 = names1 - names2
            only2 = names2 - names1
            
            logger.log(f"  {s1} vs {s2}:")
            logger.log(f"    Общих названий: {len(common)}")
            logger.log(f"    Только в {s1}: {len(only1)}")
            logger.log(f"    Только в {s2}: {len(only2)}")


# ======================================================================
# MAIN
# ======================================================================

def main():
    # Определяем путь к PDF
    if len(sys.argv) > 1:
        pdf_path = sys.argv[1]
    elif TEST_PDF:
        pdf_path = TEST_PDF
    else:
        print("Использование: python pdf_debug.py \"путь/к/файлу.pdf\"")
        print("Или пропишите путь в переменной TEST_PDF в начале скрипта")
        sys.exit(1)
    
    if not os.path.exists(pdf_path):
        print(f"❌ Файл не найден: {pdf_path}")
        sys.exit(1)
    
    # Создаём лог-файл рядом с PDF
    log_dir = os.path.dirname(pdf_path) or "."
    log_name = f"debug_{os.path.splitext(os.path.basename(pdf_path))[0]}.log"
    log_path = os.path.join(log_dir, log_name)
    
    logger = Logger(log_path)
    
    try:
        parser = DebugPDFParser(logger)
        results = parser.test_all_strategies(pdf_path)
        analyze_results(results, logger)
    except Exception as e:
        logger.log(f"❌ ОШИБКА: {e}", "ERROR")
        import traceback
        logger.log(traceback.format_exc(), "ERROR")
    finally:
        logger.save()


if __name__ == "__main__":
    main()