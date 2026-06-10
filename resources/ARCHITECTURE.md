nextt/
├── main.py # Точка входа
├── app.py # Координатор, EventBus
├── config.py # Настройки, пути к ресурсам
├── logger.py # Логирование
├── events.py # Шина событий
│
├── core/ # Бизнес-логика (нет UI)
│ ├── data_provider.py # Загрузка и фильтрация данных
│ ├── brackets.py # Расчёт кронштейнов
│ └── normalizer.py # Парсинг названий радиаторов (SpecNormalizer)
│
├── patterns/ # Обучение и поиск паттернов
│ ├── manager.py # PatternManager
│ └── storage.py # Чтение/запись patterns.json
│
├── parsing/ # Парсеры файлов
│ ├── excel_parser.py # Excel/CSV
│ ├── pdf_parser.py # PDF (pdfplumber)
│ └── column_selector.py # Диалог выбора столбцов
│
├── utils/ # Утилиты
│ ├── dpi.py # DPI-масштабирование
│ ├── async_bridge.py # Потокобезопасный мост
│ └── window_manager.py # Управление окнами
│
├── ui/ # Пользовательский интерфейс
│ ├── main_window.py # Главное окно с матрицей
│ ├── styles.py # Стили ttk
│ ├── matrix_view.py # Компонент матрицы (заготовка)
│ └── dialogs/
│ ├── correspondence.py # Таблица соответствия
│ ├── meteor_selector.py # Выбор аналога через матрицу
│ ├── preview.py # Предпросмотр спецификации
│ ├── page_selector.py # Выбор страниц PDF с миниатюрами
│ └── progress.py # Диалог прогресса
│
└── export/ # Экспорт данных
├── excel_writer.py # Запись в Excel (openpyxl)
└── spec_generator.py # Генерация спецификации

text

## Слои и зависимости
UI (main_window, dialogs)
↓
App (координатор, EventBus)
↓
Core (data_provider, brackets, normalizer) + Patterns + Parsing
↓
Utils (dpi, async_bridge, window_manager)

text

**Правило:** импорты только сверху вниз. UI не импортирует Parsing напрямую.

## Ключевые компоненты

### App (app.py)
Координатор приложения. Создаёт все компоненты, связывает их через EventBus.
Не содержит бизнес-логики.

### EventBus (events.py)
Легковесная шина событий. Компоненты подписываются на топики
и получают уведомления без прямых зависимостей.

### DataProvider (core/data_provider.py)
Единый источник данных. Загружает Мономатрицу.xlsx, предоставляет
методы фильтрации и поиска радиаторов.

### SpecNormalizer (core/normalizer.py)
Парсит названия радиаторов конкурентов и извлекает параметры:
подключение, тип, высоту, длину. Поддерживает форматы:
- Oasis Pro (PN/PB)
- Лидея (ЛК/ЛУ)
- Kermi (FTV/FKV/FKO)
- Универсальный (числовые паттерны)

### PatternManager (patterns/manager.py)
Хранит и сопоставляет паттерны названий. Обучается на ручных выборах
пользователя. Сохраняет паттерны в patterns.json.

### MainWindow (ui/main_window.py)
Главное окно с матрицей радиаторов, панелью подключения/типа,
кронштейнами и скидками.

## Поток данных при импорте спецификации

1. Пользователь выбирает файл (Excel/CSV/PDF)
2. ExcelParser/PDFParser читает файл → DataFrame
3. ColumnSelector — пользователь выбирает столбцы
4. SpecNormalizer + PatternManager — парсинг названий
5. DataProvider.find_analog() — поиск аналогов
6. CorrespondenceDialog — проверка и ручной подбор
7. Перенос в матрицу (entry_values)
8. SpecGenerator → ExcelWriter — экспорт спецификации

## Сборка

```bash
python build.py