"""Демонстрационное событие: «инженер стал недоступен».

Диспетчер задаёт время события. Семантика пересчёта:

    * уже завершённые работы инженера (planned_end <= event_time)
      СОХРАНЯЮТСЯ в плане без изменений;
    * будущие заявки этого инженера (planned_end > event_time)
      освобождаются и пересчитываются другими бригадами;
    * инженер исключается из пула кандидатов;
    * невозможные назначения остаются неназначенными с причиной
      (от планировщика: NO_QUALIFIED_ENGINEER / NO_FEASIBLE_INSERTION
      и т.п.).

Это статическая демонстрация одного события: GPS, дорожные происшествия,
мобильное приложение и универсальный обработчик всех ЧП НЕ входят в MVP.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from src.models.entities import (
    Assignment,
    Engineer,
    JobRecord,
    Plan,
    Route,
    UnassignedJob,
)
from src.optimizer.route_planner import RoutePlanner
from src.optimizer.scheduling import is_active
from src.optimizer.travel import TravelMatrix
from src.services.import_pipeline import InputBundle
from src.validation.plan_validator import PlanValidator


@dataclass
class ReplanningResult:
    """Результат пересчёта после события «инженер стал недоступен»."""

    engineer_id: str
    event_time: datetime

    old_plan: Plan
    new_plan: Plan

    # Сохранённые завершённые работы инженера (job_id).
    preserved_job_ids: list[str] = field(default_factory=list)

    # Будущие заявки инженера, попавшие в пересчёт.
    released_job_ids: list[str] = field(default_factory=list)

    # Заявки, переназначенные другим бригадам: (job_id, engineer_id).
    reassigned: list[tuple[str, str]] = field(default_factory=list)

    # Заявки инженера, оставшиеся неназначенными после пересчёта.
    unassigned_released: list[UnassignedJob] = field(default_factory=list)

    issues: list = field(default_factory=list)

    @property
    def assigned_before(self) -> int:
        return len(self.old_plan.assignments)

    @property
    def assigned_after(self) -> int:
        return len(self.new_plan.assignments)

    @property
    def unassigned_before(self) -> int:
        return len(self.old_plan.unassigned)

    @property
    def unassigned_after(self) -> int:
        return len(self.new_plan.unassigned)


def _build_completed_route(
    travel: TravelMatrix,
    engineer: Engineer,
    stops,
) -> Route | None:
    """Маршрут из сохранённых (завершённых) остановок инженера."""
    if not stops:
        return None

    prev_location = engineer.start_location_id
    travel_total = 0
    distance_total = 0.0

    for stop in stops:
        travel_min = travel.travel_min(
            prev_location,
            stop.location_id,
            engineer.transport_type,
        )

        if travel_min is not None:
            travel_total += travel_min

        entry = travel.find(
            prev_location,
            stop.location_id,
            engineer.transport_type,
        )

        if entry is not None:
            distance_total += entry.distance_km

        prev_location = stop.location_id

    return Route(
        engineer_id=engineer.id,
        stops=stops,
        total_travel_min=travel_total,
        total_distance_km=round(distance_total, 2),
    )


def replan_after_unavailability(
    bundle: InputBundle,
    plan: Plan,
    engineer_id: str,
    event_time: datetime,
) -> ReplanningResult:
    """
    Пересчитывает план после того, как инженер стал недоступен.

    Параметры:
        bundle      — входные данные (заявки, бригады, матрица);
        plan        — текущий (до события) план;
        engineer_id — инженер, ставший недоступным;
        event_time  — момент события (timezone-aware).
    """
    engineers_by_id = {engineer.id: engineer for engineer in bundle.engineers}
    jobs_by_id = {job.id: job for job in bundle.jobs}

    target = engineers_by_id.get(engineer_id)

    if target is None:
        raise ValueError(f"Инженер {engineer_id!r} не найден во входных данных")

    # --- Маршрут инженера: сохраняем завершённое, освобождаем будущее ---
    old_route = next(
        (
            route
            for route in plan.routes
            if route.engineer_id == engineer_id
        ),
        None,
    )

    preserved_stops: list = []
    released_job_ids: list[str] = []

    if old_route is not None:
        for stop in old_route.stops:
            if stop.planned_end <= event_time:
                preserved_stops.append(stop)
            else:
                released_job_ids.append(stop.job_id)

    # Освобождённые заявки, которые реально есть и активны.
    released_jobs: list[JobRecord] = [
        jobs_by_id[job_id]
        for job_id in released_job_ids
        if job_id in jobs_by_id and is_active(jobs_by_id[job_id])
    ]

    # --- Полный пересчёт без недоступного инженера ----------------------
    available_engineers = [
        engineer
        for engineer in bundle.engineers
        if engineer.id != engineer_id
    ]

    # Завершённые работы инженера исключаются из пула пересчёта
    # (они остаются за ним), всё остальное считается заново.
    replan_pool = [
        job
        for job in bundle.jobs
        if is_active(job) and job.id not in {
            stop.job_id for stop in preserved_stops
        }
    ]

    travel = TravelMatrix(bundle.travel_matrix)
    new_plan = RoutePlanner(travel).build_plan(
        replan_pool,
        available_engineers,
    )

    # --- Объединяем: новый план + сохранённые завершённые работы --------
    completed_route = _build_completed_route(travel, target, preserved_stops)

    restored_assignments = [
        Assignment(job_id=stop.job_id, engineer_id=engineer_id)
        for stop in preserved_stops
    ]

    combined_assignments = list(new_plan.assignments) + restored_assignments

    combined_routes = list(new_plan.routes)

    if completed_route is not None:
        combined_routes.append(completed_route)

    final_plan = Plan(
        assignments=combined_assignments,
        routes=combined_routes,
        unassigned_job_ids=list(new_plan.unassigned_job_ids),
        unassigned=list(new_plan.unassigned),
        status="VALID",
    )

    # --- Независимая проверка нового плана ------------------------------
    validator = PlanValidator(travel)
    issues = validator.validate(final_plan, bundle.jobs, bundle.engineers)
    final_plan.status = "VALID" if not issues else "INVALID"

    # --- Сводка переназначений -------------------------------------------
    old_by_engineer = {
        assignment.job_id: assignment.engineer_id
        for assignment in plan.assignments
    }

    reassigned: list[tuple[str, str]] = []

    for assignment in new_plan.assignments:
        previous = old_by_engineer.get(assignment.job_id)

        if previous == engineer_id and assignment.engineer_id != engineer_id:
            reassigned.append((assignment.job_id, assignment.engineer_id))

    unassigned_released = [
        item
        for item in new_plan.unassigned
        if item.job_id in set(released_job_ids)
    ]

    return ReplanningResult(
        engineer_id=engineer_id,
        event_time=event_time,
        old_plan=plan,
        new_plan=final_plan,
        preserved_job_ids=[stop.job_id for stop in preserved_stops],
        released_job_ids=released_job_ids,
        reassigned=reassigned,
        unassigned_released=unassigned_released,
        issues=issues,
    )