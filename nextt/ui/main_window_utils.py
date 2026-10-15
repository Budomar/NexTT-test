"""
Вспомогательные утилиты главного окна NexTT.

Вынесено из MainWindow: валидация ввода, парсинг количества,
нормализация названий, определение «своего» файла LaggarTT.
"""

import re
from typing import Optional

import pandas as pd

from nextt.logger import get_logger

logger = get_logger(__name__)


# ======================================================================
# Валидация полей ввода
# ======================================================================

def validate_input(value: str) -> bool:
    """
    Валидация поля ввода количества в матрице.
    Разрешает: пустую строку, цифры и знак '+'.
    """
    if value == "":
        return True
    return all(c.isdigit() or c == '+' for c in value)


def validate_number(value: str) -> bool:
    """
    Валидация числового поля (скидки 0..100).
    Разрешает: пустую строку, числа с запятой или точкой.
    """
    if value == "":
        return True
    try:
        v = float(value.replace(',', '.'))
        return 0 <= v <= 100
    except ValueError:
        return False
def parse_discount(value) -> float:
    """
    Парсит скидку из строки.
    Принимает запятую и точку как десятичный разделитель,
    игнорирует пробелы, при некорректном вводе возвращает 0.0.
    Результат ограничен диапазоном 0..100.
    """
    if value is None:
        return 0.0
    s = str(value).strip().replace(',', '.').replace(' ', '')
    if not s:
        return 0.0
    try:
        v = float(s)
    except ValueError:
        return 0.0
    if v < 0.0:
        return 0.0
    if v > 100.0:
        return 100.0
    return v

def validate_temperature(value: str) -> bool:
    """
    Валидация поля температуры: пусто или целое 0..150.
    """
    if value == "":
        return True
    return value.isdigit() and 0 <= int(value) <= 150


# ======================================================================
# Парсинг количества
# ======================================================================

def parse_qty(value) -> int:
    """
    Парсит количество из строки.
    Поддерживает форматы:
        - "5"
        - "1+2" (сумма)
        - "1 000" (пробелы как разделители тысяч)
    """
    if not value or value == "":
        return 0

    str_value = str(value).strip()

    # Убираем все пробелы (для чисел с разделителями тысяч)
    str_value = re.sub(r'\s+', '', str_value)

    if '+' in str_value:
        parts = str_value.split('+')
        total = 0
        for p in parts:
            p = p.strip()
            if not p:
                continue
            match = re.search(r'(\d+)', p)
            if match:
                total += int(match.group(1))
        return total

    match = re.search(r'(\d+)', str_value)
    return int(match.group(1)) if match else 0


def normalize_radiator_name(name: str) -> str:
    """
    Возвращает оригинальное название без изменений.
    Дедупликация не нужна — таблица соответствия должна совпадать с оригиналом.
    """
    return name.strip()


# ======================================================================
# Определение «своего» файла LaggarTT
# ======================================================================

def is_laggar_file(df: pd.DataFrame) -> bool:
    """
    Проверяет, содержит ли файл артикулы LaggarTT/Meteor.

    Достаточно хотя бы одного артикула радиатора (77246... или 77247...),
    чтобы считать файл файлом LaggarTT и обрабатывать его автоматически.
    """
    if df is None or df.empty:
        return False

    pattern = re.compile(r'7724[67]\d{5}')
    rows_to_check = min(50, len(df))
    for row_idx in range(rows_to_check):
        for col_idx in range(len(df.columns)):
            cell = str(df.iloc[row_idx, col_idx])
            if pattern.search(cell):
                return True
    return False