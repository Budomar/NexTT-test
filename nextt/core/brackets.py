"""
Расчёт кронштейнов для радиаторов LaggarTT.
Чистая бизнес-логика без зависимостей от UI.
"""

from typing import List, Tuple, Dict, Optional

from nextt.logger import get_logger

logger = get_logger(__name__)


class BracketsCalculator:
    """Рассчитывает необходимое количество и типы кронштейнов."""

    # Матрица подбора настенных кронштейнов
    # Ключ: тип радиатора -> высота -> артикул
    WALL_BRACKETS: Dict[str, Dict[int, str]] = {
        "10": {300: "К15Н.3100", 400: "К15Н.4100", 500: "К15Н.5100",
               600: "К15Н.6100", 900: "К15Н.9100"},
        "20": {300: "К15Н.3", 400: "К15Н.4", 500: "К15Н.5",
               600: "К15Н.6", 900: "К15Н.9"},
        "21": {300: "К15.4300", 400: "К15.4400", 500: "К15.4500",
               600: "К15.4600", 900: "К15.4900"},
        "22": {300: "К15.4300", 400: "К15.4400", 500: "К15.4500",
               600: "К15.4600", 900: "К15.4900"},
        "30": {300: "К15Н.3", 400: "К15Н.4", 500: "К15Н.5",
               600: "К15Н.6", 900: "К15Н.9"},
        "33": {300: "К15.4300", 400: "К15.4400", 500: "К15.4500",
               600: "К15.4600", 900: "К15.4900"},
    }

    # Матрица подбора напольных кронштейнов
    FLOOR_BRACKETS: Dict[str, Dict[int, str]] = {
        "10": {300: "КНС470", 400: "КНС470", 500: "КНС4100",
               600: "КНС4100", 900: "КНС4100"},
        "11": {300: "КНС450", 400: "КНС450", 500: "КНС470",
               600: "КНС470", 900: "КНС4100"},
        "20": {300: "КНС550", 400: "КНС550", 500: "КНС570",
               600: "КНС570", 900: "КНС5100"},
        "21": {300: "КНС650", 400: "КНС650", 500: "КНС670",
               600: "КНС670", 900: "КНС6100"},
        "22": {300: "КНС550", 400: "КНС550", 500: "КНС570",
               600: "КНС570", 900: "КНС5100"},
        "30": {300: "КНС550", 400: "КНС550", 500: "КНС570",
               600: "КНС570", 900: "КНС5100"},
        "33": {300: "КНС550", 400: "КНС550", 500: "КНС570",
               600: "КНС570", 900: "КНС5100"},
    }

    @classmethod
    def calculate(
        cls,
        radiator_type: str,
        length: int,
        height: int,
        bracket_type: str,
        quantity: int = 1,
    ) -> List[Tuple[str, int]]:
        """
        Рассчитывает кронштейны для одного типоразмера радиатора.

        Args:
            radiator_type: тип радиатора ("10", "11", "20", "21", "22", "30", "33")
            length: длина радиатора в мм
            height: высота радиатора в мм
            bracket_type: "Настенные кронштейны", "Напольные кронштейны" или "Без кронштейнов"
            quantity: количество радиаторов

        Returns:
            Список кортежей (артикул_кронштейна, количество)
        """
        if bracket_type == "Без кронштейнов":
            return []

        if bracket_type == "Настенные кронштейны":
            return cls._calculate_wall(radiator_type, length, height, quantity)
        elif bracket_type == "Напольные кронштейны":
            return cls._calculate_floor(radiator_type, length, height, quantity)

        return []

    @classmethod
    def _calculate_wall(
        cls, rad_type: str, length: int, height: int, qty: int
    ) -> List[Tuple[str, int]]:
        """Расчёт настенных кронштейнов."""
        brackets = []

        # Определяем количество по длине
        if 400 <= length <= 1600:
            bracket_qty = 2
        elif 1700 <= length <= 2500:
            bracket_qty = 3
        elif 2600 <= length <= 3000:
            bracket_qty = 4
        else:
            return []

        # Тип 11 — особый случай (левый + правый + средний)
        if rad_type == "11":
            brackets.append(("К9.2L", 2 * qty))
            brackets.append(("К9.2R", 2 * qty))
            if 1700 <= length <= 3000:
                brackets.append(("К9.3-40", 1 * qty))
            return brackets

        # Остальные типы
        if rad_type in cls.WALL_BRACKETS and height in cls.WALL_BRACKETS[rad_type]:
            art = cls.WALL_BRACKETS[rad_type][height]
            brackets.append((art, bracket_qty * qty))

        return brackets

    @classmethod
    def _calculate_floor(
        cls, rad_type: str, length: int, height: int, qty: int
    ) -> List[Tuple[str, int]]:
        """Расчёт напольных кронштейнов."""
        brackets = []

        if rad_type == "10":
            # Особый случай: 2 основных + дополнительный для длинных
            if height in [300, 400]:
                main_art = "КНС470"
            else:
                main_art = "КНС4100"

            brackets.append((main_art, 2 * qty))
            if 1700 <= length <= 3000:
                brackets.append(("КНС430", 1 * qty))
            return brackets

        if rad_type == "11":
            if height in [300, 400]:
                main_art = "КНС450"
            elif height in [500, 600]:
                main_art = "КНС470"
            else:
                main_art = "КНС4100"

            brackets.append((main_art, 2 * qty))
            if 1700 <= length <= 3000:
                brackets.append(("КНС430", 1 * qty))
            return brackets

        # Типы 20, 21, 22, 30, 33
        if rad_type in cls.FLOOR_BRACKETS and height in cls.FLOOR_BRACKETS[rad_type]:
            art = cls.FLOOR_BRACKETS[rad_type][height]

            if rad_type == "21":
                # Особая логика количества
                if 400 <= length <= 1100:
                    bracket_qty = 2
                elif 1200 <= length <= 1600:
                    bracket_qty = 3
                elif 1700 <= length <= 2400:
                    bracket_qty = 4
                elif 2500 <= length <= 3000:
                    bracket_qty = 5
                else:
                    bracket_qty = 0
            else:
                if 400 <= length <= 1100:
                    bracket_qty = 2
                elif 1101 <= length <= 1600:
                    bracket_qty = 3
                elif 1700 <= length <= 2400:
                    bracket_qty = 4
                elif 2500 <= length <= 3000:
                    bracket_qty = 5
                else:
                    bracket_qty = 0

            if bracket_qty > 0:
                brackets.append((art, bracket_qty * qty))

        return brackets

    @classmethod
    def calculate_total(
        cls,
        radiator_items: List[Dict],
        bracket_type: str,
    ) -> Dict[str, Dict]:
        """
        Рассчитывает суммарное количество кронштейнов для списка радиаторов.

        Args:
            radiator_items: список словарей с ключами:
                - rad_type: str
                - length: int
                - height: int
                - qty: int
            bracket_type: тип кронштейнов

        Returns:
            Словарь {артикул: {"qty": количество, "name": наименование}}
        """
        totals: Dict[str, Dict] = {}

        for item in radiator_items:
            brackets = cls.calculate(
                radiator_type=item["rad_type"],
                length=item["length"],
                height=item["height"],
                bracket_type=bracket_type,
                quantity=item["qty"],
            )
            for art, qty in brackets:
                if art not in totals:
                    totals[art] = {"qty": 0}
                totals[art]["qty"] += qty

        return totals