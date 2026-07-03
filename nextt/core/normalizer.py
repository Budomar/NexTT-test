"""
spec_normalizer.py - Модуль для нормализации и распознавания названий радиаторов
Версия: 7.0 — Всеядный парсер. Устойчив к сокращениям, точкам, разным падежам и форматам.
"""

import re
from typing import Dict, Optional, Tuple, List, Any

from nextt.logger import get_logger

logger = get_logger(__name__)


class ParsedRadiator:
    """Результат парсинга названия радиатора"""
    def __init__(self):
        self.recognized = False
        self.connection = "VK-правое"
        self.rad_type = "10"
        self.height = None
        self.length = None
        self.confidence = 0.0
        self.source = ""
        self.brand = ""
        self.warnings = []

    def to_dict(self) -> Dict[str, Any]:
        return {
            'recognized': self.recognized,
            'connection': self.connection,
            'type': self.rad_type,
            'height': self.height,
            'length': self.length,
            'confidence': self.confidence,
            'source': self.source,
            'brand': self.brand,
            'warnings': self.warnings
        }


class SpecNormalizer:
    """
    УНИВЕРСАЛЬНЫЙ ВСЕЯДНЫЙ НОРМАЛИЗАТОР названий радиаторов. v7.0
    Полная защита от падений. Устойчив к сокращениям и разным форматам.
    """

    VALID_TYPES = {'10', '11', '12', '20', '21', '22', '30', '33'}
    VALID_HEIGHTS = [300, 400, 500, 600, 900]
    VALID_LENGTHS = set(range(400, 3100, 100))

    HEIGHT_MAPPING = {
        200: 300, 250: 300, 305: 300, 350: 400,
        450: 500, 505: 500, 550: 600, 650: 600,
        700: 600, 750: 900, 800: 900, 1000: 900,
    }

    EVRA_TYPE_MAP = {
        'c11': '11', 'c21s': '21', 'c21': '21', 'c22': '22', 'c33': '33',
        'cv11': '11', 'cv21': '21', 'cv22': '22', 'cv33': '33',
        'h10': '10', 'h20': '20', 'h30': '30',
    }

    OASIS_CONNECTION_MAP = {
        'oc': 'K-боковое', 'pb': 'K-боковое', 'рb': 'K-боковое',
        'ov': 'VK-правое', 'pn': 'VK-правое', 'рn': 'VK-правое',
    }

    KNOWN_BRANDS = [
        'kermi', 'kermy', 'purmo', 'buderus', 'royal thermo',
        'royalthermo', 'evra', 'oasis', 'prado', 'korado',
        'valfex', 'rommer', 'arbonia','lemax', 'stelrad', 'ferroli',
        'ruterm', 'forte', 'terma', 'korad', 'hiterm',
        'vogel', 'radson', 'hitachi', 'lidea', 'ростерм',
        'meteor', 'laggar', 'logatrend', 'isoterm', 'spl',
    ]

    def __init__(self, debug: bool = False, templates_file: str = "templates.json"):
        self.debug = debug
        self.templates_file = templates_file
        self._strategies = []  # список стратегий (шаблоны + встроенные)
        self._load_templates()  # СНАЧАЛА загружаем шаблоны
        self._load_builtin_strategies()  # ПОТОМ встроенные
    
    def _load_builtin_strategies(self):
        builtin = [
            ("evra_format", self._parse_evra_format, 0.98),
            ("oasis", self._parse_oasis, 0.95),
            ("coded_triplet", self._parse_coded_triplet, 0.95),
            ("laggar", self._parse_laggar_format, 0.95),
            ("arbonia_ftv", self._parse_arbonia_ftv, 0.92),
            ("kermi", self._parse_kermi, 0.92),
            ("lidea", self._parse_lidea, 0.90),
            ("evra", self._parse_evra, 0.90),
            ("compact_prefix", self._parse_compact_with_prefix, 0.90),
            ("rostorm", self._parse_rostorm, 0.85),
            ("universal_triplet", self._parse_universal_triplet, 0.85),
            ("compact_triplet", self._parse_compact_triplet, 0.85),
            ("text_with_type", self._parse_text_with_type, 0.80),
            ("height_length", self._parse_height_length_only, 0.65),
        ]
        
        self._strategies.extend(builtin)  # ← ДОБАВЛЯЕТ!
        self._strategies.sort(key=lambda x: x[2], reverse=True)
        
        logger.info(f"[SpecNormalizer] Добавлено {len(builtin)} встроенных стратегий, всего стратегий: {len(self._strategies)}")

    def _load_templates(self):
        """Загружает шаблоны из templates.json и преобразует их в стратегии."""
        import json
        import os
        from nextt.config import get_resource_path
        
        # Ищем файл в нескольких местах
        possible_paths = [
            self.templates_file,  # переданный путь
            "templates.json",     # текущая директория
            get_resource_path("templates.json"),  # ресурсы
            os.path.join(os.path.dirname(__file__), "templates.json"),  # рядом с normalizer.py
        ]
        
        found_path = None
        for path in possible_paths:
            if path and os.path.exists(path):
                found_path = path
                break
        
        if not found_path:
            logger.info(f"[SpecNormalizer] Файл шаблонов не найден")
            return
        
        try:
            with open(found_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            templates = data.get("шаблоны", []) if isinstance(data, dict) else data
            
            logger.info(f"[SpecNormalizer] Найдено {len(templates)} шаблонов в файле: {found_path}")
            
            added_count = 0
            
            for template_data in templates:
                template_id = template_data.get("id", "")
                mask = template_data.get("mask", "")
                connection = template_data.get("connection", "VK-правое")
                priority = template_data.get("priority", 90)
                
                # Если нет mask — пропускаем
                if not mask:
                    continue
                
                # ================================================================
                # ПРЕОБРАЗОВАНИЕ MASK В РЕГУЛЯРНОЕ ВЫРАЖЕНИЕ
                # ================================================================
                import re
                # Пример: "{type}CV-{height}-{length} L"
                # Станет: r'\b(\d+)CV-(\d+)-(\d+) L(?:\s|$|[,.;:!?])'
                
                # Временно заменяем {type}, {height}, {length} на плейсхолдеры
                temp_mask = mask
                temp_mask = temp_mask.replace("{type}", "###TYPE###")
                temp_mask = temp_mask.replace("{height}", "###HEIGHT###")
                temp_mask = temp_mask.replace("{length}", "###LENGTH###")
                
                # Экранируем все специальные символы
                escaped = re.escape(temp_mask)
                
                # Возвращаем группы захвата
                regex_pattern = escaped
                regex_pattern = regex_pattern.replace("###TYPE###", "(\\d+)")
                regex_pattern = regex_pattern.replace("###HEIGHT###", "(\\d+)")
                regex_pattern = regex_pattern.replace("###LENGTH###", "(\\d+)")
                
                # Добавляем границу слова в начале и разделители в конце
                regex_pattern = r'\b' + regex_pattern + r'(?:\s|$|[,.;:!?])'
                
                # ================================================================
                # СОЗДАЁМ СТРАТЕГИЮ
                # ================================================================
                def make_strategy(pattern=regex_pattern, conn=connection, conf=priority/100, tid=template_id):
                    def strategy(text, original):
                        try:
                            match = re.search(pattern, text, re.IGNORECASE)
                            if not match:
                                return None
                            
                            type_str = match.group(1)
                            height_str = match.group(2)
                            length_str = match.group(3)
                            
                            # Преобразуем тип
                            rad_type = type_str
                            if rad_type == '12':
                                rad_type = '21'
                            elif rad_type not in ['10', '11', '20', '21', '22', '30', '33']:
                                return None
                            
                            try:
                                height = int(height_str)
                            except:
                                return None
                            
                            try:
                                length = int(length_str)
                            except:
                                return None
                            
                            # Проверяем валидность
                            if height not in [300, 400, 500, 600, 900]:
                                return None
                            if length < 400 or length > 3000 or length % 100 != 0:
                                return None
                            
                            # ================================================================
                            # КОРРЕКТИРОВКА ПОДКЛЮЧЕНИЯ ДЛЯ УНИВЕРСАЛЬНЫХ ТИПОВ
                            # ================================================================
                            # Универсальные типы (20, 21, 22) — всегда VK-правое
                            if rad_type in ['20', '21', '22']:
                                final_connection = "VK-правое"
                            else:
                                final_connection = conn
                            
                            result = ParsedRadiator()
                            result.recognized = True
                            result.connection = final_connection
                            result.rad_type = rad_type
                            result.height = height
                            result.length = length
                            result.confidence = conf
                            result.source = f"template_{tid}"
                            return result
                        except:
                            return None
                    return strategy
                
                # ДОБАВЛЯЕМ шаблон в список стратегий
                self._strategies.append((f"template_{template_id}", make_strategy(), priority / 100))
                added_count += 1
                logger.info(f"[SpecNormalizer] Добавлен шаблон: {template_id} (mask='{mask}', priority={priority/100:.2f})")
            
            # Сортируем по приоритету
            self._strategies.sort(key=lambda x: x[2], reverse=True)
            
            logger.info(f"[SpecNormalizer] Загружено и добавлено {added_count} шаблонов, всего стратегий: {len(self._strategies)}")
            
        except Exception as e:
            logger.error(f"[SpecNormalizer] Ошибка загрузки шаблонов: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    def reload_templates(self):
        """Перезагружает шаблоны (вызывается после обучения нового шаблона)."""
        # Удаляем все стратегии-шаблоны
        self._strategies = [s for s in self._strategies if not s[0].startswith("template_")]
        # Загружаем заново
        self._load_templates()
        logger.info("Шаблоны перезагружены")

    def _log(self, message: str, level: str = "INFO") -> None:
        if self.debug:
            if level == "ERROR":
                logger.error(f"[SpecNormalizer] {message}")
            elif level == "WARNING":
                logger.warning(f"[SpecNormalizer] {message}")
            else:
                logger.info(f"[SpecNormalizer] {message}")

    # ========================================================================
    # ОСНОВНОЙ МЕТОД
    # ========================================================================

    def normalize_and_extract(self, name: str) -> ParsedRadiator:
        """
        Основной метод парсинга. ГАРАНТИРОВАННО возвращает ParsedRadiator.
        Никогда не выбрасывает исключений. Не зависает.
        """
        if not name or not isinstance(name, str) or len(name.strip()) < 3:
            return ParsedRadiator()

        original = name
        processed = ""

        try:
            processed = self._preprocess(name)
        except Exception as e:
            self._log(f"Ошибка предобработки '{name[:80]}...': {e}", "ERROR")
            return ParsedRadiator()

        # Логируем, сколько стратегий всего
        logger.info(f"  [SpecNormalizer] Всего стратегий: {len(self._strategies)}")
        logger.info(f"  [SpecNormalizer] Из них шаблонов: {len([s for s in self._strategies if s[0].startswith('template_')])}")

        best_result = ParsedRadiator()

        for strategy_name, strategy_func, confidence in self._strategies:
            try:
                logger.info(f"  [SpecNormalizer] Пробуем стратегию: {strategy_name} (conf={confidence})")
                result = strategy_func(processed, original)
                if result and result.recognized:
                    logger.info(f"  [SpecNormalizer] ✅ Стратегия '{strategy_name}' сработала! "
                               f"type={result.rad_type}, h={result.height}, l={result.length}, "
                               f"conn={result.connection}, conf={result.confidence}")
                    if result.confidence > best_result.confidence:
                        best_result = result
                        if result.confidence >= 0.95:
                            logger.info(f"  [SpecNormalizer] Достигнут max confidence, прекращаем поиск")
                            break
                else:
                    logger.info(f"  [SpecNormalizer] ❌ Стратегия '{strategy_name}' не сработала")
            except Exception as e:
                self._log(f"Стратегия '{strategy_name}' упала: {e}", "ERROR")
                continue

        if best_result.recognized:
            logger.info(f"  [SpecNormalizer] Лучший результат: source={best_result.source}, conf={best_result.confidence}")
            try:
                best_result = self._validate_and_fix(best_result, original)
            except Exception as e:
                self._log(f"Ошибка валидации: {e}", "ERROR")
                best_result.recognized = False
        else:
            logger.info(f"  [SpecNormalizer] ❌ НИ ОДНА СТРАТЕГИЯ НЕ СРАБОТАЛА для '{original[:60]}'")

        return best_result

    # ========================================================================
    # ПРЕДОБРАБОТКА (УСИЛЕННАЯ)
    # ========================================================================

    def _preprocess(self, text: str) -> str:
        """
        Предобработка текста. Удаляет мусор, нормализует разделители.
        """
        if not text:
            return ""

        processed = text.lower().strip()

        # Замена специальных символов
        replacements = [
            ('ё', 'е'), ('—', '-'), ('–', '-'), ('_', ' '), ('\\', '/'),
            ('х', 'x'), ('Х', 'x'), ('×', 'x'),
            ('«', '"'), ('»', '"'),
        ]
        for old, new in replacements:
            processed = processed.replace(old, new)

        # Нормализация разделителей в размерах: 33/500/900 -> 33 500 900
        processed = re.sub(r'(\d{3,4})\s*/\s*(\d{3,4})', r'\1 \2', processed)
        # Нормализация Oasis: PN 22-4-05 -> PN 22 4 05
        processed = re.sub(
            r'\b(pn|pb|oc|ov|рn|рb)\s+(\d{1,2})\s*[\-\s]\s*(\d{1,2})\s*[\-\s]\s*(\d{1,2})\b',
            r'\1 \2 \3 \4', processed, flags=re.IGNORECASE
        )

        # Удаление мусорных фраз
        garbage_phrases = [
            r'радиатор\s+стальной\s+панельный',
            r'стальной\s+панельный\s+радиатор',
            r'панельный\s+радиатор',
            r'радиатор\s+отопления',
            r'радиатор\s+',
            r'\(боковое подключение\)',
            r'\(донное подключение\)',
            r'\(нижнее подключение\)',
            r'с гладкой поверхностью',
            r'в комплекте с',
            r'с комплектом крепления',
            r'комплект креплений',
            r'с монтажным комплектом',
            r'с настенным креплением',
            r'с боковым подключением',
            r'с нижним подключением',
            r'с нижнем подключением',
            r'с правой стороны',
            r'с левой стороны',
            r'и встроенной',
            r'вентильной вставкой',
            r'ридан\s*\d+[\w./]*',
            r'\d+\s*мм',
            r'\d+\s*cm',
            r'ral\s*\d+',
            r'q\d*\s*=\s*[\d.,]+\s*(?:вт|квт|kw|w)',
            r'гост\s*[\d\-]+',
            r'ту\s*[\d\-]+',
        ]
        for phrase in garbage_phrases:
            processed = re.sub(phrase, ' ', processed, flags=re.IGNORECASE)

        # Удаление оставшихся скобок и кавычек (но не чисел!)
        processed = re.sub(r'[\(\)\[\]""]', ' ', processed)

        # Нормализация пробелов
        processed = re.sub(r'\s+', ' ', processed).strip()

        # Заменяем запятые в числах на точки
        processed = re.sub(r'(\d),(\d)', r'\1.\2', processed)

        # Чистим края от мусора
        processed = processed.strip('.,;:!?()[]{}"\'- ')

        return processed

    # ========================================================================
    # ОПРЕДЕЛЕНИЕ СТОРОНЫ (ВСЕЯДНОЕ)
    # ========================================================================

    def _determine_side(self, text: str, original: str = "") -> Optional[str]:
        """
        Возвращает 'left', 'right', или None.
        Распознаёт ВСЕ возможные варианты написания стороны.
        """
        # Объединяем оба текста для поиска
        t = (text + " " + original).lower()

        # ================================================================
        # ПРИЗНАКИ ЛЕВОЙ СТОРОНЫ
        # ================================================================
        left_patterns = [
            # Суффиксы (отдельные слова)
            r'\b(?:la|ls)\b',
            # Суффиксы в конце строки (без границы слова после)
            r'(?:la|ls)$',
            # Буквы латиницей (отдельно стоящие, не часть слова)
            r'(?<![a-z])l(?![a-z0-9])',
            # Сокращения с точкой
            r'\bлев\.',
            # Полные слова (все падежи и роды)
            r'\bлев(?:ое|ый|ая|ые|а|о)?\b',
            # Наречие
            r'\bслева\b',
            # Сложные слова
            r'\bлевостор(?:онн(?:ее|ий|яя|ие|яя)|\.)?\b',
            # Английские
            r'\bleft\b',
            # Словосочетания
            r'подключение\s*левое',
            r'подкл\.\s*лев',
            r'исполнение\s*левое',
        ]
        for pat in left_patterns:
            if re.search(pat, t):
                return 'left'

        # ================================================================
        # ПРИЗНАКИ ПРАВОЙ СТОРОНЫ
        # ================================================================
        right_patterns = [
            # Суффиксы (отдельные слова)
            r'\b(?:ra|re)\b',
            # Суффиксы в конце строки (без границы слова после)
            r'(?:ra|re)$',
            # Буквы латиницей (отдельно стоящие)
            r'(?<![a-z])r(?![a-z0-9])',
            # Сокращения с точкой
            r'\bправ\.',
            # Полные слова (все падежи и роды)
            r'\bправ(?:ое|ый|ая|ые|а|о)?\b',
            # Наречие
            r'\bсправа\b',
            # Сложные слова
            r'\bправостор(?:онн(?:ее|ий|яя|ие|яя)|\.)?\b',
            # Английские
            r'\bright\b',
            # Словосочетания
            r'подключение\s*правое',
            r'подкл\.\s*прав',
            r'исполнение\s*правое',
        ]
        for pat in right_patterns:
            if re.search(pat, t):
                return 'right'

        #   Проверка суффиксов слов (CVL → CV + L = левое, CVR → CV + R = правое)
        # Ищем слова из 2-4 букв, заканчивающиеся на l или r
        left_suffix = re.findall(r'\b[a-z]{1,3}l\b', t)
        right_suffix = re.findall(r'\b[a-z]{1,3}r\b', t)
        
        if left_suffix and not right_suffix:
            return 'left'
        if right_suffix and not left_suffix:
            return 'right'

        return None

    def _determine_connection_type(self, text: str, original: str = "") -> str:
        """
        Определяет тип подключения: VK или K.
        Возвращает 'VK' или 'K'.
        """
        t = (text + " " + original).lower()

        # Признаки нижнего подключения (VK)
        lower_patterns = [
            r'\bнижн(?:ее|ем|им|ий|яя|его|\.)?\b',
            r'\bдонн(?:ое|ом|ым|ый|ая|ого|\.)?\b',
            r'\bventil\b',
            r'\buniversal\b',
            r'\bvalve\b',
            r'\bvk[-\s]?profil\b',
            r'\bprofil[-\s]?v\b',
            r'\bftv\b',
            r'\bfkv\b',
            r'\bvc\d{2}\b',
            r'\bcv\d{2}\b',
        ]

        # Признаки бокового подключения (K)
        side_patterns = [
            r'\bбоков(?:ое|ом|ым|ый|ая|ого|\.)?\b',
            r'\bclassic\b',
            r'\bcompact\b(?!.*ventil)',
            r'\bk[-\s]?profil\b',
            r'\bprofil[-\s]?k\b',
            r'\bfk0\b',
            r'\bfto\b',
            r'\bfko\b',
            r'\bc\d{2}\b',
        ]

        lower_score = 0
        side_score = 0

        for pat in lower_patterns:
            if re.search(pat, t):
                lower_score += 1

        for pat in side_patterns:
            if re.search(pat, t):
                side_score += 1

        # Если в тексте есть VK-Profil - это однозначно нижнее подключение
        if re.search(r'\bvk[-\s]?profil\b', t):
            return 'VK'
        
        # Если в тексте есть K-Profil - это однозначно боковое подключение
        if re.search(r'\bk[-\s]?profil\b', t):
            return 'K'

        if lower_score > side_score:
            return 'VK'
        elif side_score > lower_score:
            return 'K'
        else:
            # По умолчанию — K (боковое)
            return 'K'

    def _adjust_side_v2(self, connection: str, text: str, original: str) -> str:
        """Корректирует сторону подключения для VK-типов."""
        if connection == 'K-боковое':
            return connection

        side = self._determine_side(text, original)
        if side == 'left':
            return 'VK-левое'
        elif side == 'right':
            return 'VK-правое'

        # Если не удалось определить — для VK всегда правое по умолчанию
        return 'VK-правое'

    # ========================================================================
    # ПАРСЕРЫ
    # ========================================================================

    # ================================================================
    # НОВАЯ СТРАТЕГИЯ: УНИВЕРСАЛЬНЫЙ ПАРСЕР ДЛЯ РАДИАТОРОВ EVRA
    # ================================================================
    def _parse_evra_format(self, text: str, original: str = "") -> Optional[ParsedRadiator]:
        """
        УНИВЕРСАЛЬНЫЙ ПАРСЕР ДЛЯ РАДИАТОРОВ EVRA
        Распознаёт все форматы:
        - {type}CV-{height}-{length}[ L|L|]
        - {type}C-{height}-{length}[ L|L|]
        
        Где:
        - type: 10, 11, 20, 21, 22, 30, 33
        - height: 300, 400, 500, 600, 900
        - length: от 400 до 3000 с шагом 100
        - L или R в конце (опционально)
        """
        try:
            import re
            
            # Объединяем текст для поиска
            combined = (text + " " + original).strip()
            
            # ================================================================
            # ШАГ 1: ИЩЕМ ПАТТЕРН
            # ================================================================
            # Паттерн: тип + CV или C + высота + длина + опционально L/R
            # Примеры: 22CV-300-700 L, 33C-500-1000, 11CV-500-400L
            pattern = r'\b(\d{2})(CV|C)[\-](\d{3,4})[\-](\d{3,4})\s*([LR]?)\b'
            match = re.search(pattern, combined, re.IGNORECASE)
            
            if not match:
                return None
            
            # ================================================================
            # ШАГ 2: ИЗВЛЕКАЕМ ДАННЫЕ
            # ================================================================
            rad_type = match.group(1)        # 22, 33, 11, etc.
            connection_type = match.group(2).upper()  # CV или C
            height_str = match.group(3)      # 300, 500, etc.
            length_str = match.group(4)      # 700, 1100, etc.
            side = match.group(5).upper()    # L, R, или пусто
            
            # ================================================================
            # ШАГ 3: ПРОВЕРЯЕМ ВАЛИДНОСТЬ ТИПА
            # ================================================================
            if rad_type not in ['10', '11', '20', '21', '22', '30', '33']:
                # Тип 12 преобразуем в 21
                if rad_type == '12':
                    rad_type = '21'
                else:
                    return None
            
            # ================================================================
            # ШАГ 4: ПРОВЕРЯЕМ ВЫСОТУ
            # ================================================================
            try:
                height = int(height_str)
            except ValueError:
                return None
            
            # Допустимые высоты: 300, 400, 500, 600, 900
            if height not in [300, 400, 500, 600, 900]:
                # Пытаемся исправить через HEIGHT_MAPPING
                if height in self.HEIGHT_MAPPING:
                    height = self.HEIGHT_MAPPING[height]
                else:
                    return None
            
            # ================================================================
            # ШАГ 5: ПРОВЕРЯЕМ ДЛИНУ
            # ================================================================
            try:
                length = int(length_str)
            except ValueError:
                return None
            
            # Допустимые длины: от 400 до 3000 с шагом 100
            if length < 400 or length > 3000 or length % 100 != 0:
                # Пытаемся округлить
                rounded = round(length / 100) * 100
                if 400 <= rounded <= 3000:
                    length = rounded
                else:
                    return None
            
            # ================================================================
            # ШАГ 6: ОПРЕДЕЛЯЕМ ПОДКЛЮЧЕНИЕ
            # ================================================================
            
            # Базовое подключение: CV = VK (нижнее), C = K (боковое)
            if connection_type == 'CV':
                base_connection = "VK"
            else:  # 'C'
                base_connection = "K"
            
            # Универсальные типы (20, 21, 22) — всегда VK-правое
            # У них нет левого исполнения, игнорируем L/R
            if rad_type in ['20', '21', '22']:
                if base_connection == "VK":
                    final_connection = "VK-правое"
                else:
                    # Для типа 22 с C (боковое) — оставляем K-боковое
                    final_connection = "K-боковое"
            else:
                # Направленные типы (10, 11, 30, 33)
                if base_connection == "VK":
                    # VK-нижнее: L → левое, R или пусто → правое
                    if side == 'L':
                        final_connection = "VK-левое"
                    else:
                        final_connection = "VK-правое"
                else:
                    # K-боковое: всегда K-боковое (левого/правого нет)
                    final_connection = "K-боковое"
            
            # ================================================================
            # ШАГ 7: СОЗДАЁМ РЕЗУЛЬТАТ
            # ================================================================
            result = ParsedRadiator()
            result.recognized = True
            result.connection = final_connection
            result.rad_type = rad_type
            result.height = height
            result.length = length
            result.confidence = 0.98
            result.source = "evra_format"
            result.brand = "evra"
            
            return result
            
        except Exception as e:
            self._log(f"EVRA format parser error: {e}", "ERROR")
            return None

    def _parse_oasis(self, text: str, original: str = "") -> Optional[ParsedRadiator]:
        """Парсинг Oasis: PN 22-4-05, PB 22-5-04, OC-11-5-04"""
        try:
            normalized = re.sub(
                r'\b(pn|pb|oc|ov|рn|рb)\s*[-–]\s*',
                r'\1 ', text, flags=re.IGNORECASE
            )
            pattern = r'\b(pn|pb|oc|ov|рn|рb)\s+(\d{1,2})\s*[\-\s]\s*(\d{1,2})\s*[\-\s]\s*(\d{1,2})\b'
            match = re.search(pattern, normalized, re.IGNORECASE)
            if not match:
                return None

            prefix = match.group(1).lower()
            rad_type = match.group(2)
            height_code = match.group(3)
            length_code = match.group(4)

            if rad_type not in self.VALID_TYPES:
                return None

            connection = self.OASIS_CONNECTION_MAP.get(prefix, 'VK-правое')

            height_map = {
                '3': 300, '4': 400, '5': 500, '6': 600, '9': 900,
                '03': 300, '04': 400, '05': 500, '06': 600, '09': 900,
            }
            height = height_map.get(height_code)
            if not height:
                return None

            length = int(length_code) * 100
            if length < 400 or length > 3000:
                return None
            if length not in self.VALID_LENGTHS:
                rounded = round(length / 100) * 100
                if 400 <= rounded <= 3000:
                    length = rounded
                else:
                    return None

            result = ParsedRadiator()
            result.recognized = True
            result.connection = connection
            result.rad_type = rad_type
            result.height = height
            result.length = length
            result.confidence = 0.95
            result.source = "oasis"
            result.brand = "oasis"
            return result
        except Exception as e:
            self._log(f"Oasis parser error: {e}", "ERROR")
            return None

    def _parse_coded_triplet(self, text: str, original: str = "") -> Optional[ParsedRadiator]:
        """
        УНИВЕРСАЛЬНЫЙ парсинг кодированных форматов.
        Ищет три числа через дефис, слеш или пробел в ЛЮБОМ окружении.
        Формат: тип-код_высоты-код_длины (например, 11-03-18, 22/04/12, 33 05 20)
        
        Код высоты: 03=300, 04=400, 05=500, 06=600, 09=900
        Код длины: 04=400, 05=500, 06=600, ... 12=1200, ... 30=3000
        """
        try:
            # Объединяем очищенный текст и оригинал
            combined = (text + " " + original).lower()
            
            # Ищем три числа через разделители (дефис, слеш, пробел, x, х)
            # ВАЖНО: числа могут быть 2 или 3-4 цифры, но мы проверим позже
            sep = r'[-/xх\s]+'
            pattern = r'(?<!\d)(\d{2,4})\s*' + sep + r'\s*(\d{1,4})\s*' + sep + r'\s*(\d{1,4})(?!\d)'
            match = re.search(pattern, combined)
            if not match:
                return None
            
            first_num = match.group(1)   # тип или что-то другое
            second_num = match.group(2)  # высота (код или мм)
            third_num = match.group(3)   # длина (код или мм)
            
            # ================================================================
            # ШАГ 1: Определяем, что у нас КОДИРОВАННЫЙ формат
            # Признаки: первое число = тип (10-33), 
            # второе число <= 9 или 02-09 (код высоты),
            # третье число <= 30 (код длины)
            # ================================================================
            
            # Первое число должно быть типом (10-33)
            try:
                type_val = int(first_num)
                if type_val < 10 or type_val > 33:
                    return None
                rad_type = str(type_val)
                if rad_type not in self.VALID_TYPES:
                    # 12 преобразуем в 21?
                    if rad_type == '12':
                        rad_type = '21'
                    else:
                        return None
            except ValueError:
                return None
            
            # Второе число: должно быть кодом высоты (1-9 или 01-09)
            try:
                height_code_val = int(second_num)
                # Код высоты может быть 1-9 (3=300,4=400) или 2-значный 02-09
                if height_code_val < 1 or height_code_val > 9:
                    # Может быть 10? 10=1000мм? Но это уже не код, а мм
                    # Если число 200-900 — это прямые мм, а не код
                    if 200 <= height_code_val <= 900:
                        # Это прямые мм, значит не наш формат
                        return None
                    return None
                height_code = second_num.zfill(2)  # 3 -> "03"
            except ValueError:
                return None
            
            # Третье число: должно быть кодом длины (4-30)
            try:
                length_code_val = int(third_num)
                if length_code_val < 4 or length_code_val > 30:
                    return None
                length_code = third_num
            except ValueError:
                return None
            
            # ================================================================
            # ШАГ 2: Преобразуем коды в реальные значения
            # ================================================================
            
            # Высота: код 03=300, 04=400, 05=500, 06=600, 09=900
            height_map = {
                '03': 300, '3': 300,
                '04': 400, '4': 400,
                '05': 500, '5': 500,
                '06': 600, '6': 600,
                '09': 900, '9': 900,
            }
            height = height_map.get(height_code)
            if not height:
                # Пробуем умножить на 100 (3->300)
                try:
                    h_int = int(height_code)
                    if h_int in [3, 4, 5, 6, 9]:
                        height = h_int * 100
                    else:
                        return None
                except ValueError:
                    return None
            
            # Длина: код 04=400, 05=500, 12=1200, 18=1800, 30=3000
            try:
                length = int(length_code) * 100
            except ValueError:
                return None
            
            # Проверяем валидность длины
            if length < 400 or length > 3000:
                return None
            if length not in self.VALID_LENGTHS:
                rounded = round(length / 100) * 100
                if 400 <= rounded <= 3000:
                    length = rounded
                else:
                    return None
            
            # ================================================================
            # ШАГ 3: Определяем подключение по контексту
            # ================================================================
            
            # Ищем в оригинальном тексте указания на подключение
            combined_lower = combined
            
            # Сначала проверяем явные индикаторы VK и K профилей
            # VK-Profil — однозначно нижнее подключение
            if re.search(r'\bvk[-\s]?profil\b', combined_lower):
                connection = 'VK-правое'
            # K-Profil — однозначно боковое подключение
            elif re.search(r'\bk[-\s]?profil\b', combined_lower):
                connection = 'K-боковое'
            else:
                # Признаки нижнего подключения (VK)
                vk_indicators = [
                    r'vk', r'vк', r'вк', r'нижн', r'донн', 
                    r'ventil', r'universal', r'valve'
                ]
                # Признаки бокового подключения (K)
                k_indicators = [
                    r'k[-\s]?profil', r'kprofil', r'боков', 
                    r'classic', r'compact', r'hygiene'
                ]
                
                is_vk = any(re.search(ind, combined_lower) for ind in vk_indicators)
                is_k = any(re.search(ind, combined_lower) for ind in k_indicators)
                
                if is_vk and not is_k:
                    connection = 'VK-правое'
                elif is_k and not is_vk:
                    connection = 'K-боковое'
                else:
                    # По умолчанию — K-боковое
                    connection = 'K-боковое'
            
            # Корректируем сторону (левое/правое)
            connection = self._adjust_side_v2(connection, text, original)
            
            # ================================================================
            # ШАГ 4: Создаём результат
            # ================================================================
            
            result = ParsedRadiator()
            result.recognized = True
            result.connection = connection
            result.rad_type = rad_type
            result.height = height
            result.length = length
            result.confidence = 0.95
            result.source = "coded_triplet"
            result.brand = self._extract_brand(original)
            return result
            
        except Exception as e:
            self._log(f"Coded triplet parser error: {e}", "ERROR")
            return None
    
    def _extract_brand(self, original: str) -> str:
        """Извлекает название бренда из оригинального названия."""
        original_lower = original.lower()
        for brand in self.KNOWN_BRANDS:
            if brand in original_lower:
                return brand
        return ""

    def _parse_lidea(self, text: str, original: str = "") -> Optional[ParsedRadiator]:
        """Парсинг Лидеи: ЛК 11-504, ЛУ 33-516, ЛУ 22-05-12"""
        try:
            # Формат 1: ЛК 11-504, ЛУ 33-516 (тип-код)
            pattern1 = r'(л[кkуy])\s*(\d{2})[\-\s]*(\d{3,5})'
            match = re.search(pattern1, text, re.IGNORECASE)
            if match:
                conn_code = match.group(1).lower()
                rad_type = match.group(2)
                raw_code = match.group(3)

                code_digits = re.sub(r'\D', '', raw_code)
                if not code_digits:
                    return None

                if len(code_digits) >= 4:
                    first_digit = int(code_digits[0])
                    last_digits = int(code_digits[1:])
                elif len(code_digits) == 3:
                    first_digit = int(code_digits[0])
                    last_digits = int(code_digits[1:])
                else:
                    return None

                height_map = {3: 300, 4: 400, 5: 500, 6: 600, 9: 900}
                height = height_map.get(first_digit)
                if not height:
                    return None

                length = last_digits * 100
                if length > 3000 and len(code_digits) >= 2:
                    length = int(code_digits[-2:]) * 100

                if not (400 <= length <= 3000):
                    return None

                connection = 'K-боковое' if conn_code in ['лк', 'lk'] else 'VK-правое'

                result = ParsedRadiator()
                result.recognized = True
                result.connection = connection
                result.rad_type = rad_type
                result.height = height
                result.length = length
                result.confidence = 0.85
                result.source = "lidea"
                result.brand = "lidea"
                return result

            # Формат 2: ЛУ 22-05-12, ЛК 11-05-08 (тип-код_высоты-код_длины)
            pattern2 = r'(л[кkуy])\s*(\d{2})\s*[\-\s]\s*(\d{1,2})\s*[\-\s]\s*(\d{1,2})\b'
            match = re.search(pattern2, text, re.IGNORECASE)
            if match:
                conn_code = match.group(1).lower()
                rad_type = match.group(2)
                height_code = match.group(3)
                length_code = match.group(4)

                if rad_type not in self.VALID_TYPES:
                    return None

                # Код высоты: 05 -> 500, 3 -> 300
                height_map = {
                    '3': 300, '4': 400, '5': 500, '6': 600, '9': 900,
                    '03': 300, '04': 400, '05': 500, '06': 600, '09': 900,
                }
                height = height_map.get(height_code)
                if not height:
                    try:
                        h = int(height_code) * 100
                        if h in self.VALID_HEIGHTS:
                            height = h
                        else:
                            return None
                    except ValueError:
                        return None

                # Код длины: 04 -> 400, 12 -> 1200
                try:
                    length_code_int = int(length_code)
                    if length_code_int < 40:
                        length = length_code_int * 100
                    else:
                        length = length_code_int
                except ValueError:
                    return None

                if length < 400 or length > 3000:
                    return None
                if length not in self.VALID_LENGTHS:
                    rounded = round(length / 100) * 100
                    if 400 <= rounded <= 3000:
                        length = rounded
                    else:
                        return None

                connection = 'K-боковое' if conn_code in ['лк', 'lk'] else 'VK-правое'

                result = ParsedRadiator()
                result.recognized = True
                result.connection = connection
                result.rad_type = rad_type
                result.height = height
                result.length = length
                result.confidence = 0.90
                result.source = "lidea_v2"
                result.brand = "lidea"
                return result

            return None
        except Exception as e:
            self._log(f"Lidea parser error: {e}", "ERROR")
            return None
            
    def _parse_evra(self, text: str, original: str = "") -> Optional[ParsedRadiator]:
        """Парсинг EVRA: C11-300-500, CV22-300-400, H10-30-400"""
        try:
            patterns = [
                r'\b(?:evra\s+)?(c\d{2}s?|cv\d{2}|h\d{2})\s*[\-\s]\s*(\d{1,4})\s*[\-\s]\s*(\d{3,4})\b',
                r'\b(c\d{2}s?|cv\d{2})\s+(\d{3,4})\s*[\-xх]\s*(\d{3,4})\b',
            ]
            for pattern in patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    evra_type = match.group(1).lower()
                    raw_h = match.group(2)
                    raw_l = match.group(3)

                    if evra_type not in self.EVRA_TYPE_MAP:
                        return None
                    rad_type = self.EVRA_TYPE_MAP[evra_type]

                    height = int(raw_h)
                    length = int(raw_l)

                    if evra_type.startswith('h') and height < 100:
                        height = height * 10

                    if height not in self.VALID_HEIGHTS:
                        if height in self.HEIGHT_MAPPING:
                            height = self.HEIGHT_MAPPING[height]
                        else:
                            continue

                    if length not in self.VALID_LENGTHS:
                        rounded = round(length / 100) * 100
                        if 400 <= rounded <= 3000:
                            length = rounded
                        else:
                            continue

                    connection = 'VK-правое' if evra_type.startswith('cv') else 'K-боковое'

                    result = ParsedRadiator()
                    result.recognized = True
                    result.connection = connection
                    result.rad_type = rad_type
                    result.height = height
                    result.length = length
                    result.confidence = 0.90
                    result.source = "evra"
                    result.brand = "evra"
                    return result
            return None
        except Exception as e:
            self._log(f"Evra parser error: {e}", "ERROR")
            return None

    def _parse_rostorm(self, text: str, original: str = "") -> Optional[ParsedRadiator]:
        """Парсинг РОСТерм: 11KV 500-800, 22K 500-2400"""
        try:
            pattern = r'\b(\d{2})\s*kv?\s+(\d{3,4})\s*[\-\s]\s*(\d{3,4})\b'
            match = re.search(pattern, text, re.IGNORECASE)
            if not match:
                return None

            rad_type = match.group(1)
            height = int(match.group(2))
            length = int(match.group(3))

            if rad_type not in self.VALID_TYPES:
                return None

            if height not in self.VALID_HEIGHTS:
                if height in self.HEIGHT_MAPPING:
                    height = self.HEIGHT_MAPPING[height]
                else:
                    return None

            if length not in self.VALID_LENGTHS:
                rounded = round(length / 100) * 100
                if 400 <= rounded <= 3000:
                    length = rounded
                else:
                    return None

            connection = 'VK-правое' if 'kv' in match.group(0).lower() else 'K-боковое'
            connection = self._adjust_side_v2(connection, text, original)

            result = ParsedRadiator()
            result.recognized = True
            result.connection = connection
            result.rad_type = rad_type
            result.height = height
            result.length = length
            result.confidence = 0.85
            result.source = "rostorm"
            result.brand = "ростерм"
            return result
        except Exception as e:
            self._log(f"Rostorm parser error: {e}", "ERROR")
            return None

    def _parse_kermi(self, text: str, original: str = "") -> Optional[ParsedRadiator]:
        """Парсинг Kermi: FTV 11 500/1200, FK0 22 500/1000"""
        try:
            patterns = [
                r'(?:ftv|fkv|fk0|fto|fko)\s+(\d{2})\s+(\d{3,4})\s*[/\-\s]\s*(\d{3,4})',
                r'(?:kermi|kermy).*?(\d{2})\s*[xх\-\s]\s*(\d{3,4})\s*[xх\-\s]\s*(\d{3,4})',
                r'profil-v\s+(\d{2})\s+(\d{3,4})\s+(\d{3,4})',
                r'profil-k\s+(\d{2})\s+(\d{3,4})\s+(\d{3,4})',
            ]
            for pattern in patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    rad_type = match.group(1)
                    height = int(match.group(2))
                    length = int(match.group(3))

                    if rad_type not in self.VALID_TYPES:
                        if rad_type == '12':
                            rad_type = '21'
                        else:
                            continue

                    if height not in self.VALID_HEIGHTS:
                        if height in self.HEIGHT_MAPPING:
                            height = self.HEIGHT_MAPPING[height]
                        else:
                            continue

                    if length not in self.VALID_LENGTHS:
                        rounded = round(length / 100) * 100
                        if 400 <= rounded <= 3000:
                            length = rounded
                        else:
                            continue

                    if 'profil-v' in text or 'ftv' in text or 'fkv' in text:
                        connection = 'VK-правое'
                    elif 'profil-k' in text or 'fk0' in text or 'fto' in text or 'fko' in text:
                        connection = 'K-боковое'
                    else:
                        connection = 'K-боковое'

                    connection = self._adjust_side_v2(connection, text, original)

                    result = ParsedRadiator()
                    result.recognized = True
                    result.connection = connection
                    result.rad_type = rad_type
                    result.height = height
                    result.length = length
                    result.confidence = 0.92
                    result.source = "kermi"
                    result.brand = "kermi"
                    return result
            return None
        except Exception as e:
            self._log(f"Kermi parser error: {e}", "ERROR")
            return None

    def _parse_arbonia_ftv(self, text: str, original: str = "") -> Optional[ParsedRadiator]:
        """
        Парсинг Arbonia FTV: 
        Стальной панельный радиатор Arbonia FTV тип 12, 300x64x400 мм, вентиль слева/справа
        """
        try:
            # Проверяем, что это Arbonia FTV
            combined = (text + " " + original).lower()
            
            if 'arbonia' not in combined:
                return None
            if 'ftv' not in combined:
                return None
            
            # Ищем тип радиатора: "тип 12", "тип 22" и т.д.
            type_match = re.search(r'тип\s*(\d{2})', combined)
            if not type_match:
                return None
            
            rad_type = type_match.group(1)
            
            # Тип 12 преобразуем в 21 (в LaggarTT нет типа 12)
            if rad_type == '12':
                rad_type = '21'
            elif rad_type not in self.VALID_TYPES:
                return None
            
            # Ищем размеры: "300x64x400" или "300x64x400 мм"
            size_match = re.search(r'(\d{3,4})x\d{2,3}x(\d{3,4})', combined)
            if not size_match:
                # Альтернативный формат с пробелами
                size_match = re.search(r'(\d{3,4})\s*[xх]\s*\d{2,3}\s*[xх]\s*(\d{3,4})', combined)
            
            if not size_match:
                return None
            
            height = int(size_match.group(1))
            length = int(size_match.group(2))
            
            # Проверяем валидность высоты
            if height not in self.VALID_HEIGHTS:
                if height in self.HEIGHT_MAPPING:
                    height = self.HEIGHT_MAPPING[height]
                else:
                    return None
            
            # Проверяем валидность длины
            if length not in self.VALID_LENGTHS:
                rounded = round(length / 100) * 100
                if 400 <= rounded <= 3000:
                    length = rounded
                else:
                    return None
            
            # Определяем сторону подключения
            if 'вентиль слева' in combined:
                connection = 'VK-левое'
            elif 'вентиль справа' in combined:
                connection = 'VK-правое'
            else:
                connection = 'VK-правое'  # по умолчанию
            
            result = ParsedRadiator()
            result.recognized = True
            result.connection = connection
            result.rad_type = rad_type
            result.height = height
            result.length = length
            result.confidence = 0.92
            result.source = "arbonia_ftv"
            result.brand = "arbonia"
            return result
            
        except Exception as e:
            self._log(f"Arbonia FTV parser error: {e}", "ERROR")
            return None

    def _parse_laggar_format(self, text: str, original: str) -> Optional[ParsedRadiator]:
        """Парсинг LaggarTT: VK-Profil 33/400/400 ra, VK 22/300/1200 ra"""
        try:
            pattern = r'(vk|k)[\s\-]profil\s+(\d{2})\s*[-/\s]\s*(\d{3,4})\s*[-/\s]\s*(\d{3,4})'
            match = re.search(pattern, text, re.IGNORECASE)
            if not match:
                pattern2 = r'\b(vk|k)\s*[-/]?\s*(\d{2})\s*[-/\s]\s*(\d{3,4})\s*[-/\s]\s*(\d{3,4})'
                match = re.search(pattern2, text, re.IGNORECASE)

            if not match:
                return None

            prefix = match.group(1).lower()
            rad_type = match.group(2)
            height = int(match.group(3))
            length = int(match.group(4))

            if rad_type not in self.VALID_TYPES:
                return None

            if height not in self.VALID_HEIGHTS:
                if height in self.HEIGHT_MAPPING:
                    height = self.HEIGHT_MAPPING[height]
                else:
                    return None

            if length not in self.VALID_LENGTHS:
                rounded = round(length / 100) * 100
                if 400 <= rounded <= 3000:
                    length = rounded
                else:
                    return None

            connection = 'VK-правое' if prefix == 'vk' else 'K-боковое'
            connection = self._adjust_side_v2(connection, text, original)

            result = ParsedRadiator()
            result.recognized = True
            result.connection = connection
            result.rad_type = rad_type
            result.height = height
            result.length = length
            result.confidence = 0.95
            result.source = "laggar_format"
            return result
        except Exception as e:
            self._log(f"Laggar parser error: {e}", "ERROR")
            return None

    def _parse_compact_with_prefix(self, text: str, original: str) -> Optional[ParsedRadiator]:
        """Парсинг: C22-500-800, VC11-300-1100 R, 22KV 400-1000"""
        try:
            pattern = r'\b([ckv]{1,3})\s*(\d{2})\s*[-/\s]\s*(\d{3,4})\s*[-/\s]\s*(\d{3,4})'
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                prefix = match.group(1).lower()
                rad_type = match.group(2)
                height = int(match.group(3))
                length = int(match.group(4))
            else:
                pattern2 = r'(\d{2})(kv)\s+(\d{3,4})\s*[-/\s]\s*(\d{3,4})'
                match = re.search(pattern2, text, re.IGNORECASE)
                if match:
                    prefix = match.group(2).lower()
                    rad_type = match.group(1)
                    height = int(match.group(3))
                    length = int(match.group(4))
                else:
                    return None

            if rad_type not in self.VALID_TYPES:
                return None

            if height not in self.VALID_HEIGHTS:
                if height in self.HEIGHT_MAPPING:
                    height = self.HEIGHT_MAPPING[height]
                else:
                    return None

            if length not in self.VALID_LENGTHS:
                rounded = round(length / 100) * 100
                if 400 <= rounded <= 3000:
                    length = rounded
                else:
                    return None

            connection = 'K-боковое'
            if prefix in ['v', 'vc', 'cv', 'kv']:
                connection = 'VK-правое'
            elif prefix in ['k', 'c']:
                connection = 'K-боковое'

            connection = self._adjust_side_v2(connection, text, original)

            result = ParsedRadiator()
            result.recognized = True
            result.connection = connection
            result.rad_type = rad_type
            result.height = height
            result.length = length
            result.confidence = 0.90
            result.source = "compact_with_prefix"
            return result
        except Exception as e:
            self._log(f"Compact prefix parser error: {e}", "ERROR")
            return None

    def _parse_text_with_type(self, text: str, original: str = "") -> Optional[ParsedRadiator]:
        """Парсинг: нижнее подключение 33-5-09, тип 22, высота 400, длина 1000"""
        try:
            text_lower = text.lower()

            # нижнее подключение 33-5-09
            pattern1 = r'(нижнее|нижнем|нижним|боковое|боковом|боковым|донное)\s+подключени(?:е|я|ю|ем|и|й)?[\-\s]*(\d{2})\s*[\-\s]\s*(\d{1,2})\s*[\-\s]\s*(\d{1,2})\b'
            match = re.search(pattern1, text_lower)
            if match:
                conn_type = match.group(1)
                rad_type = match.group(2)
                height_code = int(match.group(3))
                length_code = int(match.group(4))

                if rad_type not in self.VALID_TYPES:
                    return None

                height = height_code * 100 if height_code < 10 else height_code
                length = length_code * 100 if length_code < 10 else length_code

                if height not in self.VALID_HEIGHTS:
                    if height in self.HEIGHT_MAPPING:
                        height = self.HEIGHT_MAPPING[height]
                    else:
                        return None

                if length not in self.VALID_LENGTHS:
                    rounded = round(length / 100) * 100
                    if 400 <= rounded <= 3000:
                        length = rounded
                    else:
                        return None

                connection = 'VK-правое' if conn_type.startswith('нижн') or conn_type.startswith('донн') else 'K-боковое'
                connection = self._adjust_side_v2(connection, text, original)

                result = ParsedRadiator()
                result.recognized = True
                result.connection = connection
                result.rad_type = rad_type
                result.height = height
                result.length = length
                result.confidence = 0.80
                result.source = "text_with_type"
                return result

            # тип 22, высота 400, длина 1000
            pattern2 = r'тип\s*(\d{2}).*?высот[аой]*\s*(\d{3,4}).*?длин[аой]*\s*(\d{3,4})'
            match = re.search(pattern2, text_lower)
            if match:
                rad_type = match.group(1)
                height = int(match.group(2))
                length = int(match.group(3))

                if rad_type not in self.VALID_TYPES:
                    return None

                if height not in self.VALID_HEIGHTS:
                    if height in self.HEIGHT_MAPPING:
                        height = self.HEIGHT_MAPPING[height]
                    else:
                        return None

                if length not in self.VALID_LENGTHS:
                    rounded = round(length / 100) * 100
                    if 400 <= rounded <= 3000:
                        length = rounded
                    else:
                        return None

                conn_type = self._determine_connection_type(text, original)
                connection = 'VK-правое' if conn_type == 'VK' else 'K-боковое'
                connection = self._adjust_side_v2(connection, text, original)

                result = ParsedRadiator()
                result.recognized = True
                result.connection = connection
                result.rad_type = rad_type
                result.height = height
                result.length = length
                result.confidence = 0.75
                result.source = "text_with_type"
                return result

            return None
        except Exception as e:
            self._log(f"Text with type parser error: {e}", "ERROR")
            return None

    def _parse_universal_triplet(self, text: str, original: str = "") -> Optional[ParsedRadiator]:
        """
        УНИВЕРСАЛЬНАЯ СТРАТЕГИЯ: находит три числа (тип-высота-длина) в тексте,
        затем в оставшихся словах ищет подключение и сторону.
        Всеядная — не зависит от порядка слов.
        """
        try:
            # Объединяем очищенный текст и оригинал для поиска
            combined = (text + " " + original).lower()
            
            # Шаг 1: Ищем триплет (тип-высота-длина)
            sep = r'[-/xх\s]+'
            pattern = r'(?<!\d)(\d{2})\s*' + sep + r'\s*(\d{3,4})\s*' + sep + r'\s*(\d{3,4})(?!\d)'
            match = re.search(pattern, combined)
            if not match:
                return None
            
            rad_type = match.group(1)
            height = int(match.group(2))
            length = int(match.group(3))
            
            # Проверяем валидность типа
            if rad_type not in self.VALID_TYPES:
                return None
            
            # Проверяем валидность высоты
            if height not in self.VALID_HEIGHTS:
                if height in self.HEIGHT_MAPPING:
                    height = self.HEIGHT_MAPPING[height]
                else:
                    return None
            
            # Проверяем валидность длины
            if not (400 <= length <= 3000):
                return None
            if length not in self.VALID_LENGTHS:
                rounded = round(length / 100) * 100
                if 400 <= rounded <= 3000:
                    length = rounded
                else:
                    return None
            
            # Шаг 2: Убираем найденные числа из текста
            remaining = combined[:match.start()] + " " + combined[match.end():]
            
            # Шаг 3: Определяем тип подключения по оставшимся словам
            connection = self._detect_connection_from_text(remaining, combined)
            
            # Шаг 4: Определяем сторону
            connection = self._adjust_side_v2(connection, remaining, combined)
            
            # Шаг 5: Угадываем бренд
            brand = ""
            for known_brand in self.KNOWN_BRANDS:
                if known_brand in combined:
                    brand = known_brand
                    break
            
            result = ParsedRadiator()
            result.recognized = True
            result.connection = connection
            result.rad_type = rad_type
            result.height = height
            result.length = length
            result.confidence = 0.85
            result.source = "universal_triplet"
            result.brand = brand
            return result
            
        except Exception as e:
            self._log(f"Universal triplet parser error: {e}", "ERROR")
            return None
    
    def _detect_connection_from_text(self, text: str, full_text: str) -> str:
        """
        Определяет тип подключения (VK-правое, VK-левое, K-боковое) 
        по ключевым словам в тексте.
        """
        text_lower = text.lower()
        
        # ================================================================
        # ПРИЗНАКИ НИЖНЕГО подключения (VK)
        # ================================================================
        lower_patterns = [
            # Русские слова
            r'\bнижн(?:ее|ем|им|ий|яя|его|\.)?\b',
            r'\bдонн(?:ое|ом|ым|ый|ая|ого|\.)?\b',
            r'\bнижнее\s+подключение\b',
            r'\bнижним\s+подключением\b',
            r'\bнижнее\s+правое\b',
            r'\bнижнее\s+левое\b',
            r'\bниж\.\s*правое\b',
            r'\bниж\.\s*левое\b',
            r'\bдонное\s+подключение\b',
            r'\bдонным\s+подключением\b',
            r'\bн\.\s*п\.?\b',
            r'\bн\.\s*правое\b',
            r'\bн\.\s*левое\b',
            
            # Английские / брендовые
            r'\bventil\b',
            r'\bventil\s+compact\b',
            r'\buniversal\b',
            r'\bуниверсальное\s+подключение\b',
            r'\bуниверсальный\b',
            r'\bvalve\b',
            r'\bvk[-\s]?profil\b',
            r'\bvk[_\s]?profil\b',
            r'\bvkprofil\b',
            r'\bprofil[-\s]?v\b',
            r'\bprofil\s+v\b',
            r'\bftv\b',
            r'\bfkv\b',
            r'\bvc\d{2}\b',
            r'\bcv\d{2}\b',
            r'\bpn\b',
            r'\bov\b',
            r'\bрn\b',
            r'\bvh\b',
            r'\bsoftline\b',
            r'\brvp\b',
            r'\bfv\b',
            r'\bvkn\b',
            r'\bvc\s',
            r'\bcv\s',
            r'\bнижнее\b',
            r'\bнижнем\b',
            r'\bнижним\b',
            
            #   Суффиксы с L/R для нижнего подключения
            r'\bcvl\b',   # CVL = CV + Left (нижнее левое)
            r'\bcvr\b',   # CVR = CV + Right (нижнее правое)
            r'\bvcl\b',   # VCL = VC + Left (нижнее левое)
            r'\bvcr\b',   # VCR = VC + Right (нижнее правое)
        ]
        
        # ================================================================
        # ПРИЗНАКИ БОКОВОГО подключения (K)
        # ================================================================
        side_patterns = [
            # Русские слова
            r'\bбоков(?:ое|ом|ым|ый|ая|ого|\.)?\b',
            r'\bбоковое\s+подключение\b',
            r'\bбоковым\s+подключением\b',
            r'\bбоков\.\b',
            
            # Английские / брендовые
            r'\bclassic\b',
            r'\bcompact\b(?!.*ventil)',
            r'\bk[-\s]?profil\b',
            r'\bk[_\s]?profil\b',
            r'\bkprofil\b',
            r'\bprofil[-\s]?k\b',
            r'\bprofil\s+k\b',
            r'\bfk0\b',
            r'\bfto\b',
            r'\bfko\b',
            r'\bc\d{2}\b',
            r'\bpb\b',
            r'\boc\b',
            r'\bрb\b',
            r'\bhygiene\b',
            r'\brkp\b',
            r'\bfk\b',
            r'\bkn\b',
            r'\bc\s',
            r'\bбоковое\b',
            r'\bбоковым\b',
            r'\bбоковом\b',
            
            #   Суффиксы с L/R для бокового подключения
            r'\bcl\b',    # CL = C + Left (боковое левое)
            r'\bcr\b',    # CR = C + Right (боковое правое)
        ]
        
        lower_score = 0
        side_score = 0
        
        for pat in lower_patterns:
            if re.search(pat, text_lower):
                lower_score += 1
        
        for pat in side_patterns:
            if re.search(pat, text_lower):
                side_score += 1
        
        if lower_score > side_score:
            return 'VK-правое'
        elif side_score > lower_score:
            return 'K-боковое'
        else:
            return 'K-боковое'
            
    def _parse_compact_triplet(self, text: str, original: str = "") -> Optional[ParsedRadiator]:
        """Парсинг: 22-400-1000, 11/400/500, 33 x 600 x 700"""
        try:
            sep = r'[-/xх\s]+'
            pattern = r'(?<!\d)(\d{2})\s*' + sep + r'\s*(\d{3,4})\s*' + sep + r'\s*(\d{3,4})(?!\d)'
            match = re.search(pattern, text)
            if not match:
                return None

            rad_type = match.group(1)
            height = int(match.group(2))
            length = int(match.group(3))

            if rad_type not in self.VALID_TYPES:
                return None

            if height not in self.VALID_HEIGHTS:
                if height in self.HEIGHT_MAPPING:
                    height = self.HEIGHT_MAPPING[height]
                else:
                    return None

            if not (400 <= length <= 3000):
                rounded = round(length / 100) * 100
                if 400 <= rounded <= 3000:
                    length = rounded
                else:
                    return None

            # Определение подключения по контексту
            conn_type = self._determine_connection_type(text, original)
            connection = 'VK-правое' if conn_type == 'VK' else 'K-боковое'
            connection = self._adjust_side_v2(connection, text, original)

            result = ParsedRadiator()
            result.recognized = True
            result.connection = connection
            result.rad_type = rad_type
            result.height = height
            result.length = length
            result.confidence = 0.85
            result.source = "compact_triplet"
            return result
        except Exception as e:
            self._log(f"Compact triplet parser error: {e}", "ERROR")
            return None

    def _parse_height_length_only(self, text: str, original: str = "") -> Optional[ParsedRadiator]:
        """Запасной парсер: высота x длина."""
        try:
            search_text = (original or text).lower()

            patterns = [
                r'(\d{3,4})\s*[xх]\s*(\d{3,4})',
                r'высот[аой]*\s*(\d{3,4}).*?длин[аой]*\s*(\d{3,4})',
                r'h\s*[=:]\s*(\d{3,4}).*?l\s*[=:]\s*(\d{3,4})',
            ]
            for pat in patterns:
                match = re.search(pat, search_text, re.IGNORECASE)
                if match:
                    try:
                        h1, h2 = int(match.group(1)), int(match.group(2))

                        if h1 in self.VALID_HEIGHTS or h1 in self.HEIGHT_MAPPING:
                            height, length = h1, h2
                        elif h2 in self.VALID_HEIGHTS or h2 in self.HEIGHT_MAPPING:
                            height, length = h2, h1
                        else:
                            height, length = (h1, h2) if h1 < h2 else (h2, h1)

                        if height in self.HEIGHT_MAPPING:
                            height = self.HEIGHT_MAPPING[height]
                        if height not in self.VALID_HEIGHTS:
                            continue
                        if length < 400 or length > 3000:
                            continue

                        rad_type = self._guess_type_from_context(search_text)
                        conn_type = self._determine_connection_type(text, original)
                        connection = 'VK-правое' if conn_type == 'VK' else 'K-боковое'
                        connection = self._adjust_side_v2(connection, text, original)

                        result = ParsedRadiator()
                        result.recognized = True
                        result.connection = connection
                        result.rad_type = rad_type
                        result.height = height
                        result.length = length
                        result.confidence = 0.65
                        result.source = "universal_2d"
                        return result
                    except (ValueError, IndexError):
                        continue
            return None
        except Exception as e:
            self._log(f"Height-length parser error: {e}", "ERROR")
            return None

    # ========================================================================
    # СТРАТЕГИИ ИЗ ШАБЛОНОВ (МИГРИРОВАНЫ ИЗ templates.json)
    # ========================================================================

    def _parse_template_001(self, text: str, original: str = "") -> Optional[ParsedRadiator]:
        """
        Шаблон: PB {type}-{height}-{length}
        Оригинал: PB 22-40-400
        Connection: K-боковое
        height_transform: code * 10 (40 → 400)
        length_transform: direct (400 → 400)
        """
        pattern = r'\bPB\ (\d+)-(\d+)-([\d,]+)(?:\s|$|[,.;:!?])'
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            return None
        
        type_str = match.group(1)
        height = int(match.group(2)) * 10  # code * 10
        length = int(match.group(3))       # direct
        
        return self._create_parsed_result(
            type_str=type_str,
            height=height,
            length=length,
            connection="K-боковое",
            source="template_001",
            confidence=0.95
        )

    def _parse_template_002(self, text: str, original: str = "") -> Optional[ParsedRadiator]:
        """
        Шаблон: PN {type}-{height}-{length}
        Оригинал: PN 22-40-400
        Connection: VK-правое
        height_transform: code * 10 (40 → 400)
        length_transform: direct (400 → 400)
        """
        pattern = r'\bPN\ (\d+)-(\d+)-([\d,]+)(?:\s|$|[,.;:!?])'
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            return None
        
        type_str = match.group(1)
        height = int(match.group(2)) * 10  # code * 10
        length = int(match.group(3))       # direct
        
        return self._create_parsed_result(
            type_str=type_str,
            height=height,
            length=length,
            connection="VK-правое",
            source="template_002",
            confidence=0.95
        )

    def _parse_template_003(self, text: str, original: str = "") -> Optional[ParsedRadiator]:
        """
        Шаблон: стальной пан. радиатор therm-x2 Profil -V FTV {type}-{height}-{length} ПРАВ. с нижним присоедин. патрубками...
        Оригинал: стальной пан. радиатор therm-x2 Profil -V FTV 22-040-400 ПРАВ. с нижним присоедин. патрубками...
        Connection: VK-правое
        height_transform: code * 10 (040 → 400)
        length_transform: direct (400 → 400)
        """
        pattern = r'\bстальной\ пан\.\ радиатор\ therm\-x2\ Profil\ \-V\ FTV\ (\d+)-(\d+)-([\d,]+)\ ПРАВ\.\ с\ нижним\ присоедин\.\ патрубками'
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            return None
        
        type_str = match.group(1)
        height = int(match.group(2)) * 10  # code * 10
        length = int(match.group(3))       # direct
        
        return self._create_parsed_result(
            type_str=type_str,
            height=height,
            length=length,
            connection="VK-правое",
            source="template_003",
            confidence=0.95
        )

    def _parse_template_004(self, text: str, original: str = "") -> Optional[ParsedRadiator]:
        """
        Шаблон: стальной пан. радиатор therm-x2 Profil -V FTV {type}-{height}-{length} ЛЕВЫЙ. с нижним присоедин. патрубками...
        Оригинал: стальной пан. радиатор therm-x2 Profil -V FTV 22-040-400 ЛЕВЫЙ. с нижним присоедин. патрубками...
        Connection: VK-правое
        height_transform: code * 10 (040 → 400)
        length_transform: direct (400 → 400)
        """
        pattern = r'\bстальной\ пан\.\ радиатор\ therm\-x2\ Profil\ \-V\ FTV\ (\d+)-(\d+)-([\d,]+)\ ЛЕВЫЙ\.\ с\ нижним\ присоедин\.\ патрубками'
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            return None
        
        type_str = match.group(1)
        height = int(match.group(2)) * 10  # code * 10
        length = int(match.group(3))       # direct
        
        return self._create_parsed_result(
            type_str=type_str,
            height=height,
            length=length,
            connection="VK-правое",
            source="template_004",
            confidence=0.95
        )

    def _parse_template_005(self, text: str, original: str = "") -> Optional[ParsedRadiator]:
        """
        Шаблон: стальной пан. радиатор therm-x2 Profil -V FTV {type}-{height}-{length} ПРАВЫЙ. с нижним присоедин. патрубками...
        Оригинал: стальной пан. радиатор therm-x2 Profil -V FTV 22-060-400 ПРАВЫЙ. с нижним присоедин. патрубками...
        Connection: VK-правое
        height_transform: code * 10 (060 → 600)
        length_transform: direct (400 → 400)
        """
        pattern = r'\bстальной\ пан\.\ радиатор\ therm\-x2\ Profil\ \-V\ FTV\ (\d+)-(\d+)-([\d,]+)\ ПРАВЫЙ\.\ с\ нижним\ присоедин\.\ патрубками'
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            return None
        
        type_str = match.group(1)
        height = int(match.group(2)) * 10  # code * 10
        length = int(match.group(3))       # direct
        
        return self._create_parsed_result(
            type_str=type_str,
            height=height,
            length=length,
            connection="VK-правое",
            source="template_005",
            confidence=0.95
        )

    def _parse_template_006(self, text: str, original: str = "") -> Optional[ParsedRadiator]:
        """
        Шаблон: стальной пан. радиатор therm-x2 Profil -V FTV {type}-{height}-{length} лев. с нижним присоедин. патрубками...
        Оригинал: стальной пан. радиатор therm-x2 Profil -V FTV 22-030-400 лев. с нижним присоедин. патрубками...
        Connection: VK-правое
        height_transform: code * 10 (030 → 300)
        length_transform: direct (400 → 400)
        """
        pattern = r'\bстальной\ пан\.\ радиатор\ therm\-x2\ Profil\ \-V\ FTV\ (\d+)-(\d+)-([\d,]+)\ лев\.\ с\ нижним\ присоедин\.\ патрубками'
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            return None
        
        type_str = match.group(1)
        height = int(match.group(2)) * 10  # code * 10
        length = int(match.group(3))       # direct
        
        return self._create_parsed_result(
            type_str=type_str,
            height=height,
            length=length,
            connection="VK-правое",
            source="template_006",
            confidence=0.95
        )

    def _parse_template_007(self, text: str, original: str = "") -> Optional[ParsedRadiator]:
        """
        Шаблон: стальной пан. радиатор therm-x2 Profil -K FKO {type}-{height}-{length} лев. с нижним присоедин. патрубками...
        Оригинал: стальной пан. радиатор therm-x2 Profil -K FKO 22-030-1000 лев. с нижним присоедин. патрубками...
        Connection: K-боковое
        height_transform: code * 10 (030 → 300)
        length_transform: direct (1000 → 1000)
        """
        pattern = r'\bстальной\ пан\.\ радиатор\ therm\-x2\ Profil\ \-K\ FKO\ (\d+)-(\d+)-([\d,]+)\ лев\.\ с\ нижним\ присоедин\.\ патрубками'
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            return None
        
        type_str = match.group(1)
        height = int(match.group(2)) * 10  # code * 10
        length = int(match.group(3))       # direct
        
        return self._create_parsed_result(
            type_str=type_str,
            height=height,
            length=length,
            connection="K-боковое",
            source="template_007",
            confidence=0.95
        )

    def _parse_template_008(self, text: str, original: str = "") -> Optional[ParsedRadiator]:
        """
        Шаблон: стальной пан. радиатор therm-x2 Profil -K FKO {type}-{height}-{length} прав. с нижним присоедин. патрубками...
        Оригинал: стальной пан. радиатор therm-x2 Profil -K FKO 22-030-1400 прав. с нижним присоедин. патрубками...
        Connection: K-боковое
        height_transform: code * 10 (030 → 300)
        length_transform: direct (1400 → 1400)
        """
        pattern = r'\bстальной\ пан\.\ радиатор\ therm\-x2\ Profil\ \-K\ FKO\ (\d+)-(\d+)-([\d,]+)\ прав\.\ с\ нижним\ присоедин\.\ патрубками'
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            return None
        
        type_str = match.group(1)
        height = int(match.group(2)) * 10  # code * 10
        length = int(match.group(3))       # direct
        
        return self._create_parsed_result(
            type_str=type_str,
            height=height,
            length=length,
            connection="K-боковое",
            source="template_008",
            confidence=0.95
        )

    def _parse_template_009(self, text: str, original: str = "") -> Optional[ParsedRadiator]:
        """
        Шаблон: стальной пан. радиатор therm-x2 Profil -V FTV {type}-{height}-{length} пра. с нижним присоедин. патрубками...
        Оригинал: стальной пан. радиатор therm-x2 Profil -V FTV 22-030-1200 пра. с нижним присоедин. патрубками...
        Connection: VK-правое
        height_transform: code * 10 (030 → 300)
        length_transform: direct (1200 → 1200)
        """
        pattern = r'\bстальной\ пан\.\ радиатор\ therm\-x2\ Profil\ \-V\ FTV\ (\d+)-(\d+)-([\d,]+)\ пра\.\ с\ нижним\ присоедин\.\ патрубками'
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            return None
        
        type_str = match.group(1)
        height = int(match.group(2)) * 10  # code * 10
        length = int(match.group(3))       # direct
        
        return self._create_parsed_result(
            type_str=type_str,
            height=height,
            length=length,
            connection="VK-правое",
            source="template_009",
            confidence=0.95
        )

    def _parse_template_010(self, text: str, original: str = "") -> Optional[ParsedRadiator]:
        """
        Шаблон: Стальной панельный радиатор PRADO Universal {type}, h={height}мм, нижнее подключение, L=0,{length}м
        Оригинал: Стальной панельный радиатор PRADO Universal 20, h=300мм, нижнее подключение, L=0,4м
        Connection: VK-правое
        height_transform: direct (300 → 300)
        length_transform: code * 100 (0,4 → 400)
        """
        pattern = r'\bСтальной\ панельный\ радиатор\ PRADO\ Universal\ (\d+),\ h=(\d+)мм,\ нижнее\ подключение,\ L=0,([\d,]+)м'
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            return None
        
        type_str = match.group(1)
        height = int(match.group(2))              # direct
        length = int(match.group(3)) * 100        # code * 100
        
        return self._create_parsed_result(
            type_str=type_str,
            height=height,
            length=length,
            connection="VK-правое",
            source="template_010",
            confidence=0.95
        )

    def _parse_template_011(self, text: str, original: str = "") -> Optional[ParsedRadiator]:
        """
        Шаблон: Стальной панельный радиатор PRADO Universal {type}, h={height}мм, нижнее подключение, L={length}м
        Оригинал: Стальной панельный радиатор PRADO Universal 21, h=500мм, нижнее подключение, L=1,0м
        Connection: VK-правое
        height_transform: direct (500 → 500)
        length_transform: parse_decimal (1,0 → 1000)
        """
        pattern = r'\bСтальной\ панельный\ радиатор\ PRADO\ Universal\ (\d+),\ h=(\d+)мм,\ нижнее\ подключение,\ L=([\d,]+)м'
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            return None
        
        type_str = match.group(1)
        height = int(match.group(2))              # direct
        
        # parse_decimal: 1,0 → 1000
        length_clean = match.group(3).replace(',', '.')
        length_float = float(length_clean)
        length = int(length_float * 1000)
        
        return self._create_parsed_result(
            type_str=type_str,
            height=height,
            length=length,
            connection="VK-правое",
            source="template_011",
            confidence=0.95
        )

    def _parse_template_012(self, text: str, original: str = "") -> Optional[ParsedRadiator]:
        """
        Шаблон: Стальной панельный радиатор PRADO Classic {type}, h={height}мм, боковое подключение, L={length}м
        Оригинал: Стальной панельный радиатор PRADO Classic 22, h=300мм, боковое подключение, L=0,7м
        Connection: K-боковое
        height_transform: direct (300 → 300)
        length_transform: parse_decimal (0,7 → 700)
        """
        pattern = r'\bСтальной\ панельный\ радиатор\ PRADO\ Classic\ (\d+),\ h=(\d+)мм,\ боковое\ подключение,\ L=([\d,]+)м'
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            return None
        
        type_str = match.group(1)
        height = int(match.group(2))              # direct
        
        # parse_decimal: 0,7 → 700
        length_clean = match.group(3).replace(',', '.')
        length_float = float(length_clean)
        length = int(length_float * 1000)
        
        return self._create_parsed_result(
            type_str=type_str,
            height=height,
            length=length,
            connection="K-боковое",
            source="template_012",
            confidence=0.95
        )

    def _parse_template_013(self, text: str, original: str = "") -> Optional[ParsedRadiator]:
        """
        Шаблон: Стальной панельный радиатор PRADO Classic {type}, h={height}мм, нижнее подключение, L={length}м
        Оригинал: Стальной панельный радиатор PRADO Classic 33, h=300мм, нижнее подключение, L=0,9м
        Connection: K-боковое
        height_transform: direct (300 → 300)
        length_transform: parse_decimal (0,9 → 900)
        """
        pattern = r'\bСтальной\ панельный\ радиатор\ PRADO\ Classic\ (\d+),\ h=(\d+)мм,\ нижнее\ подключение,\ L=([\d,]+)м'
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            return None
        
        type_str = match.group(1)
        height = int(match.group(2))              # direct
        
        # parse_decimal: 0,9 → 900
        length_clean = match.group(3).replace(',', '.')
        length_float = float(length_clean)
        length = int(length_float * 1000)
        
        return self._create_parsed_result(
            type_str=type_str,
            height=height,
            length=length,
            connection="K-боковое",
            source="template_013",
            confidence=0.95
        )

    def _parse_template_014(self, text: str, original: str = "") -> Optional[ParsedRadiator]:
        """
        Шаблон: Стальной панельный радиатор PRADO Classicl {type}, h={height}мм, нижнее подключение, L={length}м
        Оригинал: Стальной панельный радиатор PRADO Classicl 33, h=300мм, нижнее подключение, L=1,7м
        Connection: K-боковое
        height_transform: direct (300 → 300)
        length_transform: parse_decimal (1,7 → 1700)
        """
        pattern = r'\bСтальной\ панельный\ радиатор\ PRADO\ Classicl\ (\d+),\ h=(\d+)мм,\ нижнее\ подключение,\ L=([\d,]+)м'
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            return None
        
        type_str = match.group(1)
        height = int(match.group(2))              # direct
        
        # parse_decimal: 1,7 → 1700
        length_clean = match.group(3).replace(',', '.')
        length_float = float(length_clean)
        length = int(length_float * 1000)
        
        return self._create_parsed_result(
            type_str=type_str,
            height=height,
            length=length,
            connection="K-боковое",
            source="template_014",
            confidence=0.95
        )

    def _parse_template_015(self, text: str, original: str = "") -> Optional[ParsedRadiator]:
        """
        Шаблон: 3.1. PURMO CV {type}s {height}x{length}
        Оригинал: 3.1. PURMO CV 21s 300x800
        Connection: VK-правое
        height_transform: direct (300 → 300)
        length_transform: direct (800 → 800)
        """
        pattern = r'\b3\.1\.\ PURMO\ CV\ (\d+)s\ (\d+)x([\d,]+)(?:\s|$|[,.;:!?])'
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            return None
        
        type_str = match.group(1)
        height = int(match.group(2))       # direct
        length = int(match.group(3))       # direct
        
        return self._create_parsed_result(
            type_str=type_str,
            height=height,
            length=length,
            connection="VK-правое",
            source="template_015",
            confidence=0.95
        )

    def _parse_template_016(self, text: str, original: str = "") -> Optional[ParsedRadiator]:
        """
        Шаблон: {type}s {height}x{length}
        Оригинал: 3.2. PURMO CV 21s 500x1100
        Connection: VK-правое
        height_transform: direct (500 → 500)
        length_transform: direct (1100 → 1100)
        """
        pattern = r'\b(\d+)s\ (\d+)x([\d,]+)(?:\s|$|[,.;:!?])'
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            return None
        
        type_str = match.group(1)
        height = int(match.group(2))       # direct
        length = int(match.group(3))       # direct
        
        return self._create_parsed_result(
            type_str=type_str,
            height=height,
            length=length,
            connection="VK-правое",
            source="template_016",
            confidence=0.95
        )

    def _guess_type_from_context(self, text: str) -> str:
        """Угадывает тип радиатора из контекста."""
        try:
            type_match = re.search(r'(?:тип|type)\s*(\d{1,2})', text, re.IGNORECASE)
            if type_match:
                t = type_match.group(1)
                if t in self.VALID_TYPES:
                    return t
        except Exception:
            pass
        return '22'

    # ========================================================================
    # ВАЛИДАЦИЯ И ИСПРАВЛЕНИЕ
    # ========================================================================

    def _validate_and_fix(self, result: ParsedRadiator, original: str) -> ParsedRadiator:
        """Проверяет и исправляет результат."""
        try:
            original_lower = original.lower()

            # Спецправило Kermi: тип 12 -> 21
            if 'kermi' in original_lower and result.rad_type == '12':
                result.rad_type = '21'
                result.warnings.append("Kermi тип 12 преобразован в 21")

            # Универсальные типы 20/21/22 с VK-левым -> VK-правое
            if result.connection == "VK-левое" and result.rad_type in ('20', '21', '22'):
                result.connection = "VK-правое"
                result.warnings.append(
                    f"Тип {result.rad_type} универсальный симметричный, "
                    f"переключено с VK-левого на VK-правое"
                )

            # Приводим нестандартную высоту
            if result.height is not None and result.height not in self.VALID_HEIGHTS:
                new_height = self._find_closest_height(result.height)
                if new_height != result.height:
                    result.warnings.append(f"Высота {result.height} → {new_height}")
                    result.height = new_height

            # Проверяем валидность типа
            if result.rad_type not in self.VALID_TYPES:
                result.recognized = False
                result.warnings.append(f"Невалидный тип: {result.rad_type}")
                return result

            # Проверяем валидность длины
            if result.length is not None and result.length not in self.VALID_LENGTHS:
                rounded = round(result.length / 100) * 100
                if 400 <= rounded <= 3000:
                    result.warnings.append(f"Длина {result.length} → {rounded}")
                    result.length = rounded
                else:
                    result.recognized = False
                    result.warnings.append(f"Невалидная длина: {result.length}")
                    return result

            # Финальная корректировка стороны
            result.connection = self._adjust_side_v2(result.connection, original, original)

            # Определяем бренд
            for brand in self.KNOWN_BRANDS:
                if brand in original_lower:
                    result.brand = brand
                    break

            return result
        except Exception as e:
            self._log(f"Validation error: {e}", "ERROR")
            result.recognized = False
            return result

    def _create_parsed_result(
        self,
        type_str: str,
        height: int,
        length: int,
        connection: str,
        source: str,
        confidence: float
    ) -> Optional[ParsedRadiator]:
        """
        Общий метод для создания ParsedRadiator с валидацией.
        Используется стратегиями из шаблонов.
        """
        # Преобразуем тип
        rad_type = type_str
        if rad_type not in ['10', '11', '20', '21', '22', '30', '33']:
            if rad_type == '12':
                rad_type = '21'
            else:
                return None
        
        # Проверяем высоту
        if height not in [300, 400, 500, 600, 900]:
            # Пытаемся исправить через HEIGHT_MAPPING
            if height in self.HEIGHT_MAPPING:
                height = self.HEIGHT_MAPPING[height]
            else:
                return None
        
        # Проверяем длину
        if length < 400 or length > 3000 or length % 100 != 0:
            return None
        
        result = ParsedRadiator()
        result.recognized = True
        result.connection = connection
        result.rad_type = rad_type
        result.height = height
        result.length = length
        result.confidence = confidence
        result.source = source
        return result

    def _find_closest_height(self, height: int) -> int:
        """Находит ближайшую стандартную высоту."""
        typo_mapping = {30: 300, 40: 400, 50: 500, 60: 600, 90: 900}
        if height in typo_mapping:
            return typo_mapping[height]
        if height in self.HEIGHT_MAPPING:
            return self.HEIGHT_MAPPING[height]
        return min(self.VALID_HEIGHTS, key=lambda h: abs(h - height))