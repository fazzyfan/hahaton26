from __future__ import annotations

from src.models.entities import TravelMatrixEntry
from src.models.enums import TransportType

MatrixKey = tuple[str, str, TransportType]


class TravelMatrix:
    """
    Быстрый lookup времени/дистанции по направленной паре локаций
    и типу транспорта.

    Отсутствующая пара возвращает None — никакого выдуманного
    нулевого времени (причина NO_TRAVEL_DATA).
    """

    def __init__(self, entries: list[TravelMatrixEntry]) -> None:
        self._entries: dict[MatrixKey, TravelMatrixEntry] = {}

        for entry in entries:
            key = (
                entry.origin_location_id,
                entry.destination_location_id,
                entry.transport_type,
            )
            self._entries[key] = entry

    def find(
        self,
        origin: str,
        destination: str,
        transport_type: TransportType,
    ) -> TravelMatrixEntry | None:
        return self._entries.get(
            (origin, destination, transport_type)
        )

    def travel_min(
        self,
        origin: str,
        destination: str,
        transport_type: TransportType,
    ) -> int | None:
        # Переезд между одинаковыми точками равен нулю,
        # отдельная запись в матрице не требуется.
        if origin == destination:
            return 0

        entry = self.find(origin, destination, transport_type)

        if entry is None:
            return None

        return entry.travel_min