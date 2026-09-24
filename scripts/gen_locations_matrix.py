"""Генератор locations.json и направленной travel_matrix.json.

Читает официальные CSV из data/input, присваивает каждому адресу и офису
детерминированный location_id и строит полную направленную матрицу
перемещений для CAR / TRUCK / MOTORCYCLE.

Матрица СИНТЕТИЧЕСКАЯ (детерминированная): координаты точки вычисляются
хешем адреса, время = расстояние / средняя скорость по Манхэттену.
A->B может отличаться от B->A. Реальный маршрутизатор можно подключить
позже, заменив этот генератор.

Утилита воспроизводима: одинаковые входы -> одинаковые файлы.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
from io import StringIO
from pathlib import Path

INPUT_DIR = Path("data/input")
MATRIX_VERSION = "synth-official-v1"
KM_PER_UNIT = 0.02

OFFICE_LOCATIONS = {
    "Восток": ("OFFICE_VOSTOK", "г. Москва, ул Юных Ленинцев, д 83с 4"),
    "Юго-восток": ("OFFICE_YUGO_VOSTOK", "г. Москва, ул Бирюлёвская, д 1к1"),
    "Югоцентр": ("OFFICE_YUGO_CENTER", "г.Москва проезд Симферопольский, д.7"),
}

TRANSPORT_PROFILES = {
    "CAR": {"speed_kmh": 30.0, "reverse_factor": 1.10},
    "TRUCK": {"speed_kmh": 24.0, "reverse_factor": 1.08},
    "MOTORCYCLE": {"speed_kmh": 35.0, "reverse_factor": 1.05},
}


def _position(location_id: str) -> tuple[int, int]:
    digest = hashlib.md5(location_id.encode("utf-8")).hexdigest()
    value = int(digest[:8], 16)
    return value % 1000, (value // 1000) % 1000


def _collect_addresses() -> tuple[dict[str, str], list[str]]:
    """Возвращает (адрес -> location_id, список офисных адресов по зонам)."""
    addresses: dict[str, str] = {}
    offices: list[str] = []

    for zone, (office_id, office_address) in OFFICE_LOCATIONS.items():
        addresses.setdefault(office_address, office_id)

    for name in sorted(os.listdir(INPUT_DIR)):
        if not name.endswith("Синтетические данные.csv"):
            continue

        zone = name.replace(" Синтетические данные.csv", "").strip()

        with open(INPUT_DIR / name, encoding="cp1251") as file:
            text = file.read()

        reader = csv.reader(StringIO(text), delimiter=";")
        headers = next(reader)

        if "Адрес" not in headers:
            raise SystemExit(f"Нет колонки Адрес в {name}")

        address_index = headers.index("Адрес")
        office_id, office_address = OFFICE_LOCATIONS[zone]

        for values in reader:
            if not any(cell.strip() for cell in values):
                continue

            first_cell = values[0].strip().lower()

            if first_cell.startswith("адрес офиса"):
                offices.append(office_address)
                addresses[office_address] = office_id
                continue

            address = values[address_index].strip()

            if address:
                addresses.setdefault(address, None)

    # Детерминированные ID для адресов (офисы уже имеют фиксированные ID).
    counter = 1

    for address in sorted(addresses):
        if addresses[address] is None:
            addresses[address] = f"LOC-{counter:05d}"
            counter += 1

    return addresses, offices


def _build_locations(addresses: dict[str, str]) -> list[dict]:
    return [
        {"address": address, "location_id": location_id}
        for address, location_id in addresses.items()
    ]


def _travel_entries(addresses: dict[str, str]) -> list[dict]:
    location_ids = sorted(addresses.values())
    positions = {
        location_id: _position(location_id)
        for location_id in location_ids
    }

    entries: list[dict] = []

    for origin in location_ids:
        x1, y1 = positions[origin]

        for destination in location_ids:
            if origin == destination:
                continue

            x2, y2 = positions[destination]
            manhattan = abs(x1 - x2) + abs(y1 - y2)
            distance_km = round(manhattan * KM_PER_UNIT, 1)

            for transport_type, profile in TRANSPORT_PROFILES.items():
                travel_min = max(
                    5,
                    round(distance_km / profile["speed_kmh"] * 60),
                )
                reverse_min = max(
                    5,
                    round(travel_min * profile["reverse_factor"]),
                )

                entries.append(
                    {
                        "origin": origin,
                        "destination": destination,
                        "transport_type": transport_type,
                        "travel_min": travel_min,
                        "distance_km": distance_km,
                        "matrix_version": MATRIX_VERSION,
                    }
                )
                entries.append(
                    {
                        "origin": destination,
                        "destination": origin,
                        "transport_type": transport_type,
                        "travel_min": reverse_min,
                        "distance_km": distance_km,
                        "matrix_version": MATRIX_VERSION,
                    }
                )

    return entries


def main() -> None:
    addresses, offices = _collect_addresses()

    locations_path = INPUT_DIR / "locations.json"
    matrix_path = INPUT_DIR / "travel_matrix.json"

    locations_path.write_text(
        json.dumps(_build_locations(addresses), ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )

    entries = _travel_entries(addresses)
    matrix_path.write_text(
        json.dumps(entries, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )

    print(
        f"locations: {len(addresses)} "
        f"(offices: {len(offices)}) "
        f"matrix entries: {len(entries)} -> {matrix_path}"
    )


if __name__ == "__main__":
    main()