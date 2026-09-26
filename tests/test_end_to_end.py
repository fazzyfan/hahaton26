import json

from src.cli import main

# Окна заданы с запасом: работа должна ЗАВЕРШАТЬСЯ внутри окна
# (planned_end <= window_end), а не только начинаться в нём.
CSV_TEXT = (
    "ID;Адрес;Тип заявки BK;Начало окна;Конец окна\n"
    "1001;Ростов-на-Дону, ул. Ленина, 1;Подключение;20.09.2026 10:00;20.09.2026 14:00\n"
    "1002;Ростов-на-Дону, ул. Ленина, 1;Глобальная проблема;20.09.2026 09:30;20.09.2026 13:00\n"
)

ENGINEERS_JSON = """\
[
  {
    "id": "ENG-1",
    "name": "Иван Петров",
    "transport_type": "CAR",
    "qualifications": ["ELECTRIC"],
    "start_location": "DEPOT",
    "shift_start": "2026-09-20T09:00:00+03:00",
    "shift_end": "2026-09-20T18:00:00+03:00",
    "equipment": ["EQ-OPTIC", "INSTALLATION_KIT", "DIAGNOSTIC_KIT"],
    "service_districts": ["Восток"],
    "allowed_work_types": ["CONNECTION", "EMERGENCY"]
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
  {"origin": "DEPOT", "destination": "LOC-A", "transport_type": "CAR", "travel_min": 10, "distance_km": 5.0, "matrix_version": "e2e-v1"},
  {"origin": "LOC-A", "destination": "DEPOT", "transport_type": "CAR", "travel_min": 10, "distance_km": 5.0, "matrix_version": "e2e-v1"}
]
"""

LOCATIONS_JSON = """\
[
  {"address": "Ростов-на-Дону, ул. Ленина, 1", "location_id": "LOC-A"}
]
"""


def _write_input_files(tmp_path) -> None:
    (tmp_path / "Восток Синтетические данные.csv").write_text(
        CSV_TEXT,
        encoding="cp1251",
    )
    (tmp_path / "engineers.json").write_text(ENGINEERS_JSON, encoding="utf-8")
    (tmp_path / "equipment.json").write_text(EQUIPMENT_JSON, encoding="utf-8")
    (tmp_path / "travel_matrix.json").write_text(
        TRAVEL_MATRIX_JSON,
        encoding="utf-8",
    )
    (tmp_path / "locations.json").write_text(LOCATIONS_JSON, encoding="utf-8")


def test_end_to_end_csv_to_plan_json(tmp_path):
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

    plan = json.loads(output_path.read_text(encoding="utf-8"))

    # Обе заявки назначены, статус VALID, неназначенных нет.
    assert plan["status"] == "VALID"
    assert len(plan["assignments"]) == 2
    assert plan["unassigned"] == []
    assert len(plan["routes"]) == 1

    route = plan["routes"][0]

    assert route["engineer_id"] == "ENG-1"

    stop_job_ids = [stop["job_id"] for stop in route["stops"]]

    # EMERGENCY имеет приоритет над CONNECTION.
    assert stop_job_ids == ["1002", "1001"]

    first_stop = route["stops"][0]

    assert first_stop["location_id"] == "LOC-A"
    assert first_stop["address"] == "Ростов-на-Дону, ул. Ленина, 1"
    assert first_stop["planned_start"]
    assert first_stop["planned_end"]