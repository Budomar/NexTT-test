"""
product_normalizer.py - Извлечение параметров товара из текста
Универсальный парсер для любых форматов названий.
Версия 9.0 - делегирует распознавание котлов в boiler_parser
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
    product_type: str = ""
    brand: str = ""
    # Для котлов
    model: str = ""
    model_suffix: str = ""
    power: Optional[int] = None
    conn_type: str = ""
    has_wifi: bool = False
    has_ot: bool = False

    # Для дымоходов
    size: str = ""
    article_code: str = ""
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
        """Возвращает ключ для индексации."""
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
        Возвращает уверенность 0..1.
        Нормализовано: сумма совпавших весов / сумма заданных весов.
        """
        score = 0.0
        max_score = 0.0

        # Тип товара
        if self.product_type and other.product_type:
            max_score += 0.2
            if self.product_type == other.product_type:
                score += 0.2
            else:
                return 0.1

        # Модель
        if self.model and other.model:
            max_score += 0.25
            self_model_norm = self.model.upper().strip()
            other_model_norm = other.model.upper().strip()

            if self_model_norm == other_model_norm:
                score += 0.20
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

        # Тип подключения
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
            # Артикул — если задан в запросе, у базы тоже должен быть
            if self.article_code:
                max_score += 0.25
                if other.article_code:
                    self_art_norm = self.article_code.replace('NEW ', '').strip()
                    other_art_norm = other.article_code.replace('NEW ', '').strip()
                    if self_art_norm == other_art_norm:
                        score += 0.25

            # Размер — если задан в запросе, у базы тоже должен быть
            if self.size:
                max_score += 0.30
                if other.size:
                    if self.size == other.size:
                        score += 0.30

            # Конденсация — обязательное совпадение
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

        final = min(score, max_score) / max_score
        return max(0.0, min(1.0, final))


class ProductNormalizer:
    """Универсальный извлекатель параметров товара."""

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

    POWER_PATTERNS = [
        r'(\d{2})\s*квт',
        r'(\d{2})\s*kw',
        r'мощность\s*(\d{2})',
        r'\b(10|12|14|18|20|24|26|28|30|32|35|36|45|60|80)\b',
    ]

    MODEL_PATTERNS = [
        r'\b([A-Z])\s+([0-9]{1,2})([A-Z]{1,3})?\b',
        r'\b([A-Z][0-9]{1,2})([A-Z]{1,3})?\b',
        r'\b([A-Z])[-]?([0-9]{1,2})([A-Z]{1,3})?\b',
        r'\b([TQ])([0-9]{1})([A-Z]{1,3})?\b',
        r'\b([A-Z]{1,2})([0-9]{2})([A-Z]{1,3})?\b',
    ]

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
        if not text:
            return ""
        result = []
        for ch in text:
            result.append(self.LETTER_MAPPING.get(ch, ch))
        return ''.join(result)

    def _normalize_lower(self, text: str) -> str:
        return self._normalize(text).lower()

    def _extract_suffix_from_text(self, text: str, model_base: str, start_pos: int) -> str:
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

    def extract(self, text: str) -> ProductParams:
        """Главный метод: извлекает параметры из любого текста."""
        params = ProductParams(original_text=text)
        if not text:
            return params

        text_normalized = self._normalize(text)
        text_normalized_lower = text_normalized.lower()
        text_upper = text.upper()

        params.product_type = self._extract_product_type(text)
        params.brand = self._extract_brand(text)

        article_match = re.search(r'\b([A-Z]{2}\d{8})\b', text_upper)
        if article_match:
            params.article = article_match.group(1)

        if params.product_type == 'boiler':
            self._extract_boiler_params(params, text, text_upper, text_normalized, text_normalized_lower)
        elif params.product_type == 'chimney':
            self._extract_chimney_params(params, text_upper)
        elif params.product_type == 'water_heater':
            self._extract_water_heater_params(params, text)
        elif params.product_type == 'conversion_kit':
            self._extract_conversion_kit_params(params, text)
        elif params.product_type == 'radiator':
            self._extract_radiator_params(params, text)
        elif params.product_type == 'bracket':
            self._extract_bracket_params(params, text_upper)
        elif params.product_type == 'radiator_accessory':
            self._extract_radiator_accessory_params(params, text)
        elif params.product_type in ['sensor', 'part']:
            if not params.article:
                article_match = re.search(r'\b([A-Z]{2}\d{8})\b', text_upper)
                if article_match:
                    params.article = article_match.group(1)

        return params

    def _extract_product_type(self, text: str) -> str:
        text_lower = text.lower()
        text_normalized = self._normalize(text)

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

        if 'фланец' in text_lower:
            return 'chimney'

        if any(x in text_lower for x in ['котел', 'котёл']):
            return 'boiler'

        if re.search(r'\b6000\b', text_lower):
            return 'boiler'
        if re.search(r'(газ|gaz)\s*6000', text_lower):
            return 'boiler'

        if re.search(r'\b[BСCMВTQ]\s*[0-9]{1,2}\b', text_normalized, re.IGNORECASE):
            if re.search(r'\d{3,4}[/-]\d{3,4}', text) or 'profil' in text_lower:
                return 'radiator'
            return 'boiler'

        if re.search(r'\b[BСCMВTQ][0-9]{1,2}\b', text_normalized, re.IGNORECASE):
            if re.search(r'\d{3,4}[/-]\d{3,4}', text) or 'profil' in text_lower:
                return 'radiator'
            return 'boiler'

        if re.search(r'gaz6000', text_normalized, re.IGNORECASE):
            return 'boiler'

        if any(x in text_lower for x in ['бойлер', 'водонагреватель']):
            return 'water_heater'
        if re.search(r'iht\s*g\s*\d{3}', text_lower):
            return 'water_heater'

        if any(x in text_lower for x in ['дымоход', 'chimney']):
            return 'chimney'
        if re.search(r'dn\d{2,3}/\d{2,3}', text_lower):
            return 'chimney'
        if re.search(r'wt\d{5,6}-\d+', text_lower):
            return 'chimney'

        if any(x in text_lower for x in ['комплект', 'перенастройка', 'форсунка', 'lpg', 'сжиж']):
            return 'conversion_kit'
        if re.search(r'301\d{8}', text):
            return 'conversion_kit'

        if any(x in text_lower for x in ['радиатор', 'profil', 'kermi', 'purmo', 'buderus', 'evra', 'oasis']):
            return 'radiator'
        if re.search(r'\d{2}[/-]\d{3,4}[/-]\d{3,4}', text):
            return 'radiator'
        if re.search(r'\d{2}\s*[-]\s*\d{3,4}\s*[-]\s*\d{3,4}', text):
            return 'radiator'

        if any(x in text_lower for x in ['кронштейн', 'bracket']):
            return 'bracket'
        if re.search(r'[КK]\d{1,2}\.\d{1,4}', text):
            return 'bracket'
        if re.search(r'[КK][НH][СC]\d{3,4}', text):
            return 'bracket'
        if re.search(r'pln\d+', text_lower):
            return 'bracket'

        if any(x in text_lower for x in ['датчик', 'температуры', 'ntc']):
            return 'sensor'

        if any(x in text_lower for x in ['вентилятор', 'плата', 'клапан', 'теплообменник', 'насос', 'горелка',
                                          'форсунка', 'прокладка', 'кольцо', 'кабель', 'жгут', 'датчик',
                                          'скоба', 'клипса', 'трубка', 'штуцер', 'мотор', 'привод',
                                          'реле', 'термостат', 'сифон', 'диафрагма']):
            return 'part'
        if re.search(r'[A-Z]{2}\d{8}', text):
            return 'part'

        return 'other'

    def _extract_brand(self, text: str) -> str:
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
        Извлекает параметры котла через всеядный парсер boiler_parser.
        """
        try:
            from nextt.experimental.boiler_parser import parse_boiler
        except ImportError:
            self._log("    [WARN] boiler_parser недоступен, использую старую логику")
            self._extract_boiler_params_legacy(
                params, text, text_upper, text_normalized, text_normalized_lower
            )
            return

        parsed = parse_boiler(text)

        params.model = parsed.model or ""
        params.model_suffix = parsed.model_suffix or ""
        params.power = parsed.power
        params.conn_type = parsed.conn_type or ""
        params.has_wifi = parsed.has_wifi

        self._log(f"    [BoilerParser] model={params.model}, suffix={params.model_suffix}, "
                  f"power={params.power}, conn={params.conn_type}, wifi={params.has_wifi}")

    def _extract_boiler_params_legacy(self, params: ProductParams, text: str, text_upper: str,
                                       text_normalized: str, text_normalized_lower: str):
        """
        Старая логика извлечения параметров котла (fallback).
        """
        params.has_wifi = any(x in text.lower() for x in ['wi-fi', 'wifi', 'вайфай', 'вафай'])

        model_base = ""
        suffix = ""
        model_end_pos = 0

        # 6000 (без "ГАЗ")
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

        # ГАЗ 6000
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

        # Общий поиск моделей
        if not model_base:
            match = re.search(r'\b([BСCMВTQ])\s+([0-9]{1,2})([A-Z]{1,3})?\b', text_normalized, re.IGNORECASE)
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

        if model_base and not suffix and model_end_pos > 0:
            suffix = self._extract_suffix_from_text(text_normalized, model_base, model_end_pos)

        if model_base:
            params.model = model_base
            if suffix:
                params.model_suffix = suffix

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

        if not params.conn_type:
            if re.search(r'\bC\b', text_upper) or re.search(r'\bС\b', text_upper):
                params.conn_type = 'C'
            elif re.search(r'\bH\b', text_upper) or re.search(r'\bН\b', text_upper):
                params.conn_type = 'H'

    def _extract_chimney_params(self, params: ProductParams, text_upper: str):
        if 'ФЛАНЕЦ' in text_upper:
            return
        condensing_keywords = ['РР', 'PP', 'LN', 'ПП', 'полипропилен', 'конденсационный']
        for kw in condensing_keywords:
            if kw.upper() in text_upper:
                params.is_condensing = True
                break
        wt_match = re.search(r'(WT\d{5,6}-\d+[A-Z]*)', text_upper)
        if wt_match:
            params.article_code = wt_match.group(1)
            if 'LN' in params.article_code.upper():
                params.is_condensing = True
            if '60100' in params.article_code:
                params.size = 'DN60/100'
            elif '80125' in params.article_code:
                params.size = 'DN80/125'
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
        volume_match = re.search(r'IHT G (\d{3})', text, re.IGNORECASE)
        if volume_match:
            params.volume = int(volume_match.group(1))
            return
        volume_match = re.search(r'[Бб]ойлер\s+(\d{3})', text)
        if volume_match:
            params.volume = int(volume_match.group(1))

    def _extract_conversion_kit_params(self, params: ProductParams, text: str):
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