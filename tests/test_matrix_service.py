from src.matrix.database import MatrixDatabase
from src.matrix.demo_data import create_demo_database
from src.matrix.service import TravelMatrixService
from src.models.enums import TransportType


def test_service_returns_travel_entry(tmp_path):
    db_path = tmp_path / "demo.sqlite"

    create_demo_database(str(db_path))

    database = MatrixDatabase(db_path)
    service = TravelMatrixService(database)

    result = service.get_travel(
        "DEPOT",
        "LOC-A",
        TransportType.CAR,
    )

    assert result is not None

    assert result.origin_location_id == "DEPOT"
    assert result.destination_location_id == "LOC-A"
    assert result.transport_type == TransportType.CAR
    assert result.travel_min == 15
    assert result.distance_km == 8.5
    assert result.matrix_version == "demo-v1"


def test_service_returns_none_for_missing_route(tmp_path):
    db_path = tmp_path / "demo.sqlite"

    create_demo_database(str(db_path))

    database = MatrixDatabase(db_path)
    service = TravelMatrixService(database)

    result = service.get_travel(
        "DEPOT",
        "LOC-A",
        TransportType.MOTORCYCLE,
    )

    assert result is None