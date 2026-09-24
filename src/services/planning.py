from __future__ import annotations

from src.models.entities import Plan, ValidationIssue
from src.optimizer.route_planner import RoutePlanner
from src.optimizer.travel import TravelMatrix
from src.services.import_pipeline import InputBundle
from src.validation.plan_validator import PlanValidator


def check_plan(
    bundle: InputBundle,
    plan: Plan,
) -> list[ValidationIssue]:
    """Независимая проверка hard constraints плана по входным данным."""
    travel_matrix = TravelMatrix(bundle.travel_matrix)
    validator = PlanValidator(travel_matrix)

    return validator.validate(plan, bundle.jobs, bundle.engineers)


def build_plan(bundle: InputBundle) -> Plan:
    """
    Строит многобригадный статический план и независимо проверяет
    hard constraints.

    Статус плана:
        VALID   — нет нарушений hard constraints (неназначенные заявки
                  допустимы и имеют reason_code);
        INVALID — найдены нарушения, публиковать такой план нельзя.
    """
    travel_matrix = TravelMatrix(bundle.travel_matrix)

    planner = RoutePlanner(travel_matrix)
    plan = planner.build_plan(bundle.jobs, bundle.engineers)

    issues = check_plan(bundle, plan)

    plan.status = "VALID" if not issues else "INVALID"

    return plan