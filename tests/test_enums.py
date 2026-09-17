from src.models.enums import TransportType, Skill, JobPriority


def test_transport_type():
    assert TransportType.CAR == "CAR"


def test_skill():
    assert Skill.ELECTRIC == "ELECTRIC"


def test_priority():
    assert JobPriority.URGENT == "URGENT"



from src.models.enums import AssignmentStatus, UnassignmentReason


def test_assignment_status_values():
    assert AssignmentStatus.ASSIGNED.value == "ASSIGNED"
    assert AssignmentStatus.UNASSIGNED.value == "UNASSIGNED"


def test_unassignment_reason_values():
    assert (
        UnassignmentReason.NO_QUALIFIED_ENGINEER.value
        == "NO_QUALIFIED_ENGINEER"
    )

    assert (
        UnassignmentReason.NO_TIME_WINDOW.value
        == "NO_TIME_WINDOW"
    )

    assert (
        UnassignmentReason.SHIFT_CONFLICT.value
        == "SHIFT_CONFLICT"
    )

    assert (
        UnassignmentReason.NO_TRAVEL_DATA.value
        == "NO_TRAVEL_DATA"
    )

    assert (
        UnassignmentReason.OPTIMIZER_LIMIT.value
        == "OPTIMIZER_LIMIT"
    )