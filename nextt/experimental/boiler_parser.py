"""
Всеядный парсер параметров газовых котлов.

Работает по принципу каскада независимых стратегий:
    1. Явные ключевые слова ("ГАЗ 6000", "GAZ6000")
    2. Явная модель из списка известных (B20/B23/B30/C11/C30/M30/M6/T2/Q3)
    3. Паттерн "мощность+тип" (24C, 24H, 32H)
    4. Только мощность (24 кВт, (24кВт))

Каждая стратегия возвращает гипотезу с уверенностью.
Гипотезы сливаются: приоритет — по уверенности, но поля
дополняются из других стратегий, если согласуются.

Главное правило всеядности:
    Модель  = буква(ы) СНАЧАЛА, цифры ПОСЛЕ   -> B30, C11, M30, GAZ6000
    Мощ+тип = цифры СНАЧАЛА, буква ПОСЛЕ      -> 24C, 24H, 32H
Эти паттерны не пересекаются, поэтому "C30" никогда не спутается
с типом подключения "C".
"""

import re
from dataclasses import dataclass, field
from typing import List, Optional

from nextt.logger import get_logger

logger = get_logger(__name__)


# =========================================================================
# Известные модели котлов (используются для валидации)
# =========================================================================
KNOWN_MODELS = {
    'B20', 'B23', 'B30',
    'C11', 'C30',
    'M30', 'M6',
    'T2', 'Q3',
    'GAZ6000',
}

# Допустимые мощности котлов
KNOWN_POWERS = {10, 12, 14, 18, 20, 24, 26, 28, 30, 32, 35, 36, 45, 60, 80}

# Русские буквы -> латинские (только визуально совпадающие)
RU_TO_EN = {
    'А': 'A', 'а': 'a', 'В': 'B', 'в': 'b',
    'С': 'C', 'с': 'c', 'Е': 'E', 'е': 'e',
    'Н': 'H', 'н': 'h', 'К': 'K', 'к': 'k',
    'М': 'M', 'м': 'm', 'О': 'O', 'о': 'o',
    'Р': 'P', 'р': 'p', 'Т': 'T', 'т': 't',
    'У': 'Y', 'у': 'y', 'Х': 'X', 'х': 'x',
}


@dataclass
class BoilerParams:
    """Извлечённые параметры котла."""
    model: str = ""
    model_suffix: str = ""
    power: Optional[int] = None
    conn_type: str = ""
    has_wifi: bool = False
    confidence: float = 0.0
    source: str = ""
    warnings: List[str] = field(default_factory=list)
    original_text: str = ""


# =========================================================================
# Утилиты нормализации
# =========================================================================

def _normalize(text: str) -> str:
    """
    Нормализует текст: русские буквы -> латинские, тире -> дефис,
    лишние пробелы убираются. Регистр СОХРАНЯЕТСЯ.
    """
    if not text:
        return ""
    result = []
    for ch in text:
        result.append(RU_TO_EN.get(ch, ch))
    text = ''.join(result)

    for dash in ['–', '—', '‐', '‑', '‒', '\u00ad']:
        text = text.replace(dash, '-')

    text = re.sub(r'\s+', ' ', text)

    return text.strip()


# =========================================================================
# Стратегии извлечения
# =========================================================================

def _strategy_gaz6000(text: str) -> BoilerParams:
    """
    Стратегия 1: ГАЗ 6000 / GAZ6000.
    Особый случай: модель — слово+число.
    """
    params = BoilerParams(original_text=text)

    match = re.search(r'\bGAZ\s*6000\b', text, re.IGNORECASE)
    if not match:
        return params

    params.model = 'GAZ6000'
    params.confidence = 0.9
    params.source = "gaz6000"

    after = text[match.end():]

    power_conn = re.search(
        r'\b(\d{2})\s*/?\s*(\d{2})?\s*([CH])(?![A-Za-z0-9])',
        after, re.IGNORECASE
    )
    if power_conn:
        if power_conn.group(2):
            params.power = int(power_conn.group(2))
        else:
            params.power = int(power_conn.group(1))
        params.conn_type = power_conn.group(3).upper()
    else:
        power_only = re.search(r'\b(\d{2})\b', after)
        if power_only:
            p = int(power_only.group(1))
            if p in KNOWN_POWERS:
                params.power = p

    suffix_match = re.search(r'\b(RN[WMTQH]?)\b', after, re.IGNORECASE)
    if suffix_match:
        params.model_suffix = suffix_match.group(1).upper()

    return params


def _strategy_explicit_model(text: str) -> BoilerParams:
    """
    Стратегия 2: явная модель из списка известных.
    Ищем B20/B23/B30/C11/C30/M30/M6/T2/Q3 как отдельное слово.
    """
    params = BoilerParams(original_text=text)

    sorted_models = sorted(KNOWN_MODELS - {'GAZ6000'}, key=len, reverse=True)
    found_model = None
    found_pos = -1

    for m in sorted_models:
        pattern = r'(?<![A-Za-z0-9])' + re.escape(m) + r'(?![A-Za-z])'
        match = re.search(pattern, text)
        if match:
            found_model = m
            found_pos = match.end()
            break

    if not found_model:
        return params

    params.model = found_model
    params.confidence = 0.8
    params.source = "explicit_model"

    # Ищем мощность+тип РЯДОМ с моделью (в радиусе ~40 символов после неё)
    window_end = min(found_pos + 40, len(text))
    window = text[found_pos:window_end]

    power_conn = re.search(
        r'(?<![A-Za-z0-9])(\d{2})\s*[-]?\s*([CH])(?![A-Za-z0-9])',
        window
    )
    if power_conn:
        p = int(power_conn.group(1))
        if p in KNOWN_POWERS:
            params.power = p
            params.conn_type = power_conn.group(2).upper()
            params.confidence = 0.95

    # Если не нашли в окне — ищем по всему тексту
    if not params.power:
        power_conn_global = re.search(
            r'(?<![A-Za-z0-9])(\d{2})\s*[-]?\s*([CH])(?![A-Za-z0-9])',
            text
        )
        if power_conn_global:
            p = int(power_conn_global.group(1))
            if p in KNOWN_POWERS:
                params.power = p
                params.conn_type = power_conn_global.group(2).upper()

    return params


def _strategy_power_conn(text: str) -> BoilerParams:
    """
    Стратегия 3: паттерн "мощность+тип" без явной модели.
    """
    params = BoilerParams(original_text=text)

    candidates = []
    for match in re.finditer(
        r'(?<![A-Za-z0-9])(\d{2})\s*[-]?\s*([CH])(?![A-Za-z0-9])',
        text
    ):
        p = int(match.group(1))
        if p in KNOWN_POWERS:
            candidates.append((p, match.group(2).upper(), match.start()))

    if not candidates:
        return params

    power, conn, _ = candidates[0]
    params.power = power
    params.conn_type = conn
    params.confidence = 0.5
    params.source = "power_conn"

    return params


def _strategy_power_only(text: str) -> BoilerParams:
    """
    Стратегия 4: только мощность (без типа подключения).
    """
    params = BoilerParams(original_text=text)

    match = re.search(
        r'(?<![A-Za-z0-9])(\d{2})\s*[кk][вw][тt]\b',
        text, re.IGNORECASE
    )
    if match:
        p = int(match.group(1))
        if p in KNOWN_POWERS:
            params.power = p
            params.confidence = 0.4
            params.source = "power_only"
            return params

    match = re.search(r'\((\d{2})\s*[кk]?[вw]?[тt]?\)', text, re.IGNORECASE)
    if match:
        p = int(match.group(1))
        if p in KNOWN_POWERS:
            params.power = p
            params.confidence = 0.35
            params.source = "power_parens"

    return params


# =========================================================================
# Слияние гипотез
# =========================================================================

def _merge(hypotheses: List[BoilerParams]) -> BoilerParams:
    """
    Сливает несколько гипотез в одну по голосованию с весами.
    """
    valid = [h for h in hypotheses if h.confidence > 0]
    if not valid:
        return BoilerParams()

    valid.sort(key=lambda h: -h.confidence)

    result = BoilerParams(original_text=valid[0].original_text)
    result.confidence = valid[0].confidence
    result.source = valid[0].source

    model_votes = {}
    power_votes = {}
    conn_votes = {}
    suffix_votes = {}

    for h in valid:
        if h.model:
            model_votes[h.model] = model_votes.get(h.model, 0) + h.confidence
        if h.power:
            power_votes[h.power] = power_votes.get(h.power, 0) + h.confidence
        if h.conn_type:
            conn_votes[h.conn_type] = conn_votes.get(h.conn_type, 0) + h.confidence
        if h.model_suffix:
            suffix_votes[h.model_suffix] = suffix_votes.get(h.model_suffix, 0) + h.confidence

    if model_votes:
        result.model = max(model_votes, key=model_votes.get)
    if power_votes:
        result.power = max(power_votes, key=power_votes.get)
    if conn_votes:
        result.conn_type = max(conn_votes, key=conn_votes.get)
    if suffix_votes:
        result.model_suffix = max(suffix_votes, key=suffix_votes.get)

    return result

# =========================================================================
# Публичный API
# =========================================================================

def parse_boiler(text: str) -> BoilerParams:
    """
    Главная функция: извлекает параметры котла из текста.
    """
    if not text or len(text.strip()) < 3:
        return BoilerParams()

    normalized = _normalize(text)

    # ================================================================
    # Wi-Fi: ищем И в оригинале, И в нормализованном тексте.
    # Оригинал нужен для кириллических вариантов ("Вайфай"),
    # нормализованный — для латинских ("Wi-Fi").
    # ================================================================
    wifi_pattern = r'wi[\s\-]?fi|вайфай|вафай|вай\s*фай|вай-?фай'
    has_wifi = bool(
        re.search(wifi_pattern, text, re.IGNORECASE)
        or re.search(wifi_pattern, normalized, re.IGNORECASE)
    )

    hypotheses = [
        _strategy_gaz6000(normalized),
        _strategy_explicit_model(normalized),
        _strategy_power_conn(normalized),
        _strategy_power_only(normalized),
    ]

    result = _merge(hypotheses)

    result.has_wifi = has_wifi

    logger.info(
        f"[BoilerParser] '{text[:60]}' -> "
        f"model={result.model}, power={result.power}, "
        f"conn={result.conn_type}, suffix={result.model_suffix}, "
        f"wifi={result.has_wifi}, conf={result.confidence:.2f}, "
        f"source={result.source}"
    )
    for w in result.warnings:
        logger.warning(f"[BoilerParser] {w}")

    return result