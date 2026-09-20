from datetime import datetime

import pytest
from pydantic import ValidationError

from src.importers.csv_jobs import (
    MOSCOW_TZ,
    normalize_job_row,
    parse_moscow_datetime,
)
from src.models.entities import JobRecord


FULL_ROW = {
    "source_filename": "Восток Синтетические данные.csv",
    "source_row": 3,
    "service_zone": "Восток",
    "district": "Ворошиловский",
    "ID": "1001",
    "Адрес": "Ростов-на-Дону, ул. Ленина, 1",
    "Тип заявки BK": "Подключение",
    "Тип заявки HD": "HD-REPAIR-42",
    "Начало окна": "20.09.2026 10:00",
    "Конец окна": "20.09.2026 12:00",
    "work_type": "CONNECTION",
    "service_duration_min": 90,
    "window_start": parse_moscow_datetime("20.09.2026 10:00"),
    "window_end": parse_moscow_datetime("20.09.2026 12:00"),
}

MINIMAL_PAYLOAD = {
    "id": "2001",
    "source_bk_type": "Дозаказ",
    "work_type": "ADD_ORDER",
    "service_zone": "Югоцентр",
    "address": "Адрес клиента",
    "service_duration_min": 40,
    "source_filename": "Югоцентр Синтетические данные.csv",
}


def test_job_record_full_valid():
    record = JobRecord(**normalize_job_row(FULL_ROW))

    assert record.id == "1001"
    assert record.source_bk_type == "Подключение"
    assert record.source_hd_type == "HD-REPAIR-42"
    assert record.work_type == "CONNECTION"
    assert record.service_zone == "Восток"
    assert record.district == "Ворошиловский"
    assert record.address == "Ростов-на-Дону, ул. Ленина, 1"
    assert record.service_duration_min == 90
    assert record.source_filename == "Восток Синтетические данные.csv"
    assert record.source_row == 3

    assert record.window_start.year == 2026
    assert record.window_start.hour == 10
    assert record.window_start.tzinfo is not None
    assert record.window_start.tzinfo == MOSCOW_TZ
    assert record.window_end.hour == 12
    assert record.window_end.tzinfo == MOSCOW_TZ


def test_job_record_required_fields_are_mandatory():
    for missing_field in MINIMAL_PAYLOAD:
        payload = {
            key: value
            for key, value in MINIMAL_PAYLOAD.items()
            if key != missing_field
        }

        with pytest.raises(ValidationError):
            JobRecord(**payload)


def test_job_record_optional_fields_default_to_none():
    record = JobRecord(**MINIMAL_PAYLOAD)

    assert record.source_hd_type is None
    assert record.district is None
    assert record.window_start is None
    assert record.window_end is None
    assert record.received_at is None
    assert record.priority is None
    assert record.status is None
    assert record.gigabit_connection is None
    assert record.required_equipment == []
    assert record.source_row is None


def test_job_record_rejects_naive_datetime():
    payload = {
        **MINIMAL_PAYLOAD,
        "window_start": datetime(2026, 9, 20, 10, 0),
    }

    with pytest.raises(ValidationError):
        JobRecord(**payload)