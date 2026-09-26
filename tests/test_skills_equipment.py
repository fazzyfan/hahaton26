"""Проверка пунктов 2 и 3 ТЗ через ОСНОВНОЙ планировщик и валидатор.

Пункт 2 — допуск по типу работы: заявка НЕ назначается бригаде без
допуска (allowed_work_types), даже если бригада свободна и ближе;
валидатор отклоняет такое назначение.

Пункт 3 — оборудование: заявка с required_equipment НЕ назначается
бригаде без требуемого инструмента, даже если бригада свободна и ближе;
валидатор отклоняет такое назначение.
"""
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
from src.models.enums import TransportType, UnassignmentReason
from src.optimizer.route_planner import RoutePlanner
from src.optimizer.travel import TravelMatrix
from src.validation.plan_validator import PlanValidator

MOSCOW = timezone(timedelta(hours=3))


def _entry(
    origin: str,
    destination: str,
    travel_min: int,
) -> TravelMatrixEntry:
    return TravelMatrixEntry(
        origin_location_id=origin,
        destination_location_id=destination,
        transport_type=TransportType.CAR,
        travel_min=travel_min,
        distance_km=round(travel_min / 60 * 28, 1),
        matrix_version="test-skills-v1",
    )


# Близкая база DEPOT -> LOC-JOB (5 мин) и дальняя LOC-FAR -> LOC-JOB (90 мин).
MATRIX_ENTRIES = [
    _entry("DEPOT", "LOC-JOB", 5),
    _entry("LOC-JOB", "DEPOT", 5),
    _entry("LOC-FAR", "LOC-JOB", 90),
    _entry("LOC-JOB", "LOC-FAR", 90),
    _entry("DEPOT", "LOC-FAR", 85),
    _entry("LOC-FAR", "DEPOT", 85),
]


def _job(
    job_id: str,
    work_type: str = "EMERGENCY",
    required_equipment: list[str] | None = None,
) -> JobRecord:
    return JobRecord(
        id=job_id,
        source_bk_type="Тест",
        work_type=work_type,
        service_zone="Восток",
        address=f"Адрес {job_id}",
        service_duration_min=60,
        source_filename="Восток Синтетические данные.csv",
        window_start=datetime(2026, 9, 20, 10, 0, tzinfo=MOSCOW),
        window_end=datetime(2026, 9, 20, 12, 0, tzinfo=MOSCOW),
        location_id="LOC-JOB",
        required_equipment=required_equipment or [],
    )


def _engineer(
    engineer_id: str,
    start_location_id: str,
    allowed_work_types: list[str],
    equipment_ids: list[str] | None = None,
) -> Engineer:
    return Engineer(
        id=engineer_id,
        name=f"Бригада {engineer_id}",
        transport_type=TransportType.CAR,
        start_location_id=start_location_id,
        shift_start=datetime(2026, 9, 20, 9, 0, tzinfo=MOSCOW),
        shift_end=datetime(2026, 9, 20, 18, 0, tzinfo=MOSCOW),
        service_districts=["Восток"],
        allowed_work_types=allowed_work_types,
        equipment_ids=equipment_ids or [],
    )


# --- Пункт 2: допуск по типу работы ----------------------------------------

def test_planner_does_not_assign_without_work_type_permission_even_if_closer():
    """Ближняя свободная бригада БЕЗ допуска не получает заявку."""
    job = _job("1001", work_type="EMERGENCY")

    engineers = [
        # Дальняя бригада, но с допуском к EMERGENCY.
        _engineer(
            "ENG-A",
            start_location_id="LOC-FAR",  # 90 минут до заявки
            allowed_work_types=["EMERGENCY", "CONNECTION"],
        ),
        # Ближняя и свободная бригада, но БЕЗ допуска к EMERGENCY.
        _engineer(
            "ENG-B",
            start_location_id="DEPOT",  # 5 минут до заявки
            allowed_work_types=["CONNECTION", "LOCAL_WORK", "ADD_ORDER"],
        ),
    ]

    plan = RoutePlanner(TravelMatrix(MATRIX_ENTRIES)).build_plan(
        [job],
        engineers,
    )

    assert len(plan.assignments) == 1
    assert plan.assignments[0].engineer_id == "ENG-A"
    assert plan.assignments[0].job_id == "1001"


def test_planner_unassigns_when_no_brigade_has_work_type_permission():
    """Если ни одна бригада не имеет допуска — заявка не назначается."""
    job = _job("1001", work_type="EMERGENCY")

    engineers = [
        _engineer(
            "ENG-B",
            start_location_id="DEPOT",  # близко и свободно
            allowed_work_types=["CONNECTION", "LOCAL_WORK"],
        ),
    ]

    plan = RoutePlanner(TravelMatrix(MATRIX_ENTRIES)).build_plan(
        [job],
        engineers,
    )

    assert plan.assignments == []
    assert plan.unassigned[0].reason_code == (
        UnassignmentReason.NO_QUALIFIED_ENGINEER
    )


def test_validator_rejects_assignment_without_work_type_permission():
    """Валидатор отклоняет назначение бригаде без допуска к типу работы."""
    job = _job("1001", work_type="EMERGENCY")
    engineer = _engineer(
        "ENG-B",
        start_location_id="DEPOT",
        allowed_work_types=["CONNECTION", "LOCAL_WORK"],
    )

    stop = RouteStop(
        job_id="1001",
        location_id="LOC-JOB",
        planned_arrival=datetime(2026, 9, 20, 10, 5, tzinfo=MOSCOW),
        planned_start=datetime(2026, 9, 20, 10, 5, tzinfo=MOSCOW),
        planned_end=datetime(2026, 9, 20, 11, 5, tzinfo=MOSCOW),
    )
    plan = Plan(
        assignments=[Assignment(job_id="1001", engineer_id="ENG-B")],
        routes=[
            Route(
                engineer_id="ENG-B",
                stops=[stop],
                total_travel_min=5,
                total_distance_km=2.3,
            )
        ],
        unassigned_job_ids=[],
        status="VALID",
    )

    issues = PlanValidator(TravelMatrix(MATRIX_ENTRIES)).validate(
        plan,
        [job],
        [engineer],
    )

    assert any(
        issue.code == "INCOMPATIBLE_ENGINEER"
        and "Тип работы" in issue.message
        for issue in issues
    )


# --- Пункт 3: оборудование --------------------------------------------------

def test_planner_does_not_assign_without_equipment_even_if_closer():
    """Ближняя свободная бригада без инструмента не получает заявку."""
    job = _job("1001", work_type="CONNECTION", required_equipment=["EQ-TOOL"])

    engineers = [
        # Дальняя бригада, но имеет требуемый инструмент.
        _engineer(
            "ENG-A",
            start_location_id="LOC-FAR",
            allowed_work_types=["CONNECTION", "EMERGENCY"],
            equipment_ids=["EQ-TOOL"],
        ),
        # Ближняя и свободная бригада, но без EQ-TOOL.
        _engineer(
            "ENG-B",
            start_location_id="DEPOT",
            allowed_work_types=["CONNECTION", "LOCAL_WORK"],
            equipment_ids=["INSTALLATION_KIT"],
        ),
    ]

    plan = RoutePlanner(TravelMatrix(MATRIX_ENTRIES)).build_plan(
        [job],
        engineers,
    )

    assert len(plan.assignments) == 1
    assert plan.assignments[0].engineer_id == "ENG-A"
    assert plan.assignments[0].job_id == "1001"


def test_planner_unassigns_when_no_brigade_has_required_equipment():
    """Если требуемого инструмента нет ни у кого — заявка не назначается."""
    job = _job("1001", work_type="CONNECTION", required_equipment=["EQ-TOOL"])

    engineers = [
        _engineer(
            "ENG-B",
            start_location_id="DEPOT",
            allowed_work_types=["CONNECTION"],
            equipment_ids=["INSTALLATION_KIT"],
        ),
    ]

    plan = RoutePlanner(TravelMatrix(MATRIX_ENTRIES)).build_plan(
        [job],
        engineers,
    )

    assert plan.assignments == []
    assert plan.unassigned[0].reason_code == (
        UnassignmentReason.NO_QUALIFIED_ENGINEER
    )


def test_validator_rejects_assignment_without_required_equipment():
    """Валидатор отклоняет назначение бригаде без требуемого оборудования."""
    job = _job("1001", work_type="CONNECTION", required_equipment=["EQ-TOOL"])
    engineer = _engineer(
        "ENG-B",
        start_location_id="DEPOT",
        allowed_work_types=["CONNECTION"],
        equipment_ids=["INSTALLATION_KIT"],
    )

    stop = RouteStop(
        job_id="1001",
        location_id="LOC-JOB",
        planned_arrival=datetime(2026, 9, 20, 10, 5, tzinfo=MOSCOW),
        planned_start=datetime(2026, 9, 20, 10, 5, tzinfo=MOSCOW),
        planned_end=datetime(2026, 9, 20, 11, 15, tzinfo=MOSCOW),
    )
    plan = Plan(
        assignments=[Assignment(job_id="1001", engineer_id="ENG-B")],
        routes=[
            Route(
                engineer_id="ENG-B",
                stops=[stop],
                total_travel_min=5,
                total_distance_km=2.3,
            )
        ],
        unassigned_job_ids=[],
        status="VALID",
    )

    issues = PlanValidator(TravelMatrix(MATRIX_ENTRIES)).validate(
        plan,
        [job],
        [engineer],
    )

    assert any(
        issue.code == "INCOMPATIBLE_ENGINEER"
        and "Оборудование" in issue.message
        for issue in issues
    )