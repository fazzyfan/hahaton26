import json

import pytest

from src.cli import main


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


def test_cli_plan_writes_plan_json(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    _write_input_files(input_dir)

    output_path = tmp_path / "output" / "plan.json"

    exit_code = main(
        [
            "plan",
            "--input-dir",
            str(input_dir),
            "--output",
            str(output_path),
        ]
    )

    assert exit_code == 0
    assert output_path.exists()

    plan = json.loads(output_path.read_text(encoding="utf-8"))

    assert set(plan) >= {"assignments", "routes", "unassigned_job_ids", "status"}
    assert plan["unassigned_job_ids"] == ["1001"]


def test_cli_requires_subcommand():
    with pytest.raises(SystemExit) as exc_info:
        main([])

    assert exc_info.value.code == 2