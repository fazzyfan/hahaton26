from collections import Counter
from pathlib import Path

import pytest

from src.services.import_pipeline import load_input_directory

OFFICIAL_INPUT_DIR = Path("data/input")

ZONES = {
    "Восток": 66,
    "Юго-восток": 83,
    "Югоцентр": 56,
}

WORK_TYPE_COUNTS = {
    "CONNECTION": 95,
    "LOCAL_WORK": 77,
    "EMERGENCY": 21,
    "ADD_ORDER": 12,
}


@pytest.fixture(scope="module")
def official_bundle():
    return load_input_directory(OFFICIAL_INPUT_DIR)


def test_official_csv_produces_exact_zone_counts(official_bundle):
    """Контрольные количества: Восток 66, Юго-восток 83, Югоцентр 56."""
    counts = Counter(job.service_zone for job in official_bundle.jobs)

    assert dict(counts) == ZONES
    assert sum(counts.values()) == 205


def test_official_csv_has_no_import_errors(official_bundle):
    assert official_bundle.errors == []


def test_official_csv_extracts_three_offices(official_bundle):
    assert len(official_bundle.office_locations) == 3


def test_official_csv_work_type_distribution(official_bundle):
    work_types = Counter(job.work_type for job in official_bundle.jobs)

    assert dict(work_types) == WORK_TYPE_COUNTS


def test_official_csv_exactly_two_gigabit_jobs(official_bundle):
    gigabit = sum(
        1 for job in official_bundle.jobs if job.gigabit_connection
    )

    assert gigabit == 2


def test_official_jobs_have_derived_fields(official_bundle):
    for job in official_bundle.jobs:
        assert job.status == "NEW"
        assert job.priority in {"URGENT", "HIGH", "NORMAL"}
        assert job.required_equipment
        assert job.source_filename.endswith("Синтетические данные.csv")
        assert job.source_row is not None


def test_official_jobs_have_location_ids(official_bundle):
    assert all(job.location_id for job in official_bundle.jobs)