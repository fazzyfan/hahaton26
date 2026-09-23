from pathlib import Path

import pytest

from src.services.import_pipeline import load_input_directory

OFFICIAL_INPUT_DIR = Path("data/input")

ZONES = {
    "Восток": 66,
    "Юго-восток": 83,
    "Югоцентр": 56,
}


def _official_csv_paths() -> list[Path]:
    return [
        OFFICIAL_INPUT_DIR / f"{zone} Синтетические данные.csv"
        for zone in ZONES
    ]


def _all_official_csvs_present() -> bool:
    return all(path.exists() for path in _official_csv_paths())


@pytest.mark.skipif(
    not _all_official_csvs_present(),
    reason="Официальный архив «Обезличивание.zip» ещё не добавлен в data/input",
)
def test_official_csv_produces_exact_zone_counts():
    """Контрольные количества: Восток 66, Юго-восток 83, Югоцентр 56."""
    bundle = load_input_directory(OFFICIAL_INPUT_DIR)

    counts: dict[str, int] = {}

    for job in bundle.jobs:
        counts[job.service_zone] = counts.get(job.service_zone, 0) + 1

    assert counts == ZONES
    assert sum(counts.values()) == 205


@pytest.mark.skipif(
    not _all_official_csvs_present(),
    reason="Официальный архив «Обезличивание.zip» ещё не добавлен в data/input",
)
def test_official_csv_has_no_office_rows_and_all_have_origin():
    bundle = load_input_directory(OFFICIAL_INPUT_DIR)

    for job in bundle.jobs:
        assert job.source_filename.endswith("Синтетические данные.csv")
        assert job.address.strip()

    assert len(bundle.office_locations) >= 3