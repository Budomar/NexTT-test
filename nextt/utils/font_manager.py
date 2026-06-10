"""
Глобальный менеджер шрифтов для всего приложения.
Позволяет динамически изменять размер шрифтов во всех окнах.
"""

import tkinter as tk
from tkinter import ttk
from typing import Optional, Dict, Any

from nextt.logger import get_logger
from nextt.config import config

logger = get_logger(__name__)


class FontManager:
    """
    Централизованное управление масштабированием шрифтов.
    Сохраняет коэффициент масштаба в settings.json.
    """

    # Минимальный и максимальный коэффициенты масштаба
    MIN_SCALE = 0.5
    MAX_SCALE = 2.0
    DEFAULT_SCALE = 1.0
    STEP = 0.05  # Шаг изменения при нажатии кнопок

    def __init__(self):
        """Инициализирует менеджер шрифтов."""
        # Загружаем сохранённый коэффициент
        saved_scale = config.get("font_scale_factor", self.DEFAULT_SCALE)
        
        self._scale = float(saved_scale)
        # Ограничиваем допустимыми значениями
        self._scale = max(self.MIN_SCALE, min(self.MAX_SCALE, self._scale))
        
        # Базовые шрифты для разных типов виджетов (в пунктах)
        self._base_fonts = {
            "default": ("Segoe UI", 9),
            "bold": ("Segoe UI", 9, "bold"),
            "small": ("Segoe UI", 8),
            "large": ("Segoe UI", 11),
            "heading": ("Segoe UI", 10, "bold"),
            "title": ("Segoe UI", 12, "bold"),
            "tooltip": ("Segoe UI", 9),
        }
        
        # Сохраняем старые стили для восстановления
        self._original_styles = {}
        
        # Флаг для предотвращения рекурсии
        self._is_updating = False
        
        logger.info(f"FontManager инициализирован: scale={self._scale:.2f}")

    @property
    def scale(self) -> float:
        """Текущий коэффициент масштаба."""
        return self._scale

    def increase(self) -> float:
        """Увеличивает масштаб на STEP."""
        new_scale = min(self.MAX_SCALE, self._scale + self.STEP)
        
        if new_scale != self._scale:
            self._scale = new_scale
            self._save()
            logger.info(f"Масштаб увеличен: {self._scale:.2f}")
        
        return self._scale

    def decrease(self) -> float:
        """Уменьшает масштаб на STEP."""
        new_scale = max(self.MIN_SCALE, self._scale - self.STEP)
        
        if new_scale != self._scale:
            self._scale = new_scale
            self._save()
            logger.info(f"Масштаб уменьшен: {self._scale:.2f}")
        
        return self._scale

    def reset(self) -> float:
        """Сбрасывает масштаб к DEFAULT_SCALE."""
        if self._scale != self.DEFAULT_SCALE:
            self._scale = self.DEFAULT_SCALE
            self._save()
            logger.info(f"Масштаб сброшен: {self._scale:.2f}")
        
        return self._scale

    def _save(self) -> None:
        """Сохраняет текущий масштаб в settings.json."""
        config.set("font_scale_factor", self._scale)

    def _scale_font_size(self, base_size: int) -> int:
        """Масштабирует размер шрифта."""
        scaled = max(6, int(base_size * self._scale))
        return scaled

    def get_scaled_font(self, font_name: str = "Segoe UI", size: int = 9, weight: str = "") -> tuple:
        """
        Возвращает масштабированный шрифт.
        
        Args:
            font_name: имя шрифта
            size: базовый размер в пунктах
            weight: "bold" или ""
        
        Returns:
            кортеж шрифта для tkinter
        """
        scaled_size = self._scale_font_size(size)
        result = (font_name, scaled_size) if not weight else (font_name, scaled_size, weight)
        return result

    def get_default_font(self) -> tuple:
        """Возвращает масштабированный шрифт по умолчанию (размер 9)."""
        return self.get_scaled_font("Segoe UI", 9)

    def get_bold_font(self, base_size: int = 9) -> tuple:
        """
        Возвращает масштабированный жирный шрифт заданного базового размера.
        
        Args:
            base_size: базовый размер шрифта в пунктах (для DPI=96)
            
        Returns:
            tuple: (имя_шрифта, масштабированный_размер, 'bold')
        """
        return self.get_scaled_font("Segoe UI", base_size, "bold")

    def get_heading_font(self) -> tuple:
        """Возвращает масштабированный шрифт для заголовков (размер 10, жирный)."""
        return self.get_scaled_font("Segoe UI", 10, "bold")

    def get_title_font(self) -> tuple:
        """Возвращает масштабированный шрифт для заголовков окон (размер 12, жирный)."""
        return self.get_scaled_font("Segoe UI", 12, "bold")

    def get_font(self, base_size: int = 9) -> tuple:
        """
        Возвращает масштабированный шрифт заданного базового размера.
        
        Args:
            base_size: базовый размер шрифта в пунктах (для DPI=96)
            
        Returns:
            tuple: (имя_шрифта, масштабированный_размер)
        """
        return self.get_scaled_font("Segoe UI", base_size)

    def get_small_font(self) -> tuple:
        """Возвращает масштабированный мелкий шрифт (размер 8)."""
        return self.get_scaled_font("Segoe UI", 8)

    # ==================================================================
    # ПРИМЕНЕНИЕ ШРИФТОВ К ВИДЖЕТАМ
    # ==================================================================

    def apply_to_widget(self, widget, font_attr: str = "font") -> bool:
        """
        Применяет масштабированный шрифт к одному виджету.
        """
        if self._is_updating:
            return False
        
        try:
            if not widget or not widget.winfo_exists():
                return False

            # Определяем тип виджета и применяем соответствующий шрифт
            if isinstance(widget, (ttk.Label, ttk.Button, ttk.Radiobutton, 
                                   ttk.Checkbutton, ttk.Entry, ttk.Combobox)):
                if hasattr(widget, 'configure'):
                    try:
                        new_font = self.get_default_font()
                        widget.configure(font=new_font)
                    except tk.TclError:
                        pass
            elif isinstance(widget, (tk.Label, tk.Button, tk.Entry, tk.Text, 
                                     tk.Message, tk.Listbox)):
                new_font = self.get_default_font()
                widget.configure(font=new_font)
            elif isinstance(widget, ttk.Treeview):
                self.apply_to_treeview(widget)
            elif isinstance(widget, tk.Menu):
                new_font = self.get_default_font()
                widget.configure(font=new_font)
            elif isinstance(widget, ttk.Notebook):
                style = ttk.Style()
                style.configure("TNotebook.Tab", font=self.get_default_font())
            
            return True
        except (tk.TclError, AttributeError, RuntimeError):
            return False

    def apply_to_treeview(self, treeview: ttk.Treeview) -> None:
        """
        Применяет шрифты к Treeview (строки и заголовки).
        """
        if not treeview or not treeview.winfo_exists():
            return

        try:
            style = ttk.Style()
            style_name = str(treeview.cget("style")) if treeview.cget("style") else "Treeview"
            
            new_font = self.get_default_font()
            new_height = self._scale_font_size(25)
            
            style.configure(style_name, font=new_font, rowheight=new_height)
            
            heading_style = f"{style_name}.Heading"
            new_heading_font = self.get_heading_font()
            style.configure(heading_style, font=new_heading_font)
            
            treeview.configure(font=new_font)
            
        except (tk.TclError, RuntimeError):
            pass

    def update_all_styles(self) -> None:
        """Обновляет все глобальные стили ttk."""
        try:
            style = ttk.Style()
            default_font = self.get_default_font()
            bold_font = self.get_bold_font()
            heading_font = self.get_heading_font()
            
            # Обновляем стандартные стили
            styles_to_update = [
                (".", default_font),
                ("TLabel", default_font),
                ("TButton", default_font),
                ("TRadiobutton", default_font),
                ("TCheckbutton", default_font),
                ("TEntry", default_font),
                ("TFrame", default_font),
                ("TLabelframe", default_font),
                ("TLabelframe.Label", bold_font),
                ("TMenubutton", default_font),
                ("TNotebook", default_font),
                ("TNotebook.Tab", default_font),
                ("Treeview", default_font),
                ("Treeview.Heading", heading_font),
            ]
            
            for style_name, font_value in styles_to_update:
                try:
                    style.configure(style_name, font=font_value)
                except Exception:
                    pass
            
            # Обновляем rowheight для Treeview
            new_height = self._scale_font_size(25)
            style.configure("Treeview", rowheight=new_height)
            
        except (tk.TclError, RuntimeError):
            pass

    def apply_to_window(self, window) -> None:
        """
        Рекурсивно применяет масштабирование ко всем виджетам в окне.
        """
        if self._is_updating:
            return
        
        self._is_updating = True
        
        try:
            if not window or not window.winfo_exists():
                return

            # Обновляем глобальные стили
            self.update_all_styles()

            # Применяем к самому окну
            self.apply_to_widget(window)

            # Рекурсивно обходим всех детей
            for child in window.winfo_children():
                self.apply_to_widget_recursive(child)

            # Принудительно обновляем отрисовку
            window.update_idletasks()
            
        except (tk.TclError, RuntimeError):
            pass
        finally:
            self._is_updating = False

    def apply_to_widget_recursive(self, widget) -> None:
        """
        Рекурсивно применяет масштабирование ко всем дочерним виджетам.
        """
        if self._is_updating:
            return
            
        try:
            if not widget or not widget.winfo_exists():
                return

            # Применяем шрифт к текущему виджету
            self.apply_to_widget(widget)

            # Для Frame и Toplevel рекурсивно обрабатываем детей
            if isinstance(widget, (tk.Frame, ttk.Frame, tk.Toplevel, ttk.LabelFrame)):
                for child in widget.winfo_children():
                    self.apply_to_widget_recursive(child)

        except (tk.TclError, RuntimeError, AttributeError):
            pass

    def refresh_all_windows(self, root_window) -> None:
        """
        Обновляет шрифты во всех окнах приложения.
        """
        if not root_window or not root_window.winfo_exists():
            return

        # Обновляем глобальные стили
        self.update_all_styles()

        # Применяем к главному окну
        self.apply_to_window(root_window)

        # Применяем ко всем дочерним Toplevel окнам
        for child in root_window.winfo_children():
            if isinstance(child, tk.Toplevel) and child.winfo_exists():
                self.apply_to_window(child)

        # Принудительно обновляем отрисовку
        try:
            root_window.update_idletasks()
        except (tk.TclError, RuntimeError):
            pass
        
        logger.info(f"Шрифты обновлены во всех окнах (scale={self._scale:.2f})")