"""Юнит-тесты вспомогательных модулей Streamlit-интерфейса."""

from datetime import datetime, timedelta, timezone

from src.models.entities import (
    Assignment,
    Engineer,
    JobRecord,
    Plan,
    Route,
    RouteStop,
    TravelMatrixEntry,
)
from src.models.enums import Skill, TransportType
from src.optimizer.route_planner import RoutePlanner
from src.optimizer.travel import TravelMatrix
from src.services.planning import PlanningResult
from src.ui.explain import explain_assignment, format_planned_time
from src.ui.map_view import build_route_deck
from src.ui.tables import (
    assignments_dataframe,
    errors_dataframe,
    stops_dataframe,
    unassigned_dataframe,
)

MOSCOW = timezone(timedelta(hours=3))

MATRIX_ENTRIES = [
    TravelMatrixEntry(
        origin_location_id=origin,
        destination_location_id=destination,
        transport_type=TransportType.CAR,
        travel_min=10,
        distance_km=5.0,
        matrix_version="test-v1",
    )
    for origin in ("DEPOT", "LOC-A")
    for destination in ("DEPOT", "LOC-A")
    if origin != destination
]


def _job(job_id: str = "1001") -> JobRecord:
    return JobRecord(
        id=job_id,
        source_bk_type="Тест",
        work_type="CONNECTION",
        service_zone="Восток",
        address="г. Москва, ул Тестовая, д 1",
        service_duration_min=90,
        source_filename="Восток Синтетические данные.csv",
        window_start=datetime(2026, 9, 20, 10, 0, tzinfo=MOSCOW),
        window_end=datetime(2026, 9, 20, 16, 0, tzinfo=MOSCOW),
        location_id="LOC-A",
        priority="HIGH",
    )


def _engineer() -> Engineer:
    return Engineer(
        id="ENG-1",
        name="Иван Петров",
        transport_type=TransportType.CAR,
        qualifications=[Skill.ELECTRIC],
        start_location_id="DEPOT",
        shift_start=datetime(2026, 9, 20, 9, 0, tzinfo=MOSCOW),
        shift_end=datetime(2026, 9, 20, 18, 0, tzinfo=MOSCOW),
        service_districts=["Восток"],
        allowed_work_types=["CONNECTION", "LOCAL_WORK", "ADD_ORDER"],
    )


def _result() -> tuple[PlanningResult, list[JobRecord], list[Engineer]]:
    jobs = [_job()]
    engineers = [_engineer()]
    plan = RoutePlanner(TravelMatrix(MATRIX_ENTRIES)).build_plan(
        jobs,
        engineers,
    )

    return PlanningResult(
        bundle=None,  # type: ignore[arg-type]
        plan=plan,
        baseline_plan=None,
    ), jobs, engineers


def test_assignments_dataframe_contains_expected_columns():
    result, jobs, engineers = _result()

    df = assignments_dataframe(
        result,
        {job.id: job for job in jobs},
        {engineer.id: engineer for engineer in engineers},
    )

    assert not df.empty
    assert {"Заявка", "Тип работы", "Бригада", "Адрес", "Начало"} <= set(df.columns)
    assert df.iloc[0]["Заявка"] == "1001"


def test_unassigned_dataframe_is_empty_when_all_assigned():
    result, jobs, _ = _result()

    df = unassigned_dataframe(result, {job.id: job for job in jobs})

    assert df.empty


def test_unassigned_dataframe_lists_reason_when_not_assigned():
    job = _job("2001")
    job.work_type = "EMERGENCY"
    engineer = _engineer()
    engineer.allowed_work_types = ["CONNECTION"]

    plan = RoutePlanner(TravelMatrix(MATRIX_ENTRIES)).build_plan(
        [job],
        [engineer],
    )
    result = PlanningResult(bundle=None, plan=plan)  # type: ignore[arg-type]

    df = unassigned_dataframe(result, {job.id: job})

    assert not df.empty
    assert df.iloc[0]["Заявка"] == "2001"
    assert df.iloc[0]["reason_code"] == "NO_QUALIFIED_ENGINEER"


def test_stops_dataframe_has_travel_from_previous_point():
    result, jobs, engineers = _result()
    engineer = engineers[0]

    df = stops_dataframe(
        engineer,
        result,
        {job.id: job for job in jobs},
        TravelMatrix(MATRIX_ENTRIES),
    )

    assert not df.empty
    assert "Путь от предыдущей, мин" in df.columns
    assert df.iloc[0]["Заявка"] == "1001"


def test_explain_assignment_builds_real_checks():
    job = _job()
    engineer = _engineer()
    travel = TravelMatrix(MATRIX_ENTRIES)

    stop = RouteStop(
        job_id=job.id,
        location_id=job.location_id,
        planned_arrival=datetime(2026, 9, 20, 9, 10, tzinfo=MOSCOW),
        planned_start=datetime(2026, 9, 20, 10, 0, tzinfo=MOSCOW),
        planned_end=datetime(2026, 9, 20, 11, 30, tzinfo=MOSCOW),
        address=job.address,
    )

    lines = explain_assignment(job, engineer, travel, stop=stop)

    texts = [line["text"] for line in lines]

    assert any("Зона «Восток» входит" in text for text in texts)
    assert any("Тип работы «CONNECTION» разрешён" in text for text in texts)
    assert any("окно" in text for text in texts)
    assert any("Критерий выбора" in text for text in texts)


def test_explain_detects_window_violation():
    job = _job()
    job.window_end = datetime(2026, 9, 20, 10, 30, tzinfo=MOSCOW)
    engineer = _engineer()
    travel = TravelMatrix(MATRIX_ENTRIES)

    stop = RouteStop(
        job_id=job.id,
        location_id=job.location_id,
        planned_arrival=datetime(2026, 9, 20, 9, 10, tzinfo=MOSCOW),
        planned_start=datetime(2026, 9, 20, 10, 0, tzinfo=MOSCOW),
        planned_end=datetime(2026, 9, 20, 11, 30, tzinfo=MOSCOW),
    )

    lines = explain_assignment(job, engineer, travel, stop=stop)

    assert any(line["status"] == "bad" for line in lines)


def test_format_planned_time_handles_none():
    assert format_planned_time(None) == "—"
    assert format_planned_time(datetime(2026, 9, 20, 9, 5, tzinfo=MOSCOW)) == (
        "20.09.2026 09:05"
    )


def test_build_route_deck_with_coordinates():
    locations = [
        {"location_id": "DEPOT", "address": "Офис", "latitude": 55.75, "longitude": 37.61},
        {"location_id": "LOC-A", "address": "Объект", "latitude": 55.76, "longitude": 37.62},
    ]

    points = [
        {"location_id": "DEPOT", "label": "Офис", "is_start": True},
        {"location_id": "LOC-A", "label": "1001", "is_start": False},
    ]

    deck = build_route_deck(locations, points)

    assert deck is not None
    assert deck.layers  # есть слои PathLayer/ScatterplotLayer


def test_build_route_deck_returns_none_without_coordinates():
    locations = [
        {"location_id": "DEPOT", "address": "Офис", "latitude": None, "longitude": None}
    ]

    deck = build_route_deck(locations, [{"location_id": "DEPOT", "label": "x"}])

    assert deck is None


def test_errors_dataframe_from_bundle(tmp_path):
    from src.services.import_pipeline import load_input_directory

    (tmp_path / "Восток Синтетические данные.csv").write_text(
        "ID;Адрес;Тип заявки BK\n1001;Адрес;Неизвестный тип\n",
        encoding="cp1251",
    )
    (tmp_path / "engineers.json").write_text(
        '[{"id": "ENG-1", "name": "И", "transport_type": "CAR", '
        '"qualifications": ["ELECTRIC"], "start_location": "DEPOT", '
        '"shift_start": "2026-09-20T09:00:00+03:00", '
        '"shift_end": "2026-09-20T18:00:00+03:00", '
        '"service_districts": ["Восток"], '
        '"allowed_work_types": ["CONNECTION"]}]',
        encoding="utf-8",
    )
    (tmp_path / "equipment.json").write_text("[]", encoding="utf-8")
    (tmp_path / "travel_matrix.json").write_text("[]", encoding="utf-8")

    bundle = load_input_directory(tmp_path)

    df = errors_dataframe(bundle)

    assert not df.empty
    assert {"Файл", "Строка", "Поле", "Сообщение"} <= set(df.columns)