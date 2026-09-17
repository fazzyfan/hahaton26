# Hahaton26 — планирование выездных инженеров

MVP системы распределения заявок между инженерами.

## Запуск

```bash
cd /c/hahaton26
source venv/Scripts/activate
pytest -q
```

Текущий результат:

```text
39 passed
```

## Структура

```text
data/demo.json              # тестовые заявки и инженеры

src/models/                 # модели и Enum
src/validation/             # проверка JSON
src/matrix/                 # SQLite и матрица поездок
src/optimizer/              # совместимость и OR-Tools

tests/                      # автоматические тесты

app.py                      # Streamlit-интерфейс пока нет
requirements.txt            # зависимости
```

## Где менять данные

Основной файл:

```text
data/demo.json
```

Здесь находятся:

```json
{
  "jobs": [],
  "engineers": []
}
```

### Добавить/изменить заявку

Менять секцию:

```text
jobs
```

Основные поля:

```text
id
title
location_id
required_skill
priority
window_start
window_end
service_duration_min
```

### Добавить/изменить инженера

Менять секцию:

```text
engineers
```

Основные поля:

```text
id
name
transport_type
qualifications
start_location_id
shift_start
shift_end
```

## Где писать тесты

Все тесты находятся в:

```text
tests/
```

После изменения кода или тестовых данных:

```bash
pytest -q
```

## Что уже работает

* Pydantic-модели
* Enum
* Проверка входного JSON
* SQLite-матрица поездок
* Время и расстояние поездок
* Проверка навыков инженеров
* Таблица совместимости
* Базовый OR-Tools оптимизатор
* 39 автоматических тестов

## Что делаем дальше

```text
Multi-vehicle OR-Tools
→ реальные ограничения
→ Plan
→ PlanValidator
→ PlanningService
→ Streamlit
→ карта
→ перепланирование
```
