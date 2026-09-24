from __future__ import annotations

from datetime import datetime, timedelta, timezone

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
from src.optimizer.travel import TravelMatrix

# Официальный порядок приоритетов: авария -> подключение -> локальная/дозаказ.
WORK_TYPE_PRIORITY = {
    "EMERGENCY": 0,
    "CONNECTION": 1,
    "LOCAL_WORK": 2,
    "ADD_ORDER": 3,
}

# Штраф (минуты) за каждую уже назначенную остановку: эвристика
# балансировки загрузки между бригадами при равной стоимости вставки.
LOAD_BALANCE_PENALTY_MIN = 10

REASON_MESSAGES = {
    UnassignmentReason.NO_QUALIFIED_ENGINEER: (
        "Нет бригады, подходящей по району, типу работы или оборудованию"
    ),
    UnassignmentReason.NO_TIME_WINDOW: (
        "Окно обслуживания не пересекается с возможным временем приезда"
    ),
    UnassignmentReason.SHIFT_CONFLICT: (
        "Работа не помещается в рабочую смену бригады"
    ),
    UnassignmentReason.NO_TRAVEL_DATA: (
        "Нет данных о времени пути до локации заявки"
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
        * оборудование (required_equipment ⊆ equipment_ids);
        * данные о времени пути (travel matrix);
        * окно обслуживания (planned_start внутри окна);
        * рабочая смена (конец работы ≤ конец смены).

    Неназначенные заявки получают стабильный reason_code.
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

        ordered_jobs = sorted(jobs, key=self._sort_key)

        for job in ordered_jobs:
            compatible = [
                engineer
                for engineer in engineers
                if self._is_compatible(job, engineer)
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
            empty_reason = self._empty_route_reason(job, compatible)

            if empty_reason is not None:
                unassigned.append(self._unassigned(job, empty_reason))
                continue

            # Кандидат: (score, load, -position) -> чем меньше, тем лучше.
            best = None  # (candidate_key, engineer, position)

            for engineer in compatible:
                current_route = routes[engineer.id]
                current_travel = self._total_travel_min(
                    current_route,
                    engineer,
                )

                for position in range(len(current_route) + 1):
                    candidate = (
                        current_route[:position]
                        + [job]
                        + current_route[position:]
                    )
                    stops, reason = self._schedule(candidate, engineer)

                    if reason is not None:
                        continue

                    extra = (
                        self._total_travel_min(candidate, engineer)
                        - current_travel
                    )

                    score = extra + (
                        LOAD_BALANCE_PENALTY_MIN * len(current_route)
                    )
                    key = (score, len(current_route), -position)

                    if best is None or key < best[0]:
                        best = (key, engineer, position)

            if best is None:
                # Заявка выполнима в принципе, но не помещается ни в один
                # текущий маршрут — исчерпана ёмкость рабочих смен.
                unassigned.append(
                    self._unassigned(job, UnassignmentReason.SHIFT_CONFLICT)
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

    # --- совместимость -----------------------------------------------------

    def _is_compatible(self, job: JobRecord, engineer: Engineer) -> bool:
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

        if job.required_equipment and not set(job.required_equipment).issubset(
            set(engineer.equipment_ids)
        ):
            return False

        return True

    # --- расписание ---------------------------------------------------------

    def _schedule(
        self,
        jobs: list[JobRecord],
        engineer: Engineer,
    ) -> tuple[list[RouteStop] | None, UnassignmentReason | None]:
        """Считает времена остановок; при нарушении возвращает причину."""
        stops: list[RouteStop] = []
        cursor = engineer.shift_start
        prev_location = engineer.start_location_id

        for job in jobs:
            travel_min = self.travel.travel_min(
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

            stops, _ = self._schedule(route_jobs, engineer)

            result.append(
                Route(
                    engineer_id=engineer.id,
                    stops=stops,
                    total_travel_min=self._total_travel_min(
                        route_jobs,
                        engineer,
                    ),
                    total_distance_km=self._total_distance_km(
                        route_jobs,
                        engineer,
                    ),
                )
            )

        return result

    def _total_travel_min(
        self,
        jobs: list[JobRecord],
        engineer: Engineer,
    ) -> int:
        total = 0
        prev_location = engineer.start_location_id

        for job in jobs:
            travel_min = self.travel.travel_min(
                prev_location,
                job.location_id,
                engineer.transport_type,
            )

            if travel_min is None:
                return 0

            total += travel_min
            prev_location = job.location_id

        return total

    def _total_distance_km(
        self,
        jobs: list[JobRecord],
        engineer: Engineer,
    ) -> float:
        total = 0.0
        prev_location = engineer.start_location_id

        for job in jobs:
            if prev_location == job.location_id:
                continue

            entry = self.travel.find(
                prev_location,
                job.location_id,
                engineer.transport_type,
            )

            if entry is None:
                return 0.0

            total += entry.distance_km
            prev_location = job.location_id

        return total

    # --- вспомогательное ----------------------------------------------------

    @staticmethod
    def _sort_key(job: JobRecord) -> tuple[int, datetime]:
        priority = WORK_TYPE_PRIORITY.get(job.work_type, 9)

        if job.window_start is not None:
            return (priority, job.window_start)

        return (priority, datetime.max.replace(tzinfo=timezone.utc))

    def _empty_route_reason(
        self,
        job: JobRecord,
        engineers: list[Engineer],
    ) -> UnassignmentReason | None:
        """
        Проверяет выполнимость заявки на пустом маршруте
        (без учёта уже заполненных смен).

        None — хотя бы одна совместимая бригада может выполнить заявку;
        иначе — наиболее точная причина.
        """
        reasons: set[UnassignmentReason] = set()

        for engineer in engineers:
            _, reason = self._schedule([job], engineer)

            if reason is None:
                return None

            reasons.add(reason)

        if reasons == {UnassignmentReason.NO_TRAVEL_DATA}:
            return UnassignmentReason.NO_TRAVEL_DATA

        if UnassignmentReason.NO_TIME_WINDOW in reasons:
            return UnassignmentReason.NO_TIME_WINDOW

        return UnassignmentReason.SHIFT_CONFLICT

    def _unassigned(
        self,
        job: JobRecord,
        reason: UnassignmentReason,
    ) -> UnassignedJob:
        return UnassignedJob(
            job_id=job.id,
            reason_code=reason,
            message=REASON_MESSAGES.get(reason, str(reason)),
        )