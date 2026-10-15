"""
Подбор панельных радиаторов LaggarTT под секционные — режим «По габаритам».

Логика:
    1. Считаем мощность секционного радиатора:
           Q_секц = sections × power_per_section
    2. Длина СТРОГО фиксирована:
           length = sections × 100 мм
       Габариты не трогаем.
    3. Высота по маппингу: 300 → 300, 350 → 400, 500 → 500.
    4. Типы: {10, 11, 20, 21, 22}. Типы 30 и 33 запрещены.
    5. Допуск двусторонний: −X ≤ dev ≤ +X.
    6. Сортировка: толщина → мощность.
           10 = 11 = 21 < 20 = 22
    7. Если никого в допуске — берём ближайшего по мощности
       и помечаем in_tolerance=False.

Для тултипа в UI селектор возвращает список ВСЕХ кандидатов
(all_candidates) вместе с выбранным.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Tuple
import re

from nextt.logger import get_logger
from nextt.core.data_provider import DataProvider

logger = get_logger(__name__)


# Список типов для режима «По габаритам» (типы 30 и 33 запрещены)
PANEL_TYPES = ["10", "11", "20", "21", "22"]

# Порядок толщины: 10 = 11 = 21 < 20 = 22
# Меньше число — тоньше радиатор.
THICKNESS_ORDER = {
    "10": 1,
    "11": 1,
    "21": 1,
    "20": 2,
    "22": 2,
}

# Длина одной секции по умолчанию, мм
SECTION_LENGTH = 100


@dataclass
class SelectedByDimension:
    """Результат подбора панельного аналога по габаритам."""
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
    # Список всех кандидатов (для тултипа)
    all_candidates: List[Dict] = field(default_factory=list)


class DimensionSelector:
    """Подбирает панельный LaggarTT, сохраняя высоту и длину секционного."""

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
    ) -> Optional[SelectedByDimension]:
        """
        Подбирает панельный аналог, сохраняя высоту и длину.

        Args:
            height: высота панельного радиатора (300, 400, 500).
            sections: количество секций.
            power_per_section: мощность одной секции (Вт).
            deviation_pct: допуск в процентах (например, 5 → ±5%).
            connection_mode: 'VK-правое' / 'K-боковое' (уже строка).
            quantity: количество радиаторов.

        Returns:
            SelectedByDimension или None.
        """
        conn_str = connection_mode

        power_total_source = power_per_section * sections
        if power_total_source <= 0:
            return None

        # Длина секционного радиатора: sections × 100 мм
        source_length = sections * SECTION_LENGTH

        # Допуск в долях (например, 5 → 0.05)
        X = abs(float(deviation_pct)) / 100.0

        # Собираем ВСЕХ кандидатов (без фильтра по мощности)
        all_candidates = self._collect_candidates(
            height=height,
            length=source_length,
            connection=conn_str,
            Q_target=power_total_source,
        )

        if not all_candidates:
            logger.warning(
                f"Не найдено панельных радиаторов для h={height}, "
                f"l={source_length}, conn={conn_str}"
            )
            return None

        # Фильтр по допуску ±X
        filtered = [
            c for c in all_candidates
            if -X <= c["deviation"] / 100.0 <= X
        ]

        if filtered:
            best = min(filtered, key=self._sort_key)
            in_tolerance = True
        else:
            # Ближайший по мощности
            best = min(all_candidates, key=lambda c: abs(c["deviation"]))
            in_tolerance = False

        return self._build_result(
            best, sections, power_per_section, power_total_source,
            quantity, conn_str, height, source_length,
            in_tolerance, all_candidates,
        )

    # ------------------------------------------------------------------
    # Внутреннее
    # ------------------------------------------------------------------
    def _sort_key(self, c: Dict) -> Tuple:
        """
        Ключ сортировки кандидатов:
            1) минимальная толщина (10 = 11 = 21 < 20 = 22),
            2) минимальная мощность.
        Длина фиксирована, поэтому в сортировке не участвует.
        """
        return (
            THICKNESS_ORDER.get(c["type"], 99),
            c["power"],
        )

    def _collect_candidates(
        self,
        height: int,
        length: int,
        connection: str,
        Q_target: float,
    ) -> List[Dict]:
        """Собирает кандидатов с заданной высотой и длиной, из списка типов."""
        out: List[Dict] = []

        for rad_type in PANEL_TYPES:
            try:
                df = self.dp.filter_radiators(connection, rad_type)
            except Exception as e:
                logger.debug(f"filter_radiators упал для типа {rad_type}: {e}")
                continue

            if df is None or df.empty:
                continue

            for _, row in df.iterrows():
                name = str(row.get("Наименование", ""))
                h, l = self._extract_h_l(name)
                if h is None or l is None:
                    continue
                if h != height:
                    continue
                if l != length:
                    continue

                try:
                    power = float(row.get("Мощность, Вт", 0))
                except (ValueError, TypeError):
                    continue
                if power <= 0:
                    continue

                deviation = (power - Q_target) / Q_target * 100.0

                out.append({
                    "article": str(row.get("Артикул", "")).strip(),
                    "name": name,
                    "type": rad_type,
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

    def _build_result(
        self,
        best: Dict,
        sections: int,
        power_per_section: float,
        power_total_source: float,
        quantity: int,
        conn_str: str,
        height: int,
        source_length: int,
        in_tolerance: bool,
        all_candidates: List[Dict],
    ) -> SelectedByDimension:
        """Собирает объект SelectedByDimension из словаря-кандидата."""
        return SelectedByDimension(
            article=best["article"],
            name=best["name"],
            radiator_type=best["type"],
            height=height,
            length=source_length,
            power=best["power"],
            sections_source=sections,
            quantity=quantity,
            power_section_source=power_per_section,
            power_total_source=power_total_source * quantity,
            power_total_panel=best["power"] * quantity,
            deviation_pct=best["deviation"],
            in_tolerance=in_tolerance,
            connection=conn_str,
            all_candidates=list(all_candidates),
        )