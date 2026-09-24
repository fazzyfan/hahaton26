# Hahaton26 — планирование выездных инженеров

MVP системы распределения заявок между бригадами (multi-crew VRPTW)
на официальных синтетических данных Beeline Business.

## Запуск

```bash
cd /c/hahaton26
venv\Scripts\activate
pytest -q
```

Текущий результат:

```text
140 passed, 0 skipped
```

(интеграционные тесты официального набора выполняются всегда —
файлы `*Синтетические данные.csv` лежат в `data/input`).

## Полный backend-сценарий через CLI

```bash
python -m src.cli plan --input-dir data/input --output data/output/plan.json
```

CLI: поиск официальных CSV → импорт → нормализация в `JobRecord` →
загрузка бригад/оборудования/матрицы → многобригадное планирование →
независимая проверка hard constraints → отчёт и сохранение `plan.json`.

Фатальная ошибка импорта (`can_skip=False`) останавливает планирование;
пустой план со статусом VALID не сохраняется.

## Входные данные (`data/input`)

```text
data/input/
    Восток Синтетические данные.csv       # 66 заявок
    Юго-восток Синтетические данные.csv   # 83 заявки
    Югоцентр Синтетические данные.csv     # 56 заявок
    engineers.json                        # 10 синтетических бригад
    equipment.json                        # справочник оборудования
    locations.json                        # реестр адрес -> location_id (198)
    travel_matrix.json                    # направленная матрица (234 036 записей)
```

Официальные колонки CSV: `Заявка;Тип заявки BK;Тип заявки HD;Начало;Окончание;
Район;Адрес;[Подключение;]Гигабитное подключение`. Кодировка CP1251,
разделитель `;`, время Europe/Moscow. Файлы `*Контрольное распределение*.csv`
не используются. Строки «Адрес Офиса» (адрес во второй ячейке) и пустые
строки не попадают в заявки.

Контрольный результат импорта: Восток 66, Юго-восток 83, Югоцентр 56,
итого 205, ошибок 0, офисов 3.

## Правила MVP (по уточнениям заказчика)

* Нормативы без заложенной дороги: CONNECTION 70, LOCAL_WORK 30,
  EMERGENCY 80, ADD_ORDER 20; занятость = фактическое время пути + норматив.
* `status = NEW`, `received_at = null`;
* `priority` из типа работы: EMERGENCY URGENT, CONNECTION HIGH,
  LOCAL_WORK/ADD_ORDER NORMAL;
* `gigabit_connection`: Да → true, Нет → false (в наборе ровно 2 гигабитные);
* `required_equipment` из конфигурации: INSTALLATION_KIT / DIAGNOSTIC_KIT /
  CUSTOMER_EQUIPMENT, + GIGABIT_TESTER при гигабите;
* бригады: `service_districts` = зона файла, `allowed_work_types` =
  квалификация, стартовая точка — офис зоны, смена 17.08.2026.

## Матрица перемещений

`travel_matrix.json` — **детерминированная синтетическая** матрица:
координаты точки вычисляются хешем адреса, время = расстояние по Манхэттену
поделить на среднюю скорость транспорта (CAR/TRUCK/MOTORCYCLE), A→B может
отличаться от B→A. Реальный маршрутизатор можно подключить позже, заменив
генератор [`scripts/gen_locations_matrix.py`](scripts/gen_locations_matrix.py).
Отсутствующая пара даёт `NO_TRAVEL_DATA`.

## Что работает

* Импорт официального CSV (CP1251, `;`, даты DD.MM.YYYY HH:MM), пропуск
  пустых строк и строк офиса, структурированные ошибки импорта;
* Канонические `JobRecord` со всеми производными полями;
* Отчёт импорта по файлам: строки, заявки, пропуски, ошибки;
* Многобригадный планировщик (greedy insertion) с hard constraints:
  район, тип работы, оборудование, travel matrix, окно, смена; приоритет
  EMERGENCY → CONNECTION → LOCAL_WORK/ADD_ORDER; балансировка загрузки;
* Причины неназначения: NO_QUALIFIED_ENGINEER, NO_TRAVEL_DATA,
  NO_TIME_WINDOW, SHIFT_CONFLICT, OPTIMIZER_LIMIT;
* Независимый `PlanValidator` (включая покрытие: каждая заявка ровно в
  assignments или unassigned, count = числу заявок);
* `plan.json` c assignments / routes (job_id, location_id, address,
  planned_arrival/start/end) / unassigned (reason_code + message) / status;
* Фатальная ошибка импорта блокирует публикацию плана.

Полный прогон (набор 17.08.2026): Imported 205, Assigned 73, Unassigned 132
(SHIFT_CONFLICT — ёмкость смен), Routes 10, Used engineers 10,
Validator issues 0, Plan status VALID.

## Структура

```text
data/input/                  # входные данные (CSV + JSON)
data/output/plan.json        # результат планирования

src/models/                  # Pydantic-модели и Enum
src/config/                  # data contract v1.2, нормативы, оборудование
src/importers/               # CSV-импортёр, JSON-загрузчики
src/matrix/                  # SQLite-слой матрицы
src/optimizer/               # travel lookup, многобригадный планировщик
src/services/                # import pipeline, планирование
src/validation/              # PlanValidator (hard constraints)
src/cli.py                   # CLI
scripts/                     # генераторы и инструменты анализа

tests/                       # автоматические тесты
```

## Что дальше

* Streamlit-интерфейс (загрузка CSV, ошибки, построение плана, таблицы,
  выбор бригады, экспорт);
* при необходимости — больше бригад/вечерних смен для увеличения доли
  назначенных заявок;
* динамическое перепланирование (после закрытия статического сценария).
