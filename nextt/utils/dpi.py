"""
Работа с DPI-масштабированием для Tkinter.
Поддерживает Windows Per-Monitor DPI и macOS Retina.
"""

import ctypes
import platform
import tkinter as tk


def enable_dpi_awareness() -> None:
    """Включает поддержку DPI awareness для Windows."""
    system = platform.system()
    if system == "Windows":
        try:
            # Per Monitor DPI awareness (Windows 10 1703+)
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except AttributeError:
            try:
                # System DPI awareness (Windows 8.1 и старше)
                ctypes.windll.user32.SetProcessDPIAware()
            except AttributeError:
                pass  # Fallback: Windows XP — ничего не делаем
    # macOS: Tk 8.6+ (Python 3.11+) уже поддерживает Retina автоматически


def get_dpi_scale(root: tk.Tk) -> float:
    """
    Возвращает коэффициент масштабирования относительно стандартных 96 DPI.

    Используется для умножения всех размеров (шрифты, отступы, ширина окон).
    Не изменяет глобальный tk scaling!

    Returns:
        float: коэффициент масштаба (1.0 = 96 DPI, 2.0 = 192 DPI)
    """
    try:
        # Получаем текущий scaling factor Tk
        tk_scaling = root.tk.call('tk', 'scaling')
        if tk_scaling is None:
            return 1.0
        return float(tk_scaling)
    except (tk.TclError, ValueError):
        return 1.0


def scale_value(base_value: int, scale: float) -> int:
    """
    Масштабирует целочисленное значение с учётом DPI.

    Args:
        base_value: базовое значение для 96 DPI
        scale: коэффициент из get_dpi_scale()

    Returns:
        int: масштабированное значение
    """
    return max(1, int(base_value * scale))


def scale_font(base_name: str, base_size: int, scale: float) -> tuple:
    """
    Создаёт кортеж шрифта с масштабированным размером.

    Args:
        base_name: имя шрифта (например, "Segoe UI")
        base_size: базовый размер в пунктах для 96 DPI
        scale: коэффициент из get_dpi_scale()

    Returns:
        tuple: (font_name, font_size) готовый для tkinter
    """
    return (base_name, max(8, int(base_size * scale)))


# Сохраняем кешированный scale для использования без root
_cached_scale: float = 1.0


def cache_scale(root: tk.Tk) -> None:
    """Кеширует коэффициент масштаба при старте приложения."""
    global _cached_scale
    enable_dpi_awareness()
    _cached_scale = get_dpi_scale(root)


def get_cached_scale() -> float:
    """Возвращает закешированный коэффициент масштаба."""
    return _cached_scale