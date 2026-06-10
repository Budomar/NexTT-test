"""
Управление окнами приложения.
Следит за открытыми Toplevel, корректно закрывает их и освобождает ресурсы.
Также содержит функцию для расчёта безопасной геометрии окон.
"""

import tkinter as tk
import platform
from typing import Dict, Optional


class WindowManager:
    """
    Реестр всех дочерних окон. Гарантирует:
    - только одно окно каждого типа
    - корректное уничтожение при закрытии
    - возврат фокуса в главное окно
    """

    def __init__(self, root: tk.Tk):
        self.root = root
        self._windows: Dict[str, tk.Toplevel] = {}

    def create(
        self,
        window_id: str,
        builder: callable,
        modal: bool = False,
        on_close: Optional[callable] = None,
    ) -> tk.Toplevel:
        """
        Создаёт новое окно или поднимает существующее.

        Args:
            window_id: уникальный идентификатор окна
            builder: функция, которая создаёт содержимое окна
            modal: если True, окно будет модальным
            on_close: дополнительный callback при закрытии

        Returns:
            Созданное или существующее окно
        """
        # Если окно уже существует — поднимаем его
        if window_id in self._windows:
            win = self._windows[window_id]
            if win.winfo_exists():
                win.lift()
                win.focus_force()
                return win
            else:
                del self._windows[window_id]

        win = tk.Toplevel(self.root)
        win.title(window_id)
        win.transient(self.root)
        if modal:
            win.grab_set()

        self._windows[window_id] = win

        def on_destroy():
            if on_close:
                on_close()
            self._windows.pop(window_id, None)

        win.protocol("WM_DELETE_WINDOW", on_destroy)
        win.bind("<Escape>", lambda e: on_destroy())

        builder(win)
        return win

    def close(self, window_id: str) -> None:
        """Закрывает окно по идентификатору."""
        if window_id in self._windows:
            win = self._windows[window_id]
            if win.winfo_exists():
                win.destroy()

    def close_all(self) -> None:
        """Закрывает все зарегистрированные окна."""
        for win_id in list(self._windows.keys()):
            self.close(win_id)

    def has_open(self, window_id: str) -> bool:
        """Проверяет, открыто ли окно данного типа."""
        if window_id in self._windows:
            return self._windows[window_id].winfo_exists()
        return False


def get_safe_geometry(window: tk.Toplevel, maximized: bool = True) -> str:
    """
    Рассчитывает геометрию окна, которое гарантированно не перекрывает
    панель задач на Windows, macOS и Linux.
    
    Args:
        window: окно Toplevel, для которого рассчитывается геометрия
        maximized: если True, окно будет развёрнуто на всю рабочую область
                   (но не поверх панели задач)

    Returns:
        строка для метода .geometry() — "ШиринаxВысота+Лево+Верх"
    """
    # Обновляем информацию об окне
    window.update_idletasks()

    # Полная ширина и высота экрана в логических пикселях Tk
    screen_w = window.winfo_screenwidth()
    screen_h = window.winfo_screenheight()

    # ========== ОПРЕДЕЛЯЕМ РАБОЧУЮ ОБЛАСТЬ (без панели задач) ==========
    work_w = screen_w
    work_h = screen_h
    taskbar_height = 0

    if platform.system() == "Windows":
        try:
            import ctypes
            from ctypes import wintypes

            class RECT(ctypes.Structure):
                _fields_ = [
                    ("left",   wintypes.LONG),
                    ("top",    wintypes.LONG),
                    ("right",  wintypes.LONG),
                    ("bottom", wintypes.LONG),
                ]

            # SPI_GETWORKAREA возвращает рабочую область
            rc = RECT()
            SPI_GETWORKAREA = 0x0030
            ctypes.windll.user32.SystemParametersInfoW(
                SPI_GETWORKAREA, 0, ctypes.byref(rc), 0
            )

            work_w = rc.right - rc.left
            work_h = rc.bottom - rc.top
            taskbar_height = screen_h - work_h

            # Дополнительная проверка: если рабочая область меньше 80% экрана,
            # значит API вернул некорректные данные — используем запасной вариант
            if work_h < screen_h * 0.8:
                work_w = screen_w
                work_h = screen_h
                taskbar_height = 40  # запасной отступ

        except Exception:
            work_w = screen_w
            work_h = screen_h
            taskbar_height = 40

    # ========== macOS / Linux / fallback ==========
    # На macOS и Linux делаем отступ снизу для панели задач/дока
    if platform.system() == "Darwin":  # macOS
        taskbar_height = 50
        work_h = screen_h - taskbar_height
    elif platform.system() == "Linux":
        taskbar_height = 60
        work_h = screen_h - taskbar_height
    else:  # Windows (если API не сработал)
        if taskbar_height == 0:
            taskbar_height = 40
        work_h = screen_h - taskbar_height

    # ========== РАЗВЁРНУТОЕ ОКНО ==========
    if maximized:
        # Окно занимает всю рабочую область, но с небольшими отступами
        # чтобы кнопки внизу точно не перекрывались панелью задач
        window_width = work_w
        # Уменьшаем высоту на 10-20 пикселей для запаса
        window_height = work_h - 15
        window_x = 0
        window_y = 0
    else:
        # Обычный режим (для других случаев)
        window_width = int(work_w * 0.9)
        window_width = max(800, min(window_width, 1920))
        window_height = int(work_h * 0.85)
        window_height = max(500, window_height)
        window_x = max(0, (work_w - window_width) // 2)
        window_y = 40

    return f"{window_width}x{window_height}+{window_x}+{window_y}"

def get_taskbar_height(window: tk.Toplevel) -> int:
    """
    Возвращает высоту панели задач в пикселях.
    
    Args:
        window: окно Toplevel для получения информации об экране
        
    Returns:
        высота панели задач в пикселях
    """
    window.update_idletasks()
    
    screen_h = window.winfo_screenheight()
    
    if platform.system() == "Windows":
        try:
            import ctypes
            from ctypes import wintypes

            class RECT(ctypes.Structure):
                _fields_ = [
                    ("left",   wintypes.LONG),
                    ("top",    wintypes.LONG),
                    ("right",  wintypes.LONG),
                    ("bottom", wintypes.LONG),
                ]

            rc = RECT()
            SPI_GETWORKAREA = 0x0030
            ctypes.windll.user32.SystemParametersInfoW(
                SPI_GETWORKAREA, 0, ctypes.byref(rc), 0
            )
            
            work_h = rc.bottom - rc.top
            return screen_h - work_h
        except Exception:
            return 40
    
    # macOS и Linux
    if platform.system() == "Darwin":
        return 50
    elif platform.system() == "Linux":
        return 60
    else:
        return 40

def setup_dialog_window(window: tk.Toplevel, title: str = "") -> None:
    """
    Настраивает Toplevel-окно так, чтобы были видны все три кнопки
    в правом верхнем углу: свернуть, развернуть/восстановить, закрыть.
    
    Исправляет проблему, когда при создании окна с кастомной геометрией
    исчезают кнопки «свернуть» и «развернуть».
    
    ВАЖНО: Порядок вызовов критически важен!
    
    Args:
        window: окно Toplevel для настройки
        title: заголовок окна (если не пустой — устанавливается)
    """
    if title:
        window.title(title)
    
    # ========== КЛЮЧЕВОЙ ПОРЯДОК НАСТРОЙКИ ==========
    # 1. Убеждаемся, что окно НЕ инструментальное
    #    (инструментальные окна имеют только кнопку закрытия)
    window.attributes('-toolwindow', False)
    
    # 2. Разрешаем изменение размера (иначе кнопка «развернуть» недоступна)
    window.resizable(True, True)
    
    # 3. Убираем режим «поверх всех», если он был установлен
    window.attributes('-topmost', False)
    
    # 4. Принудительно снимаем флаг disabled
    window.attributes('-disabled', False)
    
    # 5. Обновляем отрисовку
    window.update_idletasks()
    
    # 6. Повторно устанавливаем атрибуты для надёжности
    window.attributes('-toolwindow', False)
    window.resizable(True, True)
    # ================================================


def fix_window_buttons_after_geometry(window: tk.Toplevel) -> None:
    """
    Вызывать ПОСЛЕ установки геометрии окна.
    Принудительно возвращает кнопки свернуть/развернуть,
    которые могли быть скрыты из-за кастомного размера окна.
    
    Args:
        window: окно Toplevel для исправления
    """
    window.update_idletasks()
    
    # Сбрасываем и заново устанавливаем атрибуты
    window.attributes('-toolwindow', False)
    window.attributes('-disabled', False)
    window.resizable(True, True)
    
    # Кратковременно скрываем и показываем окно,
    # чтобы Windows перерисовала заголовок с кнопками
    try:
        current_state = window.state()
        if current_state == 'normal':
            # Не используем withdraw/deiconify — они ломают позицию окна
            # Вместо этого просто обновляем геометрию
            window.geometry(window.geometry())
    except Exception:
        pass


def ensure_window_visible(window: tk.Toplevel) -> None:
    """
    Гарантирует, что окно видно и не перекрывается панелью задач.
    Вызывать после отображения окна.
    
    Args:
        window: окно Toplevel для проверки
    """
    window.update_idletasks()
    
    # Получаем текущую геометрию
    geom = window.geometry()
    parts = geom.split('+')
    if len(parts) >= 3:
        try:
            x = int(parts[1])
            y = int(parts[2])
            w = int(parts[0].split('x')[0])
            h = int(parts[0].split('x')[1])
        except (ValueError, IndexError):
            return
        
        # Получаем размеры экрана
        screen_h = window.winfo_screenheight()
        
        # Если окно уходит за нижний край (панель задач)
        if y + h > screen_h - 50:
            # Поднимаем окно вверх
            new_y = max(40, screen_h - h - 60)
            window.geometry(f"{w}x{h}+{x}+{new_y}")
            window.update_idletasks()