# Совместная разработка MVP (координация)

Репозиторий: `https://github.com/fazzyfan/hahaton26.git`
Ветка по умолчанию: `main`

## Доступ к репозиторию

Чтобы добавить соавтора (например, фронтенд-разработчика):

1. Открыть GitHub → репозиторий `fazzyfan/hahaton26` → **Settings** →
   **Collaborators and teams** → **Add people**;
2. Добавить GitHub-логин/email участника;
3. Участник клонирует:

```bash
git clone https://github.com/fazzyfan/hahaton26.git
cd hahaton26
venv\Scripts\activate          # или создать новое окружение
python -m pip install -r requirements.txt
```

Альтернатива без коллаборатора — pull request через форк.

## Команды запуска

```bash
# тесты
pytest -q

# backend (CLI): план + baseline + сравнение
python -m src.cli plan --input-dir data/input --output data/output/plan.json

# интерфейс
python -m streamlit run app.py
```

## Как вызвать backend из интерфейса

Единая точка входа — [`src/services/planning.py`](../src/services/planning.py),
функция `run_planning(input_dir, skip_rows=None, with_baseline=True,
csv_suffix=..., zone_override=...)`:

* возвращает `PlanningResult` (bundle, plan, issues, baseline_plan, comparison);
* импорт, ограничения и расчёт — один код для CLI и Streamlit;
* повторный расчёт НЕ нужен при переключении вкладок/бригады — результат
  хранится в `st.session_state`.

Полезные модули для интерфейса:

* [`src/ui/tables.py`](../src/ui/tables.py) — pandas-таблицы
  (назначения, неназначенные, остановки, сравнение, ошибки);
* [`src/ui/map_view.py`](../src/ui/map_view.py) — карта маршрута (pydeck);
* [`src/ui/explain.py`](../src/ui/explain.py) — объяснение назначения заявки.

## Соглашение о файлах (чтобы не мешать друг другу)

### Владеет фронтенд-разработчик

```text
app.py                      # экраны Streamlit: Загрузка/Проверка/Результат/Маршрут
src/ui/                     # таблицы, карта, объяснения (только отображение)
screenshots/                # скриншоты интерфейса (не коммитить лишнее)
```

### Владеет backend-часть (изменять только по согласованию)

```text
src/models/  src/config/  src/importers/  src/optimizer/
src/services/  src/validation/  src/matrix/  src/cli.py
data/input/  data/output/  scripts/  tests/
```

Правила:

* интерфейс обращается к backend **только** через `run_planning`
  и функции из `src/ui/*` — не дублировать логику в `app.py`;
* не менять контракты `InputBundle` / `Plan` / `PlanningResult` без
  обсуждения — это общий API;
* новые поля в моделях добавлять с дефолтами (обратная совместимость);
* перед push: `pytest -q` (сейчас 172 passed).

## Регламент веток

* Работаем на `main` короткими коммитами; каждый коммит — целостный
  (тесты зелёные);
* крупные фичи — ветка `feature/<name>` + pull request;
* перед мержем — полный прогон тестов и ручная проверка сценария в UI.

## Текущее состояние (для ориентира)

* backend: исправлены окна (planned_end <= window_end), матрица без
  дубликатов, причины неназначения, транспорт CAR/WALK/BICYCLE/
  PUBLIC_TRANSPORT, география и baseline — см. README;
* интерфейс: все 4 экрана работают; полный пользовательский сценарий
  проверяется автоматически (`tests/test_app_flow.py`, AppTest);
* результаты: план VALID, Assigned 97, baseline 34.