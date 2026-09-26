"""Подготовка pandas-таблиц для интерфейса."""

from __future__ import annotations

import pandas as pd

from src.models.entities import Engineer, JobRecord
from src.optimizer.travel import TravelMatrix
from src.services.comparison import PlanComparison
from src.services.planning import PlanningResult
from src.ui.explain import format_planned_time, travel_min_from_prev


def assignments_dataframe(
    result: PlanningResult,
    jobs_by_id: dict[str, JobRecord],
    engineers_by_id: dict[str, Engineer],
) -> pd.DataFrame:
    """Таблица назначений: заявка, тип, бригада, зона, адрес, времена."""
    rows = []

    for assignment in result.plan.assignments:
        job = jobs_by_id.get(assignment.job_id)
        engineer = engineers_by_id.get(assignment.engineer_id)

        if job is None or engineer is None:
            continue

        route = next(
            (
                route
                for route in result.plan.routes
                if route.engineer_id == engineer.id
            ),
            None,
        )

        stop = None
        if route is not None:
            stop = next(
                (item for item in route.stops if item.job_id == job.id),
                None,
            )

        rows.append(
            {
                "Заявка": job.id,
                "Тип работы": job.work_type,
                "Приоритет": job.priority or "—",
                "Бригада": engineer.id,
                "Зона": job.service_zone,
                "Район": job.district or "—",
                "Адрес": job.address,
                "Начало": format_planned_time(
                    stop.planned_start if stop else None
                ),
                "Окончание": format_planned_time(
                    stop.planned_end if stop else None
                ),
            }
        )

    return pd.DataFrame(rows)


def unassigned_dataframe(
    result: PlanningResult,
    jobs_by_id: dict[str, JobRecord],
) -> pd.DataFrame:
    """Таблица неназначенных заявок: заявка, приоритет, причина."""
    rows = []

    for item in result.plan.unassigned:
        job = jobs_by_id.get(item.job_id)

        rows.append(
            {
                "Заявка": item.job_id,
                "Тип работы": job.work_type if job else "—",
                "Приоритет": (job.priority if job else None) or "—",
                "Зона": job.service_zone if job else "—",
                "Причина": item.message,
                "reason_code": item.reason_code.value,
            }
        )

    return pd.DataFrame(rows)


def stops_dataframe(
    engineer: Engineer,
    result: PlanningResult,
    jobs_by_id: dict[str, JobRecord],
    travel: TravelMatrix,
) -> pd.DataFrame:
    """Таблица остановок маршрута бригады."""
    route = next(
        (
            route
            for route in result.plan.routes
            if route.engineer_id == engineer.id
        ),
        None,
    )

    if route is None:
        return pd.DataFrame()

    rows = []
    prev_location_id = engineer.start_location_id

    for index, stop in enumerate(route.stops, start=1):
        job = jobs_by_id.get(stop.job_id)
        travel_min = travel_min_from_prev(
            travel,
            engineer,
            prev_location_id,
            stop.location_id,
        )

        rows.append(
            {
                "№": index,
                "Заявка": stop.job_id,
                "Тип работы": job.work_type if job else "—",
                "Адрес": stop.address or "—",
                "Прибытие": format_planned_time(stop.planned_arrival),
                "Начало": format_planned_time(stop.planned_start),
                "Окончание": format_planned_time(stop.planned_end),
                "Путь от предыдущей, мин": (
                    travel_min if travel_min is not None else "—"
                ),
            }
        )

        prev_location_id = stop.location_id

    return pd.DataFrame(rows)


def comparison_summary_dataframe(comparison: PlanComparison) -> pd.DataFrame:
    """Сводные метрики основного плана и baseline."""
    main = comparison.metrics["main"]
    baseline = comparison.metrics["baseline"]

    return pd.DataFrame(
        {
            "Показатель": [
                "Назначено",
                "Не назначено",
                "Задействовано бригад",
                "Суммарное время в пути, мин",
                "Суммарное расстояние, км",
            ],
            "Основной план": [
                main["assigned"],
                main["unassigned"],
                main["used_engineers"],
                main["total_travel_min"],
                main["total_distance_km"],
            ],
            "Baseline": [
                baseline["assigned"],
                baseline["unassigned"],
                baseline["used_engineers"],
                baseline["total_travel_min"],
                baseline["total_distance_km"],
            ],
        }
    )


def comparison_by_engineer_dataframe(
    comparison: PlanComparison,
    engineers_by_id: dict[str, Engineer],
) -> pd.DataFrame:
    """Расстояние/время по каждой бригаде в обоих планах."""
    rows = []

    for item in comparison.by_engineer:
        engineer = engineers_by_id.get(item["engineer_id"])

        rows.append(
            {
                "Бригада": item["engineer_id"],
                "Имя": engineer.name if engineer else "—",
                "Остановок (план)": item["main_stops"],
                "Остановок (baseline)": item["baseline_stops"],
                "Время в пути, мин (план)": item["main_travel_min"],
                "Время в пути, мин (baseline)": (
                    item["baseline_travel_min"]
                ),
                "Расстояние, км (план)": item["main_distance_km"],
                "Расстояние, км (baseline)": item["baseline_distance_km"],
            }
        )

    return pd.DataFrame(rows)


def errors_dataframe(bundle) -> pd.DataFrame:
    """Таблица ошибок импорта: файл, строка, поле, сообщение."""
    rows = []

    for error in bundle.errors:
        rows.append(
            {
                "Файл": error.file,
                "Строка": error.row if error.row is not None else "—",
                "Поле": error.field or "—",
                "Код": error.code,
                "Сообщение": error.message,
                "Можно пропустить": "да" if error.can_skip else "нет",
            }
        )

    return pd.DataFrame(rows)


def import_summary_dataframe(bundle) -> pd.DataFrame:
    """Сводка по файлам: строки, принято, пропущено, ошибки."""
    rows = []

    for report in bundle.reports:
        rows.append(
            {
                "Файл": report.filename,
                "Строк-заявок": report.rows_total,
                "Принято": report.jobs_imported,
                "Пропущено пустых": report.skipped_empty,
                "Пропущено офисных": report.skipped_office,
                "Ошибок": report.error_count,
            }
        )

    return pd.DataFrame(rows)