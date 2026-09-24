from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from io import StringIO
from pathlib import Path
from zoneinfo import ZoneInfo

from src.config.loader import (
    get_required_equipment,
    get_work_type_priority,
    map_work_type,
)

MOSCOW_TZ = ZoneInfo("Europe/Moscow")
DATE_FORMAT = "%d.%m.%Y %H:%M"

# Логическая колонка -> допустимые имена заголовков.
# Официальные CSV используют «Заявка», «Начало», «Окончание»;
# легаси-формат (тесты/ранние данные) — «ID», «Начало окна», «Конец окна».
REQUIRED_ALIASES: dict[str, tuple[str, ...]] = {
    "Заявка": ("Заявка", "ID"),
    "Тип заявки BK": ("Тип заявки BK",),
    "Адрес": ("Адрес",),
}

DATE_COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "window_start": (
        "Начало",
        "Начало окна",
        "Дата начала окна",
        "Дата/время начала",
    ),
    "window_end": (
        "Окончание",
        "Конец окна",
    ),
}

NEW_CONTRACT_COLUMNS = {
    "Тип заявки HD",
    "Район",
}


@dataclass
class ImportErrorItem:
    code: str
    file: str
    row: int | None
    entity_id: str | None
    field: str | None
    message: str
    level: str = "ERROR"
    can_skip: bool = True


@dataclass
class ImportResult:
    rows: list[dict]
    errors: list[ImportErrorItem]
    office_locations: list[OfficeLocation]

    # Статистика для отчёта импорта.
    row_count: int = 0        # непустых строк-заявок (включая ошибочные)
    skipped_empty: int = 0    # полностью пустых физических строк
    skipped_office: int = 0   # строк «Адрес офиса»


@dataclass
class OfficeLocation:
    address: str
    source_filename: str
    source_row: int


def parse_moscow_datetime(value: str) -> datetime:
    """
    Преобразует дату формата DD.MM.YYYY HH:MM
    во временную метку с часовым поясом Europe/Moscow.
    """
    parsed = datetime.strptime(value.strip(), DATE_FORMAT)
    return parsed.replace(tzinfo=MOSCOW_TZ)


def parse_gigabit_flag(value: str) -> bool:
    """«Да» -> True, всё остальное («Нет») -> False."""
    return value.strip().lower() == "да"


def _normalize_key(key: str) -> str:
    return str(key).replace(" ", "").strip().lower()


def _get_column_value(
    row: dict,
    *names: str,
) -> tuple[str | None, str | None]:
    """Возвращает (значение, фактический ключ) по любому из имён колонки."""
    normalized = {
        _normalize_key(key): key
        for key in row
    }

    for name in names:
        key = normalized.get(_normalize_key(name))
        if key is not None:
            return row.get(key), key

    return None, None


def _missing_required_columns(headers: list[str]) -> set[str]:
    """Возвращает логические обязательные колонки без подходящего заголовка."""
    normalized_headers = {_normalize_key(header) for header in headers}
    missing: set[str] = set()

    for canonical, aliases in REQUIRED_ALIASES.items():
        if not any(_normalize_key(alias) in normalized_headers for alias in aliases):
            missing.add(canonical)

    return missing


def _get_job_id(row: dict) -> tuple[str | None, str | None]:
    return _get_column_value(row, "Заявка", "ID")


def load_jobs_bytes(data: bytes, filename: str) -> ImportResult:
    """
    Основная функция импорта CSV.

    Вход:
        data      — содержимое CSV в виде bytes
        filename  — имя исходного файла

    CSV:
        encoding = CP1251
        delimiter = ;

    Официальные колонки:
        Заявка;Тип заявки BK;Тип заявки HD;Начало;Окончание;Район;Адрес;
        [Подключение;]Гигабитное подключение
    """

    errors: list[ImportErrorItem] = []
    rows: list[dict] = []
    offices: list[OfficeLocation] = []

    row_count = 0
    skipped_empty = 0
    skipped_office = 0

    # 1. Проверяем кодировку.
    try:
        text = data.decode("cp1251")
    except UnicodeDecodeError:
        errors.append(
            ImportErrorItem(
                code="INVALID_ENCODING",
                file=filename,
                row=None,
                entity_id=None,
                field=None,
                message="Не удалось прочитать файл в кодировке Windows-1251.",
                can_skip=False,
            )
        )

        return ImportResult(rows=[], errors=errors)

    # 2. Создаём CSV reader.
    reader = csv.reader(
        StringIO(text),
        delimiter=";",
    )

    # 3. Получаем заголовок.
    try:
        headers = next(reader)
    except StopIteration:
        errors.append(
            ImportErrorItem(
                code="MISSING_HEADER",
                file=filename,
                row=1,
                entity_id=None,
                field=None,
                message="В CSV отсутствует строка заголовков.",
                can_skip=False,
            )
        )

        return ImportResult(
            rows=rows,
            errors=errors,
            office_locations=offices,
        )

    # Убираем BOM, если он вдруг оказался в первом заголовке.
    if headers:
        headers[0] = headers[0].lstrip("\ufeff")

    missing_columns = _missing_required_columns(headers)

    if missing_columns:
        for column in sorted(missing_columns):
            errors.append(
                ImportErrorItem(
                    code="MISSING_REQUIRED_COLUMN",
                    file=filename,
                    row=1,
                    entity_id=None,
                    field=column,
                    message=f"Отсутствует обязательная колонка: {column}.",
                    level="ERROR",
                    can_skip=False,
                )
            )

        return ImportResult(
            rows=[],
            errors=errors,
            office_locations=offices,
        )

    # 4. Читаем строки.
    for row_number, values in enumerate(reader, start=2):

        # Полностью пустая физическая строка.
        if not values or all(not value.strip() for value in values):
            skipped_empty += 1
            continue

        # Превращаем строку в словарь (ключи — исходные заголовки).
        row: dict[str, str] = {}

        for index, header in enumerate(headers):
            value = values[index] if index < len(values) else ""
            row[header] = value.strip()

        # Если в строке больше значений, чем заголовков,
        # сохраняем их под специальным ключом.
        if len(values) > len(headers):
            row["_extra_values"] = values[len(headers):]

        job_id_cell, _ = _get_job_id(row)
        address_cell = row.get("Адрес", "").strip().lower()

        if (job_id_cell or "").strip().lower().startswith("адрес офиса"):
            # Официальный формат: первая ячейка «Адрес Офиса»,
            # фактический адрес — во второй ячейке.
            office_address = values[1].strip() if len(values) > 1 else ""

            offices.append(
                OfficeLocation(
                    address=office_address,
                    source_filename=filename,
                    source_row=row_number,
                )
            )

            skipped_office += 1

            continue

        if "адрес офиса" in address_cell:
            # Легаси-формат: «Адрес офиса: ...» в колонке Адрес.
            offices.append(
                OfficeLocation(
                    address=row.get("Адрес", ""),
                    source_filename=filename,
                    source_row=row_number,
                )
            )

            skipped_office += 1

            continue

        service_zone = get_service_zone(filename)
        district = row.get("Район", "").strip()

        row_count += 1

        imported_row = {
            "source_filename": filename,
            "source_row": row_number,
            "service_zone": service_zone,
            "district": district,
            **row,
        }

        row_errors = validate_job_row(
            imported_row,
            filename,
            row_number,
        )

        if row_errors:
            errors.extend(row_errors)

        converted_row, conversion_error = convert_work_type(
            imported_row,
            filename,
            row_number,
        )

        converted_row = convert_window_datetimes(converted_row)

        rows.append(converted_row)

        if conversion_error is not None:
            errors.append(conversion_error)

    return ImportResult(
        rows=rows,
        errors=errors,
        office_locations=offices,
        row_count=row_count,
        skipped_empty=skipped_empty,
        skipped_office=skipped_office,
    )


def load_jobs_file(path) -> ImportResult:
    """
    Адаптер для загрузки CSV с диска.

    Основная логика остаётся в load_jobs_bytes().
    """
    path = path if hasattr(path, "read_bytes") else str(path)

    if hasattr(path, "read_bytes"):
        data = path.read_bytes()
        filename = path.name
    else:
        path_obj = Path(path)
        data = path_obj.read_bytes()
        filename = path_obj.name

    return load_jobs_bytes(data, filename)


def find_job_csv_files(directory: str | Path) -> list[Path]:
    """
    Возвращает отсортированный список официальных CSV-файлов заявок
    в указанной директории.

    Критерий отбора:
        * имя файла заканчивается на «Синтетические данные.csv»;
        * файл лежит непосредственно в директории (не в поддиректориях).

    Контрольные распределения и прочие посторонние файлы игнорируются.
    """
    root = Path(directory)

    return sorted(
        path
        for path in root.iterdir()
        if path.is_file() and path.name.endswith("Синтетические данные.csv")
    )


def validate_job_row(
    row: dict,
    filename: str,
    row_number: int,
) -> list[ImportErrorItem]:
    errors = []

    job_id, job_id_field = _get_job_id(row)

    if not job_id:
        errors.append(
            ImportErrorItem(
                code="EMPTY_ID",
                file=filename,
                row=row_number,
                entity_id=None,
                field=job_id_field or "Заявка",
                message="У заявки отсутствует ID.",
                level="ERROR",
                can_skip=True,
            )
        )

    if not row.get("Адрес", "").strip():
        errors.append(
            ImportErrorItem(
                code="EMPTY_ADDRESS",
                file=filename,
                row=row_number,
                entity_id=job_id or None,
                field="Адрес",
                message="У заявки отсутствует адрес.",
                level="ERROR",
                can_skip=True,
            )
        )

    date_fields = set(
        alias
        for aliases in DATE_COLUMN_ALIASES.values()
        for alias in aliases
    )

    for field_name in date_fields:
        value, actual_field = _get_column_value(row, field_name)

        if not value:
            continue

        try:
            parse_moscow_datetime(value)
        except ValueError:
            errors.append(
                ImportErrorItem(
                    code="INVALID_DATE",
                    file=filename,
                    row=row_number,
                    entity_id=job_id or None,
                    field=actual_field,
                    message=f"Некорректная дата: {value!r}.",
                    level="ERROR",
                    can_skip=True,
                )
            )

    return errors


def get_service_zone(filename: str) -> str:
    return filename.replace(" Синтетические данные.csv", "").strip()


def convert_work_type(
    row: dict,
    filename: str,
    row_number: int,
) -> tuple[dict, ImportErrorItem | None]:
    """
    Преобразует сырую CSV-строку:
    Тип заявки BK -> work_type + норматив.
    """

    raw_bk_value, bk_field = _get_column_value(row, "Тип заявки BK")
    raw_bk_type = raw_bk_value or ""

    work_type, service_duration_min, error_code = map_work_type(
        raw_bk_type
    )

    job_id, _ = _get_job_id(row)

    if error_code is not None:
        return (
            row,
            ImportErrorItem(
                code=error_code,
                file=filename,
                row=row_number,
                entity_id=job_id or None,
                field=bk_field or "Тип заявки BK",
                message=(
                    f"Неизвестный тип заявки BK: "
                    f"{raw_bk_type!r}."
                ),
                level="ERROR",
                can_skip=True,
            ),
        )

    converted_row = {
        **row,
        "work_type": work_type,
        "service_duration_min": service_duration_min,
    }

    return converted_row, None


def convert_window_datetimes(row: dict) -> dict:
    """
    Преобразует строки CSV «Начало» / «Окончание»
    в datetime-поля window_start / window_end
    с часовым поясом Europe/Moscow.

    Сырые строки CSV при этом сохраняются без изменений.
    Если дата некорректна, поле не заполняется —
    ошибка INVALID_DATE уже зафиксирована в validate_job_row().
    """
    converted_row = dict(row)

    for target_field, source_aliases in DATE_COLUMN_ALIASES.items():
        value, _ = _get_column_value(row, *source_aliases)

        if not value:
            continue

        try:
            converted_row[target_field] = parse_moscow_datetime(value)
        except ValueError:
            continue

    return converted_row


def normalize_job_row(row: dict) -> dict:
    """
    Приводит импортированную строку к каноническому набору полей JobRecord.

    Сырые значения BK и HD сохраняются без изменений
    (source_bk_type / source_hd_type).
    Производные поля по правилам MVP:
        status = NEW
        priority — из work_type (URGENT/HIGH/NORMAL)
        gigabit_connection — «Да»/«Нет»
        required_equipment — из конфигурации (+GIGABIT_TESTER при гигабите)
    received_at остаётся None до подтверждения реальной колонки.
    """
    job_id, _ = _get_job_id(row)
    bk_value, _ = _get_column_value(row, "Тип заявки BK")

    work_type = row.get("work_type")
    service_duration_min = row.get("service_duration_min")

    normalized = {
        "id": (job_id or "").strip(),
        "source_bk_type": (bk_value or "").strip(),
        "work_type": work_type,
        "service_zone": row.get("service_zone", "").strip(),
        "address": row.get("Адрес", "").strip(),
        "service_duration_min": service_duration_min,
        "source_filename": row.get("source_filename", "").strip(),
        "source_row": row.get("source_row"),
    }

    hd_value, _ = _get_column_value(row, "Тип заявки HD")
    if hd_value:
        normalized["source_hd_type"] = hd_value.strip()

    district_value = row.get("district", "").strip()
    if district_value:
        normalized["district"] = district_value

    gigabit_value, _ = _get_column_value(row, "Гигабитное подключение")
    if gigabit_value:
        raw = gigabit_value.strip()
        normalized["gigabit_connection_raw"] = raw
        normalized["gigabit_connection"] = parse_gigabit_flag(raw)

    gigabit = normalized.get("gigabit_connection") is True

    # Правила MVP для полей, которых нет в CSV.
    normalized["status"] = "NEW"

    if work_type:
        priority = get_work_type_priority(work_type)
        if priority is not None:
            normalized["priority"] = priority

        normalized["required_equipment"] = get_required_equipment(
            work_type,
            gigabit_connection=gigabit,
        )

    for target_field in ("window_start", "window_end"):
        value = row.get(target_field)
        if value is not None:
            normalized[target_field] = value

    return normalized