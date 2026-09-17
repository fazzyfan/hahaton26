from datetime import datetime

from src.models.entities import Engineer, Job
from src.models.enums import JobPriority, Skill, TransportType
from src.optimizer.compatibility import CompatibilityService


def create_job(skill: Skill) -> Job:
    return Job(
        id="JOB-TEST",
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


def test_engineer_is_compatible_with_required_skill():
    service = CompatibilityService()

    job = create_job(Skill.ELECTRIC)

    engineer = create_engineer(
        "ENG-001",
        [Skill.ELECTRIC, Skill.NETWORK],
    )

    assert service.is_compatible(job, engineer) is True


def test_engineer_is_not_compatible_without_required_skill():
    service = CompatibilityService()

    job = create_job(Skill.MECHANIC)

    engineer = create_engineer(
        "ENG-001",
        [Skill.ELECTRIC, Skill.NETWORK],
    )

    assert service.is_compatible(job, engineer) is False


def test_get_compatible_engineers():
    service = CompatibilityService()

    job = create_job(Skill.ELECTRIC)

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

    compatible = service.get_compatible_engineers(
        job,
        engineers,
    )

    assert [engineer.id for engineer in compatible] == [
        "ENG-001",
        "ENG-003",
    ]