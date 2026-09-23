from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from pydantic import ValidationError

from src.importers.csv_jobs import (
    ImportErrorItem,
    OfficeLocation,
    find_job_csv_files,
    load_jobs_file,
    normalize_job_row,
)
from src.importers.json_inputs import (
    load_engineers_file,
    load_equipment_file,
    load_locations_file,
    load_travel_matrix_file,
)
from src.models.entities import Engineer, Equipment, JobRecord, TravelMatrixEntry


@dataclass
class FileImportReport:
    """Отчёт по одному официальному CSV-файлу."""

    filename: str
    rows_total: int        # непустых строк-заявок (включая ошибочные)
    jobs_imported: int     # валидных JobRecord из этого файла
    skipped_empty: int
    skipped_office: int
    error_count: int


@dataclass
class InputBundle:
    """Единый результат загрузки всех входных данных."""

    jobs: list[JobRecord]
    engineers: list[Engineer]
    equipment: list[Equipment]
    travel_matrix: list[TravelMatrixEntry]

    errors: list[ImportErrorItem] = field(default_factory=list)
    office_locations: list[OfficeLocation] = field(default_factory=list)
    reports: list[FileImportReport] = field(default_factory=list)


# Единый PlanningInput: заявки, команды, оборудование и матрица времени.
PlanningInput = InputBundle


def _has_errors_for_row(
    errors: list[ImportErrorItem],
    row: dict,
) -> bool:
    """Возвращает True, если для CSV-строки уже зафиксирована ошибка."""
    filename = row.get("source_filename")
    row_number = row.get("source_row")

    return any(
        error.file == filename and error.row == row_number
        for error in errors
    )


def load_input_directory(input_dir: str | Path) -> InputBundle:
    """
    Загружает все входные данные из директории:

        data/input/
            <зона> Синтетические данные.csv  -> JobRecord[]
            engineers.json                    -> list[Engineer]
            equipment.json                    -> list[Equipment]
            travel_matrix.json                -> list[TravelMatrixEntry]

    Строки CSV с ошибками импорта в заявки не попадают,
    ошибки сохраняются в bundle.errors.
    """
    root = Path(input_dir)

    jobs: list[JobRecord] = []
    errors: list[ImportErrorItem] = []
    offices: list[OfficeLocation] = []
    reports: list[FileImportReport] = []

    for csv_path in find_job_csv_files(root):
        result = load_jobs_file(csv_path)

        errors.extend(result.errors)
        offices.extend(result.office_locations)

        jobs_before = len(jobs)

        for row in result.rows:
            if _has_errors_for_row(errors, row):
                continue

            try:
                record = JobRecord(**normalize_job_row(row))
            except ValidationError as error:
                errors.append(
                    ImportErrorItem(
                        code="INVALID_JOB_RECORD",
                        file=row.get("source_filename", ""),
                        row=row.get("source_row"),
                        entity_id=row.get("ID") or None,
                        field=None,
                        message=str(error),
                        can_skip=True,
                    )
                )
                continue

            jobs.append(record)

        reports.append(
            FileImportReport(
                filename=csv_path.name,
                rows_total=result.row_count,
                jobs_imported=len(jobs) - jobs_before,
                skipped_empty=result.skipped_empty,
                skipped_office=result.skipped_office,
                error_count=sum(1 for error in result.errors),
            )
        )

    engineers = load_engineers_file(root / "engineers.json")
    equipment = load_equipment_file(root / "equipment.json")
    travel_matrix = load_travel_matrix_file(root / "travel_matrix.json")

    # Опциональный реестр адресов -> location_id для travel matrix.
    locations_path = root / "locations.json"

    if locations_path.exists():
        locations = load_locations_file(locations_path)

        for job in jobs:
            if job.location_id is None:
                job.location_id = locations.get(job.address)

    return InputBundle(
        jobs=jobs,
        engineers=engineers,
        equipment=equipment,
        travel_matrix=travel_matrix,
        errors=errors,
        office_locations=offices,
        reports=reports,
    )