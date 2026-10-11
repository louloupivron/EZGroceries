"""The shopping list stays les Avengers instead of rotating S3, S4, …"""

from comida.basket import DEFAULT_LIST_NAME, default_list_name
from comida.telegram_schedule import current_week_list_name


def test_default_list_name_is_les_avengers(monkeypatch):
    monkeypatch.setenv("MIGROS_SHOPPING_LIST_NAME", "les Avengers")
    assert default_list_name() == "les Avengers"
    assert DEFAULT_LIST_NAME == "les Avengers"


def test_week_list_does_not_advance_to_the_next_s(monkeypatch, tmp_path):
    monkeypatch.setenv("COMIDA_WEEK_LIST_NAME", "les Avengers")
    monkeypatch.setenv("MIGROS_SHOPPING_LIST_NAME", "les Avengers")
    monkeypatch.setattr("comida.telegram_schedule.STATE_PATH", tmp_path / "schedule.json")
    name = current_week_list_name({
        "week_key": "2020-W01",
        "list_name": "S3",
        "messages_sent": {"thu_am": "sent"},
    })
    assert name == "les Avengers"
    stored = (tmp_path / "schedule.json").read_text(encoding="utf-8")
    assert "S4" not in stored
    assert "les Avengers" in stored
