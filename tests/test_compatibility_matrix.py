"""Тесты матрицы совместимости по единому источнику допуска.

Матрица строится по allowed_work_types (типы работ из конфигурации);
устаревшие навыки ELECTRIC/NETWORK/MECHANIC в выборе не участвуют.
"""
from datetime import datetime, timedelta, timezone

from src.models.entities import Engineer, JobRecord
from src.models.enums import TransportType
from src.optimizer.compatibility_matrix import CompatibilityMatrix

MOSCOW = timezone(timedelta(hours=3))

SHIFT_START = datetime(2026, 9, 17, 9, 0, tzinfo=MOSCOW)
WINDOW_END = datetime(2026, 9, 17, 13, 0, tzinfo=MOSCOW)
SHIFT_END = datetime(2026, 9, 17, 17, 0, tzinfo=MOSCOW)


def create_job(job_id: str, work_type: str) -> JobRecord:
    return JobRecord(
        id=job_id,
        source_bk_type="Тест",
        work_type=work_type,
        service_zone="Восток",
        address=f"Адрес {job_id}",
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


def test_build_compatibility_matrix():
    jobs = [
        create_job("JOB-001", "CONNECTION"),
        create_job("JOB-002", "EMERGENCY"),
    ]

    engineers = [
        create_engineer("ENG-001", ["CONNECTION", "LOCAL_WORK"]),
        create_engineer("ENG-002", ["EMERGENCY"]),
        create_engineer("ENG-003", ["CONNECTION"]),
    ]

    matrix = CompatibilityMatrix()

    result = matrix.build(jobs, engineers)

    assert result == {
        "JOB-001": ["ENG-001", "ENG-003"],
        "JOB-002": ["ENG-002"],
    }