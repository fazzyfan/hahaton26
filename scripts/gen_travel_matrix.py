"""Одноразовый генератор data/input/travel_matrix.json (синтетические данные).

Генерирует направленные пары DEPOT + LOC-A..LOC-F для CAR и TRUCK.
Время TRUCK = CAR * 1.3 (округлено), расстояния одинаковые.
"""
import json
from pathlib import Path

LOCATIONS = ["DEPOT", "LOC-A", "LOC-B", "LOC-C", "LOC-D", "LOC-E", "LOC-F"]

# CAR: время в минутах, дистанция в км (симметрично)
CAR_MIN = {
    ("DEPOT", "LOC-A"): (15, 8.5),
    ("DEPOT", "LOC-B"): (20, 10.2),
    ("DEPOT", "LOC-C"): (18, 9.1),
    ("DEPOT", "LOC-D"): (12, 6.7),
    ("DEPOT", "LOC-E"): (22, 11.5),
    ("DEPOT", "LOC-F"): (25, 13.0),
    ("LOC-A", "LOC-B"): (10, 5.2),
    ("LOC-A", "LOC-C"): (14, 7.0),
    ("LOC-A", "LOC-D"): (9, 4.5),
    ("LOC-A", "LOC-E"): (16, 8.0),
    ("LOC-A", "LOC-F"): (19, 9.5),
    ("LOC-B", "LOC-C"): (13, 6.5),
    ("LOC-B", "LOC-D"): (16, 8.0),
    ("LOC-B", "LOC-E"): (9, 4.8),
    ("LOC-B", "LOC-F"): (12, 6.2),
    ("LOC-C", "LOC-D"): (12, 6.0),
    ("LOC-C", "LOC-E"): (18, 9.0),
    ("LOC-C", "LOC-F"): (21, 10.5),
    ("LOC-D", "LOC-E"): (20, 10.0),
    ("LOC-D", "LOC-F"): (15, 7.6),
    ("LOC-E", "LOC-F"): (17, 8.6),
}


def truck_time(car_min: int) -> int:
    return round(car_min * 1.3)


entries = []

for (origin, destination), (car_min, distance_km) in CAR_MIN.items():
    for transport_type, travel_min in (
        ("CAR", car_min),
        ("TRUCK", truck_time(car_min)),
    ):
        entries.append(
            {
                "origin": origin,
                "destination": destination,
                "transport_type": transport_type,
                "travel_min": travel_min,
                "distance_km": distance_km,
                "matrix_version": "synth-v1",
            }
        )
        # Обратное направление с той же метрикой (синтетические данные).
        entries.append(
            {
                "origin": destination,
                "destination": origin,
                "transport_type": transport_type,
                "travel_min": travel_min,
                "distance_km": distance_km,
                "matrix_version": "synth-v1",
            }
        )

path = Path("data/input/travel_matrix.json")
path.write_text(
    json.dumps(entries, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)

print(f"entries: {len(entries)} -> {path}")