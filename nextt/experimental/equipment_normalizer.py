"""
equipment_normalizer.py - Версия 7.0
Универсальный поиск по параметрам с поддержкой суффиксов RN и приоритетом бренда LaggarTT.
Добавлена поддержка артикулов бойлеров (7U..., 7I...) и фланцев (B-01).
Скоринг нормализован в [0, 1], убраны двойные штрафы.
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
    Версия 7.0: поиск по структурированным параметрам с приоритетом бренда.
    """

    def __init__(self, equipment_df=None, debug: bool = True):
        self.equipment_df = equipment_df
        self.debug = debug
        self.product_normalizer = ProductNormalizer()

        self._article_index: Dict[str, Any] = {}
        self._params_index: List[Tuple[ProductParams, str]] = []

        self._build_indices()

    def _log(self, message: str, level: str = "INFO") -> None:
        if self.debug:
            if level == "ERROR":
                logger.error(f"[EquipmentNormalizer] {message}")
            elif level == "WARNING":
                logger.warning(f"[EquipmentNormalizer] {message}")
            else:
                logger.info(f"[EquipmentNormalizer] {message}")

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

            self._article_index[article] = row

            # Извлекаем параметры из названия через ProductNormalizer
            # (для котлов ProductNormalizer делегирует в boiler_parser)
            params = self.product_normalizer.extract(name)
            params.article = article

            self._params_index.append((params, article))

        self._log(f"Индекс построен: {len(self._params_index)} записей")

    def _search_by_params(self, query_params: ProductParams) -> Optional[Tuple[str, str, float]]:
        """
        Поиск по параметрам с учётом типа товара и модели.
        Скоринг нормализован, без двойных штрафов.
        """
        if not query_params.product_type or query_params.product_type == 'other':
            self._log(f"    Тип не определён, пропускаем поиск по параметрам")
            return None

        # ============================================================
        # ОТСЕЧЕНИЕ МУСОРА: для котлов обязательны модель и мощность
        # ============================================================
        if query_params.product_type == 'boiler':
            if not query_params.model:
                self._log(f"    Котёл без модели — пропускаем")
                return None
            if not query_params.power:
                self._log(f"    Котёл без мощности — пропускаем")
                return None

        # ============================================================
        # ОТСЕЧЕНИЕ МУСОРА: для дымоходов нужен хотя бы один признак
        # (размер, артикул или признак конденсации).
        # Иначе запрос вида "Фланец" или "Дымоход" без конкретики
        # может подобрать что угодно.
        # ============================================================
        if query_params.product_type == 'chimney':
            if not (query_params.size or query_params.article_code or query_params.is_condensing):
                self._log(f"    Дымоход без конкретики (нет размера/артикула/PP) — пропускаем")
                return None

        best_match = None
        best_score = 0.0
        best_article = None
        best_name = None

        query_model = query_params.model.upper() if query_params.model else ""
        self._log(f"    Поиск по модели: '{query_model}'")

        for db_params, article in self._params_index:
            # Тип товара должен совпадать точно
            if db_params.product_type != query_params.product_type:
                continue

            # Для котлов: модель и мощность обязательны
            if query_params.product_type == 'boiler':
                if not db_params.model:
                    self._log(f"    Пропускаем {article}: нет модели в базе")
                    continue
                if query_model != db_params.model.upper():
                    continue
                if not db_params.power:
                    self._log(f"    Пропускаем {article}: нет мощности в базе")
                    continue
                if query_params.power != db_params.power:
                    continue

            # Для котлов: тип подключения должен совпадать
            if query_params.product_type == 'boiler':
                if query_params.conn_type and db_params.conn_type:
                    if query_params.conn_type != db_params.conn_type:
                        self._log(f"    Пропускаем {article}: тип подключения "
                                  f"{db_params.conn_type} != {query_params.conn_type}")
                        continue
                elif query_params.conn_type and not db_params.conn_type:
                    self._log(f"    Пропускаем {article}: у запроса есть тип "
                              f"{query_params.conn_type}, у базы нет")
                    continue

            # ============================================================
            # ЖЁСТКОЕ ОТСЕЧЕНИЕ: для дымоходов
            # ============================================================
            if query_params.product_type == 'chimney':
                # Если у запроса есть размер — у базы он должен совпадать
                if query_params.size:
                    if not db_params.size:
                        self._log(f"    Пропускаем {article}: нет размера в базе")
                        continue
                    if query_params.size != db_params.size:
                        self._log(f"    Пропускаем {article}: размер {db_params.size} != {query_params.size}")
                        continue
                # Если у запроса есть артикул — у базы он должен совпадать
                if query_params.article_code:
                    if not db_params.article_code:
                        self._log(f"    Пропускаем {article}: нет артикула в базе")
                        continue
                    self_art = query_params.article_code.replace('NEW ', '').strip()
                    db_art = db_params.article_code.replace('NEW ', '').strip()
                    if self_art != db_art:
                        self._log(f"    Пропускаем {article}: артикул {db_art} != {self_art}")
                        continue

            score = query_params.matches_params(db_params)

            # Лёгкий бонус за бренд LaggarTT (только если бренд не указан в запросе)
            if not query_params.brand and db_params.brand == 'laggartt':
                score += 0.02

            if score > best_score:
                best_score = score
                best_article = article
                best_name = str(self._article_index[article].get('Наименование', ''))

        if best_score >= 0.75:
            self._log(f"    Поиск по параметрам: уверенность={best_score:.2f}")
            return (best_article, best_name, best_score)

        self._log(f"    Поиск по параметрам: лучшая уверенность={best_score:.2f} (ниже порога 0.75)")
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
        article_patterns = [
            r'\b([A-Z]{2}\d{8})\b',
            r'\b(7[A-Z]\d{9})\b',
            r'\b(\d{10,11})\b',
            r'\b([A-Z]-\d+)\b',
            r'\b([КK]\d{1,2}\.\d{1,4}[A-Z]?\d*)\b',
        ]
        for pattern in article_patterns:
            match = re.search(pattern, text.upper())
            if match:
                article = match.group(1)
                self._log(f"    Найден потенциальный артикул: {article}")
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

        self._log(f"    Извлечены параметры: тип={query_params.product_type}, "
                  f"модель={query_params.model}, суффикс={query_params.model_suffix}, "
                  f"мощность={query_params.power}, тип_подкл={query_params.conn_type}, wifi={query_params.has_wifi}")

        # ========== 2. ПОИСК ПО ПАРАМЕТРАМ ==========
        found = self._search_by_params(query_params)
        if found:
            found_article, found_name, found_confidence = found

            power_mismatch = False
            if query_params.power and query_params.product_type == 'boiler':
                for db_params, article in self._params_index:
                    if article == found_article and db_params.power:
                        if db_params.power != query_params.power:
                            power_mismatch = True
                            self._log(f"    ⚠ НЕСОВПАДЕНИЕ МОЩНОСТИ: запрос {query_params.power} кВт, найдено {db_params.power} кВт")
                            result.warnings.append(f"Мощность не совпадает: запрос {query_params.power} кВт, найдено {db_params.power} кВт")
                        break

            if power_mismatch:
                found_confidence = min(found_confidence, 0.4)
                self._log(f"    Уверенность снижена до {found_confidence:.2f} из-за несовпадения мощности")

            if found_confidence >= 0.5:
                result.article = found_article
                result.name = found_name
                result.recognized = True
                result.confidence = found_confidence
                result.source = "params_match"
                self._log(f"    ✅ Найдено по параметрам: {result.article} (уверенность={result.confidence:.2f})")
                return result
            else:
                self._log(f"    ❌ Отклонено из-за низкой уверенности: {found_confidence:.2f}")

        # ========== 3. ЗАПАСНОЙ ПОИСК: FUZZY ==========
        found = self._search_by_fuzzy(text)
        if found:
            found_article, found_name, found_confidence = found
            result.article = found_article
            result.name = found_name
            result.recognized = True
            result.confidence = found_confidence
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