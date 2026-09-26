"""Генератор locations.json и направленной travel_matrix.json (MVP v2).

Читает официальные CSV из data/input, присваивает каждому адресу и офису
детерминированный location_id и строит полную направленную матрицу
перемещений для CAR / WALK / BICYCLE / PUBLIC_TRANSPORT.

География (источник и точность зафиксированы):
    * офисы — РЕАЛЬНЫЕ координаты Москвы (приблизительные, ~1 км точности,
      по публичным данным районов города);
    * адреса заявок — документированная ОЦЕНКА: базовая точка района +
      детерминированный сдвиг (±0.012° широты / ±0.015° долготы, ~1.5 км),
      вычисляемый хешем адреса. Такая оценка даёт «похожие адреса — рядом»,
      а одинаковые входы — одинаковые координаты;
    * адреса городов Московской области (Кашира, Домодедово, Ступино) —
      ОЦЕНОЧНАЯ точка центра города по публичным данным (точность ~1-2 км),
      адрес размещается около своего города тем же детерминированным сдвигом.
      Город определяется по названию в адресе (подстрока).

Матрица (оценка времени по координатам и типу транспорта):
    * расстояние — гаверсинус по координатам;
    * CAR — средняя городская скорость 28 км/ч;
    * WALK — 4.5 км/ч;
    * BICYCLE — 12 км/ч;
    * PUBLIC_TRANSPORT — УСРЕДНЁННАЯ модель: детур-фактор 1.3,
      средняя скорость 20 км/ч + фиксированные 10 минут на ожидание.
    * A->B может отличаться от B->A (обратный коэффициент 1.05-1.10).

Каждая НАПРАВЛЕННАЯ пара (origin, destination, transport_type) генерируется
ровно один раз — дубликатов ключей нет.

Утилита воспроизводима: одинаковые входы -> одинаковые файлы.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import os
from io import StringIO
from pathlib import Path

INPUT_DIR = Path("data/input")
# v2: добавлены оценочные точки городов Подмосковья (Кашира, Домодедово,
# Ступино) — адреса этих городов больше не «стягиваются» к базовой точке
# района (Москва), а размещаются около своего города.
MATRIX_VERSION = "geo-v2"

# Реальные (приблизительные) координаты офисов, взятые по публичным данным
# районов Москвы. Точность ~1 км; при наличии точного геокодера заменить.
OFFICE_LOCATIONS = {
    "Восток": (
        "OFFICE_VOSTOK",
        "г. Москва, ул Юных Ленинцев, д 83с 4",
        55.7025,
        37.7745,
    ),
    "Юго-восток": (
        "OFFICE_YUGO_VOSTOK",
        "г. Москва, ул Бирюлёвская, д 1к1",
        55.5850,
        37.6710,
    ),
    "Югоцентр": (
        "OFFICE_YUGO_CENTER",
        "г.Москва проезд Симферопольский, д.7",
        55.6470,
        37.6100,
    ),
}

# Базовые точки районов (центр района) для оценки координат адресов.
DISTRICT_BASES = {
    "Восток": (55.7200, 37.8000),
    "Юго-восток": (55.6500, 37.7500),
    "Югоцентр": (55.6300, 37.6200),
}

# Оценочные точки городов Московской области (центр города, публичные
# данные, точность ~1-2 км). Адреса, содержащие название города,
# размещаются около этой точки.
CITY_BASES = {
    "Домодедово": (55.4367, 37.7667),
    "Кашира": (54.8536, 38.1533),
    "Ступино": (54.9008, 38.0689),
}


def _detect_city_base(address: str) -> tuple[float, float] | None:
    """Возвращает координаты города по названию в адресе или None."""
    lowered = address.lower()

    for city, coords in CITY_BASES.items():
        if city.lower() in lowered:
            return coords

    return None

JITTER_LAT = 0.012   # ~1.3 км
JITTER_LON = 0.015   # ~1.0 км

TRANSPORT_PROFILES = {
    "CAR": {"speed_kmh": 28.0, "reverse_factor": 1.10, "min_min": 5},
    "WALK": {"speed_kmh": 4.5, "reverse_factor": 1.02, "min_min": 5},
    "BICYCLE": {"speed_kmh": 12.0, "reverse_factor": 1.05, "min_min": 5},
    # Усреднённая модель общественного транспорта: детур 1.3,
    # средняя скорость 20 км/ч, +10 мин на ожидание/пересадки.
    "PUBLIC_TRANSPORT": {
        "speed_kmh": 20.0,
        "reverse_factor": 1.08,
        "min_min": 5,
        "detour": 1.3,
        "fixed_min": 10,
    },
}


def _haversine_km(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
    radius = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)

    value = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )

    return 2 * radius * math.asin(math.sqrt(value))


def _jitter(address: str) -> tuple[float, float]:
    digest = hashlib.md5(address.encode("utf-8")).hexdigest()
    value = int(digest[:8], 16)

    lat_offset = (value % 10000) / 10000 * 2 - 1
    lon_offset = ((value // 10000) % 10000) / 10000 * 2 - 1

    return lat_offset * JITTER_LAT, lon_offset * JITTER_LON


def _collect_addresses() -> dict[str, dict]:
    """Возвращает {address: {location_id, latitude, longitude}}."""
    registry: dict[str, dict] = {}

    for zone, (office_id, office_address, lat, lon) in (
        OFFICE_LOCATIONS.items()
    ):
        registry[office_address] = {
            "location_id": office_id,
            "latitude": lat,
            "longitude": lon,
        }

    for name in sorted(os.listdir(INPUT_DIR)):
        if not name.endswith("Синтетические данные.csv"):
            continue

        zone = name.replace(" Синтетические данные.csv", "").strip()
        default_lat, default_lon = DISTRICT_BASES.get(
            zone,
            (55.7000, 37.6500),
        )

        with open(INPUT_DIR / name, encoding="cp1251") as file:
            text = file.read()

        reader = csv.reader(StringIO(text), delimiter=";")
        headers = next(reader)

        if "Адрес" not in headers:
            raise SystemExit(f"Нет колонки Адрес в {name}")

        address_index = headers.index("Адрес")

        for values in reader:
            if not any(cell.strip() for cell in values):
                continue

            first_cell = values[0].strip().lower()

            if first_cell.startswith("адрес офиса"):
                continue

            address = values[address_index].strip()

            if not address:
                continue

            if address in registry:
                continue

            city_base = _detect_city_base(address)

            if city_base is not None:
                base_lat, base_lon = city_base
            else:
                base_lat, base_lon = default_lat, default_lon

            d_lat, d_lon = _jitter(address)
            registry[address] = {
                "location_id": None,
                "latitude": round(base_lat + d_lat, 6),
                "longitude": round(base_lon + d_lon, 6),
            }

    # Детерминированные ID для адресов (офисы уже имеют фиксированные ID).
    counter = 1

    for address in sorted(registry):
        if registry[address]["location_id"] is None:
            registry[address]["location_id"] = f"LOC-{counter:05d}"
            counter += 1

    return registry


def _build_locations(registry: dict[str, dict]) -> list[dict]:
    return [
        {
            "location_id": item["location_id"],
            "address": address,
            "latitude": item["latitude"],
            "longitude": item["longitude"],
        }
        for address, item in sorted(
            registry.items(),
            key=lambda pair: pair[1]["location_id"],
        )
    ]


def _travel_entries(registry: dict[str, dict]) -> list[dict]:
    items = list(registry.values())
    position = {
        item["location_id"]: (item["latitude"], item["longitude"])
        for item in items
    }
    location_ids = sorted(position)

    entries: list[dict] = []

    # Перебираем НЕУПОРЯДОЧЕННЫЕ пары один раз и добавляем оба направления.
    for i, origin in enumerate(location_ids):
        lat1, lon1 = position[origin]

        for destination in location_ids[i + 1:]:
            lat2, lon2 = position[destination]
            distance_km = round(_haversine_km(lat1, lon1, lat2, lon2), 1)

            for transport_type, profile in TRANSPORT_PROFILES.items():
                detour = profile.get("detour", 1.0)
                fixed = profile.get("fixed_min", 0)
                effective = distance_km * detour

                travel_min = max(
                    profile["min_min"],
                    round(effective / profile["speed_kmh"] * 60 + fixed),
                )
                reverse_min = max(
                    profile["min_min"],
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
    registry = _collect_addresses()

    locations_path = INPUT_DIR / "locations.json"
    matrix_path = INPUT_DIR / "travel_matrix.json"

    locations_path.write_text(
        json.dumps(_build_locations(registry), ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )

    entries = _travel_entries(registry)
    matrix_path.write_text(
        json.dumps(entries, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )

    offices = sum(
        1 for item in registry.values() if str(item["location_id"]).startswith("OFFICE")
    )

    print(
        f"locations: {len(registry)} (offices: {offices}) "
        f"matrix entries: {len(entries)} -> {matrix_path}"
    )


if __name__ == "__main__":
    main()