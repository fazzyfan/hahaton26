import json
from pathlib import Path


CONFIG_PATH = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "config"
    / "data_contract_v1_2.json"
)


def load_config():
    with CONFIG_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


def test_contract_version():
    config = load_config()

    assert config["version"] == "1.2"
    assert config["timezone"] == "Europe/Moscow"
    assert config["datetime"]["format"] == "%d.%m.%Y %H:%M"


def test_work_type_mapping():
    config = load_config()

    assert config["work_types"]["Подключение"]["code"] == "CONNECTION"
    assert config["work_types"]["Локальная заявка"]["code"] == "LOCAL_WORK"
    assert config["work_types"]["Глобальная проблема"]["code"] == "EMERGENCY"
    assert config["work_types"]["Дозаказ"]["code"] == "ADD_ORDER"


def test_service_duration_norms():
    config = load_config()

    assert config["work_types"]["Подключение"]["service_duration_min"] == 90
    assert config["work_types"]["Локальная заявка"]["service_duration_min"] == 50
    assert config["work_types"]["Глобальная проблема"]["service_duration_min"] == 100
    assert config["work_types"]["Дозаказ"]["service_duration_min"] == 40


def test_unknown_work_type():
    config = load_config()

    assert (
        config["unknown_work_type"]["code"]
        == "UNKNOWN_WORK_TYPE_MAPPING"
    )


from src.config.loader import load_data_contract, map_work_type


def test_load_data_contract():
    config = load_data_contract()

    assert config["version"] == "1.2"
    assert "work_types" in config


def test_map_connection():
    work_type, duration, error = map_work_type("Подключение")

    assert work_type == "CONNECTION"
    assert duration == 90
    assert error is None


def test_map_local_work():
    work_type, duration, error = map_work_type("Локальная заявка")

    assert work_type == "LOCAL_WORK"
    assert duration == 50
    assert error is None


def test_map_emergency():
    work_type, duration, error = map_work_type("Глобальная проблема")

    assert work_type == "EMERGENCY"
    assert duration == 100
    assert error is None


def test_map_add_order():
    work_type, duration, error = map_work_type("Дозаказ")

    assert work_type == "ADD_ORDER"
    assert duration == 40
    assert error is None


def test_unknown_work_type():
    work_type, duration, error = map_work_type("Что-то неизвестное")

    assert work_type is None
    assert duration is None
    assert error == "UNKNOWN_WORK_TYPE_MAPPING"


def test_empty_work_type():
    work_type, duration, error = map_work_type("")

    assert work_type is None
    assert duration is None
    assert error == "UNKNOWN_WORK_TYPE_MAPPING"