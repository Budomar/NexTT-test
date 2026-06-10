"""
Генератор спецификаций на основе заполненной матрицы.
Адаптировано из оригинального SpecGenerator (next1.71.py).
"""

import re
from typing import Dict, List, Tuple, Optional

import pandas as pd

from nextt.logger import get_logger

logger = get_logger(__name__)


class SpecGenerator:
    """Генерирует спецификацию радиаторов и кронштейнов."""

    VALID_HEIGHTS = [300, 400, 500, 600, 900]

    def __init__(self, data_provider):
        """
        Args:
            data_provider: экземпляр DataProvider для доступа к данным
        """
        self.data_provider = data_provider

    def prepare_spec_data(
        self,
        entry_values: Dict[tuple, str],
        bracket_type: str = "Настенные кронштейны",
        radiator_discount: float = 0.0,
        bracket_discount: float = 0.0,
    ) -> Optional[pd.DataFrame]:
        """
        Готовит данные для спецификации на основе заполненной матрицы.

        Args:
            entry_values: словарь {(connection_type, art): "кол-во"}
            bracket_type: тип кронштейнов
            radiator_discount: скидка на радиаторы (%)
            bracket_discount: скидка на кронштейны (%)

        Returns:
            DataFrame с колонками:
            №, Артикул, Наименование, Мощность, Вт, Цена, Скидка, %,
            Цена со скидкой, Кол-во, Сумма
        """
        radiator_rows = []
        bracket_rows = []
        brackets_temp: Dict[str, dict] = {}

        radiators_df = self.data_provider.radiators_df
        brackets_df = self.data_provider.brackets_df

        for key, value in entry_values.items():
            if not value:
                continue

            if not isinstance(key, tuple) or len(key) != 2:
                continue

            sheet_or_conn, art = key

            # Ищем радиатор по артикулу
            mask = radiators_df['Артикул'].astype(str).str.strip() == str(art).strip()
            matches = radiators_df[mask]
            if matches.empty:
                continue

            product = matches.iloc[0]
            qty = self.parse_quantity(value)
            if qty <= 0:
                continue

            try:
                price = float(product.get('Цена, руб', 0))
                disc_price = round(price * (1 - radiator_discount / 100), 2)
                total = round(disc_price * qty, 2)

                name = str(product['Наименование'])
                power = product.get('Мощность, Вт', 0)

                # Извлекаем параметры для сортировки
                height, length, rad_type, conn = self._extract_params(name)

                radiator_rows.append({
                    "№": 0,  # будет пересчитан после сортировки
                    "Артикул": str(product['Артикул']).strip(),
                    "Наименование": name,
                    "Мощность, Вт": float(power) if power else 0.0,
                    "Цена, руб (с НДС)": price,
                    "Скидка, %": radiator_discount,
                    "Цена со скидкой, руб (с НДС)": disc_price,
                    "Кол-во": qty,
                    "Сумма, руб (с НДС)": total,
                    "_connection": conn,
                    "_type": int(rad_type) if rad_type else 10,
                    "_height": height,
                    "_length": length,
                })

                # Расчёт кронштейнов
                if bracket_type != "Без кронштейнов" and rad_type and height and length:
                    brackets = self._calculate_brackets(
                        str(rad_type), length, height, bracket_type, qty
                    )
                    for art_b, qty_b in brackets:
                        mask_b = brackets_df['Артикул'] == art_b
                        if mask_b.any():
                            b_info = brackets_df[mask_b].iloc[0]
                            key_b = art_b.strip()
                            if key_b not in brackets_temp:
                                brackets_temp[key_b] = {
                                    "Артикул": art_b,
                                    "Наименование": str(b_info['Наименование']),
                                    "Цена, руб (с НДС)": float(b_info.get('Цена, руб', 0)),
                                    "Кол-во": 0,
                                    "Сумма, руб (с НДС)": 0.0,
                                }
                            b_price = float(b_info.get('Цена, руб', 0))
                            b_disc = round(b_price * (1 - bracket_discount / 100), 2)
                            brackets_temp[key_b]["Кол-во"] += qty_b
                            brackets_temp[key_b]["Сумма, руб (с НДС)"] += round(b_disc * qty_b, 2)

            except Exception as e:
                logger.error(f"Ошибка в данных радиатора {product.get('Артикул', '')}: {e}")
                continue

        # Сортировка радиаторов: сначала VK, потом K, по типу, высоте, длине
        if radiator_rows:
            radiator_rows.sort(key=lambda x: (
                0 if x["_connection"] == "VK" else 1,
                x["_type"],
                x["_height"],
                x["_length"],
            ))
            for i, row in enumerate(radiator_rows, 1):
                row["№"] = i

        # Кронштейны
        if brackets_temp:
            for b in brackets_temp.values():
                bracket_rows.append({
                    "№": len(radiator_rows) + len(bracket_rows) + 1,
                    "Артикул": b["Артикул"],
                    "Наименование": b["Наименование"],
                    "Мощность, Вт": 0.0,
                    "Цена, руб (с НДС)": b["Цена, руб (с НДС)"],
                    "Скидка, %": bracket_discount,
                    "Цена со скидкой, руб (с НДС)": round(
                        b["Цена, руб (с НДС)"] * (1 - bracket_discount / 100), 2
                    ),
                    "Кол-во": b["Кол-во"],
                    "Сумма, руб (с НДС)": b["Сумма, руб (с НДС)"],
                })

        if not radiator_rows and not bracket_rows:
            return None

        combined = radiator_rows + bracket_rows

        # Убираем служебные колонки
        df = pd.DataFrame(combined)
        columns = [
            "№", "Артикул", "Наименование", "Мощность, Вт",
            "Цена, руб (с НДС)", "Скидка, %",
            "Цена со скидкой, руб (с НДС)", "Кол-во",
            "Сумма, руб (с НДС)"
        ]
        return df[[c for c in columns if c in df.columns]]

    # ==================================================================
    # ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ
    # ==================================================================

    def parse_quantity(self, value) -> int:
        """Парсит количество (поддерживает 1+2)."""
        if not value or value == "":
            return 0
        str_value = str(value).strip()
        if '+' in str_value:
            parts = str_value.split('+')
            return sum(self._extract_int(p.strip()) for p in parts if p.strip())
        return self._extract_int(str_value)

    def _extract_int(self, text: str) -> int:
        """Извлекает первое целое число из строки."""
        match = re.search(r'(\d+[.,]?\d*)', text)
        if not match:
            return 0
        try:
            val = float(match.group(1).replace(',', '.'))
            return int(val) if abs(val - round(val)) < 0.001 else 0
        except ValueError:
            return 0

    def _extract_params(self, name: str) -> Tuple[int, int, str, str]:
        """Извлекает высоту, длину, тип и подключение из названия."""
        height, length = 500, 1000
        rad_type, conn = "10", "VK"

        parts = name.split('/')
        if len(parts) >= 3:
            try:
                # Длина (последняя часть)
                lm = re.search(r'(\d{3,4})', parts[-1])
                if lm:
                    length = int(lm.group(1))
                # Высота (предпоследняя)
                hm = re.search(r'(\d{3,4})', parts[-2])
                if hm:
                    height = int(hm.group(1))
                # Тип
                for p in reversed(parts[:-2]):
                    tm = re.search(r'(\d{2})', p)
                    if tm:
                        rad_type = tm.group(1)
                        break
            except (ValueError, IndexError):
                pass

        # Подключение
        if 'VK' in name:
            conn = "VK"
        elif 'K-' in name or 'K-Profil' in name:
            conn = "K"

        return height, length, rad_type, conn

    def _calculate_brackets(
        self, rad_type: str, length: int, height: int,
        bracket_type: str, qty: int
    ) -> List[Tuple[str, int]]:
        """Рассчитывает кронштейны через BracketsCalculator."""
        from nextt.core.brackets import BracketsCalculator
        return BracketsCalculator.calculate(rad_type, length, height, bracket_type, qty)

    def calculate_totals(self, spec_data: pd.DataFrame) -> Tuple[float, float, float]:
        """Рассчитывает общую мощность, вес и объём."""
        total_power = 0.0
        total_weight = 0.0
        total_volume = 0.0

        radiators_df = self.data_provider.radiators_df

        for _, row in spec_data.iterrows():
            if "Кронштейн" in str(row["Наименование"]):
                continue
            art = str(row["Артикул"]).strip()
            qty = int(row["Кол-во"])
            mask = radiators_df['Артикул'].astype(str).str.strip() == art
            if mask.any():
                prod = radiators_df[mask].iloc[0]
                total_power += float(prod.get('Мощность, Вт', 0)) * qty
                total_weight += float(prod.get('Вес, кг', 0)) * qty
                total_volume += float(prod.get('Объем, м3', 0)) * qty

        return total_power, round(total_weight, 1), round(total_volume, 3)

    def format_power(self, power_w: float) -> str:
        """Форматирует мощность."""
        if power_w >= 1_000_000:
            return f"{round(power_w / 1_000_000, 3)} МВт"
        elif power_w >= 1_000:
            return f"{round(power_w / 1_000, 3)} кВт"
        return f"{round(power_w, 2)} Вт"

    def format_weight(self, weight_kg: float) -> str:
        """Форматирует вес."""
        if weight_kg >= 1000:
            return f"{weight_kg / 1000:.3f} т"
        return f"{weight_kg:.3f} кг"