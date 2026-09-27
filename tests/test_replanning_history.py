"""Приёмочные тесты перепланирования: сохранность истории и временная граница.

Сценарий «инженер стал недоступен»:

    * событие посреди работы недоступного инженера отклоняется
      (заявка 75881 у ENG-5 выполняется 14:00–15:10, событие в 15:00
      не строит план и предлагает время не раньше 15:10);
    * событие после окончания работы строит план; завершённые работы
      всех бригад сохраняют исполнителей и времена (86002 остаётся
      у ENG-4 в прежнее время);
    * ни одна новая остановка не начинается до времени события;
      путь считается от фактической последней зафиксированной точки;
    * освобождённая заявка либо назначена в допустимое окно, либо
      получает причину неназначения;
    * PlanValidator и проверка сохранности истории дают 0 нарушений.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from src.models.entities import (
    Assignment,
    Engineer,
    JobRecord,
    Plan,
    Route,
    RouteStop,
    TravelMatrixEntry,
    UnassignedJob,
)
from src.models.enums import TransportType, UnassignmentReason
from src.optimizer.route_planner import RoutePlanner
from src.optimizer.scheduling import schedule_continuation
from src.optimizer.travel import TravelMatrix
from src.services.import_pipeline import load_input_directory
from src.services.planning import build_plan
from src.services.replanning import replan_after_unavailability
from src.validation.history_check import check_history_preservation
from src.validation.plan_validator import PlanValidator

MOSCOW = timezone(timedelta(hours=3))

DEMO_DATE = datetime(2026, 8, 17, tzinfo=MOSCOW)


def _entry(origin: str, destination: str, travel_min: int) -> TravelMatrixEntry:
    return TravelMatrixEntry(
        origin_location_id=origin,
        destination_location_id=destination,
        transport_type=TransportType.CAR,
        travel_min=travel_min,
        distance_km=round(travel_min / 60 * 28, 1),
        matrix_version="replan-history-v1",
    )


MATRIX_ENTRIES = [
    _entry("DEPOT", "LOC-A", 10),
    _entry("LOC-A", "DEPOT", 10),
    _entry("DEPOT", "LOC-B", 10),
    _entry("LOC-B", "DEPOT", 10),
    _entry("DEPOT", "LOC-C", 15),
    _entry("LOC-C", "DEPOT", 15),
    _entry("LOC-A", "LOC-B", 5),
    _entry("LOC-B", "LOC-A", 5),
    _entry("LOC-B", "LOC-C", 5),
    _entry("LOC-C", "LOC-B", 5),
    _entry("LOC-A", "LOC-C", 10),
    _entry("LOC-C", "LOC-A", 10),
]


def _job(
    job_id: str,
    start: str,
    end: str,
    location_id: str,
    duration: int = 30,
) -> JobRecord:
    return JobRecord(
        id=job_id,
        source_bk_type="Подключение",
        work_type="CONNECTION",
        service_zone="Восток",
        address=f"Адрес {job_id}",
        service_duration_min=duration,
        source_filename="Восток Синтетические данные.csv",
        window_start=datetime.fromisoformat(start),
        window_end=datetime.fromisoformat(end),
        location_id=location_id,
        required_equipment=["INSTALLATION_KIT"],
        status="NEW",
    )


def _engineer(engineer_id: str) -> Engineer:
    return Engineer(
        id=engineer_id,
        name=f"Бригада {engineer_id}",
        transport_type=TransportType.CAR,
        start_location_id="DEPOT",
        shift_start=datetime(2026, 8, 17, 9, 0, tzinfo=MOSCOW),
        shift_end=datetime(2026, 8, 17, 18, 0, tzinfo=MOSCOW),
        service_districts=["Восток"],
        allowed_work_types=[
            "CONNECTION",
            "LOCAL_WORK",
            "ADD_ORDER",
            "EMERGENCY",
        ],
        equipment_ids=["INSTALLATION_KIT"],
    )


def _bundle(jobs, engineers):
    return SimpleNamespace(
        jobs=jobs,
        engineers=engineers,
        travel_matrix=MATRIX_ENTRIES,
        errors=[],
        locations=[],
    )


def _stop(job_id, location_id, arrival, start, end) -> RouteStop:
    return RouteStop(
        job_id=job_id,
        location_id=location_id,
        planned_arrival=datetime.fromisoformat(arrival),
        planned_start=datetime.fromisoformat(start),
        planned_end=datetime.fromisoformat(end),
        address=f"Адрес {job_id}",
    )


def _old_plan() -> Plan:
    """Демо-структура: ENG-4 (86002 завершена) и ENG-5 (75881 до 15:10)."""
    return Plan(
        assignments=[
            Assignment(job_id="86002", engineer_id="ENG-4"),
            Assignment(job_id="88888", engineer_id="ENG-4"),
            Assignment(job_id="75881", engineer_id="ENG-5"),
            Assignment(job_id="99999", engineer_id="ENG-5"),
        ],
        routes=[
            Route(
                engineer_id="ENG-4",
                stops=[
                    _stop(
                        "86002",
                        "LOC-B",
                        "2026-08-17T13:34:00+03:00",
                        "2026-08-17T14:00:00+03:00",
                        "2026-08-17T14:30:00+03:00",
                    ),
                    _stop(
                        "88888",
                        "LOC-B",
                        "2026-08-17T14:47:00+03:00",
                        "2026-08-17T16:00:00+03:00",
                        "2026-08-17T16:30:00+03:00",
                    ),
                ],
                total_travel_min=15,
                total_distance_km=7.0,
            ),
            Route(
                engineer_id="ENG-5",
                stops=[
                    _stop(
                        "75881",
                        "LOC-A",
                        "2026-08-17T13:51:00+03:00",
                        "2026-08-17T14:00:00+03:00",
                        "2026-08-17T15:10:00+03:00",
                    ),
                    _stop(
                        "99999",
                        "LOC-C",
                        "2026-08-17T15:15:00+03:00",
                        "2026-08-17T16:00:00+03:00",
                        "2026-08-17T16:30:00+03:00",
                    ),
                ],
                total_travel_min=20,
                total_distance_km=9.0,
            ),
        ],
        unassigned_job_ids=[],
        status="VALID",
    )


def _demo_jobs() -> list[JobRecord]:
    return [
        _job(
            "75881",
            "2026-08-17T13:00:00+03:00",
            "2026-08-17T16:00:00+03:00",
            "LOC-A",
            duration=70,
        ),
        _job(
            "86002",
            "2026-08-17T13:00:00+03:00",
            "2026-08-17T15:00:00+03:00",
            "LOC-B",
        ),
        _job(
            "99999",
            "2026-08-17T16:00:00+03:00",
            "2026-08-17T17:00:00+03:00",
            "LOC-C",
        ),
        _job(
            "88888",
            "2026-08-17T16:00:00+03:00",
            "2026-08-17T17:00:00+03:00",
            "LOC-B",
        ),
    ]


def _at(hour: int, minute: int = 0) -> datetime:
    return DEMO_DATE.replace(hour=hour, minute=minute)


# --- Приёмочные сценарии ----------------------------------------------------


def test_event_mid_work_is_rejected_with_suggested_time():
    """Событие ENG-5 в 15:00 отклоняется: 75881 выполняется до 15:10."""
    jobs = _demo_jobs()
    engineers = [_engineer("ENG-4"), _engineer("ENG-5"), _engineer("ENG-10")]
    bundle = _bundle(jobs, engineers)
    old_plan = _old_plan()

    result = replan_after_unavailability(
        bundle,
        old_plan,
        engineer_id="ENG-5",
        event_time=_at(15, 0),
    )

    assert result.rejected is True
    assert result.suggested_time == _at(15, 10)
    assert "75881" in result.message
    assert "15:10" in result.message

    # План не строился: новый план совпадает со старым.
    assert result.new_plan is old_plan
    assert result.new_plan.status == old_plan.status

    # 86002 не тронута и остаётся у ENG-4.
    assignment = next(
        item for item in old_plan.assignments if item.job_id == "86002"
    )
    assert assignment.engineer_id == "ENG-4"


def test_event_after_work_builds_plan_and_keeps_completed_jobs():
    """Событие ENG-5 в 15:10 строит план; 86002 остаётся у ENG-4."""
    jobs = _demo_jobs()
    engineers = [_engineer("ENG-4"), _engineer("ENG-5"), _engineer("ENG-10")]
    bundle = _bundle(jobs, engineers)
    old_plan = _old_plan()

    result = replan_after_unavailability(
        bundle,
        old_plan,
        engineer_id="ENG-5",
        event_time=_at(15, 10),
    )

    assert result.rejected is False

    new_by_job = {
        assignment.job_id: assignment.engineer_id
        for assignment in result.new_plan.assignments
    }

    # 86002 завершена до события — остаётся у ENG-4 в прежние времена.
    assert new_by_job["86002"] == "ENG-4"

    new_route_eng4 = next(
        route
        for route in result.new_plan.routes
        if route.engineer_id == "ENG-4"
    )
    stop_86002 = next(
        stop for stop in new_route_eng4.stops if stop.job_id == "86002"
    )

    assert stop_86002.planned_arrival == datetime.fromisoformat(
        "2026-08-17T13:34:00+03:00"
    )
    assert stop_86002.planned_start == datetime.fromisoformat(
        "2026-08-17T14:00:00+03:00"
    )
    assert stop_86002.planned_end == datetime.fromisoformat(
        "2026-08-17T14:30:00+03:00"
    )

    # 75881 завершена ровно к событию — остаётся у ENG-5.
    assert new_by_job["75881"] == "ENG-5"

    # Будущая заявка ENG-5 освобождена в пул.
    assert result.released_job_ids == ["99999"]

    # Освобождённая заявка либо назначена, либо получила причину.
    assigned_ids = set(new_by_job)
    unassigned_ids = {item.job_id for item in result.new_plan.unassigned}

    assert "99999" in assigned_ids or "99999" in unassigned_ids


def test_completed_works_of_all_crews_preserve_executors_and_times():
    """Завершённые работы всех бригад сохраняют исполнителей и времена."""
    jobs = _demo_jobs()
    engineers = [_engineer("ENG-4"), _engineer("ENG-5"), _engineer("ENG-10")]
    bundle = _bundle(jobs, engineers)
    old_plan = _old_plan()

    result = replan_after_unavailability(
        bundle,
        old_plan,
        engineer_id="ENG-5",
        event_time=_at(15, 10),
    )

    event_time = _at(15, 10)
    new_stops_by_job = {
        stop.job_id: (route.engineer_id, stop)
        for route in result.new_plan.routes
        for stop in route.stops
    }

    for route in old_plan.routes:
        for stop in route.stops:
            if stop.planned_end > event_time:
                continue

            entry = new_stops_by_job.get(stop.job_id)

            assert entry is not None, (
                f"Работа {stop.job_id} исчезла из нового плана"
            )

            new_engineer_id, new_stop = entry

            assert new_engineer_id == route.engineer_id
            assert new_stop.planned_arrival == stop.planned_arrival
            assert new_stop.planned_start == stop.planned_start
            assert new_stop.planned_end == stop.planned_end


def test_no_new_stop_starts_before_event_time():
    """Ни одна новая остановка не начинается до времени события."""
    jobs = _demo_jobs()
    engineers = [_engineer("ENG-4"), _engineer("ENG-5"), _engineer("ENG-10")]
    bundle = _bundle(jobs, engineers)
    old_plan = _old_plan()

    event_time = _at(15, 10)

    result = replan_after_unavailability(
        bundle,
        old_plan,
        engineer_id="ENG-5",
        event_time=event_time,
    )

    preserved = {
        stop.job_id
        for route in old_plan.routes
        for stop in route.stops
        if stop.planned_start <= event_time
    }

    for route in result.new_plan.routes:
        for stop in route.stops:
            if stop.job_id in preserved:
                continue

            assert stop.planned_start >= event_time, (
                f"Новая остановка {stop.job_id} у {route.engineer_id} "
                f"начинается {stop.planned_start.isoformat()} раньше события"
            )


def test_history_check_and_validator_have_zero_violations():
    """PlanValidator и проверка сохранности истории дают 0 нарушений."""
    jobs = _demo_jobs()
    engineers = [_engineer("ENG-4"), _engineer("ENG-5"), _engineer("ENG-10")]
    bundle = _bundle(jobs, engineers)
    old_plan = _old_plan()

    result = replan_after_unavailability(
        bundle,
        old_plan,
        engineer_id="ENG-5",
        event_time=_at(15, 10),
    )

    assert result.history_issues == []
    assert result.validator_issues == []
    assert result.issues == []
    assert result.new_plan.status == "VALID"

    # Дублируем независимую проверку на итоговом плане.
    travel = TravelMatrix(MATRIX_ENTRIES)
    assert (
        check_history_preservation(old_plan, result.new_plan, _at(15, 10))
        == []
    )
    assert (
        PlanValidator(travel).validate(
            result.new_plan,
            jobs,
            engineers,
        )
        == []
    )


# --- Единичные проверки новых примитивов ------------------------------------


def test_schedule_continuation_starts_from_cursor():
    """Продолжение считается от cursor_time/cursor_location."""
    job = _job(
        "9001",
        "2026-08-17T16:00:00+03:00",
        "2026-08-17T17:00:00+03:00",
        "LOC-B",
    )
    engineer = _engineer("ENG-X")
    travel = TravelMatrix(MATRIX_ENTRIES)

    stops, reason = schedule_continuation(
        travel,
        [job],
        engineer,
        cursor_time=_at(15, 0),
        cursor_location="LOC-A",
    )

    assert reason is None
    assert stops[0].planned_arrival == _at(15, 5)  # LOC-A -> LOC-B = 5 мин
    assert stops[0].planned_start == _at(16, 0)  # окно клиента
    assert stops[0].planned_end == _at(16, 30)


def test_route_planner_builds_prefix_plus_continuation():
    """Маршрут = зафиксированный префикс + продолжение от курсора."""
    prefix = [
        _stop(
            "9001",
            "LOC-A",
            "2026-08-17T09:30:00+03:00",
            "2026-08-17T09:30:00+03:00",
            "2026-08-17T10:00:00+03:00",
        )
    ]
    job = _job(
        "9002",
        "2026-08-17T16:00:00+03:00",
        "2026-08-17T17:00:00+03:00",
        "LOC-B",
    )
    engineer = _engineer("ENG-X")
    travel = TravelMatrix(MATRIX_ENTRIES)

    plan = RoutePlanner(travel).build_plan(
        [job],
        [engineer],
        fixed_prefixes={"ENG-X": prefix},
        cursor_times={"ENG-X": _at(15, 0)},
        cursor_locations={"ENG-X": "LOC-A"},
    )

    route = plan.routes[0]

    assert [stop.job_id for stop in route.stops] == ["9001", "9002"]

    continuation = route.stops[1]
    assert continuation.planned_arrival == _at(15, 5)
    assert continuation.planned_start >= _at(15, 0)


def test_history_check_flags_changed_completed_work():
    """Проверка истории ловит изменение завершённой работы."""
    old_plan = _old_plan()

    changed = Plan(
        assignments=[
            Assignment(job_id="86002", engineer_id="ENG-10"),
            Assignment(job_id="88888", engineer_id="ENG-4"),
            Assignment(job_id="75881", engineer_id="ENG-5"),
            Assignment(job_id="99999", engineer_id="ENG-5"),
        ],
        routes=[
            Route(
                engineer_id="ENG-10",
                stops=[
                    _stop(
                        "86002",
                        "LOC-B",
                        "2026-08-17T15:16:00+03:00",
                        "2026-08-17T15:26:00+03:00",
                        "2026-08-17T15:56:00+03:00",
                    )
                ],
                total_travel_min=5,
                total_distance_km=2.0,
            ),
            Route(
                engineer_id="ENG-4",
                stops=[
                    _stop(
                        "88888",
                        "LOC-B",
                        "2026-08-17T14:47:00+03:00",
                        "2026-08-17T16:00:00+03:00",
                        "2026-08-17T16:30:00+03:00",
                    )
                ],
                total_travel_min=10,
                total_distance_km=5.0,
            ),
            Route(
                engineer_id="ENG-5",
                stops=[
                    _stop(
                        "75881",
                        "LOC-A",
                        "2026-08-17T13:51:00+03:00",
                        "2026-08-17T14:00:00+03:00",
                        "2026-08-17T15:10:00+03:00",
                    ),
                    _stop(
                        "99999",
                        "LOC-C",
                        "2026-08-17T15:15:00+03:00",
                        "2026-08-17T16:00:00+03:00",
                        "2026-08-17T16:30:00+03:00",
                    ),
                ],
                total_travel_min=20,
                total_distance_km=9.0,
            ),
        ],
        unassigned_job_ids=[],
        status="VALID",
    )

    issues = check_history_preservation(old_plan, changed, _at(15, 10))

    codes = {issue.code for issue in issues}

    assert "HISTORY_CHANGED" in codes
    assert any("86002" in issue.message for issue in issues)


def test_history_check_flags_past_assignment():
    """Проверка истории ловит новую работу, назначенную в прошлое."""
    old_plan = _old_plan()

    bad = Plan(
        assignments=[
            Assignment(job_id="86002", engineer_id="ENG-4"),
            Assignment(job_id="88888", engineer_id="ENG-4"),
            Assignment(job_id="75881", engineer_id="ENG-5"),
            Assignment(job_id="99999", engineer_id="ENG-5"),
            Assignment(job_id="77777", engineer_id="ENG-10"),
        ],
        routes=[
            Route(
                engineer_id="ENG-4",
                stops=[
                    _stop(
                        "86002",
                        "LOC-B",
                        "2026-08-17T13:34:00+03:00",
                        "2026-08-17T14:00:00+03:00",
                        "2026-08-17T14:30:00+03:00",
                    ),
                    _stop(
                        "88888",
                        "LOC-B",
                        "2026-08-17T14:47:00+03:00",
                        "2026-08-17T16:00:00+03:00",
                        "2026-08-17T16:30:00+03:00",
                    ),
                ],
                total_travel_min=15,
                total_distance_km=7.0,
            ),
            Route(
                engineer_id="ENG-5",
                stops=[
                    _stop(
                        "75881",
                        "LOC-A",
                        "2026-08-17T13:51:00+03:00",
                        "2026-08-17T14:00:00+03:00",
                        "2026-08-17T15:10:00+03:00",
                    ),
                    _stop(
                        "99999",
                        "LOC-C",
                        "2026-08-17T15:15:00+03:00",
                        "2026-08-17T16:00:00+03:00",
                        "2026-08-17T16:30:00+03:00",
                    ),
                ],
                total_travel_min=20,
                total_distance_km=9.0,
            ),
            Route(
                engineer_id="ENG-10",
                stops=[
                    _stop(
                        "77777",
                        "LOC-B",
                        "2026-08-17T15:05:00+03:00",
                        "2026-08-17T15:05:00+03:00",
                        "2026-08-17T15:35:00+03:00",
                    )
                ],
                total_travel_min=10,
                total_distance_km=5.0,
            ),
        ],
        unassigned_job_ids=[],
        status="VALID",
    )

    issues = check_history_preservation(old_plan, bad, _at(15, 10))

    assert any(
        issue.code == "PAST_ASSIGNMENT" and "77777" in issue.message
        for issue in issues
    )


# --- Интеграция на официальном демонстрационном наборе ----------------------

OFFICIAL_INPUT_DIR = Path("data/input")


def test_official_demo_scenario_eng5_at_1510():
    """Демо-набор: ENG-5 в 15:10 строит план, 86002 остаётся у ENG-4.

    Полный сценарий на официальных синтетических данных: заявки
    75881 (ENG-5, 14:00–15:10) и 86002 (ENG-4, 14:00–14:30) не меняют
    исполнителей и времена; все завершённые работы всех бригад
    сохраняются; нарушений 0.
    """
    bundle = load_input_directory(OFFICIAL_INPUT_DIR)
    plan = build_plan(bundle)

    # Контроль демо-структуры до события.
    old_86002 = _find_stop(plan, "86002")
    old_75881 = _find_stop(plan, "75881")

    assert old_86002[0] == "ENG-4"
    assert old_86002[1].planned_start == datetime.fromisoformat(
        "2026-08-17T14:00:00+03:00"
    )
    assert old_86002[1].planned_end == datetime.fromisoformat(
        "2026-08-17T14:30:00+03:00"
    )

    assert old_75881[0] == "ENG-5"
    assert old_75881[1].planned_start == datetime.fromisoformat(
        "2026-08-17T14:00:00+03:00"
    )
    assert old_75881[1].planned_end == datetime.fromisoformat(
        "2026-08-17T15:10:00+03:00"
    )

    # Событие посреди работы отклоняется.
    rejected = replan_after_unavailability(
        bundle,
        plan,
        engineer_id="ENG-5",
        event_time=_at(15, 0),
    )

    assert rejected.rejected is True
    assert rejected.suggested_time == datetime.fromisoformat(
        "2026-08-17T15:10:00+03:00"
    )

    # Событие после окончания работы строит корректный план.
    result = replan_after_unavailability(
        bundle,
        plan,
        engineer_id="ENG-5",
        event_time=_at(15, 10),
    )

    assert result.rejected is False

    new_86002 = _find_stop(result.new_plan, "86002")
    new_75881 = _find_stop(result.new_plan, "75881")

    assert new_86002[0] == "ENG-4"
    assert new_86002[1].planned_start == old_86002[1].planned_start
    assert new_86002[1].planned_end == old_86002[1].planned_end

    assert new_75881[0] == "ENG-5"
    assert new_75881[1].planned_start == old_75881[1].planned_start
    assert new_75881[1].planned_end == old_75881[1].planned_end

    # Все завершённые работы всех бригад сохранены без изменений.
    for route in plan.routes:
        for stop in route.stops:
            if stop.planned_end > _at(15, 10):
                continue

            new_entry = _find_stop(result.new_plan, stop.job_id)

            assert new_entry is not None
            assert new_entry[0] == route.engineer_id
            assert new_entry[1].planned_arrival == stop.planned_arrival
            assert new_entry[1].planned_start == stop.planned_start
            assert new_entry[1].planned_end == stop.planned_end

    # Ни одна новая остановка не начинается до времени события.
    preserved = {
        stop.job_id
        for route in plan.routes
        for stop in route.stops
        if stop.planned_start <= _at(15, 10)
    }

    for route in result.new_plan.routes:
        for stop in route.stops:
            if stop.job_id in preserved:
                continue

            assert stop.planned_start >= _at(15, 10)

    # Освобождённые заявки ENG-5: назначены или с причиной.
    assigned_ids = {
        assignment.job_id for assignment in result.new_plan.assignments
    }
    unassigned_ids = {
        item.job_id for item in result.new_plan.unassigned
    }

    for job_id in result.released_job_ids:
        assert job_id in assigned_ids or job_id in unassigned_ids

    # PlanValidator и проверка сохранности истории — 0 нарушений.
    assert result.issues == []
    assert result.new_plan.status == "VALID"


def _find_stop(plan: Plan, job_id: str):
    for route in plan.routes:
        for stop in route.stops:
            if stop.job_id == job_id:
                return route.engineer_id, stop

    return None