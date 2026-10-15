"""
Подбор панельных радиаторов LaggarTT под секционные радиаторы.

Логика:
    1. Считаем мощность секционного радиатора:
           Q_секц = sections × power_per_section
    2. Стартовая длина: L = sections × 100 (шаг секции 100 мм).
    3. Перебираем кандидатов — тип 22 и тип 21 той же высоты и подключения
       на длинах в окне [L − WINDOW, L + WINDOW] с шагом 100.
    4. Оставляем тех, у кого отклонение dev = (Q_пан − Q_секц)/Q_секц × 100
       не ниже допустимого (по умолчанию −5 %).
    5. Из оставшихся выбираем ближайшего к целевому отклонению:
       - Сначала пробуем тип 22. Если есть кандидат с dev ≤ TARGET_UPPER
         (например, +5 %), берём лучшего из 22.
       - Если все 22 дают dev > TARGET_UPPER (избыток), берём лучшего из 21.
       - Если ни один не в допуске — берём ближайшего по |dev| среди всех,
         помечаем флагом `in_tolerance=False`.
"""

from dataclasses import dataclass
from typing import List, Optional, Dict
import re

from nextt.logger import get_logger
from nextt.core.data_provider import DataProvider

logger = get_logger(__name__)


# Мощность одной секции, Вт (эталон 95/85/20)
SECTION_POWER = {
    500: 185,
    300: 140,
}

# Диапазон количества секций
MIN_SECTIONS = 3
MAX_SECTIONS = 30

# Окно перебора длин вокруг стартовой L = sections × 100
LENGTH_WINDOW = 400  # мм

# Верхняя граница отклонения: если 22 даёт больше этого, пробуем 21
TARGET_UPPER = 5.0  # %


@dataclass
class SelectedRadiator:
    """Результат подбора панельного аналога."""
    article: str
    name: str
    radiator_type: str
    height: int
    length: int
    power: float
    sections_source: int
    quantity: int
    power_section_source: float
    power_total_source: float
    power_total_panel: float
    deviation_pct: float
    in_tolerance: bool
    connection: str


class SectionToPanelSelector:
    """Подбирает панельный LaggarTT под секционный радиатор."""

    def __init__(self, data_provider: DataProvider):
        self.dp = data_provider

    # ------------------------------------------------------------------
    # Публичный API
    # ------------------------------------------------------------------
    def select(
        self,
        height: int,
        sections: int,
        power_per_section: float,
        deviation_pct: float,
        connection_mode: str,
        quantity: int = 1,
    ) -> Optional[SelectedRadiator]:
        """Подбирает панельный аналог для одной позиции."""
        if height not in SECTION_POWER:
            logger.warning(f"Недопустимая высота: {height}")
            return None
        if not (MIN_SECTIONS <= sections <= MAX_SECTIONS):
            logger.warning(f"Секции вне диапазона: {sections}")
            return None
        if quantity <= 0:
            return None

        if connection_mode == "VK":
            conn_str = "VK-правое"
        elif connection_mode == "K":
            conn_str = "K-боковое"
        else:
            logger.warning(f"Неизвестный режим подключения: {connection_mode}")
            return None

        power_section_source = float(power_per_section)
        power_total_source = power_section_source * sections
        power_total_source_all = power_total_source * quantity

        if power_total_source <= 0:
            return None

        L0 = sections * 100
        L_min = max(400, L0 - LENGTH_WINDOW)
        L_max = min(3000, L0 + LENGTH_WINDOW)

        candidates_22 = self._collect_candidates(
            height=height, connection=conn_str,
            radiator_type="22",
            L_min=L_min, L_max=L_max,
            Q_target=power_total_source,
        )
        candidates_21 = self._collect_candidates(
            height=height, connection=conn_str,
            radiator_type="21",
            L_min=L_min, L_max=L_max,
            Q_target=power_total_source,
        )

        D = float(deviation_pct)

        def in_tol(c) -> bool:
            return c["deviation"] >= D

        tol_22 = [c for c in candidates_22 if in_tol(c)]
        tol_21 = [c for c in candidates_21 if in_tol(c)]

        best = None

        if tol_22:
            not_over = [c for c in tol_22 if c["deviation"] <= TARGET_UPPER]
            if not_over:
                best = min(not_over, key=lambda c: abs(c["deviation"]))
            else:
                if tol_21:
                    not_over_21 = [c for c in tol_21 if c["deviation"] <= TARGET_UPPER]
                    pool_21 = not_over_21 if not_over_21 else tol_21
                    best = min(pool_21, key=lambda c: abs(c["deviation"]))
                else:
                    best = min(tol_22, key=lambda c: abs(c["deviation"]))
        else:
            if tol_21:
                best = min(tol_21, key=lambda c: abs(c["deviation"]))
            else:
                all_c = candidates_22 + candidates_21
                if not all_c:
                    logger.warning(
                        f"Не найден панельный аналог: h={height}, "
                        f"sections={sections}, conn={conn_str}"
                    )
                    return None
                best = min(all_c, key=lambda c: abs(c["deviation"]))

        q_panel = best["power"]
        dev = best["deviation"]

        return SelectedRadiator(
            article=best["article"],
            name=best["name"],
            radiator_type=best["type"],
            height=height,
            length=best["length"],
            power=q_panel,
            sections_source=sections,
            quantity=quantity,
            power_section_source=power_section_source,
            power_total_source=power_total_source_all,
            power_total_panel=q_panel * quantity,
            deviation_pct=dev,
            in_tolerance=(dev >= D),
            connection=conn_str,
        )

    # ------------------------------------------------------------------
    # Внутреннее
    # ------------------------------------------------------------------
    def _collect_candidates(
        self,
        height: int,
        connection: str,
        radiator_type: str,
        L_min: int,
        L_max: int,
        Q_target: float,
    ) -> List[Dict]:
        """Собирает кандидатов указанного типа с нужной высотой,
        подключением и длиной в диапазоне [L_min, L_max]."""
        try:
            df = self.dp.filter_radiators(connection, radiator_type)
        except Exception as e:
            logger.debug(f"filter_radiators упал: {e}")
            return []

        if df is None or df.empty:
            return []

        out: List[Dict] = []
        for _, row in df.iterrows():
            name = str(row.get("Наименование", ""))
            h, l = self._extract_h_l(name)
            if h is None or l is None:
                continue
            if h != height:
                continue
            if not (L_min <= l <= L_max):
                continue

            try:
                power = float(row.get("Мощность, Вт", 0))
            except (ValueError, TypeError):
                continue
            if power <= 0:
                continue

            if Q_target <= 0:
                continue

            deviation = (power - Q_target) / Q_target * 100.0

            out.append({
                "article": str(row.get("Артикул", "")).strip(),
                "name": name,
                "type": radiator_type,
                "length": l,
                "power": power,
                "deviation": deviation,
            })

        return out

    @staticmethod
    def _extract_h_l(name: str):
        """Извлекает высоту и длину из наименования вида '.../500/1400'."""
        m = re.search(r"/(\d{3})/(\d{3,4})(?:\D|$)", name)
        if not m:
            return None, None
        try:
            return int(m.group(1)), int(m.group(2))
        except ValueError:
            return None, None