"""Построение карты маршрута бригады через pydeck.

Точки остановок — ScatterplotLayer, линия в порядке посещения — PathLayer.
Линия соединяет координаты напрямую, поэтому под картой выводится
подпись «Схематический маршрут».
"""
from __future__ import annotations

import pydeck as pdk

# Жёлтый акцент интерфейса (точки) и тёмный цвет линии.
POINT_FILL = [245, 197, 24]
POINT_STROKE = [26, 26, 26]
LINE_COLOR = [26, 26, 26]


def _location_coords(
    locations: list[dict],
    location_id: str,
) -> tuple[float, float] | None:
    for item in locations:
        if item.get("location_id") == location_id:
            latitude = item.get("latitude")
            longitude = item.get("longitude")

            if latitude is None or longitude is None:
                return None

            return float(latitude), float(longitude)

    return None


def build_route_deck(
    locations: list[dict],
    route_points: list[dict],
) -> pdk.Deck | None:
    """
    Строит карту маршрута.

    route_points: список словарей вида
        {"location_id", "label", "is_start"} в порядке посещения,
        включая стартовую точку офиса.

    Возвращает None, если для маршрута нет координат (карту показать
    нельзя).
    """
    resolved: list[dict] = []

    for point in route_points:
        coords = _location_coords(locations, point["location_id"])

        if coords is None:
            continue

        resolved.append(
            {
                "lat": coords[0],
                "lon": coords[1],
                "label": point.get("label", point["location_id"]),
                "is_start": point.get("is_start", False),
            }
        )

    if not resolved:
        return None

    scatter_data = [
        {
            "position": [item["lon"], item["lat"]],
            "label": item["label"],
            "radius": 140 if item["is_start"] else 90,
        }
        for item in resolved
    ]

    path_data = [
        {
            "path": [[item["lon"], item["lat"]] for item in resolved],
            "width": 3,
        }
    ]

    layers = [
        pdk.Layer(
            "PathLayer",
            data=path_data,
            get_path="path",
            get_color=LINE_COLOR,
            width_scale=4,
            width_min_pixels=2,
            rounded=True,
            pickable=False,
        ),
        pdk.Layer(
            "ScatterplotLayer",
            data=scatter_data,
            get_position="position",
            get_fill_color=POINT_FILL,
            get_line_color=POINT_STROKE,
            get_radius="radius",
            line_width_min_pixels=2,
            stroked=True,
            pickable=True,
            auto_highlight=True,
        ),
    ]

    first = resolved[0]

    view_state = pdk.ViewState(
        latitude=first["lat"],
        longitude=first["lon"],
        zoom=11,
        pitch=0,
    )

    return pdk.Deck(
        layers=layers,
        initial_view_state=view_state,
        tooltip={"html": "{label}", "style": {"color": "#1a1a1a"}},
        map_style="light",
    )