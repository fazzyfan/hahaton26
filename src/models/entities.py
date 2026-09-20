from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from .enums import JobPriority, Skill, TransportType


class Engineer(BaseModel):
    id: str
    name: str
    transport_type: TransportType
    qualifications: list[Skill]

    start_location_id: str

    shift_start: datetime
    shift_end: datetime


class Job(BaseModel):
    id: str
    title: str

    location_id: str

    required_skill: Skill
    priority: JobPriority

    window_start: datetime
    window_end: datetime

    service_duration_min: int

class TravelMatrixEntry(BaseModel):
    origin_location_id: str
    destination_location_id: str
    transport_type: TransportType

    travel_min: int
    distance_km: float

    matrix_version: str


class Assignment(BaseModel):
    job_id: str
    engineer_id: str



class RouteStop(BaseModel):
    job_id: str
    location_id: str

    planned_arrival: datetime
    planned_start: datetime
    planned_end: datetime



class Route(BaseModel):
    engineer_id: str
    stops: list[RouteStop]

    total_travel_min: int
    total_distance_km: float



class Plan(BaseModel):
    assignments: list[Assignment]
    routes: list[Route]

    unassigned_job_ids: list[str]

    status: str


class ValidationIssue(BaseModel):
    code: str
    message: str

    entity_type: str
    entity_id: str | None = None

    field: str | None = None



class ReplanningEvent(BaseModel):
    event_id: str
    job_id: str

    old_plan_id: str | None = None
    new_plan_id: str | None = None

    reason: str


class JobRecord(BaseModel):
    """
    Канонический контракт заявки после нормализации CSV-импорта.

    Поля received_at, priority, status, gigabit_connection,
    required_equipment пока не заполняются импортёром —
    их источники станут известны после появления реальных CSV.
    """

    id: str
    source_bk_type: str
    source_hd_type: str | None = None
    work_type: str
    service_zone: str
    district: str | None = None
    address: str

    window_start: datetime | None = None
    window_end: datetime | None = None
    received_at: datetime | None = None

    service_duration_min: int

    priority: str | None = None
    status: str | None = None
    gigabit_connection: bool | None = None
    required_equipment: list[str] = Field(default_factory=list)

    source_filename: str
    source_row: int | None = None

    @field_validator("window_start", "window_end", "received_at")
    @classmethod
    def datetime_must_be_timezone_aware(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("datetime должен быть с часовым поясом")

        return value