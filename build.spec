# -*- mode: python ; coding: utf-8 -*-

import os

block_cipher = None

# =============================================================================
# 1. СПИСОК ФАЙЛОВ ДАННЫХ (по аналогии со старым spec)
# =============================================================================
data_files = [
    # Excel файлы данных
    ('resources/Мономатрица.xlsx', '.'),
    ('resources/Прайс-лист.xlsx', '.'),
    ('resources/Программа пересчета мощностей радиаторов LaggarTT.xlsx', '.'),
    ('resources/Формуляр для регистрации проектов.xlsm', '.'),
    
    # Изображения
    ('resources/icon.ico', '.'),
    ('resources/Lagar.png', '.'),
    ('resources/PBO3.png', '.'),
    ('resources/1.png', '.'),
    ('resources/2.png', '.'),
    ('resources/3.png', '.'),
    
    # PDF и документация
    ('resources/Инструкция.pdf', '.'),
    
    # Файлы данных
    ('resources/patterns.json', '.'),
    
    # Дополнительные файлы (если нужны)
    # ('resources/README.md', '.'),
    # ('resources/ARCHITECTURE.md', '.'),
]

# =============================================================================
# 2. ДОБАВЛЯЕМ ВСЕ .py ФАЙЛЫ ИЗ ПАПКИ nextt (если нужно)
# =============================================================================
# Это нужно, если PyInstaller не видит какие-то модули
additional_py_files = [
    # Основные модули (уже импортируются через hiddenimports, но на всякий случай)
]

for file in additional_py_files:
    if os.path.exists(file):
        data_files.append((file, '.'))

# =============================================================================
# 3. АНАЛИЗ
# =============================================================================
a = Analysis(
    ['nextt/main.py'],  # ТОЧКА ВХОДА (ваш главный файл)
    pathex=[os.getcwd()],
    binaries=[],
    datas=data_files,
    hiddenimports=[
        # Стандартные библиотеки
        'pandas',
        'openpyxl',
        'tkinter',
        'tkinter.ttk',
        'pyperclip',
        'numpy',
        'xlrd',
        'chardet',
        're',
        'datetime',
        'tempfile',
        'platform',
        'subprocess',
        'webbrowser',
        'traceback',
        'typing',
        'collections',
        'string',
        'sys',
        'os',
        'queue',
        'threading',
        'io',
        
        # Pillow (для работы с изображениями)
        'PIL',
        'PIL.Image',
        'PIL.ImageTk',
        
        # PyMuPDF (для работы с PDF)
        'fitz',
        'pymupdf',
        
        # pdfplumber (для парсинга PDF)
        'pdfplumber',
        
        # ========== МОДУЛИ ВАШЕГО ПРОЕКТА ==========
        # Основные модули
        'nextt',
        'nextt.app',
        'nextt.config',
        'nextt.logger',
        'nextt.events',
        
        # Ядро
        'nextt.core.data_provider',
        'nextt.core.brackets',
        'nextt.core.normalizer',
        
        # Паттерны
        'nextt.patterns.manager',
        'nextt.patterns.storage',
        
        # Парсинг
        'nextt.parsing.excel_parser',
        'nextt.parsing.pdf_parser',
        'nextt.parsing.column_selector',
        'nextt.parsing.word_parser',
        
        # Утилиты
        'nextt.utils.dpi',
        'nextt.utils.window_manager',
        'nextt.utils.font_manager',
        
        # UI
        'nextt.ui.main_window',
        'nextt.ui.dialogs.correspondence',
        'nextt.ui.dialogs.meteor_selector',
        'nextt.ui.dialogs.preview',
        'nextt.ui.dialogs.page_selector',
        
        # Экспорт
        'nextt.export.excel_writer',
        'nextt.export.spec_generator',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib',
        'scipy',
        'pytest',
        'PyQt5',
        'PySide2',
        'wx',
        'test',
        'unittest',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# =============================================================================
# 4. ДОПОЛНИТЕЛЬНЫЙ СБОР СКРЫТЫХ ИМПОРТОВ
# =============================================================================
# Это помогает PyInstaller найти все подмодули
for mod in ['tkinter', 'PIL', 'fitz', 'pymupdf', 'pdfplumber']:
    try:
        import importlib
        imported = importlib.import_module(mod)
        for attr in dir(imported):
            try:
                submodule_name = f"{mod}.{attr}"
                importlib.import_module(submodule_name)
                if submodule_name not in a.hiddenimports:
                    a.hiddenimports.append(submodule_name)
            except:
                pass
    except ImportError:
        pass

# =============================================================================
# 5. СБОРКА PYZ
# =============================================================================
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# =============================================================================
# 6. СБОРКА EXE
# =============================================================================
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='NexTT-1.83',           # Имя итогового EXE
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                     
    runtime_tmpdir=None,
    console=False,                # БЕЗ консольного окна
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='resources/icon.ico',    # Иконка для EXE
)