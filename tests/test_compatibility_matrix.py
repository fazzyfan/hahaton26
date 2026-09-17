from datetime import datetime

from src.models.entities import Engineer, Job
from src.models.enums import JobPriority, Skill, TransportType
from src.optimizer.compatibility_matrix import CompatibilityMatrix


def create_job(job_id: str, skill: Skill) -> Job:
    return Job(
        id=job_id,
        title="Тестовая заявка",
        location_id="LOC-A",
        required_skill=skill,
        priority=JobPriority.NORMAL,
        window_start=datetime(2026, 9, 17, 9, 0),
        window_end=datetime(2026, 9, 17, 13, 0),
        service_duration_min=60,
    )


def create_engineer(
    engineer_id: str,
    qualifications: list[Skill],
) -> Engineer:
    return Engineer(
        id=engineer_id,
        name="Тестовый инженер",
        transport_type=TransportType.CAR,
        qualifications=qualifications,
        start_location_id="DEPOT",
        shift_start=datetime(2026, 9, 17, 8, 0),
        shift_end=datetime(2026, 9, 17, 17, 0),
    )


def test_build_compatibility_matrix():
    jobs = [
        create_job("JOB-001", Skill.ELECTRIC),
        create_job("JOB-002", Skill.MECHANIC),
    ]

    engineers = [
        create_engineer(
            "ENG-001",
            [Skill.ELECTRIC, Skill.NETWORK],
        ),
        create_engineer(
            "ENG-002",
            [Skill.MECHANIC],
        ),
        create_engineer(
            "ENG-003",
            [Skill.ELECTRIC],
        ),
    ]

    matrix = CompatibilityMatrix()

    result = matrix.build(jobs, engineers)

    assert result == {
        "JOB-001": ["ENG-001", "ENG-003"],
        "JOB-002": ["ENG-002"],
    }