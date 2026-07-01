"""
run_tests.py - Скрипт для ручного запуска регрессионных тестов.
Читает regression_tests.txt, прогоняет запросы через EquipmentNormalizer,
выводит отчет в консоль и сохраняет в файл.
"""
import os
import sys
from datetime import datetime
import pandas as pd

# Добавляем корневую папку проекта в путь поиска модулей
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

try:
    from nextt.config import get_resource_path
    from nextt.experimental.equipment_normalizer import EquipmentNormalizer
except ImportError as e:
    print(f"❌ Ошибка импорта модулей: {e}")
    print("Убедитесь, что скрипт запущен из корневой папки проекта, где лежит папка nextt.")
    sys.exit(1)

TEST_FILE = "regression_tests.txt"
REPORT_DIR = os.path.join(ROOT_DIR, "test_reports")

def load_test_cases(filepath):
    """Загружает тесты из текстового файла."""
    cases = []
    if not os.path.exists(filepath):
        print(f"❌ Файл тестов не найден: {filepath}")
        return cases

    with open(filepath, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            parts = [p.strip() for p in line.split('|')]
            if len(parts) < 3:
                print(f"⚠️ Строка {line_num}: неверный формат. Ожидается: Запрос | Артикул | Кол-во")
                continue

            query = parts[0]
            expected_art = parts[1].upper()
            expected_qty = int(parts[2])
            category = parts[3] if len(parts) > 3 else "без категории"
            comment = parts[4] if len(parts) > 4 else ""

            cases.append({
                'line_num': line_num,
                'query': query,
                'expected_art': expected_art,
                'expected_qty': expected_qty,
                'category': category,
                'comment': comment
            })
    return cases

def run_tests():
    """Основная функция запуска тестов."""
    print("🔄 Загрузка базы данных и инициализация нормализатора...")
    try:
        excel_path = get_resource_path("Все_категории.xlsx")
        if not os.path.exists(excel_path):
            print(f"❌ Файл базы не найден: {excel_path}")
            return

        # Загружаем прайс-лист. Используем тот же движок, что и в основном коде.
        df = pd.read_excel(excel_path, sheet_name="Прайс", engine='openpyxl')
        # Отключаем отладочный вывод, чтобы не забивать консоль логами нормализатора
        normalizer = EquipmentNormalizer(df, debug=False)
    except Exception as e:
        print(f"❌ Ошибка инициализации: {e}")
        return

    test_cases = load_test_cases(TEST_FILE)
    if not test_cases:
        print("⚠️ Тесты не найдены. Проверьте файл regression_tests.txt")
        return

    print(f"📦 Найдено тестов: {len(test_cases)}")
    print("="*90)

    results = []
    passed_count = 0
    failed_count = 0

    for i, tc in enumerate(test_cases, 1):
        query = tc['query']
        exp_art = tc['expected_art']
        exp_qty = tc['expected_qty']

        try:
            # Запускаем поиск через нормализатор (как это делает основной скрипт)
            res = normalizer.match_line(query)
            act_art = str(res.get('article', '')).strip().upper()
            act_qty = res.get('quantity', 0)
            is_success = res.get('success', False)

            # Проверка результатов
            art_ok = act_art == exp_art
            qty_ok = act_qty == exp_qty
            test_passed = art_ok and qty_ok and is_success

            if test_passed:
                passed_count += 1
                status = "✅ PASS"
            else:
                failed_count += 1
                status = "❌ FAIL"

            results.append({
                'num': i,
                'status': status,
                'query': query,
                'exp_art': exp_art,
                'act_art': act_art,
                'exp_qty': exp_qty,
                'act_qty': act_qty,
                'passed': test_passed,
                'comment': tc['comment']
            })
        except Exception as e:
            failed_count += 1
            results.append({
                'num': i, 'status': '💥 ERROR', 'query': query,
                'exp_art': exp_art, 'act_art': 'ERR',
                'exp_qty': exp_qty, 'act_qty': 'ERR',
                'passed': False, 'comment': str(e)
            })

    # Вывод результатов в консоль
    for r in results:
        print(f"{r['status']} | №{r['num']:02} | Арт: {r['exp_art']} -> {r['act_art']} | Кол: {r['exp_qty']} -> {r['act_qty']}")
        print(f"       Запрос: \"{r['query']}\"")
        if not r['passed'] and r['comment']:
            print(f"       💬 {r['comment']}")
        print("-" * 90)

    print(f"\n📊 ИТОГ: ВСЕГО {len(results)} | ✅ ПРОЙДЕНО: {passed_count} | ❌ НЕ ПРОЙДЕНО: {failed_count}")

    # Сохранение отчета в файл
    os.makedirs(REPORT_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    report_path = os.path.join(REPORT_DIR, f"test_report_{timestamp}.txt")

    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(f"ОТЧЕТ ТЕСТИРОВАНИЯ: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\n")
        f.write("="*90 + "\n")
        f.write(f"ВСЕГО: {len(results)} | ПРОЙДЕНО: {passed_count} | НЕ ПРОЙДЕНО: {failed_count}\n")
        f.write("="*90 + "\n\n")
        for r in results:
            f.write(f"{r['status']} | №{r['num']:02}\n")
            f.write(f"  Запрос: {r['query']}\n")
            f.write(f"  Ожидалось: Арт={r['exp_art']}, Кол={r['exp_qty']}\n")
            f.write(f"  Получено:  Арт={r['act_art']}, Кол={r['act_qty']}\n")
            if r['comment']:
                f.write(f"  Примечание: {r['comment']}\n")
            f.write("-" * 90 + "\n")

    print(f"📄 Полный отчет сохранен: {report_path}")

if __name__ == "__main__":
    run_tests()