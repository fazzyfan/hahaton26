"""Тесты исправлений корректности MVP (окна, матрица, причины, валидация)."""

from datetime import datetime, timedelta, timezone

import pytest

from src.importers.json_inputs import load_locations_registry, load_travel_matrix_file
from src.models.entities import (
    Assignment,
    Engineer,
    JobRecord,
    Plan,
    Route,
    RouteStop,
    TravelMatrixEntry,
)
from src.models.enums import Skill, TransportType, UnassignmentReason
from src.optimizer.baseline import BaselinePlanner
from src.optimizer.route_planner import (
    WORK_TYPE_PRIORITY,
    RoutePlanner,
)
from src.optimizer.travel import TravelMatrix
from src.services.comparison import compare_plans
from src.services.import_pipeline import load_input_directory
from src.validation.input_validator import InputValidator
from src.validation.plan_validator import PlanValidator

MOSCOW = timezone(timedelta(hours=3))

LOCATIONS = ["DEPOT", "LOC-A", "LOC-B"]

MATRIX_ENTRIES = [
    TravelMatrixEntry(
        origin_location_id=origin,
        destination_location_id=destination,
        transport_type=TransportType.CAR,
        travel_min=10,
        distance_km=5.0,
        matrix_version="test-v1",
    )
    for origin in LOCATIONS
    for destination in LOCATIONS
    if origin != destination
]


def _entry(
    origin: str,
    destination: str,
    transport_type: TransportType,
    travel_min: int,
    matrix_version: str = "v1",
) -> TravelMatrixEntry:
    return TravelMatrixEntry(
        origin_location_id=origin,
        destination_location_id=destination,
        transport_type=transport_type,
        travel_min=travel_min,
        distance_km=5.0,
        matrix_version=matrix_version,
    )


def _job(
    job_id: str,
    work_type: str = "CONNECTION",
    window_start: str = "2026-09-20T10:00:00+03:00",
    window_end: str = "2026-09-20T16:00:00+03:00",
    duration: int = 90,
    status: str | None = "NEW",
    required_transport_type: TransportType | None = None,
) -> JobRecord:
    return JobRecord(
        id=job_id,
        source_bk_type="Тест",
        work_type=work_type,
        service_zone="Восток",
        address=f"Адрес {job_id}",
        service_duration_min=duration,
        source_filename="Восток Синтетические данные.csv",
        window_start=datetime.fromisoformat(window_start),
        window_end=datetime.fromisoformat(window_end),
        location_id="LOC-A",
        status=status,
        required_transport_type=required_transport_type,
    )


def _engineer(
    engineer_id: str = "ENG-1",
    transport_type: TransportType = TransportType.CAR,
    shift_end: str = "2026-09-20T18:00:00+03:00",
    service_districts: list[str] | None = None,
    allowed_work_types: list[str] | None = None,
) -> Engineer:
    return Engineer(
        id=engineer_id,
        name=f"Бригада {engineer_id}",
        transport_type=transport_type,
        qualifications=[Skill.ELECTRIC],
        start_location_id="DEPOT",
        shift_start=datetime(2026, 9, 20, 9, 0, tzinfo=MOSCOW),
        shift_end=datetime.fromisoformat(shift_end),
        service_districts=service_districts or ["Восток"],
        allowed_work_types=allowed_work_types
        or ["CONNECTION", "LOCAL_WORK", "ADD_ORDER", "EMERGENCY"],
    )


# --- 1. Окно обслуживания: planned_end <= window_end ------------------------


def test_window_boundary_end_exactly_at_window_end_is_allowed():
    """Окончание ровно на границе окна допустимо (planned_end == window_end)."""
    job = _job(
        "1001",
        window_start="2026-09-20T10:00:00+03:00",
        window_end="2026-09-20T11:10:00+03:00",  # 09:10 приезд, старт 10:00, конец 11:10
        duration=70,
    )

    plan = RoutePlanner(TravelMatrix(MATRIX_ENTRIES)).build_plan(
        [job],
        [_engineer()],
    )

    assert plan.assignments != []
    stop = plan.routes[0].stops[0]
    assert stop.planned_end == job.window_end


def test_window_end_one_minute_later_is_unassigned():
    """Окончание на минуту позже окна недопустимо."""
    job = _job(
        "1001",
        window_start="2026-09-20T10:00:00+03:00",
        window_end="2026-09-20T11:09:00+03:00",  # конец 11:10 > 11:09
        duration=70,
    )

    plan = RoutePlanner(TravelMatrix(MATRIX_ENTRIES)).build_plan(
        [job],
        [_engineer()],
    )

    assert plan.assignments == []
    assert plan.unassigned[0].reason_code == UnassignmentReason.NO_TIME_WINDOW


def test_validator_accepts_end_on_window_boundary():
    validator = PlanValidator(TravelMatrix(MATRIX_ENTRIES))
    job = _job("1001")
    engineer = _engineer()
    stop = RouteStop(
        job_id="1001",
        location_id="LOC-A",
        planned_arrival=datetime(2026, 9, 20, 9, 10, tzinfo=MOSCOW),
        planned_start=datetime(2026, 9, 20, 10, 0, tzinfo=MOSCOW),
        planned_end=datetime(2026, 9, 20, 16, 0, tzinfo=MOSCOW),
    )
    plan = Plan(
        assignments=[Assignment(job_id="1001", engineer_id="ENG-1")],
        routes=[Route(engineer_id="ENG-1", stops=[stop], total_travel_min=10, total_distance_km=5.0)],
        unassigned_job_ids=[],
        status="VALID",
    )

    issues = validator.validate(plan, [job], [engineer])

    assert all(issue.code != "WINDOW_VIOLATION" for issue in issues)


def test_validator_rejects_end_after_window():
    validator = PlanValidator(TravelMatrix(MATRIX_ENTRIES))
    job = _job("1001")
    engineer = _engineer()
    stop = RouteStop(
        job_id="1001",
        location_id="LOC-A",
        planned_arrival=datetime(2026, 9, 20, 9, 10, tzinfo=MOSCOW),
        planned_start=datetime(2026, 9, 20, 10, 0, tzinfo=MOSCOW),
        planned_end=datetime(2026, 9, 20, 16, 1, tzinfo=MOSCOW),  # на минуту позже
    )
    plan = Plan(
        assignments=[Assignment(job_id="1001", engineer_id="ENG-1")],
        routes=[Route(engineer_id="ENG-1", stops=[stop], total_travel_min=10, total_distance_km=5.0)],
        unassigned_job_ids=[],
        status="VALID",
    )

    issues = validator.validate(plan, [job], [engineer])

    codes = [issue.code for issue in issues]

    assert "WINDOW_VIOLATION" in codes
    assert any("заканчивается позже" in issue.message for issue in issues)


# --- 2. Матрица: уникальные ключи, запрет дубликатов ------------------------


def test_travel_matrix_loader_rejects_duplicate_key(tmp_path):
    payload = (
        '[{"origin": "A", "destination": "B", "transport_type": "CAR", '
        '"travel_min": 10, "distance_km": 5.0, "matrix_version": "v1"},'
        '{"origin": "A", "destination": "B", "transport_type": "CAR", '
        '"travel_min": 99, "distance_km": 5.0, "matrix_version": "v1"}]'
    )
    path = tmp_path / "travel_matrix.json"
    path.write_text(payload, encoding="utf-8")

    with pytest.raises(ValueError, match="Дубликат записи матрицы"):
        load_travel_matrix_file(path)


def test_travel_matrix_rejects_duplicate_key_at_runtime():
    entries = [
        _entry("A", "B", TransportType.CAR, travel_min=10),
        _entry("A", "B", TransportType.CAR, travel_min=99),
    ]

    with pytest.raises(ValueError, match="Дубликат записи матрицы"):
        TravelMatrix(entries)


# --- 3. Причины неназначения ------------------------------------------------


def test_no_feasible_insertion_when_heuristic_cannot_insert():
    """Заявка выполнима на пустом маршруте, но не встаёт в текущий."""
    job1 = _job(
        "A1",
        window_start="2026-09-20T09:00:00+03:00",
        window_end="2026-09-20T17:30:00+03:00",
        duration=480,
    )
    job2 = _job(
        "B1",
        window_start="2026-09-20T16:00:00+03:00",
        window_end="2026-09-20T18:00:00+03:00",
        duration=120,
    )

    plan = RoutePlanner(TravelMatrix(MATRIX_ENTRIES)).build_plan(
        [job1, job2],
        [_engineer()],
    )

    assert [a.job_id for a in plan.assignments] == ["A1"]
    assert plan.unassigned[0].job_id == "B1"
    assert (
        plan.unassigned[0].reason_code
        == UnassignmentReason.NO_FEASIBLE_INSERTION
    )


def test_shift_conflict_still_reported_on_empty_route():
    """Подтверждённый конфликт смены по-прежнему даёт SHIFT_CONFLICT."""
    job = _job(
        "1001",
        window_start="2026-09-20T17:00:00+03:00",
        window_end="2026-09-20T20:00:00+03:00",
        duration=120,
    )

    plan = RoutePlanner(TravelMatrix(MATRIX_ENTRIES)).build_plan(
        [job],
        [_engineer()],
    )

    assert plan.assignments == []
    assert plan.unassigned[0].reason_code == UnassignmentReason.SHIFT_CONFLICT


# --- 4. Пустые списки квалификаций и зон ------------------------------------


def test_input_validator_rejects_empty_engineer_capabilities():
    validator = InputValidator()

    data = {
        "jobs": [],
        "engineers": [
            {
                "id": "ENG-1",
                "name": "Без квалификаций",
                "transport_type": "CAR",
                "qualifications": [],
                "start_location_id": "DEPOT",
                "shift_start": "2026-09-20T09:00:00+03:00",
                "shift_end": "2026-09-20T18:00:00+03:00",
                "service_districts": ["Восток"],
                "allowed_work_types": ["CONNECTION"],
            }
        ],
    }

    _, _, issues = validator.validate(data)

    codes = [issue.code for issue in issues]

    assert "EMPTY_QUALIFICATIONS" in codes


def test_input_validator_rejects_empty_service_districts():
    validator = InputValidator()

    data = {
        "jobs": [],
        "engineers": [
            {
                "id": "ENG-1",
                "name": "Без зон",
                "transport_type": "CAR",
                "qualifications": ["ELECTRIC"],
                "start_location_id": "DEPOT",
                "shift_start": "2026-09-20T09:00:00+03:00",
                "shift_end": "2026-09-20T18:00:00+03:00",
                "service_districts": [],
                "allowed_work_types": ["CONNECTION"],
            }
        ],
    }

    _, _, issues = validator.validate(data)

    codes = [issue.code for issue in issues]

    assert "EMPTY_SERVICE_DISTRICTS" in codes


def test_pipeline_reports_fatal_error_for_empty_capabilities(tmp_path):
    (tmp_path / "Восток Синтетические данные.csv").write_text(
        "ID;Адрес;Тип заявки BK;Начало окна;Конец окна\n"
        "1001;г. Москва, ул Тестовая, д 1;Подключение;20.09.2026 10:00;20.09.2026 12:00\n",
        encoding="cp1251",
    )
    (tmp_path / "engineers.json").write_text(
        '[{"id": "ENG-1", "name": "Без зон", "transport_type": "CAR", '
        '"qualifications": ["ELECTRIC"], "start_location": "DEPOT", '
        '"shift_start": "2026-09-20T09:00:00+03:00", '
        '"shift_end": "2026-09-20T18:00:00+03:00"}]',
        encoding="utf-8",
    )
    (tmp_path / "equipment.json").write_text("[]", encoding="utf-8")
    (tmp_path / "travel_matrix.json").write_text("[]", encoding="utf-8")

    bundle = load_input_directory(tmp_path)

    codes = [error.code for error in bundle.errors]

    assert "EMPTY_ENGINEER_CAPABILITIES" in codes
    assert all(not error.can_skip for error in bundle.errors)


# --- 5. required_transport_type ---------------------------------------------


def test_required_transport_type_mismatch_is_unassigned():
    job = _job(
        "1001",
        required_transport_type=TransportType.BICYCLE,
    )

    plan = RoutePlanner(TravelMatrix(MATRIX_ENTRIES)).build_plan(
        [job],
        [_engineer(transport_type=TransportType.CAR)],
    )

    assert plan.assignments == []
    assert (
        plan.unassigned[0].reason_code
        == UnassignmentReason.NO_QUALIFIED_ENGINEER
    )


def test_required_transport_type_match_is_assigned():
    job = _job(
        "1001",
        required_transport_type=TransportType.BICYCLE,
    )

    bicycle_entries = [
        TravelMatrixEntry(
            origin_location_id=origin,
            destination_location_id=destination,
            transport_type=TransportType.BICYCLE,
            travel_min=20,
            distance_km=3.0,
            matrix_version="test-v1",
        )
        for origin in LOCATIONS
        for destination in LOCATIONS
        if origin != destination
    ]

    plan = RoutePlanner(TravelMatrix(bicycle_entries)).build_plan(
        [job],
        [_engineer(transport_type=TransportType.BICYCLE)],
    )

    assert len(plan.assignments) == 1


# --- 6. Приоритеты и статусы ------------------------------------------------


def test_local_work_and_add_order_have_same_business_priority():
    assert WORK_TYPE_PRIORITY["LOCAL_WORK"] == WORK_TYPE_PRIORITY["ADD_ORDER"]


def test_completed_and_cancelled_jobs_are_excluded_from_planning():
    active = _job("1001", status="NEW")
    completed = _job("1002", status="COMPLETED")
    cancelled = _job("1003", status="CANCELLED")

    plan = RoutePlanner(TravelMatrix(MATRIX_ENTRIES)).build_plan(
        [active, completed, cancelled],
        [_engineer()],
    )

    assert [a.job_id for a in plan.assignments] == ["1001"]
    assert plan.unassigned == []


# --- 7. Baseline и сравнение ------------------------------------------------


def test_baseline_assigns_in_fixed_order_to_first_engineer():
    jobs = [_job(f"100{i}") for i in range(1, 4)]
    engineers = [_engineer("ENG-1"), _engineer("ENG-2")]

    plan = BaselinePlanner(TravelMatrix(MATRIX_ENTRIES)).build_plan(
        jobs,
        engineers,
    )

    assert len(plan.assignments) == 3
    # Первая подходящая бригада получает все заявки (в конец маршрута).
    assert {a.engineer_id for a in plan.assignments} == {"ENG-1"}
    assert [s.job_id for s in plan.routes[0].stops] == ["1001", "1002", "1003"]


def test_comparison_reports_metrics_for_both_plans():
    jobs = [_job(f"10{i}") for i in range(1, 4)]
    engineers = [_engineer("ENG-1"), _engineer("ENG-2")]
    travel = TravelMatrix(MATRIX_ENTRIES)

    main_plan = RoutePlanner(travel).build_plan(jobs, engineers)
    baseline_plan = BaselinePlanner(travel).build_plan(jobs, engineers)

    comparison = compare_plans(main_plan, baseline_plan, jobs, engineers)

    assert comparison.metrics["main"]["assigned"] == 3
    assert comparison.metrics["baseline"]["assigned"] == 3
    assert len(comparison.by_engineer) == 2
    assert len(comparison.by_priority) >= 1