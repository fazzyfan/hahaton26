"""Streamlit-интерфейс «Планировщик инженеров».

Пользовательский сценарий диспетчера:

    Загрузка  ->  Проверка данных  ->  Результат  ->  Маршрут бригады

Интерфейс использует тот же backend, что и CLI (src.services.planning):
импорт, ограничения, расчёт и независимая валидация выполняются одним
кодом. Результат расчёта хранится в st.session_state и НЕ пересчитывается
при переключении вкладок или бригады.

Запуск:
    python -m streamlit run app.py
"""
from __future__ import annotations

import shutil
import tempfile
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

from src.models.entities import Engineer, JobRecord
from src.optimizer.travel import TravelMatrix
from src.services.import_pipeline import load_input_directory
from src.services.planning import PlanningResult, run_planning
from src.ui.explain import explain_assignment
from src.ui.map_view import build_route_deck
from src.ui.tables import (
    assignments_dataframe,
    comparison_by_engineer_dataframe,
    comparison_summary_dataframe,
    errors_dataframe,
    import_summary_dataframe,
    stops_dataframe,
    unassigned_dataframe,
)

DEMO_INPUT_DIR = Path("data/input")

# Допустимые зоны для пользовательской загрузки CSV.
ZONES = ["Восток", "Юго-восток", "Югоцентр"]

REFERENCE_FILES = [
    "engineers.json",
    "equipment.json",
    "locations.json",
    "travel_matrix.json",
]

YELLOW = "#F5C518"
YELLOW_DARK = "#E0AE00"

# Тёмная тема.
BG = "#0F1115"
PANEL = "#181B21"
BORDER = "#262B33"
TEXT = "#E8EAF0"
MUTED = "#9AA3B2"

PAGE_CSS = f"""
<style>
    .stApp {{
        background-color: {BG};
        color: {TEXT};
        font-family: "Segoe UI", -apple-system, "Helvetica Neue", Arial, sans-serif;
    }}

    h1, h2, h3 {{
        color: {TEXT};
        letter-spacing: -0.2px;
    }}

    /* Карточки метрик */
    .metric-card {{
        background-color: {PANEL};
        border: 1px solid {BORDER};
        border-radius: 12px;
        padding: 12px 16px;
        margin-bottom: 8px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.25);
        transition: transform 0.08s ease;
    }}
    .metric-card:hover {{ transform: translateY(-1px); }}
    .metric-icon {{ font-size: 20px; }}
    .metric-label {{
        font-size: 11px;
        color: {MUTED};
        text-transform: uppercase;
        letter-spacing: 0.5px;
        margin-top: 2px;
    }}
    .metric-value {{
        font-size: 24px;
        font-weight: 800;
        color: {TEXT};
        margin-top: 2px;
    }}
    .metric-accent {{
        border-top: 3px solid {YELLOW};
    }}

    /* Бейджи статусов */
    .badge {{
        display: inline-block;
        padding: 3px 10px;
        border-radius: 999px;
        font-size: 13px;
        font-weight: 600;
    }}
    .badge-ok {{ background: #123524; color: #4ade80; }}
    .badge-bad {{ background: #3b1216; color: #f87171; }}
    .badge-warn {{ background: #33270f; color: #fbbf24; }}

    /* Карточка файла */
    .file-card {{
        background: {PANEL};
        border: 1px solid {BORDER};
        border-radius: 10px;
        padding: 8px 12px;
        margin: 4px 0;
        font-size: 14px;
        color: {TEXT};
    }}

    /* Объяснение назначения */
    .explain-ok {{ color: #4ade80; }}
    .explain-bad {{ color: #f87171; }}
    .explain-info {{ color: {MUTED}; }}

    /* Primary-кнопки (жёлтые, контраст на тёмном) */
    .stButton > button[kind="primary"] {{
        background-color: {YELLOW};
        color: #141414;
        border: none;
        border-radius: 10px;
        font-weight: 700;
        padding: 0.55rem 1.1rem;
        box-shadow: 0 2px 10px rgba(245,197,24,0.25);
        transition: background-color 0.12s ease;
    }}
    .stButton > button[kind="primary"]:hover {{
        background-color: {YELLOW_DARK};
        color: #141414;
    }}

    /* Боковая панель */
    [data-testid="stSidebar"] {{
        background-color: {PANEL};
        border-right: 1px solid {BORDER};
    }}

    /* Таблицы */
    [data-testid="stDataFrame"] {{
        border-radius: 10px;
        overflow: hidden;
        border: 1px solid {BORDER};
    }}

    /* Вкладки */
    .stTabs [data-baseweb="tab-list"] {{
        gap: 6px;
    }}
    .stTabs [data-baseweb="tab"] {{
        border-radius: 8px 8px 0 0;
        padding: 8px 16px;
        font-weight: 600;
    }}

    /* Подписи и мелкий текст */
    .stCaption, [data-testid="stCaptionContainer"] p {{
        color: {MUTED};
    }}
</style>
"""


def init_state() -> None:
    defaults = {
        "stage": "load",
        "mode": "demo",
        "input_dir": None,
        "csv_suffix": "Синтетические данные.csv",
        "zone_overrides": {},
        "bundle": None,
        "planning": None,
        "skip_rows": set(),
        "selected_engineer": None,
        "plan_date": date.today(),
    }

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def set_stage(stage: str) -> None:
    st.session_state["stage"] = stage


def _current_bundle():
    return st.session_state["bundle"]


# --- Экран «Загрузка» --------------------------------------------------------

def _save_uploaded_files(
    csv_files,
    zone_by_name: dict[str, str],
    reference_option: str,
    reference_files,
) -> tuple[Path, dict[str, str], str]:
    """Сохраняет загруженные файлы во временную папку запуска.

    Имена CSV сохраняются исходными (для отчёта), зона передаётся через
    zone_override. Демонстрационный набор при этом не изменяется.
    """
    temp_dir = Path(tempfile.mkdtemp(prefix="hahaton_input_"))

    zone_overrides: dict[str, str] = {}

    for uploaded in csv_files:
        target = temp_dir / uploaded.name
        target.write_bytes(uploaded.getvalue())
        zone_overrides[uploaded.name] = zone_by_name.get(
            uploaded.name,
            "Восток",
        )

    if reference_option == "bundled":
        # Готовый комплект справочников из проекта.
        for name in REFERENCE_FILES:
            source = DEMO_INPUT_DIR / name
            if source.exists():
                shutil.copy(source, temp_dir / name)
    else:
        # Отдельно загруженные справочники.
        for uploaded in reference_files:
            if uploaded is not None:
                (temp_dir / uploaded.name).write_bytes(uploaded.getvalue())

    return temp_dir, zone_overrides, ".csv"


def _start_validation(bundle) -> None:
    st.session_state["bundle"] = bundle
    st.session_state["planning"] = None
    st.session_state["skip_rows"] = set()
    set_stage("validate")
    st.rerun()


def render_load() -> None:
    st.title("Планировщик выездных инженеров")
    st.caption("🗺️ MVP · распределение заявок между бригадами (multi-crew VRPTW)")

    selected_mode = st.sidebar.radio(
        "Режим данных",
        ["Демонстрационный набор", "Загрузить файлы"],
        index=0 if st.session_state["mode"] == "demo" else 1,
    )
    mode = "demo" if selected_mode == "Демонстрационный набор" else "upload"
    st.session_state["mode"] = mode

    st.session_state["plan_date"] = st.date_input(
        "Дата планирования",
        value=st.session_state["plan_date"],
    )

    if mode == "demo":
        csv_files = sorted(DEMO_INPUT_DIR.glob("*Синтетические данные.csv"))

        st.info(
            "Демонстрационный набор: официальные синтетические CSV "
            "Beeline Business (205 заявок) и готовые справочники."
        )

        st.markdown("**Файлы набора:**")

        for path in csv_files:
            st.markdown(
                f'<div class="file-card">📄 {path.name}</div>',
                unsafe_allow_html=True,
            )

        for name in REFERENCE_FILES:
            st.markdown(
                f'<div class="file-card">📦 {name}</div>',
                unsafe_allow_html=True,
            )

        if st.button("Проверить данные", type="primary", use_container_width=True):
            bundle = load_input_directory(DEMO_INPUT_DIR)

            st.session_state["input_dir"] = str(DEMO_INPUT_DIR)
            st.session_state["csv_suffix"] = "Синтетические данные.csv"
            st.session_state["zone_overrides"] = {}
            _start_validation(bundle)

        return

    # --- Пользовательская загрузка ---
    st.markdown("### Файлы заявок (CSV)")

    csv_files = st.file_uploader(
        "Выберите один или несколько CSV-файлов заявок",
        type=["csv"],
        accept_multiple_files=True,
    )

    zone_by_name: dict[str, str] = {}

    if csv_files:
        st.markdown("**Зона обслуживания для каждого файла:**")

        for uploaded in csv_files:
            zone = st.selectbox(
                f"Зона для «{uploaded.name}»",
                ZONES,
                key=f"zone_{uploaded.name}",
            )
            zone_by_name[uploaded.name] = zone

    st.markdown("### Справочники")

    reference_option = st.radio(
        "Источник справочников",
        ["Использовать готовый комплект", "Загрузить отдельно"],
        horizontal=True,
    )

    reference_files: list = []

    if reference_option == "Загрузить отдельно":
        reference_files.append(
            st.file_uploader("engineers.json (бригады)", type=["json"])
        )
        reference_files.append(
            st.file_uploader("equipment.json (оборудование)", type=["json"])
        )
        reference_files.append(
            st.file_uploader(
                "locations.json (локации с координатами)",
                type=["json"],
            )
        )
        reference_files.append(
            st.file_uploader(
                "travel_matrix.json (матрица перемещений)",
                type=["json"],
            )
        )

    can_check = bool(csv_files)

    if not can_check:
        st.warning("Загрузите хотя бы один CSV-файл заявок.")

    if st.button(
        "Проверить данные",
        type="primary",
        use_container_width=True,
        disabled=not can_check,
    ):
        input_dir, zone_overrides, csv_suffix = _save_uploaded_files(
            csv_files,
            zone_by_name,
            (
                "bundled"
                if reference_option == "Использовать готовый комплект"
                else "custom"
            ),
            reference_files,
        )

        bundle = load_input_directory(
            input_dir,
            csv_suffix=csv_suffix,
            zone_override=zone_overrides,
        )

        st.session_state["input_dir"] = str(input_dir)
        st.session_state["csv_suffix"] = csv_suffix
        st.session_state["zone_overrides"] = zone_overrides
        _start_validation(bundle)


# --- Экран «Проверка данных» -------------------------------------------------

def _reimport(skip_rows: set[tuple[str, int]]) -> None:
    with st.spinner("Повторная проверка данных…"):
        bundle = load_input_directory(
            st.session_state["input_dir"],
            skip_rows=skip_rows,
            csv_suffix=st.session_state["csv_suffix"],
            zone_override=st.session_state["zone_overrides"],
        )

    st.session_state["bundle"] = bundle
    st.session_state["skip_rows"] = skip_rows
    st.session_state["planning"] = None


def render_validate() -> None:
    bundle = _current_bundle()

    if bundle is None:
        set_stage("load")
        st.rerun()

    st.title("📋 Проверка данных")

    total_rows = sum(report.rows_total for report in bundle.reports)
    total_empty = sum(report.skipped_empty for report in bundle.reports)
    total_office = sum(report.skipped_office for report in bundle.reports)
    error_count = len(bundle.errors)
    fatal_count = sum(1 for error in bundle.errors if not error.can_skip)

    col1, col2, col3, col4 = st.columns(4)

    metric_cards = [
        ("📄", "Строк-заявок", total_rows),
        ("✅", "Принято заявок", len(bundle.jobs)),
        ("⏭️", "Пропущено", f"{total_empty} пустых · {total_office} офисных"),
        ("⚠️", "Ошибок", error_count),
    ]

    for column, (icon, label, value) in zip(
        (col1, col2, col3, col4),
        metric_cards,
    ):
        with column:
            st.markdown(
                '<div class="metric-card metric-accent">'
                f'<div class="metric-icon">{icon}</div>'
                f'<div class="metric-label">{label}</div>'
                f'<div class="metric-value">{value}</div></div>',
                unsafe_allow_html=True,
            )

    st.subheader("Сводка по файлам")
    st.dataframe(
        import_summary_dataframe(bundle),
        use_container_width=True,
        hide_index=True,
    )

    if bundle.office_locations:
        offices_text = ", ".join(
            office.address for office in bundle.office_locations[:5]
        )
        if len(bundle.office_locations) > 5:
            offices_text += "…"

        st.caption(f"Исключённые записи (строки «Адрес Офиса»): {offices_text}")

    if error_count:
        st.subheader("Ошибки импорта")
        st.dataframe(
            errors_dataframe(bundle),
            use_container_width=True,
            hide_index=True,
        )

    fatal = [error for error in bundle.errors if not error.can_skip]
    skippable = [error for error in bundle.errors if error.can_skip]

    if fatal:
        st.error(
            f"Обнаружены фатальные ошибки ({fatal_count}) — расчёт "
            "заблокирован до их исправления."
        )

        col_a, col_b = st.columns(2)

        with col_a:
            if st.button(
                "Исправить и загрузить повторно",
                use_container_width=True,
            ):
                set_stage("load")
                st.rerun()

        with col_b:
            if st.button("Отменить загрузку", use_container_width=True):
                st.session_state["bundle"] = None
                st.session_state["planning"] = None
                set_stage("load")
                st.rerun()

        return

    if skippable:
        st.warning(
            f"Найдено {len(skippable)} исправимых ошибок. Можно пропустить "
            "выбранные записи или вернуться к загрузке."
        )

        options = {
            f"{error.file}#{error.row}": (error.file, error.row)
            for error in skippable
        }

        selected = st.multiselect(
            "Выберите ошибочные записи для пропуска",
            list(options),
        )

        col_a, col_b, col_c = st.columns(3)

        with col_a:
            if st.button(
                "Пропустить выбранные ошибочные записи",
                use_container_width=True,
                disabled=not selected,
            ):
                skip_set = {options[item] for item in selected}
                _reimport(skip_set)
                st.rerun()

        with col_b:
            if st.button(
                "Исправить и загрузить повторно",
                use_container_width=True,
            ):
                set_stage("load")
                st.rerun()

        with col_c:
            if st.button("Отменить загрузку", use_container_width=True):
                st.session_state["bundle"] = None
                st.session_state["planning"] = None
                set_stage("load")
                st.rerun()

        st.divider()

    if not bundle.jobs:
        st.warning("Не осталось принятых заявок — построить план невозможно.")

        if st.button("Вернуться к загрузке"):
            set_stage("load")
            st.rerun()

        return

    st.success(
        f"Данные проверены: {len(bundle.jobs)} заявок готово к планированию."
    )

    if st.button(
        "Построить план",
        type="primary",
        use_container_width=True,
    ):
        with st.spinner("Строим план, считаем baseline и сравниваем…"):
            result = run_planning(
                st.session_state["input_dir"],
                skip_rows=st.session_state["skip_rows"],
                csv_suffix=st.session_state["csv_suffix"],
                zone_override=st.session_state["zone_overrides"],
            )

        st.session_state["planning"] = result
        set_stage("result")
        st.rerun()


# --- Экран «Результат» -------------------------------------------------------

def render_result() -> None:
    result: PlanningResult | None = st.session_state["planning"]

    if result is None or result.plan is None:
        st.info("План ещё не построен.")

        if st.button("К загрузке данных"):
            set_stage("load")
            st.rerun()

        return

    plan = result.plan
    bundle = result.bundle

    st.title("📊 Результат планирования")

    used_engineers = {assignment.engineer_id for assignment in plan.assignments}
    total_travel_min = sum(route.total_travel_min for route in plan.routes)
    total_distance_km = round(
        sum(route.total_distance_km for route in plan.routes),
        2,
    )

    metric_cards = [
        ("📥", "Принято заявок", len(bundle.jobs)),
        ("✅", "Назначено", len(plan.assignments)),
        ("⛔", "Не назначено", len(plan.unassigned)),
        ("👥", "Бригад задействовано", len(used_engineers)),
        ("⏱️", "Время в пути, мин", total_travel_min),
        ("📏", "Расстояние, км", total_distance_km),
    ]

    columns = st.columns(6)

    for column, (icon, label, value) in zip(columns, metric_cards):
        with column:
            st.markdown(
                '<div class="metric-card metric-accent">'
                f'<div class="metric-icon">{icon}</div>'
                f'<div class="metric-label">{label}</div>'
                f'<div class="metric-value">{value}</div></div>',
                unsafe_allow_html=True,
            )

    if result.issues:
        st.error(
            f"План содержит {len(result.issues)} нарушений независимой "
            "проверки и НЕ считается успешно рассчитанным."
        )

        issues_df = pd.DataFrame(
            [
                {
                    "Код": issue.code,
                    "Сущность": issue.entity_type,
                    "ID": issue.entity_id or "—",
                    "Сообщение": issue.message,
                }
                for issue in result.issues
            ]
        )
        st.dataframe(issues_df, use_container_width=True, hide_index=True)
    else:
        st.markdown(
            '<span class="badge badge-ok">✅ Независимая проверка пройдена '
            "— нарушений обязательных ограничений нет</span>",
            unsafe_allow_html=True,
        )

    jobs_by_id: dict[str, JobRecord] = {job.id: job for job in bundle.jobs}
    engineers_by_id: dict[str, Engineer] = {
        engineer.id: engineer for engineer in bundle.engineers
    }

    tab_assignments, tab_unassigned, tab_comparison = st.tabs(
        ["Назначения", "Неназначенные", "Сравнение с baseline"]
    )

    with tab_assignments:
        assignments_df = assignments_dataframe(
            result,
            jobs_by_id,
            engineers_by_id,
        )

        st.dataframe(assignments_df, use_container_width=True, hide_index=True)

        st.download_button(
            "Скачать назначения (CSV)",
            data=assignments_df.to_csv(index=False).encode("utf-8-sig"),
            file_name="assignments.csv",
            mime="text/csv",
        )

    with tab_unassigned:
        unassigned_df = unassigned_dataframe(result, jobs_by_id)

        if unassigned_df.empty:
            st.success("Неназначенных заявок нет.")
        else:
            st.dataframe(unassigned_df, use_container_width=True, hide_index=True)
            st.caption(
                "reason_code — технический код причины; колонка «Причина» — "
                "понятное описание."
            )

    with tab_comparison:
        if result.comparison is None:
            st.info("Baseline не рассчитан.")
        else:
            st.subheader("Сводные метрики")
            st.dataframe(
                comparison_summary_dataframe(result.comparison),
                use_container_width=True,
                hide_index=True,
            )

            st.subheader("Назначения по приоритетам")

            priority_df = pd.DataFrame(result.comparison.by_priority)
            priority_df.columns = ["Приоритет", "Основной план", "Baseline"]
            st.dataframe(priority_df, use_container_width=True, hide_index=True)

            st.subheader("Расстояние и время по бригадам")
            st.dataframe(
                comparison_by_engineer_dataframe(
                    result.comparison,
                    engineers_by_id,
                ),
                use_container_width=True,
                hide_index=True,
            )

            st.caption(
                "Baseline: заявки в фиксированном порядке, первая подходящая "
                "бригада, добавление в конец маршрута; те же ограничения, "
                "что и в основном алгоритме."
            )

    st.divider()

    st.download_button(
        "Скачать план (JSON)",
        data=plan.model_dump_json(indent=2),
        file_name="plan.json",
        mime="application/json",
    )

    st.subheader("Маршрут бригады")

    engineer_options = {
        engineer.id: f"{engineer.id} — {engineer.name}"
        for engineer in bundle.engineers
    }

    selected = st.selectbox(
        "Выберите бригаду",
        list(engineer_options),
        format_func=lambda key: engineer_options[key],
    )

    if st.button("Показать маршрут", type="primary"):
        st.session_state["selected_engineer"] = selected
        set_stage("route")
        st.rerun()


# --- Экран «Маршрут бригады» -------------------------------------------------

def render_route() -> None:
    result: PlanningResult | None = st.session_state["planning"]

    if result is None or result.plan is None:
        set_stage("result")
        st.rerun()

    bundle = result.bundle
    engineers_by_id = {engineer.id: engineer for engineer in bundle.engineers}
    jobs_by_id = {job.id: job for job in bundle.jobs}

    st.title("🚚 Маршрут бригады")

    if st.button("← Назад к результату"):
        set_stage("result")
        st.rerun()

    engineer_options = {
        engineer.id: f"{engineer.id} — {engineer.name}"
        for engineer in bundle.engineers
    }

    default_engineer = st.session_state.get("selected_engineer")

    index = (
        list(engineer_options).index(default_engineer)
        if default_engineer in engineer_options
        else 0
    )

    selected = st.selectbox(
        "Бригада",
        list(engineer_options),
        index=index,
        format_func=lambda key: engineer_options[key],
    )

    st.session_state["selected_engineer"] = selected

    engineer = engineers_by_id[selected]

    route = next(
        (
            item
            for item in result.plan.routes
            if item.engineer_id == engineer.id
        ),
        None,
    )

    start_address = next(
        (
            item["address"]
            for item in bundle.locations
            if item.get("location_id") == engineer.start_location_id
        ),
        engineer.start_location_id,
    )

    st.markdown(
        f"**Стартовая точка:** `{engineer.start_location_id}` — "
        f"{start_address}"
    )
    st.caption(
        f"Транспорт: {engineer.transport_type.value} · "
        f"Смена: {engineer.shift_start.strftime('%H:%M')}–"
        f"{engineer.shift_end.strftime('%H:%M')}"
    )

    if route is None or not route.stops:
        st.info("У этой бригады нет назначенных остановок.")
        return

    travel = TravelMatrix(bundle.travel_matrix)

    # --- Карта ---
    route_points = [
        {
            "location_id": engineer.start_location_id,
            "label": f"Офис ({engineer.start_location_id})",
            "is_start": True,
        }
    ]

    for stop in route.stops:
        route_points.append(
            {
                "location_id": stop.location_id,
                "label": stop.job_id,
                "is_start": False,
            }
        )

    deck = build_route_deck(bundle.locations, route_points)

    if deck is not None:
        st.pydeck_chart(deck)
        st.caption("Схематический маршрут: линия соединяет точки напрямую.")
    else:
        st.warning(
            "Для маршрута нет координат (проверьте locations.json) — "
            "карта недоступна."
        )

    # --- Таблица остановок ---
    st.subheader("Последовательность остановок")
    st.dataframe(
        stops_dataframe(engineer, result, jobs_by_id, travel),
        use_container_width=True,
        hide_index=True,
    )

    # --- Объяснение назначения ---
    st.subheader("Объяснение назначения")

    stop_options = {
        stop.job_id: f"{stop.job_id} · {stop.address or ''}"
        for stop in route.stops
    }

    selected_job = st.selectbox(
        "Заявка",
        list(stop_options),
        format_func=lambda key: stop_options[key],
    )

    stop = next(
        (item for item in route.stops if item.job_id == selected_job),
        None,
    )
    job = jobs_by_id.get(selected_job)

    if job is not None and stop is not None:
        explanation = explain_assignment(
            job,
            engineer,
            travel,
            stop=stop,
            route_load=route.stops.index(stop),
        )

        for line in explanation:
            marker = {"ok": "✅", "bad": "⛔", "info": "ℹ️"}.get(
                line["status"],
                "•",
            )
            css_class = f"explain-{line['status']}"

            st.markdown(
                f'<div class="{css_class}">{marker} {line["text"]}</div>',
                unsafe_allow_html=True,
            )


# --- Точка входа -------------------------------------------------------------

def main() -> None:
    st.set_page_config(
        page_title="Планировщик инженеров",
        page_icon="🗺️",
        layout="wide",
    )
    st.markdown(PAGE_CSS, unsafe_allow_html=True)

    init_state()

    stage = st.session_state["stage"]

    if stage == "load":
        render_load()
    elif stage == "validate":
        render_validate()
    elif stage == "result":
        render_result()
    elif stage == "route":
        render_route()
    else:
        set_stage("load")
        st.rerun()


if __name__ == "__main__":
    main()