from src.matrix.database import MatrixDatabase
from src.models.entities import TravelMatrixEntry
from src.models.enums import TransportType


class TravelMatrixService:
    """Предоставляет удобный доступ к матрице поездок."""

    def __init__(self, database: MatrixDatabase):
        self.database = database

    def get_travel(
        self,
        origin_location_id: str,
        destination_location_id: str,
        transport_type: TransportType,
    ) -> TravelMatrixEntry | None:
        """Возвращает информацию о поездке."""

        result = self.database.get_travel(
            origin_location_id,
            destination_location_id,
            transport_type.value,
        )

        if result is None:
            return None

        travel_min, distance_km, matrix_version = result

        return TravelMatrixEntry(
            origin_location_id=origin_location_id,
            destination_location_id=destination_location_id,
            transport_type=transport_type,
            travel_min=travel_min,
            distance_km=distance_km,
            matrix_version=matrix_version,
        )