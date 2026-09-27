"""Проверка сохранности истории при перепланировании.

Независимая проверка того, что пересчёт плана после события
(«инженер стал недоступен») не изменил прошлое:

    * каждая работа, начавшаяся до времени события (planned_start <=
      event_time — завершённая или ещё выполняемая), сохраняет прежнего
      инженера и прежние planned_arrival / planned_start / planned_end;
    * ни одна новая остановка не начинается раньше времени события
      (назначение в прошлое запрещено).

Запускается ДО существующего PlanValidator: если история нарушена,
план помечается INVALID независимо от результата PlanValidator.
"""
from __future__ import annotations

from datetime import datetime

from src.models.entities import Plan, RouteStop, ValidationIssue


def check_history_preservation(
    old_plan: Plan,
    new_plan: Plan,
    event_time: datetime,
) -> list[ValidationIssue]:
    """
    Сравнивает новый план со старым по зафиксированной части истории.

    Возвращает список нарушений:

        * HISTORY_MISSING  — зафиксированная до события работа исчезла
                             из нового плана;
        * HISTORY_CHANGED  — у зафиксированной работы изменились инженер
                             или времена;
        * PAST_ASSIGNMENT  — новая остановка начинается раньше времени
                             события (назначение в прошлое).
    """
    issues: list[ValidationIssue] = []

    old_stops = _stops_by_job(old_plan)
    new_stops = _stops_by_job(new_plan)

    # --- 1. Зафиксированное прошлое не должно меняться -------------------
    for job_id in sorted(old_stops):
        old_engineer_id, old_stop = old_stops[job_id]

        if old_stop.planned_start > event_time:
            continue

        entry = new_stops.get(job_id)

        if entry is None:
            issues.append(
                _issue(
                    "HISTORY_MISSING",
                    (
                        f"Завершённая до события работа {job_id!r} "
                        "исчезла из нового плана"
                    ),
                    "Job",
                    job_id,
                )
            )
            continue

        new_engineer_id, new_stop = entry

        if new_engineer_id != old_engineer_id:
            issues.append(
                _issue(
                    "HISTORY_CHANGED",
                    (
                        f"Работа {job_id!r}, начавшаяся до события, "
                        f"перенесена с {old_engineer_id!r} на "
                        f"{new_engineer_id!r}"
                    ),
                    "Job",
                    job_id,
                )
            )

        if _times_changed(old_stop, new_stop):
            issues.append(
                _issue(
                    "HISTORY_CHANGED",
                    (
                        f"Времена завершённой до события работы "
                        f"{job_id!r} изменены при пересчёте"
                    ),
                    "RouteStop",
                    job_id,
                )
            )

    # --- 2. Никаких новых назначений в прошлое ----------------------------
    for job_id in sorted(new_stops):
        new_engineer_id, new_stop = new_stops[job_id]

        if new_stop.planned_start >= event_time:
            continue

        preserved = old_stops.get(job_id)

        if preserved is None:
            issues.append(
                _issue(
                    "PAST_ASSIGNMENT",
                    (
                        f"Работа {job_id!r} назначена в прошлое: "
                        f"начало {new_stop.planned_start.isoformat()} "
                        f"раньше времени события "
                        f"{event_time.isoformat()}"
                    ),
                    "RouteStop",
                    job_id,
                )
            )
            continue

        old_engineer_id, old_stop = preserved

        if new_engineer_id != old_engineer_id or _times_changed(
            old_stop,
            new_stop,
        ):
            issues.append(
                _issue(
                    "PAST_ASSIGNMENT",
                    (
                        f"Начало работы {job_id!r} раньше времени события, "
                        "но остановка изменена при пересчёте"
                    ),
                    "RouteStop",
                    job_id,
                )
            )

    return issues


def _stops_by_job(
    plan: Plan,
) -> dict[str, tuple[str, RouteStop]]:
    result: dict[str, tuple[str, RouteStop]] = {}

    for route in plan.routes:
        for stop in route.stops:
            result[stop.job_id] = (route.engineer_id, stop)

    return result


def _times_changed(left: RouteStop, right: RouteStop) -> bool:
    return (
        left.planned_arrival != right.planned_arrival
        or left.planned_start != right.planned_start
        or left.planned_end != right.planned_end
    )


def _issue(
    code: str,
    message: str,
    entity_type: str,
    entity_id: str,
) -> ValidationIssue:
    return ValidationIssue(
        code=code,
        message=message,
        entity_type=entity_type,
        entity_id=entity_id,
    )