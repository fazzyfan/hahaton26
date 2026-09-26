import json
from pathlib import Path

from pydantic import ValidationError

from src.models.entities import Engineer, Job, ValidationIssue


class InputValidator:
    """Проверяет входной JSON с заявками и инженерами."""

    def load_json(self, file_path: str | Path) -> dict:
        """Читает JSON-файл и возвращает его содержимое."""

        path = Path(file_path)

        with path.open("r", encoding="utf-8") as file:
            return json.load(file)

    def validate(self, data: dict) -> tuple[list[Job], list[Engineer], list[ValidationIssue]]:
        """Проверяет JSON и возвращает модели и список ошибок."""

        issues: list[ValidationIssue] = []
        jobs: list[Job] = []
        engineers: list[Engineer] = []

        # Проверяем наличие обязательных разделов
        if "jobs" not in data:
            issues.append(
                ValidationIssue(
                    code="MISSING_SECTION",
                    message="Required section 'jobs' is missing",
                    entity_type="Input",
                    field="jobs",
                )
            )

        if "engineers" not in data:
            issues.append(
                ValidationIssue(
                    code="MISSING_SECTION",
                    message="Required section 'engineers' is missing",
                    entity_type="Input",
                    field="engineers",
                )
            )

        # Если раздела нет, дальше его проверять невозможно
        if "jobs" not in data:
            jobs_data = []
        else:
            jobs_data = data["jobs"]

        if "engineers" not in data:
            engineers_data = []
        else:
            engineers_data = data["engineers"]

        # Проверяем заявки
        if not isinstance(jobs_data, list):
            issues.append(
                ValidationIssue(
                    code="INVALID_TYPE",
                    message="'jobs' must be a list",
                    entity_type="Input",
                    field="jobs",
                )
            )
            jobs_data = []

        for item in jobs_data:
            try:
                job = Job.model_validate(item)
                jobs.append(job)
            except ValidationError as error:
                issues.extend(self._pydantic_issues(error, "Job", item))

        # Проверяем инженеров
        if not isinstance(engineers_data, list):
            issues.append(
                ValidationIssue(
                    code="INVALID_TYPE",
                    message="'engineers' must be a list",
                    entity_type="Input",
                    field="engineers",
                )
            )
            engineers_data = []

        for item in engineers_data:
            try:
                engineer = Engineer.model_validate(item)
                engineers.append(engineer)
            except ValidationError as error:
                issues.extend(self._pydantic_issues(error, "Engineer", item))

        # Проверяем уникальность ID
        issues.extend(self._check_unique_job_ids(jobs))
        issues.extend(self._check_unique_engineer_ids(engineers))

        # Проверяем временные интервалы
        issues.extend(self._check_job_times(jobs))
        issues.extend(self._check_engineer_shifts(engineers))

        # Пустые списки квалификаций/зон не должны означать
        # «разрешено всё».
        issues.extend(self._check_engineer_requirements(engineers))

        return jobs, engineers, issues

    def _pydantic_issues(
        self,
        error: ValidationError,
        entity_type: str,
        raw_data: dict,
    ) -> list[ValidationIssue]:
        """Преобразует ошибки Pydantic в наши ValidationIssue."""

        issues = []

        entity_id = raw_data.get("id") if isinstance(raw_data, dict) else None

        for error_item in error.errors():
            field = str(error_item["loc"][0])
            message = error_item["msg"]

            issues.append(
                ValidationIssue(
                    code="INVALID_FIELD",
                    message=message,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    field=field,
                )
            )

        return issues

    def _check_unique_job_ids(
        self,
        jobs: list[Job],
    ) -> list[ValidationIssue]:
        """Проверяет, что ID заявок не повторяются."""

        issues = []
        seen: set[str] = set()

        for job in jobs:
            if job.id in seen:
                issues.append(
                    ValidationIssue(
                        code="DUPLICATE_ID",
                        message=f"Duplicate job ID: {job.id}",
                        entity_type="Job",
                        entity_id=job.id,
                        field="id",
                    )
                )

            seen.add(job.id)

        return issues

    def _check_unique_engineer_ids(
        self,
        engineers: list[Engineer],
    ) -> list[ValidationIssue]:
        """Проверяет, что ID инженеров не повторяются."""

        issues = []
        seen: set[str] = set()

        for engineer in engineers:
            if engineer.id in seen:
                issues.append(
                    ValidationIssue(
                        code="DUPLICATE_ID",
                        message=f"Duplicate engineer ID: {engineer.id}",
                        entity_type="Engineer",
                        entity_id=engineer.id,
                        field="id",
                    )
                )

            seen.add(engineer.id)

        return issues

    def _check_job_times(
        self,
        jobs: list[Job],
    ) -> list[ValidationIssue]:
        """Проверяет временные окна заявок."""

        issues = []

        for job in jobs:
            if job.window_end <= job.window_start:
                issues.append(
                    ValidationIssue(
                        code="INVALID_TIME_WINDOW",
                        message="window_end must be after window_start",
                        entity_type="Job",
                        entity_id=job.id,
                        field="window_end",
                    )
                )

            if job.service_duration_min <= 0:
                issues.append(
                    ValidationIssue(
                        code="INVALID_SERVICE_DURATION",
                        message="service_duration_min must be greater than 0",
                        entity_type="Job",
                        entity_id=job.id,
                        field="service_duration_min",
                    )
                )

        return issues

    def _check_engineer_shifts(
        self,
        engineers: list[Engineer],
    ) -> list[ValidationIssue]:
        """Проверяет рабочие смены инженеров."""

        issues = []

        for engineer in engineers:
            if engineer.shift_end <= engineer.shift_start:
                issues.append(
                    ValidationIssue(
                        code="INVALID_SHIFT",
                        message="shift_end must be after shift_start",
                        entity_type="Engineer",
                        entity_id=engineer.id,
                        field="shift_end",
                    )
                )

        return issues

    def _check_engineer_requirements(
        self,
        engineers: list[Engineer],
    ) -> list[ValidationIssue]:
        """
        Пустые списки зон и допускаемых типов работ НЕ означают
        «разрешено всё»: такие бригады отклоняются.

        Допуск бригады задаётся единственным полем allowed_work_types;
        устаревшее поле qualifications (ELECTRIC/NETWORK/MECHANIC)
        не проверяется — по Data Contract v1.2 тестовые навыки заменены
        официальными типами работ из конфигурации.
        """

        issues = []

        for engineer in engineers:
            if not engineer.service_districts:
                issues.append(
                    ValidationIssue(
                        code="EMPTY_SERVICE_DISTRICTS",
                        message=(
                            "engineer must serve at least one district"
                        ),
                        entity_type="Engineer",
                        entity_id=engineer.id,
                        field="service_districts",
                    )
                )

            if not engineer.allowed_work_types:
                issues.append(
                    ValidationIssue(
                        code="EMPTY_ALLOWED_WORK_TYPES",
                        message=(
                            "engineer must support at least one work type"
                        ),
                        entity_type="Engineer",
                        entity_id=engineer.id,
                        field="allowed_work_types",
                    )
                )

        return issues