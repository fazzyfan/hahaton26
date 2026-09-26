from __future__ import annotations

from datetime import datetime, timezone

from src.models.entities import (
    Assignment,
    Engineer,
    JobRecord,
    Plan,
    Route,
    UnassignedJob,
)
from src.models.enums import UnassignmentReason
from src.optimizer.scheduling import (
    empty_route_reason,
    is_active,
    is_compatible,
    schedule_route,
    total_distance_km,
    total_travel_min,
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
    """

    def __init__(self, travel_matrix: TravelMatrix) -> None:
        self.travel = travel_matrix

    def build_plan(
        self,
        jobs: list[JobRecord],
        engineers: list[Engineer],
    ) -> Plan:
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
            # если заявку в принципе нельзя выполнить (нет данных о пути,
            # окно или смена не позволяют) — фиксируем причину сразу.
            empty_reason = empty_route_reason(self.travel, job, compatible)

            if empty_reason is not None:
                unassigned.append(self._unassigned(job, empty_reason))
                continue

            # Кандидат: (score, load, -position) -> чем меньше, тем лучше.
            best = None  # (candidate_key, engineer, position)

            for engineer in compatible:
                current_route = routes[engineer.id]
                current_travel = total_travel_min(
                    self.travel,
                    current_route,
                    engineer,
                )

                for position in range(len(current_route) + 1):
                    candidate = (
                        current_route[:position]
                        + [job]
                        + current_route[position:]
                    )
                    stops, reason = schedule_route(
                        self.travel,
                        candidate,
                        engineer,
                    )

                    if reason is not None:
                        continue

                    extra = (
                        total_travel_min(self.travel, candidate, engineer)
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

        result_routes = self._build_routes(routes, engineers)

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
    ) -> list[Route]:
        result: list[Route] = []

        for engineer in engineers:
            route_jobs = routes[engineer.id]

            if not route_jobs:
                continue

            stops, _ = schedule_route(self.travel, route_jobs, engineer)

            result.append(
                Route(
                    engineer_id=engineer.id,
                    stops=stops,
                    total_travel_min=total_travel_min(
                        self.travel,
                        route_jobs,
                        engineer,
                    ),
                    total_distance_km=total_distance_km(
                        self.travel,
                        route_jobs,
                        engineer,
                    ),
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