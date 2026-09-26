from __future__ import annotations

from datetime import timedelta

from src.models.entities import (
    Engineer,
    JobRecord,
    Plan,
    ValidationIssue,
)
from src.optimizer.travel import TravelMatrix


class PlanValidator:
    """
    Независимая проверка hard constraints плана.

    Не использует внутреннюю логику планировщика — проверяет
    итоговый план по исходным данным (заявки, бригады, матрица).
    """

    def __init__(self, travel_matrix: TravelMatrix) -> None:
        self.travel = travel_matrix

    def validate(
        self,
        plan: Plan,
        jobs: list[JobRecord],
        engineers: list[Engineer],
    ) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []

        jobs_by_id = {job.id: job for job in jobs}
        engineers_by_id = {engineer.id: engineer for engineer in engineers}

        self._check_coverage(plan, jobs, issues)
        self._check_unique_assignments(plan, issues)
        self._check_routes_match_assignments(plan, issues)

        for assignment in plan.assignments:
            job = jobs_by_id.get(assignment.job_id)
            engineer = engineers_by_id.get(assignment.engineer_id)

            if job is None:
                issues.append(
                    self._issue(
                        "UNKNOWN_JOB",
                        f"Заявка {assignment.job_id!r} не найдена во входных данных",
                        "Assignment",
                        assignment.job_id,
                    )
                )
                continue

            if engineer is None:
                issues.append(
                    self._issue(
                        "UNKNOWN_ENGINEER",
                        f"Бригада {assignment.engineer_id!r} не найдена во входных данных",
                        "Assignment",
                        assignment.job_id,
                    )
                )
                continue

            self._check_compatibility(assignment.job_id, job, engineer, issues)

        self._check_routes_timing(plan, jobs_by_id, engineers_by_id, issues)

        return issues

    # --- покрытие -----------------------------------------------------------

    def _check_coverage(
        self,
        plan: Plan,
        jobs: list[JobRecord],
        issues: list[ValidationIssue],
    ) -> None:
        valid_job_ids = {job.id for job in jobs}
        assigned_ids = {assignment.job_id for assignment in plan.assignments}
        unassigned_ids = {item.job_id for item in plan.unassigned}

        for job_id in sorted(valid_job_ids):
            in_assigned = job_id in assigned_ids
            in_unassigned = job_id in unassigned_ids

            if in_assigned and in_unassigned:
                issues.append(
                    self._issue(
                        "BOTH_ASSIGNED_AND_UNASSIGNED",
                        f"Заявка {job_id!r} одновременно назначена и неназначена",
                        "Job",
                        job_id,
                    )
                )
            elif not in_assigned and not in_unassigned:
                issues.append(
                    self._issue(
                        "JOB_NOT_COVERED",
                        f"Заявка {job_id!r} отсутствует и в назначениях, "
                        "и в неназначенных",
                        "Job",
                        job_id,
                    )
                )

        if len(assigned_ids) + len(unassigned_ids) != len(valid_job_ids):
            issues.append(
                self._issue(
                    "COVERAGE_COUNT",
                    (
                        f"len(assignments) + len(unassigned) = "
                        f"{len(assigned_ids) + len(unassigned_ids)}, "
                        f"ожидалось {len(valid_job_ids)}"
                    ),
                    "Plan",
                    "-",
                )
            )

    # --- назначения ---------------------------------------------------------

    def _check_unique_assignments(
        self,
        plan: Plan,
        issues: list[ValidationIssue],
    ) -> None:
        seen: set[str] = set()

        for assignment in plan.assignments:
            if assignment.job_id in seen:
                issues.append(
                    self._issue(
                        "DOUBLE_ASSIGNMENT",
                        f"Заявка {assignment.job_id!r} назначена более чем одной бригаде",
                        "Assignment",
                        assignment.job_id,
                    )
                )

            seen.add(assignment.job_id)

    def _check_routes_match_assignments(
        self,
        plan: Plan,
        issues: list[ValidationIssue],
    ) -> None:
        assigned_pairs = {
            (assignment.job_id, assignment.engineer_id)
            for assignment in plan.assignments
        }

        stop_job_ids: set[str] = set()

        for route in plan.routes:
            for stop in route.stops:
                stop_job_ids.add(stop.job_id)

                if (stop.job_id, route.engineer_id) not in assigned_pairs:
                    issues.append(
                        self._issue(
                            "ROUTE_MISMATCH",
                            (
                                f"Остановка {stop.job_id!r} в маршруте "
                                f"{route.engineer_id!r} не соответствует назначению"
                            ),
                            "RouteStop",
                            stop.job_id,
                        )
                    )

        for job_id, _ in assigned_pairs:
            if job_id not in stop_job_ids:
                issues.append(
                    self._issue(
                        "ROUTE_MISSING_STOP",
                        f"Назначенная заявка {job_id!r} отсутствует в маршрутах",
                        "Assignment",
                        job_id,
                    )
                )

    # --- совместимость -------------------------------------------------------

    def _check_compatibility(
        self,
        job_id: str,
        job: JobRecord,
        engineer: Engineer,
        issues: list[ValidationIssue],
    ) -> None:
        if (
            engineer.service_districts
            and job.service_zone not in engineer.service_districts
        ):
            issues.append(
                self._issue(
                    "INCOMPATIBLE_ENGINEER",
                    (
                        f"Район {job.service_zone!r} заявки {job_id!r} "
                        "не входит в зоны бригады"
                    ),
                    "Assignment",
                    job_id,
                )
            )

        if (
            engineer.allowed_work_types
            and job.work_type not in engineer.allowed_work_types
        ):
            issues.append(
                self._issue(
                    "INCOMPATIBLE_ENGINEER",
                    (
                        f"Тип работы {job.work_type!r} заявки {job_id!r} "
                        "не разрешён бригаде"
                    ),
                    "Assignment",
                    job_id,
                )
            )

        if job.required_equipment and not set(job.required_equipment).issubset(
            set(engineer.equipment_ids)
        ):
            issues.append(
                self._issue(
                    "INCOMPATIBLE_ENGINEER",
                    (
                        f"Оборудование {job.required_equipment!r} заявки "
                        f"{job_id!r} отсутствует у бригады"
                    ),
                    "Assignment",
                    job_id,
                )
            )

        if (
            job.required_transport_type is not None
            and engineer.transport_type != job.required_transport_type
        ):
            issues.append(
                self._issue(
                    "INCOMPATIBLE_ENGINEER",
                    (
                        f"Заявка {job_id!r} требует транспорт "
                        f"{job.required_transport_type.value!r}, "
                        f"у бригады — {engineer.transport_type.value!r}"
                    ),
                    "Assignment",
                    job_id,
                )
            )

    # --- тайминги маршрутов --------------------------------------------------

    def _check_routes_timing(
        self,
        plan: Plan,
        jobs_by_id: dict[str, JobRecord],
        engineers_by_id: dict[str, Engineer],
        issues: list[ValidationIssue],
    ) -> None:
        for route in plan.routes:
            engineer = engineers_by_id.get(route.engineer_id)

            if engineer is None:
                continue

            prev_location = engineer.start_location_id
            prev_end = engineer.shift_start

            for stop in route.stops:
                travel_min = self.travel.travel_min(
                    prev_location,
                    stop.location_id,
                    engineer.transport_type,
                )

                if travel_min is None:
                    issues.append(
                        self._issue(
                            "TRAVEL_VIOLATION",
                            (
                                f"Нет данных о времени пути "
                                f"{prev_location!r} -> {stop.location_id!r}"
                            ),
                            "RouteStop",
                            stop.job_id,
                        )
                    )
                elif stop.planned_arrival < prev_end + timedelta(
                    minutes=travel_min
                ):
                    issues.append(
                        self._issue(
                            "TRAVEL_VIOLATION",
                            (
                                f"Прибытие к {stop.job_id!r} раньше, чем "
                                f"позволяет время пути ({travel_min} мин)"
                            ),
                            "RouteStop",
                            stop.job_id,
                        )
                    )

                if stop.planned_start < stop.planned_arrival:
                    issues.append(
                        self._issue(
                            "START_BEFORE_ARRIVAL",
                            (
                                f"Начало работы {stop.job_id!r} раньше прибытия"
                            ),
                            "RouteStop",
                            stop.job_id,
                        )
                    )

                job = jobs_by_id.get(stop.job_id)

                if job is not None:
                    if (
                        job.window_start is not None
                        and stop.planned_start < job.window_start
                    ):
                        issues.append(
                            self._issue(
                                "WINDOW_VIOLATION",
                                (
                                    f"Начало работы {stop.job_id!r} раньше "
                                    "начала окна обслуживания"
                                ),
                                "RouteStop",
                                stop.job_id,
                            )
                        )

                    if (
                        job.window_end is not None
                        and stop.planned_start > job.window_end
                    ):
                        issues.append(
                            self._issue(
                                "WINDOW_VIOLATION",
                                (
                                    f"Начало работы {stop.job_id!r} позже "
                                    "конца окна обслуживания"
                                ),
                                "RouteStop",
                                stop.job_id,
                            )
                        )

                    # Работа должна завершиться не позже конца клиентского
                    # окна: planned_end <= window_end. Окончание ровно на
                    # границе допустимо.
                    if (
                        job.window_end is not None
                        and stop.planned_end > job.window_end
                    ):
                        issues.append(
                            self._issue(
                                "WINDOW_VIOLATION",
                                (
                                    f"Работа {stop.job_id!r} заканчивается "
                                    "позже конца окна обслуживания"
                                ),
                                "RouteStop",
                                stop.job_id,
                            )
                        )

                    expected_end = stop.planned_start + timedelta(
                        minutes=job.service_duration_min
                    )

                    if stop.planned_end != expected_end:
                        issues.append(
                            self._issue(
                                "DURATION_VIOLATION",
                                (
                                    f"Длительность работы {stop.job_id!r} "
                                    "не соответствует нормативу"
                                ),
                                "RouteStop",
                                stop.job_id,
                            )
                        )

                if stop.planned_end > engineer.shift_end:
                    issues.append(
                        self._issue(
                            "SHIFT_VIOLATION",
                            (
                                f"Работа {stop.job_id!r} заканчивается "
                                "позже конца смены"
                            ),
                            "RouteStop",
                            stop.job_id,
                        )
                    )

                prev_location = stop.location_id
                prev_end = stop.planned_end

    # --- вспомогательное -----------------------------------------------------

    @staticmethod
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