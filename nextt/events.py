"""
Легковесная шина событий для связи модулей без прямых зависимостей.
"""

from typing import Any, Callable, Dict, List
from nextt.logger import get_logger

logger = get_logger(__name__)


class EventBus:
    """
    Простая шина событий.
    Модули подписываются на топики и получают уведомления
    без необходимости знать друг о друге.
    """

    def __init__(self):
        self._subscribers: Dict[str, List[Callable]] = {}

    def subscribe(self, topic: str, callback: Callable[..., Any]) -> None:
        """Подписаться на событие."""
        if topic not in self._subscribers:
            self._subscribers[topic] = []
        if callback not in self._subscribers[topic]:
            self._subscribers[topic].append(callback)
            logger.debug(f"Подписка на '{topic}': {callback.__name__}")

    def unsubscribe(self, topic: str, callback: Callable) -> None:
        """Отписаться от события."""
        if topic in self._subscribers:
            self._subscribers[topic] = [
                cb for cb in self._subscribers[topic] if cb != callback
            ]

    def emit(self, topic: str, **kwargs) -> None:
        """Отправить событие всем подписчикам."""
        if topic not in self._subscribers:
            return
        for callback in self._subscribers[topic]:
            try:
                callback(**kwargs)
            except Exception as e:
                logger.error(
                    f"Ошибка в обработчике '{topic}' → "
                    f"{getattr(callback, '__name__', str(callback))}: {e}"
                )

    def clear(self) -> None:
        """Очистить все подписки."""
        self._subscribers.clear()


# Глобальный экземпляр (синглтон) — импортируется всеми модулями
bus = EventBus()


# ======================================================================
# Темы событий
# ======================================================================
class Events:
    """Имена всех событий в приложении."""
    # Данные
    DATA_LOADED = "data:loaded"
    PATTERNS_UPDATED = "patterns:updated"

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

    # Шрифты (НОВОЕ)
    FONT_SCALE_CHANGED = "font:scale_changed"