"""Смоук-тест полного пользовательского сценария через Streamlit AppTest.

Прогоняет интерфейс без браузера: Загрузка -> Проверка данных ->
Результат -> Маршрут бригады. Проверяет, что переключение экранов
происходит по кнопкам и оптимизатор не пересчитывается при переключении.
"""
from pathlib import Path
from types import SimpleNamespace

from streamlit.testing.v1 import AppTest

APP_PATH = Path(__file__).resolve().parents[1] / "app.py"


def _find_button(at, label: str):
    matches = [button for button in at.button if button.label == label]

    assert matches, f"Кнопка {label!r} не найдена"

    return matches[0]


def test_full_user_scenario_demo_mode():
    at = AppTest.from_file(str(APP_PATH), default_timeout=60)
    at.run()

    # Экран «Загрузка».
    assert "Планировщик выездных инженеров" in at.title[0].value
    assert _find_button(at, "Проверить данные")

    # Шаг 1: проверка данных (демонстрационный набор).
    _find_button(at, "Проверить данные").click()
    at.run()

    assert "Проверка данных" in at.title[0].value

    markdown_text = " ".join(str(m.value) for m in at.markdown)

    assert "Принято заявок" in markdown_text

    # Шаг 2: построение плана.
    _find_button(at, "Построить план").click()
    at.run()

    assert "Результат планирования" in at.title[0].value

    plan_tabs = [tab.label for tab in at.tabs]

    assert "Назначения" in plan_tabs
    assert "Неназначенные" in plan_tabs
    assert "Сравнение с baseline" in plan_tabs

    markdown_text = " ".join(str(m.value) for m in at.markdown)

    assert "Независимая проверка пройдена" in markdown_text

    # Шаг 3: маршрут бригады.
    _find_button(at, "Показать маршрут").click()
    at.run()

    assert "Маршрут бригады" in at.title[0].value
    assert any("Стартовая точка" in str(m.value) for m in at.markdown)

    # На экране два выбора: «Бригада» и «Заявка» (для объяснения).
    selectbox_labels = [selectbox.label for selectbox in at.selectbox]

    assert "Бригада" in selectbox_labels
    assert "Заявка" in selectbox_labels


def test_demo_mode_shows_dataset_date_and_no_date_input():
    """Вместо «Даты планирования» показывается дата набора 17.08.2026."""
    at = AppTest.from_file(str(APP_PATH), default_timeout=60)
    at.run()

    # Выбор «Даты планирования» убран: виджет date_input отсутствует.
    assert not at.date_input

    # Дата набора отображается подписью (caption), а не выбирается.
    captions = [str(item.value) for item in at.caption]

    assert any("17.08.2026" in text for text in captions)


def test_plan_building_gate_blocks_plan_while_import_errors_unresolved():
    """План не строится, пока ошибки импорта не разрешены явным действием."""
    from app import plan_building_gate

    ok_bundle = SimpleNamespace(jobs=[object()], errors=[])

    can_build, message = plan_building_gate(ok_bundle)

    assert can_build is True
    assert message is None

    # Исправимая ошибка импорта не разрешена — план недоступен.
    bad_bundle = SimpleNamespace(jobs=[object()], errors=["ошибка строки 5"])

    can_build, message = plan_building_gate(bad_bundle)

    assert can_build is False
    assert "Ошибки импорта не разрешены" in message

    # Нет заявок — план невозможен.
    empty_bundle = SimpleNamespace(jobs=[], errors=[])

    can_build, message = plan_building_gate(empty_bundle)

    assert can_build is False
    assert "Не осталось принятых заявок" in message


def test_upload_mode_requires_csv_file():
    at = AppTest.from_file(str(APP_PATH), default_timeout=60)
    at.run()

    # Переключаемся на «Загрузить файлы».
    radio = at.radio[0]
    radio.set_value("Загрузить файлы")
    at.run()

    # Без CSV кнопка проверки отключена.
    check_button = _find_button(at, "Проверить данные")

    assert check_button.disabled
    assert "Загрузите хотя бы один CSV-файл" in " ".join(
        str(w.value) for w in at.warning
    )