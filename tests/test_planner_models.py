from datetime import datetime, timedelta, timezone

from src.models.entities import (
    Engineer,
    JobRecord,
    Plan,
    RouteStop,
    UnassignedJob,
)
from src.models.enums import (
    Skill,
    TransportType,
    UnassignmentReason,
)

MOSCOW = timezone(timedelta(hours=3))


def _engineer(**overrides) -> Engineer:
    values = {
        "id": "ENG-1",
        "name": "Иван Петров",
        "transport_type": TransportType.CAR,
        "qualifications": [Skill.ELECTRIC],
        "start_location_id": "DEPOT",
        "shift_start": datetime(2026, 9, 20, 9, 0, tzinfo=MOSCOW),
        "shift_end": datetime(2026, 9, 20, 18, 0, tzinfo=MOSCOW),
    }
    values.update(overrides)
    return Engineer(**values)


def test_engineer_allowed_work_types_defaults_empty():
    engineer = _engineer()

    assert engineer.allowed_work_types == []
    assert engineer.service_districts == []


def test_engineer_allowed_work_types_and_districts():
    engineer = _engineer(
        allowed_work_types=["CONNECTION", "EMERGENCY"],
        service_districts=["Восток", "Югоцентр"],
    )

    assert engineer.allowed_work_types == ["CONNECTION", "EMERGENCY"]
    assert engineer.service_districts == ["Восток", "Югоцентр"]


def test_job_record_location_id_optional():
    payload = {
        "id": "1001",
        "source_bk_type": "Подключение",
        "work_type": "CONNECTION",
        "service_zone": "Восток",
        "address": "Адрес клиента",
        "service_duration_min": 90,
        "source_filename": "Восток Синтетические данные.csv",
    }

    record = JobRecord(**payload)
    assert record.location_id is None

    record_with_location = JobRecord(**payload, location_id="LOC-A")
    assert record_with_location.location_id == "LOC-A"


def test_unassigned_job_model():
    item = UnassignedJob(
        job_id="1001",
        reason_code=UnassignmentReason.NO_TRAVEL_DATA,
        message="Нет данных о времени пути",
    )

    assert item.job_id == "1001"
    assert item.reason_code == UnassignmentReason.NO_TRAVEL_DATA
    assert item.reason_code.value == "NO_TRAVEL_DATA"


def test_plan_contains_unassigned_with_reasons():
    plan = Plan(
        assignments=[],
        routes=[],
        unassigned_job_ids=["1001"],
        status="PLANNED",
        unassigned=[
            UnassignedJob(
                job_id="1001",
                reason_code=UnassignmentReason.SHIFT_CONFLICT,
                message="Смена не позволяет выполнить",
            )
        ],
    )

    assert len(plan.unassigned) == 1
    assert plan.unassigned[0].reason_code == UnassignmentReason.SHIFT_CONFLICT


def test_route_stop_optional_address():
    stop = RouteStop(
        job_id="1001",
        location_id="LOC-A",
        planned_arrival=datetime(2026, 9, 20, 10, 0, tzinfo=MOSCOW),
        planned_start=datetime(2026, 9, 20, 10, 0, tzinfo=MOSCOW),
        planned_end=datetime(2026, 9, 20, 11, 30, tzinfo=MOSCOW),
        address="Ростов-на-Дону, ул. Ленина, 1",
    )

    assert stop.address == "Ростов-на-Дону, ул. Ленина, 1"