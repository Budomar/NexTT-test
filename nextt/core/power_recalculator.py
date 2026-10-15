"""
Пересчёт тепловой мощности радиаторов LaggarTT
с эталонного графика 95/85/20 (Δt = 70 °С) на произвольный.

Методика: ГОСТ 31311-2022 (НИИ Витатерм 2016).
Формула: Q = Qном × (Δt / 70)^n,
    где Qном — паспортная мощность, Вт (при Δt = 70 °С),
    n     — экспонент, зависящий от типа и высоты радиатора.

Источник данных для Qном — Мономатрица.xlsx (через DataProvider).
"""

from typing import Dict, TYPE_CHECKING

from nextt.logger import get_logger

if TYPE_CHECKING:
    from nextt.core.data_provider import DataProvider

logger = get_logger(__name__)


# =========================================================================
# Таблицы из ГОСТ 31311-2022 (лист «Данные» Excel-файла)
# =========================================================================

# Экспонент n (столбец C):
#   EXPONENTS[высота_мм][тип] = n
#
#
EXPONENTS: Dict[int, Dict[str, float]] = {
    300: {'10': 1.14, '11': 1.14, '20': 1.18, '21': 1.16, '22': 1.14, '30': 1.19, '33': 1.15},
    400: {'10': 1.14, '11': 1.14, '20': 1.18, '21': 1.16, '22': 1.14, '30': 1.19, '33': 1.15},
    500: {'10': 1.14, '11': 1.14, '20': 1.18, '21': 1.16, '22': 1.14, '30': 1.19, '33': 1.15},
    600: {'10': 1.14, '11': 1.14, '20': 1.18, '21': 1.16, '22': 1.14, '30': 1.19, '33': 1.15},
    900: {'10': 1.14, '11': 1.14, '20': 1.18, '21': 1.16, '22': 1.14, '30': 1.19, '33': 1.15},
}

# Стандартные высоты радиаторов, мм
VALID_HEIGHTS = sorted(EXPONENTS.keys())   # [300, 400, 500, 600, 900]

# Стандартные длины радиаторов, мм (шаг 100)
VALID_LENGTHS = list(range(400, 3100, 100))

# Типы радиаторов, для которых есть экспоненты
VALID_TYPES = ['10', '11', '20', '21', '22', '30', '33']


# =========================================================================
# Основной класс
# =========================================================================
class PowerRecalculator:
    """
    Утилита для пересчёта мощности радиатора под произвольный температурный график.

    Ключевая инвариантность:
        factor(..., delta_t=70.0) == 1.0
        recalc_power(q, ..., delta_t=70.0) == q
    Значит, при эталонном графике любые вычисления дают бит-в-бит исходные значения.
    """

    # Δt эталонного графика 95/85/20: (95+85)/2 − 20 = 70
    REFERENCE_DELTA = 70.0

    # Допуск, при котором график считается эталонным
    REFERENCE_EPS = 0.001

    # =====================================================================
    # Δt
    # =====================================================================

    @staticmethod
    def delta_t_from(supply: float, ret: float, room: float) -> float:
        """
        Температурный напор Δt = (t_подача + t_обратка) / 2 − t_помещение.
        """
        return (float(supply) + float(ret)) / 2.0 - float(room)

    @staticmethod
    def is_reference(delta_t: float) -> bool:
        """True, если Δt соответствует эталонному графику 95/85/20 (Δt = 70)."""
        return abs(delta_t - PowerRecalculator.REFERENCE_DELTA) < PowerRecalculator.REFERENCE_EPS

    @staticmethod
    def is_valid_delta(delta_t: float) -> bool:
        """True, если Δt физически корректен (> 0 и не слишком велик)."""
        return delta_t > 0.0 and delta_t <= 120.0

    # =====================================================================
    # Нормализация типа и высоты
    # =====================================================================

    @staticmethod
    def normalize_type(rad_type: str) -> str:
        """
        Приводит тип радиатора к каноническому виду.
        Тип 12 (Kermi) → 21.
        """
        t = str(rad_type).strip()
        if t == '12':
            return '21'
        return t

    @staticmethod
    def normalize_height(height_mm: int) -> int:
        """
        Приводит высоту к одной из стандартных: 300, 400, 500, 600, 900.
        Если высота нестандартная — берётся ближайшая.
        """
        try:
            h = int(height_mm)
        except (ValueError, TypeError):
            return 500
        if h in VALID_HEIGHTS:
            return h
        return min(VALID_HEIGHTS, key=lambda x: abs(x - h))

    # =====================================================================
    # Коэффициент пересчёта и мощность
    # =====================================================================

    @staticmethod
    def factor(rad_type: str, height_mm: int, delta_t: float) -> float:
        """
        Коэффициент пересчёта (Δt / 70)^n.

        При delta_t = 70 → ровно 1.0 (эталонный график, пересчёт не нужен).
        При delta_t < 70 → коэффициент < 1 (мощность падает).
        При delta_t > 70 → коэффициент > 1 (мощность растёт).
        При некорректном delta_t (≤ 0) → 1.0 (безопасный fallback).
        """
        if PowerRecalculator.is_reference(delta_t):
            return 1.0
        if delta_t <= 0.0:
            logger.warning(
                f"factor(): некорректный Δt = {delta_t}, "
                f"возвращён безопасный коэффициент 1.0"
            )
            return 1.0

        rt = PowerRecalculator.normalize_type(rad_type)
        h  = PowerRecalculator.normalize_height(height_mm)

        if rt not in EXPONENTS[h]:
            logger.warning(
                f"factor(): неизвестный тип '{rad_type}' (нормализован в '{rt}'), "
                f"высота {h}. Возвращён коэффициент 1.0"
            )
            return 1.0

        n = EXPONENTS[h][rt]
        return (float(delta_t) / PowerRecalculator.REFERENCE_DELTA) ** n

    @staticmethod
    def recalc_power(
        qnom_w: float,
        rad_type: str,
        height_mm: int,
        delta_t: float,
    ) -> float:
        """
        Пересчитанная мощность, Вт.

        При delta_t = 70 возвращает qnom_w без изменений (бит-в-бит).
        """
        if PowerRecalculator.is_reference(delta_t):
            return float(qnom_w)
        return float(qnom_w) * PowerRecalculator.factor(rad_type, height_mm, delta_t)

    # =====================================================================
    # Массовые вычисления для справочной таблицы
    # =====================================================================

    @staticmethod
    def full_table_for_height(
        height_mm: int,
        delta_t: float,
        data_provider: "DataProvider",
    ) -> Dict[str, list]:
        """
        Возвращает таблицу мощностей для одной высоты:
            { тип: [Q400, Q500, ..., Q3000] }

        Использует DataProvider для получения паспортных мощностей из Excel.
        Значения — округлённые до целых ватт.
        """
        h = PowerRecalculator.normalize_height(height_mm)
        result: Dict[str, list] = {}

        all_radiators = data_provider.radiators_df
        if all_radiators.empty:
            return {}

        # Фильтруем DataFrame по высоте
        try:
            # Извлекаем высоту из наименования, например, "/500/"
            height_mask = all_radiators['Наименование'].str.contains(f'/{h}/', regex=False, na=False)
            radiators_for_height = all_radiators[height_mask]
        except Exception as e:
            logger.error(f"Ошибка при фильтрации радиаторов по высоте {h}: {e}")
            return {}

        for rt in VALID_TYPES:
            row = []
            try:
                type_int = int(rt)
                radiators_for_type = radiators_for_height[radiators_for_height['RadiatorType'] == type_int]
                
                # Создаем словарь для быстрого поиска мощности по длине
                power_map = {}
                for _, rad in radiators_for_type.iterrows():
                    # Ищем длину в названии, например, "/1000"
                    import re
                    match = re.search(r'/(\d{3,4})$', rad['Наименование'])
                    if match:
                        length = int(match.group(1))
                        power_map[length] = rad.get('Мощность, Вт', 0)

                for L in VALID_LENGTHS:
                    qnom = power_map.get(L)
                    if qnom is None:
                        logger.warning(f"Не найдена паспортная мощность для типа {rt}, высоты {h}, длины {L}")
                        row.append(0)
                        continue
                    
                    q_recalc = PowerRecalculator.recalc_power(qnom, rt, h, delta_t)
                    row.append(int(round(q_recalc)))
            except Exception as e:
                logger.error(f"Ошибка при обработке типа {rt} для высоты {h}: {e}")
                row = [0] * len(VALID_LENGTHS)
            
            result[rt] = row

        return result

    @staticmethod
    def full_table_all_heights(
        delta_t: float,
        data_provider: "DataProvider",
    ) -> Dict[int, Dict[str, list]]:
        """
        Возвращает таблицы для всех 5 высот:
            { 300: {тип: [...]}, 400: {...}, ... }
        Используется для экспорта в Excel.
        """
        return {
            h: PowerRecalculator.full_table_for_height(h, delta_t, data_provider)
            for h in VALID_HEIGHTS
        }