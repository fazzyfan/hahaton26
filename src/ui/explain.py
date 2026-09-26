"""Формирование объяснения назначения заявки бригаде.

Объяснение строится из РЕАЛЬНЫХ проверок, которые выполняет планировщик:
зона, тип работы, транспорт, оборудование, окно обслуживания, смена,
а также критерий выбора вставки (приоритет, дополнительный путь,
балансировка загрузки).
"""
from __future__ import annotations

from datetime import timedelta

from src.models.entities import Engineer, JobRecord, RouteStop
from src.optimizer.route_planner import (
    LOAD_BALANCE_PENALTY_MIN,
    WORK_TYPE_PRIORITY,
)
from src.optimizer.travel import TravelMatrix


def explain_assignment(
    job: JobRecord,
    engineer: Engineer,
    travel: TravelMatrix,
    stop: RouteStop | None = None,
    route_load: int = 0,
) -> list[dict]:
    """Возвращает список строк объяснения: {"status", "text"}."""
    lines: list[dict] = []

    # 1. Зона обслуживания.
    if job.service_zone in engineer.service_districts:
        lines.append(
            {
                "status": "ok",
                "text": (
                    f"Зона «{job.service_zone}» входит в зоны бригады "
                    f"({', '.join(engineer.service_districts)})"
                ),
            }
        )
    else:
        lines.append(
            {
                "status": "bad",
                "text": (
                    f"Зона «{job.service_zone}» НЕ входит в зоны бригады "
                    f"({', '.join(engineer.service_districts) or 'нет зон'})"
                ),
            }
        )

    # 2. Тип работы.
    if job.work_type in engineer.allowed_work_types:
        lines.append(
            {
                "status": "ok",
                "text": (
                    f"Тип работы «{job.work_type}» разрешён бригаде "
                    f"({', '.join(engineer.allowed_work_types)})"
                ),
            }
        )
    else:
        lines.append(
            {
                "status": "bad",
                "text": (
                    f"Тип работы «{job.work_type}» НЕ разрешён бригаде "
                    f"({', '.join(engineer.allowed_work_types) or 'нет типов'})"
                ),
            }
        )

    # 3. Транспорт.
    if job.required_transport_type is None:
        lines.append(
            {
                "status": "info",
                "text": (
                    f"Ограничений по транспорту нет "
                    f"(у бригады — {engineer.transport_type.value})"
                ),
            }
        )
    elif engineer.transport_type == job.required_transport_type:
        lines.append(
            {
                "status": "ok",
                "text": (
                    f"Требуемый транспорт {job.required_transport_type.value} "
                    f"совпадает с транспортом бригады"
                ),
            }
        )
    else:
        lines.append(
            {
                "status": "bad",
                "text": (
                    f"Заявка требует транспорт "
                    f"{job.required_transport_type.value}, у бригады — "
                    f"{engineer.transport_type.value}"
                ),
            }
        )

    # 4. Оборудование.
    if job.required_equipment:
        missing = set(job.required_equipment) - set(engineer.equipment_ids)

        if not missing:
            lines.append(
                {
                    "status": "ok",
                    "text": (
                        f"Всё необходимое оборудование есть у бригады: "
                        f"{', '.join(job.required_equipment)}"
                    ),
                }
            )
        else:
            lines.append(
                {
                    "status": "bad",
                    "text": (
                        f"У бригады отсутствует оборудование: "
                        f"{', '.join(sorted(missing))}"
                    ),
                }
            )
    else:
        lines.append(
            {"status": "info", "text": "Дополнительное оборудование не требуется"}
        )

    # 5. Окно обслуживания и смена (по фактическому расписанию остановки).
    if stop is not None:
        fmt = "%H:%M"

        if job.window_start is not None:
            fits_window_start = stop.planned_start >= job.window_start
        else:
            fits_window_start = True

        if job.window_end is not None:
            fits_window_end = stop.planned_end <= job.window_end
        else:
            fits_window_end = True

        fits_shift = stop.planned_end <= engineer.shift_end

        window_text = (
            f"окно {job.window_start.strftime(fmt)}–"
            f"{job.window_end.strftime(fmt)}"
            if job.window_start is not None and job.window_end is not None
            else "окно не задано"
        )

        if fits_window_start and fits_window_end:
            lines.append(
                {
                    "status": "ok",
                    "text": (
                        f"Работа помещается в клиентское окно ({window_text}): "
                        f"старт {stop.planned_start.strftime(fmt)}, "
                        f"окончание {stop.planned_end.strftime(fmt)}"
                    ),
                }
            )
        else:
            lines.append(
                {
                    "status": "bad",
                    "text": (
                        f"Работа НЕ помещается в окно ({window_text}): "
                        f"старт {stop.planned_start.strftime(fmt)}, "
                        f"окончание {stop.planned_end.strftime(fmt)}"
                    ),
                }
            )

        if fits_shift:
            lines.append(
                {
                    "status": "ok",
                    "text": (
                        f"Окончание {stop.planned_end.strftime(fmt)} "
                        f"не позже конца смены "
                        f"{engineer.shift_end.strftime(fmt)}"
                    ),
                }
            )
        else:
            lines.append(
                {
                    "status": "bad",
                    "text": (
                        f"Окончание {stop.planned_end.strftime(fmt)} ПОЗЖЕ "
                        f"конца смены {engineer.shift_end.strftime(fmt)}"
                    ),
                }
            )

        if stop.planned_arrival is not None:
            arrival_before_shift = stop.planned_arrival <= engineer.shift_end
            lines.append(
                {
                    "status": "ok" if arrival_before_shift else "bad",
                    "text": (
                        f"Прибытие {stop.planned_arrival.strftime(fmt)} "
                        + ("в пределах смены" if arrival_before_shift else "после конца смены")
                    ),
                }
            )
    else:
        lines.append(
            {"status": "info", "text": "Остановка не рассчитана (нет маршрута)"}
        )

    # 6. Критерий выбора алгоритма.
    priority = WORK_TYPE_PRIORITY.get(job.work_type, 9)
    penalty = LOAD_BALANCE_PENALTY_MIN * route_load

    criterion_text = (
        f"Приоритет заявки {priority} "
        f"(EMERGENCY=0, CONNECTION=1, LOCAL_WORK/ADD_ORDER=2)"
    )

    if route_load:
        criterion_text += (
            f"; штраф балансировки {penalty} мин "
            f"за {route_load} уже назначенных остановок"
        )

    lines.append({"status": "info", "text": f"Критерий выбора: {criterion_text}."})

    return lines


def format_planned_time(value) -> str:
    """Форматирует datetime для таблиц («ДД.ММ.ГГГГ ЧЧ:ММ»)."""
    if value is None:
        return "—"

    return value.strftime("%d.%m.%Y %H:%M")


def travel_min_from_prev(
    travel: TravelMatrix,
    engineer: Engineer,
    prev_location_id: str,
    location_id: str,
) -> int | None:
    """Время пути от предыдущей точки до текущей (минуты)."""
    return travel.travel_min(
        prev_location_id,
        location_id,
        engineer.transport_type,
    )