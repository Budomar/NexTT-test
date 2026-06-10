"""
Парсер Excel/CSV/TSV файлов.
Извлекает данные в DataFrame для дальнейшей обработки.
"""

import os
from typing import Optional, Tuple

import pandas as pd

from nextt.logger import get_logger

logger = get_logger(__name__)


class ExcelParser:
    """Читает табличные файлы в DataFrame."""

    @classmethod
    def parse(cls, file_path: str) -> pd.DataFrame:
        """
        Читает файл и возвращает DataFrame.

        Поддерживает: .xlsx, .xls, .xlsm, .ods, .csv, .tsv, .txt

        Args:
            file_path: путь к файлу

        Returns:
            DataFrame с данными (все значения как строки)

        Raises:
            ValueError: если формат не поддерживается
        """
        ext = os.path.splitext(file_path)[1].lower()

        if ext in ['.xlsx', '.xlsm']:
            return cls._read_excel(file_path, engine='openpyxl')
        elif ext == '.xls':
            return cls._read_excel(file_path, engine='xlrd')
        elif ext == '.ods':
            return cls._read_excel(file_path, engine='odf')
        elif ext in ['.csv', '.tsv', '.txt']:
            return cls._read_csv(file_path)
        else:
            raise ValueError(f"Неподдерживаемый формат: {ext}")

    @classmethod
    def _read_excel(cls, file_path: str, engine: str) -> pd.DataFrame:
        """Читает Excel-файл."""
        try:
            df = pd.read_excel(file_path, header=None, engine=engine, dtype=str)
            return df.fillna('')
        except ImportError:
            raise ImportError(
                f"Для чтения {os.path.splitext(file_path)[1]} файлов "
                f"требуется библиотека {engine}. Установите: pip install {engine}"
            )
        except Exception as e:
            raise RuntimeError(f"Ошибка чтения Excel: {e}")

    @classmethod
    def _read_csv(cls, file_path: str) -> pd.DataFrame:
        """Читает CSV/TSV файл с автоопределением кодировки и разделителя."""
        try:
            import chardet
        except ImportError:
            raise ImportError(
                "Для чтения CSV/TSV требуется chardet. Установите: pip install chardet"
            )

        # Определяем кодировку
        with open(file_path, 'rb') as f:
            raw = f.read()
        encoding = chardet.detect(raw)['encoding'] or 'utf-8'

        # Определяем разделитель
        first_line = raw.decode(encoding, errors='ignore').split('\n')[0]
        if '\t' in first_line:
            sep = '\t'
        elif ';' in first_line:
            sep = ';'
        else:
            sep = ','

        try:
            df = pd.read_csv(
                file_path, sep=sep, header=None,
                encoding=encoding, dtype=str,
                on_bad_lines='skip', engine='python'
            )
            return df.fillna('')
        except Exception as e:
            raise RuntimeError(f"Ошибка чтения CSV/TSV: {e}")

    @classmethod
    def find_columns(
        cls, df: pd.DataFrame
    ) -> Tuple[Optional[int], Optional[int]]:
        """
        Автоматически находит столбцы с артикулами и количеством.

        Args:
            df: DataFrame с данными

        Returns:
            (art_col, qty_col) — индексы столбцов или None
        """
        art_col = None
        qty_col = None

        for i, row in df.iterrows():
            for j, cell in enumerate(row):
                cell_str = str(cell).strip().lower()
                if not art_col and any(
                    kw in cell_str for kw in ['артикул', 'art', 'код', 'article']
                ):
                    art_col = j
                if not qty_col and any(
                    kw in cell_str for kw in ['кол-во', 'количество', 'qty', 'quantity']
                ):
                    qty_col = j
            if art_col is not None and qty_col is not None:
                break

        return art_col, qty_col

    @classmethod
    def auto_detect_qty_column(cls, df: pd.DataFrame) -> Optional[int]:
        """
        Автоматически находит столбец с количеством.
        Ищет столбец, где есть 3+ подряд идущих числовых значения.

        Args:
            df: DataFrame с данными

        Returns:
            Индекс столбца или None
        """
        import re

        for col_idx in range(len(df.columns)):
            consecutive = 0
            max_consecutive = 0

            for val in df.iloc[:, col_idx].dropna().astype(str):
                val_clean = val.strip()
                if not val_clean:
                    consecutive = 0
                    continue

                cleaned = re.sub(r'[^\d.,]', '', val_clean)
                if not cleaned:
                    consecutive = 0
                    continue

                try:
                    cleaned = cleaned.replace(',', '.')
                    float(cleaned)
                    consecutive += 1
                    if consecutive > max_consecutive:
                        max_consecutive = consecutive
                except ValueError:
                    consecutive = 0

            if max_consecutive >= 3:
                return col_idx

        return None