"""Тесты события «инженер стал недоступен» (статистическое перепланирование).

Завершённые работы сохраняются, будущие заявки инженера пересчитываются,
невозможные назначения остаются неназначенными с причиной.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from src.models.entities import (
    Assignment,
    Engineer,
    JobRecord,
    Plan,
    Route,
    RouteStop,
    TravelMatrixEntry,
)
from src.models.enums import TransportType
from src.optimizer.travel import TravelMatrix
from src.services.replanning import replan_after_unavailability
from src.validation.plan_validator import PlanValidator

MOSCOW = timezone(timedelta(hours=3))


def _entry(origin: str, destination: str, travel_min: int) -> TravelMatrixEntry:
    return TravelMatrixEntry(
        origin_location_id=origin,
        destination_location_id=destination,
        transport_type=TransportType.CAR,
        travel_min=travel_min,
        distance_km=round(travel_min / 60 * 28, 1),
        matrix_version="replan-v1",
    )


MATRIX_ENTRIES = [
    _entry("DEPOT", "LOC-A", 10),
    _entry("LOC-A", "DEPOT", 10),
    _entry("DEPOT", "LOC-B", 10),
    _entry("LOC-B", "DEPOT", 10),
    _entry("LOC-A", "LOC-B", 5),
    _entry("LOC-B", "LOC-A", 5),
]


def _job(job_id: str, start: str, end: str, location_id: str) -> JobRecord:
    return JobRecord(
        id=job_id,
        source_bk_type="Подключение",
        work_type="CONNECTION",
        service_zone="Восток",
        address=f"Адрес {job_id}",
        service_duration_min=30,
        source_filename="Восток Синтетические данные.csv",
        window_start=datetime.fromisoformat(start),
        window_end=datetime.fromisoformat(end),
        location_id=location_id,
        required_equipment=["INSTALLATION_KIT"],
    )


def _engineer(engineer_id: str) -> Engineer:
    return Engineer(
        id=engineer_id,
        name=f"Бригада {engineer_id}",
        transport_type=TransportType.CAR,
        start_location_id="DEPOT",
        shift_start=datetime(2026, 8, 17, 9, 0, tzinfo=MOSCOW),
        shift_end=datetime(2026, 8, 17, 18, 0, tzinfo=MOSCOW),
        service_districts=["Восток"],
        allowed_work_types=["CONNECTION", "LOCAL_WORK", "ADD_ORDER", "EMERGENCY"],
        equipment_ids=["INSTALLATION_KIT", "DIAGNOSTIC_KIT", "CUSTOMER_EQUIPMENT"],
    )


def _bundle(jobs, engineers):
    return SimpleNamespace(
        jobs=jobs,
        engineers=engineers,
        travel_matrix=MATRIX_ENTRIES,
        errors=[],
        locations=[],
    )


def _old_plan_with_two_stops(engineer_id: str) -> Plan:
    """Старый план: ранняя работа (завершена) + поздняя (будущая) у инженера."""
    stop_early = RouteStop(
        job_id="1001",
        location_id="LOC-A",
        planned_arrival=datetime(2026, 8, 17, 9, 10, tzinfo=MOSCOW),
        planned_start=datetime(2026, 8, 17, 9, 10, tzinfo=MOSCOW),
        planned_end=datetime(2026, 8, 17, 9, 40, tzinfo=MOSCOW),
    )
    stop_late = RouteStop(
        job_id="1002",
        location_id="LOC-B",
        planned_arrival=datetime(2026, 8, 17, 9, 45, tzinfo=MOSCOW),
        planned_start=datetime(2026, 8, 17, 16, 0, tzinfo=MOSCOW),
        planned_end=datetime(2026, 8, 17, 16, 30, tzinfo=MOSCOW),
    )

    return Plan(
        assignments=[
            Assignment(job_id="1001", engineer_id=engineer_id),
            Assignment(job_id="1002", engineer_id=engineer_id),
        ],
        routes=[
            Route(
                engineer_id=engineer_id,
                stops=[stop_early, stop_late],
                total_travel_min=15,
                total_distance_km=7.0,
            )
        ],
        unassigned_job_ids=[],
        status="VALID",
    )


def test_preserved_completed_and_reassigned_future():
    jobs = [
        _job(
            "1001",
            "2026-08-17T09:00:00+03:00",
            "2026-08-17T10:00:00+03:00",
            "LOC-A",
        ),
        _job(
            "1002",
            "2026-08-17T16:00:00+03:00",
            "2026-08-17T17:00:00+03:00",
            "LOC-B",
        ),
    ]
    engineers = [_engineer("ENG-A"), _engineer("ENG-B")]
    bundle = _bundle(jobs, engineers)

    old_plan = _old_plan_with_two_stops("ENG-A")

    event_time = datetime(2026, 8, 17, 12, 0, tzinfo=MOSCOW)

    result = replan_after_unavailability(
        bundle,
        old_plan,
        engineer_id="ENG-A",
        event_time=event_time,
    )

    # Завершённая до события работа сохранена за ENG-A.
    assert result.preserved_job_ids == ["1001"]

    # Будущая заявка освобождена и переназначена другой бригаде.
    assert result.released_job_ids == ["1002"]
    assert ("1002", "ENG-B") in result.reassigned

    # Итоговый план валиден и не содержит нарушений.
    assert result.issues == []
    assert result.new_plan.status == "VALID"

    new_by_job = {
        assignment.job_id: assignment.engineer_id
        for assignment in result.new_plan.assignments
    }

    assert new_by_job["1001"] == "ENG-A"
    assert new_by_job["1002"] == "ENG-B"


def test_impossible_reassignment_stays_unassigned_with_reason():
    """Если будущую заявку некому взять — она остаётся неназначенной."""
    jobs = [
        _job(
            "1001",
            "2026-08-17T09:00:00+03:00",
            "2026-08-17T10:00:00+03:00",
            "LOC-A",
        ),
        _job(
            "1002",
            "2026-08-17T16:00:00+03:00",
            "2026-08-17T17:00:00+03:00",
            "LOC-B",
        ),
    ]
    engineers = [
        _engineer("ENG-A"),
        _engineer("ENG-B"),
    ]
    # ENG-B не имеет допуска к типу работы 1002 (LOCAL_WORK).
    engineers[0].allowed_work_types = ["CONNECTION", "LOCAL_WORK"]
    engineers[1].allowed_work_types = ["CONNECTION"]
    jobs[1].work_type = "LOCAL_WORK"
    jobs[1].source_bk_type = "Локальная заявка"

    bundle = _bundle(jobs, engineers)

    old_plan = _old_plan_with_two_stops("ENG-A")

    event_time = datetime(2026, 8, 17, 12, 0, tzinfo=MOSCOW)

    result = replan_after_unavailability(
        bundle,
        old_plan,
        engineer_id="ENG-A",
        event_time=event_time,
    )

    # 1001 сохранена; 1002 освобождена, но её некому выполнить.
    assert result.preserved_job_ids == ["1001"]
    assert result.released_job_ids == ["1002"]
    assert result.reassigned == []

    assert any(item.job_id == "1002" for item in result.unassigned_released)

    # Итоговый план корректен для независимого валидатора.
    validator = PlanValidator(TravelMatrix(MATRIX_ENTRIES))
    issues = validator.validate(result.new_plan, jobs, engineers)

    assert issues == []


def test_unknown_engineer_raises():
    bundle = _bundle([], [])
    empty_plan = Plan(
        assignments=[],
        routes=[],
        unassigned_job_ids=[],
        status="VALID",
    )

    try:
        replan_after_unavailability(
            bundle,
            empty_plan,
            engineer_id="ENG-X",
            event_time=datetime(2026, 8, 17, 12, 0, tzinfo=MOSCOW),
        )
    except ValueError as error:
        assert "ENG-X" in str(error)
    else:  # pragma: no cover
        raise AssertionError("Ожидалась ValueError для неизвестного инженера")