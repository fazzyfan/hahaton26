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


def get_work_type_priority(work_type: str) -> str | None:
    """
    Возвращает приоритет по коду типа работы
    (URGENT / HIGH / NORMAL) из конфигурации.
    """
    config = load_data_contract()

    for mapping in config["work_types"].values():
        if mapping["code"] == work_type:
            return mapping.get("priority")

    return None


def get_required_equipment(
    work_type: str,
    gigabit_connection: bool = False,
) -> list[str]:
    """
    Возвращает обязательное оборудование заявки из конфигурации.

    Гигабитное подключение дополнительно требует GIGABIT_TESTER.
    """
    config = load_data_contract()

    equipment = list(config["equipment_requirements"].get(work_type, []))

    if gigabit_connection:
        equipment.extend(config["gigabit_extra_equipment"])

    return equipment