from __future__ import annotations

from src.models.entities import (
    Assignment,
    Engineer,
    JobRecord,
    Plan,
    Route,
    UnassignedJob,
)
from src.models.enums import UnassignmentReason
from src.optimizer.route_planner import REASON_MESSAGES
from src.optimizer.scheduling import (
    empty_route_reason,
    is_active,
    is_compatible,
    schedule_route,
    total_distance_km,
    total_travel_min,
)
from src.optimizer.travel import TravelMatrix


class BaselinePlanner:
    """
    Простой эталонный планировщик (baseline) для сравнения с основным.

    Правила baseline:
        * заявки обрабатываются в ЗАФИКСИРОВАННОМ порядке: при наличии
          received_at — по нему, иначе — в порядке файлов и строк входного
          набора (допущение явно документируется в отчёте);
        * выбирается ПЕРВАЯ подходящая бригада из списка;
        * заявка добавляется В КОНЕЦ её маршрута (без перестановок);
        * ограничения те же, что и в основном алгоритме (район, тип работы,
          транспорт, оборудование, travel matrix, окно, смена).
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

        ordered_jobs = sorted(
            (job for job in jobs if is_active(job)),
            key=self._sort_key,
        )

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

            empty_reason = empty_route_reason(self.travel, job, compatible)

            if empty_reason is not None:
                unassigned.append(self._unassigned(job, empty_reason))
                continue

            # Первая подходящая бригада, в конец её маршрута.
            assigned = False

            for engineer in compatible:
                candidate = routes[engineer.id] + [job]
                stops, reason = schedule_route(
                    self.travel,
                    candidate,
                    engineer,
                )

                if reason is None:
                    routes[engineer.id].append(job)
                    assignments.append(
                        Assignment(job_id=job.id, engineer_id=engineer.id)
                    )
                    assigned = True
                    break

            if not assigned:
                unassigned.append(
                    self._unassigned(
                        job,
                        UnassignmentReason.NO_FEASIBLE_INSERTION,
                    )
                )

        result_routes = self._build_routes(routes, engineers)

        return Plan(
            assignments=assignments,
            routes=result_routes,
            unassigned_job_ids=[item.job_id for item in unassigned],
            unassigned=unassigned,
            status="PLANNED",
        )

    @staticmethod
    def _sort_key(job: JobRecord) -> tuple:
        # received_at — источник порядка, если он есть; иначе сохраняем
        # порядок входного набора (стабильная сортировка).
        if job.received_at is not None:
            return (0, job.received_at)

        return (1,)

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