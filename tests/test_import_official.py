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