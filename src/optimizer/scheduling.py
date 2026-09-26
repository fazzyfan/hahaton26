from __future__ import annotations

from datetime import timedelta

from src.models.entities import Engineer, JobRecord, RouteStop
from src.models.enums import UnassignmentReason
from src.optimizer.travel import TravelMatrix

# Статусы, исключаемые из активного планирования.
INACTIVE_STATUSES = {"COMPLETED", "CANCELLED"}


def is_active(job: JobRecord) -> bool:
    """Заявки COMPLETED/CANCELLED не участвуют в активном планировании."""
    return job.status not in INACTIVE_STATUSES


def is_compatible(job: JobRecord, engineer: Engineer) -> bool:
    """Проверяет базовую совместимость заявки и бригады."""
    if (
        engineer.service_districts
        and job.service_zone not in engineer.service_districts
    ):
        return False

    if (
        engineer.allowed_work_types
        and job.work_type not in engineer.allowed_work_types
    ):
        return False

    if (
        job.required_transport_type is not None
        and engineer.transport_type != job.required_transport_type
    ):
        return False

    if job.required_equipment and not set(job.required_equipment).issubset(
        set(engineer.equipment_ids)
    ):
        return False

    return True


def empty_route_reason(
    travel: TravelMatrix,
    job: JobRecord,
    engineers: list[Engineer],
) -> UnassignmentReason | None:
    """
    Проверяет выполнимость заявки на пустом маршруте
    (без учёта уже заполненных смен).

    None — хотя бы одна совместимая бригада может выполнить заявку;
    иначе — наиболее точная причина. SHIFT_CONFLICT возвращается только
    когда ВСЕ совместимые бригады упираются именно в смену.
    """
    reasons: set[UnassignmentReason] = set()

    for engineer in engineers:
        _, reason = schedule_route(travel, [job], engineer)

        if reason is None:
            return None

        reasons.add(reason)

    if reasons == {UnassignmentReason.NO_TRAVEL_DATA}:
        return UnassignmentReason.NO_TRAVEL_DATA

    if reasons == {UnassignmentReason.SHIFT_CONFLICT}:
        return UnassignmentReason.SHIFT_CONFLICT

    if UnassignmentReason.NO_TIME_WINDOW in reasons:
        return UnassignmentReason.NO_TIME_WINDOW

    # Смешанные причины (часть бригад — смена, часть — окно и т.п.).
    return UnassignmentReason.NO_FEASIBLE_INSERTION


def schedule_route(
    travel: TravelMatrix,
    jobs: list[JobRecord],
    engineer: Engineer,
) -> tuple[list[RouteStop] | None, UnassignmentReason | None]:
    """
    Считает времена остановок маршрута для одной бригады.

    Возвращает (stops, None) при успехе либо (None, причина) при первом
    нарушении hard constraint:

        * NO_TRAVEL_DATA — нет данных о времени пути;
        * SHIFT_CONFLICT  — бригада физически не может доехать/закончить
                            работу в пределах своей смены;
        * NO_TIME_WINDOW  — начало или окончание работы выходит за окно
                            обслуживания клиента.

    Правило окна: работа должна не только начаться внутри окна, но и
    ЗАВЕРШИТЬСЯ не позже window_end (planned_end <= window_end).
    Окончание ровно на границе окна допустимо.
    """
    stops: list[RouteStop] = []
    cursor = engineer.shift_start
    prev_location = engineer.start_location_id

    for job in jobs:
        travel_min = travel.travel_min(
            prev_location,
            job.location_id,
            engineer.transport_type,
        )

        if travel_min is None:
            return None, UnassignmentReason.NO_TRAVEL_DATA

        arrival = cursor + timedelta(minutes=travel_min)

        if arrival > engineer.shift_end:
            return None, UnassignmentReason.SHIFT_CONFLICT

        if job.window_start is not None:
            start = max(arrival, job.window_start)
        else:
            start = arrival

        if job.window_end is not None and start > job.window_end:
            return None, UnassignmentReason.NO_TIME_WINDOW

        end = start + timedelta(minutes=job.service_duration_min)

        # Работа должна завершиться внутри клиентского окна.
        if job.window_end is not None and end > job.window_end:
            return None, UnassignmentReason.NO_TIME_WINDOW

        if end > engineer.shift_end:
            return None, UnassignmentReason.SHIFT_CONFLICT

        stops.append(
            RouteStop(
                job_id=job.id,
                location_id=job.location_id,
                planned_arrival=arrival,
                planned_start=start,
                planned_end=end,
                address=job.address,
            )
        )

        cursor = end
        prev_location = job.location_id

    return stops, None


def total_travel_min(
    travel: TravelMatrix,
    jobs: list[JobRecord],
    engineer: Engineer,
) -> int:
    """Суммарное время в пути по маршруту (в минутах)."""
    total = 0
    prev_location = engineer.start_location_id

    for job in jobs:
        travel_min = travel.travel_min(
            prev_location,
            job.location_id,
            engineer.transport_type,
        )

        if travel_min is None:
            return 0

        total += travel_min
        prev_location = job.location_id

    return total


def total_distance_km(
    travel: TravelMatrix,
    jobs: list[JobRecord],
    engineer: Engineer,
) -> float:
    """Суммарное расстояние по маршруту (в км)."""
    total = 0.0
    prev_location = engineer.start_location_id

    for job in jobs:
        if prev_location == job.location_id:
            continue

        entry = travel.find(
            prev_location,
            job.location_id,
            engineer.transport_type,
        )

        if entry is None:
            return 0.0

        total += entry.distance_km
        prev_location = job.location_id

    return total