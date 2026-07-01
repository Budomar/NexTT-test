"""
equipment_normalizer.py - Версия 6.1
Универсальный поиск по параметрам с поддержкой суффиксов RN и приоритетом бренда LaggarTT.
Добавлена поддержка артикулов бойлеров (7U..., 7I...) и фланцев (B-01).
"""
import re
from typing import Dict, Optional, Tuple, List, Any
from dataclasses import dataclass, field
import difflib
import pandas as pd
from ..logger import get_logger
from .product_normalizer import ProductNormalizer, ProductParams

logger = get_logger(__name__)

@dataclass
class ParsedEquipment:
    """Результат парсинга названия оборудования."""
    recognized: bool = False
    article: str = ""
    name: str = ""
    confidence: float = 0.0
    source: str = ""
    warnings: List[str] = field(default_factory=list)
    
    # Дополнительные параметры
    brand: str = ""
    category: str = ""
    power_kw: Optional[int] = None
    model: str = ""
    model_suffix: str = ""
    connection_type: str = ""
    size: str = ""
    article_code: str = ""
    has_wifi: bool = False
    has_ot: bool = False

class EquipmentNormalizer:
    """
    УНИВЕРСАЛЬНЫЙ НОРМАЛИЗАТОР для названий оборудования.
    Версия 6.1: поиск по структурированным параметрам с приоритетом бренда.
    """
    
    def __init__(self, equipment_df=None, debug: bool = True):
        self.equipment_df = equipment_df
        self.debug = debug
        self.product_normalizer = ProductNormalizer()
        
        # Индексы для быстрого поиска
        self._article_index: Dict[str, Any] = {}
        self._params_index: List[Tuple[ProductParams, str]] = []  # (параметры, артикул)
        
        self._build_indices()

    def _log(self, message: str, level: str = "INFO") -> None:
        if self.debug:
            if level == "ERROR":
                logger.error(f"[EquipmentNormalizer] {message}")
            elif level == "WARNING":
                logger.warning(f"[EquipmentNormalizer] {message}")
            else:
                logger.info(f"[EquipmentNormalizer] {message}")

    def _get_model_base(self, model: str) -> str:
        """Получает базовую модель без суффиксов."""
        if not model:
            return ''
        base = re.sub(r'[RNAMTQBCXYZ]+$', '', model.upper())
        return base

    def _extract_boiler_params_for_index(self, text: str) -> ProductParams:
        """
        Извлекает параметры котла из названия для индексации.
        Специально для базы данных — учитывает суффиксы (RN, A, M, T, Q, H, C).
        """
        params = ProductParams(original_text=text)
        
        text_upper = text.upper()
        text_normalized = self.product_normalizer._normalize(text)
        
        # Определяем тип и бренд 
        params.product_type = 'boiler'
        params.brand = self.product_normalizer._extract_brand(text)
        
        # ========== ИЩЕМ МОДЕЛЬ И СУФФИКС ==========
        model_base = ""
        suffix = ""
        
        # Специальная обработка для ГАЗ 6000
        gaz_match = re.search(r'(ГАЗ|GAZ)\s*6000', text_normalized, re.IGNORECASE)
        if gaz_match:
            model_base = 'GAZ6000'
            after_model = text_normalized[gaz_match.end():]
            
            # Ищем тип подключения и суффикс
            # Паттерны: "24 C RN", "24C RN", "24RN", "24 H RN"
            patterns = [
                r'(\d*)\s*([CH])\s+([A-Z]{1,3})\b',   # 24 C RN
                r'(\d*)([CH])\s+([A-Z]{1,3})\b',      # 24C RN
                r'(\d*)([A-Z]{1,3})\b',                # 24RN
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
                self._log(f"    Найден суффикс для GAZ6000: {suffix}")
        
        # Общий поиск моделей (для M30, B30, C30 и т.д.)
        if not model_base:
            model_match = re.search(r'\b([A-Z]{1,3}[0-9]{1,2})\b', text_normalized, re.IGNORECASE)
            if model_match:
                model_base = model_match.group(1).upper()
                after_model = text_normalized[model_match.end():]
                
                # Ищем суффикс после модели
                suffix_match = re.search(r'^\s*([A-Z]{1,3})\b', after_model, re.IGNORECASE)
                if suffix_match:
                    suffix = suffix_match.group(1).upper()
                    self._log(f"    Найдена модель {model_base}, суффикс={suffix}")
                else:
                    self._log(f"    Найдена модель {model_base}, суффикс не найден")
        
        # Устанавливаем модель и суффикс (раздельно!)
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
            power_match_simple = re.search(r'\b(10|12|14|18|20|24|26|28|30|32|35|36|45|60|80)\b', text_upper)
            if power_match_simple:
                params.power = int(power_match_simple.group(1))
        
        # Wi-Fi
        params.has_wifi = any(x in text.lower() for x in ['wi-fi', 'wifi', 'вайфай', 'вафай'])
        
        # Для отладки
        self._log(f"    ИТОГО: модель={params.model}, суффикс={params.model_suffix}, мощность={params.power}, тип={params.conn_type}")
        
        return params

    def _build_indices(self) -> None:
        """Строит индекс параметров из базы данных с учётом суффиксов."""
        if self.equipment_df is None or self.equipment_df.empty:
            self._log("База данных оборудования не загружена", "WARNING")
            return
        
        self._log(f"Построение индекса параметров из {len(self.equipment_df)} записей...")
        
        for idx, row in self.equipment_df.iterrows():
            article = str(row.get('Артикул', '')).strip()
            name = str(row.get('Наименование', '')).strip()
            
            if not article or article == 'nan' or not name or name == 'nan':
                continue
            
            # ========== ОТЛАДКА: выводим все артикулы с AC ==========
            if article.startswith('AC'):
                self._log(f"    [ОТЛАДКА] НАЙДЕН АРТИКУЛ AC: {article} - {name[:50]}")
            
            # Индекс по артикулу
            self._article_index[article] = row
            
            # Извлекаем параметры из названия
            if any(x in name.lower() for x in ['котел', 'котёл', 'газ 6000']):
                params = self._extract_boiler_params_for_index(name)
            else:
                params = self.product_normalizer.extract(name)
            
            params.article = article
            
            if params.product_type == 'boiler':
                self._log(f"    Индекс: {article} -> модель={params.model}, суффикс={params.model_suffix}, мощность={params.power}, тип={params.conn_type}, wifi={params.has_wifi}")
            
            self._params_index.append((params, article))
        
        self._log(f"Индекс построен: {len(self._params_index)} записей")
        # ========== ДОПОЛНИТЕЛЬНАЯ ОТЛАДКА: список артикулов AC ==========
        ac_articles = [a for a in self._article_index.keys() if a.startswith('AC')]
        self._log(f"    [ОТЛАДКА] Артикулы AC в индексе: {ac_articles}")

    def _search_by_params(self, query_params: ProductParams) -> Optional[Tuple[str, str, float]]:
        """
        Поиск по параметрам с учётом суффиксов и типа подключения.
        """
        best_match = None
        best_score = 0.0
        best_article = None
        best_name = None
        
        for db_params, article in self._params_index:
            # Сравниваем параметры
            score = query_params.matches_params(db_params)
            
            # Бонус за приоритет бренда LaggarTT
            if not query_params.brand and db_params.brand == 'laggartt':
                score += 0.05
            
            # ========== ДЛЯ КОТЛОВ: дополнительные проверки ==========
            if query_params.product_type == 'boiler' and db_params.product_type == 'boiler':
                
                # 1. ШТРАФ за несовпадение типа подключения (C vs H)
                if query_params.conn_type and db_params.conn_type:
                    if query_params.conn_type != db_params.conn_type:
                        score -= 0.30
                        self._log(f"      Штраф: несовпадение типа подключения ({query_params.conn_type} vs {db_params.conn_type}) -0.30")
                
                # 2. Бонус/штраф за суффикс
                if query_params.model_suffix and db_params.model_suffix:
                    if query_params.model_suffix == db_params.model_suffix:
                        score += 0.15
                        self._log(f"      Бонус: совпадение суффикса {query_params.model_suffix} +0.15")
                    else:
                        score -= 0.10
                        self._log(f"      Штраф: несовпадение суффикса ({query_params.model_suffix} vs {db_params.model_suffix}) -0.10")
                elif query_params.model_suffix and not db_params.model_suffix:
                    score -= 0.10
                    self._log(f"      Штраф: у запроса есть суффикс {query_params.model_suffix}, у записи нет -0.10")
                elif not query_params.model_suffix and db_params.model_suffix:
                    score += 0.02
                
                # 3. Бонус за совпадение мощности
                if query_params.power and db_params.power:
                    if query_params.power == db_params.power:
                        score += 0.10
                    else:
                        score -= 0.05
            
            # ========== ДЛЯ ДЫМОХОДОВ: приоритет записям с размером ==========
            if query_params.product_type == 'chimney' and db_params.product_type == 'chimney':
                if query_params.size and db_params.size:
                    # У обоих есть размер - нормально, уже учтено в matches_params
                    pass
                elif query_params.size and not db_params.size:
                    # У запроса есть размер, у записи нет - штраф
                    score -= 0.20
                    self._log(f"      Штраф: у записи {article} нет размера, хотя у запроса есть {query_params.size} -0.20")
                elif not query_params.size and db_params.size:
                    # У запроса нет размера, у записи есть - небольшой бонус
                    score += 0.05
                    self._log(f"      Бонус: у записи {article} есть размер {db_params.size} +0.05")
            
            if score > best_score:
                best_score = score
                best_article = article
                best_name = str(self._article_index[article].get('Наименование', ''))
        
        if best_score >= 0.5:
            self._log(f"    Поиск по параметрам: уверенность={best_score:.2f}")
            return (best_article, best_name, best_score)
        
        return None

    def _search_by_fuzzy(self, text: str) -> Optional[Tuple[str, str, float]]:
        """Запасной поиск: нечёткое сравнение строк."""
        if not self._params_index:
            return None
        
        query_normalized = self.product_normalizer._normalize(text)
        
        names_list = []
        name_to_article = {}
        for db_params, article in self._params_index:
            name = str(self._article_index[article].get('Наименование', ''))
            normalized = self.product_normalizer._normalize(name)
            names_list.append(normalized)
            name_to_article[normalized] = article
        
        matches = difflib.get_close_matches(query_normalized, names_list, n=1, cutoff=0.4)
        
        if matches:
            best_match = matches[0]
            confidence = difflib.SequenceMatcher(None, query_normalized, best_match).ratio()
            article = name_to_article.get(best_match)
            if article:
                name = str(self._article_index[article].get('Наименование', ''))
                self._log(f"    Fuzzy поиск: уверенность={confidence:.2f}")
                return (article, name, confidence)
        
        return None

    def normalize_and_extract(self, text: str) -> ParsedEquipment:
        """Основной метод поиска."""
        result = ParsedEquipment()
        
        if not text or len(text.strip()) < 3:
            return result
        
        # ========== ПРЯМОЙ ПОИСК ПО АРТИКУЛУ (ПРИОРИТЕТ 1) ==========
        # Ищем артикул в тексте
        article_patterns = [
            r'\b([A-Z]{2}\d{8})\b',   # AC02000024, AA04010164
            r'\b(7[A-Z]\d{9})\b',     # 7U121011001, 7I121011001 (бойлеры)
            r'\b(\d{10,11})\b',        # 87323019330
            r'\b([A-Z]-\d+)\b',        # B-01 (фланцы)
            r'\b([КK]\d{1,2}\.\d{1,4}[A-Z]?\d*)\b',  # Кронштейны
        ]
        for pattern in article_patterns:
            match = re.search(pattern, text.upper())
            if match:
                article = match.group(1)
                self._log(f"    Найден потенциальный артикул: {article}")
                # Ищем в индексе по артикулу
                if article in self._article_index:
                    row = self._article_index[article]
                    result.article = article
                    result.name = str(row.get('Наименование', ''))
                    result.recognized = True
                    result.confidence = 1.0
                    result.source = "article_match"
                    self._log(f"    ✅ Найдено по артикулу: {article} - {result.name[:50]}")
                    return result
                else:
                    self._log(f"    Артикул {article} не найден в базе, продолжаем поиск")
        
        # ========== ПРИОРИТЕТ 2: ИЗВЛЕКАЕМ ПАРАМЕТРЫ ==========
        query_params = self.product_normalizer.extract(text)
        result.category = query_params.product_type
        result.brand = query_params.brand
        result.power_kw = query_params.power
        result.model = query_params.model
        result.model_suffix = query_params.model_suffix
        result.connection_type = query_params.conn_type
        result.has_wifi = query_params.has_wifi
        
        self._log(f"    Извлечены параметры: тип={query_params.product_type}, модель={query_params.model}, суффикс={query_params.model_suffix}, мощность={query_params.power}, тип_подкл={query_params.conn_type}, wifi={query_params.has_wifi}")
        
        # 2. Поиск по параметрам
        found = self._search_by_params(query_params)
        if found:
            result.article, result.name, result.confidence = found
            result.recognized = True
            result.source = "params_match"
            self._log(f"    ✅ Найдено по параметрам: {result.article} (уверенность={result.confidence:.2f})")
            return result
        
        # 3. Запасной поиск: fuzzy
        found = self._search_by_fuzzy(text)
        if found:
            result.article, result.name, result.confidence = found
            result.recognized = True
            result.source = "fuzzy_match"
            self._log(f"    ✅ Найдено через fuzzy поиск: {result.article} (уверенность={result.confidence:.2f})")
            return result
        
        self._log(f"    ❌ НЕ НАЙДЕНО")
        return result

    def match_line(self, text: str, quantity: Optional[int] = None) -> Dict:
        """Обрабатывает одну строку."""
        result = {
            'success': False,
            'article': '',
            'name': '',
            'quantity': quantity or 0,
            'original_text': text,
            'error': '',
            'confidence': 0.0,
            'source': ''
        }
        
        self._log(f"Обработка строки: '{text[:80]}'")
        parsed = self.normalize_and_extract(text)
        
        if parsed.recognized and parsed.article:
            result['success'] = True
            result['article'] = parsed.article
            result['name'] = parsed.name
            result['confidence'] = parsed.confidence
            result['source'] = parsed.source
            self._log(f"  ✅ УСПЕХ: {parsed.article} - {parsed.name[:50]}")
        else:
            result['error'] = 'Не найдено в базе'
            self._log(f"  ❌ НЕ НАЙДЕНО")
        
        return result