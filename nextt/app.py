"""
Главный координатор приложения NexTT.
Создаёт все компоненты и связывает их через EventBus.
"""

import tkinter as tk
from typing import Optional

from nextt.config import config
from nextt.logger import get_logger, setup_logger
from nextt.utils.dpi import cache_scale, get_cached_scale
from nextt.utils.window_manager import WindowManager
from nextt.utils.font_manager import FontManager
from nextt.core.data_provider import DataProvider
from nextt.core.normalizer import SpecNormalizer
from nextt.events import bus

logger = get_logger(__name__)


# ======================================================================
# Темы событий (константы для подписки/отправки)
# ======================================================================
class Events:
    """Имена всех событий в приложении."""
    # Данные
    DATA_LOADED = "data:loaded"

    # UI
    CONNECTION_CHANGED = "ui:connection_changed"
    TYPE_CHANGED = "ui:type_changed"
    MATRIX_CELL_CHANGED = "ui:matrix_cell_changed"

    # Окна
    PREVIEW_OPENED = "window:preview_opened"
    PREVIEW_CLOSED = "window:preview_closed"
    CORRESPONDENCE_OPENED = "window:correspondence_opened"
    CORRESPONDENCE_CLOSED = "window:correspondence_closed"

    # Спецификация
    SPEC_GENERATED = "spec:generated"
    SPEC_SAVED = "spec:saved"

    # Ошибки
    ERROR = "error"

    # Шрифты
    FONT_SCALE_CHANGED = "font:scale_changed"


# ======================================================================
# Координатор
# ======================================================================
class App:
    """Главный класс приложения NexTT."""

    def __init__(self):
        # --- Логирование ---
        setup_logger(level="INFO", log_file=None)
        
        logger.info("=" * 60)
        logger.info("Запуск NexTT 2.4")
        logger.info("=" * 60)

        # --- Root-окно (ПОЛНОСТЬЮ СКРЫТО до готовности) ---
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.title("NexTT 2.4")

        # --- Настройка DPI ---
        cache_scale(self.root)
        self.scale = get_cached_scale()
        logger.info(f"DPI scale factor: {self.scale:.2f}")

        # --- Иконка ---
        try:
            from nextt.config import get_resource_path
            icon_path = get_resource_path("icon.ico")
            if icon_path and __import__('os').path.exists(icon_path):
                self.root.iconbitmap(icon_path)
        except Exception as e:
            logger.debug(f"Иконка не загружена: {e}")

        # --- Компоненты ---
        self.window_manager = WindowManager(self.root)
        self.data_provider = DataProvider()
        self.normalizer = SpecNormalizer(debug=False, templates_file="templates.json")
        
        # --- Менеджер шрифтов ---
        self.font_manager = FontManager()

        # --- Менеджер шаблонов ---
        from nextt.patterns.template_manager import TemplateManager
        self.template_manager = TemplateManager()

        # --- Переменные состояния ---
        self.connection_var = tk.StringVar(value="VK-правое")
        self.radiator_type_var = tk.StringVar(value="10")
        self.entry_values: dict = {}

        # --- Загружаем сохранённую геометрию окна ---
        self._load_window_geometry()

        # --- Подписки на события ---
        self._setup_events()

        # --- Создаём главное окно (GUI) ---
        from nextt.ui.main_window import MainWindow
        self.main_window = MainWindow(self)

        # --- Для хранения исходных данных при повторном импорте ---
        self._last_raw_data = None
        self._last_file_path = None
        self._last_file_type = None
        self._last_correspondence_dialog = None
        self._all_correspondence_data = None
        self._last_correspondence_data = None
        self._all_correspondence_data_for_export = None   
        self._last_imported_file = None

        # --- Генератор спецификаций ---
        from nextt.export.spec_generator import SpecGenerator
        self.spec_generator = SpecGenerator(self.data_provider)

        # --- Принудительная отрисовка интерфейса ---
        self.root.update_idletasks()

        # --- Применяем сохранённую геометрию окна ---
        self._apply_window_geometry()

        # --- Применяем сохранённый масштаб шрифтов ---
        if self.font_manager.scale != 1.0:
            self.font_manager.refresh_all_windows(self.root)

        # --- Показываем окно ---
        self.root.deiconify()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        # --- Отправляем событие о готовности ---
        bus.emit(Events.DATA_LOADED, count=len(self.data_provider.radiators_df))

        logger.info("Приложение готово к работе")

    def _load_window_geometry(self) -> None:
        """Загружает сохранённую геометрию окна из settings.json."""
        import os, sys, json

        if getattr(sys, 'frozen', False):
            base_path = os.path.dirname(sys.executable)
        else:
            base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        settings_path = os.path.join(base_path, "settings.json")

        self.window_x = 0
        self.window_y = 0
        self.window_width = 1913
        self.window_height = 329
        self.window_zoomed = False

        if os.path.exists(settings_path):
            try:
                with open(settings_path, "r", encoding="utf-8") as f:
                    settings = json.load(f)

                if "window_geometry" in settings:
                    wg = settings["window_geometry"]
                    
                    if wg.get("x") is not None:
                        self.window_x = wg.get("x")
                    if wg.get("y") is not None:
                        self.window_y = wg.get("y")
                    if wg.get("width") is not None:
                        self.window_width = wg.get("width")
                    if wg.get("height") is not None:
                        self.window_height = wg.get("height")
                    self.window_zoomed = wg.get("zoomed", False)

            except Exception as e:
                logger.debug(f"Ошибка загрузки геометрии окна: {e}")

    def _apply_window_geometry(self) -> None:
        """Применяет сохранённую геометрию окна."""
        self.root.geometry(f"{self.window_width}x{self.window_height}+{self.window_x}+{self.window_y}")

        if self.window_zoomed:
            self.root.after(50, lambda: self.root.state('zoomed'))

        logger.debug(f"Геометрия окна: {self.window_width}x{self.window_height}+{self.window_x}+{self.window_y}, развёрнуто: {self.window_zoomed}")
    
    # ==================================================================
    # Подписки на события
    # ==================================================================
    def _setup_events(self) -> None:
        """Настраивает обработчики событий."""
        bus.subscribe(Events.CONNECTION_CHANGED, self._on_connection_changed)
        bus.subscribe(Events.TYPE_CHANGED, self._on_type_changed)
        bus.subscribe(Events.ERROR, self._on_error)

    def _on_connection_changed(self, connection: str) -> None:
        """Обработчик смены подключения."""
        logger.info(f"Подключение изменено: {connection}")
        self.connection_var.set(connection)

    def _on_type_changed(self, rad_type: str) -> None:
        """Обработчик смены типа радиатора."""
        logger.info(f"Тип радиатора изменён: {rad_type}")
        self.radiator_type_var.set(rad_type)

    def _on_error(self, message: str, exception: Optional[Exception] = None) -> None:
        """Обработчик ошибок."""
        logger.error(f"Ошибка: {message}")
        if exception:
            logger.exception(exception)

    # ==================================================================
    # Публичные методы
    # ==================================================================
    def filter_radiators(self, connection: str = None, rad_type: str = None):
        """Фильтрует радиаторы по параметрам."""
        conn = connection or self.connection_var.get()
        rt = rad_type or self.radiator_type_var.get()
        return self.data_provider.filter_radiators(conn, rt)

    def find_analog(self, connection: str, rad_type: str, height: int, length: int):
        """Ищет аналог LaggarTT по параметрам."""
        return self.data_provider.find_analog(connection, rad_type, height, length)

    def parse_radiator_name(self, name: str):
        """Парсит название радиатора конкурента."""
        return self.normalizer.normalize_and_extract(name)

    def find_matching_template(self, name: str):
        """Ищет подходящий шаблон для названия."""
        return self.template_manager.find_matching_template(name)

    def learn_template(self, original_name: str, connection: str, rad_type: str,
                       height: int, length: int) -> None:
        """Обучает новый шаблон."""
        template = self.template_manager.analyze_and_create_template(
            original_name, connection, rad_type, height, length
        )
        if template:
            self.template_manager.save()
            # Перезагружаем шаблоны в SpecNormalizer
            self.normalizer.reload_templates()
        return template

    # ==================================================================
    # Жизненный цикл
    # ==================================================================
    def on_close(self) -> None:
        """Обработчик закрытия главного окна."""
        logger.info("Закрытие приложения...")

        try:
            is_zoomed = self.root.state() == 'zoomed'
            
            if is_zoomed:
                x = None
                y = None
                width = None
                height = None
            else:
                x = self.root.winfo_x()
                y = self.root.winfo_y()
                width = self.root.winfo_width()
                height = self.root.winfo_height()

            config.set("window_geometry", {
                "x": x,
                "y": y,
                "width": width,
                "height": height,
                "zoomed": is_zoomed,
            })
            config.save()
            logger.debug(f"Сохранена геометрия окна: x={x}, y={y}, w={width}, h={height}, zoomed={is_zoomed}")
            
        except Exception as e:
            logger.debug(f"Ошибка сохранения геометрии окна: {e}")

        self.window_manager.close_all()
        self.root.destroy()
        logger.info("Приложение завершено")
        
    def run(self) -> None:
        """Запускает главный цикл обработки событий."""
        self.root.mainloop()