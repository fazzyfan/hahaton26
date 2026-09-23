from src.services.import_pipeline import load_input_directory


ENGINEERS_JSON = """\
[]
"""

EQUIPMENT_JSON = """\
[]
"""

TRAVEL_MATRIX_JSON = """\
[]
"""


def _write_minimal_files(tmp_path) -> None:
    (tmp_path / "engineers.json").write_text(ENGINEERS_JSON, encoding="utf-8")
    (tmp_path / "equipment.json").write_text(EQUIPMENT_JSON, encoding="utf-8")
    (tmp_path / "travel_matrix.json").write_text(TRAVEL_MATRIX_JSON, encoding="utf-8")


def test_import_report_counts_rows_jobs_skips_and_errors(tmp_path):
    (tmp_path / "Восток Синтетические данные.csv").write_text(
        "ID;Адрес;Тип заявки BK\n"
        "\n"
        ";Адрес офиса: Ростов;\n"
        "1001;Адрес клиента;Подключение\n"
        "1002;Адрес клиента;Неизвестный тип\n",
        encoding="cp1251",
    )
    _write_minimal_files(tmp_path)

    bundle = load_input_directory(tmp_path)

    assert len(bundle.reports) == 1

    report = bundle.reports[0]

    assert report.filename == "Восток Синтетические данные.csv"
    assert report.rows_total == 2
    assert report.jobs_imported == 1
    assert report.skipped_empty == 1
    assert report.skipped_office == 1
    assert report.error_count == 1

    assert len(bundle.jobs) == 1
    assert bundle.jobs[0].id == "1001"


def test_import_report_covers_each_file_separately(tmp_path):
    (tmp_path / "Восток Синтетические данные.csv").write_text(
        "ID;Адрес;Тип заявки BK\n"
        "1001;Адрес клиента;Подключение\n",
        encoding="cp1251",
    )
    (tmp_path / "Югоцентр Синтетические данные.csv").write_text(
        "ID;Адрес;Тип заявки BK\n"
        "\n"
        "2001;Адрес клиента;Дозаказ\n",
        encoding="cp1251",
    )
    _write_minimal_files(tmp_path)

    bundle = load_input_directory(tmp_path)

    assert [report.filename for report in bundle.reports] == [
        "Восток Синтетические данные.csv",
        "Югоцентр Синтетические данные.csv",
    ]

    by_name = {report.filename: report for report in bundle.reports}

    assert by_name["Восток Синтетические данные.csv"].jobs_imported == 1
    assert by_name["Восток Синтетические данные.csv"].skipped_empty == 0

    assert by_name["Югоцентр Синтетические данные.csv"].jobs_imported == 1
    assert by_name["Югоцентр Синтетические данные.csv"].skipped_empty == 1

    assert len(bundle.jobs) == 2