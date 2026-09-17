from src.matrix.database import MatrixDatabase
from src.matrix.demo_data import create_demo_database


def test_get_travel_returns_data(tmp_path):
    db_path = tmp_path / "demo.sqlite"

    create_demo_database(str(db_path))

    database = MatrixDatabase(db_path)

    result = database.get_travel(
        "DEPOT",
        "LOC-A",
        "CAR",
    )

    assert result is not None

    travel_min, distance_km, matrix_version = result

    assert travel_min == 15
    assert distance_km == 8.5
    assert matrix_version == "demo-v1"


def test_get_travel_respects_direction(tmp_path):
    db_path = tmp_path / "demo.sqlite"

    create_demo_database(str(db_path))

    database = MatrixDatabase(db_path)

    forward = database.get_travel(
        "DEPOT",
        "LOC-A",
        "CAR",
    )

    backward = database.get_travel(
        "LOC-A",
        "DEPOT",
        "CAR",
    )

    assert forward is not None
    assert backward is not None

    assert forward[0] == 15
    assert backward[0] == 17


def test_get_travel_returns_none_when_missing(tmp_path):
    db_path = tmp_path / "demo.sqlite"

    create_demo_database(str(db_path))

    database = MatrixDatabase(db_path)

    result = database.get_travel(
        "DEPOT",
        "LOC-A",
        "MOTORCYCLE",
    )

    assert result is None