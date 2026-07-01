"""
Поиск оборудования в базе Все_категории.xlsx.
Использует EquipmentNormalizer для интеллектуального парсинга.
"""
import re
from typing import Optional, Dict, List
from pathlib import Path
import pandas as pd
from nextt.logger import get_logger
from nextt.config import get_resource_path
from nextt.experimental.equipment_normalizer import EquipmentNormalizer

logger = get_logger(__name__)

class EquipmentSearcher:
    """Поиск оборудования по артикулу или ключевым словам."""
    
    def __init__(self, data_provider=None, selected_categories=None):
        self.data_provider = data_provider
        self.selected_categories = selected_categories
        self.df = self._load_all_categories()
        
        # Фильтруем по категориям
        filtered_df = self._filter_by_categories(self.df)
        
        # Создаём нормализатор с отфильтрованной базой
        self.normalizer = EquipmentNormalizer(filtered_df, debug=True)

    def _filter_by_categories(self, df: pd.DataFrame) -> pd.DataFrame:
        """Фильтрует DataFrame по выбранным категориям."""
        if self.selected_categories is None or len(self.selected_categories) == 0:
            return df
        
        # Ищем столбец с иерархией/категориями
        hierarchy_col = None
        for col in df.columns:
            col_lower = str(col).lower()
            if 'иерархия' in col_lower or 'категория' in col_lower or 'category' in col_lower:
                hierarchy_col = col
                break
        
        if hierarchy_col is None:
            logger.warning("Столбец с категориями не найден, фильтрация не применяется")
            return df
        
        # Фильтруем
        filtered_df = df[df[hierarchy_col].astype(str).str.lower().isin([c.lower() for c in self.selected_categories])]
        logger.info(f"Фильтрация по категориям {self.selected_categories}: {len(filtered_df)} из {len(df)} записей")
        
        return filtered_df

    def _normalize_quantity_text(self, text: str) -> str:
        """
        Нормализует текст для поиска количества:
        - заменяет все виды тире на обычный дефис
        - нормализует пробелы
        - исправляет опечатки в слове "штука"
        """
        if not text:
            return text
        
        # Замена всех видов тире на обычный дефис
        dash_patterns = [
            '–',   # среднее тире
            '—',   # длинное тире
            '‐',   # дефис
            '‑',   # неразрывный дефис
            '‒',   # цифровое тире
        ]
        result = text
        for dash in dash_patterns:
            result = result.replace(dash, '-')
         
        # Исправляем опечатки в "штука"
        result = result.replace('щтука', 'штука')
        result = result.replace('щтук', 'штук')
        
        # Нормализуем пробелы: убираем лишние
        result = re.sub(r'\s+', ' ', result)
         
        return result

    def extract_quantity(self, text: str) -> int:
        """
        Извлекает количество из текста.
        """
        if not text:
            return 0
        
        # Нормализуем текст
        normalized = self._normalize_quantity_text(text)
        
        # ========== ПАТТЕРН 1: слово + дефис + пробел + число + пробел + штука ==========
        pattern1 = r'\w+-\s*(\d+(?:[.,]\d+)?)\s*(?:шт\.?|штук[аи]?|штука)\b'
        match = re.search(pattern1, normalized, re.IGNORECASE)
        if match:
            try:
                qty = int(float(match.group(1).replace(',', '.')))
                if qty > 0:
                    logger.info(f"  Количество найдено (паттерн 1 - слово+дефис+штука): {qty}")
                    return qty
            except (ValueError, TypeError):
                pass
        
        # ========== ПАТТЕРН 2: "В наличии" или "Нет в наличии" + число ==========
        pattern2 = r'(?:в наличии|нет в наличии)\s+(\d+(?:[.,]\d+)?)'
        match = re.search(pattern2, normalized, re.IGNORECASE)
        if match:
            try:
                qty = int(float(match.group(1).replace(',', '.')))
                if qty > 0:
                    logger.info(f"  Количество найдено (паттерн 2 - В наличии): {qty}")
                    return qty
            except (ValueError, TypeError):
                pass
        
        # ========== ПАТТЕРН 3: тире + число + шт ==========
        pattern3 = r'-\s*(\d+(?:[., ]\d+)?)\s*(?:шт\.?|штук[аи]?|штука)\b'
        match = re.search(pattern3, normalized, re.IGNORECASE)
        if match:
            try:
                qty = int(float(match.group(1).replace(',', '.')))
                if qty > 0:
                    logger.info(f"  Количество найдено (паттерн 3 - тире+штука): {qty}")
                    return qty
            except (ValueError, TypeError):
                pass
        
        # ========== ПАТТЕРН 4: число + штука (без тире) ==========
        pattern4 = r'(\d+(?:[.,]\d+)?)\s*(?:шт\.?|штук[аи]?|штука)\b'
        match = re.search(pattern4, normalized, re.IGNORECASE)
        if match:
            try:
                qty = int(float(match.group(1).replace(',', '.')))
                if qty > 0:
                    logger.info(f"  Количество найдено (паттерн 4 - число+штука): {qty}")
                    return qty
            except (ValueError, TypeError):
                pass
        
        # ========== ПАТТЕРН 5: число в конце строки (после пробела) ==========
        pattern5 = r'(\d+(?:[.,]\d+)?)\s*$'
        match = re.search(pattern5, normalized.strip())
        if match:
            try:
                qty = int(float(match.group(1).replace(',', '.')))
                if 1 <= qty <= 10000:
                    logger.info(f"  Количество найдено (паттерн 5 - конец строки): {qty}")
                    return qty
            except (ValueError, TypeError):
                pass
        
        # ========== ПАТТЕРН 6: число в начале строки ==========
        pattern6 = r'^(\d+(?:[.,]\d+)?)\s*(?:шт\.?|штук[аи]?)?\s+'
        match = re.search(pattern6, normalized, re.IGNORECASE)
        if match:
            try:
                qty = int(float(match.group(1).replace(',', '.')))
                if 1 <= qty <= 10000:
                    logger.info(f"  Количество найдено (паттерн 6 - начало строки): {qty}")
                    return qty
            except (ValueError, TypeError):
                pass
        
        # ========== ПАТТЕРН 7: сложные форматы (1+2, 2-3) ==========
        pattern7 = r'(\d+(?:\+\d+|\-\d+|\s*[xх]\s*\d+)?)\s*(?:шт\.?|штук[аи]?)'
        match = re.search(pattern7, normalized, re.IGNORECASE)
        if match:
            quantity_str = match.group(1)
            if '+' in quantity_str:
                parts = quantity_str.split('+')
                total = 0
                for part in parts:
                    try:
                        total += int(float(part.strip().replace(',', '.')))
                    except (ValueError, TypeError):
                        pass
                if total > 0:
                    logger.info(f"  Количество найдено (паттерн 7 - сложный): {total}")
                    return total
            elif '-' in quantity_str:
                parts = quantity_str.split('-')
                try:
                    total = int(float(parts[0].strip().replace(',', '.')))
                    logger.info(f"  Количество найдено (паттерн 7 - диапазон): {total}")
                    return total
                except (ValueError, TypeError):
                    pass
        
        return 0

    def _normalize_article(self, article: str) -> str:
        """Нормализует артикул: заменяет русские буквы на латинские."""
        if not article:
            return article
        
        letter_mapping = {
            'К': 'K', 'к': 'k',
            'С': 'C', 'с': 'c',
            'Н': 'H', 'н': 'h',
            'Р': 'P', 'р': 'p',
            'Т': 'T', 'т': 't',
            'В': 'B', 'в': 'b',
            'Х': 'X', 'х': 'x',
            'У': 'Y', 'у': 'y',
            'А': 'A', 'а': 'a',
            'О': 'O', 'о': 'o',
            'Е': 'E', 'е': 'e',
            'М': 'M', 'м': 'm',
            'П': 'P', 'п': 'p',
            'Г': 'G', 'г': 'g',
            'Л': 'L', 'л': 'l',
            'Д': 'D', 'д': 'd',
        }
        
        result = []
        for ch in article:
            result.append(letter_mapping.get(ch, ch))
        
        return ''.join(result)

    def _load_all_categories(self) -> pd.DataFrame:
        """Загружает данные из файла Все_категории.xlsx."""
        try:
            file_path = get_resource_path("Все_категории.xlsx")
            if not Path(file_path).exists():
                logger.warning(f"Файл Все_категории.xlsx не найден: {file_path}")
                return pd.DataFrame()
            
            # Пробуем загрузить лист 'Прайс'
            try:
                df = pd.read_excel(file_path, sheet_name="Прайс", engine='openpyxl')
                logger.info(f"Загружен лист 'Прайс' из Все_категории.xlsx")
            except Exception:
                # Если нет листа 'Прайс', загружаем первый лист
                try:
                    df = pd.read_excel(file_path, sheet_name="Лист1", engine='openpyxl')
                    logger.info(f"Загружен лист 'Лист1' из Все_категории.xlsx")
                except Exception:
                    xl = pd.ExcelFile(file_path)
                    sheet_names = xl.sheet_names
                    if sheet_names:
                        df = pd.read_excel(file_path, sheet_name=sheet_names[0], engine='openpyxl')
                        logger.info(f"Загружен первый лист '{sheet_names[0]}' из Все_категории.xlsx")
                    else:
                        logger.error("В файле Все_категории.xlsx нет листов")
                        return pd.DataFrame()
            
            # Приводим столбцы к стандартному виду
            article_col = None
            name_col = None
            price_col = None
             
            for col in df.columns:
                col_str = str(col).lower().strip()
                if col_str in ['артикул', 'article', 'art', 'код', 'code']:
                    article_col = col
                elif col_str in ['наименование', 'name', 'название', 'товар', 'product']:
                    name_col = col
                elif col_str in ['цена', 'price', 'cost', 'стоимость']:
                    price_col = col
            
            if article_col is None and len(df.columns) > 0:
                article_col = df.columns[0]
            if name_col is None and len(df.columns) > 1:
                name_col = df.columns[1]
            
            rename_dict = {}
            if article_col:
                rename_dict[article_col] = 'Артикул'
            if name_col:
                rename_dict[name_col] = 'Наименование'
            if price_col:
                rename_dict[price_col] = 'Цена'
            
            if rename_dict:
                df = df.rename(columns=rename_dict)
            
            df['Артикул'] = df['Артикул'].astype(str).str.strip()
            df['Наименование'] = df['Наименование'].astype(str).str.strip()
            df = df.fillna('')
             
            df = df[df['Артикул'] != '']
            df = df[df['Артикул'] != 'nan']
            
            logger.info(f"Загружено {len(df)} записей из Все_категории.xlsx")
            
            # Для отладки показываем несколько кронштейнов
            brackets = df[df['Артикул'].str.contains(r'[КK]\d', na=False)]
            if not brackets.empty:
                logger.info(f"Примеры кронштейнов в базе: {brackets['Артикул'].head(5).tolist()}")
            
            return df
            
        except Exception as e:
            logger.error(f"Ошибка загрузки Все_категории.xlsx: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return pd.DataFrame()

    def find_by_article(self, article: str) -> Optional[pd.Series]:
        """Находит оборудование по артикулу с нормализацией."""
        if not article or self.df.empty:
            return None
        
        article_clean = str(article).strip()
        normalized_article = self._normalize_article(article_clean)
        
        logger.info(f"  Поиск артикула: '{article_clean}' → нормализован: '{normalized_article}'")
        
        # Прямое совпадение
        mask = self.df['Артикул'].astype(str).str.strip() == article_clean
        matches = self.df[mask]
        
        if not matches.empty:
            logger.info(f"  Найден прямой артикул: {article_clean}")
            return matches.iloc[0]
        
        # Поиск с нормализацией
        for idx, row in self.df.iterrows():
            db_art = str(row['Артикул']).strip()
            normalized_db = self._normalize_article(db_art)
            if normalized_db == normalized_article:
                logger.info(f"  Найден нормализованный артикул: {db_art} → {normalized_db}")
                return row
        
        # Поиск по вхождению
        for idx, row in self.df.iterrows():
            db_art = str(row['Артикул']).strip()
            if article_clean in db_art or db_art in article_clean:
                logger.info(f"  Найден по вхождению: {db_art}")
                return row
        
        return None

    def _extract_article_simple(self, text: str) -> Optional[str]:
        """Простое извлечение артикула из текста с нормализацией."""
        # Нормализуем текст для поиска артикулов
        normalized = self._normalize_article(text)
        
        # Сначала ищем кронштейны
        bracket_patterns = [
            r'\b([КK]\d{1,2}\.\d{1,4}[A-Za-zА-Яа-я]?\d*)\b',
            r'\b([КK][НH][СC]\d{3,4})\b',
            r'\b([КK]15[НH]\.\d{3,4})\b',
            r'\b([КK]15\.\d{1,2})\b',
            r'\b([КK]9\.\d[LRS]?)\b',
            r'\b(PLN\d+)\b',
        ]
        
        for pattern in bracket_patterns:
            match = re.search(pattern, normalized, re.IGNORECASE)
            if match:
                article = match.group(1).strip()
                logger.info(f"  Найден артикул кронштейна: '{article}'")
                return article
        
        # Остальные паттерны
        patterns = [
            r'\b(1068\d{7})\b',
            r'\b(10680\d{6})\b',
            r'\b(87323\d{6})\b',
            r'\b(8732\d{6})\b',
            r'\b(7[A-Z]\d{9})\b',
            r'\b([A-Z]{2}\d{8})\b',
            r'\b(301\d{8})\b',
            r'\b(8755D\d{8})\b',
            r'\b([A-Z]-\d+)\b',
            r'\b(\d{10,11})\b',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, normalized, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        
        return None

    def match_line(self, line: str, quantity: Optional[int] = None) -> Dict:
        """
        Обрабатывает одну строку с использованием EquipmentNormalizer.
        """
        result = {
            'success': False,
            'article': '',
            'name': '',
            'quantity': 0,
            'original_text': line,
            'error': '',
            'confidence': 0.0,
            'source': ''
        }
        
        logger.info("-" * 50)
        logger.info(f"Строка: '{line[:100]}'")
        
        # Определяем количество
        qty = quantity if quantity is not None else self.extract_quantity(line)
        result['quantity'] = qty
        logger.info(f"  Количество: {qty}")
        
        if qty <= 0:
            result['error'] = 'Количество не найдено'
            logger.warning(f"  ❌ Количество = 0")
            return result

        # Используем EquipmentNormalizer для нечёткого поиска
        logger.info(f"  Пробуем нормализатор...")
        normalized = self.normalizer.match_line(line, qty)
        
        if normalized['success']:
            result['success'] = True
            result['article'] = normalized['article']
            result['name'] = normalized['name']
            result['confidence'] = normalized['confidence']
            result['source'] = normalized['source']
            logger.info(f"  ✅ УСПЕХ через нормализатор!")
            return result

        result['error'] = 'Не найдено в базе'
        logger.warning(f"  ❌ НЕ НАЙДЕНО")
        return result

    def match_dataframe(self, df: pd.DataFrame, name_col: int = 0, qty_col: int = 1) -> List[Dict]:
        """Обрабатывает весь DataFrame."""
        logger.info("=" * 70)
        logger.info(f"НАЧАЛО ОБРАБОТКИ: {len(df)} строк")
        logger.info("=" * 70)
        logger.info(f"Столбцы в df: {list(df.columns)}")
        
        # Автоматически определяем столбцы по их именам
        name_column_name = None
        qty_column_name = None
        
        for col in df.columns:
            col_lower = str(col).lower()
            # Для столбца наименования
            if 'наименование' in col_lower or 'name' in col_lower:
                name_column_name = col
            # Для столбца количества (учитываем 'кол-во' с дефисом)
            if 'кол-во' in col_lower or 'колво' in col_lower or 'количество' in col_lower or 'qty' in col_lower:
                qty_column_name = col
        
        # Если нашли по именам, используем их
        if name_column_name:
            name_col = df.columns.get_loc(name_column_name)
            logger.info(f"  Найден столбец наименования: '{name_column_name}' (индекс {name_col})")
        else:
            logger.info(f"  Столбец наименования не найден, используем индекс {name_col}")
        
        if qty_column_name:
            qty_col = df.columns.get_loc(qty_column_name)
            logger.info(f"  Найден столбец количества: '{qty_column_name}' (индекс {qty_col})")
        else:
            logger.info(f"  Столбец количества не найден, используем индекс {qty_col}")
        
        results = []
        for idx, row in df.iterrows():
            # Берём название из столбца наименования
            name = str(row.iloc[name_col]).strip() if len(row) > name_col else ''
            
            # Берём количество из столбца количества
            qty_str = str(row.iloc[qty_col]).strip() if len(row) > qty_col else ''
            
            logger.info(f"  Строка {idx}: name='{name[:50]}', qty_str='{qty_str}'")
            
            # Парсим количество
            qty = self.extract_quantity(qty_str)
            
            # Если количество не найдено, пробуем извлечь из названия
            if qty == 0: 
                qty = self.extract_quantity(name)
            
            results.append(self.match_line(name, qty))
        
        found = sum(1 for r in results if r['success'])
        logger.info("=" * 70)
        logger.info(f"ИТОГ: Найдено {found} из {len(results)} строк")
        logger.info("=" * 70)
        return results

    def determine_data_type(self, df: pd.DataFrame) -> str:
        """Определяет тип данных: радиаторы или оборудование."""
        if df.empty:
            return 'unknown'
        
        radiator = 0
        equipment = 0
        
        # Индикаторы для самих радиаторов (требуют подбора аналогов)
        radiator_indicators = ['k-profil', 'vk-profil', 'радиатор', '77246', '77247', '/300/', '/400/', '/500/']
        
        # Индикаторы для оборудования (котлы, бойлеры, дымоходы, фланцы и т.д.)
        equipment_indicators = ['котел', 'котёл', 'бойлер', 'дымоход', 'газовый', 'газ 6000', 'кронштейн', 'фланец']
        
        # НОВЫЕ ИНДИКАТОРЫ: Комплектующие к радиаторам (решетки, клипсы и т.д.)
        # Они должны классифицироваться как 'equipment', чтобы не запускать логику подбора аналогов радиаторов
        accessory_indicators = [
            'решетка', 'решётка', 'клипса', 'заглушка', 'кран воздушный', 'воздушный кран',
            'переходник', 'адаптер', 'панель боковая', 'боковая панель', 'колпачок',
            'регулятор', 'набор клипс', 'набор адаптеров'
        ]
        
        for i in range(min(10, len(df))):
            text = ' '.join(str(v) for v in df.iloc[i].values).lower()
            
            if any(ind in text for ind in radiator_indicators):
                radiator += 1
            elif any(ind in text for ind in equipment_indicators):
                equipment += 1
            elif any(ind in text for ind in accessory_indicators):
                # Комплектующие считаем оборудованием, так как они есть в базе
                equipment += 1
                logger.info(f"  Найдены признаки комплектующих в строке {i}")
        
        logger.info(f"Определение типа: radiator={radiator}, equipment={equipment}")
        
        if radiator == 0 and equipment == 0:
            for i in range(min(10, len(df))):
                text = ' '.join(str(v) for v in df.iloc[i].values)
                if self._extract_article_simple(text):
                    equipment += 1
        
        return 'radiators' if radiator > equipment else 'equipment'