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
    load_locations_registry,
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

    # Полный реестр локаций (location_id, address, latitude, longitude)
    # для карты маршрутов; пустой, если locations.json не найден.
    locations: list[dict] = field(default_factory=list)


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


def _validate_engineers(
    engineers: list[Engineer],
) -> list[ImportErrorItem]:
    """
    Пустые списки зон обслуживания и допускаемых типов работ НЕ означают
    «разрешено всё»: такие бригады считаются фатальной ошибкой набора.

    Допуск бригады задаётся ЕДИНСТВЕННЫМ полем allowed_work_types
    (официальные типы работ из конфигурации). Устаревшее поле
    qualifications (ELECTRIC/NETWORK/MECHANIC) в проверке не участвует —
    по Data Contract v1.2 тестовые навыки заменены типами работ.
    """
    errors: list[ImportErrorItem] = []

    for engineer in engineers:
        empty_fields = []

        if not engineer.service_districts:
            empty_fields.append("service_districts")
        if not engineer.allowed_work_types:
            empty_fields.append("allowed_work_types")

        if empty_fields:
            errors.append(
                ImportErrorItem(
                    code="EMPTY_ENGINEER_CAPABILITIES",
                    file="engineers.json",
                    row=None,
                    entity_id=engineer.id,
                    field=", ".join(empty_fields),
                    message=(
                        f"У бригады {engineer.id!r} пустые списки: "
                        f"{', '.join(empty_fields)}. Пустой список не "
                        "означает «разрешено всё» — заполните данные."
                    ),
                    level="ERROR",
                    can_skip=False,
                )
            )

    return errors


def load_input_directory(
    input_dir: str | Path,
    skip_rows: set[tuple[str, int]] | None = None,
    csv_suffix: str = "Синтетические данные.csv",
    zone_override: dict[str, str] | None = None,
) -> InputBundle:
    """
    Загружает все входные данные из директории:

        data/input/
            <зона> Синтетические данные.csv  -> JobRecord[]
            engineers.json                    -> list[Engineer]
            equipment.json                    -> list[Equipment]
            locations.json                    -> реестр локаций (карта)
            travel_matrix.json                -> list[TravelMatrixEntry]

    Строки CSV с ошибками импорта в заявки не попадают,
    ошибки сохраняются в bundle.errors.

    skip_rows: набор (filename, source_row) строк, которые пользователь
    решил пропустить на этапе проверки (только для исправимых ошибок).

    csv_suffix: суффикс имён CSV-файлов заявок. Пользовательская загрузка
    через интерфейс может использовать произвольные имена — в этом случае
    передаётся csv_suffix="".

    zone_override: mapping имя_файла -> зона обслуживания. Используется
    интерфейсом, когда зона выбирается диспетчером вручную, а не берётся
    из имени файла.
    """
    root = Path(input_dir)

    skip_rows = skip_rows or set()
    zone_override = zone_override or {}

    jobs: list[JobRecord] = []
    errors: list[ImportErrorItem] = []
    offices: list[OfficeLocation] = []
    reports: list[FileImportReport] = []

    for csv_path in find_job_csv_files(root, suffix=csv_suffix):
        zone = zone_override.get(csv_path.name)
        result = load_jobs_file(csv_path, zone=zone)

        errors.extend(result.errors)
        offices.extend(result.office_locations)

        jobs_before = len(jobs)

        for row in result.rows:
            filename = row.get("source_filename", "")
            row_number = row.get("source_row")

            # Пользователь решил пропустить эту строку на этапе проверки.
            if (filename, row_number) in skip_rows:
                continue

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
    errors.extend(_validate_engineers(engineers))

    equipment = load_equipment_file(root / "equipment.json")

    locations: list[dict] = []
    locations_path = root / "locations.json"

    if locations_path.exists():
        locations = load_locations_registry(locations_path)
        addresses = {
            item["address"]: item["location_id"] for item in locations
        }

        for job in jobs:
            if job.location_id is None:
                job.location_id = addresses.get(job.address)

    travel_matrix_path = root / "travel_matrix.json"

    try:
        travel_matrix = load_travel_matrix_file(travel_matrix_path)
    except ValueError as error:
        # Дубликаты ключей матрицы блокируют расчёт с понятной ошибкой.
        errors.append(
            ImportErrorItem(
                code="DUPLICATE_MATRIX_KEY",
                file=travel_matrix_path.name,
                row=None,
                entity_id=None,
                field=None,
                message=str(error),
                level="ERROR",
                can_skip=False,
            )
        )
        travel_matrix = []

    # Пропущенные пользователем строки исключаются и из заявок, и из ошибок:
    # ошибка «пропущенной» строки больше не блокирует и не показывается.
    if skip_rows:
        errors = [
            error
            for error in errors
            if (error.file, error.row) not in skip_rows
        ]

    return InputBundle(
        jobs=jobs,
        engineers=engineers,
        equipment=equipment,
        travel_matrix=travel_matrix,
        errors=errors,
        office_locations=offices,
        reports=reports,
        locations=locations,
    )