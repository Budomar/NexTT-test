# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['c:\\Projects\\NexТТ 2.3 про\\nextt\\main.py'],
    pathex=[],
    binaries=[],
    datas=[('c:\\Projects\\NexТТ 2.3 про\\resources\\.gitignore', '.'), ('c:\\Projects\\NexТТ 2.3 про\\resources\\1.png', '.'), ('c:\\Projects\\NexТТ 2.3 про\\resources\\2.png', '.'), ('c:\\Projects\\NexТТ 2.3 про\\resources\\3.png', '.'), ('c:\\Projects\\NexТТ 2.3 про\\resources\\ARCHITECTURE.md', '.'), ('c:\\Projects\\NexТТ 2.3 про\\resources\\icon.ico', '.'), ('c:\\Projects\\NexТТ 2.3 про\\resources\\Lagar.png', '.'), ('c:\\Projects\\NexТТ 2.3 про\\resources\\NexTT — Руководство пользователя.html', '.'), ('c:\\Projects\\NexТТ 2.3 про\\resources\\patterns.json', '.'), ('c:\\Projects\\NexТТ 2.3 про\\resources\\PBO3.png', '.'), ('c:\\Projects\\NexТТ 2.3 про\\resources\\README.md', '.'), ('c:\\Projects\\NexТТ 2.3 про\\resources\\~$Все_категории.xlsx', '.'), ('c:\\Projects\\NexТТ 2.3 про\\resources\\Все_категории.xlsx', '.'), ('c:\\Projects\\NexТТ 2.3 про\\resources\\Инструкция.pdf', '.'), ('c:\\Projects\\NexТТ 2.3 про\\resources\\Инструкция.pptx', '.'), ('c:\\Projects\\NexТТ 2.3 про\\resources\\Мономатрица.xlsx', '.'), ('c:\\Projects\\NexТТ 2.3 про\\resources\\Прайс-лист.xlsx', '.'), ('c:\\Projects\\NexТТ 2.3 про\\resources\\Программа пересчета мощностей радиаторов LaggarTT.xlsx', '.'), ('c:\\Projects\\NexТТ 2.3 про\\resources\\Формуляр для регистрации проектов.xlsm', '.'), ('c:\\Projects\\NexТТ 2.3 про\\templates.json', '.'), ('c:\\Projects\\NexТТ 2.3 про\\nextt\\experimental\\equipment_dialog.py', 'nextt\\experimental'), ('c:\\Projects\\NexТТ 2.3 про\\nextt\\experimental\\equipment_normalizer.py', 'nextt\\experimental'), ('c:\\Projects\\NexТТ 2.3 про\\nextt\\experimental\\equipment_searcher.py', 'nextt\\experimental'), ('c:\\Projects\\NexТТ 2.3 про\\nextt\\experimental\\paste_dialog.py', 'nextt\\experimental'), ('c:\\Projects\\NexТТ 2.3 про\\nextt\\experimental\\paste_handler.py', 'nextt\\experimental'), ('c:\\Projects\\NexТТ 2.3 про\\nextt\\experimental\\product_normalizer.py', 'nextt\\experimental'), ('c:\\Projects\\NexТТ 2.3 про\\nextt\\experimental\\universal_parser.py', 'nextt\\experimental'), ('c:\\Projects\\NexТТ 2.3 про\\nextt\\experimental\\__init__.py', 'nextt\\experimental')],
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
    name='NexTT-2.3',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['c:\\Projects\\NexТТ 2.3 про\\resources\\icon.ico'],
)
