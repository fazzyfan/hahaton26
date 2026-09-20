from __future__ import annotations

import json
from pathlib import Path


CONFIG_PATH = Path(__file__).with_name("data_contract_v1_2.json")


def load_data_contract() -> dict:
    with CONFIG_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


def map_work_type(raw_bk_type: str | None) -> tuple[str | None, int | None, str | None]:
    config = load_data_contract()

    value = (raw_bk_type or "").strip()

    mapping = config["work_types"].get(value)

    if mapping is None:
        return (
            None,
            None,
            config["unknown_work_type"]["code"],
        )

    return (
        mapping["code"],
        mapping["service_duration_min"],
        None,
    )