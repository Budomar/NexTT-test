"""
Экспериментальные модули NextTТ.
"""

from .equipment_normalizer import EquipmentNormalizer, ParsedEquipment
from .paste_handler import EXPERIMENTAL_ENABLED, show_paste_dialog
from .universal_parser import UniversalParser
from .equipment_dialog import EquipmentDialog
from .paste_dialog import PasteDialog

__all__ = [
    'EquipmentNormalizer',
    'ParsedEquipment',
    'EXPERIMENTAL_ENABLED',
    'show_paste_dialog',
    'UniversalParser',
    'EquipmentDialog',
    'PasteDialog',
]