import pytest

from src.models.entities import JobRecord
from src.services.import_pipeline import load_input_directory


CSV_HEADER = "ID;Адрес;Тип заявки BK;Начало окна;Конец окна\n"
VALID_ROW = "1001;Ростов-на-Дону, ул. Ленина, 1;Подключение;20.09.2026 10:00;20.09.2026 12:00\n"

ENGINEERS_JSON = """\
[
  {
    "id": "ENG-1",
    "name": "Иван Петров",
    "transport_type": "CAR",
    "qualifications": ["ELECTRIC", "NETWORK"],
    "start_location": "DEPOT",
    "shift_start": "2026-09-20T09:00:00+03:00",
    "shift_end": "2026-09-20T18:00:00+03:00",
    "equipment": ["EQ-OPTIC"]
  }
]
"""

EQUIPMENT_JSON = """\
[
  {"id": "EQ-OPTIC", "name": "Оптический тестер", "category": "measurement"}
]
"""

TRAVEL_MATRIX_JSON = """\
[
  {
    "origin": "DEPOT",
    "destination": "LOC-A",
    "transport_type": "CAR",
    "travel_min": 15,
    "distance_km": 8.5,
    "matrix_version": "synth-v1"
  }
]
"""


def _write_input_files(tmp_path) -> None:
    (tmp_path / "Восток Синтетические данные.csv").write_text(
        CSV_HEADER + VALID_ROW,
        encoding="cp1251",
    )
    (tmp_path / "engineers.json").write_text(ENGINEERS_JSON, encoding="utf-8")
    (tmp_path / "equipment.json").write_text(EQUIPMENT_JSON, encoding="utf-8")
    (tmp_path / "travel_matrix.json").write_text(TRAVEL_MATRIX_JSON, encoding="utf-8")


def test_load_input_directory_returns_complete_bundle(tmp_path):
    _write_input_files(tmp_path)

    bundle = load_input_directory(tmp_path)

    assert len(bundle.jobs) == 1
    assert isinstance(bundle.jobs[0], JobRecord)

    job = bundle.jobs[0]
    assert job.id == "1001"
    assert job.work_type == "CONNECTION"
    assert job.service_duration_min == 70
    assert job.service_zone == "Восток"
    assert job.address == "Ростов-на-Дону, ул. Ленина, 1"
    assert job.window_start.tzinfo is not None
    assert job.window_end.tzinfo is not None

    assert len(bundle.engineers) == 1
    assert len(bundle.equipment) == 1
    assert len(bundle.travel_matrix) == 1

    assert bundle.errors == []


def test_load_input_directory_skips_rows_with_import_errors(tmp_path):
    (tmp_path / "Восток Синтетические данные.csv").write_text(
        "ID;Адрес;Тип заявки BK\n"
        "1002;Адрес клиента;Неизвестный тип\n",
        encoding="cp1251",
    )
    (tmp_path / "engineers.json").write_text(ENGINEERS_JSON, encoding="utf-8")
    (tmp_path / "equipment.json").write_text(EQUIPMENT_JSON, encoding="utf-8")
    (tmp_path / "travel_matrix.json").write_text(TRAVEL_MATRIX_JSON, encoding="utf-8")

    bundle = load_input_directory(tmp_path)

    assert bundle.jobs == []

    codes = [error.code for error in bundle.errors]

    assert "UNKNOWN_WORK_TYPE_MAPPING" in codes


def test_load_input_directory_raises_when_engineers_missing(tmp_path):
    (tmp_path / "Восток Синтетические данные.csv").write_text(
        CSV_HEADER + VALID_ROW,
        encoding="cp1251",
    )
    (tmp_path / "equipment.json").write_text(EQUIPMENT_JSON, encoding="utf-8")
    (tmp_path / "travel_matrix.json").write_text(TRAVEL_MATRIX_JSON, encoding="utf-8")

    with pytest.raises(FileNotFoundError):
        load_input_directory(tmp_path)