from datetime import datetime, timedelta, timezone

from src.models.entities import (
    Assignment,
    Engineer,
    JobRecord,
    Plan,
    Route,
    RouteStop,
    TravelMatrixEntry,
    UnassignedJob,
)
from src.models.enums import Skill, TransportType, UnassignmentReason
from src.optimizer.route_planner import RoutePlanner
from src.optimizer.travel import TravelMatrix
from src.validation.plan_validator import PlanValidator

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
    for origin in ("DEPOT", "LOC-A", "LOC-B")
    for destination in ("DEPOT", "LOC-A", "LOC-B")
    if origin != destination
]


def _job(job_id: str = "1001") -> JobRecord:
    return JobRecord(
        id=job_id,
        source_bk_type="Тест",
        work_type="CONNECTION",
        service_zone="Восток",
        address=f"Адрес {job_id}",
        service_duration_min=90,
        source_filename="Восток Синтетические данные.csv",
        window_start=datetime(2026, 9, 20, 10, 0, tzinfo=MOSCOW),
        window_end=datetime(2026, 9, 20, 16, 0, tzinfo=MOSCOW),
        location_id="LOC-A",
    )


def _engineer(engineer_id: str = "ENG-1") -> Engineer:
    return Engineer(
        id=engineer_id,
        name=f"Бригада {engineer_id}",
        transport_type=TransportType.CAR,
        qualifications=[Skill.ELECTRIC],
        start_location_id="DEPOT",
        shift_start=datetime(2026, 9, 20, 9, 0, tzinfo=MOSCOW),
        shift_end=datetime(2026, 9, 20, 18, 0, tzinfo=MOSCOW),
    )


def _built_plan() -> tuple[Plan, list[JobRecord], list[Engineer]]:
    jobs = [_job()]
    engineers = [_engineer()]
    plan = RoutePlanner(TravelMatrix(MATRIX_ENTRIES)).build_plan(jobs, engineers)
    return plan, jobs, engineers


def _validate(plan, jobs, engineers):
    validator = PlanValidator(TravelMatrix(MATRIX_ENTRIES))
    return validator.validate(plan, jobs, engineers)


def test_validator_accepts_planner_output():
    plan, jobs, engineers = _built_plan()

    issues = _validate(plan, jobs, engineers)

    assert issues == []


def test_validator_detects_double_assignment():
    plan, jobs, engineers = _built_plan()

    plan.assignments.append(
        Assignment(job_id="1001", engineer_id="ENG-1")
    )

    issues = _validate(plan, jobs, engineers)

    codes = [issue.code for issue in issues]

    assert "DOUBLE_ASSIGNMENT" in codes


def test_validator_detects_window_violation():
    plan, jobs, engineers = _built_plan()

    job = jobs[0]
    job.window_start = datetime(2026, 9, 20, 15, 0, tzinfo=MOSCOW)

    issues = _validate(plan, jobs, engineers)

    codes = [issue.code for issue in issues]

    assert "WINDOW_VIOLATION" in codes


def test_validator_detects_shift_violation():
    plan, jobs, engineers = _built_plan()

    engineers[0].shift_end = datetime(2026, 9, 20, 11, 0, tzinfo=MOSCOW)

    issues = _validate(plan, jobs, engineers)

    codes = [issue.code for issue in issues]

    assert "SHIFT_VIOLATION" in codes


def test_validator_detects_zone_mismatch():
    plan, jobs, engineers = _built_plan()

    engineers[0].service_districts = ["Югоцентр"]

    issues = _validate(plan, jobs, engineers)

    codes = [issue.code for issue in issues]

    assert "INCOMPATIBLE_ENGINEER" in codes


def test_validator_detects_travel_underestimate():
    plan, jobs, engineers = _built_plan()

    stop = plan.routes[0].stops[0]
    stop.planned_arrival = datetime(2026, 9, 20, 9, 5, tzinfo=MOSCOW)

    issues = _validate(plan, jobs, engineers)

    codes = [issue.code for issue in issues]

    assert "TRAVEL_VIOLATION" in codes


def test_validator_detects_job_not_covered():
    plan, jobs, engineers = _built_plan()

    # Заявка есть во входных данных, но ни назначена, ни в unassigned.
    jobs.append(_job("1002"))

    issues = _validate(plan, jobs, engineers)

    codes = [issue.code for issue in issues]

    assert "JOB_NOT_COVERED" in codes


def test_validator_detects_job_in_both_lists():
    plan, jobs, engineers = _built_plan()

    plan.unassigned.append(
        UnassignedJob(
            job_id="1001",
            reason_code=UnassignmentReason.SHIFT_CONFLICT,
            message="Дубликат",
        )
    )
    plan.unassigned_job_ids.append("1001")

    issues = _validate(plan, jobs, engineers)

    codes = [issue.code for issue in issues]

    assert "BOTH_ASSIGNED_AND_UNASSIGNED" in codes