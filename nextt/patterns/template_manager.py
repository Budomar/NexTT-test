"""
Менеджер обучаемых шаблонов для распознавания названий радиаторов.
Шаблоны хранят МАСКУ названия с маркерами {type}, {height}, {length}.
Применяются ко всем похожим названиям.
"""

import json
import re
import os
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple

from nextt.logger import get_logger

logger = get_logger(__name__)


class Template:
    """Один обучаемый шаблон — маска названия с маркерами."""

    def __init__(
        self,
        template_id: str = "",
        name: str = "",
        original_example: str = "",
        mask: str = "",
        connection: str = "VK-правое",
        type_transform: Dict[str, str] = None,
        height_transform: str = "direct",
        length_transform: str = "direct",
        priority: int = 95,
    ):
        self.id = template_id
        self.name = name
        self.original_example = original_example
        self.mask = mask
        self.connection = connection
        self.type_transform = type_transform or {}
        self.height_transform = height_transform
        self.length_transform = length_transform
        self.priority = priority
        self.created_at = datetime.now().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "original_example": self.original_example,
            "mask": self.mask,
            "connection": self.connection,
            "type_transform": self.type_transform,
            "height_transform": self.height_transform,
            "length_transform": self.length_transform,
            "priority": self.priority,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Template':
        return cls(
            template_id=data.get("id", ""),
            name=data.get("name", ""),
            original_example=data.get("original_example", ""),
            mask=data.get("mask", ""),
            connection=data.get("connection", "VK-правое"),
            type_transform=data.get("type_transform", {}),
            height_transform=data.get("height_transform", "direct"),
            length_transform=data.get("length_transform", "direct"),
            priority=data.get("priority", 95),
        )


class TemplateManager:
    """Управляет обучаемыми шаблонами."""

    VALID_HEIGHTS = [300, 400, 500, 600, 900]
    VALID_LENGTHS = list(range(400, 3100, 100))

    def __init__(self, templates_file: str = "templates.json"):
        self._file_path = templates_file
        self._templates: List[Template] = []
        self.load()

    def load(self) -> None:
        """Загружает шаблоны из файла."""
        if not os.path.exists(self._file_path):
            logger.info(f"Файл шаблонов не найден: {self._file_path}")
            return

        try:
            with open(self._file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            templates_data = data.get("шаблоны", []) if isinstance(data, dict) else data
            self._templates = [Template.from_dict(t) for t in templates_data]
            logger.info(f"Загружено {len(self._templates)} шаблонов")
        except Exception as e:
            logger.error(f"Ошибка загрузки шаблонов: {e}")
            self._templates = []

    def save(self) -> None:
        """Сохраняет шаблоны в файл."""
        try:
            data = {
                "версия": "1.0",
                "шаблоны": [t.to_dict() for t in self._templates]
            }
            with open(self._file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info(f"Сохранено {len(self._templates)} шаблонов")
        except Exception as e:
            logger.error(f"Ошибка сохранения шаблонов: {e}")

    # ==================================================================
    # АНАЛИЗ И СОЗДАНИЕ ШАБЛОНА
    # ==================================================================

    def analyze_and_create_template(
        self,
        original_name: str,
        analog_connection: str,
        analog_type: str,
        analog_height: int,
        analog_length: int,
    ) -> Optional[Template]:
        """
        Анализирует название и создаёт шаблон-маску.
        Теперь поддерживает любые форматы длины (0,4м, 1,2м, 1,0м, 1200мм и т.д.)
        """
        name = original_name.strip()
        
        logger.info("=" * 60)
        logger.info(f"📊 СОЗДАНИЕ ШАБЛОНА")
        logger.info(f"   Название: '{name}'")
        logger.info(f"   Аналог: {analog_connection} {analog_type}/{analog_height}/{analog_length}")
        logger.info(f"   Тип данных height: {type(analog_height)}, value: {analog_height}")
        logger.info(f"   Тип данных length: {type(analog_length)}, value: {analog_length}")
        logger.info("=" * 60)
        
        # ==================================================================
        # ШАГ 1: Находим все числа в названии
        # ==================================================================
        numbers = re.findall(r'\d+', name)
        logger.info(f"📊 Найдены числа: {numbers}")
        
        if len(numbers) < 3:
            logger.warning(f"   ❌ Найдено меньше 3 чисел")
            return None
        
        # ==================================================================
        # ШАГ 2: Находим также десятичные числа (с запятой или точкой)
        # ==================================================================
        decimal_numbers = re.findall(r'\d+[.,]\d+', name)
        logger.info(f"📊 Найдены десятичные числа: {decimal_numbers}")
        
        # ==================================================================
        # ШАГ 3: Сопоставляем числа с параметрами аналога
        # ==================================================================
        type_idx = -1
        type_value = None
        height_idx = -1
        height_value = None
        length_idx = -1
        length_value = None
        length_is_decimal = False
        
        # Ищем тип
        for i, num in enumerate(numbers):
            if num == analog_type or (num == '12' and analog_type == '21'):
                type_idx = i
                type_value = num
                logger.info(f"   ✅ Тип: число '{num}' на позиции {i}")
                break
        
        if type_idx == -1:
            logger.warning(f"   ❌ Не найдено число для типа {analog_type}")
            return None
        
        # Ищем высоту - с приоритетами и исключением номеров строк
        possible_height_numbers = []
        
        for i, num in enumerate(numbers):
            if i == type_idx:
                continue
            
            # Проверяем, не является ли число номером строки
            pos = name.find(num)
            if pos != -1 and pos < 10 and len(num) <= 2:
                next_char = name[pos + len(num)] if pos + len(num) < len(name) else ''
                if next_char == '.':
                    logger.info(f"   ⏭ Пропускаем номер строки: '{num}' на позиции {pos}")
                    continue
            
            try:
                num_int = int(num)
                logger.info(f"   Проверяем число '{num}' = {num_int} мм, нужно {analog_height} мм")
                
                if num_int == analog_height:
                    possible_height_numbers.append((i, num, "direct", 0))
                    logger.info(f"      Прямое совпадение: {num_int} == {analog_height}")
                elif num_int * 100 == analog_height:
                    possible_height_numbers.append((i, num, "code * 100", 1))
                    logger.info(f"      Код * 100: {num_int} * 100 == {analog_height}")
                elif num_int * 10 == analog_height:
                    possible_height_numbers.append((i, num, "code * 10", 2))
                    logger.info(f"      Код * 10: {num_int} * 10 == {analog_height}")
                elif num_int // 100 == analog_height and num_int % 100 == 0:
                    possible_height_numbers.append((i, num, "code / 100", 3))
                    logger.info(f"      Код / 100: {num_int} // 100 == {analog_height}")
                elif num_int // 10 == analog_height and num_int % 10 == 0:
                    possible_height_numbers.append((i, num, "code / 10", 4))
                    logger.info(f"      Код / 10: {num_int} // 10 == {analog_height}")
            except (ValueError, TypeError):
                continue
        
        possible_height_numbers.sort(key=lambda x: x[3])
        
        if possible_height_numbers:
            height_idx = possible_height_numbers[0][0]
            height_value = possible_height_numbers[0][1]
            height_transform = possible_height_numbers[0][2]
            logger.info(f"   ✅ Высота: выбрано число '{height_value}' на позиции {height_idx} (transform: {height_transform})")
        else:
            logger.warning(f"   ❌ Не найдено подходящее число для высоты {analog_height}")
            return None
        
        # Ищем длину
        for dec_num in decimal_numbers:
            dec_num_clean = dec_num.replace(',', '.')
            try:
                dec_num_float = float(dec_num_clean)
                dec_num_mm = int(dec_num_float * 1000)
                logger.info(f"   Проверяем десятичное число '{dec_num}' → {dec_num_mm} мм, нужно {analog_length} мм")
                if dec_num_mm == analog_length:
                    length_idx = -2
                    length_value = dec_num
                    length_is_decimal = True
                    logger.info(f"   ✅ Длина: десятичное число '{dec_num}' на позиции → {analog_length} мм")
                    break
            except:
                pass
        
        if length_idx == -1:
            possible_length_numbers = []
            
            for i, num in enumerate(numbers):
                if i == type_idx or i == height_idx:
                    continue
                
                pos = name.find(num)
                if pos != -1 and pos < 10 and len(num) <= 2:
                    next_char = name[pos + len(num)] if pos + len(num) < len(name) else ''
                    if next_char == '.':
                        logger.info(f"   ⏭ Пропускаем номер строки: '{num}' на позиции {pos}")
                        continue
                
                try:
                    num_int = int(num)
                    logger.info(f"   Проверяем число '{num}' = {num_int} мм, нужно {analog_length} мм")
                    
                    if num_int == analog_length:
                        possible_length_numbers.append((i, num, "direct", 0))
                        logger.info(f"      Прямое совпадение: {num_int} == {analog_length}")
                    elif num_int * 10 == analog_length:
                        possible_length_numbers.append((i, num, "code * 10", 1))
                        logger.info(f"      Код * 10: {num_int} * 10 == {analog_length}")
                    elif num_int * 100 == analog_length:
                        possible_length_numbers.append((i, num, "code * 100", 2))
                        logger.info(f"      Код * 100: {num_int} * 100 == {analog_length}")
                    elif num_int // 10 == analog_length and num_int % 10 == 0:
                        possible_length_numbers.append((i, num, "code / 10", 3))
                        logger.info(f"      Код / 10: {num_int} // 10 == {analog_length}")
                    elif num_int // 100 == analog_length and num_int % 100 == 0:
                        possible_length_numbers.append((i, num, "code / 100", 4))
                        logger.info(f"      Код / 100: {num_int} // 100 == {analog_length}")
                except (ValueError, TypeError):
                    continue
            
            possible_length_numbers.sort(key=lambda x: x[3])
            
            if possible_length_numbers:
                length_idx = possible_length_numbers[0][0]
                length_value = possible_length_numbers[0][1]
                length_transform = possible_length_numbers[0][2]
                length_is_decimal = False
                logger.info(f"   ✅ Длина: выбрано число '{length_value}' на позиции {length_idx} (transform: {length_transform})")
            else:
                logger.warning(f"   ❌ Не найдено подходящее число для длины {analog_length}")
                return None
        
        # ==================================================================
        # ШАГ 4: Находим позиции чисел в строке для создания маски
        # ==================================================================
        all_positions = []
        temp_name = name
        offset = 0
        
        for num in numbers:
            pos = temp_name.find(num)
            if pos != -1:
                all_positions.append((offset + pos, offset + pos + len(num), num, False))
                offset += pos + len(num)
                temp_name = temp_name[pos + len(num):]
            else:
                all_positions.append((0, 0, num, False))
        
        if length_is_decimal:
            dec_pos = name.find(length_value)
            if dec_pos != -1:
                all_positions = [p for p in all_positions if p[2] != length_value]
                all_positions.append((dec_pos, dec_pos + len(length_value), length_value, True))
        
        all_positions.sort(key=lambda x: x[0])
        
        # Выбираем нужные числа
        selected = []
        found_type = False
        found_height = False
        found_length = False
        
        for start, end, num, is_decimal in all_positions:
            if not found_type and (num == type_value or (type_value == '12' and num == '21')):
                selected.append((start, end, num, 'type', is_decimal))
                found_type = True
            elif not found_height and num == height_value:
                selected.append((start, end, num, 'height', is_decimal))
                found_height = True
            elif not found_length and num == length_value:
                selected.append((start, end, num, 'length', is_decimal))
                found_length = True
        
        selected.sort(key=lambda x: x[0])
        
        # ==================================================================
        # ШАГ 5: Очищаем префикс от номеров строк
        # ==================================================================
        if selected:
            first_selected_start = selected[0][0]
            prefix = name[:first_selected_start]
            
            # Ищем и удаляем номера строк в префиксе
            # Паттерн: цифры + точка + цифры + точка + пробел
            pattern = r'^(\d+\.\d+\.\s*)'
            match = re.match(pattern, prefix)
            
            if match:
                line_number = match.group(1)
                cleaned_prefix = prefix[len(line_number):]
                logger.info(f"   🗑️ Удаляем номер строки из префикса: '{line_number}'")
                logger.info(f"   📝 Очищенный префикс: '{cleaned_prefix}'")
                
                # Обновляем name, удаляя номер строки
                name = cleaned_prefix + name[first_selected_start:]
                
                # Корректируем позиции в selected (сдвигаем влево на длину удаленного номера строки)
                shift = len(line_number)
                selected = [(s - shift, e - shift, num, marker, dec) for s, e, num, marker, dec in selected]
                
                # Обновляем last_end для создания маски
                last_end = selected[0][0]
                
                logger.info(f"   📝 Обновленное имя: '{name}'")
                logger.info(f"   📝 Новые позиции: {selected}")
            else:
                last_end = 0
        else:
            last_end = 0
        
        # ==================================================================
        # ШАГ 6: Создаём маску
        # ==================================================================
        mask = ""
        
        for start, end, num, marker, is_decimal in selected:
            mask += name[last_end:start]
            if marker == 'type':
                mask += '{type}'
            elif marker == 'height':
                mask += '{height}'
            else:
                mask += '{length}'
            last_end = end
        
        mask += name[last_end:]
        
        logger.info(f"   📝 Маска: '{mask}'")
        
        # ==================================================================
        # ШАГ 7: Определяем преобразования
        # ==================================================================
        def detect_transform(code_str: str, real_value: int, is_decimal: bool = False) -> str:
            if is_decimal:
                logger.info(f"   Десятичное число '{code_str}' → parse_decimal")
                return "parse_decimal"
            
            try:
                code_int = int(code_str)
                if code_int == real_value:
                    return "direct"
                elif code_int * 10 == real_value:
                    return "code * 10"
                elif code_int * 100 == real_value:
                    return "code * 100"
                elif code_int // 10 == real_value and code_int % 10 == 0:
                    return "code / 10"
                elif code_int // 100 == real_value and code_int % 100 == 0:
                    return "code / 100"
                else:
                    return "direct"
            except:
                return "direct"
        
        height_transform = detect_transform(height_value, analog_height, False)
        length_transform = detect_transform(length_value, analog_length, length_is_decimal)
        
        logger.info(f"   Преобразование высоты: '{height_value}' → {analog_height} -> {height_transform}")
        logger.info(f"   Преобразование длины: '{length_value}' → {analog_length} -> {length_transform}")
        
        type_transform = {}
        if type_value == '12' and analog_type == '21':
            type_transform = {"12": "21"}
        
        # ==================================================================
        # ШАГ 8: Создаём шаблон
        # ==================================================================
        template_id = f"template_{len(self._templates) + 1:03d}"
        prefix_name = original_name[:20].upper() if original_name else "UNKNOWN"
        template_name = f"{prefix_name}..."
        
        template = Template(
            template_id=template_id,
            name=template_name,
            original_example=original_name,
            mask=mask,
            connection=analog_connection,
            type_transform=type_transform,
            height_transform=height_transform,
            length_transform=length_transform,
            priority=95,
        )
        
        self._templates.append(template)
        self.save()
        
        logger.info(f"   ✅ Шаблон создан: {template_name}")
        logger.info(f"   ID: {template_id}")
        logger.info("=" * 60)
        
        return template
    # ==================================================================
    # ПРИМЕНЕНИЕ ШАБЛОНА
    # ==================================================================

    def apply_templates(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Применяет все шаблоны к названию.
        Возвращает лучший результат.
        """
        best_result = None
        best_priority = 0
        
        for template in self._templates:
            result = self._apply_template(template, name)
            if result:
                if template.priority > best_priority:
                    best_priority = template.priority
                    best_result = result
        
        return best_result

    def _apply_template(self, template: Template, name: str) -> Optional[Dict[str, Any]]:
        """
        Применяет один шаблон к названию.
        Теперь ищет шаблон в любом месте строки (не только в начале).
        """
        # Получаем маску
        mask = template.mask
        
        # Превращаем маску в регулярное выражение
        regex_pattern = ""
        i = 0
        while i < len(mask):
            if mask[i] == '{':
                j = mask.find('}', i)
                if j != -1:
                    marker = mask[i:j+1]
                    if marker == '{type}':
                        regex_pattern += r'(\d+)'
                    elif marker == '{height}':
                        regex_pattern += r'(\d+)'
                    elif marker == '{length}':
                        regex_pattern += r'([\d,]+)'
                    else:
                        regex_pattern += re.escape(marker)
                    i = j + 1
                    continue
            regex_pattern += re.escape(mask[i])
            i += 1
        
        # ================================================================
        # ИЗМЕНЕНИЕ: ищем шаблон в любом месте строки, а не только в начале
        # ================================================================
        # Было: regex_pattern = '^' + regex_pattern + '$'
        # Стало: ищем шаблон где угодно, но требуем, чтобы после шаблона
        #        не было других значимых символов (кроме пробелов и знаков препинания)
        # ================================================================
        # Ищем шаблон в любом месте строки
        # \b - граница слова, чтобы не захватывать часть другого слова
        search_pattern = r'\b' + regex_pattern + r'(?:\s|$|[,.;:!?])'
        
        logger.info(f"   Применяем шаблон: mask='{mask}'")
        logger.info(f"   RegEx (поиск): {search_pattern}")
        
        # Ищем совпадение в любом месте строки
        match = re.search(search_pattern, name, re.IGNORECASE)
        if not match:
            return None
        
        groups = match.groups()
        if len(groups) != 3:
            return None
        
        # Определяем порядок маркеров
        type_pos_in_mask = mask.find('{type}')
        height_pos_in_mask = mask.find('{height}')
        length_pos_in_mask = mask.find('{length}')
        
        marker_positions = []
        if type_pos_in_mask != -1:
            marker_positions.append((type_pos_in_mask, 'type'))
        if height_pos_in_mask != -1:
            marker_positions.append((height_pos_in_mask, 'height'))
        if length_pos_in_mask != -1:
            marker_positions.append((length_pos_in_mask, 'length'))
        marker_positions.sort(key=lambda x: x[0])
        
        type_str = None
        height_str = None
        length_str = None
        
        for idx, (_, marker) in enumerate(marker_positions):
            if idx < len(groups):
                if marker == 'type':
                    type_str = groups[idx]
                elif marker == 'height':
                    height_str = groups[idx]
                else:
                    length_str = groups[idx]
        
        if not type_str or not height_str or not length_str:
            return None
        
        logger.info(f"   Извлечено: тип={type_str}, высота={height_str}, длина={length_str}")
        
        # Преобразуем тип
        rad_type = template.type_transform.get(type_str, type_str)
        
        # Преобразуем высоту
        try:
            height = int(height_str)
            if template.height_transform == "code * 10":
                height = height * 10
            elif template.height_transform == "code * 100":
                height = height * 100
            elif template.height_transform == "code / 10":
                height = height // 10
            elif template.height_transform == "code / 100":
                height = height // 100
        except:
            height = 0
        
        # Преобразуем длину
        try:
            if template.length_transform == "code * 10":
                length = int(length_str) * 10
            elif template.length_transform == "code * 100":
                length = int(length_str) * 100
            elif template.length_transform == "code / 10":
                length = int(length_str) // 10
            elif template.length_transform == "code / 100":
                length = int(length_str) // 100
            elif template.length_transform == "parse_decimal":
                length_clean = length_str.replace(',', '.')
                length_float = float(length_clean)
                length = int(length_float * 1000)
            else:
                length = int(length_str)
        except:
            length = 0
        
        logger.info(f"   После преобразования: тип={rad_type}, высота={height}, длина={length}")
        
        # Валидация
        if height not in self.VALID_HEIGHTS:
            logger.info(f"   ❌ Высота {height} не в списке допустимых {self.VALID_HEIGHTS}")
            return None
        if length not in self.VALID_LENGTHS:
            logger.info(f"   ❌ Длина {length} не в списке допустимых")
            return None
        if rad_type not in ['10', '11', '20', '21', '22', '30', '33']:
            if rad_type == '12':
                rad_type = '21'
            else:
                logger.info(f"   ❌ Тип {rad_type} не в списке допустимых")
                return None
        
        return {
            "connection": template.connection,
            "rad_type": rad_type,
            "height": height,
            "length": length,
            "source": f"template_{template.id}",
            "confidence": template.priority / 100,
        }

    def find_matching_template(self, name: str) -> Optional[Template]:
        """Находит первый подходящий шаблон."""
        for template in self._templates:
            if self._apply_template(template, name):
                return template
        return None

    @property
    def count(self) -> int:
        return len(self._templates)