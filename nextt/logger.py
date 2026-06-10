"""
Настройка логирования для NextT.
Заменяет все print() вызовы на структурированные логи.
"""

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logger(
    name: str = "nextt",
    log_file: str = None,
    level: int = logging.WARNING,
    max_bytes: int = 5 * 1024 * 1024,
    backup_count: int = 3,
) -> logging.Logger:
    """
    Создаёт и настраивает логгер.

    В production-режиме (EXE) пишет только в консоль на уровне WARNING.
    В режиме разработки можно включить запись в файл.

    Args:
        name: имя логгера
        log_file: путь к файлу лога (None = только консоль)
        level: уровень логирования
        max_bytes: максимальный размер файла до ротации
        backup_count: количество резервных копий

    Returns:
        Настроенный экземпляр Logger
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Удаляем старые handlers если есть
    if logger.handlers:
        logger.handlers.clear()

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)-7s] %(message)s",
        datefmt="%H:%M:%S",
    )

    # Консольный handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # Файловый handler — если передан путь к файлу
    if log_file:
        try:
            file_handler = RotatingFileHandler(
                log_file, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
            )
            file_handler.setLevel(level)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
            print(f"[LOG] Логирование в файл: {log_file}")
        except Exception as e:
            print(f"[LOG] Не удалось создать файл лога: {e}")

    return logger


# Глобальный логгер — импортировать в других модулях как:
# from nextt.logger import get_logger
# logger = get_logger(__name__)
_main_logger = None


def get_logger(name: str = "nextt") -> logging.Logger:
    """Возвращает настроенный логгер для модуля."""
    global _main_logger
    if _main_logger is None:
        _main_logger = setup_logger()
    return _main_logger.getChild(name)