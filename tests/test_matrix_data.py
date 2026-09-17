from src.matrix.database import MatrixDatabase
from src.matrix.demo_data import create_demo_database


def test_demo_database_contains_locations(tmp_path):
    db_path = tmp_path / "demo.sqlite"

    create_demo_database(str(db_path))

    database = MatrixDatabase(db_path)

    with database.connect() as connection:
        rows = connection.execute(
            "SELECT location_id FROM locations"
        ).fetchall()

    location_ids = {row[0] for row in rows}

    assert location_ids == {
        "DEPOT",
        "LOC-A",
        "LOC-B",
        "LOC-C",
        "LOC-D",
        "LOC-E",
    }


def test_demo_database_contains_travel_matrix(tmp_path):
    db_path = tmp_path / "demo.sqlite"

    create_demo_database(str(db_path))

    database = MatrixDatabase(db_path)

    with database.connect() as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM travel_matrix"
        ).fetchone()[0]

    assert count == 30


def test_travel_is_directional(tmp_path):
    db_path = tmp_path / "demo.sqlite"

    create_demo_database(str(db_path))

    database = MatrixDatabase(db_path)

    with database.connect() as connection:
        forward = connection.execute(
            """
            SELECT travel_min
            FROM travel_matrix
            WHERE origin_location_id = ?
              AND destination_location_id = ?
              AND transport_type = ?
            """,
            ("DEPOT", "LOC-A", "CAR"),
        ).fetchone()

        backward = connection.execute(
            """
            SELECT travel_min
            FROM travel_matrix
            WHERE origin_location_id = ?
              AND destination_location_id = ?
              AND transport_type = ?
            """,
            ("LOC-A", "DEPOT", "CAR"),
        ).fetchone()

    assert forward[0] == 15
    assert backward[0] == 17