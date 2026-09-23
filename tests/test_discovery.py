from src.importers.csv_jobs import find_job_csv_files


def test_find_job_csv_files_picks_only_official_names(tmp_path):
    (tmp_path / "Восток Синтетические данные.csv").write_text(
        "ID;Адрес\n", encoding="utf-8"
    )
    (tmp_path / "Юго-восток Синтетические данные.csv").write_text(
        "ID;Адрес\n", encoding="utf-8"
    )
    (tmp_path / "Югоцентр Синтетические данные.csv").write_text(
        "ID;Адрес\n", encoding="utf-8"
    )

    # Контрольные и посторонние файлы не должны попадать в выборку.
    (tmp_path / "Контрольное распределение.csv").write_text(
        "a;b\n", encoding="utf-8"
    )
    (tmp_path / "Распределение заявок.xlsx").write_bytes(b"x")
    (tmp_path / "notes.txt").write_text("x", encoding="utf-8")

    found = find_job_csv_files(tmp_path)

    assert [path.name for path in found] == [
        "Восток Синтетические данные.csv",
        "Юго-восток Синтетические данные.csv",
        "Югоцентр Синтетические данные.csv",
    ]


def test_find_job_csv_files_ignores_subdirectories(tmp_path):
    subdir = tmp_path / "nested"
    subdir.mkdir()
    (subdir / "Восток Синтетические данные.csv").write_text(
        "ID;Адрес\n", encoding="utf-8"
    )

    found = find_job_csv_files(tmp_path)

    assert found == []


def test_find_job_csv_files_empty_dir(tmp_path):
    found = find_job_csv_files(tmp_path)

    assert found == []