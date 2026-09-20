from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from io import StringIO
from zoneinfo import ZoneInfo
from src.config.loader import map_work_type

MOSCOW_TZ = ZoneInfo("Europe/Moscow")
DATE_FORMAT = "%d.%m.%Y %H:%M"
REQUIRED_COLUMNS = {
    "ID",
    "Адрес",
    "Тип заявки BK",
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


def _is_blank_row(row: dict) -> bool:
    """
    Возвращает True, если вся строка CSV пустая.
    """
    return all(
        value is None or not str(value).strip()
        for value in row.values()
    )


def load_jobs_bytes(data: bytes, filename: str) -> ImportResult:
    """
    Основная функция импорта CSV.

    Вход:
        data      — содержимое CSV в виде bytes
        filename  — имя исходного файла

    CSV:
        encoding = CP1251
        delimiter = ;
    """

    errors: list[ImportErrorItem] = []
    rows: list[dict] = []
    offices: list[OfficeLocation] = []

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
    missing_columns = REQUIRED_COLUMNS - set(headers)

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
            continue

        # Превращаем строку в словарь.
        row = {}

        for index, header in enumerate(headers):
            value = values[index] if index < len(values) else ""
            row[header] = value.strip()

        # Если в строке больше значений, чем заголовков,
        # сохраняем их под специальным ключом.
        if len(values) > len(headers):
            row["_extra_values"] = values[len(headers):]

        address = row.get("Адрес", "").lower()

        if (
            "адрес офиса" in address
            or "адрес офиса" in str(row).lower()
        ):
            offices.append(
                OfficeLocation(
                    address=row.get("Адрес", ""),
                    source_filename=filename,
                    source_row=row_number,
                )
            )

            continue

        service_zone = get_service_zone(filename)
        district = row.get("Район", "").strip()

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
            )

    # Сохраняем строки как словари.
    for row in reader:
    # csv.DictReader.line_num содержит физический номер
    # строки исходного CSV-файла.
        row_number = reader.line_num

    # Полностью пустые строки пропускаем.
        if _is_blank_row(row):
            continue

    rows.append(
        {
            "source_filename": filename,
            "source_row": row_number,
            **{
                key: value.strip() if isinstance(value, str) else value
                for key, value in row.items()
            },
        }
    )

    return ImportResult(rows=rows, errors=errors)


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
        from pathlib import Path

        path_obj = Path(path)
        data = path_obj.read_bytes()
        filename = path_obj.name

    return load_jobs_bytes(data, filename)

def _get_column_value(row: dict, *names: str) -> tuple[str | None, str | None]:
    normalized = {
        str(key).replace(" ", "").strip().lower(): key
        for key in row
    }

    for name in names:
        key = normalized.get(
            name.replace(" ", "").strip().lower()
        )
        if key is not None:
            return row.get(key), key

    return None, None

def validate_job_row(
    row: dict,
    filename: str,
    row_number: int,
) -> list[ImportErrorItem]:
    errors = []

    if not row.get("ID", "").strip():
        errors.append(
            ImportErrorItem(
                code="EMPTY_ID",
                file=filename,
                row=row_number,
                entity_id=None,
                field="ID",
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
                entity_id=row.get("ID") or None,
                field="Адрес",
                message="У заявки отсутствует адрес.",
                level="ERROR",
                can_skip=True,
            )
        )
    date_fields = (
        "Начало окна",
        "Дата начала окна",
        "Дата/время начала",
        "Конец окна",
    )

    for field_name in date_fields:
        value, actual_field = _get_column_value(
            row,
            field_name,
        )

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
                    entity_id=row.get("ID") or None,
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

    raw_bk_type = row.get("Тип заявки BK")

    work_type, service_duration_min, error_code = map_work_type(
        raw_bk_type
    )

    if error_code is not None:
        return (
            row,
            ImportErrorItem(
                code=error_code,
                file=filename,
                row=row_number,
                entity_id=row.get("ID") or None,
                field="Тип заявки BK",
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
    Преобразует строки CSV «Начало окна» / «Конец окна»
    в datetime-поля window_start / window_end
    с часовым поясом Europe/Moscow.

    Сырые строки CSV при этом сохраняются без изменений.
    Если дата некорректна, поле не заполняется —
    ошибка INVALID_DATE уже зафиксирована в validate_job_row().
    """
    converted_row = dict(row)

    for target_field, source_column in (
        ("window_start", "Начало окна"),
        ("window_end", "Конец окна"),
    ):
        value, _ = _get_column_value(row, source_column)

        if not value:
            continue

        try:
            converted_row[target_field] = parse_moscow_datetime(value)
        except ValueError:
            continue

    return converted_row


def normalize_job_row(row: dict) -> dict:
    """
    Приводит импортированную строку к каноническому набору полей Job.

    Сырые значения BK и HD сохраняются без изменений
    (source_bk_type / source_hd_type).
    Необязательные поля включаются в результат, только если присутствуют.
    received_at будет добавлен, когда станет известна фактическая
    колонка CSV с датой поступления.
    """
    normalized = {
        "id": row.get("ID", "").strip(),
        "source_bk_type": row.get("Тип заявки BK", "").strip(),
        "work_type": row.get("work_type"),
        "service_zone": row.get("service_zone", "").strip(),
        "address": row.get("Адрес", "").strip(),
        "service_duration_min": row.get("service_duration_min"),
        "source_filename": row.get("source_filename", "").strip(),
        "source_row": row.get("source_row"),
    }

    hd_value, _ = _get_column_value(row, "Тип заявки HD")
    if hd_value:
        normalized["source_hd_type"] = hd_value.strip()

    district_value = row.get("district", "").strip()
    if district_value:
        normalized["district"] = district_value

    for target_field in ("window_start", "window_end"):
        value = row.get(target_field)
        if value is not None:
            normalized[target_field] = value

    return normalized




def test_empty_id_creates_structured_error():
    csv_text = (
        "ID;Адрес;Тип заявки BK\n"
        ";Адрес клиента;Подключение\n"
    )

    result = load_jobs_bytes(
        csv_text.encode("cp1251"),
        "Восток Синтетические данные.csv",
    )

    assert len(result.rows) == 1
    assert len(result.errors) == 1

    error = result.errors[0]

    assert error.code == "EMPTY_ID"
    assert error.row == 2
    assert error.entity_id is None
    assert error.field == "ID"
    assert error.can_skip is True