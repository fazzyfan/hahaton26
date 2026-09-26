from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from src.models.entities import Plan, ValidationIssue
from src.optimizer.baseline import BaselinePlanner
from src.optimizer.route_planner import RoutePlanner
from src.optimizer.travel import TravelMatrix
from src.services.comparison import PlanComparison, compare_plans
from src.services.import_pipeline import InputBundle, load_input_directory
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


@dataclass
class PlanningResult:
    """Полный результат прогона: импорт + основной план + baseline."""

    bundle: InputBundle
    plan: Plan | None = None
    issues: list[ValidationIssue] = field(default_factory=list)
    baseline_plan: Plan | None = None
    comparison: PlanComparison | None = None

    @property
    def fatal_errors(self) -> list:
        return [
            error for error in self.bundle.errors if not error.can_skip
        ]

    @property
    def has_fatal_errors(self) -> bool:
        return bool(self.fatal_errors)

    @property
    def is_valid(self) -> bool:
        return self.plan is not None and not self.issues and self.plan.status == "VALID"


def run_planning(
    input_dir: str | Path,
    skip_rows: set[tuple[str, int]] | None = None,
    with_baseline: bool = True,
    csv_suffix: str = "Синтетические данные.csv",
    zone_override: dict[str, str] | None = None,
) -> PlanningResult:
    """
    Единая точка входа планирования для CLI и Streamlit:

        импорт -> проверка ошибок -> основной план -> независимая
        валидация -> baseline -> сравнение.

    Импорт, ограничения и расчёт выполняются одним кодом для всех
    интерфейсов. Если в импорте есть фатальные ошибки, план не строится.

    csv_suffix / zone_override пробрасываются в импорт (см.
    load_input_directory) для пользовательской загрузки через интерфейс.
    """
    bundle = load_input_directory(
        input_dir,
        skip_rows=skip_rows,
        csv_suffix=csv_suffix,
        zone_override=zone_override,
    )

    if any(not error.can_skip for error in bundle.errors):
        return PlanningResult(bundle=bundle)

    if not bundle.jobs:
        return PlanningResult(bundle=bundle)

    plan = build_plan(bundle)
    issues = check_plan(bundle, plan)

    baseline_plan: Plan | None = None
    comparison: PlanComparison | None = None

    if with_baseline:
        travel_matrix = TravelMatrix(bundle.travel_matrix)
        baseline_planner = BaselinePlanner(travel_matrix)
        baseline_plan = baseline_planner.build_plan(
            bundle.jobs,
            bundle.engineers,
        )
        comparison = compare_plans(
            plan,
            baseline_plan,
            bundle.jobs,
            bundle.engineers,
        )

    return PlanningResult(
        bundle=bundle,
        plan=plan,
        issues=issues,
        baseline_plan=baseline_plan,
        comparison=comparison,
    )