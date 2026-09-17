from enum import StrEnum


class TransportType(StrEnum):
    CAR = "CAR"
    TRUCK = "TRUCK"
    MOTORCYCLE = "MOTORCYCLE"


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
    OPTIMIZER_LIMIT = "OPTIMIZER_LIMIT"