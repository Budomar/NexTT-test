"""
product_normalizer.py - Извлечение параметров товара из текста
Универсальный парсер для любых форматов названий.
Версия 8.3 - улучшено распознавание котлов без явных ключевых слов
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
    product_type: str = ""  # котел, бойлер, дымоход, комплект, датчик, радиатор, кронштейн, radiator_accessory
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
    is_condensing: bool = False

    # Для бойлеров
    volume: Optional[int] = None

    # Для комплектов
    kit_type: str = ""

    # Для радиаторов
    radiator_type: str = ""
    height: Optional[int] = None
    length: Optional[int] = None
    connection: str = ""

    # Для кронштейнов
    bracket_article: str = ""

    # Для комплектующих к радиаторам
    accessory_type: str = ""
    accessory_subtype: str = ""
    accessory_brand: str = ""
    types_list: List[str] = field(default_factory=list)

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
        elif self.product_type == 'radiator_accessory':
            return ('radiator_accessory', self.accessory_type, 
                    tuple(sorted(self.types_list)) if self.types_list else (),
                    self.height, self.length, self.accessory_brand, self.accessory_subtype)
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
                
                # Совпадение суффикса
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
        
        # Wi-Fi
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
        
        # Для комплектующих к радиаторам
        if self.product_type == 'radiator_accessory' and other.product_type == 'radiator_accessory':
            if self.accessory_type and other.accessory_type:
                max_score += 0.25
                if self.accessory_type == other.accessory_type:
                    score += 0.25
            
            if self.types_list and other.types_list:
                max_score += 0.20
                if set(self.types_list) == set(other.types_list):
                    score += 0.20
                elif set(self.types_list) & set(other.types_list):
                    intersection = len(set(self.types_list) & set(other.types_list))
                    union = len(set(self.types_list) | set(other.types_list))
                    score += 0.20 * (intersection / union) if union > 0 else 0
            
            if self.length and other.length:
                max_score += 0.20
                if self.length == other.length:
                    score += 0.20
            
            if self.height and other.height:
                max_score += 0.20
                if self.height == other.height:
                    score += 0.20
            
            if self.accessory_brand and other.accessory_brand:
                max_score += 0.15
                if self.accessory_brand == other.accessory_brand:
                    score += 0.15
            
            if self.accessory_subtype and other.accessory_subtype:
                max_score += 0.15
                if self.accessory_subtype == other.accessory_subtype:
                    score += 0.15
        
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

    # Паттерны для моделей котлов - универсальные, с учётом пробелов и дефисов
    MODEL_PATTERNS = [
        # Буква + пробел + 1-2 цифры (B 30, C 11) - для пользовательских запросов
        r'\b([A-Z])\s+([0-9]{1,2})([A-Z]{1,3})?\b',
        # Буква + 1-2 цифры (B30, C11) - для базы данных
        r'\b([A-Z][0-9]{1,2})([A-Z]{1,3})?\b',
        # Модели с дефисом (B-30, C-11)
        r'\b([A-Z])[-]?([0-9]{1,2})([A-Z]{1,3})?\b',
        # T2, Q3 (буква + одна цифра)
        r'\b([TQ])([0-9]{1})([A-Z]{1,3})?\b',
        # M30, B20 и т.д. (буква + 2 цифры)
        r'\b([A-Z]{1,2})([0-9]{2})([A-Z]{1,3})?\b',
    ]

    # Допустимые суффиксы для котлов
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
        
        patterns = [
            r'^([A-Z]{1,3})(?=\s|$|[^A-Z])',
            r'^\s+([A-Z]{1,3})(?:\s|$)',
            r'^-([A-Z]{1,3})(?:\s|$)',
            r'^[\s-]*([A-Z]{1,3})(?:\s|$)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, remaining, re.IGNORECASE)
            if match:
                suffix = match.group(1).upper()
                if suffix in self.VALID_SUFFIXES or len(suffix) <= 3 and suffix.isalpha():
                    return suffix
        
        return ""

    def _extract_power_from_text(self, text: str) -> Optional[int]:
        """Извлекает мощность из текста любым способом."""
        # Ищем в формате "24 C" или "24H"
        match = re.search(r'\b(\d{2})\s*[CH]\b', text, re.IGNORECASE)
        if match:
            return int(match.group(1))
        
        # Ищем "24 кВт"
        match = re.search(r'(\d{2})\s*квт', text, re.IGNORECASE)
        if match:
            return int(match.group(1))
        
        # Ищем любое число из списка мощностей
        for pattern in self.POWER_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return int(match.group(1))
        
        return None

    def _extract_conn_type_from_text(self, text: str) -> str:
        """Извлекает тип подключения C/H."""
        text_upper = text.upper()
        if re.search(r'\bC\b', text_upper) or re.search(r'\bС\b', text_upper):
            return 'C'
        if re.search(r'\bH\b', text_upper) or re.search(r'\bН\b', text_upper):
            return 'H'
        return ''

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
        
        # 3. Ищем артикул
        article_match = re.search(r'\b([A-Z]{2}\d{8})\b', text_upper)
        if article_match:
            params.article = article_match.group(1)
        
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
        
        # 10. Для комплектующих к радиаторам
        elif params.product_type == 'radiator_accessory':
            self._extract_radiator_accessory_params(params, text)
        
        # 11. Для датчиков и запчастей
        elif params.product_type in ['sensor', 'part']:
            if not params.article:
                article_match = re.search(r'\b([A-Z]{2}\d{8})\b', text_upper)
                if article_match:
                    params.article = article_match.group(1)
        
        return params

    def _extract_product_type(self, text: str) -> str:
        """
        Определяет тип товара по ключевым словам или паттернам.
        Универсальный — распознаёт даже без явных ключевых слов.
        """
        text_lower = text.lower()
        text_normalized = self._normalize(text)
        
        # ========== КОМПЛЕКТУЮЩИЕ К РАДИАТОРАМ ==========
        if any(x in text_lower for x in ['решетка', 'решётка', 'защитная решетка']):
            return 'radiator_accessory'
        if any(x in text_lower for x in ['боковая панель', 'панель боковая']):
            return 'radiator_accessory'
        if 'клипса' in text_lower:
            return 'radiator_accessory'
        if 'заглушка' in text_lower:
            return 'radiator_accessory'
        if any(x in text_lower for x in ['воздушный кран', 'кран воздушный']):
            return 'radiator_accessory'
        if 'колпачок' in text_lower:
            return 'radiator_accessory'
        if 'регулятор' in text_lower and 'af' in text_lower:
            return 'radiator_accessory'
        if 'адаптер' in text_lower and 'решётк' in text_lower:
            return 'radiator_accessory'
        
        # ========== ФЛАНЕЦ = ДЫМОХОД ==========
        if 'фланец' in text_lower:
            return 'chimney'
        
        # ========== КОТЛЫ ==========
        # Явные ключевые слова
        if any(x in text_lower for x in ['котел', 'котёл']):
            return 'boiler'
        
        # 6000 = ГАЗ 6000 = котёл (даже без слова "ГАЗ")
        if re.search(r'\b6000\b', text_lower):
            return 'boiler'
        
        # GAZ 6000 (с разными вариантами написания)
        if re.search(r'(газ|gaz)\s*6000', text_lower):
            return 'boiler'
        
        # ========== МОДЕЛИ КОТЛОВ (С ПРОБЕЛОМ И БЕЗ) ==========
        # ИСПРАВЛЕНИЕ: ищем И русскую С, И латинскую C
        # Паттерн: буква (B, C, M, T, Q) + пробел + 1-2 цифры
        # [BСMВTQ] - здесь С - русская
        # [BCMTQ] - здесь C - латинская
        # Используем [BСCMВTQ] - ищем обе буквы
        
        # Проверяем паттерн: буква + пробел + цифры (C 11, B 30)
        if re.search(r'\b[BСCMВTQ]\s*[0-9]{1,2}\b', text_normalized, re.IGNORECASE):
            # Если есть признаки радиатора (высота/длина) — это радиатор
            if re.search(r'\d{3,4}[/-]\d{3,4}', text) or 'profil' in text_lower:
                return 'radiator'
            return 'boiler'
        
        # Проверяем паттерн: буква + цифры без пробела (C11, B30)
        if re.search(r'\b[BСCMВTQ][0-9]{1,2}\b', text_normalized, re.IGNORECASE):
            if re.search(r'\d{3,4}[/-]\d{3,4}', text) or 'profil' in text_lower:
                return 'radiator'
            return 'boiler'
        
        # GAZ6000 слитно
        if re.search(r'gaz6000', text_normalized, re.IGNORECASE):
            return 'boiler'
        
        # ========== БОЙЛЕРЫ ==========
        if any(x in text_lower for x in ['бойлер', 'водонагреватель']):
            return 'water_heater'
        if re.search(r'iht\s*g\s*\d{3}', text_lower):
            return 'water_heater'
        
        # ========== ДЫМОХОДЫ ==========
        if any(x in text_lower for x in ['дымоход', 'chimney']):
            return 'chimney'
        if re.search(r'dn\d{2,3}/\d{2,3}', text_lower):
            return 'chimney'
        if re.search(r'wt\d{5,6}-\d+', text_lower):
            return 'chimney'
        
        # ========== КОМПЛЕКТЫ ==========
        if any(x in text_lower for x in ['комплект', 'перенастройка', 'форсунка', 'lpg', 'сжиж']):
            return 'conversion_kit'
        if re.search(r'301\d{8}', text):
            return 'conversion_kit'
        
        # ========== РАДИАТОРЫ ==========
        if any(x in text_lower for x in ['радиатор', 'profil', 'kermi', 'purmo', 'buderus', 'evra', 'oasis']):
            return 'radiator'
        if re.search(r'\d{2}[/-]\d{3,4}[/-]\d{3,4}', text):
            return 'radiator'
        if re.search(r'\d{2}\s*[-]\s*\d{3,4}\s*[-]\s*\d{3,4}', text):
            return 'radiator'
        
        # ========== КРОНШТЕЙНЫ ==========
        if any(x in text_lower for x in ['кронштейн', 'bracket']):
            return 'bracket'
        if re.search(r'[КK]\d{1,2}\.\d{1,4}', text):
            return 'bracket'
        if re.search(r'[КK][НH][СC]\d{3,4}', text):
            return 'bracket'
        if re.search(r'pln\d+', text_lower):
            return 'bracket'
        
        # ========== ДАТЧИКИ ==========
        if any(x in text_lower for x in ['датчик', 'температуры', 'ntc']):
            return 'sensor'
        
        # ========== ЗАПЧАСТИ ==========
        if any(x in text_lower for x in ['вентилятор', 'плата', 'клапан', 'теплообменник', 'насос', 'горелка']):
            return 'part'
        if re.search(r'[A-Z]{2}\d{8}', text):
            return 'part'
        
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
        Извлекает параметры котла с поддержкой любых форматов.
        Универсальный — работает с B30, B 30, GAZ6000, 6000 и т.д.
        """
        params.has_wifi = any(x in text.lower() for x in ['wi-fi', 'wifi', 'вайфай', 'вафай'])
        
        model_base = ""
        suffix = ""
        model_end_pos = 0
        
        # ========== 1. 6000 (без "ГАЗ") ==========
        if re.search(r'\b6000\b', text_normalized, re.IGNORECASE) and \
           not re.search(r'(ГАЗ|GAZ)\s*6000', text_normalized, re.IGNORECASE):
            model_base = 'GAZ6000'
            match_6000 = re.search(r'\b6000\b', text_normalized, re.IGNORECASE)
            if match_6000:
                model_end_pos = match_6000.end()
                after_model = text_normalized[model_end_pos:]
                
                power_patterns = [
                    r'(\d+)\s*([CH])\s+([A-Z]{1,3})\b',
                    r'(\d+)\s*([CH])\b',
                    r'(\d+)\s*([A-Z]{1,3})\b',
                ]
                
                for pattern in power_patterns:
                    match = re.search(pattern, after_model, re.IGNORECASE)
                    if match:
                        groups = match.groups()
                        if len(groups) >= 2:
                            try:
                                params.power = int(groups[0])
                            except ValueError:
                                pass
                            
                            if groups[1] in ['C', 'H']:
                                params.conn_type = groups[1]
                                if len(groups) >= 3 and groups[2]:
                                    suffix = groups[2].upper()
                            else:
                                potential_suffix = groups[1].upper()
                                if potential_suffix in self.VALID_SUFFIXES:
                                    suffix = potential_suffix
                        break
                
                if suffix:
                    params.model_suffix = suffix
                    self._log(f"    Найден суффикс для 6000: {suffix}")
        
        # ========== 2. ГАЗ 6000 ==========
        if not model_base:
            gaz_match = re.search(r'(ГАЗ|GAZ)\s*6000', text_normalized, re.IGNORECASE)
            if gaz_match:
                model_base = 'GAZ6000'
                model_end_pos = gaz_match.end()
                after_model = text_normalized[model_end_pos:]
                
                patterns = [
                    r'(\d*)\s*([CH])\s+([A-Z]{1,3})\b',
                    r'(\d*)([CH])\s+([A-Z]{1,3})\b',
                    r'(\d*)([A-Z]{1,3})\b',
                ]
                
                for pattern in patterns:
                    match = re.search(pattern, after_model, re.IGNORECASE)
                    if match:
                        groups = match.groups()
                        if len(groups) >= 2:
                            if groups[1] in ['C', 'H']:
                                params.conn_type = groups[1]
                                if len(groups) >= 3 and groups[2]:
                                    suffix = groups[2].upper()
                            else:
                                potential_suffix = groups[1].upper()
                                if potential_suffix in self.VALID_SUFFIXES:
                                    suffix = potential_suffix
                        break
                
                if suffix:
                    params.model_suffix = suffix
                    self._log(f"    Найден суффикс для ГАЗ 6000: {suffix}")
        
        # ========== 3. Общий поиск моделей (ИСПРАВЛЕН) ==========
        if not model_base:
            # Ищем букву + пробел + цифры (C 11, B 30)
            # Используем [BСCMВTQ] - и русскую и латинскую C
            match = re.search(r'\b([BСCMВTQ])\s+([0-9]{1,2})([A-Z]{1,3})?\b', text_normalized, re.IGNORECASE)
            if match:
                letters = match.group(1).upper()
                numbers = match.group(2)
                suffix_part = match.group(3) if match.group(3) else ''
                # Если буква - русская С, заменяем на латинскую C для единообразия
                if letters == 'С':
                    letters = 'C'
                model_base = f"{letters}{numbers}"
                model_end_pos = match.end()
                if suffix_part:
                    suffix = suffix_part.upper()
                else:
                    suffix = self._extract_suffix_from_text(text_normalized, model_base, model_end_pos)
                self._log(f"    Найдена модель (с пробелом): {model_base}, суффикс={suffix}")
            
            # Если не нашли с пробелом, ищем без пробела (C11, B30)
            if not model_base:
                match = re.search(r'\b([BСCMВTQ])([0-9]{1,2})([A-Z]{1,3})?\b', text_normalized, re.IGNORECASE)
                if match:
                    letters = match.group(1).upper()
                    numbers = match.group(2)
                    suffix_part = match.group(3) if match.group(3) else ''
                    if letters == 'С':
                        letters = 'C'
                    model_base = f"{letters}{numbers}"
                    model_end_pos = match.end()
                    if suffix_part:
                        suffix = suffix_part.upper()
                    else:
                        suffix = self._extract_suffix_from_text(text_normalized, model_base, model_end_pos)
                    self._log(f"    Найдена модель (без пробела): {model_base}, суффикс={suffix}")
        
        # Если нашли модель, но не нашли суффикс — пробуем извлечь из остатка
        if model_base and not suffix and model_end_pos > 0:
            suffix = self._extract_suffix_from_text(text_normalized, model_base, model_end_pos)
        
        # Устанавливаем модель и суффикс
        if model_base:
            params.model = model_base
            if suffix:
                params.model_suffix = suffix
        
        # ========== 4. Мощность (если ещё не найдена) ==========
        if not params.power:
            power_match = re.search(r'\b(\d{2})\s*[CH]\b', text, re.IGNORECASE)
            if power_match:
                params.power = int(power_match.group(1))
            else:
                for pattern in self.POWER_PATTERNS:
                    match = re.search(pattern, text, re.IGNORECASE)
                    if match:
                        params.power = int(match.group(1))
                        break
        
        # ========== 5. Тип подключения (если ещё не найден) ==========
        if not params.conn_type:
            if re.search(r'\bC\b', text_upper) or re.search(r'\bС\b', text_upper):
                params.conn_type = 'C'
            elif re.search(r'\bH\b', text_upper) or re.search(r'\bН\b', text_upper):
                params.conn_type = 'H'
        
        self._log(f"    ИТОГО: модель={params.model}, суффикс={params.model_suffix}, "
                  f"мощность={params.power}, тип={params.conn_type}, wifi={params.has_wifi}")
                  
    def _extract_chimney_params(self, params: ProductParams, text_upper: str):
        """Извлекает параметры дымохода."""
        if 'ФЛАНЕЦ' in text_upper:
            return
        
        # Конденсационный тип
        condensing_keywords = ['РР', 'PP', 'LN', 'ПП', 'полипропилен', 'конденсационный']
        for kw in condensing_keywords:
            if kw.upper() in text_upper:
                params.is_condensing = True
                break
        
        # Артикул WT...
        wt_match = re.search(r'(WT\d{5,6}-\d+[A-Z]*)', text_upper)
        if wt_match:
            params.article_code = wt_match.group(1)
            if 'LN' in params.article_code.upper():
                params.is_condensing = True
            
            if '60100' in params.article_code:
                params.size = 'DN60/100'
            elif '80125' in params.article_code:
                params.size = 'DN80/125'
        
        # Размер DN
        if not params.size:
            size_match = re.search(r'DN(\d{2,3})/(\d{2,3})', text_upper)
            if size_match:
                params.size = f"DN{size_match.group(1)}/{size_match.group(2)}"
        
        if not params.size:
            size_match = re.search(r'(\d{2,3})/(\d{2,3})', text_upper)
            if size_match:
                params.size = f"DN{size_match.group(1)}/{size_match.group(2)}"
        
        if not params.size:
            size_match = re.search(r'(\d{2,3})\s+на\s+(\d{2,3})', text_upper, re.IGNORECASE)
            if size_match:
                params.size = f"DN{size_match.group(1)}/{size_match.group(2)}"
        
        if not params.size:
            size_match = re.search(r'(\d{2,3})[хxX](\d{2,3})', text_upper)
            if size_match:
                params.size = f"DN{size_match.group(1)}/{size_match.group(2)}"

    def _extract_water_heater_params(self, params: ProductParams, text: str):
        """Извлекает параметры бойлера."""
        volume_match = re.search(r'IHT G (\d{3})', text, re.IGNORECASE)
        if volume_match:
            params.volume = int(volume_match.group(1))
            return
        
        volume_match = re.search(r'[Бб]ойлер\s+(\d{3})', text)
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
            r'(\d{2})\s*[-]\s*(\d{3,4})\s*[-]\s*(\d{3,4})',
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

    def _extract_radiator_accessory_params(self, params: ProductParams, text: str):
        """Извлекает параметры комплектующих к радиаторам."""
        text_lower = text.lower()
        
        if any(x in text_lower for x in ['решетка', 'решётка']):
            params.accessory_type = 'решетка'
        elif any(x in text_lower for x in ['боковая панель', 'панель боковая']):
            params.accessory_type = 'панель'
        elif 'клипса' in text_lower:
            params.accessory_type = 'клипса'
        elif 'заглушка' in text_lower:
            params.accessory_type = 'заглушка'
        elif any(x in text_lower for x in ['воздушный кран', 'кран воздушный']):
            params.accessory_type = 'кран'
        elif 'колпачок' in text_lower:
            params.accessory_type = 'колпачок'
        elif 'регулятор' in text_lower:
            params.accessory_type = 'регулятор'
        elif 'адаптер' in text_lower:
            params.accessory_type = 'адаптер'
        else:
            params.accessory_type = 'другое'
        
        if params.accessory_type in ['решетка', 'панель']:
            types_match = re.search(r'тип\s+([\d\s,]+)', text_lower)
            if types_match:
                types_str = types_match.group(1)
                types = re.findall(r'\d+', types_str)
                params.types_list = types
        
        if params.accessory_type == 'решетка':
            length_match = re.search(r'длина\s+(\d+)', text_lower)
            if length_match:
                params.length = int(length_match.group(1))
        
        if params.accessory_type == 'панель':
            height_match = re.search(r'высота\s+(\d+)', text_lower)
            if height_match:
                params.height = int(height_match.group(1))
        
        if params.accessory_type == 'клипса':
            if 'laggartt' in text_lower or 'laggar' in text_lower or 'бренд' in text_lower:
                params.accessory_brand = 'laggartt'
            elif 'meteor' in text_lower:
                params.accessory_brand = 'meteor'
            
            if 'коротк' in text_lower:
                params.accessory_subtype = 'короткая'
            elif 'длинн' in text_lower:
                params.accessory_subtype = 'длинная'