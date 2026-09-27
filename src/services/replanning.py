"""Демонстрационное событие: «инженер стал недоступен».

Диспетчер задаёт время события. Семантика пересчёта:

    * остановки КАЖДОЙ бригады разделяются по времени события: всё, что
      началось до события (planned_start <= event_time — завершённое или
      ещё выполняемое), закрепляется с прежним инженером и прежними
      planned_arrival/start/end и в планировщик повторно не отправляется;
    * если в момент события работу выполняет сам недоступный инженер,
      прерывание работ НЕ моделируется: новый план не строится, диспетчер
      получает понятное сообщение и предложенное время после окончания
      работы;
    * недоступный инженер исключается из кандидатов; его ещё не начатые
      заявки возвращаются в общий пул вместе с будущими заявками остальных
      бригад; ранее неназначенные заявки также рассматриваются повторно;
    * для каждой оставшейся бригады рассчитывается только продолжение от
      её последней зафиксированной точки и доступного времени на момент
      события, а не от утреннего офиса и начала смены;
    * итоговый маршрут собирается как «неизменённые остановки +
      рассчитанное продолжение»; входной план не изменяется на месте;
    * после пересчёта проверяется сохранность истории (прошлое не
      изменилось, нет назначений в прошлое), затем — существующий
      PlanValidator; при любых нарушениях план помечается INVALID.

Это статическая демонстрация одного события: GPS, дорожные происшествия,
мобильное приложение и универсальный обработчик всех ЧП НЕ входят в MVP.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from src.models.entities import (
    Assignment,
    Engineer,
    Plan,
    Route,
    RouteStop,
    UnassignedJob,
)
from src.optimizer.route_planner import RoutePlanner
from src.optimizer.scheduling import is_active, route_totals
from src.optimizer.travel import TravelMatrix
from src.services.import_pipeline import InputBundle
from src.validation.history_check import check_history_preservation
from src.validation.plan_validator import PlanValidator


@dataclass
class ReplanningResult:
    """Результат пересчёта после события «инженер стал недоступен»."""

    engineer_id: str
    event_time: datetime

    old_plan: Plan
    new_plan: Plan

    # Событие посреди работы недоступного инженера: план не строится.
    rejected: bool = False
    message: str | None = None
    suggested_time: datetime | None = None

    # Зафиксированные до события остановки ВСЕХ бригад (job_id).
    preserved_job_ids: list[str] = field(default_factory=list)

    # Будущие заявки недоступного инженера, вернувшиеся в пул.
    released_job_ids: list[str] = field(default_factory=list)

    # Заявки, переназначенные другим бригадам: (job_id, engineer_id).
    reassigned: list[tuple[str, str]] = field(default_factory=list)

    # Ранее неназначенные заявки, назначенные после события.
    newly_assigned: list[tuple[str, str]] = field(default_factory=list)

    # Заявки из будущего (все бригады), оставшиеся неназначенными.
    unassigned_released: list[UnassignedJob] = field(default_factory=list)

    # Проверка сохранности истории (прошлое не изменено).
    history_issues: list = field(default_factory=list)

    # Нарушения независимого PlanValidator.
    validator_issues: list = field(default_factory=list)

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


def _split_stops(
    stops: list[RouteStop],
    event_time: datetime,
) -> tuple[list[RouteStop], list[str], RouteStop | None]:
    """Разделяет остановки маршрута по времени события.

    Возвращает (fixed, future_job_ids, in_progress):

        fixed           — всё, что началось до события (завершённое и ещё
                          выполняемое), НЕ изменяется при пересчёте;
        future_job_ids  — заявки, ещё не начатые
                          (planned_start > event_time), попадают в пул;
        in_progress     — остановка, выполняемая в момент события
                          (planned_start <= event_time < planned_end),
                          или None.
    """
    fixed: list[RouteStop] = []
    future_job_ids: list[str] = []
    in_progress: RouteStop | None = None

    for stop in stops:
        if stop.planned_end <= event_time:
            fixed.append(stop)
        elif stop.planned_start <= event_time:
            # Началась до события, ещё выполняется: фиксируем до конца.
            fixed.append(stop)

            if in_progress is None:
                in_progress = stop
        else:
            future_job_ids.append(stop.job_id)

    return fixed, future_job_ids, in_progress


def _build_fixed_route(
    travel: TravelMatrix,
    engineer: Engineer,
    stops: list[RouteStop],
) -> Route | None:
    """Маршрут из зафиксированных (исторических) остановок бригады."""
    if not stops:
        return None

    travel_total, distance_total = route_totals(travel, engineer, stops)

    return Route(
        engineer_id=engineer.id,
        stops=list(stops),
        total_travel_min=travel_total,
        total_distance_km=distance_total,
    )


def _format_time(value: datetime) -> str:
    return value.strftime("%H:%M")


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

    target = engineers_by_id.get(engineer_id)

    if target is None:
        raise ValueError(f"Инженер {engineer_id!r} не найден во входных данных")

    # --- Разделяем остановки каждой бригады по времени события ----------
    fixed_stops: dict[str, list[RouteStop]] = {}
    future_job_ids: set[str] = set()
    target_future_ids: list[str] = []
    target_in_progress: RouteStop | None = None

    for route in plan.routes:
        fixed, future_ids, in_progress = _split_stops(
            route.stops,
            event_time,
        )

        if fixed:
            fixed_stops[route.engineer_id] = fixed

        future_job_ids.update(future_ids)

        if route.engineer_id == engineer_id:
            target_future_ids = future_ids

            if in_progress is not None:
                target_in_progress = in_progress

    preserved_job_ids = [
        stop.job_id
        for stops in fixed_stops.values()
        for stop in stops
    ]
    fixed_ids = set(preserved_job_ids)

    # --- Событие посреди работы недоступного инженера --------------------
    if target_in_progress is not None:
        suggested = target_in_progress.planned_end

        message = (
            f"Событие отклонено: в {_format_time(event_time)} бригада "
            f"{engineer_id} выполняет заявку {target_in_progress.job_id} "
            f"(с {_format_time(target_in_progress.planned_start)} по "
            f"{_format_time(suggested)}). Прерывание работ не "
            "моделируется. Выберите время события не раньше "
            f"{_format_time(suggested)}."
        )

        return ReplanningResult(
            engineer_id=engineer_id,
            event_time=event_time,
            old_plan=plan,
            new_plan=plan,
            rejected=True,
            message=message,
            suggested_time=suggested,
            preserved_job_ids=preserved_job_ids,
            released_job_ids=target_future_ids,
            issues=[],
        )

    # --- Пул пересчёта: будущее всех бригад + ранее неназначенные --------
    available_engineers = [
        engineer
        for engineer in bundle.engineers
        if engineer.id != engineer_id
    ]

    pool = [
        job
        for job in bundle.jobs
        if is_active(job) and job.id not in fixed_ids
    ]

    travel = TravelMatrix(bundle.travel_matrix)

    # --- Точки продолжения для каждой доступной бригады ------------------
    fixed_prefixes: dict[str, list[RouteStop]] = {}
    cursor_times: dict[str, datetime] = {}
    cursor_locations: dict[str, str] = {}

    for eng_id, stops in fixed_stops.items():
        if eng_id == engineer_id:
            continue

        engineer = engineers_by_id[eng_id]
        fixed_prefixes[eng_id] = stops

        last = stops[-1]
        # Время продолжения: не раньше события; если последняя
        # зафиксированная работа ещё выполняется — после её окончания.
        cursor_times[eng_id] = max(event_time, last.planned_end)
        cursor_locations[eng_id] = last.location_id

    for engineer in available_engineers:
        if engineer.id not in cursor_times:
            # Завершённых работ не было: стартовая точка — офис,
            # время старта — не раньше времени события.
            cursor_times[engineer.id] = max(event_time, engineer.shift_start)
            cursor_locations[engineer.id] = engineer.start_location_id

    replanned = RoutePlanner(travel).build_plan(
        pool,
        available_engineers,
        fixed_prefixes=fixed_prefixes,
        cursor_times=cursor_times,
        cursor_locations=cursor_locations,
    )

    # --- Объединяем: зафиксированная история + рассчитанное продолжение ---
    restored_assignments = [
        Assignment(job_id=stop.job_id, engineer_id=eng_id)
        for eng_id, stops in fixed_stops.items()
        for stop in stops
    ]

    combined_assignments = list(replanned.assignments) + restored_assignments
    combined_routes = list(replanned.routes)

    target_route = _build_fixed_route(
        travel,
        target,
        fixed_stops.get(engineer_id, []),
    )

    if target_route is not None:
        combined_routes.append(target_route)

    final_plan = Plan(
        assignments=combined_assignments,
        routes=combined_routes,
        unassigned_job_ids=list(replanned.unassigned_job_ids),
        unassigned=list(replanned.unassigned),
        status="PLANNED",
    )

    # --- Проверка: сохранность истории + существующий PlanValidator ------
    history_issues = check_history_preservation(plan, final_plan, event_time)
    validator_issues = PlanValidator(travel).validate(
        final_plan,
        bundle.jobs,
        bundle.engineers,
    )

    issues = history_issues + validator_issues
    final_plan.status = "VALID" if not issues else "INVALID"

    # --- Сводка переназначений -------------------------------------------
    old_by_engineer = {
        assignment.job_id: assignment.engineer_id
        for assignment in plan.assignments
    }
    old_unassigned_ids = {
        item.job_id for item in plan.unassigned
    }

    reassigned: list[tuple[str, str]] = []
    newly_assigned: list[tuple[str, str]] = []

    for assignment in replanned.assignments:
        previous = old_by_engineer.get(assignment.job_id)

        if previous is None:
            if assignment.job_id in old_unassigned_ids:
                newly_assigned.append(
                    (assignment.job_id, assignment.engineer_id)
                )
        elif previous != assignment.engineer_id:
            reassigned.append((assignment.job_id, assignment.engineer_id))

    unassigned_released = [
        item
        for item in replanned.unassigned
        if item.job_id in future_job_ids
    ]

    return ReplanningResult(
        engineer_id=engineer_id,
        event_time=event_time,
        old_plan=plan,
        new_plan=final_plan,
        preserved_job_ids=preserved_job_ids,
        released_job_ids=target_future_ids,
        reassigned=reassigned,
        newly_assigned=newly_assigned,
        unassigned_released=unassigned_released,
        history_issues=history_issues,
        validator_issues=validator_issues,
        issues=issues,
    )