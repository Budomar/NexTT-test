"""
product_normalizer.py - Извлечение параметров товара из текста
Универсальный парсер для любых форматов названий.
Версия 8.1 - исправлен вес Wi-Fi в поиске
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
    model_suffix: str = ""  # RN, A, M, T, Q, H, C и т.д. (модификация модели)
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
            return ('boiler', self.brand, self.model, self.model_suffix, self.power, self.conn_type, self.has_wifi)
        elif self.product_type == 'chimney':
            return ('chimney', self.size or self.article_code, self.is_condensing)
        elif self.product_type == 'conversion_kit':
            return ('conversion_kit', self.kit_type, self.power)
        elif self.product_type == 'radiator':
            return ('radiator', self.radiator_type, self.height, self.length, self.connection)
        elif self.product_type == 'bracket':
            return ('bracket', self.bracket_article)
        else:
            return (self.product_type, self.brand, self.model, self.model_suffix, self.power, self.has_wifi)
    
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
                return 0.1
        
        # ========== МОДЕЛЬ С УЧЕТОМ СУФФИКСОВ ==========
        if self.model and other.model:
            max_score += 0.25
            
            self_model_norm = self.model.upper().strip()
            other_model_norm = other.model.upper().strip()
            
            # Полное совпадение модели
            if self_model_norm == other_model_norm:
                score += 0.20
                
                # Совпадение суффикса - ВАЖНЫЙ БОНУС!
                if self.model_suffix and other.model_suffix:
                    if self.model_suffix.upper() == other.model_suffix.upper():
                        score += 0.15
                    else:
                        score += 0.02
                elif not self.model_suffix and not other.model_suffix:
                    score += 0.05
                elif self.model_suffix or other.model_suffix:
                    score += 0.02
            else:
                # Проверка на вхождение
                if self_model_norm in other_model_norm or other_model_norm in self_model_norm:
                    score += 0.15
                    
                    if len(self_model_norm) > len(other_model_norm):
                        longer = self_model_norm
                        shorter = other_model_norm
                    else:
                        longer = other_model_norm
                        shorter = self_model_norm
                    
                    potential_suffix = longer.replace(shorter, '')
                    if potential_suffix:
                        if (self.model_suffix and potential_suffix == self.model_suffix.upper()) or \
                           (other.model_suffix and potential_suffix == other.model_suffix.upper()):
                            score += 0.10
                else:
                    self_base = re.sub(r'[^A-Z0-9]', '', self_model_norm)
                    other_base = re.sub(r'[^A-Z0-9]', '', other_model_norm)
                    if self_base == other_base and len(self_base) >= 3:
                        score += 0.10
        
        # Мощность
        if self.power and other.power:
            max_score += 0.15
            if self.power == other.power:
                score += 0.15
        
        # Тип подключения (C/H)
        if self.conn_type and other.conn_type:
            max_score += 0.10
            if self.conn_type == other.conn_type:
                score += 0.10
        
        # Wi-Fi - увеличенный вес
        max_score += 0.10
        if self.has_wifi == other.has_wifi:
            score += 0.10
        
        # Бренд
        if self.brand and other.brand:
            max_score += 0.05
            if self.brand == other.brand:
                score += 0.05
        
        # Объём для бойлеров
        if self.volume and other.volume:
            max_score += 0.15
            if self.volume == other.volume:
                score += 0.15
        
        # Для дымоходов
        if self.product_type == 'chimney' and other.product_type == 'chimney':
            if self.article_code and other.article_code:
                max_score += 0.25
                self_art_norm = self.article_code.replace('NEW ', '').strip()
                other_art_norm = other.article_code.replace('NEW ', '').strip()
                if self_art_norm == other_art_norm:
                    score += 0.25
            
            if self.size and other.size:
                max_score += 0.20
                if self.size == other.size:
                    score += 0.20
            
            max_score += 0.30
            if self.is_condensing == other.is_condensing:
                score += 0.30
            else:
                score -= 0.20
        
        # Для комплектов
        if self.product_type == 'conversion_kit' and other.product_type == 'conversion_kit':
            if self.kit_type and other.kit_type:
                max_score += 0.20
                if self.kit_type == other.kit_type:
                    score += 0.20
        
        # Для радиаторов
        if self.product_type == 'radiator' and other.product_type == 'radiator':
            if self.radiator_type and other.radiator_type:
                max_score += 0.15
                if self.radiator_type == other.radiator_type:
                    score += 0.15
            
            if self.height and other.height:
                max_score += 0.10
                if self.height == other.height:
                    score += 0.10
            
            if self.length and other.length:
                max_score += 0.10
                if self.length == other.length:
                    score += 0.10
            
            if self.connection and other.connection:
                max_score += 0.10
                if self.connection == other.connection:
                    score += 0.10
        
        # Для кронштейнов
        if self.product_type == 'bracket' and other.product_type == 'bracket':
            if self.bracket_article and other.bracket_article:
                max_score += 0.30
                if self.bracket_article == other.bracket_article:
                    score += 0.30
        
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
        'Д': 'D', 'д': 'd', 'З': 'Z', 'з': 'z', 'Ф': 'F', 'ф': 'f',
        'И': 'I', 'и': 'i', 'Ы': 'Y', 'ы': 'y', 'Б': 'B', 'б': 'b',
        'Ю': 'U', 'ю': 'u', 'Я': 'Ja', 'я': 'ja', 'Ч': 'Ch', 'ч': 'ch',
        'Ш': 'Sh', 'ш': 'sh', 'Щ': 'Shh', 'щ': 'shh', 'Ъ': '', 'ъ': '',
        'Э': 'E', 'э': 'e',
    }
    
    # Паттерны для извлечения мощности
    POWER_PATTERNS = [
        r'(\d{2})\s*квт',
        r'(\d{2})\s*kw',
        r'мощность\s*(\d{2})',
        r'\b(10|12|14|18|20|24|26|28|30|32|35|36|45|60|80)\b',
    ]
    
    # Паттерны для моделей котлов (общие, без жёсткой привязки к конкретным)
    MODEL_PATTERNS = [
        # Буква + 2 цифры, возможно с суффиксом (B30, B30RN, C11, M30A, T2, Q3)
        r'\b([A-Z][0-9]{1,2})([A-Z]{1,3})?\b',
        # Модели с дефисом (B-30, C-11)
        r'\b([A-Z])[-]?([0-9]{1,2})([A-Z]{1,3})?\b',
        # ГАЗ 6000 и аналоги (цифры в названии)
        r'\b([A-Z]{2,4})\s*([0-9]{3,4})([A-Z]{1,3})?\b',
        # T2, Q3 (буква + одна цифра)
        r'\b([TQ])([0-9]{1})([A-Z]{1,3})?\b',
    ]
    
    # Допустимые суффиксы для котлов (в порядке приоритета)
    VALID_SUFFIXES = {'RN', 'A', 'M', 'T', 'Q', 'H', 'C', 'RNW', 'RNM', 'RNH', 'RNC', 'LA', 'RA', 'RE', 'LE'}
    
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
        """Нормализует текст: русские буквы -> латинские, НЕ меняет регистр."""
        if not text:
            return ""
        result = []
        for ch in text:
            result.append(self.LETTER_MAPPING.get(ch, ch))
        return ''.join(result)
    
    def _normalize_lower(self, text: str) -> str:
        """Нормализует текст и приводит к нижнему регистру."""
        return self._normalize(text).lower()
    
    def _extract_suffix_from_text(self, text: str, model_base: str, start_pos: int) -> str:
        """
        Универсальное извлечение суффикса из текста после модели.
        """
        if not text or not model_base or start_pos >= len(text):
            return ""
        
        remaining = text[start_pos:]
        
        # Паттерны для поиска суффикса (в порядке приоритета)
        patterns = [
            # RN сразу после цифр: GAZ6000RN
            r'^([A-Z]{1,3})(?=\s|$|[^A-Z])',
            # Пробел и буквы: GAZ 6000 RN
            r'^\s+([A-Z]{1,3})(?:\s|$)',
            # Дефис и буквы: GAZ6000-RN
            r'^-([A-Z]{1,3})(?:\s|$)',
            # Пробел или дефис, затем буквы
            r'^[\s-]*([A-Z]{1,3})(?:\s|$)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, remaining, re.IGNORECASE)
            if match:
                suffix = match.group(1).upper()
                # Проверяем, что это допустимый суффикс
                if suffix in self.VALID_SUFFIXES or len(suffix) <= 3 and suffix.isalpha():
                    self._log(f"    Найден суффикс: '{suffix}' после модели {model_base}")
                    return suffix
        
        return ""
    
    def extract(self, text: str) -> ProductParams:
        """
        Главный метод: извлекает параметры из любого текста.
        """
        params = ProductParams(original_text=text)
        if not text:
            return params
        
        # Нормализуем текст
        text_normalized = self._normalize(text)
        text_normalized_lower = text_normalized.lower()
        text_upper = text.upper()
        
        # 1. Определяем тип товара
        params.product_type = self._extract_product_type(text)
        
        # 2. Извлекаем бренд
        params.brand = self._extract_brand(text)
        
        # 3. Ищем артикул в любом тексте (для запчастей и датчиков)
        article_match = re.search(r'\b([A-Z]{2}\d{8})\b', text_upper)
        if article_match:
            params.article = article_match.group(1)
            params.product_type = 'part'  # или 'sensor' если есть слово датчик
            self._log(f"    Найден артикул: {params.article}")
        
        # 4. Для котлов
        if params.product_type == 'boiler':
            self._extract_boiler_params(params, text, text_upper, text_normalized, text_normalized_lower)
        
        # 5. Для дымоходов
        elif params.product_type == 'chimney':
            self._extract_chimney_params(params, text_upper)
        
        # 6. Для бойлеров
        elif params.product_type == 'water_heater':
            self._extract_water_heater_params(params, text)
        
        # 7. Для комплектов
        elif params.product_type == 'conversion_kit':
            self._extract_conversion_kit_params(params, text)
        
        # 8. Для радиаторов
        elif params.product_type == 'radiator':
            self._extract_radiator_params(params, text)
        
        # 9. Для кронштейнов
        elif params.product_type == 'bracket':
            self._extract_bracket_params(params, text_upper)
        
        # 10. Для датчиков и запчастей - уже есть артикул
        elif params.product_type in ['sensor', 'part']:
            # Если артикул не найден, пробуем извлечь
            if not params.article:
                article_match = re.search(r'\b([A-Z]{2}\d{8})\b', text_upper)
                if article_match:
                    params.article = article_match.group(1)
                    self._log(f"    Найден артикул для запчасти: {params.article}")
        
        return params
    
    def _extract_product_type(self, text: str) -> str:
        """Определяет тип товара по ключевым словам или паттернам."""
        text_lower = text.lower()
        
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
        
        if re.search(r'[BCMВСTQ][0-9]{1,2}', text, re.IGNORECASE):
            return 'boiler'
        if re.search(r'(ГАЗ|GAZ)\s*6000', text, re.IGNORECASE):
            return 'boiler'
        if re.search(r'DN\d{2,3}/\d{2,3}', text, re.IGNORECASE):
            return 'chimney'
        if re.search(r'WT\d{5,6}-\d+', text, re.IGNORECASE):
            return 'chimney'
        if re.search(r'\d{2}[/-]\d{3,4}[/-]\d{3,4}', text):
            return 'radiator'
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
    
    def _extract_boiler_params(self, params: ProductParams, text: str, text_upper: str, 
                                text_normalized: str, text_normalized_lower: str):
        """
        Извлекает параметры котла с поддержкой суффиксов (RN и т.д.).
        """
        params.has_wifi = any(x in text.lower() for x in ['wi-fi', 'wifi', 'вайфай', 'вафай'])
        
        # ========== ИЩЕМ МОДЕЛЬ И СУФФИКС ==========
        model_base = ""
        suffix = ""
        model_end_pos = 0
        
        # Специальная обработка для ГАЗ 6000
        gaz_match = re.search(r'(ГАЗ|GAZ)\s*6000', text_normalized, re.IGNORECASE)
        if gaz_match:
            model_base = 'GAZ6000'
            model_end_pos = gaz_match.end()
            after_model = text_normalized[model_end_pos:]
            
            # Ищем тип подключения и суффикс в строке пользователя
            # Паттерны: "24 C RN", "24C RN", "24RN", "24 H RN"
            patterns = [
                r'(\d*)\s*([CH])\s+([A-Z]{1,3})\b',   # 24 C RN
                r'(\d*)([CH])\s+([A-Z]{1,3})\b',      # 24C RN
                r'(\d*)([A-Z]{1,3})\b',               # 24RN
            ]
            
            for pattern in patterns:
                match = re.search(pattern, after_model, re.IGNORECASE)
                if match:
                    groups = match.groups()
                    if len(groups) >= 2:
                        # Определяем тип подключения
                        if groups[1] in ['C', 'H']:
                            params.conn_type = groups[1]
                            if len(groups) >= 3 and groups[2]:
                                suffix = groups[2].upper()
                        else:
                            # Возможно суффикс без явного типа
                            potential_suffix = groups[1].upper()
                            if potential_suffix in ['RN', 'RNW', 'RNM', 'RNC', 'RNH']:
                                suffix = potential_suffix
                    break
            
            if suffix:
                self._log(f"    Найден суффикс для GAZ6000 в запросе: {suffix}")
        
        # Общий поиск моделей (для M30, B30, C30 и т.д.)
        if not model_base:
            for pattern in self.MODEL_PATTERNS:
                match = re.search(pattern, text_normalized, re.IGNORECASE)
                if match:
                    groups = match.groups()
                    if len(groups) >= 2:
                        letters = groups[0] if groups[0] else ''
                        numbers = groups[1] if len(groups) > 1 and groups[1] else ''
                        suffix_part = groups[2] if len(groups) > 2 and groups[2] else ''
                        
                        if letters and numbers:
                            model_base = f"{letters}{numbers}"
                            model_end_pos = match.end()
                            if suffix_part:
                                suffix = suffix_part.upper()
                            else:
                                suffix = self._extract_suffix_from_text(text_normalized, model_base, model_end_pos)
                            break
        
        # Поиск T2, Q3
        if not model_base:
            model_match = re.search(r'\b([TQ])([0-9]{1})\b', text_normalized, re.IGNORECASE)
            if model_match:
                model_base = f"{model_match.group(1).upper()}{model_match.group(2)}"
                model_end_pos = model_match.end()
                suffix = self._extract_suffix_from_text(text_normalized, model_base, model_end_pos)
        
        # Поиск любых буква+цифры
        if not model_base:
            model_match = re.search(r'\b([A-Z]+[0-9]+)\b', text_normalized)
            if model_match:
                model_base = model_match.group(1).upper()
                model_end_pos = model_match.end()
                suffix = self._extract_suffix_from_text(text_normalized, model_base, model_end_pos)
        
        # Устанавливаем модель и суффикс
        if model_base:
            params.model = model_base
            if suffix:
                params.model_suffix = suffix
        
        # ========== МОЩНОСТЬ ==========
        power_match = re.search(r'(\d{2})\s*([CHСН])', text_upper)
        if power_match:
            params.power = int(power_match.group(1))
            conn = power_match.group(2)
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
        
        self._log(f"    ИТОГО: модель={params.model}, суффикс={params.model_suffix}, мощность={params.power}, тип={params.conn_type}, wifi={params.has_wifi}")
    
    def _extract_chimney_params(self, params: ProductParams, text_upper: str):
        """Извлекает параметры дымохода."""
        self._log(f"    [ОТЛАДКА] Начало обработки дымохода. Текст: '{text_upper[:100]}'")
        
        # Конденсационный тип
        condensing_keywords = ['РР', 'PP', 'LN', 'ПП', 'полипропилен', 'конденсационный']
        for kw in condensing_keywords:
            if kw.upper() in text_upper:
                params.is_condensing = True
                self._log(f"    [ОТЛАДКА] Найден конденсационный признак: {kw}")
                break
        
        # Артикул WT...
        wt_match = re.search(r'(WT\d{5,6}-\d+[A-Z]*)', text_upper)
        if wt_match:
            params.article_code = wt_match.group(1)
            self._log(f"    [ОТЛАДКА] Найден артикул WT: {params.article_code}")
            if 'LN' in params.article_code.upper():
                params.is_condensing = True
                self._log(f"    [ОТЛАДКА] Артикул содержит LN -> конденсационный")
            
            # ========== ОПРЕДЕЛЯЕМ РАЗМЕР ПО АРТИКУЛУ ==========
            if '60100' in params.article_code:
                params.size = 'DN60/100'
                self._log(f"    [ОТЛАДКА] Определён размер по артикулу {params.article_code}: DN60/100")
            elif '80125' in params.article_code:
                params.size = 'DN80/125'
                self._log(f"    [ОТЛАДКА] Определён размер по артикулу {params.article_code}: DN80/125")
            else:
                self._log(f"    [ОТЛАДКА] Не удалось определить размер по артикулу {params.article_code}")
        
        # Размер DN (если ещё не определён)
        if not params.size:
            size_match = re.search(r'DN(\d{2,3})/(\d{2,3})', text_upper)
            if size_match:
                params.size = f"DN{size_match.group(1)}/{size_match.group(2)}"
                self._log(f"    [ОТЛАДКА] Найден размер DN: {params.size}")
        
        # Альтернативные форматы (60/100, 60 на 100, 60х100)
        if not params.size:
            size_match = re.search(r'(\d{2,3})/(\d{2,3})', text_upper)
            if size_match:
                params.size = f"DN{size_match.group(1)}/{size_match.group(2)}"
                self._log(f"    [ОТЛАДКА] Найден размер в формате X/X: {params.size}")
        
        if not params.size:
            size_match = re.search(r'(\d{2,3})\s+на\s+(\d{2,3})', text_upper, re.IGNORECASE)
            if size_match:
                params.size = f"DN{size_match.group(1)}/{size_match.group(2)}"
                self._log(f"    [ОТЛАДКА] Найден размер в формате X на X: {params.size}")
        
        if not params.size:
            size_match = re.search(r'(\d{2,3})[хxX](\d{2,3})', text_upper)
            if size_match:
                params.size = f"DN{size_match.group(1)}/{size_match.group(2)}"
                self._log(f"    [ОТЛАДКА] Найден размер в формате XxX: {params.size}")
        
        if not params.size:
            self._log(f"    [ОТЛАДКА] НЕ УДАЛОСЬ ОПРЕДЕЛИТЬ РАЗМЕР!")
        
        self._log(f"    [ОТЛАДКА] ИТОГО: size={params.size}, article={params.article_code}, condensing={params.is_condensing}")

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
        
        if '36' in text:
            params.power = 36
        elif '10-32' in text or '10 32' in text:
            params.power = 32
        else:
            params.power = 32
    
    def _extract_radiator_params(self, params: ProductParams, text: str):
        """Извлекает параметры радиатора."""
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
        
        text_lower = text.lower()
        if 'vk' in text_lower or 'нижн' in text_lower:
            params.connection = 'VK'
        elif 'k-profil' in text_lower or 'боков' in text_lower:
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