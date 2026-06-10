"""
Универсальный парсер для данных из буфера обмена.
Извлекает: артикул, количество, нормализованное название.
"""

import re
from typing import Tuple, Optional


class UniversalParser:
    """Универсальный парсер для вставки из буфера."""
    
    # Паттерны для извлечения артикулов (в порядке приоритета)
    ARTICLE_PATTERNS = [
        # LaggarTT/Meteor радиаторы: 7724655312, 7724755312
        (r'\b(7724[67]\d{6})\b', 1),
        # Котлы Meteor: 10680203003, 10680503011, 10680725001
        (r'\b(1068\d{7})\b', 2),
        # Котлы ГАЗ 6000: 8732306494, 8732302142
        (r'\b(8732\d{6})\b', 3),
        # Бойлеры: 7I121011001, 7L121011003, 7U121011001
        (r'\b(7[A-Z]\d{9})\b', 4),
        # Кронштейны: К15.4300, К9.2L, КНС470, К31.35, PLN20
        (r'\b([КK]\d{1,2}\.\d{1,2}[A-Z]?\d*)\b', 5),
        (r'\b([КK][A-Z]{2}\d+)\b', 5),
        (r'\b([A-Z]{2,4}\d+)\b', 5),
        # Дымоходы: NEW WT60100-05, WT60100-01LN, WT80125-01
        (r'\b(NEW\s+[A-Z]+\d+-\d+)\b', 6),
        (r'\b([A-Z]+\d+-\d+[A-Z]*\d*)\b', 7),
        # Фланцы: B-01
        (r'\b([A-Z]-\d+)\b', 8),
        # Датчики: AC01000061, BB99000142
        (r'\b([A-Z]{2}\d{8})\b', 9),
        # Комплекты перенастройки: 30100000002, 30100000001
        (r'\b(301\d{8})\b', 10),
        # Защитные решетки: 8755D70101
        (r'\b(8755D\d{8})\b', 11),
        # Любые 10-11 цифр (запасной вариант)
        (r'\b(\d{10,11})\b', 12),
    ]
    
    # Паттерны для извлечения количества (в порядке приоритета)
    QUANTITY_PATTERNS = [
        # "- 3 шт", "— 5 штук", "- 64 ШТ."
        r'[–\-]\s*(\d+)\s*шт',
        # "= 4 шт", "= 1 шт."
        r'=\s*(\d+)\s*шт',
        # "2 штуки", "1 штук", "5 штук"
        r'(\d+)\s*шт\w*',
        # "3 шт.", "10 шт"
        r'(\d+)\s*шт\.?',
        # "x 10", "х 5"
        r'[xх]\s*(\d+)',
        # "— 64" (число после тире в конце строки)
        r'[–\-]\s*(\d+)\s*$',
        # просто число в конце строки
        r'(\d+)\s*$',
        # число в начале строки (редко)
        r'^(\d+)\s+',
    ]
    
    @classmethod
    def parse_line(cls, text: str) -> Tuple[Optional[str], int, str]:
        """
        Парсит одну строку.
        
        Returns:
            (артикул, количество, очищенное_название)
        """
        if not text:
            return None, 0, ""
        
        text_clean = text.strip()
        
        # 1. Извлекаем артикул
        article = cls._extract_article(text_clean)
        
        # 2. Извлекаем количество
        quantity = cls._extract_quantity(text_clean)
        
        # 3. Очищаем название от артикула и количества
        clean_name = cls._clean_name(text_clean, article, quantity)
        
        return article, quantity, clean_name
    
    @classmethod
    def _extract_article(cls, text: str) -> Optional[str]:
        """Извлекает артикул из текста."""
        for pattern, _ in cls.ARTICLE_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return None
    
    @classmethod
    def _extract_quantity(cls, text: str) -> int:
        """Извлекает количество из текста."""
        for pattern in cls.QUANTITY_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    qty = int(match.group(1))
                    if qty > 0 and qty < 10000:
                        return qty
                except:
                    pass
        return 0
    
    @classmethod
    def _clean_name(cls, text: str, article: Optional[str], quantity: int) -> str:
        """
        Очищает название от артикула и количества.
        """
        result = text
        
        # Удаляем артикул (в скобках или без)
        if article:
            # Удаляем артикул в скобках
            result = re.sub(r'\(' + re.escape(article) + r'\)', '', result)
            # Удаляем артикул без скобок как отдельное слово
            result = re.sub(r'\b' + re.escape(article) + r'\b', '', result)
        
        # Удаляем количество с "шт", "штук" и т.д.
        if quantity > 0:
            patterns = [
                r'[–\-]\s*' + str(quantity) + r'\s*шт\w*',
                r'=\s*' + str(quantity) + r'\s*шт\w*',
                r'\s*' + str(quantity) + r'\s*шт\w*',
                r'[xх]\s*' + str(quantity),
                r'[–\-]\s*' + str(quantity) + r'\s*$',
                r'\s*' + str(quantity) + r'\s*$',
                r'^\s*' + str(quantity) + r'\s+',
            ]
            for pattern in patterns:
                result = re.sub(pattern, '', result, flags=re.IGNORECASE)
        
        # Удаляем лишние пробелы и знаки
        result = re.sub(r'\s+', ' ', result)
        result = result.strip(' ()-–=,;:')
        
        return result
    
    @classmethod
    def parse_dataframe(cls, df) -> list:
        """
        Парсит весь DataFrame.
        DataFrame уже содержит выбранные пользователем столбцы:
        - первый столбец (индекс 0) - наименование/артикул
        - второй столбец (индекс 1) - количество
        Возвращает список словарей с результатами.
        """
        results = []
        for idx, row in df.iterrows():
            # Первый столбец - наименование/артикул
            text = str(row.iloc[0]).strip() if len(row) > 0 else ""
            
            # Второй столбец - количество
            qty_str = str(row.iloc[1]).strip() if len(row) > 1 else ""
            
            # Парсим строку (извлекаем артикул и очищаем название)
            article, _, clean_name = cls.parse_line(text)
            
            # Извлекаем количество из второго столбца
            qty = cls._extract_quantity(qty_str)
            
            # Если количество не найдено, пробуем извлечь из текста
            if qty == 0:
                _, qty_from_text, _ = cls.parse_line(text)
                qty = qty_from_text
            
            # Если артикул не найден, пробуем извлечь из текста напрямую
            if not article:
                article = cls._extract_article(text)
            
            results.append({
                'original_text': text,
                'article': article,
                'quantity': qty,
                'clean_name': clean_name,
                'row_index': idx,
            })
        
        return results