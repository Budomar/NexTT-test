"""
Экспериментальный модуль для новых фич.
Все изменения здесь изолированы от основного кода.
"""

from .paste_handler import register_paste_button, show_paste_dialog
from .equipment_searcher import EquipmentSearcher
from .equipment_dialog import EquipmentDialog
from .equipment_normalizer import EquipmentNormalizer, ParsedEquipment

__all__ = [
    'register_paste_button', 
    'show_paste_dialog', 
    'EquipmentSearcher', 
    'EquipmentDialog',
    'EquipmentNormalizer',
    'ParsedEquipment'
]