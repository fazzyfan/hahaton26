import pytest

from src.importers.json_inputs import (
    load_engineers_file,
    load_equipment_file,
    load_locations_file,
    load_travel_matrix_file,
)
from src.models.entities import Equipment, TravelMatrixEntry
from src.models.enums import Skill, TransportType


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
    "equipment": ["EQ-OPTIC", "EQ-SPLICE"]
  }
]
"""

EQUIPMENT_JSON = """\
[
  {"id": "EQ-OPTIC", "name": "Оптический тестер", "category": "measurement"},
  {"id": "EQ-SPLICE", "name": "Сварочный аппарат", "category": "installation"}
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
    "matrix_version": "v1"
  }
]
"""


def test_load_engineers_file_maps_json_contract_to_model(tmp_path):
    path = tmp_path / "engineers.json"
    path.write_text(ENGINEERS_JSON, encoding="utf-8")

    engineers = load_engineers_file(path)

    assert len(engineers) == 1

    engineer = engineers[0]

    assert engineer.id == "ENG-1"
    assert engineer.name == "Иван Петров"
    assert engineer.transport_type == TransportType.CAR
    assert engineer.qualifications == [Skill.ELECTRIC, Skill.NETWORK]
    assert engineer.start_location_id == "DEPOT"
    assert engineer.equipment_ids == ["EQ-OPTIC", "EQ-SPLICE"]

    assert engineer.shift_start.tzinfo is not None
    assert engineer.shift_start.hour == 9
    assert engineer.shift_end.hour == 18


def test_load_engineers_file_rejects_naive_shift_datetime(tmp_path):
    payload = ENGINEERS_JSON.replace(
        "2026-09-20T09:00:00+03:00",
        "2026-09-20T09:00:00",
    )
    path = tmp_path / "engineers.json"
    path.write_text(payload, encoding="utf-8")

    with pytest.raises(ValueError):
        load_engineers_file(path)


def test_load_equipment_file_returns_equipment_models(tmp_path):
    path = tmp_path / "equipment.json"
    path.write_text(EQUIPMENT_JSON, encoding="utf-8")

    equipment = load_equipment_file(path)

    assert len(equipment) == 2
    assert isinstance(equipment[0], Equipment)
    assert equipment[0].id == "EQ-OPTIC"
    assert equipment[0].name == "Оптический тестер"
    assert equipment[1].category == "installation"


def test_load_travel_matrix_file_maps_json_contract_to_model(tmp_path):
    path = tmp_path / "travel_matrix.json"
    path.write_text(TRAVEL_MATRIX_JSON, encoding="utf-8")

    entries = load_travel_matrix_file(path)

    assert len(entries) == 1

    entry = entries[0]

    assert isinstance(entry, TravelMatrixEntry)
    assert entry.origin_location_id == "DEPOT"
    assert entry.destination_location_id == "LOC-A"
    assert entry.transport_type == TransportType.CAR
    assert entry.travel_min == 15
    assert entry.distance_km == 8.5
    assert entry.matrix_version == "v1"


LOCATIONS_JSON = """\
[
  {"address": "Ростов-на-Дону, ул. Ленина, 1", "location_id": "LOC-A"}
]
"""


def test_load_locations_file_returns_address_to_location_map(tmp_path):
    path = tmp_path / "locations.json"
    path.write_text(LOCATIONS_JSON, encoding="utf-8")

    locations = load_locations_file(path)

    assert locations == {"Ростов-на-Дону, ул. Ленина, 1": "LOC-A"}