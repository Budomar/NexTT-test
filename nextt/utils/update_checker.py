"""
Модуль проверки обновлений.
Автоматически проверяет наличие новой версии при запуске программы.
"""

import json
import urllib.request
import urllib.error
import ssl
import webbrowser
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional, Dict, Any
import os

from nextt.logger import get_logger

logger = get_logger(__name__)

# ============================================================================
# НАСТРОЙКИ
# ============================================================================

# RAW-ссылка на файл version.json в GitHub
VERSION_URL = "https://raw.githubusercontent.com/e-laggartt/NexTT/main/version.json"

# Текущая версия программы
CURRENT_VERSION = "2.4"
CURRENT_VERSION_CODE = 24

# Путь к иконке (относительно корня проекта)
ICON_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "resources", "icon.ico")

# ============================================================================


def _create_ssl_context():
    """
    Создаёт SSL-контекст, который не проверяет сертификаты.
    Это нужно для обхода ошибки CERTIFICATE_VERIFY_FAILED на некоторых Windows.
    """
    try:
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        return ssl_context
    except Exception as e:
        logger.warning(f"Не удалось создать SSL-контекст: {e}")
        return None


class UpdateChecker:
    """Проверяет наличие обновлений."""

    def __init__(self, parent_window, font_manager=None):
        self.parent = parent_window
        self.font_manager = font_manager

    def check_for_updates(self, show_no_update_message: bool = False) -> Optional[Dict[str, Any]]:
        """
        Проверяет наличие обновлений.

        Args:
            show_no_update_message: показывать ли сообщение "У вас последняя версия"

        Returns:
            Словарь с данными об обновлении или None
        """
        try:
            logger.info("Проверка обновлений...")
            
            # Создаём обработчик для обхода SSL-ошибок
            ssl_context = _create_ssl_context()
            
            if ssl_context:
                opener = urllib.request.build_opener(
                    urllib.request.HTTPSHandler(context=ssl_context)
                )
                urllib.request.install_opener(opener)
            
            # Скачиваем version.json
            req = urllib.request.Request(
                VERSION_URL,
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) NexTT Update Checker'}
            )
            
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode('utf-8'))
            
            remote_version = data.get('version', '')
            remote_version_code = data.get('version_code', 0)
            
            logger.info(f"Текущая версия: {CURRENT_VERSION} (код: {CURRENT_VERSION_CODE})")
            logger.info(f"Доступная версия: {remote_version} (код: {remote_version_code})")
            
            if remote_version_code > CURRENT_VERSION_CODE:
                logger.info(f"✅ Доступна новая версия: {remote_version}")
                return data
            else:
                logger.info(f"✅ У вас последняя версия ({CURRENT_VERSION})")
                if show_no_update_message and self.parent:
                    messagebox.showinfo(
                        "Обновления не найдены",
                        f"У вас установлена последняя версия {CURRENT_VERSION}.\n"
                        "Обновление не требуется."
                    )
                return None
                
        except urllib.error.URLError as e:
            logger.warning(f"Не удалось проверить обновления (ошибка сети): {e}")
            return None
        except json.JSONDecodeError as e:
            logger.warning(f"Не удалось проверить обновления (ошибка парсинга): {e}")
            return None
        except Exception as e:
            logger.warning(f"Не удалось проверить обновления: {e}")
            return None

    def show_update_dialog(self, update_data: Dict[str, Any]) -> None:
        """
        Показывает диалог с предложением обновиться.
        Окно динамически подстраивается под содержимое.
        """
        if not self.parent:
            return

        # Получаем данные из version.json
        new_version = update_data.get('version', '')
        whats_new = update_data.get('whats_new', [])
        release_date = update_data.get('release_date', '')

        # Получаем шрифты
        if self.font_manager:
            default_font = self.font_manager.get_default_font()
            bold_font = self.font_manager.get_bold_font()
            heading_font = self.font_manager.get_heading_font()
        else:
            default_font = ("Segoe UI", 10)
            bold_font = ("Segoe UI", 10, "bold")
            heading_font = ("Segoe UI", 14, "bold")

        # Создаём диалог
        dialog = tk.Toplevel(self.parent)
        dialog.title("NexTT")
        dialog.transient(self.parent)
        dialog.grab_set()
        dialog.resizable(False, False)
        dialog.configure(bg='#f0f0f0')

        # ========== УСТАНАВЛИВАЕМ ИКОНКУ ==========
        try:
            if os.path.exists(ICON_PATH):
                dialog.iconbitmap(default=ICON_PATH)
        except Exception:
            pass

        # Основной фрейм (без фиксированных размеров)
        main_frame = ttk.Frame(dialog, padding="25")
        main_frame.pack(fill="both", expand=True)

        # ========== ЗАГОЛОВОК С НОМЕРОМ ВЕРСИИ ==========
        ttk.Label(
            main_frame,
            text=f"Доступна новая версия {new_version}!",
            font=heading_font,
            foreground="#1a5f7a"
        ).pack(anchor="center", pady=(0, 20))

        # Разделитель
        ttk.Separator(main_frame, orient="horizontal").pack(fill="x", pady=(0, 20))

        # ========== БЛОК «ЧТО НОВОГО» ==========
        # Используем LabelFrame с текстом
        changes_frame = ttk.LabelFrame(main_frame, text="Что нового:", padding="15")
        changes_frame.pack(fill="both", expand=True, pady=(0, 20))

        # Создаём фрейм для текста, чтобы правильно работала прокрутка при необходимости
        text_frame = ttk.Frame(changes_frame)
        text_frame.pack(fill="both", expand=True)

        # Добавляем каждый пункт как отдельную метку
        if whats_new:
            for item in whats_new:
                # Пропускаем пустые строки
                if not item or not item.strip():
                    continue
                # Убираем возможные дубликаты
                label_text = f"• {item.strip()}"
                ttk.Label(
                    text_frame,
                    text=label_text,
                    font=default_font,
                    wraplength=480,
                    justify="left"
                ).pack(anchor="w", pady=3)
        else:
            ttk.Label(
                text_frame,
                text="• Улучшена стабильность работы\n• Исправлены обнаруженные ошибки",
                font=default_font
            ).pack(anchor="w", pady=3)

        # ========== ДАТА ВЫПУСКА ==========
        if release_date:
            ttk.Label(
                main_frame,
                text=f"Дата выпуска: {release_date}",
                font=default_font,
                foreground="#888"
            ).pack(anchor="center", pady=(0, 20))

        # ========== КНОПКИ (ЦЕНТРИРОВАННЫЕ) ==========
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill="x", pady=(10, 0))

        center_frame = ttk.Frame(btn_frame)
        center_frame.pack(expand=True)

        btn_download = ttk.Button(
            center_frame,
            text="Скачать обновление",
            command=lambda: self._open_download_link(update_data.get('download_url', ''), dialog),
            width=22
        )
        btn_download.pack(side="left", padx=10)

        btn_close = ttk.Button(
            center_frame,
            text="Закрыть",
            command=dialog.destroy,
            width=22
        )
        btn_close.pack(side="left", padx=10)

        # ========== ДИНАМИЧЕСКИЙ РАЗМЕР ОКНА ==========
        # Принудительно обновляем геометрию
        dialog.update_idletasks()

        # Получаем предпочтительные размеры окна
        req_width = dialog.winfo_reqwidth()
        req_height = dialog.winfo_reqheight()

        # Добавляем небольшой запас (30 пикселей по краям)
        final_width = req_width + 30
        final_height = req_height + 30

        # Центрируем окно на экране
        screen_width = dialog.winfo_screenwidth()
        screen_height = dialog.winfo_screenheight()
        x = (screen_width - final_width) // 2
        y = (screen_height - final_height) // 2

        dialog.geometry(f"{final_width}x{final_height}+{x}+{y}")

        # Обработка закрытия окна
        dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)

        # Поднимаем окно наверх
        dialog.lift()
        dialog.focus_force()

    def _open_download_link(self, url: str, dialog: tk.Toplevel) -> None:
        """
        Открывает ссылку для скачивания в браузере.
        Информационное окно остаётся ПОВЕРХ браузера (topmost).
        """
        if not url:
            messagebox.showerror("Ошибка", "Ссылка для скачивания не найдена")
            dialog.destroy()
            return

        # Открываем браузер
        webbrowser.open(url)

        # Создаём НЕЗАВИСИМОЕ информационное окно
        info = tk.Toplevel()
        info.title("Инструкция по обновлению")
        info.resizable(False, False)
        info.configure(bg='#f0f0f0')

        # Устанавливаем иконку
        try:
            if os.path.exists(ICON_PATH):
                info.iconbitmap(default=ICON_PATH)
        except Exception:
            pass

        # Делаем окно ВСЕГДА ПОВЕРХ всех окон
        info.attributes('-topmost', True)

        # Основной фрейм с отступами
        main_frame = ttk.Frame(info, padding="20")
        main_frame.pack(fill="both", expand=True)

        # Текст инструкции
        ttk.Label(
            main_frame,
            text="Ссылка для скачивания уже открыта в вашем браузере.",
            font=("Segoe UI", 10),
            wraplength=410,
            justify="left"
        ).pack(anchor="w", pady=(0, 15))

        ttk.Label(
            main_frame,
            text="Что нужно сделать:",
            font=("Segoe UI", 10, "bold")
        ).pack(anchor="w", pady=(0, 10))

        ttk.Label(
            main_frame,
            text="1. Скачайте файл NexTT.exe",
            font=("Segoe UI", 10)
        ).pack(anchor="w", pady=3)

        ttk.Label(
            main_frame,
            text="2. Замените им старый файл (в той же папке)",
            font=("Segoe UI", 10)
        ).pack(anchor="w", pady=3)

        ttk.Label(
            main_frame,
            text="3. Запустите новый файл — установка не требуется",
            font=("Segoe UI", 10)
        ).pack(anchor="w", pady=(3, 20))

        # Кнопка OK
        btn_ok = ttk.Button(
            main_frame,
            text="Понятно, закрыть",
            width=25,
            command=info.destroy
        )
        btn_ok.pack(pady=(5, 0))

        # ========== ЦЕНТРИРУЕМ ОКНО НА ЭКРАНЕ ==========
        info.update_idletasks()
        width = info.winfo_reqwidth()
        height = info.winfo_reqheight()
        screen_width = info.winfo_screenwidth()
        screen_height = info.winfo_screenheight()
        x = (screen_width - width) // 2
        y = (screen_height - height) // 2
        info.geometry(f"{width}x{height}+{x}+{y}")

        # Принудительно поднимаем окно наверх
        info.lift()
        info.focus_force()

        # Закрываем основное окно обновления
        dialog.destroy()

def check_updates_on_startup(parent_window, font_manager=None) -> None:
    """
    Проверяет обновления при запуске программы (в отдельном потоке).
    """
    def do_check():
        checker = UpdateChecker(parent_window, font_manager)
        update_data = checker.check_for_updates(show_no_update_message=False)
        
        if update_data:
            parent_window.after(2000, lambda: checker.show_update_dialog(update_data))
    
    import threading
    thread = threading.Thread(target=do_check, daemon=True)
    thread.start()