"""
Tooltip (всплывающая подсказка) для ячеек матрицы NexTT.

Вынесено из MainWindow:
    • _create_tooltip_window  — создание окна подсказки
    • _show_cell_tooltip      — показ подсказки при наведении на ячейку
    • _hide_cell_tooltip      — скрытие подсказки

Подсказка показывает:
    • наименование радиатора
    • артикул
    • мощность / вес / объём
    • цену со скидкой и итог по количеству
    • состав кронштейнов (если выбраны)
"""

import re
import tkinter as tk

from nextt.logger import get_logger
from nextt.core.power_recalculator import PowerRecalculator

logger = get_logger(__name__)


# ======================================================================
# Создание окна подсказки
# ======================================================================

def create_tooltip_window(main_window) -> None:
    """Создаёт окно подсказки (один раз)."""
    if (hasattr(main_window, '_tooltip_window')
            and main_window._tooltip_window
            and main_window._tooltip_window.winfo_exists()):
        return

    main_window._tooltip_window = tk.Toplevel(main_window.root)
    main_window._tooltip_window.wm_overrideredirect(True)
    main_window._tooltip_window.withdraw()

    main_frame = tk.Frame(main_window._tooltip_window, bg='#ffffe0', padx=5, pady=5)
    main_frame.pack()

    main_window._tooltip_name = tk.Label(
        main_frame, font=("Segoe UI", 10, "bold"),
        bg='#ffffe0', fg='#000000',
        wraplength=300, justify="left",
    )
    main_window._tooltip_name.pack(anchor="w")

    sep1 = tk.Frame(main_frame, height=1, bg='#cccccc', width=300)
    sep1.pack(fill="x", pady=3)

    main_window._tooltip_art = tk.Label(
        main_frame, font=("Segoe UI", 9),
        bg='#ffffe0', fg='#000000', justify="left",
    )
    main_window._tooltip_art.pack(anchor="w")

    main_window._tooltip_params = tk.Label(
        main_frame, font=("Segoe UI", 9),
        bg='#ffffe0', fg='#000000', justify="left",
    )
    main_window._tooltip_params.pack(anchor="w")

    sep2 = tk.Frame(main_frame, height=1, bg='#cccccc', width=300)
    sep2.pack(fill="x", pady=3)

    main_window._tooltip_price = tk.Label(
        main_frame, font=("Segoe UI", 9, "bold"),
        bg='#ffffe0', fg='#000000', justify="left",
    )
    main_window._tooltip_price.pack(anchor="w")


# ======================================================================
# Показ подсказки
# ======================================================================

def show_cell_tooltip(main_window, event, product) -> None:
    """Показывает подсказку с параметрами радиатора."""
    if not main_window.show_tooltips_var.get():
        return

    font_manager = main_window.app.font_manager
    default_font = font_manager.get_default_font()
    bold_font = font_manager.get_bold_font()
    italic_font = font_manager.get_font(9)

    # Создаём окно если ещё нет ИЛИ оно было уничтожено
    if (not hasattr(main_window, '_tooltip_window')
            or not main_window._tooltip_window
            or not main_window._tooltip_window.winfo_exists()):
        _build_tooltip_widgets(main_window, default_font, bold_font, italic_font)
    else:
        # Если окно уже существует — обновляем шрифты (на случай изменения масштаба)
        _refresh_tooltip_fonts(main_window, default_font, bold_font, italic_font)

    if not main_window._tooltip_window.winfo_exists():
        return

    # === Извлечение данных ===
    name = str(product.get('Наименование', ''))
    art = str(product.get('Артикул', ''))
    power = product.get('Мощность, Вт', '')
    weight = product.get('Вес, кг', 0)
    volume = product.get('Объем, м3', 0)

    # Извлекаем параметры из названия для кронштейнов
    rad_type = None
    height = None
    length = None
    connection = None

    try:
        match = re.search(r'/(\d{2})/(\d{3,4})/(\d{3,4})', name)
        if match:
            rad_type, h, l = match.groups()
            height, length = int(h), int(l)
        else:
            parts = name.split('/')
            if len(parts) >= 3:
                last_part = parts[-1].strip()
                lm = re.search(r'(\d{3,4})', last_part)
                if lm:
                    length = int(lm.group(1))
                height_part = parts[-2].strip()
                hm = re.search(r'(\d{3,4})', height_part)
                if hm:
                    height = int(hm.group(1))
                for p in reversed(parts[:-2]):
                    tm = re.search(r'(\d{2})', p)
                    if tm:
                        rad_type = tm.group(1)
                        break

        # Определяем подключение
        name_lower = name.lower()
        if 'ventil hygiene (hv)' in name_lower:
            if ' la' in name_lower or ' l ' in name_lower or name_lower.endswith(' la'):
                connection = "HV-левое"
            else:
                connection = "HV-правое"
        elif 'hygiene (h)' in name_lower:
            connection = "H-боковое"
        elif 'vk' in name_lower:
            if ' la' in name_lower or ' l ' in name_lower or name_lower.endswith(' la'):
                connection = "VK-левое"
            else:
                connection = "VK-правое"
        elif 'k-profil' in name_lower or 'k-' in name_lower:
            connection = "K-боковое"
        else:
            connection = "VK-правое"
    except Exception:
        pass

    # Количество радиаторов из ячейки
    qty_radiators = 1
    for (key, val) in main_window.app.entry_values.items():
        if isinstance(key, tuple) and len(key) >= 2 and key[1] == art:
            if val and val.strip():
                qty_radiators = main_window._parse_qty(val) or 1
            break

    # Формат параметров (с пересчётом мощности при нестандартном графике)
    delta_t = main_window._current_delta_t()

    if not power:
        power_text = "Мощность: не указана"
    elif PowerRecalculator.is_reference(delta_t):
        power_text = f"Мощность: {power} Вт"
    else:
        try:
            power_nom_f = float(power)
        except (ValueError, TypeError):
            power_nom_f = 0.0

        rad_type_for_recalc = rad_type if rad_type else "10"
        height_for_recalc = height if height else 500

        power_recalc = PowerRecalculator.recalc_power(
            power_nom_f, rad_type_for_recalc, height_for_recalc, delta_t
        )
        power_text = (
            f"Мощность: {int(round(power_recalc))} Вт "
            f"(при Δt={delta_t:.0f} °С; паспорт: {int(round(power_nom_f))} Вт)"
        )

    params_text = f"{power_text}  •  Вес: {weight} кг  •  Объём: {volume} м³"

    # Цена радиатора со скидкой
    base_price = product.get('Цена, руб (с НДС)', '') or product.get('Цена, руб', '')
    price_val = None
    price_disc = None
    price_total = None
    price_str = "Цена: не указана"
    try:
        disc_rad = float(main_window.radiator_discount_var.get() or "0")
        disc_rad = max(0.0, min(100.0, disc_rad))
        price_val = float(base_price)
        price_disc = price_val * (1 - disc_rad / 100)
        price_total = price_disc * qty_radiators

        def fmt(val):
            return f"{val:,.2f}".replace(",", " ").replace(".", ",")

        price_str = (
            f"Цена с НДС: {fmt(price_disc)} руб × "
            f"{qty_radiators} шт = {fmt(price_total)} руб"
        )
    except Exception:
        pass

    # Обновляем основные строки
    main_window._tip_name.config(text=name)
    main_window._tip_art.config(text=f"Артикул: {art}")
    main_window._tip_params.config(text=params_text)
    main_window._tip_price.config(text=price_str)

    # Скрываем блок кронштейнов
    main_window._tip_bracket_info.pack_forget()
    for lbl in main_window._tip_bracket_lines:
        lbl.pack_forget()
    main_window._tip_sep3.pack_forget()
    main_window._tip_total.pack_forget()

    # ================================================================
    # Обработка кронштейнов
    # ================================================================
    bracket_choice = main_window.bracket_var.get()

    if bracket_choice != "Без кронштейнов" and rad_type and height and length and connection:
        try:
            from nextt.core.brackets import BracketsCalculator

            brackets_list = BracketsCalculator.calculate(
                radiator_type=rad_type,
                length=length,
                height=height,
                bracket_type=bracket_choice,
                connection=connection,
                quantity=qty_radiators,
            )

            if brackets_list:
                main_window._tip_bracket_info.config(
                    text="Кронштейны приобретаются отдельно"
                )
                main_window._tip_bracket_info.pack(anchor="w")

                total_brackets_sum = 0.0
                lines_used = 0

                brackets_df = main_window.app.data_provider.brackets_df

                for art_bracket, qty_bracket in brackets_list:
                    mask = brackets_df['Артикул'].astype(str).str.strip() == art_bracket
                    if not mask.any():
                        continue

                    bracket_info = brackets_df[mask].iloc[0]
                    full_name = str(bracket_info['Наименование'])

                    display_name = full_name
                    if display_name.startswith("Кронштейн "):
                        display_name = display_name[len("Кронштейн "):]
                    display_name = re.sub(r'\s*\(.*?\)', '', display_name).strip()

                    base_bracket_price = float(bracket_info.get('Цена, руб', 0))
                    try:
                        disc_br = float(main_window.bracket_discount_var.get() or "0")
                        disc_br = max(0.0, min(100.0, disc_br))
                    except Exception:
                        disc_br = 0.0

                    bracket_price_disc = base_bracket_price * (1 - disc_br / 100)
                    line_total = bracket_price_disc * qty_bracket
                    total_brackets_sum += line_total

                    qty_per_rad = (
                        qty_bracket // qty_radiators if qty_radiators > 0 else qty_bracket
                    )

                    def fmt(val):
                        return f"{val:,.2f}".replace(",", " ").replace(".", ",")

                    line_text = (
                        f"{display_name} — "
                        f"{qty_per_rad} шт × {qty_radiators} рад × "
                        f"{fmt(bracket_price_disc)} руб = "
                        f"{fmt(line_total)} руб"
                    )

                    if lines_used < len(main_window._tip_bracket_lines):
                        main_window._tip_bracket_lines[lines_used].config(text=line_text)
                        main_window._tip_bracket_lines[lines_used].pack(anchor="w")
                        lines_used += 1

                if price_val and price_total:
                    total_with = price_total + total_brackets_sum
                    main_window._tip_total.config(
                        text=f"Итого с кронштейнами: {fmt(total_with)} руб"
                    )
                    main_window._tip_sep3.pack(fill="x", pady=3)
                    main_window._tip_total.pack(anchor="w")

        except Exception as e:
            logger.debug(f"Ошибка подбора кронштейнов: {e}")

    # ================================================================
    # Умное позиционирование
    # ================================================================
    _position_tooltip(main_window)


# ======================================================================
# Позиционирование
# ======================================================================

def _position_tooltip(main_window) -> None:
    """Умное позиционирование подсказки относительно курсора."""
    pointer_x = main_window.root.winfo_pointerx()
    pointer_y = main_window.root.winfo_pointery()
    screen_w = main_window.root.winfo_screenwidth()
    screen_h = main_window.root.winfo_screenheight()

    main_window._tooltip_window.update_idletasks()
    tw = main_window._tooltip_window.winfo_reqwidth()
    th = main_window._tooltip_window.winfo_reqheight()

    # Высота панели задач (снизу экрана)
    try:
        from nextt.utils.window_manager import get_taskbar_height
        taskbar_h = get_taskbar_height(main_window._tooltip_window)
    except Exception:
        taskbar_h = 0

    x = pointer_x + 15
    y = pointer_y + 15

    if x + tw > screen_w:
        x = pointer_x - tw - 15

    # Нижняя граница рабочей области (с учётом панели задач)
    bottom_limit = screen_h - taskbar_h - 10

    if y + th > bottom_limit:
        y = pointer_y - th - 15
    if y < 10:
        y = 10

    main_window._tooltip_window.wm_geometry(f"+{x}+{y}")
    main_window._tooltip_window.deiconify()


# ======================================================================
# Скрытие подсказки
# ======================================================================

def hide_cell_tooltip(main_window, event=None) -> None:
    """Скрывает подсказку."""
    if (hasattr(main_window, '_tooltip_window')
            and main_window._tooltip_window
            and main_window._tooltip_window.winfo_exists()):
        main_window._tooltip_window.withdraw()


# ======================================================================
# Внутренние помощники
# ======================================================================

def _build_tooltip_widgets(main_window, default_font, bold_font, italic_font) -> None:
    """Создаёт виджеты окна подсказки (используется при первом показе)."""
    main_window._tooltip_window = tk.Toplevel(main_window.root)
    main_window._tooltip_window.wm_overrideredirect(True)
    main_window._tooltip_window.withdraw()

    main_frame = tk.Frame(main_window._tooltip_window, bg='#ffffe0', padx=5, pady=5)
    main_frame.pack()

    main_window._tip_name = tk.Label(
        main_frame, font=bold_font,
        bg='#ffffe0', fg='#000000', wraplength=300, justify="left",
    )
    main_window._tip_name.pack(anchor="w")

    sep1 = tk.Frame(main_frame, height=1, bg='#cccccc', width=300)
    sep1.pack(fill="x", pady=3)

    main_window._tip_art = tk.Label(
        main_frame, font=default_font,
        bg='#ffffe0', fg='#000000', justify="left",
    )
    main_window._tip_art.pack(anchor="w")

    main_window._tip_params = tk.Label(
        main_frame, font=default_font,
        bg='#ffffe0', fg='#000000', justify="left",
    )
    main_window._tip_params.pack(anchor="w")

    sep2 = tk.Frame(main_frame, height=1, bg='#cccccc', width=300)
    sep2.pack(fill="x", pady=3)

    main_window._tip_price = tk.Label(
        main_frame, font=bold_font,
        bg='#ffffe0', fg='#000000', justify="left",
    )
    main_window._tip_price.pack(anchor="w")

    # Кронштейны
    main_window._tip_bracket_info = tk.Label(
        main_frame, font=italic_font,
        bg='#ffffe0', fg='#000000', justify="left",
    )
    main_window._tip_bracket_lines = []
    for _ in range(5):
        lbl = tk.Label(
            main_frame, font=default_font,
            bg='#ffffe0', fg='#000000', justify="left",
        )
        main_window._tip_bracket_lines.append(lbl)

    main_window._tip_sep3 = tk.Frame(main_frame, height=1, bg='#cccccc', width=300)
    main_window._tip_total = tk.Label(
        main_frame, font=bold_font,
        bg='#ffffe0', fg='#000000', justify="left",
    )


def _refresh_tooltip_fonts(main_window, default_font, bold_font, italic_font) -> None:
    """Обновляет шрифты существующего окна подсказки."""
    if hasattr(main_window, '_tip_name'):
        main_window._tip_name.config(font=bold_font)
    if hasattr(main_window, '_tip_art'):
        main_window._tip_art.config(font=default_font)
    if hasattr(main_window, '_tip_params'):
        main_window._tip_params.config(font=default_font)
    if hasattr(main_window, '_tip_price'):
        main_window._tip_price.config(font=bold_font)
    if hasattr(main_window, '_tip_bracket_info'):
        main_window._tip_bracket_info.config(font=italic_font)
    if hasattr(main_window, '_tip_bracket_lines'):
        for lbl in main_window._tip_bracket_lines:
            lbl.config(font=default_font)
    if hasattr(main_window, '_tip_total'):
        main_window._tip_total.config(font=bold_font)