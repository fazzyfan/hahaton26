"""Тесты единого источника допуска бригады (allowed_work_types).

По Data Contract v1.2 тестовые навыки ELECTRIC/NETWORK/MECHANIC заменены
официальными типами работ из конфигурации. Совместимость заявки и бригады
определяется ТОЛЬКО по полю allowed_work_types (плюс зоны/транспорт/
оборудование), а не по qualifications.
"""
from datetime import datetime, timedelta, timezone

from src.models.entities import Engineer, JobRecord
from src.models.enums import TransportType
from src.optimizer.compatibility import CompatibilityService

MOSCOW = timezone(timedelta(hours=3))

SHIFT_START = datetime(2026, 9, 17, 9, 0, tzinfo=MOSCOW)
WINDOW_END = datetime(2026, 9, 17, 13, 0, tzinfo=MOSCOW)
SHIFT_END = datetime(2026, 9, 17, 17, 0, tzinfo=MOSCOW)


def create_job(work_type: str) -> JobRecord:
    return JobRecord(
        id="JOB-TEST",
        source_bk_type="Подключение",
        work_type=work_type,
        service_zone="Восток",
        address="Адрес JOB-TEST",
        service_duration_min=60,
        source_filename="Восток Синтетические данные.csv",
        window_start=SHIFT_START,
        window_end=WINDOW_END,
        location_id="LOC-A",
    )


def create_engineer(
    engineer_id: str,
    allowed_work_types: list[str],
) -> Engineer:
    return Engineer(
        id=engineer_id,
        name="Тестовый инженер",
        transport_type=TransportType.CAR,
        start_location_id="DEPOT",
        shift_start=SHIFT_START,
        shift_end=SHIFT_END,
        allowed_work_types=allowed_work_types,
    )


def test_engineer_is_compatible_when_work_type_allowed():
    service = CompatibilityService()

    job = create_job("CONNECTION")

    engineer = create_engineer(
        "ENG-001",
        ["CONNECTION", "LOCAL_WORK"],
    )

    assert service.is_compatible(job, engineer) is True


def test_engineer_is_not_compatible_without_work_type_permission():
    """Заявка НЕ назначается бригаде без допуска к её типу работы."""
    service = CompatibilityService()

    job = create_job("EMERGENCY")

    engineer = create_engineer(
        "ENG-001",
        ["CONNECTION", "LOCAL_WORK"],  # EMERGENCY не разрешён
    )

    assert service.is_compatible(job, engineer) is False


def test_qualifications_do_not_grant_permission():
    """Навыки ELECTRIC/NETWORK/MECHANIC не дают допуск к типу работы."""
    service = CompatibilityService()

    job = create_job("EMERGENCY")

    engineer = Engineer(
        id="ENG-001",
        name="Тестовый инженер",
        transport_type=TransportType.CAR,
        qualifications=["MECHANIC", "ELECTRIC"],  # устаревшее поле
        start_location_id="DEPOT",
        shift_start=SHIFT_START,
        shift_end=SHIFT_END,
        allowed_work_types=["CONNECTION"],
    )

    assert service.is_compatible(job, engineer) is False


def test_get_compatible_engineers_filters_by_work_type():
    service = CompatibilityService()

    job = create_job("CONNECTION")

    engineers = [
        create_engineer("ENG-001", ["CONNECTION", "LOCAL_WORK"]),
        create_engineer("ENG-002", ["LOCAL_WORK"]),
        create_engineer("ENG-003", ["CONNECTION"]),
    ]

    compatible = service.get_compatible_engineers(job, engineers)

    assert [engineer.id for engineer in compatible] == [
        "ENG-001",
        "ENG-003",
    ]