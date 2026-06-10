"""
Центральная конфигурация приложения NextT.
Все пути, константы и параметры загружаются здесь.
"""

import os
import sys
import json
from pathlib import Path
from typing import Any, Dict, Optional


class AppConfig:
    """Загружает и хранит настройки приложения."""

    # Стандартные значения
    DEFAULTS = {
        "window_geometry": {
            "x": 0,
            "y": 0,
            "width": 1200,
            "height": 800,
            "zoomed": False,
        },
        "font_scale_factor": 1.0,  # Коэффициент масштабирования шрифтов
    }

    def __init__(self, config_path: Optional[str] = None):
        """Загружает конфигурацию из JSON-файла."""
        if config_path:
            self._config_path = Path(config_path)
        else:
            # Определяем путь к settings.json
            if getattr(sys, 'frozen', False):
                base = Path(sys.executable).parent
            else:
                base = Path(__file__).parent.parent  # на уровень выше пакета nextt
            self._config_path = base / "settings.json"

        self._data: Dict[str, Any] = self.DEFAULTS.copy()
        self._load()

    def _load(self) -> None:
        """Читает настройки из файла, если он существует."""
        if self._config_path.exists():
            try:
                with open(self._config_path, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                # Мержим: сохранённые значения перезаписывают дефолтные
                for key, value in saved.items():
                    if key in self._data and isinstance(self._data[key], dict) and isinstance(value, dict):
                        self._data[key].update(value)
                    else:
                        self._data[key] = value
            except json.JSONDecodeError:
                pass  # Файл поврежден — используем дефолты

    def save(self) -> None:
        """Сохраняет текущие настройки в файл."""
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._config_path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    def get(self, key: str, default: Any = None) -> Any:
        """Получает значение по ключу."""
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Устанавливает значение и сразу сохраняет."""
        self._data[key] = value
        self.save()

    # --- Удобные свойства ---
    @property
    def window_geometry(self) -> Dict[str, Any]:
        return self._data.get("window_geometry", {})

    @property
    def font_scale_factor(self) -> float:
        """Коэффициент масштабирования шрифтов."""
        return self._data.get("font_scale_factor", 1.0)


# --- Пути к ресурсам (зависят от окружения) ---
def get_resource_path(relative_path: str) -> str:
    """
    Возвращает абсолютный путь к ресурсу.
    Работает и при запуске скрипта, и в собранном PyInstaller EXE.
    """
    import sys
    import os

    try:
        # PyInstaller создаёт временную папку _MEIPASS
        base = sys._MEIPASS
        # В EXE все файлы лежат в корне _MEIPASS
        return os.path.join(base, relative_path)
    except AttributeError:
        # При обычном запуске — ищем в папке resources рядом с пакетом nextt
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(base, "resources", relative_path)

# Экземпляр конфигурации (будет создан один раз при старте)
config = AppConfig()