from enum import StrEnum


class TransportType(StrEnum):
    """Типы транспорта бригады (поддерживаются матрицей перемещений)."""

    CAR = "CAR"
    WALK = "WALK"
    BICYCLE = "BICYCLE"
    PUBLIC_TRANSPORT = "PUBLIC_TRANSPORT"


class Skill(StrEnum):
    ELECTRIC = "ELECTRIC"
    NETWORK = "NETWORK"
    MECHANIC = "MECHANIC"


class JobPriority(StrEnum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    URGENT = "URGENT"


class AssignmentStatus(StrEnum):
    ASSIGNED = "ASSIGNED"
    UNASSIGNED = "UNASSIGNED"


class UnassignmentReason(StrEnum):
    NO_QUALIFIED_ENGINEER = "NO_QUALIFIED_ENGINEER"
    NO_TIME_WINDOW = "NO_TIME_WINDOW"
    SHIFT_CONFLICT = "SHIFT_CONFLICT"
    NO_TRAVEL_DATA = "NO_TRAVEL_DATA"
    NO_FEASIBLE_INSERTION = "NO_FEASIBLE_INSERTION"
    OPTIMIZER_LIMIT = "OPTIMIZER_LIMIT"