"""
Настройка ttk-стилей для главного окна приложения NexTT.

Вынесено из MainWindow._setup_styles для уменьшения размера main_window.py
и улучшения читаемости.

Все стили зависят только от FontManager, который передаётся в функцию.
"""

import tkinter.font as tkfont
from tkinter import ttk

from nextt.logger import get_logger

logger = get_logger(__name__)


def setup_styles(font_manager) -> None:
    """
    Настраивает все ttk-стили для главного окна.

    Args:
        font_manager: экземпляр FontManager для получения масштабированных шрифтов
    """
    style = ttk.Style()
    style.theme_use('clam')

    # ================================================================
    # БАЗОВЫЕ СТИЛИ
    # ================================================================
    style.configure('.', background="#dedede", foreground='#444141')
    style.configure('TFrame', background='#dedede')

    default_font = font_manager.get_default_font()
    heading_font = font_manager.get_heading_font()
    bold_font = font_manager.get_bold_font()

    style.configure('TLabel', background='#dedede', font=default_font)
    style.configure('TEntry', font=default_font, fieldbackground='white')

    # ================================================================
    # РАССЧИТЫВАЕМ ВЫСОТУ ДЛЯ РАДИОКНОПОК
    # ================================================================
    font_obj = tkfont.Font(font=default_font)
    row_height = font_obj.metrics('linespace') * 2 + 10

    # ================================================================
    # ЕДИНЫЙ СТИЛЬ ДЛЯ ВСЕХ РАДИОКНОПОК
    # ================================================================
    style.configure('TRadiobutton',
                    background='#dedede',
                    foreground='#444141',
                    font=bold_font,
                    height=row_height)

    style.configure('Green.TRadiobutton',
                    background='#dedede',
                    foreground='#008000',
                    font=bold_font,
                    height=row_height)

    style.configure('Active.TRadiobutton',
                    background='#c8c8c8',
                    foreground='#444141',
                    font=bold_font,
                    height=row_height)

    style.configure('Active.Green.TRadiobutton',
                    background='#c8c8c8',
                    foreground='#008000',
                    font=bold_font,
                    height=row_height)

    # ================================================================
    # СТИЛЬ ДЛЯ КНОПОК ТИПА РАДИАТОРА
    # ================================================================
    style.configure('Type.TRadiobutton',
                    background='#dedede',
                    foreground='#444141',
                    font=bold_font,
                    height=font_obj.metrics('linespace') + 10)

    style.configure('Active.Type.TRadiobutton',
                    background='#c8c8c8',
                    foreground='#444141',
                    font=bold_font,
                    height=font_obj.metrics('linespace') + 10)

    # ================================================================
    # СТИЛЬ ДЛЯ ЧЕКБОКСА
    # ================================================================
    style.configure('TCheckbutton',
                    background='#dedede',
                    font=default_font)

    # ================================================================
    # СТИЛЬ ДЛЯ КНОПОК
    # ================================================================
    style.configure('TButton', font=default_font,
                    background='#263168', foreground='white')
    style.map('TButton',
              background=[('active', '#7E1A2F'), ('!disabled', '#263168')],
              foreground=[('!disabled', 'white')])

    # ================================================================
    # СТИЛЬ ДЛЯ MENUBUTTON
    # ================================================================
    style.configure('TMenubutton', font=default_font,
                    background='#263168', foreground='white', arrowcolor='white')
    style.map('TMenubutton',
              background=[('active', '#7E1A2F')],
              foreground=[('!active', 'white')],
              arrowcolor=[('!active', 'white')])

    # ================================================================
    # СТИЛЬ ДЛЯ КОМБОБОКСА
    # ================================================================
    style.configure('TCombobox', font=default_font, fieldbackground='white')

    # ================================================================
    # СТИЛЬ ДЛЯ СЕГМЕНТИРОВАННОГО ПЕРЕКЛЮЧАТЕЛЯ (Toolbutton)
    #   Используется в диалогах для переключателей вида [ A | B | C ]
    #
    #   Неактивная вкладка — светлая (как фон окна);
    #   Активная вкладка   — синяя с белым текстом.
    # ================================================================
    # Неактивная кнопка — светлая, тёмный текст
    style.configure('Toolbutton',
                    font=bold_font,
                    background='#e8e8e8',
                    foreground='#444141',
                    relief='flat',
                    borderwidth=1,
                    padding=(14, 6),
                    anchor='center')

    style.map('Toolbutton',
              background=[('active', '#d0d0d0'), ('!disabled', '#e8e8e8')],
              foreground=[('!disabled', '#444141')])

    # Активная кнопка — синяя, белый текст
    style.configure('Active.Toolbutton',
                    font=bold_font,
                    background='#263168',
                    foreground='white',
                    relief='flat',
                    borderwidth=1,
                    padding=(14, 6),
                    anchor='center')

    style.map('Active.Toolbutton',
              background=[('active', '#263168'), ('!disabled', '#263168')],
              foreground=[('!disabled', 'white')])