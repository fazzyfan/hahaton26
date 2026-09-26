from __future__ import annotations

import json
from pathlib import Path

from src.models.entities import Engineer, Equipment, TravelMatrixEntry


def _load_json_array(path: str | Path) -> list[dict]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_engineers_file(path: str | Path) -> list[Engineer]:
    """
    Загружает синтетический справочник инженеров из engineers.json.

    JSON-контракт записи:
        id, name, transport_type, qualifications,
        start_location, shift_start, shift_end, equipment

    Контракт адаптируется к модели Engineer:
        start_location -> start_location_id
        equipment      -> equipment_ids
    """
    engineers = []

    for item in _load_json_array(path):
        engineer = Engineer(
            id=item["id"],
            name=item["name"],
            transport_type=item["transport_type"],
            qualifications=item.get("qualifications", []),
            start_location_id=item["start_location"],
            shift_start=item["shift_start"],
            shift_end=item["shift_end"],
            equipment_ids=item.get("equipment", []),
            service_districts=item.get("service_districts", []),
            allowed_work_types=item.get("allowed_work_types", []),
        )

        if (
            engineer.shift_start.tzinfo is None
            or engineer.shift_end.tzinfo is None
        ):
            raise ValueError(
                f"Смена инженера {engineer.id!r} "
                "должна быть с часовым поясом"
            )

        engineers.append(engineer)

    return engineers


def load_equipment_file(path: str | Path) -> list[Equipment]:
    """
    Загружает синтетический справочник оборудования из equipment.json.

    JSON-контракт записи:
        id, name, category
    """
    return [Equipment(**item) for item in _load_json_array(path)]


def load_locations_file(path: str | Path) -> dict[str, str]:
    """
    Загружает реестр адресов -> location_id из locations.json.

    JSON-контракт записи:
        address, location_id

    Полезно для обратной совместимости; для карты используйте
    load_locations_registry() — там есть широта и долгота.
    """
    locations: dict[str, str] = {}

    for item in _load_json_array(path):
        locations[item["address"]] = item["location_id"]

    return locations


def load_locations_registry(path: str | Path) -> list[dict]:
    """
    Загружает полный реестр локаций из locations.json.

    JSON-контракт записи:
        location_id, address, latitude, longitude

    Координаты нужны для карты маршрутов (pydeck) и для расчёта времени
    поездки по географии. Источник и точность координат фиксируются
    в README (MVP: документированная оценка по району + детерминированный
    сдвиг, офисы — реальные координаты).
    """
    registry: list[dict] = []

    for item in _load_json_array(path):
        registry.append(
            {
                "location_id": item["location_id"],
                "address": item.get("address", ""),
                "latitude": item.get("latitude"),
                "longitude": item.get("longitude"),
            }
        )

    return registry


def load_travel_matrix_file(path: str | Path) -> list[TravelMatrixEntry]:
    """
    Загружает travel matrix из travel_matrix.json.

    JSON-контракт записи:
        origin, destination, transport_type,
        travel_min, distance_km, matrix_version

    Контракт адаптируется к модели TravelMatrixEntry:
        origin      -> origin_location_id
        destination -> destination_location_id

    Уникальность ключа (origin, destination, transport_type,
    matrix_version) проверяется при загрузке ДО расчёта: дубликаты дают
    понятную ошибку вместо молчаливой перезаписи значений.
    """
    entries = []
    seen: set[tuple[str, str, str, str]] = set()

    for item in _load_json_array(path):
        key = (
            item["origin"],
            item["destination"],
            item["transport_type"],
            item["matrix_version"],
        )

        if key in seen:
            raise ValueError(
                "Дубликат записи матрицы перемещений: "
                f"{key[0]!r} -> {key[1]!r} / {key[2]!r} "
                f"(matrix_version {key[3]!r}). "
                "Каждая направленная пара должна встречаться ровно один раз."
            )

        seen.add(key)

        entries.append(
            TravelMatrixEntry(
                origin_location_id=item["origin"],
                destination_location_id=item["destination"],
                transport_type=item["transport_type"],
                travel_min=item["travel_min"],
                distance_km=item["distance_km"],
                matrix_version=item["matrix_version"],
            )
        )

    return entries