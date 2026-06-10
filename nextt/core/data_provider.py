"""
Провайдер данных приложения NextT.
Загружает Мономатрицу.xlsx, предоставляет методы фильтрации.
Заменяет load_data(), _build_legacy_sheets_dict() и build_radiator_data().
"""

from pathlib import Path
from typing import List, Optional, Tuple

import pandas as pd

from nextt.config import get_resource_path
from nextt.logger import get_logger

logger = get_logger(__name__)


class DataProvider:
    """
    Единый источник данных о радиаторах и кронштейнах.
    Загружает Excel один раз при создании.
    """

    # Стандартные параметры
    VALID_HEIGHTS = [300, 400, 500, 600, 900]
    VALID_LENGTHS = list(range(400, 3100, 100))
    VALID_TYPES = ['10', '11', '20', '21', '22', '30', '33']
    CONNECTIONS = ['VK-правое', 'VK-левое', 'K-боковое']

    def __init__(self, file_path: Optional[str] = None):
        """
        Args:
            file_path: путь к Excel-файлу. Если None — используется Мономатрица.xlsx
        """
        if file_path is None:
            file_path = get_resource_path("Мономатрица.xlsx")
            if not Path(file_path).exists():
                file_path = get_resource_path("Матрица.xlsx")

        logger.info(f"Загрузка данных из: {file_path}")
        self._file_path = file_path
        self._radiators_df: Optional[pd.DataFrame] = None
        self._brackets_df: Optional[pd.DataFrame] = None
        self._load()

    def _load(self) -> None:
        """Загружает все листы Excel и обрабатывает данные."""
        try:
            all_sheets = pd.read_excel(self._file_path, sheet_name=None, engine='openpyxl')

            # --- Радиаторы ---
            if "Радиаторы" in all_sheets:
                self._radiators_df = all_sheets["Радиаторы"].copy()
            else:
                first_sheet = list(all_sheets.keys())[0]
                self._radiators_df = all_sheets[first_sheet].copy()
                logger.warning(f"Лист 'Радиаторы' не найден, используется: {first_sheet}")

            # Очистка и приведение типов
            self._radiators_df['Артикул'] = self._radiators_df['Артикул'].astype(str).str.strip()
            self._radiators_df['Вес, кг'] = pd.to_numeric(
                self._radiators_df['Вес, кг'], errors='coerce'
            ).fillna(0)
            self._radiators_df['Объем, м3'] = pd.to_numeric(
                self._radiators_df['Объем, м3'], errors='coerce'
            ).fillna(0)

            # Добавляем служебные колонки, если их нет
            if 'Connection' not in self._radiators_df.columns:
                self._radiators_df['Connection'] = ''
            if 'RadiatorType' not in self._radiators_df.columns:
                self._radiators_df['RadiatorType'] = ''
            if 'Мощность, Вт' not in self._radiators_df.columns:
                self._radiators_df['Мощность, Вт'] = ''

            # Заполняем служебные колонки из названий
            self._extract_connection_and_type()

            # --- Кронштейны ---
            if "Кронштейны" in all_sheets:
                self._brackets_df = all_sheets["Кронштейны"].copy()
                self._brackets_df['Артикул'] = self._brackets_df['Артикул'].astype(str).str.strip()
            else:
                self._brackets_df = pd.DataFrame()
                logger.warning("Лист 'Кронштейны' не найден")

            logger.info(
                f"Загружено: {len(self._radiators_df)} радиаторов, "
                f"{len(self._brackets_df)} кронштейнов"
            )

        except FileNotFoundError:
            logger.error(f"Файл не найден: {self._file_path}")
            raise
        except Exception as e:
            logger.error(f"Ошибка загрузки данных: {e}")
            raise

    def _extract_connection_and_type(self) -> None:
        """
        Извлекает Connection (VK-правое, VK-левое, K-боковое)
        и RadiatorType (число) из наименований.
        """
        import re

        for idx, row in self._radiators_df.iterrows():
            name = str(row['Наименование']).lower()

            # Уже заполнено — пропускаем
            if row['Connection'] and row['RadiatorType']:
                continue

            # Определяем подключение
            if 'vk-profil' in name:
                if ' la' in name or '-l' in name or name.endswith(' la'):
                    self._radiators_df.at[idx, 'Connection'] = 'VK-левое'
                else:
                    self._radiators_df.at[idx, 'Connection'] = 'VK-правое'
            elif 'k-profil' in name:
                self._radiators_df.at[idx, 'Connection'] = 'K-боковое'
            else:
                if name.endswith(' la') or ' la' in name:
                    self._radiators_df.at[idx, 'Connection'] = 'VK-левое'
                else:
                    self._radiators_df.at[idx, 'Connection'] = 'VK-правое'

            # Определяем тип радиатора
            type_match = re.search(r'(?:profil|тип)\s*(\d{2})', name)
            if type_match:
                self._radiators_df.at[idx, 'RadiatorType'] = type_match.group(1)
            else:
                type_match2 = re.search(r'/(\d{2})/', name)
                if type_match2:
                    self._radiators_df.at[idx, 'RadiatorType'] = type_match2.group(1)

    # ======================================================================
    # Публичные методы
    # ======================================================================

    @property
    def radiators_df(self) -> pd.DataFrame:
        """Возвращает копию DataFrame с радиаторами."""
        return self._radiators_df.copy()

    @property
    def brackets_df(self) -> pd.DataFrame:
        """Возвращает копию DataFrame с кронштейнами."""
        return self._brackets_df.copy()

    def filter_radiators(
        self,
        connection: str,
        radiator_type: str,
    ) -> pd.DataFrame:
        """
        Фильтрует радиаторы по подключению и типу.

        Args:
            connection: 'VK-правое', 'VK-левое' или 'K-боковое'
            radiator_type: '10', '11', '20', '21', '22', '30', '33'

        Returns:
            Отфильтрованный DataFrame (копия)
        """
        if self._radiators_df is None or self._radiators_df.empty:
            return pd.DataFrame()

        try:
            type_int = int(radiator_type)
            mask = (
                (self._radiators_df['Connection'] == connection) &
                (self._radiators_df['RadiatorType'] == type_int)
            )
        except ValueError:
            mask = (
                (self._radiators_df['Connection'] == connection) &
                (self._radiators_df['RadiatorType'].astype(str) == radiator_type)
            )

        return self._radiators_df[mask].copy()

    def find_by_article(self, article: str) -> Optional[pd.Series]:
        """
        Находит радиатор по артикулу.

        Args:
            article: артикул (77246... или 77247...)

        Returns:
            Series с данными радиатора или None
        """
        article_clean = str(article).strip()
        mask = self._radiators_df['Артикул'].astype(str).str.strip() == article_clean
        matches = self._radiators_df[mask]
        if not matches.empty:
            return matches.iloc[0]
        return None

    def find_analog(
        self,
        connection: str,
        rad_type: str,
        height: int,
        length: int,
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Ищет аналог LaggarTT по параметрам.
        Автоматически преобразует коды в реальные миллиметры:
        - height=3 → 300, height=03 → 300
        - length=12 → 1200, length=04 → 400
        - type=12 → 21 (в LaggarTT нет типа 12)
        """
        try:
            type_int = int(rad_type)
        except ValueError:
            return None, None

        # ================================================================
        # ПРЕОБРАЗОВАНИЕ ТИПА (12 → 21)
        # ================================================================
        if type_int == 12:
            type_int = 21
            rad_type = "21"

            # ================================================================
        # ФИКС: универсальные типы (20,21,22) не имеют левого/правого исполнения
        # VK-левое автоматически заменяем на VK-правое
        # ================================================================
        if connection == "VK-левое" and str(type_int) in ('20', '21', '22'):
            connection = "VK-правое"


        # ================================================================
        # ПРЕОБРАЗОВАНИЕ ВЫСОТЫ (код → миллиметры)
        # ================================================================
        actual_height = height
        
        # Если высота меньше 100 — это код, преобразуем в миллиметры
        if height < 100:
            # Код 3 → 300, код 03 → 3 → 300
            actual_height = height * 100
            
            # Корректировка для особых случаев
            if actual_height == 200:
                actual_height = 300
            elif actual_height == 700:
                actual_height = 600
            elif actual_height == 800:
                actual_height = 900
            elif actual_height == 1000:
                actual_height = 900
        
        # Проверяем валидность высоты
        if actual_height not in self.VALID_HEIGHTS:
            # Ищем ближайшую допустимую высоту
            closest = min(self.VALID_HEIGHTS, key=lambda h: abs(h - actual_height))
            if abs(closest - actual_height) <= 100:
                actual_height = closest
            else:
                return None, None

        # ================================================================
        # ПРЕОБРАЗОВАНИЕ ДЛИНЫ (код → миллиметры)
        # ================================================================
        actual_length = length
        
        # Если длина меньше 100 — это код, преобразуем в миллиметры
        if length < 100:
            actual_length = length * 100
            
            # Корректировка для особых случаев
            if actual_length == 300:
                actual_length = 300
            elif actual_length == 700:
                actual_length = 700
            elif actual_length == 800:
                actual_length = 800
            elif actual_length == 900:
                actual_length = 900
            # 1000 и выше уже нормально
        
        # Проверяем валидность длины
        if actual_length not in self.VALID_LENGTHS:
            # Округляем до ближайшего шага 100
            rounded = round(actual_length / 100) * 100
            if 400 <= rounded <= 3000:
                actual_length = rounded
            else:
                return None, None

        # ================================================================
        # ПОИСК В БАЗЕ
        # ================================================================
        pattern = f"/{actual_height}/{actual_length}"

        try:
            mask = (
                (self._radiators_df['Connection'] == connection) &
                (self._radiators_df['RadiatorType'] == type_int) &
                (self._radiators_df['Наименование'].str.contains(pattern, na=False, regex=False))
            )
            matches = self._radiators_df[mask]
        except Exception:
            return None, None

        if not matches.empty:
            row = matches.iloc[0]
            return str(row['Артикул']), str(row['Наименование'])

        return None, None

    def convert_meteor_to_laggar(self, article: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Конвертирует артикул Meteor (77246...) в LaggarTT (77247...) и ищет его.

        Returns:
            (артикул LaggarTT, наименование) или (None, None)
        """
        import re
        clean = re.sub(r'\D', '', article)
        if len(clean) != 10:
            return None, None

        if clean.startswith('77246'):
            laggar_art = clean[:4] + '7' + clean[5:]
        elif clean.startswith('77247'):
            laggar_art = clean
        else:
            return None, None

        found = self.find_by_article(laggar_art)
        if found is not None:
            return str(found['Артикул']), str(found['Наименование'])
        return None, None

    def get_brackets_list(self) -> List[dict]:
        """Возвращает список кронштейнов для UI."""
        brackets = []
        if not self._brackets_df.empty:
            for _, row in self._brackets_df.iterrows():
                brackets.append({
                    'article': str(row['Артикул']).strip(),
                    'name': str(row['Наименование']).strip(),
                })
        return brackets

    def find_bracket_by_article(self, article: str) -> Optional[pd.Series]:
        """Находит кронштейн по артикулу."""
        if self._brackets_df.empty:
            return None
        mask = self._brackets_df['Артикул'].astype(str).str.strip() == str(article).strip()
        matches = self._brackets_df[mask]
        if not matches.empty:
            return matches.iloc[0]
        return None