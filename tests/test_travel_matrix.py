from src.models.entities import TravelMatrixEntry
from src.models.enums import TransportType
from src.optimizer.travel import TravelMatrix


def _entry(
    origin: str,
    destination: str,
    transport_type: TransportType,
    travel_min: int = 10,
) -> TravelMatrixEntry:
    return TravelMatrixEntry(
        origin_location_id=origin,
        destination_location_id=destination,
        transport_type=transport_type,
        travel_min=travel_min,
        distance_km=5.0,
        matrix_version="synth-v1",
    )


def test_travel_matrix_finds_entry_by_all_keys():
    matrix = TravelMatrix(
        [
            _entry("DEPOT", "LOC-A", TransportType.CAR, travel_min=15),
            _entry("LOC-A", "DEPOT", TransportType.CAR, travel_min=17),
        ]
    )

    assert matrix.travel_min("DEPOT", "LOC-A", TransportType.CAR) == 15
    assert matrix.travel_min("LOC-A", "DEPOT", TransportType.CAR) == 17


def test_travel_matrix_respects_transport_type():
    matrix = TravelMatrix(
        [_entry("DEPOT", "LOC-A", TransportType.CAR, travel_min=15)]
    )

    assert matrix.travel_min("DEPOT", "LOC-A", TransportType.CAR) == 15
    assert matrix.travel_min("DEPOT", "LOC-A", TransportType.WALK) is None


def test_travel_matrix_missing_pair_returns_none():
    matrix = TravelMatrix(
        [_entry("DEPOT", "LOC-A", TransportType.CAR)]
    )

    assert matrix.travel_min("LOC-A", "DEPOT", TransportType.CAR) is None
    assert matrix.travel_min("DEPOT", "LOC-B", TransportType.CAR) is None


def test_travel_matrix_find_returns_full_entry():
    matrix = TravelMatrix(
        [_entry("DEPOT", "LOC-A", TransportType.CAR, travel_min=15)]
    )

    entry = matrix.find("DEPOT", "LOC-A", TransportType.CAR)

    assert entry is not None
    assert entry.distance_km == 5.0
    assert entry.matrix_version == "synth-v1"


def test_travel_matrix_same_location_is_zero_without_entry():
    matrix = TravelMatrix([])

    assert matrix.travel_min("LOC-A", "LOC-A", TransportType.CAR) == 0