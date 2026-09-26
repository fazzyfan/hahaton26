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

    Дубликаты ключа (origin, destination, transport_type) запрещены:
    повторная запись с другим временем означала бы молчаливую перезапись
    значений, поэтому при загрузке выбрасывается ValueError.
    """

    def __init__(self, entries: list[TravelMatrixEntry]) -> None:
        self._entries: dict[MatrixKey, TravelMatrixEntry] = {}

        for entry in entries:
            key = (
                entry.origin_location_id,
                entry.destination_location_id,
                entry.transport_type,
            )

            if key in self._entries:
                previous = self._entries[key]

                raise ValueError(
                    "Дубликат записи матрицы перемещений: "
                    f"{entry.origin_location_id!r} -> "
                    f"{entry.destination_location_id!r} / "
                    f"{entry.transport_type.value!r} "
                    f"(matrix_version {previous.matrix_version!r} и "
                    f"{entry.matrix_version!r})"
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