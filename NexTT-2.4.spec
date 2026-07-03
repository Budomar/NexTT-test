# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['c:\\Projects\\01.07.26 NexТТ 2.3 pro\\nextt\\main.py'],
    pathex=[],
    binaries=[],
    datas=[('c:\\Projects\\01.07.26 NexТТ 2.3 pro\\resources\\.gitignore', '.'), ('c:\\Projects\\01.07.26 NexТТ 2.3 pro\\resources\\1.png', '.'), ('c:\\Projects\\01.07.26 NexТТ 2.3 pro\\resources\\2.png', '.'), ('c:\\Projects\\01.07.26 NexТТ 2.3 pro\\resources\\3.png', '.'), ('c:\\Projects\\01.07.26 NexТТ 2.3 pro\\resources\\ARCHITECTURE.md', '.'), ('c:\\Projects\\01.07.26 NexТТ 2.3 pro\\resources\\icon.ico', '.'), ('c:\\Projects\\01.07.26 NexТТ 2.3 pro\\resources\\Lagar.png', '.'), ('c:\\Projects\\01.07.26 NexТТ 2.3 pro\\resources\\NexTT — Руководство пользователя.html', '.'), ('c:\\Projects\\01.07.26 NexТТ 2.3 pro\\resources\\patterns.json', '.'), ('c:\\Projects\\01.07.26 NexТТ 2.3 pro\\resources\\PBO3.png', '.'), ('c:\\Projects\\01.07.26 NexТТ 2.3 pro\\resources\\README.md', '.'), ('c:\\Projects\\01.07.26 NexТТ 2.3 pro\\resources\\~$Все_категории.xlsx', '.'), ('c:\\Projects\\01.07.26 NexТТ 2.3 pro\\resources\\Все_категории.xlsx', '.'), ('c:\\Projects\\01.07.26 NexТТ 2.3 pro\\resources\\Инструкция.pdf', '.'), ('c:\\Projects\\01.07.26 NexТТ 2.3 pro\\resources\\Инструкция.pptx', '.'), ('c:\\Projects\\01.07.26 NexТТ 2.3 pro\\resources\\Мономатрица.xlsx', '.'), ('c:\\Projects\\01.07.26 NexТТ 2.3 pro\\resources\\Прайс-лист.xlsx', '.'), ('c:\\Projects\\01.07.26 NexТТ 2.3 pro\\resources\\Программа пересчета мощностей радиаторов LaggarTT.xlsx', '.'), ('c:\\Projects\\01.07.26 NexТТ 2.3 pro\\resources\\Формуляр для регистрации проектов.xlsm', '.'), ('c:\\Projects\\01.07.26 NexТТ 2.3 pro\\templates.json', '.'), ('c:\\Projects\\01.07.26 NexТТ 2.3 pro\\nextt\\experimental\\equipment_dialog.py', 'nextt\\experimental'), ('c:\\Projects\\01.07.26 NexТТ 2.3 pro\\nextt\\experimental\\equipment_normalizer.py', 'nextt\\experimental'), ('c:\\Projects\\01.07.26 NexТТ 2.3 pro\\nextt\\experimental\\equipment_searcher.py', 'nextt\\experimental'), ('c:\\Projects\\01.07.26 NexТТ 2.3 pro\\nextt\\experimental\\paste_dialog.py', 'nextt\\experimental'), ('c:\\Projects\\01.07.26 NexТТ 2.3 pro\\nextt\\experimental\\paste_handler.py', 'nextt\\experimental'), ('c:\\Projects\\01.07.26 NexТТ 2.3 pro\\nextt\\experimental\\product_normalizer.py', 'nextt\\experimental'), ('c:\\Projects\\01.07.26 NexТТ 2.3 pro\\nextt\\experimental\\universal_parser.py', 'nextt\\experimental'), ('c:\\Projects\\01.07.26 NexТТ 2.3 pro\\nextt\\experimental\\__init__.py', 'nextt\\experimental')],
    hiddenimports=['pandas', 'openpyxl', 'tkinter', 'tkinter.ttk', 'pyperclip', 'numpy', 'xlrd', 'chardet', 'fitz', 'pymupdf', 'pdfplumber', 'PIL', 'PIL.Image', 'PIL.ImageTk', 'nextt', 'nextt.app', 'nextt.config', 'nextt.logger', 'nextt.events', 'nextt.core.data_provider', 'nextt.core.brackets', 'nextt.core.normalizer', 'nextt.patterns.template_manager', 'nextt.parsing.excel_parser', 'nextt.parsing.pdf_parser', 'nextt.parsing.column_selector', 'nextt.parsing.word_parser', 'nextt.utils.dpi', 'nextt.utils.window_manager', 'nextt.utils.font_manager', 'nextt.utils.update_checker', 'nextt.ui.main_window', 'nextt.ui.dialogs.correspondence', 'nextt.ui.dialogs.meteor_selector', 'nextt.ui.dialogs.preview', 'nextt.ui.dialogs.page_selector', 'nextt.export.excel_writer', 'nextt.export.spec_generator', 'nextt.experimental', 'nextt.experimental.paste_handler', 'nextt.experimental.paste_dialog', 'nextt.experimental.equipment_searcher', 'nextt.experimental.equipment_dialog', 'nextt.experimental.equipment_normalizer', 'nextt.experimental.product_normalizer', 'nextt.experimental.universal_parser'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['matplotlib', 'scipy', 'pytest', 'PyQt5', 'PySide2', 'wx'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='NexTT-2.4',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['c:\\Projects\\01.07.26 NexТТ 2.3 pro\\resources\\icon.ico'],
)
