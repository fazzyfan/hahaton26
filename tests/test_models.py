from datetime import datetime

from src.models.entities import Engineer, Job
from src.models.enums import JobPriority, Skill, TransportType


def test_engineer():
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
    assert engineer.transport_type == TransportType.CAR
    assert Skill.ELECTRIC in engineer.qualifications


def test_job():
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
    assert job.priority == JobPriority.URGENT
    assert job.service_duration_min == 60