from src.importers.csv_jobs import load_jobs_bytes, normalize_job_row


def test_optional_columns_pass_through_when_present():
    csv_text = (
        "ID;Адрес;Тип заявки BK;Подключение;Гигабитное подключение\n"
        "1001;Адрес клиента;Подключение;да;да\n"
    )

    result = load_jobs_bytes(
        csv_text.encode("cp1251"),
        "Восток Синтетические данные.csv",
    )

    assert result.errors == []
    assert len(result.rows) == 1

    row = result.rows[0]

    assert row["Подключение"] == "да"
    assert row["Гигабитное подключение"] == "да"


def test_optional_columns_absent_are_ignored():
    csv_text = (
        "ID;Адрес;Тип заявки BK\n"
        "1001;Адрес клиента;Подключение\n"
    )

    result = load_jobs_bytes(
        csv_text.encode("cp1251"),
        "Восток Синтетические данные.csv",
    )

    assert result.errors == []
    assert len(result.rows) == 1

    row = result.rows[0]

    assert "Подключение" not in row
    assert "Гигабитное подключение" not in row


def test_normalize_job_row_keeps_gigabit_raw_when_present():
    row = {
        "source_filename": "Восток Синтетические данные.csv",
        "source_row": 2,
        "service_zone": "Восток",
        "ID": "1001",
        "Адрес": "Адрес клиента",
        "Тип заявки BK": "Подключение",
        "Гигабитное подключение": "да",
        "work_type": "CONNECTION",
        "service_duration_min": 90,
    }

    normalized = normalize_job_row(row)

    assert normalized["gigabit_connection_raw"] == "да"


def test_import_counts_rows_and_skips():
    csv_text = (
        "ID;Адрес;Тип заявки BK\n"
        "\n"
        ";Адрес офиса: Ростов, ул. Ленина, 1;\n"
        "1001;Адрес клиента;Подключение\n"
        ";;\n"
        "1002;Адрес клиента;Дозаказ\n"
    )

    result = load_jobs_bytes(
        csv_text.encode("cp1251"),
        "Восток Синтетические данные.csv",
    )

    assert result.errors == []

    assert result.row_count == 2
    assert result.skipped_empty == 2
    assert result.skipped_office == 1

    assert len(result.rows) == 2
    assert len(result.office_locations) == 1


OFFICIAL_HEADER = (
    "Заявка;Тип заявки BK;Тип заявки HD;Начало;Окончание;"
    "Район;Адрес;Гигабитное подключение\n"
)


def test_official_header_imports_job():
    csv_text = (
        OFFICIAL_HEADER
        + "74198;Подключение;Конвергенция абонента;17.08.2026 20:00;"
        + "17.08.2026 22:00;Кузьминки;Город Москва, пр-кт.Волгоградский, "
        + "д. 128 к 5;Нет\n"
    )

    result = load_jobs_bytes(
        csv_text.encode("cp1251"),
        "Восток Синтетические данные.csv",
    )

    assert result.errors == []
    assert len(result.rows) == 1

    row = result.rows[0]

    assert row["Заявка"] == "74198"
    assert row["Начало"] == "17.08.2026 20:00"
    assert row["Окончание"] == "17.08.2026 22:00"
    assert row["work_type"] == "CONNECTION"
    assert row["service_duration_min"] == 70
    assert row["window_start"].hour == 20
    assert row["window_end"].hour == 22


def test_official_office_row_address_taken_from_second_cell():
    csv_text = (
        OFFICIAL_HEADER
        + "Адрес Офиса;г. Москва, ул Юных Ленинцев, д 83с 4;;;;;;;\n"
        + "74198;Подключение;;17.08.2026 20:00;17.08.2026 22:00;"
        + "Кузьминки;Адрес клиента;Нет\n"
    )

    result = load_jobs_bytes(
        csv_text.encode("cp1251"),
        "Восток Синтетические данные.csv",
    )

    assert len(result.rows) == 1
    assert len(result.office_locations) == 1
    assert result.skipped_office == 1

    office = result.office_locations[0]

    assert office.address == "г. Москва, ул Юных Ленинцев, д 83с 4"


def test_normalize_official_row_with_gigabit_yes():
    row = {
        "source_filename": "Восток Синтетические данные.csv",
        "source_row": 2,
        "service_zone": "Восток",
        "Заявка": "74198",
        "Тип заявки BK": "Подключение",
        "Гигабитное подключение": "Да",
        "work_type": "CONNECTION",
        "service_duration_min": 70,
    }

    normalized = normalize_job_row(row)

    assert normalized["id"] == "74198"
    assert normalized["gigabit_connection"] is True
    assert normalized["status"] == "NEW"
    assert normalized["priority"] == "HIGH"
    assert normalized["required_equipment"] == [
        "INSTALLATION_KIT",
        "GIGABIT_TESTER",
    ]


def test_normalize_official_row_with_gigabit_no():
    row = {
        "source_filename": "Восток Синтетические данные.csv",
        "source_row": 2,
        "service_zone": "Восток",
        "Заявка": "74199",
        "Тип заявки BK": "Дозаказ",
        "Гигабитное подключение": "Нет",
        "work_type": "ADD_ORDER",
        "service_duration_min": 20,
    }

    normalized = normalize_job_row(row)

    assert normalized["gigabit_connection"] is False
    assert normalized["priority"] == "NORMAL"
    assert normalized["required_equipment"] == ["CUSTOMER_EQUIPMENT"]


def test_office_row_without_address_column_does_not_break_import():
    csv_text = (
        "Заявка;Тип заявки BK;Адрес\n"
        "Адрес Офиса;г. Москва, ул Тестовая, д 1;\n"
        "1001;Подключение;Адрес клиента\n"
    )

    result = load_jobs_bytes(
        csv_text.encode("cp1251"),
        "Югоцентр Синтетические данные.csv",
    )

    assert len(result.rows) == 1
    assert result.rows[0]["Заявка"] == "1001"
    assert len(result.office_locations) == 1
    assert result.office_locations[0].address == "г. Москва, ул Тестовая, д 1"