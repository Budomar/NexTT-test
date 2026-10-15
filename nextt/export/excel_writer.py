"""
Запись спецификации в Excel-файл.
Создаёт три листа: Спецификация, Таблица соответствия (если есть данные),
Упаковочный лист.

Все три листа используют единый стиль шапки документа:
    • Строка 1: крупный заголовок слева + «Программа:» справа
    • Строка 2: подзаголовок слева + «Дата формирования:» справа
    • Строка 3: синяя линия на всю ширину
    • Строки 4-5: мета-карточки (единый стиль)
"""

import os
import re
import tempfile
from datetime import datetime
from typing import Optional, Tuple, List

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, Border, Side, numbers, PatternFill
from openpyxl.utils import get_column_letter

from nextt.logger import get_logger
from nextt.core.power_recalculator import PowerRecalculator
from nextt.core.pallet_calculator import PalletCalculator
from nextt.utils.format import (
    format_power as _fmt_power_common,
    format_weight as _fmt_weight_common,
    format_volume as _fmt_volume_common,
)

logger = get_logger(__name__)


class ExcelWriter:
    """Записывает спецификацию в Excel."""

    # ================================================================
    # БАЗОВЫЕ СТИЛИ
    # ================================================================
    HEADER_FONT = Font(name='Calibri', size=11, bold=True)
    DATA_FONT = Font(name='Calibri', size=11)
    BOLD_FONT = Font(name='Calibri', size=11, bold=True)
    ITALIC_FONT = Font(name='Calibri', size=11, italic=True, color="595959")

    ALIGN_CENTER = Alignment(horizontal='center', vertical='center')
    ALIGN_LEFT = Alignment(horizontal='left', vertical='center')
    ALIGN_RIGHT = Alignment(horizontal='right', vertical='center')
    ALIGN_LEFT_WRAP = Alignment(
        horizontal='left', vertical='center', wrap_text=True
    )
    ALIGN_LEFT_TOP_WRAP = Alignment(
        horizontal='left', vertical='top', wrap_text=True
    )

    THIN_BORDER = Border(
        left=Side(style='thin'),
        right=Side(style='thin'),
        top=Side(style='thin'),
        bottom=Side(style='thin'),
    )

    MONEY_FORMAT = '#,##0.00'

    # ================================================================
    # ЦВЕТА
    # ================================================================
    COLOR_BLUE = "263168"
    COLOR_GREY_NOTE = "7A8798"
    COLOR_TEXT_DARK = "1A2230"
    COLOR_TEXT_SUB = "5B6779"
    COLOR_META_BG = "F6F8FB"
    COLOR_ROW_ALT = "F4F6FA"
    COLOR_TOTAL_BG = "EAF3EA"
    COLOR_GROUP_BG = "EEF1F5"
    COLOR_STAR = "B14B00"
    COLOR_DISCLAIMER = "4A5468"

    # ================================================================
    # ШРИФТЫ ДЛЯ ШАПКИ ДОКУМЕНТА (единые для всех листов)
    # ================================================================
    FONT_DOC_TITLE = Font(
        name='Calibri', size=18, bold=True, color=COLOR_BLUE
    )
    FONT_DOC_SUBTITLE = Font(
        name='Calibri', size=11, color=COLOR_TEXT_SUB
    )

    # Правый блок «Программа / Дата формирования»
    FONT_META_RIGHT_K = Font(
        name='Calibri', size=11, color=COLOR_TEXT_SUB
    )
    FONT_META_RIGHT_V = Font(
        name='Calibri', size=11, bold=True, color=COLOR_TEXT_DARK
    )

    # ================================================================
    # ШРИФТЫ ДЛЯ МЕТА-КАРТОЧЕК (единые для всех листов)
    # ================================================================
    FONT_META_KEY = Font(
        name='Calibri', size=9, color=COLOR_GREY_NOTE
    )
    FONT_META_VAL = Font(
        name='Calibri', size=12, bold=True, color=COLOR_TEXT_DARK
    )

    # ================================================================
    # ШРИФТЫ ДЛЯ ТАБЛИЦ
    # ================================================================
    FONT_TH = Font(name='Calibri', size=10, bold=True, color="FFFFFF")
    FONT_TH_SUB = Font(name='Calibri', size=9, bold=True, color="FFFFFF")
    FONT_TOTAL = Font(name='Calibri', size=11, bold=True, color="FFFFFF")

    FONT_DATA = Font(name='Calibri', size=11, color=COLOR_TEXT_DARK)
    FONT_DATA_MONO = Font(name='Consolas', size=11, color=COLOR_TEXT_DARK)
    FONT_DATA_TOTAL = Font(name='Calibri', size=11, bold=True, color=COLOR_BLUE)

    # ================================================================
    # ШРИФТЫ ДЛЯ ИТОГОВ УПАКОВКИ
    # ================================================================
    FONT_TOTALS_SECTION = Font(
        name='Calibri', size=11, bold=True, color="FFFFFF"
    )
    FONT_TOTALS_GROUP = Font(
        name='Calibri', size=10, bold=True, color=COLOR_BLUE
    )
    FONT_TOTALS_LBL = Font(name='Calibri', size=11, color=COLOR_TEXT_DARK)
    FONT_TOTALS_VAL = Font(
        name='Calibri', size=11, bold=True, color=COLOR_TEXT_DARK
    )
    FONT_TOTALS_NOTE = Font(
        name='Calibri', size=10, italic=True, color=COLOR_GREY_NOTE
    )

    FONT_FOOTNOTE = Font(
        name='Calibri', size=10, italic=True, color=COLOR_GREY_NOTE
    )
    FONT_DISCLAIMER = Font(
        name='Calibri', size=10, italic=True, color=COLOR_DISCLAIMER
    )

    # ================================================================
    # ЗАЛИВКИ
    # ================================================================
    FILL_TH = PatternFill(
        start_color=COLOR_BLUE, end_color=COLOR_BLUE, fill_type="solid"
    )
    FILL_META = PatternFill(
        start_color=COLOR_META_BG, end_color=COLOR_META_BG, fill_type="solid"
    )
    FILL_ALT = PatternFill(
        start_color=COLOR_ROW_ALT, end_color=COLOR_ROW_ALT, fill_type="solid"
    )
    FILL_TOTAL = PatternFill(
        start_color=COLOR_TOTAL_BG, end_color=COLOR_TOTAL_BG, fill_type="solid"
    )
    FILL_GROUP = PatternFill(
        start_color=COLOR_GROUP_BG, end_color=COLOR_GROUP_BG, fill_type="solid"
    )

    # ================================================================
    # БОРДЕРЫ
    # ================================================================
    BORDER_WHITE = Border(
        left=Side(style='thin', color='FFFFFF'),
        right=Side(style='thin', color='FFFFFF'),
        top=Side(style='thin', color='FFFFFF'),
        bottom=Side(style='thin', color='FFFFFF'),
    )

    BORDER_META_LEFT = Border(
        left=Side(style='medium', color=COLOR_BLUE),
    )

    # ================================================================
    # ЕДИНЫЕ ВЫСОТЫ СТРОК ШАПКИ
    # ================================================================
    ROW_HEIGHT_TITLE = 26      # строка 1 — заголовок + «Программа»
    ROW_HEIGHT_SUBTITLE = 18   # строка 2 — подзаголовок + «Дата формирования»
    ROW_HEIGHT_LINE = 3        # строка 3 — синяя линия
    ROW_HEIGHT_META_KEY = 16   # строка 4 — ключи мета-карточек
    ROW_HEIGHT_META_VAL = 22   # строка 5 — значения мета-карточек

    def __init__(self, data_provider=None):
        """
        Args:
            data_provider: экземпляр DataProvider для поиска мощности по артикулу
        """
        self.data_provider = data_provider

    # ================================================================
    # ПУБЛИЧНЫЙ МЕТОД СОХРАНЕНИЯ
    # ================================================================

    def save(self, spec_data: pd.DataFrame, file_path: str,
             correspondence_data: Optional[pd.DataFrame] = None,
             program_name: str = "NexTT",
             graph_meta: Optional[dict] = None,
             project_name: str = "",
             radiator_discount: float = 0.0,
             bracket_discount: float = 0.0) -> None:
        """
        Сохраняет спецификацию в Excel.

        Args:
            spec_data: DataFrame с данными спецификации
            file_path: путь для сохранения
            correspondence_data: DataFrame с таблицей соответствия
            program_name: название программы для подписи
            graph_meta: метаданные температурного графика
            project_name: название проекта
        """
        from datetime import datetime as _dt

        if graph_meta is None:
            graph_meta = {
                "supply": 95,
                "return": 85,
                "room":   20,
                "delta_t": 70.0,
                "is_reference": True,
            }

        supply = graph_meta.get("supply", 95)
        ret    = graph_meta.get("return", 85)
        room   = graph_meta.get("room",   20)
        delta_t = graph_meta.get("delta_t", 70.0)

        graph_str = f"{supply}/{ret}/{room}"
        delta_str = f"{delta_t:.1f}".replace('.', ',')

        project_value = project_name.strip() if project_name else ""
        if not project_value:
            project_value = "—"

        # ================================================================
        # СУММАРНАЯ МОЩНОСТЬ
        # ================================================================
        total_power = 0.0
        for _, row in spec_data.iterrows():
            if "Кронштейн" in str(row.get("Наименование", "")):
                continue
            try:
                power = float(row.get("Мощность, Вт", 0) or 0)
                qty = int(row.get("Кол-во", 0) or 0)
                total_power += power * qty
            except (ValueError, TypeError):
                continue

        power_str = _fmt_power_common(total_power, sep=',')

        # ================================================================
        # СУММАРНЫЙ ВЕС И ОБЪЁМ
        # ================================================================
        total_weight_rad, total_volume_rad = self._calculate_total_weight_and_volume(spec_data)
        total_weight_br = self._calculate_total_brackets_weight(spec_data)

        weight_rad_str = _fmt_weight_common(total_weight_rad, sep=',')
        weight_br_str  = _fmt_weight_common(total_weight_br, sep=',')
        volume_str     = _fmt_volume_common(total_volume_rad, sep=',')

        wb = Workbook()
        ws = wb.active
        ws.title = "Спецификация"

        date_str = _dt.now().strftime("%d.%m.%Y")

        # ================================================================
        # ШАПКА СПЕЦИФИКАЦИИ
        # ================================================================
        self._write_doc_header(
            ws,
            title="СПЕЦИФИКАЦИЯ РАДИАТОРОВ LAGGARTT",
            subtitle="",
            program_name=program_name,
            date_str=date_str,
            left_end_col=6,
            right_start_col=7,
            right_end_col=10,
        )
         # ================================================================
        # ПОЛЯ СКИДОК — ТОЛЬКО НА ЛИСТЕ «СПЕЦИФИКАЦИЯ»
        # Подпись: C2. Поля: D2 (радиаторы), E2 (кронштейны).
        # ================================================================
        # 1. Разъединяем A2:F2 (объединение из _write_doc_header),
        #    чтобы можно было писать в C2, D2, E2.
        for merged_range in list(ws.merged_cells.ranges):
            if (merged_range.min_row == 2 and merged_range.max_row == 2
                    and merged_range.min_col == 1 and merged_range.max_col == 6):
                ws.unmerge_cells(str(merged_range))
                break

        # 2. Подпись — C2
        cell = ws.cell(
            row=2, column=3,
            value="Скидки на радиаторы и кронштейны, %:",
        )
        cell.font = Font(name='Calibri', size=11, bold=True, color='2B2B2B')
        cell.alignment = Alignment(horizontal='right', vertical='center')

        # 3. Поля ввода — D2 (радиаторы) и E2 (кронштейны)
        INPUT_FILL = PatternFill(
            start_color='FFFDF2', end_color='FFFDF2', fill_type='solid'
        )
        INPUT_BORDER = Border(
            left=Side(style='thin', color='B8A55C'),
            right=Side(style='thin', color='B8A55C'),
            top=Side(style='thin', color='B8A55C'),
            bottom=Side(style='thin', color='B8A55C'),
        )
        INPUT_FONT = Font(name='Calibri', size=11, bold=True, color='2B2B2B')

        # D2 — скидка на радиаторы
        cell_d = ws.cell(row=2, column=4, value=radiator_discount)
        cell_d.number_format = '0.00'
        cell_d.font = INPUT_FONT
        cell_d.alignment = Alignment(horizontal='center', vertical='center')
        cell_d.fill = INPUT_FILL
        cell_d.border = INPUT_BORDER

        # E2 — скидка на кронштейны
        cell_e = ws.cell(row=2, column=5, value=bracket_discount)
        cell_e.number_format = '0.00'
        cell_e.font = INPUT_FONT
        cell_e.alignment = Alignment(horizontal='center', vertical='center')
        cell_e.fill = INPUT_FILL
        cell_e.border = INPUT_BORDER
        # ================================================================
        # МЕТА-КАРТОЧКИ
        # ================================================================
        self._write_meta_cards(
            ws,
            start_row=4,
            cards=[
                ("ТЕМПЕРАТУРНЫЙ ГРАФИК",
                 f"{graph_str} °С (Δt = {delta_str} °С)"),
                ("ПРОЕКТ", project_value),
            ],
            col_ranges=[(1, 3), (4, 10)],
            total_cols=10,
        )

        # Строка 6 — пустая (отступ перед таблицей)

        # ================================================================
        # ТАБЛИЦА СПЕЦИФИКАЦИИ (с 7-й строки)
        # ================================================================
        header_start_row = 7

        headers = [
            "№", "Артикул", "Наименование", "Мощность, Вт", "Вид монтажа",
            "Цена, руб (с НДС)", "Скидка, %",
            "Цена со скидкой, руб (с НДС)", "Кол-во",
            "Сумма, руб (с НДС)"
        ]

        for col, header_text in enumerate(headers, 1):
            cell = ws.cell(row=header_start_row, column=col, value=header_text)
            cell.font = self.FONT_TH
            cell.fill = self.FILL_TH
            cell.alignment = Alignment(
                horizontal='center', vertical='center', wrap_text=True
            )
            cell.border = self.BORDER_WHITE

        ws.row_dimensions[header_start_row].height = 34

        # ================================================================
        # ДАННЫЕ ТАБЛИЦЫ (с «зеброй» #E4E9F2)
        # ================================================================
        data_start_row = header_start_row + 1
        for idx, (_, row) in enumerate(spec_data.iterrows()):
            row_num = data_start_row + idx

            is_bracket = "Кронштейн" in str(row.get("Наименование", ""))
            power_value = "" if is_bracket else row.get("Мощность, Вт", "")

            if is_bracket:
                mount_value = ""
            else:
                raw_mount = str(row.get("Тип монтажа", "")).strip().lower()
                if raw_mount == "настенный":
                    mount_value = "На стену"
                elif raw_mount == "напольный":
                    mount_value = "На пол"
                else:
                    mount_value = ""

            # A — №
            ws.cell(row=row_num, column=1, value=idx + 1)
            # B — Артикул (как ТЕКСТ)
            art_cell = ws.cell(row=row_num, column=2)
            art_cell.number_format = '@'
            art_cell.value = str(row.get("Артикул", ""))
            art_cell.data_type = 's'
            # C — Наименование
            ws.cell(row=row_num, column=3, value=row.get("Наименование", ""))
            # D — Мощность
            ws.cell(row=row_num, column=4, value=power_value)
            # E — Вид монтажа
            ws.cell(row=row_num, column=5, value=mount_value)
            # F — Цена
            ws.cell(row=row_num, column=6,
                    value=float(row.get("Цена, руб (с НДС)", 0)))
            # G — Скидка, % (формула: радиаторы → $D$2, кронштейны → $E$2)
            discount_ref = "$E$2" if is_bracket else "$D$2"
            discount_cell = ws.cell(row=row_num, column=7, value=f"={discount_ref}")
            discount_cell.number_format = '0.00'
            # H — Формула цены со скидкой
            ws.cell(row=row_num, column=8,
                    value=f"=F{row_num}*(1-G{row_num}/100)")
            # I — Кол-во
            ws.cell(row=row_num, column=9,
                    value=int(row.get("Кол-во", 0)))
            # J — Формула суммы
            ws.cell(row=row_num, column=10,
                    value=f"=H{row_num}*I{row_num}")

            # Оформление + «зебра»
            is_alt = (idx % 2 == 1)

            for col in range(1, 11):
                cell = ws.cell(row=row_num, column=col)
                cell.font = self.DATA_FONT
                cell.border = self.THIN_BORDER
                if is_alt:
                    cell.fill = self.FILL_ALT
                if col in [6, 8, 10]:
                    cell.number_format = self.MONEY_FORMAT
                    cell.alignment = self.ALIGN_CENTER
                elif col in [1, 4, 5, 7, 9]:
                    cell.alignment = self.ALIGN_CENTER
                else:
                    cell.alignment = self.ALIGN_LEFT

        # ================================================================
        # ИТОГОВАЯ СТРОКА
        # ================================================================
        total_row = data_start_row + len(spec_data)

        total_qty_rad = sum(
            int(row["Кол-во"]) for _, row in spec_data.iterrows()
            if "Кронштейн" not in str(row.get("Наименование", ""))
        )
        total_qty_br = sum(
            int(row["Кол-во"]) for _, row in spec_data.iterrows()
            if "Кронштейн" in str(row.get("Наименование", ""))
        )

        ws.merge_cells(
            start_row=total_row, start_column=1,
            end_row=total_row, end_column=8,
        )
        ws.cell(row=total_row, column=1,
                value="Итого (радиаторы/кронштейны):")
        ws.cell(row=total_row, column=9, value=f"{total_qty_rad}/{total_qty_br}")
        ws.cell(row=total_row, column=10,
                value=f"=SUM(J{data_start_row}:J{total_row - 1})")

        # Оформление: заливка + тонкие границы
        for col in range(1, 11):
            cell = ws.cell(row=total_row, column=col)
            cell.font = self.FONT_DATA_TOTAL
            cell.fill = self.FILL_TOTAL
            cell.border = self.THIN_BORDER
            if col == 1:
                cell.alignment = self.ALIGN_RIGHT
            else:
                cell.alignment = self.ALIGN_CENTER
            if col == 10:
                cell.number_format = self.MONEY_FORMAT

        # Двойные линии сверху и снизу — на все ячейки A:J
        for col in range(1, 11):
            cell = ws.cell(row=total_row, column=col)
            existing_left = cell.border.left if cell.border else Side()
            existing_right = cell.border.right if cell.border else Side()
            cell.border = Border(
                left=existing_left,
                right=existing_right,
                top=Side(style='double', color='263168'),
                bottom=Side(style='double', color='263168'),
            )

        # ================================================================
        # ДОПОЛНИТЕЛЬНЫЕ СВЕДЕНИЯ И КОМПЛЕКТАЦИЯ
        # ================================================================
        info_start_row = total_row + 2

        info_end_row = self._write_additional_info_block(
            ws,
            start_row=info_start_row,
            weight_rad_str=weight_rad_str,
            weight_br_str=weight_br_str,
            volume_str=volume_str,
            power_str=power_str,
        )

        kit_start_row = info_end_row + 2
        self._write_kit_block(
            ws,
            start_row=kit_start_row,
            spec_data=spec_data,
        )

        # ================================================================
        # ШИРИНА СТОЛБЦОВ
        # ================================================================
        widths = {'A': 5, 'B': 12, 'C': 50, 'D': 15, 'E': 14,
                  'F': 20, 'G': 10, 'H': 40, 'I': 12, 'J': 20}
        for col_letter, width in widths.items():
            ws.column_dimensions[col_letter].width = width

        ws.sheet_view.showGridLines = False

        # ================================================================
        # ЛИСТ «ТАБЛИЦА СООТВЕТСТВИЯ»
        # ================================================================
        if correspondence_data is not None and not correspondence_data.empty:
            if "Таблица соответствия" in wb.sheetnames:
                std = wb["Таблица соответствия"]
                wb.remove(std)

            ws_corr = wb.create_sheet("Таблица соответствия")

            show_calc_power_column = not PowerRecalculator.is_reference(delta_t)

            delta_str_for_header = f"{delta_t:.2f}".replace('.', ',')

            corr_headers = [
                'Оригинальное наименование',
                'Количество',
                'Наименование LaggarTT',
                'Артикул LaggarTT',
                'Номинальный\nтепловой поток, Вт',
            ]
            if show_calc_power_column:
                corr_headers.append(
                    f'Тепловой поток при\nΔt = {delta_str_for_header} °С, Вт'
                )

            num_corr_cols = len(corr_headers)

            self._write_doc_header(
                ws_corr,
                title="ТАБЛИЦА СООТВЕТСТВИЯ АНАЛОГОВ LAGGARTT",
                subtitle="Приложение к спецификации",
                program_name=program_name,
                date_str=date_str,
                left_end_col=3,
                right_start_col=4,
                right_end_col=num_corr_cols,
            )

            self._write_meta_cards(
                ws_corr,
                start_row=4,
                cards=[
                    ("ТЕМПЕРАТУРНЫЙ ГРАФИК",
                     f"{graph_str} °С (Δt = {delta_str} °С)"),
                    ("ПРОЕКТ", project_value),
                ],
                col_ranges=[(1, 2), (3, num_corr_cols)],
                total_cols=num_corr_cols,
            )

            corr_header_row = 7

            processed_data = []
            for _, row in correspondence_data.iterrows():
                meteor_art = str(row.get('Артикул LaggarTT', '')).strip()

                power_nom, power_calc = self._get_power_data_by_article(
                    meteor_art, delta_t
                )

                qty_value = 0
                if 'Кол-во' in row:
                    qty_value = row.get('Кол-во', 0)
                elif 'Количество' in row:
                    qty_value = row.get('Количество', 0)
                else:
                    qty_value = row.get(list(row.index)[1], 0) if len(row.index) > 1 else 0

                original_name = ''
                if 'Наименование' in row:
                    original_name = row.get('Наименование', '')
                elif 'Оригинальное наименование' in row:
                    original_name = row.get('Оригинальное наименование', '')
                else:
                    original_name = row.get(list(row.index)[0], '') if len(row.index) > 0 else ''

                meteor_name = ''
                if 'Наименование LaggarTT' in row:
                    meteor_name = row.get('Наименование LaggarTT', '')
                else:
                    meteor_name = row.get(list(row.index)[2], '') if len(row.index) > 2 else ''

                processed_data.append({
                    'Оригинальное наименование': original_name,
                    'Количество': qty_value,
                    'Наименование LaggarTT': meteor_name,
                    'Артикул LaggarTT': meteor_art,
                    'Мощность паспортная, Вт': power_nom,
                    'Мощность расчётная, Вт': power_calc,
                })

            for col_idx, header_text in enumerate(corr_headers, 1):
                cell = ws_corr.cell(
                    row=corr_header_row, column=col_idx, value=header_text
                )
                cell.font = self.FONT_TH
                cell.fill = self.FILL_TH
                cell.alignment = Alignment(
                    horizontal='center', vertical='center', wrap_text=True
                )
                cell.border = self.BORDER_WHITE

            ws_corr.row_dimensions[corr_header_row].height = 34

            data_start_row_corr = corr_header_row + 1
            total_qty_corr = 0

            for i, row_data in enumerate(processed_data):
                row_num = data_start_row_corr + i

                row_for_append = [
                    row_data['Оригинальное наименование'],
                    row_data['Количество'],
                    row_data['Наименование LaggarTT'],
                    row_data['Артикул LaggarTT'],
                    row_data['Мощность паспортная, Вт'],
                ]
                if show_calc_power_column:
                    row_for_append.append(row_data['Мощность расчётная, Вт'])

                # «Зебра»
                is_alt = (i % 2 == 1)

                for col_idx, val in enumerate(row_for_append, 1):
                    cell = ws_corr.cell(row=row_num, column=col_idx)
                    if col_idx == 4:
                        cell.number_format = '@'
                        cell.value = str(val)
                    else:
                        cell.value = val
                    cell.font = self.DATA_FONT
                    cell.border = self.THIN_BORDER
                    if is_alt:
                        cell.fill = self.FILL_ALT
                    if col_idx in [2, 4, 5, 6, 7]:
                        cell.alignment = self.ALIGN_CENTER
                    else:
                        cell.alignment = self.ALIGN_LEFT

                art = str(row_data['Артикул LaggarTT']).strip()
                if art and art != '' and art != 'None':
                    try:
                        total_qty_corr += int(row_data['Количество'])
                    except (ValueError, TypeError):
                        pass

            # ИТОГОВАЯ СТРОКА ТАБЛИЦЫ СООТВЕТСТВИЯ
            total_row_corr = data_start_row_corr + len(processed_data)

            ws_corr.cell(row=total_row_corr, column=1, value="Итого")
            ws_corr.cell(row=total_row_corr, column=2, value=total_qty_corr)

            RED_FONT = Font(
                name='Calibri', size=11, bold=True, color="FF0000"
            )

            for col in range(1, len(corr_headers) + 1):
                cell = ws_corr.cell(row=total_row_corr, column=col)
                cell.border = self.THIN_BORDER
                cell.fill = self.FILL_TOTAL
                if col == 2 and total_qty_corr != total_qty_rad:
                    cell.font = RED_FONT
                else:
                    cell.font = self.FONT_DATA_TOTAL
                if col == 1:
                    cell.alignment = self.ALIGN_RIGHT
                else:
                    cell.alignment = self.ALIGN_CENTER

            # Двойные линии сверху и снизу
            for col in range(1, len(corr_headers) + 1):
                cell = ws_corr.cell(row=total_row_corr, column=col)
                existing_left = cell.border.left if cell.border else Side()
                existing_right = cell.border.right if cell.border else Side()
                cell.border = Border(
                    left=existing_left,
                    right=existing_right,
                    top=Side(style='double', color='263168'),
                    bottom=Side(style='double', color='263168'),
                )

            if show_calc_power_column:
                self._write_recalc_explanation_block(
                    ws_corr,
                    start_row=total_row_corr + 1,
                    delta_t=delta_t,
                    graph_str=graph_str,
                    processed_data=processed_data,
                    corr_headers=corr_headers,
                )

            column_width_rules = {
                'Оригинальное наименование':          ('long',  55, 20),
                'Количество':                          ('short', 12, 10),
                'Наименование LaggarTT':               ('long',  55, 20),
                'Артикул LaggarTT':                    ('short', 24, 20),
                'Номинальный\nтепловой поток, Вт':     ('short', 24, 20),
            }

            for col_idx, column_name in enumerate(corr_headers, 1):
                column_letter = get_column_letter(col_idx)

                rule = column_width_rules.get(column_name)
                if rule is None:
                    if 'Тепловой поток при' in str(column_name):
                        rule = ('short', 20, 16)
                    else:
                        rule = ('short', 20, 10)

                kind, max_width, min_width = rule

                max_data_len = 0
                for row_cells in ws_corr.iter_rows(min_col=col_idx, max_col=col_idx):
                    for cell in row_cells:
                        try:
                            cell_len = len(str(cell.value)) if cell.value is not None else 0
                            if cell_len > max_data_len:
                                max_data_len = cell_len
                        except Exception:
                            pass

                header_lines = str(column_name).split('\n')
                header_len = max(len(line) for line in header_lines)

                width = max(max_data_len, header_len)
                if width > max_width:
                    width = max_width
                if width < min_width:
                    width = min_width

                adjusted_width = width + 2
                ws_corr.column_dimensions[column_letter].width = adjusted_width

            ws_corr.sheet_view.showGridLines = False

        # ================================================================
        # ЛИСТ «УПАКОВОЧНЫЙ ЛИСТ»
        # ================================================================
        try:
            self._write_logistics_sheet(
                wb,
                spec_data=spec_data,
                graph_meta=graph_meta,
                program_name=program_name,
                date_str=date_str,
                project_value=project_value,
            )
        except Exception as e:
            logger.error(f"Не удалось построить лист «Упаковочный лист»: {e}")
            import traceback
            logger.error(traceback.format_exc())

        wb.save(file_path)
        logger.info(f"Спецификация сохранена: {file_path}")
    # ====================================================================
    # ЕДИНАЯ ШАПКА ДОКУМЕНТА
    # ====================================================================

    def _write_doc_header(
        self,
        ws,
        title: str,
        subtitle: str,
        program_name: str,
        date_str: str,
        left_end_col: int,
        right_start_col: int,
        right_end_col: int,
    ) -> int:
        """
        Рисует единую шапку документа:
            • Строка 1: заголовок (слева) + «Программа:» и значение (справа)
            • Строка 2: подзаголовок (слева) + «Дата формирования:» и значение (справа)
            • Строка 3: синяя линия на всю ширину

        Правый блок: подпись — в предпоследнем столбце блока,
        значение — в последнем. Оба выровнены по ПРАВОМУ краю.
        Пустые столбцы между правым блоком и заголовком
        остаются как «воздух».

        Returns:
            Номер следующей свободной строки (4).
        """
        # --- Строка 1: заголовок слева ---
        ws.merge_cells(
            start_row=1, start_column=1,
            end_row=1, end_column=left_end_col,
        )
        cell = ws.cell(row=1, column=1, value=title)
        cell.font = self.FONT_DOC_TITLE
        cell.alignment = self.ALIGN_LEFT

        # --- Строка 1: «Программа:» + значение справа ---
        # Подпись — предпоследний столбец правого блока,
        # значение — последний столбец.
        sign_col = max(right_start_col, right_end_col - 1)
        value_col = right_end_col

        cell = ws.cell(row=1, column=sign_col, value="Программа:")
        cell.font = self.FONT_META_RIGHT_K
        cell.alignment = self.ALIGN_RIGHT

        cell = ws.cell(row=1, column=value_col, value=program_name)
        cell.font = self.FONT_META_RIGHT_V
        cell.alignment = self.ALIGN_RIGHT

        # --- Строка 2: подзаголовок слева ---
        ws.merge_cells(
            start_row=2, start_column=1,
            end_row=2, end_column=left_end_col,
        )
        cell = ws.cell(row=2, column=1, value=subtitle)
        cell.font = self.FONT_DOC_SUBTITLE
        cell.alignment = self.ALIGN_LEFT

        # --- Строка 2: «Дата формирования:» + значение справа ---
        cell = ws.cell(row=2, column=sign_col, value="Дата формирования:")
        cell.font = self.FONT_META_RIGHT_K
        cell.alignment = self.ALIGN_RIGHT

        cell = ws.cell(row=2, column=value_col, value=date_str)
        cell.font = self.FONT_META_RIGHT_V
        cell.alignment = self.ALIGN_RIGHT

        # --- Строка 3: синяя линия ---
        for col in range(1, right_end_col + 1):
            ws.cell(row=3, column=col).fill = self.FILL_TH
        ws.row_dimensions[3].height = self.ROW_HEIGHT_LINE

        # --- Единые высоты строк 1 и 2 ---
        ws.row_dimensions[1].height = self.ROW_HEIGHT_TITLE
        ws.row_dimensions[2].height = self.ROW_HEIGHT_SUBTITLE

        return 4

    # ====================================================================
    # ЕДИНЫЕ МЕТА-КАРТОЧКИ
    # ====================================================================

    def _write_meta_cards(
        self,
        ws,
        start_row: int,
        cards: list,
        col_ranges: list,
        total_cols: int,
    ) -> int:
        """
        Рисует полосу мета-карточек. Единый стиль для всех листов.

        Высота строки значений автоматически рассчитывается так,
        чтобы текст полностью помещался:
            • Если в тексте есть переносы строк — высота
              рассчитывается как (кол-во переносов + 1) × 18 px.
            • Если текст длинный и не содержит переносов —
              добавляем запас исходя из длины.
        """
        row_key = start_row
        row_val = start_row + 1

        # --- Заливка фона на всю ширину листа ---
        for col in range(1, total_cols + 1):
            ws.cell(row=row_key, column=col).fill = self.FILL_META
            ws.cell(row=row_val, column=col).fill = self.FILL_META

        # --- Заполнение карточек ---
        max_val_lines = 1

        for (key_text, val_text), (c_start, c_end) in zip(cards, col_ranges):
            # Ключ
            if c_end > c_start:
                ws.merge_cells(
                    start_row=row_key, start_column=c_start,
                    end_row=row_key, end_column=c_end,
                )
            cell_k = ws.cell(row=row_key, column=c_start, value=key_text)
            cell_k.font = self.FONT_META_KEY
            cell_k.alignment = self.ALIGN_LEFT

            # Значение
            if c_end > c_start:
                ws.merge_cells(
                    start_row=row_val, start_column=c_start,
                    end_row=row_val, end_column=c_end,
                )
            cell_v = ws.cell(row=row_val, column=c_start, value=val_text)
            cell_v.font = self.FONT_META_VAL
            cell_v.alignment = self.ALIGN_LEFT_WRAP

            # Жирный синий левый бордер
            for r in (row_key, row_val):
                cell = ws.cell(row=r, column=c_start)
                cell.border = self.BORDER_META_LEFT

            # ---------- Расчёт высоты ----------
            text_str = str(val_text) if val_text is not None else ""

            # Сколько уже есть «физических» строк в тексте
            physical_lines = text_str.split("\n")
            num_physical = len(physical_lines)

            # Сколько символов в самой длинной физической строке
            max_phys_len = max((len(p) for p in physical_lines), default=0)

            # Оценка ширины карточки в символах:
            # одна ширина столбца Excel ~ 8 символов шрифта 12 pt.
            # Но у нас столбцы разной ширины — возьмём эмпирически:
            # 1 столбец шапки ~ 20 символов.
            width_cols = c_end - c_start + 1
            estimated_chars = max(20, width_cols * 20)

            # Сколько дополнительных строк нужно на самую длинную
            # физическую строку
            if max_phys_len > estimated_chars:
                extra_wraps = (max_phys_len + estimated_chars - 1) // estimated_chars
            else:
                extra_wraps = 1

            # Итого строк для этой карточки
            lines_needed = num_physical + (extra_wraps - 1)

            if lines_needed > max_val_lines:
                max_val_lines = lines_needed

        # --- Единые высоты строк ---
        ws.row_dimensions[row_key].height = self.ROW_HEIGHT_META_KEY

        # Базовая высота одной строки — 22 px.
        # Каждая дополнительная строка добавляет 18 px.
        line_height = 18
        val_height = self.ROW_HEIGHT_META_VAL + (max_val_lines - 1) * line_height
        ws.row_dimensions[row_val].height = val_height

        return start_row + 2

    # ====================================================================
    # ЛИСТ «УПАКОВОЧНЫЙ ЛИСТ»
    # ====================================================================

    def _write_logistics_sheet(
        self,
        wb,
        spec_data: pd.DataFrame,
        graph_meta: dict,
        program_name: str,
        date_str: str,
        project_value: str = "—",
    ) -> None:
        """Создаёт третий лист «Упаковочный лист»."""
        import math

        # ---- Считаем паллеты ----
        calc = PalletCalculator(self.data_provider)
        calc_df = calc.calculate_for_spec(spec_data)

        # ---- Удаляем старый лист, если был ----
        if "Упаковочный лист" in wb.sheetnames:
            std = wb["Упаковочный лист"]
            wb.remove(std)

        ws = wb.create_sheet("Упаковочный лист")

        supply = graph_meta.get("supply", 95)
        ret    = graph_meta.get("return", 85)
        room   = graph_meta.get("room",   20)
        delta_t = graph_meta.get("delta_t", 70.0)
        graph_str = f"{supply}/{ret}/{room}"
        delta_str = f"{delta_t:.1f}".replace('.', ',')

        # ================================================================
        # ШАПКА ДОКУМЕНТА
        # ================================================================
        self._write_doc_header(
            ws,
            title="УПАКОВОЧНЫЙ ЛИСТ",
            subtitle="Приложение к спецификации радиаторов LaggarTT",
            program_name=program_name,
            date_str=date_str,
            left_end_col=6,
            right_start_col=7,
            right_end_col=11,
        )

        # ================================================================
        # МЕТА-КАРТОЧКИ
        # ================================================================
        self._write_meta_cards(
            ws,
            start_row=4,
            cards=[
                ("ТЕМПЕРАТУРНЫЙ ГРАФИК",
                 f"{graph_str} °С (Δt = {delta_str} °С)"),
                ("ПРОЕКТ", project_value),
            ],
            col_ranges=[(1, 3), (4, 11)],
            total_cols=11,
        )

        # ================================================================
        # ТАБЛИЦА
        # ================================================================
        header_top_row = 7
        header_sub_row = 8
        ws.row_dimensions[header_top_row].height = 34
        ws.row_dimensions[header_sub_row].height = 24

        top_headers = [
            (1, 1, "№\nпоз."),
            (2, 2, "Код\nизделия"),
            (3, 3, "Наименование изделия"),
            (4, 4, "Длина,\nмм"),
            (5, 5, "Норма\nзагрузки,\nшт/пал."),
            (6, 6, "Количество\nпаллет, шт"),
            (7, 7, "Количество\nрадиаторов, шт"),
            (8, 10, "МАССА, КГ"),
            (11, 11, "Масса\nбрутто,\nкг"),
        ]

        for col_start, col_end, text in top_headers:
            if col_start != col_end:
                ws.merge_cells(
                    start_row=header_top_row, start_column=col_start,
                    end_row=header_top_row, end_column=col_end,
                )
            cell = ws.cell(row=header_top_row, column=col_start, value=text)
            cell.font = self.FONT_TH
            cell.fill = self.FILL_TH
            cell.alignment = Alignment(
                horizontal='center', vertical='center', wrap_text=True
            )
            for c in range(col_start, col_end + 1):
                ws.cell(row=header_top_row, column=c).fill = self.FILL_TH
                ws.cell(row=header_top_row, column=c).border = self.BORDER_WHITE

        sub_headers = [
            (8,  "одного\nрадиатора"),
            (9,  "радиаторов"),
            (10, "паллет"),
        ]

        for col, text in sub_headers:
            cell = ws.cell(row=header_sub_row, column=col, value=text)
            cell.font = self.FONT_TH_SUB
            cell.fill = self.FILL_TH
            cell.alignment = Alignment(
                horizontal='center', vertical='center', wrap_text=True
            )
            cell.border = self.BORDER_WHITE

        for col in [1, 2, 3, 4, 5, 6, 7, 11]:
            ws.merge_cells(
                start_row=header_top_row, start_column=col,
                end_row=header_sub_row, end_column=col,
            )
            cell = ws.cell(row=header_sub_row, column=col)
            cell.fill = self.FILL_TH
            cell.border = self.BORDER_WHITE

        # ================================================================
        # ДАННЫЕ — С ОКРУГЛЕНИЕМ ПАЛЛЕТ ВВЕРХ
        # ================================================================
        data_start = header_sub_row + 1
        approximate_count = 0
        approximate_qty = 0
        approximate_pallets = 0
        rows_for_totals = []

        for i, (_, row) in enumerate(calc_df.iterrows()):
            r = data_start + i

            try:
                pallets_drob = float(row.get("Паллет, шт", 0) or 0)
            except (ValueError, TypeError):
                pallets_drob = 0.0
            pallets_int = math.ceil(pallets_drob) if pallets_drob > 0 else 0

            weight_pallets_int = round(pallets_int * 15.0, 2)

            try:
                weight_total = float(row.get("Вес общий, кг", 0) or 0)
            except (ValueError, TypeError):
                weight_total = 0.0
            weight_with_pallets_int = round(weight_total + weight_pallets_int, 2)

            length_val = row.get("Длина, мм", "")
            try:
                length_int = int(length_val) if length_val != "" else 0
            except (ValueError, TypeError):
                length_int = 0

            rad_type, height, _ = PalletCalculator._extract_params_from_name(
                str(row.get("Наименование", ""))
            )
            is_approx = (
                rad_type is not None
                and height is not None
                and length_int > 2000
            )
            if is_approx:
                approximate_count += 1
                try:
                    approximate_qty += int(row.get("Кол-во", 0) or 0)
                except (ValueError, TypeError):
                    pass
                approximate_pallets += pallets_int

            rows_for_totals.append({
                "length": length_int,
                "pallets_int": pallets_int,
                "weight_total": weight_total,
                "weight_pallets_int": weight_pallets_int,
                "weight_with_pallets_int": weight_with_pallets_int,
            })

            ws.cell(row=r, column=1, value=i + 1)
            # Код изделия — как ТЕКСТ
            art_cell = ws.cell(row=r, column=2)
            art_cell.number_format = '@'
            art_cell.value = str(row.get("Артикул", ""))
            art_cell.data_type = 's'
            ws.cell(row=r, column=3, value=row.get("Наименование", ""))
            ws.cell(row=r, column=4, value=row.get("Длина, мм", ""))

            on_pallet_val = row.get("На паллете, шт", "")
            if is_approx and on_pallet_val != "":
                on_pallet_str = f"{on_pallet_val} *"
            else:
                on_pallet_str = str(on_pallet_val) if on_pallet_val != "" else ""
            ws.cell(row=r, column=5, value=on_pallet_str)

            ws.cell(row=r, column=6, value=pallets_int)
            ws.cell(row=r, column=7, value=row.get("Кол-во", 0))
            ws.cell(row=r, column=8, value=row.get("Вес 1, кг", 0))
            ws.cell(row=r, column=9, value=weight_total)
            ws.cell(row=r, column=10, value=weight_pallets_int)
            ws.cell(row=r, column=11, value=weight_with_pallets_int)

            for col in range(1, 12):
                cell = ws.cell(row=r, column=col)
                cell.font = self.FONT_DATA_MONO if col == 2 else self.FONT_DATA
                cell.border = self.THIN_BORDER
                if col in (1, 4, 5, 6, 7):
                    cell.alignment = self.ALIGN_CENTER
                elif col in (8, 9, 10, 11):
                    cell.alignment = self.ALIGN_RIGHT
                    cell.number_format = '#,##0.00'
                else:
                    cell.alignment = self.ALIGN_LEFT

                if i % 2 == 1:
                    cell.fill = self.FILL_ALT

        # ================================================================
        # ИТОГОВАЯ СТРОКА ТАБЛИЦЫ
        # ================================================================
        total_row_table = data_start + len(calc_df)

        total_qty_rad = sum(int(row.get("Кол-во", 0) or 0) for _, row in calc_df.iterrows())
        total_brutto = sum(r["weight_with_pallets_int"] for r in rows_for_totals)

        # Объединение A:F — подпись
        ws.merge_cells(
            start_row=total_row_table, start_column=1,
            end_row=total_row_table, end_column=6,
        )
        cell = ws.cell(row=total_row_table, column=1, value="ИТОГО по документу:")
        cell.font = self.FONT_DATA_TOTAL
        cell.alignment = self.ALIGN_RIGHT
        cell.fill = self.FILL_TOTAL
        cell.border = self.THIN_BORDER

        for c in range(1, 7):
            cc = ws.cell(row=total_row_table, column=c)
            cc.fill = self.FILL_TOTAL
            cc.border = self.THIN_BORDER

        # Ячейка G — количество радиаторов
        ws.cell(row=total_row_table, column=7, value=total_qty_rad)
        cell = ws.cell(row=total_row_table, column=7)
        cell.font = self.FONT_DATA_TOTAL
        cell.alignment = self.ALIGN_CENTER
        cell.fill = self.FILL_TOTAL
        cell.border = self.THIN_BORDER

        # Объединение H:J — пустые ячейки под «МАССА, КГ»
        ws.merge_cells(
            start_row=total_row_table, start_column=8,
            end_row=total_row_table, end_column=10,
        )
        for c in range(8, 11):
            cc = ws.cell(row=total_row_table, column=c)
            cc.fill = self.FILL_TOTAL
            cc.border = self.THIN_BORDER

        # Ячейка K — масса брутто
        ws.cell(row=total_row_table, column=11, value=round(total_brutto, 2))
        cell = ws.cell(row=total_row_table, column=11)
        cell.font = self.FONT_DATA_TOTAL
        cell.alignment = self.ALIGN_RIGHT
        cell.number_format = '#,##0.00'
        cell.fill = self.FILL_TOTAL
        cell.border = self.THIN_BORDER

        # Двойные линии сверху и снизу — на A:K
        for c in range(1, 12):
            cell = ws.cell(row=total_row_table, column=c)
            existing_left = cell.border.left if cell.border else Side()
            existing_right = cell.border.right if cell.border else Side()
            cell.border = Border(
                left=existing_left,
                right=existing_right,
                top=Side(style='double', color='263168'),
                bottom=Side(style='double', color='263168'),
            )

        # ================================================================
        # СНОСКА ПОД ТАБЛИЦЕЙ
        # ================================================================
        if approximate_count > 0:
            footnote_row = total_row_table + 2

            ws.merge_cells(
                start_row=footnote_row, start_column=1,
                end_row=footnote_row, end_column=11,
            )
            footnote_text = (
                "* — количество радиаторов на паллете для изделий длиной более "
                "2000 мм указано приблизительно и требует уточнения у поставщика."
            )
            cell = ws.cell(row=footnote_row, column=1, value=footnote_text)
            cell.font = self.FONT_FOOTNOTE
            cell.alignment = self.ALIGN_LEFT

            totals_start = footnote_row + 2
        else:
            totals_start = total_row_table + 2

        # ================================================================
        # ИТОГИ УПАКОВКИ
        # ================================================================
        pallets_short_int = sum(
            r["pallets_int"] for r in rows_for_totals
            if 0 < r["length"] <= 1200
        )
        pallets_long_int = sum(
            r["pallets_int"] for r in rows_for_totals
            if r["length"] > 1200
        )
        total_pallets_int = pallets_short_int + pallets_long_int

        floor_meters = math.ceil(pallets_short_int / 2) + pallets_long_int

        if floor_meters > 0:
            trucks = math.ceil(floor_meters / 13.0)
        else:
            trucks = 0

        total_weight_kg = sum(r["weight_with_pallets_int"] for r in rows_for_totals)
        total_weight_t = total_weight_kg / 1000.0

        if trucks > 0:
            weight_per_truck_t = (total_weight_kg / trucks) / 1000.0
        else:
            weight_per_truck_t = 0.0

        ws.merge_cells(
            start_row=totals_start, start_column=1,
            end_row=totals_start, end_column=11,
        )
        cell = ws.cell(row=totals_start, column=1, value="ИТОГИ УПАКОВКИ")
        cell.font = self.FONT_TOTALS_SECTION
        cell.fill = self.FILL_TH
        cell.alignment = self.ALIGN_CENTER
        ws.row_dimensions[totals_start].height = 22

        for c in range(1, 12):
            ws.cell(row=totals_start, column=c).border = self.THIN_BORDER
            ws.cell(row=totals_start, column=c).fill = self.FILL_TH

        def plural_fura(n: int) -> str:
            n_abs = abs(int(n))
            last_two = n_abs % 100
            last_one = n_abs % 10
            if 11 <= last_two <= 14:
                return "фур"
            if last_one == 1:
                return "фура"
            if 2 <= last_one <= 4:
                return "фуры"
            return "фур"

        def write_group(r, text):
            ws.merge_cells(
                start_row=r, start_column=1,
                end_row=r, end_column=11,
            )
            cell = ws.cell(row=r, column=1, value=text.upper())
            cell.font = self.FONT_TOTALS_GROUP
            cell.fill = self.FILL_GROUP
            cell.alignment = self.ALIGN_LEFT
            for c in range(1, 12):
                ws.cell(row=r, column=c).border = self.THIN_BORDER
                ws.cell(row=r, column=c).fill = self.FILL_GROUP
            ws.row_dimensions[r].height = 20

        def write_row(r, label, value, note):
            ws.merge_cells(
                start_row=r, start_column=1,
                end_row=r, end_column=3,
            )
            cell_l = ws.cell(row=r, column=1, value=label)
            cell_l.font = self.FONT_TOTALS_LBL
            cell_l.alignment = self.ALIGN_LEFT_WRAP

            ws.merge_cells(
                start_row=r, start_column=4,
                end_row=r, end_column=5,
            )
            cell_v = ws.cell(row=r, column=4, value=value)
            cell_v.font = self.FONT_TOTALS_VAL
            cell_v.alignment = self.ALIGN_RIGHT

            ws.merge_cells(
                start_row=r, start_column=6,
                end_row=r, end_column=11,
            )
            cell_n = ws.cell(row=r, column=6, value=note)
            cell_n.font = self.FONT_TOTALS_NOTE
            cell_n.alignment = self.ALIGN_LEFT_WRAP

            for c in range(1, 12):
                ws.cell(row=r, column=c).border = self.THIN_BORDER

            ws.row_dimensions[r].height = 30

        row_idx = totals_start + 1

        write_group(row_idx, "Грузовые места (паллеты)")
        row_idx += 1

        write_row(row_idx,
                  "Паллет с короткими радиаторами (длина ≤ 1200 мм)",
                  f"{pallets_short_int} шт",
                  "Сумма паллет по всем радиаторам с длиной до 1200 мм включительно.")
        row_idx += 1

        write_row(row_idx,
                  "Паллет с длинными радиаторами (длина > 1200 мм)",
                  f"{pallets_long_int} шт",
                  "Сумма паллет по всем радиаторам с длиной более 1200 мм.")
        row_idx += 1

        write_row(row_idx,
                  "Всего грузовых мест",
                  f"{total_pallets_int} шт",
                  "Общее количество паллет для всей отгрузки.")
        row_idx += 1

        write_group(row_idx, "Размещение в фуре")
        row_idx += 1

        write_row(row_idx,
                  "Занимаемая длина пола фуры",
                  f"{floor_meters} м",
                  f"Короткие паллеты штабелируются по 2 в высоту "
                  f"({pallets_short_int} / 2 = {math.ceil(pallets_short_int / 2)}), "
                  f"длинные устанавливаются по 1 ({pallets_long_int}). "
                  f"Итого {math.ceil(pallets_short_int / 2)} + "
                  f"{pallets_long_int} = {floor_meters} м.")
        row_idx += 1

        write_row(row_idx,
                  "Требуется фур (длина 13 м)",
                  f"{trucks} {plural_fura(trucks)}",
                  f"Расчёт по длине пола фуры: {floor_meters} / 13 ≈ "
                  f"{floor_meters / 13:.2f} → округление до {trucks}.")
        row_idx += 1

        write_group(row_idx, "Масса груза")
        row_idx += 1

        write_row(row_idx,
                  "Общая масса груза с паллетами",
                  f"{total_weight_t:.3f}".replace('.', ',') + " т",
                  "Масса радиаторов + масса деревянных паллет (по 15 кг каждая).")
        row_idx += 1

        write_row(row_idx,
                  "Средняя масса на одну фуру",
                  f"{weight_per_truck_t:.3f}".replace('.', ',') + " т",
                  f"Общая масса груза / количество фур "
                  f"({total_weight_t:.3f} / {trucks}). "
                  f"Норма для фуры 13 м — не более 20 т.")
        row_idx += 1

        if approximate_count > 0:
            write_group(row_idx, "Примечания")
            row_idx += 1

            write_row(row_idx,
                      "Позиций с приблизительными данными — строк в таблице",
                      f"{approximate_count}",
                      "Строки с радиаторами длиной более 2000 мм.")
            row_idx += 1

            write_row(row_idx,
                      "Позиций с приблизительными данными — радиаторов всего",
                      f"{approximate_qty} шт",
                      "Суммарное количество радиаторов в этих строках.")
            row_idx += 1

            write_row(row_idx,
                      "Позиций с приблизительными данными — паллет (по ним)",
                      f"{approximate_pallets} шт",
                      "Суммарное количество паллет по этим строкам "
                      "(округлённое вверх).")
            row_idx += 1

        # ================================================================
        # ЮРИДИЧЕСКИЙ ДИСКЛЕЙМЕР
        # ================================================================
        disclaimer_row = row_idx + 1

        ws.merge_cells(
            start_row=disclaimer_row, start_column=1,
            end_row=disclaimer_row + 2, end_column=11,
        )
        disclaimer_text = (
            "Настоящий документ сформирован автоматически и носит "
            "информационный характер. Расчётные значения упаковки, массы "
            "брутто, количества паллет и грузовых мест являются "
            "ориентировочными и могут отличаться от фактических. "
            "Окончательные параметры отгрузки согласовываются с поставщиком. "
            "Программа NexTT не несёт ответственности за возможные расхождения."
        )
        cell = ws.cell(row=disclaimer_row, column=1, value=disclaimer_text)
        cell.font = self.FONT_DISCLAIMER
        cell.alignment = self.ALIGN_LEFT_TOP_WRAP

        for r in (disclaimer_row, disclaimer_row + 1, disclaimer_row + 2):
            for c in range(1, 12):
                ws.cell(row=r, column=c).border = Border()

        # ================================================================
        # ШИРИНА СТОЛБЦОВ
        # ================================================================
        widths = {
            'A': 6,   'B': 14,  'C': 55,  'D': 10,  'E': 11,
            'F': 12,  'G': 12,  'H': 11,  'I': 12,  'J': 11,  'K': 12,
        }
        for col_letter, width in widths.items():
            ws.column_dimensions[col_letter].width = width

        ws.sheet_view.showGridLines = False
    # ====================================================================
    # БЛОК ПОЯСНЕНИЯ РАСЧЁТА
    # ====================================================================

    def _write_recalc_explanation_block(
        self,
        ws,
        start_row: int,
        delta_t: float,
        graph_str: str,
        processed_data: list,
        corr_headers: list,
    ) -> None:
        """
        Блок пояснения расчёта теплового потока.

        Три секции:
            1. Формула пересчёта + пояснение переменных.
            2. Таблица экспонентов по типам радиаторов.
            3. Пример расчёта для первого радиатора из таблицы.

        Все секции — без заливки фона.
        Формула выделена моноширинным шрифтом.
        """
        TITLE_FONT = Font(name='Calibri', size=12, bold=True, color="263168")
        SECTION_FONT = Font(name='Calibri', size=11, bold=True, color="263168")
        TEXT_FONT = Font(name='Calibri', size=11, color="1A2456")
        ITALIC_FONT = Font(
            name='Calibri', size=10, italic=True, color="5B6779"
        )
        MONO_FONT = Font(
            name='Consolas', size=10, color="1A2456"
        )
        TABLE_HEADER_FONT = Font(name='Calibri', size=10, bold=True, color="1A2456")
        TABLE_DATA_FONT = Font(name='Calibri', size=10, color="1A2456")
        RESULT_FONT = Font(name='Calibri', size=11, bold=True, color="263168")

        TABLE_HEADER_FILL = PatternFill(
            start_color="E8E8E8", end_color="E8E8E8", fill_type="solid"
        )

        align_left = Alignment(horizontal='left', vertical='center')
        align_center = Alignment(horizontal='center', vertical='center')

        # Отступ: одна пустая строка между итоговой строкой и блоком
        row = start_row + 1

        # ================================================================
        # ЗАГОЛОВОК БЛОКА
        # ================================================================
        ws.cell(
            row=row, column=1,
            value="РАСЧЁТ ТЕПЛОВОГО ПОТОКА ПРИ ТЕКУЩЕМ ГРАФИКЕ"
        ).font = TITLE_FONT
        row += 1

        # Строка с графиком
        delta_display = f"{delta_t:.2f}".replace('.', ',')
        graph_line = (
            f"Температурный график: {graph_str} °С   "
            f"(Δt = {delta_display} °С)"
        )
        ws.cell(row=row, column=1, value=graph_line).font = TEXT_FONT
        row += 2  # пустая строка перед секцией 1

        # ================================================================
        # СЕКЦИЯ 1. ФОРМУЛА ПЕРЕСЧЁТА
        # ================================================================
        ws.cell(
            row=row, column=1,
            value="1. Формула пересчёта"
        ).font = SECTION_FONT
        row += 1

        # Формула
        ws.cell(
            row=row, column=1,
            value="Q = Qном × (Δt / 70)ⁿ"
        ).font = MONO_FONT
        row += 1

        # Пояснения переменных (курсивом)
        note_lines = [
            "где Qном — паспортная мощность при 95/85/20 (Δt = 70 °С);",
            "      Δt — текущий температурный напор;",
            "      n — экспонент типа радиатора.",
        ]
        for line in note_lines:
            ws.cell(row=row, column=1, value=line).font = ITALIC_FONT
            row += 1

        row += 1  # пустая строка перед секцией 2

        # ================================================================
        # СЕКЦИЯ 2. ТАБЛИЦА ЭКСПОНЕНТОВ
        # ================================================================
        ws.cell(
            row=row, column=1,
            value="2. Экспоненты n по типам радиаторов"
        ).font = SECTION_FONT
        row += 1

        from nextt.core.power_recalculator import EXPONENTS, VALID_TYPES

        exponents_500 = EXPONENTS.get(500, {})

        # Заголовок таблицы: Тип | n
        cell = ws.cell(row=row, column=1, value="Тип")
        cell.font = TABLE_HEADER_FONT
        cell.fill = TABLE_HEADER_FILL
        cell.border = self.THIN_BORDER
        cell.alignment = align_center

        cell = ws.cell(row=row, column=2, value="n")
        cell.font = TABLE_HEADER_FONT
        cell.fill = TABLE_HEADER_FILL
        cell.border = self.THIN_BORDER
        cell.alignment = align_center
        row += 1

        for rt in VALID_TYPES:
            n_val = exponents_500.get(rt, 1.0)
            n_str = f"{n_val:.2f}".replace('.', ',')

            cell_type = ws.cell(row=row, column=1, value=str(rt))
            cell_type.font = TABLE_DATA_FONT
            cell_type.border = self.THIN_BORDER
            cell_type.alignment = align_center

            cell_n = ws.cell(row=row, column=2, value=n_str)
            cell_n.font = TABLE_DATA_FONT
            cell_n.border = self.THIN_BORDER
            cell_n.alignment = align_center

            row += 1

        row += 1  # пустая строка перед секцией 3

        # ================================================================
        # СЕКЦИЯ 3. ПРИМЕР РАСЧЁТА
        # ================================================================
        ws.cell(
            row=row, column=1,
            value="3. Пример для радиатора из таблицы"
        ).font = SECTION_FONT
        row += 1

        example = self._pick_example_radiator(processed_data)
        if example is None:
            ws.cell(
                row=row, column=1,
                value="(подходящий радиатор не найден)"
            ).font = ITALIC_FONT
            return

        art, name, qnom, rad_type, height = example

        # Извлекаем экспонент
        n_value = exponents_500.get(rad_type, 1.0)
        n_str = f"{n_value:.2f}".replace('.', ',')
        factor = (delta_t / 70.0) ** n_value if delta_t > 0 else 1.0
        factor_str = f"{factor:.3f}".replace('.', ',')

        q_calc = qnom * factor
        q_calc_int = int(round(q_calc))
        qnom_int = int(round(qnom))
        delta_int_str = f"{delta_t:.0f}"

        # Короткое наименование: убираем «Радиатор LaggarTT Classic»
        short_name = name
        for prefix in ("Радиатор LaggarTT Classic ", "Радиатор LaggarTT ",
                       "Радиатор "):
            if short_name.startswith(prefix):
                short_name = short_name[len(prefix):]
                break

        # Строки данных примера: подпись в A, значение в B
        rows_data = [
            ("Артикул", art),
            ("Наименование", short_name),
            ("Qном (паспорт)", f"{qnom_int} Вт"),
            ("Тип / высота", f"{rad_type} / {height} мм"),
            ("Экспонент n", n_str),
            ("Коэффициент", f"({delta_int_str}/70)^{n_str} = {factor_str}"),
        ]

        for label, value in rows_data:
            cell_label = ws.cell(row=row, column=1, value=label)
            cell_label.font = TEXT_FONT
            cell_label.alignment = align_left

            cell_value = ws.cell(row=row, column=2, value=value)
            cell_value.font = MONO_FONT
            cell_value.alignment = align_left
            row += 1

        # Результат — с отступом и жирным шрифтом
        row += 1

        cell_label = ws.cell(
            row=row, column=1,
            value="Тепловой поток Q"
        )
        cell_label.font = RESULT_FONT
        cell_label.alignment = align_left

        result_text = (
            f"{qnom_int} × {factor_str} ≈ {q_calc_int} Вт"
        )
        cell_value = ws.cell(row=row, column=2, value=result_text)
        cell_value.font = RESULT_FONT
        cell_value.alignment = align_left
        row += 1

    def _pick_example_radiator(self, processed_data: list):
        """Выбирает первый радиатор, для которого есть все данные."""
        for row_data in processed_data:
            art = str(row_data.get('Артикул LaggarTT', '')).strip()
            if not art or art == 'None':
                continue

            power_nom_raw = row_data.get('Мощность паспортная, Вт', '')
            if power_nom_raw == '' or power_nom_raw is None:
                continue
            try:
                qnom = float(power_nom_raw)
            except (ValueError, TypeError):
                continue

            name = str(row_data.get('Наименование LaggarTT', ''))
            rad_type = self._extract_type_from_name(name)
            height = self._extract_height_from_name(name)

            if rad_type is None or height is None:
                continue

            return (art, name, qnom, rad_type, height)

        return None

    # ====================================================================
    # РАСЧЁТ ВЕСА И ОБЪЁМА
    # ====================================================================

    def _calculate_total_weight_and_volume(self, spec_data: pd.DataFrame) -> Tuple[float, float]:
        """Рассчитывает общий вес и объём радиаторов (без кронштейнов)."""
        total_weight = 0.0
        total_volume = 0.0

        if self.data_provider is None:
            return round(total_weight, 1), round(total_volume, 3)

        radiators_df = self.data_provider.radiators_df

        for _, row in spec_data.iterrows():
            if "Кронштейн" in str(row.get("Наименование", "")):
                continue

            art = str(row.get("Артикул", "")).strip()
            if not art:
                continue

            try:
                qty = int(row.get("Кол-во", 0))
                if qty <= 0:
                    continue
            except (ValueError, TypeError):
                continue

            mask = radiators_df['Артикул'].astype(str).str.strip() == art
            if mask.any():
                product = radiators_df[mask].iloc[0]
                total_weight += float(product.get('Вес, кг', 0)) * qty
                total_volume += float(product.get('Объем, м3', 0)) * qty

        return round(total_weight, 1), round(total_volume, 3)

    def _calculate_total_brackets_weight(self, spec_data: pd.DataFrame) -> float:
        """Считает суммарный вес кронштейнов."""
        total_weight = 0.0

        if self.data_provider is None:
            return 0.0

        brackets_df = self.data_provider.brackets_df
        if brackets_df.empty:
            return 0.0

        for _, row in spec_data.iterrows():
            if "Кронштейн" not in str(row.get("Наименование", "")):
                continue

            art = str(row.get("Артикул", "")).strip()
            if not art:
                continue

            try:
                qty = int(row.get("Кол-во", 0))
                if qty <= 0:
                    continue
            except (ValueError, TypeError):
                continue

            mask = brackets_df['Артикул'].astype(str).str.strip() == art
            if mask.any():
                b_info = brackets_df[mask].iloc[0]
                try:
                    weight = float(b_info.get('Вес, кг', 0))
                except (ValueError, TypeError):
                    weight = 0.0
                total_weight += weight * qty

        return round(total_weight, 2)

    # ====================================================================
    # ПОИСК МОЩНОСТИ ПО АРТИКУЛУ
    # ====================================================================

    def _find_power_by_article(self, article: str):
        """Находит паспортную мощность радиатора по артикулу."""
        if not article or not self.data_provider:
            return ""
        found = self.data_provider.find_by_article(article)
        if found is not None:
            power = found.get('Мощность, Вт', '')
            try:
                if pd.isna(power):
                    return ""
                return float(power)
            except (ValueError, TypeError):
                return str(power) if not pd.isna(power) else ""
        return ""

    def _get_power_data_by_article(self, article: str, delta_t: float) -> Tuple:
        """Возвращает кортеж (паспортная_мощность, расчётная_мощность)."""
        if not article or not self.data_provider:
            return "", ""

        found = self.data_provider.find_by_article(article)
        if found is None:
            return "", ""

        power_nom_raw = found.get('Мощность, Вт', '')
        if pd.isna(power_nom_raw) or power_nom_raw == '':
            return "", ""

        try:
            power_nom = float(power_nom_raw)
        except (ValueError, TypeError):
            return "", ""

        name = str(found.get('Наименование', ''))
        rad_type = self._extract_type_from_name(name)
        height = self._extract_height_from_name(name)

        if rad_type is None or height is None:
            logger.debug(
                f"_get_power_data_by_article: не удалось извлечь параметры "
                f"для артикула {article} ('{name}')"
            )
            return power_nom, power_nom

        power_calc = PowerRecalculator.recalc_power(
            power_nom, rad_type, height, delta_t
        )

        if PowerRecalculator.is_reference(delta_t):
            power_calc_out = int(round(power_nom))
        else:
            power_calc_out = int(round(power_calc))

        return power_nom, power_calc_out

    def _extract_type_from_name(self, name: str) -> Optional[str]:
        """Извлекает тип радиатора из наименования."""
        patterns = [
            r'/(\d{2})/',
            r'Profil\s*(\d{2})',
            r'тип\s*(\d{2})',
            r'(\d{2})\s*[/\-]',
        ]
        for pattern in patterns:
            match = re.search(pattern, name, re.IGNORECASE)
            if match:
                rt = match.group(1)
                if rt in ['10', '11', '20', '21', '22', '30', '33']:
                    return rt
        return None

    def _extract_height_from_name(self, name: str) -> Optional[int]:
        """Извлекает высоту радиатора из наименования."""
        match = re.search(r'/(\d{3})/', name)
        if match:
            h = int(match.group(1))
            if h in [300, 400, 500, 600, 900]:
                return h
        return None

    # ====================================================================
    # БЛОК «ДОПОЛНИТЕЛЬНЫЕ СВЕДЕНИЯ»
    # ====================================================================

    def _write_additional_info_block(
        self,
        ws,
        start_row: int,
        weight_rad_str: str,
        weight_br_str: str,
        volume_str: str,
        power_str: str,
    ) -> int:
        """
        Блок «Дополнительные сведения (нетто)».

        Заголовок — курсивом, без подчёркивания, с двоеточием.
        Каждая строка данных имеет маркер «✓» в столбце A.
        Подпись — в B:C (объединены), значение — в D.
        Нижняя тонкая линия — под каждой строкой.

        Returns:
            Номер следующей свободной строки.
        """
        title_font = Font(
            name='Calibri', size=11, italic=True,
        )
        row_font = Font(name='Calibri', size=11)
        marker_font = Font(
            name='Calibri', size=11, bold=True, color="263168",
        )

        align_left_B = Alignment(horizontal='left', vertical='center')
        align_left_D = Alignment(horizontal='left', vertical='center')
        align_center_A = Alignment(horizontal='center', vertical='center')

        bottom_border = Border(
            bottom=Side(style='thin', color='808080'),
        )

        # --- Заголовок: A:C, курсив, с двоеточием ---
        ws.merge_cells(
            start_row=start_row, start_column=1,
            end_row=start_row, end_column=3,
        )
        cell = ws.cell(
            row=start_row, column=1,
            value="Дополнительные сведения (нетто):",
        )
        cell.font = title_font
        cell.alignment = align_left_B

        # Данные — без двоеточий в подписях
        rows_data = [
            ("Вес радиаторов", weight_rad_str),
            ("Вес кронштейнов", weight_br_str),
            ("Объём радиаторов", volume_str + " м³"),
            ("Суммарная мощность", power_str),
        ]

        for i, (label, value) in enumerate(rows_data):
            r = start_row + 1 + i

            # Маркер «✓» в столбце A
            cell_marker = ws.cell(row=r, column=1, value="✓")
            cell_marker.font = marker_font
            cell_marker.alignment = align_center_A

            # Подпись — B:C (объединены)
            ws.merge_cells(
                start_row=r, start_column=2,
                end_row=r, end_column=3,
            )
            cell_label = ws.cell(row=r, column=2, value=label)
            cell_label.font = row_font
            cell_label.alignment = align_left_B

            # Значение — D
            cell_value = ws.cell(row=r, column=4, value=value)
            cell_value.font = row_font
            cell_value.alignment = align_left_D

            # Нижняя линия под строкой — на все ячейки A:D
            for col in range(1, 5):
                cc = ws.cell(row=r, column=col)
                cc.border = bottom_border

        return start_row + len(rows_data)
    # ====================================================================
    # БЛОК «КОМПЛЕКТАЦИЯ»
    # ====================================================================

    def _detect_connection_kinds_in_spec(self, spec_data) -> List[str]:
        """Определяет, какие типы подключения радиаторов есть в спецификации."""
        order: List[str] = []

        for _, row in spec_data.iterrows():
            name = str(row.get("Наименование", ""))
            if not name:
                continue

            if "Кронштейн" in name:
                continue

            kind = self._detect_connection_kind_by_name(name)
            if kind and kind not in order:
                order.append(kind)

        return order

    @staticmethod
    def _detect_connection_kind_by_name(name: str) -> Optional[str]:
        """Определяет тип подключения по наименованию радиатора."""
        name_low = name.lower()

        if "ventil hygiene (hv)" in name_low:
            return "HV"
        if "hygiene (h)" in name_low:
            return "H"

        if "vk-profil" in name_low or "vk profil" in name_low:
            return "VK"
        if "k-profil" in name_low or "k profil" in name_low:
            return "K"

        return None

    def _write_kit_block(
        self,
        ws,
        start_row: int,
        spec_data,
    ) -> int:
        """
        Блок «Комплектация».

        Заголовок «Комплектация» — курсивом, без подчёркивания.
        Заголовок раздела «В комплект поставки… входят:» — курсив,
        с жирными курсивными вставками («нижним подключением» и т.п.),
        с двоеточием в конце.

        Строки состава:
          • маркер «•» в столбце A (по центру);
          • описание — в B:C (с wrap_text для длинных);
          • D — количество;
          • нижняя граница A:D;
          • вертикальная граница слева в столбце D.

        Длинная строка нижнего подключения:
          • объединение A на 3 строки, маркер «•» по центру;
          • объединение B:C на 3 строки;
          • D — на 3 строки.

        Returns:
            Номер последней использованной строки.
        """
        from openpyxl.cell.rich_text import CellRichText, TextBlock
        from openpyxl.cell.text import InlineFont

        title_font = Font(
            name='Calibri', size=11, italic=True,
        )
        marker_font = Font(
            name='Calibri', size=11, bold=True, color="263168",
        )

        section_font_italic = InlineFont(
            rFont='Calibri', sz=11, b=False, i=True
        )
        section_font_italic_bold = InlineFont(
            rFont='Calibri', sz=11, b=True, i=True
        )

        row_font = Font(name='Calibri', size=11)

        align_left_B = Alignment(horizontal='left', vertical='center')
        align_left_D = Alignment(horizontal='left', vertical='center')
        align_right_D = Alignment(horizontal='right', vertical='center')
        align_center_A = Alignment(horizontal='center', vertical='center')
        align_left_B_wrap = Alignment(
            horizontal='left', vertical='center', wrap_text=True,
        )

        bottom_border = Border(
            bottom=Side(style='thin', color='808080'),
        )
        left_border_col_D = Border(
            left=Side(style='thin', color='808080'),
        )
        bottom_left_border = Border(
            bottom=Side(style='thin', color='808080'),
            left=Side(style='thin', color='808080'),
        )

        # --- Заголовок «Комплектация»: A:C, курсив ---
        ws.merge_cells(
            start_row=start_row, start_column=1,
            end_row=start_row, end_column=3,
        )
        cell = ws.cell(row=start_row, column=1, value="Комплектация")
        cell.font = title_font
        cell.alignment = align_left_B

        current_row = start_row + 1

        kinds_in_spec = self._detect_connection_kinds_in_spec(spec_data)

        # Подписи без двоеточий
        klass_common = [
            ("воздухоотводчик ½”", "1 шт."),
            ("заглушка ½”", "1 шт."),
            ("паспорт", "1 шт."),
        ]
        klass_clips = [
            ("клипсы для фиксации кронштейна (для 20,21,22,30,33)", "2 шт."),
            ("для длины > 1.6 м", "3 шт."),
            ("для длины > 2.5 м", "4 шт."),
        ]
        hygiene_common = [
            ("воздухоотводчик ½”", "1 шт."),
            ("заглушка ½”", "1 шт."),
            ("паспорт", "1 шт."),
        ]

        # Длинные описания — без двоеточия в конце
        first_line_side = (
            "радиатор в упаковке с полиэтиленовой пробкой "
            "в нижнем отверстии"
        )
        first_line_bottom = (
            "радиатор в упаковке, в сборе с транзитным теплопроводом "
            "и вентильной вставкой (с защитным колпачком) присоединительным "
            "размером М30, с транспортировочными полиэтиленовыми пробками"
        )

        for kind in kinds_in_spec:
            if kind == "K":
                rich = CellRichText(
                    TextBlock(section_font_italic, "В комплект поставки радиаторов с "),
                    TextBlock(section_font_italic_bold, "боковым подключением"),
                    TextBlock(section_font_italic, " входят:"),
                )
                lines = (
                    [(first_line_side, "1 шт.", False)]
                    + [(d, q, False) for d, q in klass_common]
                    + [(d, q, False) for d, q in klass_clips]
                )

            elif kind == "VK":
                rich = CellRichText(
                    TextBlock(section_font_italic, "В комплект поставки радиаторов с "),
                    TextBlock(section_font_italic_bold, "нижним подключением"),
                    TextBlock(section_font_italic, " входят:"),
                )
                lines = (
                    [(first_line_bottom, "1 шт.", True)]
                    + [(d, q, False) for d, q in klass_common]
                    + [(d, q, False) for d, q in klass_clips]
                )

            elif kind == "H":
                rich = CellRichText(
                    TextBlock(section_font_italic, "В комплект поставки "),
                    TextBlock(section_font_italic_bold, "Hygiene с боковым подключением"),
                    TextBlock(section_font_italic, " входят:"),
                )
                lines = (
                    [(first_line_side, "1 шт.", False)]
                    + [(d, q, False) for d, q in hygiene_common]
                )

            elif kind == "HV":
                rich = CellRichText(
                    TextBlock(section_font_italic, "В комплект поставки "),
                    TextBlock(section_font_italic_bold, "Hygiene с нижним подключением"),
                    TextBlock(section_font_italic, " входят:"),
                )
                lines = (
                    [(first_line_bottom, "1 шт.", True)]
                    + [(d, q, False) for d, q in hygiene_common]
                )

            else:
                continue

            # --- Заголовок раздела: A:C, rich text, курсив ---
            ws.merge_cells(
                start_row=current_row, start_column=1,
                end_row=current_row, end_column=3,
            )
            cell_head = ws.cell(row=current_row, column=1, value=rich)
            cell_head.alignment = align_left_B
            for col in range(1, 5):
                cc = ws.cell(row=current_row, column=col)
                cc.border = Border(
                    bottom=Side(style='thin', color='808080'),
                )
            current_row += 1

            # --- Строки состава ---
            for desc, qty, is_long in lines:
                if is_long:
                    # Длинная строка — 3 строки по вертикали.
                    # Маркер «•» — в объединённой ячейке A на 3 строки,
                    # выровнен по центру (как в обычных строках).
                    ws.merge_cells(
                        start_row=current_row, start_column=1,
                        end_row=current_row + 2, end_column=1,
                    )
                    cell_marker = ws.cell(row=current_row, column=1, value="•")
                    cell_marker.font = marker_font
                    cell_marker.alignment = align_center_A

                    # Объединение B:C на 3 строки
                    ws.merge_cells(
                        start_row=current_row, start_column=2,
                        end_row=current_row + 2, end_column=3,
                    )
                    cell_desc = ws.cell(row=current_row, column=2, value=desc)
                    cell_desc.font = row_font
                    cell_desc.alignment = align_left_B_wrap

                    # D — количество на 3 строки
                    ws.merge_cells(
                        start_row=current_row, start_column=4,
                        end_row=current_row + 2, end_column=4,
                    )
                    cell_qty = ws.cell(row=current_row, column=4, value=qty)
                    cell_qty.font = row_font
                    cell_qty.alignment = align_right_D

                    # Границы: нижняя на последней строке, левая в D.
                    for i_offset in range(3):
                        rr = current_row + i_offset
                        for col in range(1, 4):
                            cc = ws.cell(row=rr, column=col)
                            if i_offset == 2:
                                cc.border = Border(
                                    bottom=Side(style='thin', color='808080'),
                                )
                        cc_d = ws.cell(row=rr, column=4)
                        if i_offset == 2:
                            cc_d.border = bottom_left_border
                        else:
                            cc_d.border = left_border_col_D

                    for r in (current_row, current_row + 1, current_row + 2):
                        ws.row_dimensions[r].height = 20

                    current_row += 3
                else:
                    # Обычная строка
                    cell_marker = ws.cell(row=current_row, column=1, value="•")
                    cell_marker.font = marker_font
                    cell_marker.alignment = align_center_A

                    ws.merge_cells(
                        start_row=current_row, start_column=2,
                        end_row=current_row, end_column=3,
                    )
                    cell_desc = ws.cell(row=current_row, column=2, value=desc)
                    cell_desc.font = row_font
                    cell_desc.alignment = align_left_B

                    cell_qty = ws.cell(row=current_row, column=4, value=qty)
                    cell_qty.font = row_font
                    cell_qty.alignment = align_right_D

                    # Нижняя граница A:C, нижняя + левая для D.
                    for col in range(1, 4):
                        cc = ws.cell(row=current_row, column=col)
                        cc.border = bottom_border
                    cc_d = ws.cell(row=current_row, column=4)
                    cc_d.border = bottom_left_border

                    current_row += 1

            # --- Пустая строка между разделами ---
            current_row += 1
            # --- Пустая строка между разделами ---
            current_row += 1

        # ================================================================
        # ПРИМЕЧАНИЕ О КРОНШТЕЙНАХ
        # ================================================================
        # Показываем блок только если в спецификации есть кронштейны.
        # Если монтаж «Без кронштейнов» — предупреждать не о чем.
        has_brackets = any(
            "Кронштейн" in str(row.get("Наименование", ""))
            for _, row in spec_data.iterrows()
        )

        if has_brackets:
            # --- Заголовок «Примечание»: A:C, курсив ---
            ws.merge_cells(
                start_row=current_row, start_column=1,
                end_row=current_row, end_column=3,
            )
            cell = ws.cell(row=current_row, column=1, value="Примечание")
            cell.font = title_font
            cell.alignment = align_left_B
            current_row += 1

            # --- Строка с оговоркой: маркер в A, текст в B:D ---
            cell_marker = ws.cell(row=current_row, column=1, value="•")
            cell_marker.font = marker_font
            cell_marker.alignment = align_center_A

            ws.merge_cells(
                start_row=current_row, start_column=2,
                end_row=current_row, end_column=4,
            )
            cell_desc = ws.cell(
                row=current_row, column=2,
                value="кронштейны в комплект поставки радиаторов "
                      "не входят и приобретаются отдельно",
            )
            cell_desc.font = row_font
            cell_desc.alignment = align_left_B

            # Нижняя граница не накладывается — примечание не часть списка.

            current_row += 1

        return current_row - 1