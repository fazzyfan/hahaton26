from pathlib import Path

from src.importers.csv_jobs import (
    MOSCOW_TZ,
    load_jobs_bytes,
    normalize_job_row,
    parse_moscow_datetime,
)


def test_import_cp1251_and_semicolon():
    csv_text = (
        "ID;Адрес;Тип заявки BK\n"
        "1001;Ростов-на-Дону, ул. Ленина, 1;Подключение\n"
        "1002;Ростов-на-Дону, ул. Пушкина, 2;Локальная заявка\n"
    )

    result = load_jobs_bytes(
        csv_text.encode("cp1251"),
        "Восток Синтетические данные.csv",
    )

    assert result.errors == []
    assert len(result.rows) == 2

    assert result.rows[0]["ID"] == "1001"
    assert result.rows[0]["Адрес"] == "Ростов-на-Дону, ул. Ленина, 1"


def test_blank_rows_are_skipped():
    csv_text = (
        "ID;Адрес;Тип заявки BK\n"
        "\n"
        "1001;Ростов-на-Дону, ул. Ленина, 1;Подключение\n"
        ";;\n"
        "\n"
        "1002;Ростов-на-Дону, ул. Пушкина, 2;Дозаказ\n"
    )

    result = load_jobs_bytes(
        csv_text.encode("cp1251"),
        "Восток Синтетические данные.csv",
    )

    assert result.errors == []
    assert len(result.rows) == 2


def test_source_filename_and_physical_row_are_saved():
    csv_text = (
        "ID;Адрес;Тип заявки BK\n"
        "\n"
        "1001;Адрес 1;Подключение\n"
    )

    result = load_jobs_bytes(
        csv_text.encode("cp1251"),
        "Югоцентр Синтетические данные.csv",
    )

    assert len(result.rows) == 1

    row = result.rows[0]

    assert row["source_filename"] == "Югоцентр Синтетические данные.csv"
    assert row["source_row"] == 3


def test_moscow_datetime():
    value = parse_moscow_datetime("20.09.2026 14:30")

    assert value.year == 2026
    assert value.month == 9
    assert value.day == 20
    assert value.hour == 14
    assert value.minute == 30

    assert value.tzinfo is not None
    assert value.utcoffset().total_seconds() == 3 * 60 * 60



from src.importers.csv_jobs import convert_work_type


def test_convert_connection():
    row = {
        "ID": "1001",
        "Тип заявки BK": "Подключение",
    }

    converted, error = convert_work_type(
        row,
        "Восток Синтетические данные.csv",
        2,
    )

    assert error is None
    assert converted["work_type"] == "CONNECTION"
    assert converted["service_duration_min"] == 70


def test_convert_emergency():
    row = {
        "ID": "1002",
        "Тип заявки BK": "Глобальная проблема",
    }

    converted, error = convert_work_type(
        row,
        "Восток Синтетические данные.csv",
        3,
    )

    assert error is None
    assert converted["work_type"] == "EMERGENCY"
    assert converted["service_duration_min"] == 80


def test_unknown_bk_type_creates_structured_error():
    row = {
        "ID": "1003",
        "Тип заявки BK": "Неизвестный тип",
    }

    converted, error = convert_work_type(
        row,
        "Югоцентр Синтетические данные.csv",
        17,
    )

    assert converted == row

    assert error is not None
    assert error.code == "UNKNOWN_WORK_TYPE_MAPPING"
    assert error.file == "Югоцентр Синтетические данные.csv"
    assert error.row == 17
    assert error.entity_id == "1003"
    assert error.field == "Тип заявки BK"
    assert error.can_skip is True


def test_import_applies_work_type_mapping():
    csv_text = (
        "ID;Адрес;Тип заявки BK\n"
        "1001;Адрес 1;Подключение\n"
        "1002;Адрес 2;Глобальная проблема\n"
        "1003;Адрес 3;Дозаказ\n"
        "1004;Адрес 4;Локальная заявка\n"
    )

    result = load_jobs_bytes(
        csv_text.encode("cp1251"),
        "Восток Синтетические данные.csv",
    )

    assert result.errors == []
    assert len(result.rows) == 4

    assert result.rows[0]["work_type"] == "CONNECTION"
    assert result.rows[0]["service_duration_min"] == 70

    assert result.rows[1]["work_type"] == "EMERGENCY"
    assert result.rows[1]["service_duration_min"] == 80

    assert result.rows[2]["work_type"] == "ADD_ORDER"
    assert result.rows[2]["service_duration_min"] == 20

    assert result.rows[3]["work_type"] == "LOCAL_WORK"
    assert result.rows[3]["service_duration_min"] == 30


def test_import_reports_unknown_work_type():
    csv_text = (
        "ID;Адрес;Тип заявки BK\n"
        "1001;Адрес 1;Подключение\n"
        "1002;Адрес 2;Неизвестная заявка\n"
        "1003;Адрес 3;Дозаказ\n"
    )

    result = load_jobs_bytes(
        csv_text.encode("cp1251"),
        "Югоцентр Синтетические данные.csv",
    )

    assert len(result.rows) == 3
    assert len(result.errors) == 1

    error = result.errors[0]

    assert error.code == "UNKNOWN_WORK_TYPE_MAPPING"
    assert error.row == 3
    assert error.entity_id == "1002"
    assert error.field == "Тип заявки BK"

    assert result.rows[0]["work_type"] == "CONNECTION"
    assert result.rows[2]["work_type"] == "ADD_ORDER"



def test_office_address_is_not_imported_as_job():
    csv_text = (
        "ID;Адрес;Тип заявки BK\n"
        ";Адрес офиса: Ростов, ул. Ленина, 1;\n"
        "1001;Адрес клиента;Подключение\n"
    )

    result = load_jobs_bytes(
        csv_text.encode("cp1251"),
        "Восток Синтетические данные.csv",
    )

    assert len(result.rows) == 1
    assert len(result.office_locations) == 1

    office = result.office_locations[0]

    assert "Ростов" in office.address
    assert office.source_row == 2


def test_missing_required_column_is_reported():
    csv_text = (
        "ID;Адрес\n"
        "1001;Адрес клиента\n"
    )

    result = load_jobs_bytes(
        csv_text.encode("cp1251"),
        "Восток Синтетические данные.csv",
    )

    assert result.rows == []

    error_codes = {error.code for error in result.errors}

    assert "MISSING_REQUIRED_COLUMN" in error_codes
    assert any(
        error.field == "Тип заявки BK"
        for error in result.errors
    )



def test_empty_address_creates_structured_error():
    csv_text = (
        "ID;Адрес;Тип заявки BK\n"
        "1001;;Подключение\n"
    )

    result = load_jobs_bytes(
        csv_text.encode("cp1251"),
        "Восток Синтетические данные.csv",
    )

    assert len(result.rows) == 1
    assert len(result.errors) == 1

    error = result.errors[0]

    assert error.code == "EMPTY_ADDRESS"
    assert error.row == 2
    assert error.entity_id == "1001"
    assert error.field == "Адрес"
    assert error.can_skip is True


def test_invalid_date_creates_structured_error():
    csv_text = (
        "ID;Адрес;Тип заявки BK;Начало окна;Конец окна\n"
        "1001;Адрес клиента;Подключение;31.02.2026 10:00;01.03.2026 12:00\n"
    )

    result = load_jobs_bytes(
        csv_text.encode("cp1251"),
        "Восток Синтетические данные.csv",
    )

    assert len(result.rows) == 1
    assert len(result.errors) == 1

    error = result.errors[0]

    assert error.code == "INVALID_DATE"
    assert error.row == 2
    assert error.entity_id == "1001"
    assert error.field == "Начало окна"
    assert error.can_skip is True



def test_raw_bk_and_hd_values_are_preserved():
    csv_text = (
        "ID;Адрес;Тип заявки BK;Тип заявки HD\n"
        "1001;Адрес клиента;Подключение;HD-REPAIR-42\n"
    )

    result = load_jobs_bytes(
        csv_text.encode("cp1251"),
        "Восток Синтетические данные.csv",
    )

    assert result.errors == []
    assert len(result.rows) == 1

    row = result.rows[0]

    assert row["Тип заявки BK"] == "Подключение"
    assert row["Тип заявки HD"] == "HD-REPAIR-42"
    assert row["work_type"] == "CONNECTION"




def test_service_zone_is_taken_from_filename():
    csv_text = (
        "ID;Адрес;Тип заявки BK;Район\n"
        "1001;Адрес клиента;Подключение;Ворошиловский\n"
    )

    result = load_jobs_bytes(
        csv_text.encode("cp1251"),
        "Югоцентр Синтетические данные.csv",
    )

    assert result.errors == []
    assert len(result.rows) == 1

    row = result.rows[0]

    assert row["service_zone"] == "Югоцентр"
    assert row["Район"] == "Ворошиловский"



def test_district_is_saved_separately():
    csv_text = (
        "ID;Адрес;Тип заявки BK;Район\n"
        "1001;Адрес клиента;Подключение;Ворошиловский\n"
    )

    result = load_jobs_bytes(
        csv_text.encode("cp1251"),
        "Югоцентр Синтетические данные.csv",
    )

    assert result.errors == []
    assert len(result.rows) == 1

    row = result.rows[0]

    assert row["Район"] == "Ворошиловский"
    assert row["district"] == "Ворошиловский"



def test_window_datetimes_are_parsed_with_moscow_timezone():
    csv_text = (
        "ID;Адрес;Тип заявки BK;Начало окна;Конец окна\n"
        "1001;Адрес клиента;Подключение;20.09.2026 10:00;20.09.2026 12:00\n"
    )

    result = load_jobs_bytes(
        csv_text.encode("cp1251"),
        "Восток Синтетические данные.csv",
    )

    assert result.errors == []
    assert len(result.rows) == 1

    row = result.rows[0]

    assert row["window_start"].year == 2026
    assert row["window_start"].hour == 10
    assert row["window_start"].tzinfo is not None
    assert row["window_start"].tzinfo == MOSCOW_TZ

    assert row["window_end"].hour == 12
    assert row["window_end"].tzinfo == MOSCOW_TZ


def test_normalize_job_row_produces_canonical_fields():
    row = {
        "source_filename": "Восток Синтетические данные.csv",
        "source_row": 3,
        "service_zone": "Восток",
        "district": "Ворошиловский",
        "ID": "1001",
        "Адрес": "Ростов-на-Дону, ул. Ленина, 1",
        "Тип заявки BK": "Подключение",
        "Тип заявки HD": "HD-REPAIR-42",
        "Начало окна": "20.09.2026 10:00",
        "Конец окна": "20.09.2026 12:00",
        "work_type": "CONNECTION",
        "service_duration_min": 90,
        "window_start": parse_moscow_datetime("20.09.2026 10:00"),
        "window_end": parse_moscow_datetime("20.09.2026 12:00"),
    }

    normalized = normalize_job_row(row)

    assert normalized["id"] == "1001"
    assert normalized["source_bk_type"] == "Подключение"
    assert normalized["source_hd_type"] == "HD-REPAIR-42"
    assert normalized["work_type"] == "CONNECTION"
    assert normalized["service_zone"] == "Восток"
    assert normalized["district"] == "Ворошиловский"
    assert normalized["address"] == "Ростов-на-Дону, ул. Ленина, 1"
    assert normalized["window_start"].hour == 10
    assert normalized["window_end"].hour == 12
    assert normalized["service_duration_min"] == 90
    assert normalized["source_filename"] == "Восток Синтетические данные.csv"
    assert normalized["source_row"] == 3


def test_normalize_job_row_skips_missing_optional_fields():
    row = {
        "source_filename": "Югоцентр Синтетические данные.csv",
        "source_row": 2,
        "service_zone": "Югоцентр",
        "ID": "2001",
        "Адрес": "Адрес клиента",
        "Тип заявки BK": "Дозаказ",
        "work_type": "ADD_ORDER",
        "service_duration_min": 40,
    }

    normalized = normalize_job_row(row)

    assert normalized["id"] == "2001"
    assert normalized["address"] == "Адрес клиента"
    assert normalized["work_type"] == "ADD_ORDER"

    assert "source_hd_type" not in normalized
    assert "district" not in normalized
    assert "window_start" not in normalized
    assert "window_end" not in normalized