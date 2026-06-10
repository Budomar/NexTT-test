"""
product_normalizer.py - Извлечение параметров товара из текста
Универсальный парсер для любых форматов названий.
"""

import re
from typing import Dict, Optional, Tuple, List
from dataclasses import dataclass, field

from nextt.logger import get_logger

logger = get_logger(__name__)



@dataclass
class ProductParams:
    """Структурированные параметры товара."""
    # Основные
    product_type: str = ""  # котел, бойлер, дымоход, комплект, датчик, радиатор, кронштейн
    brand: str = ""         # laggartt, meteor, devotion
    
    # Для котлов
    model: str = ""         # B30, C11, M30, T2, Q3, GAZ6000
    power: Optional[int] = None
    conn_type: str = ""     # C, H
    has_wifi: bool = False
    has_ot: bool = False
    
    # Для дымоходов
    size: str = ""          # DN60/100, DN80/125
    article_code: str = ""  # WT60100-01LN
    is_condensing: bool = False  # True если для конденсационного котла (есть PP или LN)
    
    # Для бойлеров
    volume: Optional[int] = None  # 150, 200, 300
    
    # Для комплектов
    kit_type: str = ""      # сжиженный газ, перенастройка
    
    # Для радиаторов
    radiator_type: str = ""  # 10, 11, 20, 21, 22, 30, 33
    height: Optional[int] = None
    length: Optional[int] = None
    connection: str = ""     # VK, K
    
    # Для кронштейнов
    bracket_article: str = ""
    
    # Общее
    article: str = ""
    confidence: float = 0.0
    original_text: str = ""
    
    def to_key(self) -> tuple:
        """Возвращает ключ для индексации (только значимые параметры)."""
        if self.product_type == 'boiler':
            return ('boiler', self.brand, self.volume)
        elif self.product_type == 'chimney':
            return ('chimney', self.size or self.article_code)
        elif self.product_type == 'conversion_kit':
            return ('conversion_kit', self.kit_type, self.power)
        elif self.product_type == 'boiler':
            return ('boiler', self.model, self.power, self.conn_type, self.has_wifi)
        elif self.product_type == 'radiator':
            return ('radiator', self.radiator_type, self.height, self.length, self.connection)
        elif self.product_type == 'bracket':
            return ('bracket', self.bracket_article)
        else:
            return (self.product_type, self.brand, self.model, self.power)
    
    def matches_params(self, other: 'ProductParams') -> float:
        """
        Сравнивает два набора параметров.
        Возвращает уверенность (0-1).
        """
        score = 0.0
        max_score = 0.0
        
        # Тип товара (обязательно для совпадения)
        if self.product_type and other.product_type:
            max_score += 0.2
            if self.product_type == other.product_type:
                score += 0.2
            else:
                # Разные типы товаров - низкая уверенность
                return 0.1
        
        # Модель
        if self.model and other.model:
            max_score += 0.2
            if self.model.upper() == other.model.upper():
                score += 0.2
        
        # Мощность
        if self.power and other.power:
            max_score += 0.15
            if self.power == other.power:
                score += 0.15
        
        # Тип подключения (C/H)
        if self.conn_type and other.conn_type:
            max_score += 0.1
            if self.conn_type == other.conn_type:
                score += 0.1
        
        # Wi-Fi
        if self.has_wifi == other.has_wifi:
            max_score += 0.05
            score += 0.05
        
        # Бренд (с приоритетом LaggarTT)
        if self.brand and other.brand:
            max_score += 0.05
            if self.brand == other.brand:
                score += 0.05
        
        # Объём для бойлеров
        if self.volume and other.volume:
            max_score += 0.15
            if self.volume == other.volume:
                score += 0.15
        
        # ========== ДЛЯ ДЫМОХОДОВ ==========
        if self.product_type == 'chimney' and other.product_type == 'chimney':
            # Артикул WT...
            if self.article_code and other.article_code:
                max_score += 0.25
                if self.article_code == other.article_code:
                    score += 0.25
            
            # Размер DN
            if self.size and other.size:
                max_score += 0.2
                if self.size == other.size:
                    score += 0.2
            
            # Конденсационный тип (PP/LN)
            max_score += 0.15
            if self.is_condensing == other.is_condensing:
                score += 0.15
        
        # ========== ДЛЯ КОМПЛЕКТОВ ==========
        if self.product_type == 'conversion_kit' and other.product_type == 'conversion_kit':
            # Тип комплекта (сжиженный газ и т.д.)
            if self.kit_type and other.kit_type:
                max_score += 0.2
                if self.kit_type == other.kit_type:
                    score += 0.2
        
        # ========== ДЛЯ РАДИАТОРОВ ==========
        if self.product_type == 'radiator' and other.product_type == 'radiator':
            if self.radiator_type and other.radiator_type:
                max_score += 0.15
                if self.radiator_type == other.radiator_type:
                    score += 0.15
            
            if self.height and other.height:
                max_score += 0.1
                if self.height == other.height:
                    score += 0.1
            
            if self.length and other.length:
                max_score += 0.1
                if self.length == other.length:
                    score += 0.1
            
            if self.connection and other.connection:
                max_score += 0.1
                if self.connection == other.connection:
                    score += 0.1
        
        # ========== ДЛЯ КРОНШТЕЙНОВ ==========
        if self.product_type == 'bracket' and other.product_type == 'bracket':
            if self.bracket_article and other.bracket_article:
                max_score += 0.3
                if self.bracket_article == other.bracket_article:
                    score += 0.3
        
        if max_score == 0:
            return 0.0
        
        return score / max_score


class ProductNormalizer:
    """
    Универсальный извлекатель параметров товара.
    Работает с любыми текстами: и с запросами пользователя, и с названиями из базы.
    """
    
    # Сопоставление русских букв латинским
    LETTER_MAPPING = {
        'А': 'A', 'а': 'a', 'В': 'B', 'в': 'b', 'С': 'C', 'с': 'c',
        'Н': 'H', 'н': 'h', 'Р': 'P', 'р': 'p', 'Т': 'T', 'т': 't',
        'К': 'K', 'к': 'k', 'Х': 'X', 'х': 'x', 'У': 'Y', 'у': 'y',
        'О': 'O', 'о': 'o', 'Е': 'E', 'е': 'e', 'М': 'M', 'м': 'm',
        'П': 'P', 'п': 'p', 'Г': 'G', 'г': 'g', 'Л': 'L', 'л': 'l',
        'Д': 'D', 'д': 'd',
    }
    
    # Паттерны для извлечения мощности
    POWER_PATTERNS = [
        r'(\d{2})\s*квт',
        r'(\d{2})\s*kw',
        r'мощность\s*(\d{2})',
        r'\b(10|12|14|18|20|24|26|28|30|32|35|36|45|60|80)\b',
    ]
    
    # Паттерны для моделей котлов
    MODEL_PATTERNS = [
        r'\b(B20|B23|B30)\b',
        r'\b(C11|C30)\b',
        r'\b(M30)\b',
        r'\b(T2)\b',
        r'\b(Q3)\b',
        r'(ГАЗ|GAZ)\s*6000',
    ]
    
    def __init__(self):
        pass
    
    def _log(self, message: str, level: str = "INFO") -> None:
        if level == "ERROR":
            logger.error(f"[ProductNormalizer] {message}")
        elif level == "WARNING":
            logger.warning(f"[ProductNormalizer] {message}")
        else:
            logger.info(f"[ProductNormalizer] {message}")
    
    def _normalize(self, text: str) -> str:
        """Нормализует текст: русские буквы -> латинские, нижний регистр."""
        if not text:
            return ""
        result = []
        for ch in text:
            result.append(self.LETTER_MAPPING.get(ch, ch))
        return ''.join(result).lower()
    
    def extract(self, text: str) -> ProductParams:
        """
        Главный метод: извлекает параметры из любого текста.
        """
        params = ProductParams(original_text=text)
        if not text:
            return params
        
        normalized = self._normalize(text)
        text_upper = text.upper()
        
        # 1. Определяем тип товара
        params.product_type = self._extract_product_type(text)
        
        # 2. Извлекаем бренд
        params.brand = self._extract_brand(text)
        
        # 3. Для котлов
        if params.product_type == 'boiler':
            self._extract_boiler_params(params, text, normalized, text_upper)
        
        # 4. Для дымоходов
        elif params.product_type == 'chimney':
            self._extract_chimney_params(params, text_upper)
        
        # 5. Для бойлеров
        elif params.product_type == 'water_heater':
            self._extract_water_heater_params(params, text)
        
        # 6. Для комплектов
        elif params.product_type == 'conversion_kit':
            self._extract_conversion_kit_params(params, text)
        
        # 7. Для радиаторов
        elif params.product_type == 'radiator':
            self._extract_radiator_params(params, text)
        
        # 8. Для кронштейнов
        elif params.product_type == 'bracket':
            self._extract_bracket_params(params, text_upper)
        
        # 9. Для датчиков
        elif params.product_type == 'sensor':
            pass  # Датчики не имеют дополнительных параметров
        
        # 10. Для запчастей
        elif params.product_type == 'part':
            pass
        
        return params
    
    def _extract_product_type(self, text: str) -> str:
        """Определяет тип товара по ключевым словам или паттернам."""
        text_lower = text.lower()
        
        # 1. По ключевым словам
        if any(x in text_lower for x in ['котел', 'котёл']):
            return 'boiler'
        if any(x in text_lower for x in ['бойлер', 'водонагреватель']):
            return 'water_heater'
        if any(x in text_lower for x in ['дымоход', 'chimney', 'wt', 'dn']):
            return 'chimney'
        if any(x in text_lower for x in ['комплект', 'перенастройка', 'форсунка', 'lpg', 'сжиж']):
            return 'conversion_kit'
        if any(x in text_lower for x in ['радиатор', 'profil', 'kermi']):
            return 'radiator'
        if any(x in text_lower for x in ['кронштейн', 'bracket']):
            return 'bracket'
        if any(x in text_lower for x in ['датчик', 'температуры', 'ntc']):
            return 'sensor'
        if any(x in text_lower for x in ['вентилятор', 'плата', 'клапан', 'теплообменник', 'насос', 'горелка']):
            return 'part'
        
        # 2. По паттернам (если нет ключевых слов)
        # Паттерн котла: B30-18С, В30-18С, M30-26H, C11-24C
        if re.search(r'[BCMВС]\d{2}[- ]?\d{2}[CHСН]', text, re.IGNORECASE):
            return 'boiler'
        
        # Паттерн ГАЗ 6000
        if re.search(r'(ГАЗ|GAZ)\s*6000', text, re.IGNORECASE):
            return 'boiler'
        
        # Паттерн дымохода: DN60/100, WT80125-01
        if re.search(r'DN\d{2,3}/\d{2,3}', text, re.IGNORECASE):
            return 'chimney'
        if re.search(r'WT\d{5,6}-\d+', text, re.IGNORECASE):
            return 'chimney'
        
        # Паттерн радиатора: 22/400/700, 22-400-700
        if re.search(r'\d{2}[/-]\d{3,4}[/-]\d{3,4}', text):
            return 'radiator'
        
        # Паттерн артикула кронштейна: К15.4300, КНС470
        if re.search(r'[КK]\d{1,2}\.\d{1,4}', text):
            return 'bracket'
        
        return 'other'
    
    def _extract_brand(self, text: str) -> str:
        """Извлекает бренд."""
        text_lower = text.lower()
        if 'laggartt' in text_lower or 'laggar' in text_lower:
            return 'laggartt'
        if 'meteor' in text_lower:
            return 'meteor'
        if 'devotion' in text_lower:
            return 'devotion'
        return ''
    
    def _extract_boiler_params(self, params: ProductParams, text: str, normalized: str, text_upper: str):
        """Извлекает параметры котла."""
        # Wi-Fi
        params.has_wifi = any(x in text.lower() for x in ['wi-fi', 'wifi', 'вайфай', 'вафай'])
        
        # Нормализуем текст для поиска модели (русские буквы -> латинские)
        text_normalized_for_model = self._normalize(text)
        text_normalized_upper = text_normalized_for_model.upper()
        
        # Модель - ищем в нормализованном тексте
        for pattern in self.MODEL_PATTERNS:
            # Применяем паттерн к нормализованному тексту
            match = re.search(pattern, text_normalized_upper)
            if match:
                model = match.group(1) if match.lastindex else match.group(0)
                if 'GAZ' in model or 'ГАЗ' in model:
                    params.model = 'GAZ6000'
                else:
                    params.model = model.upper()
                break
        
        # Если модель не найдена через паттерны, пробуем найти просто букву с цифрой
        if not params.model:
            model_match = re.search(r'\b([BCM][0-9]{2})\b', text_normalized_upper)
            if model_match:
                params.model = model_match.group(1)
        
        # Мощность и тип подключения (ищем в оригинальном тексте с учётом русских букв)
        power_conn_match = re.search(r'(\d{2})\s*([CHСН])', text_upper)
        if power_conn_match:
            params.power = int(power_conn_match.group(1))
            conn = power_conn_match.group(2)
            if conn in ['C', 'С']:
                params.conn_type = 'C'
            elif conn in ['H', 'Н']:
                params.conn_type = 'H'
        else:
            for pattern in self.POWER_PATTERNS:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    params.power = int(match.group(1))
                    break
            
            if not params.conn_type:
                if re.search(r'\bC\b', text_upper) or re.search(r'\bС\b', text_upper):
                    params.conn_type = 'C'
                elif re.search(r'\bH\b', text_upper) or re.search(r'\bН\b', text_upper):
                    params.conn_type = 'H'
        
        if not params.power:
            power_match = re.search(r'\b(\d{2})\b', normalized)
            if power_match:
                params.power = int(power_match.group(1))

    def _extract_chimney_params(self, params: ProductParams, text_upper: str):
        """Извлекает параметры дымохода."""
        # Проверка на конденсационный (PP или LN в названии)
        if 'PP' in text_upper or 'LN' in text_upper:
            params.is_condensing = True
        
        # Артикул WT...
        wt_match = re.search(r'(WT\d{5,6}-\d+[A-Z]*)', text_upper)
        if wt_match:
            params.article_code = wt_match.group(1)
            # Если в артикуле есть LN - это конденсационный
            if 'LN' in params.article_code:
                params.is_condensing = True
        
        # Размер DN
        size_match = re.search(r'DN(\d{2,3})/(\d{2,3})', text_upper)
        if size_match:
            params.size = f"DN{size_match.group(1)}/{size_match.group(2)}"
    
    def _extract_water_heater_params(self, params: ProductParams, text: str):
        """Извлекает параметры бойлера."""
        volume_match = re.search(r'IHT G (\d{3})', text, re.IGNORECASE)
        if volume_match:
            params.volume = int(volume_match.group(1))
    
    def _extract_conversion_kit_params(self, params: ProductParams, text: str):
        """Извлекает параметры комплекта перенастройки."""
        text_lower = text.lower()
        if 'сжиж' in text_lower or 'lpg' in text_lower:
            params.kit_type = 'сжиженный газ'
        
        # Если мощность явно указана
        if '36' in text:
            params.power = 36
        elif '10-32' in text or '10 32' in text:
            params.power = 32
        elif '10' in text and '32' in text:
            params.power = 32
        else:
            # Мощность не указана. По умолчанию для 95% случаев нужен комплект 10-32 кВт
            params.power = 32
            self._log(f"    Мощность не указана, используем по умолчанию 10-32 кВт")
    
    def _extract_radiator_params(self, params: ProductParams, text: str):
        """Извлекает параметры радиатора."""
        # Форматы: 22/400/700, 22-400-700, 22 400 700
        patterns = [
            r'(\d{2})[/-](\d{3,4})[/-](\d{3,4})',
            r'(\d{2})\s+(\d{3,4})\s+(\d{3,4})',
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                params.radiator_type = match.group(1)
                params.height = int(match.group(2))
                params.length = int(match.group(3))
                break
        
        # Подключение
        text_lower = text.lower()
        if 'vk' in text_lower or 'нижн' in text_lower:
            params.connection = 'VK'
        elif 'k-profil' in text_lower or 'k ' in text_lower or 'боков' in text_lower:
            params.connection = 'K'
    
    def _extract_bracket_params(self, params: ProductParams, text_upper: str):
        """Извлекает параметры кронштейна."""
        bracket_patterns = [
            r'\b([КK]\d{1,2}\.\d{1,4}[A-Z]?\d*)\b',
            r'\b([КK][НH][СC]\d{3,4})\b',
            r'\b(PLN\d+)\b',
        ]
        for pattern in bracket_patterns:
            match = re.search(pattern, text_upper)
            if match:
                params.bracket_article = match.group(1)
                break