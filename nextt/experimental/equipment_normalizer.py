"""
equipment_normalizer.py - Версия 5.0
Универсальный поиск по параметрам с приоритетом бренда LaggarTT.
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
    Версия 5.0: поиск по структурированным параметрам с приоритетом бренда.
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
        """
        Получает базовую модель без суффиксов.
        Например: GAZ6000RN -> GAZ6000, B30RN -> B30
        """
        if not model:
            return ''
        # Удаляем суффиксы: RN, A, M, T, Q, C, H, S и т.д.
        base = re.sub(r'[RNAMTQBCXYZ]+$', '', model.upper())
        return base
    
    def _build_indices(self) -> None:
        """Строит индекс параметров из базы данных."""
        if self.equipment_df is None or self.equipment_df.empty:
            self._log("База данных оборудования не загружена", "WARNING")
            return
        
        self._log(f"Построение индекса параметров из {len(self.equipment_df)} записей...")
        
        for idx, row in self.equipment_df.iterrows():
            article = str(row.get('Артикул', '')).strip()
            name = str(row.get('Наименование', '')).strip()
            
            if not article or article == 'nan' or not name or name == 'nan':
                continue
            
            # Индекс по артикулу
            self._article_index[article] = row
            
            # Извлекаем параметры из названия
            params = self.product_normalizer.extract(name)
            params.article = article

            # ОТЛАДКА: выводим параметры для котлов
            if params.product_type == 'boiler':
                self._log(f"    Индекс: {article} -> модель={params.model}{params.model_suffix}, мощность={params.power}, тип={params.conn_type}, wifi={params.has_wifi}")
            
            self._params_index.append((params, article))
        
        self._log(f"Индекс построен: {len(self._params_index)} записей")
    
    def _search_by_params(self, query_params: ProductParams) -> Optional[Tuple[str, str, float]]:
        """
        Поиск по параметрам.
        Возвращает (артикул, название, уверенность) или None.
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
            
            # Для комплектов: если мощность не указана, приоритет 32 кВт (10-32)
            if query_params.product_type == 'conversion_kit' and query_params.power is None:
                if db_params.power == 32:
                    score += 0.1
                elif db_params.power == 36:
                    score -= 0.05
            
            # ========== ДЛЯ ДЫМОХОДОВ ==========
            if query_params.product_type == 'chimney':
                # Бонус за совпадение артикула
                if query_params.article_code and db_params.article_code:
                    if query_params.article_code == db_params.article_code:
                        score += 0.5
                        self._log(f"      Совпадение артикула дымохода: {query_params.article_code}")
                
                # Бонус за совпадение размера
                if query_params.size and db_params.size:
                    if query_params.size == db_params.size:
                        score += 0.3
                    else:
                        score -= 0.2
                
                # Бонус/штраф за конденсационный тип (PP/LN)
                if query_params.is_condensing == db_params.is_condensing:
                    score += 0.2
                else:
                    score -= 0.3
            
            # ========== ДЛЯ КОТЛОВ: бонус/штраф за совпадение модели ==========
            if query_params.product_type == 'boiler' and query_params.model and db_params.model:
                # Полное совпадение модели и суффикса
                if (query_params.model.upper() == db_params.model.upper() and 
                    query_params.model_suffix.upper() == db_params.model_suffix.upper()):
                    score += 0.25  # Полный матч
                elif query_params.model.upper() == db_params.model.upper():
                    score += 0.15   # Совпадение по модели без суффикса
                else:
                    # Частичное совпадение (основы)
                    # Для GAZ6000: GAZ6000RN, GAZ6000A, GAZ6000 должны совпадать
                    query_base = self._get_model_base(query_params.model)
                    db_base = self._get_model_base(db_params.model)
                    if query_base == db_base:
                        # Базы совпадают (например, GAZ6000), проверяем суффикс
                        if query_params.model_suffix and db_params.model_suffix:
                            if query_params.model_suffix.upper() == db_params.model_suffix.upper():
                                score += 0.15  # Суффикс совпал — большой бонус
                            else:
                                score += 0.05  # Разные суффиксы, но база та же
                        elif not query_params.model_suffix:
                            score += 0.10  # Запрос без суффикса — любое совпадение базы
                        else:
                            # У запроса есть суффикс, у записи нет — небольшой штраф
                            score += 0.03
                    else:
                        score -= 0.05  # Разные модели
            
            # Если модель не указана, но есть мощность и тип подключения
            elif query_params.product_type == 'boiler' and not query_params.model:
                # Будем искать только по мощности и типу подключения
                pass
            
            if score > best_score:
                best_score = score
                best_article = article
                best_name = str(self._article_index[article].get('Наименование', ''))
        
        if best_score >= 0.5:
            self._log(f"    Поиск по параметрам: уверенность={best_score:.2f}")
            return (best_article, best_name, best_score)
        
        return None
    
    def _search_by_fuzzy(self, text: str) -> Optional[Tuple[str, str, float]]:
        """
        Запасной поиск: нечёткое сравнение строк.
        """
        if not self._params_index:
            return None
        
        # Нормализуем текст пользователя
        query_normalized = self.product_normalizer._normalize(text)
        
        # Собираем все нормализованные названия из индекса
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
        """
        Основной метод поиска.
        """
        result = ParsedEquipment()
        
        if not text or len(text.strip()) < 3:
            return result
        
        # 1. Извлекаем параметры из запроса пользователя
        query_params = self.product_normalizer.extract(text)
        result.category = query_params.product_type
        result.brand = query_params.brand
        result.power_kw = query_params.power
        result.model = query_params.model
        result.model_suffix = query_params.model_suffix
        result.connection_type = query_params.conn_type
        result.has_wifi = query_params.has_wifi
        
        self._log(f"    Извлечены параметры: тип={query_params.product_type}, модель={query_params.model}{query_params.model_suffix}, мощность={query_params.power}, тип_подкл={query_params.conn_type}, wifi={query_params.has_wifi}")
        
        # ОТЛАДКА: показываем параметры для ГАЗ6000
        if 'GAZ6000' in query_params.model.upper():
            self._log(f"    DEBUG: query_params.model_suffix = '{query_params.model_suffix}'")
        
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