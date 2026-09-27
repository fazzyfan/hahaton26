from __future__ import annotations

from datetime import datetime, timezone

from src.models.entities import (
    Assignment,
    Engineer,
    JobRecord,
    Plan,
    Route,
    RouteStop,
    UnassignedJob,
)
from src.models.enums import UnassignmentReason
from src.optimizer.scheduling import (
    empty_route_reason,
    is_active,
    is_compatible,
    route_totals,
    schedule_continuation,
    travel_min_for_locations,
)
from src.optimizer.travel import TravelMatrix

# Официальный порядок приоритетов: авария -> подключение -> локальная/дозаказ.
# LOCAL_WORK и ADD_ORDER имеют ОДИНАКОВЫЙ бизнес-приоритет (NORMAL).
WORK_TYPE_PRIORITY = {
    "EMERGENCY": 0,
    "CONNECTION": 1,
    "LOCAL_WORK": 2,
    "ADD_ORDER": 2,
}

# Штраф (минуты) за каждую уже назначенную остановку: эвристика
# балансировки загрузки между бригадами при равной стоимости вставки.
LOAD_BALANCE_PENALTY_MIN = 10

REASON_MESSAGES = {
    UnassignmentReason.NO_QUALIFIED_ENGINEER: (
        "Нет бригады, подходящей по району, типу работы или оборудованию"
    ),
    UnassignmentReason.NO_TIME_WINDOW: (
        "Окно обслуживания не вмещает работу целиком "
        "(начало или окончание вне окна)"
    ),
    UnassignmentReason.SHIFT_CONFLICT: (
        "Работа не помещается в рабочую смену бригады"
    ),
    UnassignmentReason.NO_TRAVEL_DATA: (
        "Нет данных о времени пути до локации заявки"
    ),
    UnassignmentReason.NO_FEASIBLE_INSERTION: (
        "Заявка выполнима в принципе, но не встаёт ни в один текущий маршрут"
    ),
    UnassignmentReason.OPTIMIZER_LIMIT: (
        "Ограничение оптимизатора не позволило назначить заявку"
    ),
}


class RoutePlanner:
    """
    Многобригадный статический планировщик (жадная вставка, VRPTW).

    Hard constraints:
        * район (service_districts);
        * тип работы (allowed_work_types);
        * требуемый тип транспорта (required_transport_type, если задан);
        * оборудование (required_equipment ⊆ equipment_ids);
        * данные о времени пути (travel matrix);
        * окно обслуживания (planned_start >= window_start и
          planned_end <= window_end);
        * рабочая смена (конец работы <= конец смены).

    Заявки со статусом COMPLETED/CANCELLED в активное планирование
    не попадают. Неназначенные заявки получают стабильный reason_code.

    При перепланировании (build_plan с fixed_prefixes/cursor_times/
    cursor_locations) маршруты строятся как «зафиксированная история +
    рассчитанное продолжение»: прошлое каждой бригады не изменяется,
    будущее считается от последней зафиксированной точки модели.
    """

    def __init__(self, travel_matrix: TravelMatrix) -> None:
        self.travel = travel_matrix

    def build_plan(
        self,
        jobs: list[JobRecord],
        engineers: list[Engineer],
        *,
        fixed_prefixes: dict[str, list[RouteStop]] | None = None,
        cursor_times: dict[str, datetime] | None = None,
        cursor_locations: dict[str, str] | None = None,
    ) -> Plan:
        """
        Строит многобригадный план.

        Параметры перепланирования (необязательные):

            fixed_prefixes   — engineer_id -> неизменяемые остановки
                               (завершённые до события / выполняемые
                               в момент события);
            cursor_times     — engineer_id -> время, с которого считается
                               продолжение (не раньше времени события);
            cursor_locations — engineer_id -> точка, от которой считается
                               путь к первой работе продолжения.

        Без этих параметров поведение совпадает со статическим
        планированием от утреннего офиса и начала смены.
        """
        prefixes = fixed_prefixes or {}
        cursors = cursor_times or {}
        cursor_locs = cursor_locations or {}

        routes: dict[str, list[JobRecord]] = {
            engineer.id: [] for engineer in engineers
        }
        assignments: list[Assignment] = []
        unassigned: list[UnassignedJob] = []

        active_jobs = [job for job in jobs if is_active(job)]
        ordered_jobs = sorted(active_jobs, key=self._sort_key)

        for job in ordered_jobs:
            compatible = [
                engineer
                for engineer in engineers
                if is_compatible(job, engineer)
            ]

            if not compatible:
                unassigned.append(
                    self._unassigned(
                        job,
                        UnassignmentReason.NO_QUALIFIED_ENGINEER,
                    )
                )
                continue

            # Причина определяется по выполнимости на пустом маршруте:
            # если заявку в принципе нельзя выполнить от точки продолжения
            # (нет данных о пути, окно или смена не позволяют) —
            # фиксируем причину сразу.
            empty_reason = empty_route_reason(
                self.travel,
                job,
                compatible,
                cursor_times=cursors,
                cursor_locations=cursor_locs,
            )

            if empty_reason is not None:
                unassigned.append(self._unassigned(job, empty_reason))
                continue

            # Кандидат: (score, load, -position) -> чем меньше, тем лучше.
            best = None  # (candidate_key, engineer, position)

            for engineer in compatible:
                current_route = routes[engineer.id]
                cursor_time = cursors.get(engineer.id, engineer.shift_start)
                cursor_loc = cursor_locs.get(
                    engineer.id,
                    engineer.start_location_id,
                )

                current_locations = [cursor_loc] + [
                    job.location_id for job in current_route
                ]
                current_travel = travel_min_for_locations(
                    self.travel,
                    current_locations,
                    engineer.transport_type,
                )

                for position in range(len(current_route) + 1):
                    candidate = (
                        current_route[:position]
                        + [job]
                        + current_route[position:]
                    )
                    stops, reason = schedule_continuation(
                        self.travel,
                        candidate,
                        engineer,
                        cursor_time,
                        cursor_loc,
                    )

                    if reason is not None:
                        continue

                    candidate_locations = [cursor_loc] + [
                        item.location_id for item in candidate
                    ]

                    extra = (
                        travel_min_for_locations(
                            self.travel,
                            candidate_locations,
                            engineer.transport_type,
                        )
                        - current_travel
                    )

                    score = extra + (
                        LOAD_BALANCE_PENALTY_MIN * len(current_route)
                    )
                    key = (score, len(current_route), -position)

                    if best is None or key < best[0]:
                        best = (key, engineer, position)

            if best is None:
                # Заявка выполнима на пустом маршруте, но жадная вставка
                # не нашла позиции в текущих маршрутах. Это не конфликт
                # смены как таковой — фиксируем NO_FEASIBLE_INSERTION.
                unassigned.append(
                    self._unassigned(
                        job,
                        UnassignmentReason.NO_FEASIBLE_INSERTION,
                    )
                )
                continue

            _, engineer, position = best

            routes[engineer.id].insert(position, job)
            assignments.append(
                Assignment(job_id=job.id, engineer_id=engineer.id)
            )

        result_routes = self._build_routes(
            routes,
            engineers,
            prefixes,
            cursors,
            cursor_locs,
        )

        return Plan(
            assignments=assignments,
            routes=result_routes,
            unassigned_job_ids=[item.job_id for item in unassigned],
            unassigned=unassigned,
            status="PLANNED",
        )

    # --- итоговые маршруты --------------------------------------------------

    def _build_routes(
        self,
        routes: dict[str, list[JobRecord]],
        engineers: list[Engineer],
        prefixes: dict[str, list[RouteStop]],
        cursors: dict[str, datetime],
        cursor_locs: dict[str, str],
    ) -> list[Route]:
        result: list[Route] = []

        for engineer in engineers:
            route_jobs = routes[engineer.id]
            prefix = prefixes.get(engineer.id, [])

            if not prefix and not route_jobs:
                continue

            cursor_time = cursors.get(engineer.id, engineer.shift_start)
            cursor_loc = cursor_locs.get(
                engineer.id,
                engineer.start_location_id,
            )

            stops, _ = schedule_continuation(
                self.travel,
                route_jobs,
                engineer,
                cursor_time,
                cursor_loc,
            )

            # Итоговый маршрут = зафиксированная история + продолжение.
            full_stops = list(prefix) + (stops or [])

            travel_total, distance_total = route_totals(
                self.travel,
                engineer,
                full_stops,
            )

            result.append(
                Route(
                    engineer_id=engineer.id,
                    stops=full_stops,
                    total_travel_min=travel_total,
                    total_distance_km=distance_total,
                )
            )

        return result

    # --- вспомогательное ----------------------------------------------------

    @staticmethod
    def _sort_key(job: JobRecord) -> tuple[int, datetime]:
        priority = WORK_TYPE_PRIORITY.get(job.work_type, 9)

        if job.window_start is not None:
            return (priority, job.window_start)

        return (priority, datetime.max.replace(tzinfo=timezone.utc))

    @staticmethod
    def _unassigned(
        job: JobRecord,
        reason: UnassignmentReason,
    ) -> UnassignedJob:
        return UnassignedJob(
            job_id=job.id,
            reason_code=reason,
            message=REASON_MESSAGES.get(reason, str(reason)),
        )