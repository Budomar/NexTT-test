"""
Общие функции форматирования чисел для NexTT.

Все функции поддерживают выбор десятичного разделителя:
    - ',' — для отображения пользователю (русская локаль, Excel)
    - '.' — для внутренних нужд (отладка, старый API)

Примеры:
    format_weight(15.75, ',')  → '15,750 кг'
    format_weight(1800.0, ',') → '1,800 т'
    format_weight(850.5, '.')  → '850.500 кг'
    format_power(13635, ',')   → '13,635 кВт'
    format_money(16393.23, ',')→ '16 393,23'
"""

from typing import Literal


DecimalSep = Literal[',', '.']


def _dec(value: float, sep: DecimalSep) -> str:
    """Приводит точку к выбранному разделителю."""
    return str(value).replace('.', sep)


def format_weight(weight_kg: float, sep: DecimalSep = ',') -> str:
    """
    Форматирует вес с автопереводом в тонны.

    < 1000 кг  →  '850,000 кг'  (3 знака)
    ≥ 1000 кг  →  '1,800 т'     (3 знака)
    """
    if weight_kg >= 1000:
        val = f"{weight_kg / 1000:.3f}"
        return f"{_dec(val, sep)} т"
    val = f"{weight_kg:.3f}"
    return f"{_dec(val, sep)} кг"


def format_power(power_w: float, sep: DecimalSep = ',') -> str:
    """
    Форматирует мощность: Вт / кВт / МВт.

    < 1000 Вт     →  '850,50 Вт'    (2 знака)
    < 1 000 000   →  '48,250 кВт'   (3 знака)
    ≥ 1 000 000   →  '1,234 МВт'    (3 знака)
    """
    if power_w >= 1_000_000:
        val = round(power_w / 1_000_000, 3)
        return f"{_dec(f'{val}', sep)} МВт"
    elif power_w >= 1_000:
        val = round(power_w / 1_000, 3)
        return f"{_dec(f'{val}', sep)} кВт"
    val = round(power_w, 2)
    return f"{_dec(f'{val}', sep)} Вт"


def format_volume(volume_m3: float, sep: DecimalSep = ',') -> str:
    """Форматирует объём: 3 знака после разделителя."""
    val = f"{volume_m3:.3f}"
    return _dec(val, sep)


def format_money(value: float, sep: DecimalSep = ',') -> str:
    """
    Форматирует сумму: пробел-тысячи, 2 знака после разделителя.

    Пример: 16 393,23
    """
    try:
        v = float(value)
    except (ValueError, TypeError):
        return ""
    integer_part = int(v)
    frac = abs(v - integer_part)
    sign = '-' if v < 0 else ''
    int_str = f"{abs(integer_part):,}".replace(',', ' ')
    frac_str = f"{frac:.2f}"[2:]  # отбрасываем '0.'
    return f"{sign}{int_str}{sep}{frac_str}"