from datetime import datetime, timedelta, timezone

from src.models.entities import (
    Engineer,
    JobRecord,
    TravelMatrixEntry,
    UnassignedJob,
)
from src.models.enums import Skill, TransportType, UnassignmentReason
from src.optimizer.route_planner import RoutePlanner
from src.optimizer.travel import TravelMatrix

MOSCOW = timezone(timedelta(hours=3))

LOCATIONS = ["DEPOT", "LOC-A", "LOC-B", "LOC-C"]

# Полный связный граф CAR: 10 минут между любыми двумя точками.
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


def _job(
    job_id: str,
    work_type: str = "CONNECTION",
    service_zone: str = "Восток",
    location: str = "LOC-A",
    window_start: str = "2026-09-20T10:00:00+03:00",
    window_end: str = "2026-09-20T16:00:00+03:00",
    duration: int = 90,
    required_equipment: list[str] | None = None,
) -> JobRecord:
    return JobRecord(
        id=job_id,
        source_bk_type="Тест",
        work_type=work_type,
        service_zone=service_zone,
        address=f"Адрес {job_id}",
        service_duration_min=duration,
        source_filename="Восток Синтетические данные.csv",
        window_start=datetime.fromisoformat(window_start),
        window_end=datetime.fromisoformat(window_end),
        location_id=location,
        required_equipment=required_equipment or [],
    )


def _engineer(
    engineer_id: str = "ENG-1",
    service_districts: list[str] | None = None,
    allowed_work_types: list[str] | None = None,
    equipment_ids: list[str] | None = None,
    shift_start: str = "2026-09-20T09:00:00+03:00",
    shift_end: str = "2026-09-20T18:00:00+03:00",
) -> Engineer:
    return Engineer(
        id=engineer_id,
        name=f"Бригада {engineer_id}",
        transport_type=TransportType.CAR,
        qualifications=[Skill.ELECTRIC],
        start_location_id="DEPOT",
        shift_start=datetime.fromisoformat(shift_start),
        shift_end=datetime.fromisoformat(shift_end),
        service_districts=service_districts or [],
        allowed_work_types=allowed_work_types or [],
        equipment_ids=equipment_ids or [],
    )


def _plan(jobs: list[JobRecord], engineers: list[Engineer]):
    planner = RoutePlanner(TravelMatrix(MATRIX_ENTRIES))
    return planner.build_plan(jobs, engineers)


def test_assigns_job_to_qualified_engineer():
    job = _job("1001")
    plan = _plan([job], [_engineer()])

    assert [assignment.job_id for assignment in plan.assignments] == ["1001"]
    assert plan.unassigned == []

    stop = plan.routes[0].stops[0]
    assert stop.job_id == "1001"
    assert stop.planned_start >= job.window_start
    assert stop.planned_start <= job.window_end
    assert stop.planned_end == stop.planned_start + timedelta(minutes=90)


def test_district_mismatch_is_unassigned():
    job = _job("1001", service_zone="Югоцентр")
    engineer = _engineer(service_districts=["Восток"])

    plan = _plan([job], [engineer])

    assert plan.assignments == []
    assert plan.unassigned_job_ids == ["1001"]
    assert plan.unassigned[0].reason_code == UnassignmentReason.NO_QUALIFIED_ENGINEER


def test_work_type_mismatch_is_unassigned():
    job = _job("1001", work_type="EMERGENCY")
    engineer = _engineer(allowed_work_types=["LOCAL_WORK"])

    plan = _plan([job], [engineer])

    assert plan.assignments == []
    assert plan.unassigned[0].reason_code == UnassignmentReason.NO_QUALIFIED_ENGINEER


def test_equipment_mismatch_is_unassigned():
    job = _job("1001", required_equipment=["EQ-SPLICER"])
    engineer = _engineer(equipment_ids=["EQ-OPTIC"])

    plan = _plan([job], [engineer])

    assert plan.assignments == []
    assert plan.unassigned[0].reason_code == UnassignmentReason.NO_QUALIFIED_ENGINEER


def test_missing_travel_data_is_unassigned():
    job = _job("1001", location="LOC-ZZZ")

    plan = _plan([job], [_engineer()])

    assert plan.assignments == []
    assert plan.unassigned[0].reason_code == UnassignmentReason.NO_TRAVEL_DATA


def test_window_conflict_is_unassigned():
    job = _job(
        "1001",
        window_start="2026-09-20T05:00:00+03:00",
        window_end="2026-09-20T08:00:00+03:00",
    )

    plan = _plan([job], [_engineer()])

    assert plan.assignments == []
    assert plan.unassigned[0].reason_code == UnassignmentReason.NO_TIME_WINDOW


def test_shift_conflict_is_unassigned():
    job = _job(
        "1001",
        window_start="2026-09-20T17:00:00+03:00",
        window_end="2026-09-20T20:00:00+03:00",
        duration=120,
    )

    plan = _plan([job], [_engineer()])

    assert plan.assignments == []
    assert plan.unassigned[0].reason_code == UnassignmentReason.SHIFT_CONFLICT


def test_multiple_jobs_split_across_crews():
    jobs = [_job(f"10{i}") for i in range(1, 4)]
    engineers = [_engineer("ENG-1"), _engineer("ENG-2")]

    plan = _plan(jobs, engineers)

    assert len(plan.assignments) == 3
    assert len({a.engineer_id for a in plan.assignments}) == 2


def test_route_times_account_for_travel_and_service():
    job_a = _job("A1", location="LOC-A")
    job_b = _job("B1", location="LOC-B")

    plan = _plan([job_a, job_b], [_engineer()])

    assert [s.job_id for s in plan.routes[0].stops] == ["A1", "B1"]

    first, second = plan.routes[0].stops

    # Выезд из DEPOT в 09:00, путь 10 мин -> прибытие 09:10.
    assert first.planned_arrival.hour == 9
    assert first.planned_arrival.minute == 10

    # Начало первой работы >= окна (10:00) -> старт 10:00, конец 11:30.
    assert first.planned_start.hour == 10
    assert first.planned_end.hour == 11
    assert first.planned_end.minute == 30

    # Путь LOC-A -> LOC-B 10 минут, старт второй >= 11:40 и >= её окна.
    assert second.planned_arrival >= first.planned_end + timedelta(minutes=10)
    assert second.planned_start >= second.planned_arrival
    assert second.planned_start >= job_b.window_start


def test_each_job_assigned_at_most_once():
    jobs = [_job(f"10{i}") for i in range(1, 6)]
    engineers = [_engineer("ENG-1"), _engineer("ENG-2")]

    plan = _plan(jobs, engineers)

    job_ids = [assignment.job_id for assignment in plan.assignments]

    assert len(job_ids) == len(set(job_ids))