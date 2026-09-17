from copy import deepcopy

from src.validation.input_validator import InputValidator


def load_demo_data():
    validator = InputValidator()
    return validator.load_json("data/demo.json")


def test_valid_demo_json():
    validator = InputValidator()
    data = load_demo_data()

    jobs, engineers, issues = validator.validate(data)

    assert len(jobs) == 5
    assert len(engineers) == 3
    assert issues == []


def test_missing_jobs():
    validator = InputValidator()
    data = load_demo_data()

    del data["jobs"]

    jobs, engineers, issues = validator.validate(data)

    assert len(jobs) == 0
    assert len(engineers) == 3
    assert any(
        issue.code == "MISSING_SECTION"
        and issue.field == "jobs"
        for issue in issues
    )


def test_missing_engineers():
    validator = InputValidator()
    data = load_demo_data()

    del data["engineers"]

    jobs, engineers, issues = validator.validate(data)

    assert len(jobs) == 5
    assert len(engineers) == 0
    assert any(
        issue.code == "MISSING_SECTION"
        and issue.field == "engineers"
        for issue in issues
    )


def test_invalid_job_skill():
    validator = InputValidator()
    data = load_demo_data()

    data["jobs"][0]["required_skill"] = "PILOT"

    jobs, engineers, issues = validator.validate(data)

    assert len(jobs) == 4
    assert len(engineers) == 3
    assert any(
        issue.entity_type == "Job"
        and issue.entity_id == "JOB-001"
        and issue.field == "required_skill"
        for issue in issues
    )


def test_duplicate_job_id():
    validator = InputValidator()
    data = load_demo_data()

    data["jobs"][1]["id"] = data["jobs"][0]["id"]

    jobs, engineers, issues = validator.validate(data)

    assert any(
        issue.code == "DUPLICATE_ID"
        and issue.entity_type == "Job"
        for issue in issues
    )


def test_invalid_job_time_window():
    validator = InputValidator()
    data = load_demo_data()

    data["jobs"][0]["window_start"] = "2026-09-17T14:00:00"
    data["jobs"][0]["window_end"] = "2026-09-17T10:00:00"

    jobs, engineers, issues = validator.validate(data)

    assert any(
        issue.code == "INVALID_TIME_WINDOW"
        and issue.entity_id == "JOB-001"
        for issue in issues
    )


def test_invalid_engineer_shift():
    validator = InputValidator()
    data = load_demo_data()

    data["engineers"][0]["shift_start"] = "2026-09-17T18:00:00"
    data["engineers"][0]["shift_end"] = "2026-09-17T08:00:00"

    jobs, engineers, issues = validator.validate(data)

    assert any(
        issue.code == "INVALID_SHIFT"
        and issue.entity_id == "ENG-001"
        for issue in issues
    )


def test_multiple_errors_are_collected():
    validator = InputValidator()
    data = load_demo_data()

    # Ошибка №1
    data["jobs"][0]["required_skill"] = "PILOT"

    # Ошибка №2
    data["jobs"][1]["window_start"] = "2026-09-17T16:00:00"
    data["jobs"][1]["window_end"] = "2026-09-17T10:00:00"

    # Ошибка №3
    data["engineers"][0]["shift_start"] = "2026-09-17T18:00:00"
    data["engineers"][0]["shift_end"] = "2026-09-17T08:00:00"

    jobs, engineers, issues = validator.validate(data)

    assert len(issues) >= 3

    assert any(
        issue.entity_id == "JOB-001"
        and issue.field == "required_skill"
        for issue in issues
    )

    assert any(
        issue.entity_id == "JOB-002"
        and issue.code == "INVALID_TIME_WINDOW"
        for issue in issues
    )

    assert any(
        issue.entity_id == "ENG-001"
        and issue.code == "INVALID_SHIFT"
        for issue in issues
    )