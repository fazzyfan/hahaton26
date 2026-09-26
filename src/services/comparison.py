from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from src.models.entities import Engineer, JobRecord, Plan


@dataclass
class PlanComparison:
    """Сравнение основного плана и baseline на одинаковых входных данных."""

    metrics: dict                      # сводные метрики по обоим планам
    by_priority: list[dict]            # назначения по приоритетам
    unassigned_by_reason: list[dict]   # неназначения по причинам
    by_engineer: list[dict]            # расстояние/время по бригадам


def _engineer_metrics(plan: Plan, engineers: list[Engineer]) -> dict[str, dict]:
    routes_by_engineer = {
        route.engineer_id: route for route in plan.routes
    }
    result: dict[str, dict] = {}

    for engineer in engineers:
        route = routes_by_engineer.get(engineer.id)

        if route is None or not route.stops:
            result[engineer.id] = {
                "engineer_id": engineer.id,
                "stops": 0,
                "travel_min": 0,
                "distance_km": 0.0,
            }
            continue

        result[engineer.id] = {
            "engineer_id": engineer.id,
            "stops": len(route.stops),
            "travel_min": route.total_travel_min,
            "distance_km": round(route.total_distance_km, 2),
        }

    return result


def compare_plans(
    main_plan: Plan,
    baseline_plan: Plan,
    jobs: list[JobRecord],
    engineers: list[Engineer],
) -> PlanComparison:
    """
    Сравнивает два плана, построенных на одинаковых заявках, бригадах
    и матрице перемещений.
    """
    jobs_by_id = {job.id: job for job in jobs}

    def assigned_priorities(plan: Plan) -> Counter:
        counts: Counter = Counter()

        for assignment in plan.assignments:
            job = jobs_by_id.get(assignment.job_id)

            if job is None:
                counts["UNKNOWN"] += 1
            else:
                counts[job.priority or "UNKNOWN"] += 1

        return counts

    main_priorities = assigned_priorities(main_plan)
    baseline_priorities = assigned_priorities(baseline_plan)

    def unassigned_reasons(plan: Plan) -> Counter:
        return Counter(item.reason_code.value for item in plan.unassigned)

    main_reasons = unassigned_reasons(main_plan)
    baseline_reasons = unassigned_reasons(baseline_plan)

    main_by_engineer = _engineer_metrics(main_plan, engineers)
    baseline_by_engineer = _engineer_metrics(baseline_plan, engineers)

    used_main = {a.engineer_id for a in main_plan.assignments}
    used_baseline = {a.engineer_id for a in baseline_plan.assignments}

    metrics = {
        "main": {
            "assigned": len(main_plan.assignments),
            "unassigned": len(main_plan.unassigned),
            "used_engineers": len(used_main),
            "total_travel_min": sum(
                route.total_travel_min for route in main_plan.routes
            ),
            "total_distance_km": round(
                sum(route.total_distance_km for route in main_plan.routes),
                2,
            ),
        },
        "baseline": {
            "assigned": len(baseline_plan.assignments),
            "unassigned": len(baseline_plan.unassigned),
            "used_engineers": len(used_baseline),
            "total_travel_min": sum(
                route.total_travel_min for route in baseline_plan.routes
            ),
            "total_distance_km": round(
                sum(
                    route.total_distance_km for route in baseline_plan.routes
                ),
                2,
            ),
        },
    }

    priority_keys = sorted(
        set(main_priorities) | set(baseline_priorities)
    )

    by_priority = [
        {
            "priority": key,
            "main": main_priorities.get(key, 0),
            "baseline": baseline_priorities.get(key, 0),
        }
        for key in priority_keys
    ]

    reason_keys = sorted(set(main_reasons) | set(baseline_reasons))

    unassigned_by_reason = [
        {
            "reason_code": key,
            "main": main_reasons.get(key, 0),
            "baseline": baseline_reasons.get(key, 0),
        }
        for key in reason_keys
    ]

    by_engineer = [
        {
            "engineer_id": engineer.id,
            "main_stops": main_by_engineer[engineer.id]["stops"],
            "baseline_stops": baseline_by_engineer[engineer.id]["stops"],
            "main_travel_min": main_by_engineer[engineer.id]["travel_min"],
            "baseline_travel_min": (
                baseline_by_engineer[engineer.id]["travel_min"]
            ),
            "main_distance_km": main_by_engineer[engineer.id]["distance_km"],
            "baseline_distance_km": (
                baseline_by_engineer[engineer.id]["distance_km"]
            ),
        }
        for engineer in engineers
    ]

    return PlanComparison(
        metrics=metrics,
        by_priority=by_priority,
        unassigned_by_reason=unassigned_by_reason,
        by_engineer=by_engineer,
    )