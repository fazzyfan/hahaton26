# Hahaton26 — планирование выездных инженеров

MVP системы распределения заявок между бригадами (multi-crew VRPTW).

## Запуск

```bash
cd /c/hahaton26
venv\Scripts\activate
pytest -q
```

Текущий результат:

```text
120 passed, 2 skipped
```

(2 skipped — интеграционные тесты официального архива «Обезличивание.zip»,
выполняются после добавления трёх `*Синтетические данные.csv` в `data/input`.)

## Backend-сценарий через CLI

```bash
python -m src.cli plan --input-dir data/input --output data/output/plan.json
```

CLI выполняет полный путь: поиск официальных CSV → импорт → нормализация в
JobRecord → загрузка бригад/оборудования/матрицы → многобригадное
планирование → независимая проверка hard constraints → сохранение `plan.json`.

## Входные данные (`data/input`)

```text
data/input/
    <зона> Синтетические данные.csv   # официальные CSV (CP1251, ';')
    engineers.json                    # бригады
    equipment.json                    # справочник оборудования
    travel_matrix.json                # направленная матрица времени
    locations.json                    # реестр адрес -> location_id (опционально)
```

Только файлы с суффиксом `Синтетические данные.csv` учитываются;
`*Контрольное распределение*.csv` не используется.

Контрольные количества после импорта: Восток 66, Юго-восток 83, Югоцентр 56
(итого 205). Проверяется интеграционным тестом `tests/test_official_integration.py`.

## Структура

```text
data/input/                  # входные данные (CSV + JSON)
data/output/plan.json        # результат планирования

src/models/                  # Pydantic-модели и Enum
src/config/                  # data contract v1.2 и маппинг типов работ
src/importers/               # CSV-импортёр, JSON-загрузчики
src/matrix/                  # SQLite-слой матрицы
src/optimizer/               # travel lookup, многобригадный планировщик
src/services/                # import pipeline, планирование
src/validation/              # PlanValidator (hard constraints)
src/cli.py                   # CLI
scripts/gen_travel_matrix.py # генератор синтетической матрицы

tests/                       # автоматические тесты
```

## Что уже работает

* Импорт официального CSV: CP1251, `;`, даты DD.MM.YYYY HH:MM, Europe/Moscow,
  пропуск пустых строк и «Адрес офиса», структурированные ошибки импорта;
* Канонические `JobRecord` (включая сырое значение «Гигабитное подключение»);
* Отчёт импорта по файлам: строки, заявки, пропуски, ошибки;
* Многобригадный статический планировщик (greedy insertion) с hard
  constraints: район, тип работы, оборудование, travel matrix, окно, смена;
* Причины неназначения: NO_QUALIFIED_ENGINEER, NO_TRAVEL_DATA, NO_TIME_WINDOW,
  SHIFT_CONFLICT, OPTIMIZER_LIMIT;
* Независимый `PlanValidator` с кодами нарушений;
* `plan.json` c assignments / routes / unassigned (reason_code + message) / status.

## Что дальше

* Прогон на официальном архиве «Обезличивание.zip» (66/83/56);
* `received_at` / `priority` / `status` / `gigabit_connection` /
  `required_equipment` по фактическим колонкам CSV;
* Streamlit-интерфейс;
* динамическое перепланирование.
