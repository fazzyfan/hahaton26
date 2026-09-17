from datetime import datetime

from src.models.entities import (
    Assignment,
    Engineer,
    Job,
    Plan,
    ReplanningEvent,
    Route,
    RouteStop,
    TravelMatrixEntry,
    ValidationIssue,
)
from src.models.enums import JobPriority, Skill, TransportType


def test_travel_matrix_entry():
    entry = TravelMatrixEntry(
        origin_location_id="LOC-A",
        destination_location_id="LOC-B",
        transport_type=TransportType.CAR,
        travel_min=30,
        distance_km=15.5,
        matrix_version="v1",
    )

    assert entry.origin_location_id == "LOC-A"
    assert entry.destination_location_id == "LOC-B"
    assert entry.transport_type == TransportType.CAR
    assert entry.travel_min == 30
    assert entry.distance_km == 15.5
    assert entry.matrix_version == "v1"


def test_assignment():
    assignment = Assignment(
        job_id="JOB-001",
        engineer_id="ENG-001",
    )

    assert assignment.job_id == "JOB-001"
    assert assignment.engineer_id == "ENG-001"


def test_route_stop():
    stop = RouteStop(
        job_id="JOB-001",
        location_id="LOC-A",
        planned_arrival=datetime(2026, 9, 17, 10, 0),
        planned_start=datetime(2026, 9, 17, 10, 10),
        planned_end=datetime(2026, 9, 17, 11, 10),
    )

    assert stop.job_id == "JOB-001"
    assert stop.location_id == "LOC-A"
    assert stop.planned_arrival.hour == 10
    assert stop.planned_start.minute == 10
    assert stop.planned_end.minute == 10


def test_route():
    stop = RouteStop(
        job_id="JOB-001",
        location_id="LOC-A",
        planned_arrival=datetime(2026, 9, 17, 10, 0),
        planned_start=datetime(2026, 9, 17, 10, 10),
        planned_end=datetime(2026, 9, 17, 11, 10),
    )

    route = Route(
        engineer_id="ENG-001",
        stops=[stop],
        total_travel_min=30,
        total_distance_km=15.5,
    )

    assert route.engineer_id == "ENG-001"
    assert len(route.stops) == 1
    assert route.total_travel_min == 30
    assert route.total_distance_km == 15.5


def test_plan():
    assignment = Assignment(
        job_id="JOB-001",
        engineer_id="ENG-001",
    )

    plan = Plan(
        assignments=[assignment],
        routes=[],
        unassigned_job_ids=["JOB-002"],
        status="VALID",
    )

    assert len(plan.assignments) == 1
    assert plan.assignments[0].job_id == "JOB-001"
    assert plan.unassigned_job_ids == ["JOB-002"]
    assert plan.status == "VALID"


def test_validation_issue():
    issue = ValidationIssue(
        code="INVALID_ID",
        message="Invalid job ID",
        entity_type="Job",
        entity_id="JOB-001",
        field="id",
    )

    assert issue.code == "INVALID_ID"
    assert issue.entity_type == "Job"
    assert issue.entity_id == "JOB-001"
    assert issue.field == "id"


def test_replanning_event():
    event = ReplanningEvent(
        event_id="EVENT-001",
        job_id="JOB-001",
        old_plan_id="PLAN-001",
        new_plan_id="PLAN-002",
        reason="Urgent job added",
    )

    assert event.event_id == "EVENT-001"
    assert event.job_id == "JOB-001"
    assert event.old_plan_id == "PLAN-001"
    assert event.new_plan_id == "PLAN-002"
    assert event.reason == "Urgent job added"


def test_engineer_with_all_fields():
    engineer = Engineer(
        id="ENG-001",
        name="Ivan",
        transport_type=TransportType.CAR,
        qualifications=[
            Skill.ELECTRIC,
            Skill.NETWORK,
        ],
        start_location_id="DEPOT-A",
        shift_start=datetime(2026, 9, 17, 9, 0),
        shift_end=datetime(2026, 9, 17, 18, 0),
    )

    assert engineer.id == "ENG-001"
    assert engineer.name == "Ivan"
    assert engineer.transport_type == TransportType.CAR
    assert len(engineer.qualifications) == 2
    assert engineer.shift_start.hour == 9
    assert engineer.shift_end.hour == 18


def test_job_with_all_fields():
    job = Job(
        id="JOB-001",
        title="Repair equipment",
        location_id="LOC-A",
        required_skill=Skill.ELECTRIC,
        priority=JobPriority.URGENT,
        window_start=datetime(2026, 9, 17, 11, 0),
        window_end=datetime(2026, 9, 17, 14, 0),
        service_duration_min=60,
    )

    assert job.id == "JOB-001"
    assert job.title == "Repair equipment"
    assert job.location_id == "LOC-A"
    assert job.required_skill == Skill.ELECTRIC
    assert job.priority == JobPriority.URGENT
    assert job.service_duration_min == 60