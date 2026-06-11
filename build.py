"""
Скрипт сборки NexTT 2.0 в EXE.
Включает экспериментальную фичу "Вставить из буфера".
Версия 2.0 с поддержкой новых модулей product_normalizer.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyInstaller.__main__ import run as pyinstaller_run

# ============================================================================
# БАЗОВЫЕ ПУТИ
# ============================================================================
base_dir = os.path.dirname(os.path.abspath(__file__))          # корень проекта
resources_dir = os.path.join(base_dir, "resources")            # папка с ресурсами
main_script = os.path.join(base_dir, "nextt", "main.py")       # точка входа

# ============================================================================
# ДОБАВЛЕНИЕ РЕСУРСОВ (папка resources/)
# ============================================================================
datas = []
for root, dirs, files in os.walk(resources_dir):
    for file in files:
        src = os.path.join(root, file)
        rel_path = os.path.relpath(root, resources_dir)
        if rel_path == ".":
            dst = "."
        else:
            dst = rel_path
        datas.append((src, dst))

# ============================================================================
# ДОБАВЛЕНИЕ ФАЙЛА ШАБЛОНОВ (templates.json)
# ============================================================================
templates_file = os.path.join(base_dir, "templates.json")
if os.path.exists(templates_file):
    datas.append((templates_file, "."))
    print(f"Добавлен шаблон: {templates_file}")
else:
    print("ВНИМАНИЕ: templates.json не найден, будет создан при первом запуске")

# ============================================================================
# ДОБАВЛЕНИЕ ЭКСПЕРИМЕНТАЛЬНОЙ ПАПКИ (nextt/experimental/)
# ============================================================================
experimental_dir = os.path.join(base_dir, "nextt", "experimental")
if os.path.exists(experimental_dir):
    for root, dirs, files in os.walk(experimental_dir):
        for file in files:
            if file.endswith('.py'):
                src = os.path.join(root, file)
                rel_path = os.path.relpath(root, base_dir)
                dst = rel_path
                datas.append((src, dst))
                print(f"Добавлен экспериментальный модуль: {src}")
    print(f"Экспериментальная папка добавлена: {experimental_dir}")
else:
    print("ВНИМАНИЕ: experimental папка не найдена, фича будет недоступна")

# ============================================================================
# ОСНОВНЫЕ ПАРАМЕТРЫ СБОРКИ
# ============================================================================
args = [
    main_script,
    "--name=NexTT-2.2",                    # ← ИМЯ ВЫХОДНОГО EXE (можно менять)
    "--onefile",                           # один EXE файл
    # "--windowed",                          # без консольного окна (убрать для dev)
    "--icon=" + os.path.join(resources_dir, "icon.ico"),  # иконка
    "--clean",                             # очистить временные файлы
    "--noconfirm",                         # не спрашивать подтверждение
]

# ============================================================================
# ДОБАВЛЕНИЕ ВСЕХ ФАЙЛОВ ДАННЫХ (resources, templates, experimental)
# ============================================================================
for src, dst in datas:
    args.append(f"--add-data={src}{os.pathsep}{dst}")

# ============================================================================
# СКРЫТЫЕ ИМПОРТЫ (библиотеки, которые PyInstaller может не найти сам)
# ============================================================================
hidden_imports = [
    # Основные библиотеки
    "pandas",
    "openpyxl",
    "tkinter",
    "tkinter.ttk",
    "pyperclip",
    "numpy",
    "xlrd",
    "chardet",
    
    # PDF библиотеки
    "fitz",
    "pymupdf",
    "pdfplumber",
    "PIL",
    "PIL.Image",
    "PIL.ImageTk",
    
    # Модули приложения
    "nextt",
    "nextt.app",
    "nextt.config",
    "nextt.logger",
    "nextt.events",
    "nextt.core.data_provider",
    "nextt.core.brackets",
    "nextt.core.normalizer",
    "nextt.patterns.template_manager",
    "nextt.parsing.excel_parser",
    "nextt.parsing.pdf_parser",
    "nextt.parsing.column_selector",
    "nextt.parsing.word_parser",
    "nextt.utils.dpi",
    "nextt.utils.window_manager",
    "nextt.utils.font_manager",
    "nextt.utils.update_checker",           # ← НОВЫЙ МОДУЛЬ (проверка обновлений)
    "nextt.ui.main_window",
    "nextt.ui.dialogs.correspondence",
    "nextt.ui.dialogs.meteor_selector",
    "nextt.ui.dialogs.preview",
    "nextt.ui.dialogs.page_selector",
    "nextt.export.excel_writer",
    "nextt.export.spec_generator",
    
    # Экспериментальные модули
    "nextt.experimental",
    "nextt.experimental.paste_handler",
    "nextt.experimental.paste_dialog",
    "nextt.experimental.equipment_searcher",
    "nextt.experimental.equipment_dialog",
    "nextt.experimental.equipment_normalizer",
    "nextt.experimental.product_normalizer",
    "nextt.experimental.universal_parser",
]

for mod in hidden_imports:
    args.append(f"--hidden-import={mod}")

# ============================================================================
# ИСКЛЮЧАЕМ НЕНУЖНЫЕ БОЛЬШИЕ БИБЛИОТЕКИ (уменьшают размер EXE)
# ============================================================================
excludes = [
    "matplotlib",
    "scipy",
    "pytest",
    "PyQt5",
    "PySide2",
    "wx",
]

for mod in excludes:
    args.append(f"--exclude-module={mod}")

# ============================================================================
# ЗАПУСК СБОРКИ
# ============================================================================
print("=" * 60)
print("Сборка NexTT 2.0 с экспериментальной фичей")
print("=" * 60)
print(f"Главный скрипт: {main_script}")
print(f"Ресурсы: {resources_dir}")
print(f"Файлов данных: {len(datas)}")
print("=" * 60)

pyinstaller_run(args)

print("\n" + "=" * 60)
print("Готово! EXE-файл в папке dist/")
print("=" * 60)