from comida.pantry import load_pantry
from comida.prep import (
    add_migros_link,
    apply_pantry_checks,
    exclude_weekly_item,
    pantry_checklist,
    parse_product_id,
    restore_weekly_item,
)
from comida.ui.workflow import compute_workflow


KOOKD = """\
Produce:
• 500 g Riz blanc
• 300 g Polenta
• 16 c.à.s Huile d'olive
"""

PANTRY = """\
huile en tout genre
polenta

# Toujours acheter (+), même si un article garde-manger correspond
+ sauce soja
"""


def _patch_files(tmp_path, monkeypatch):
    exports = tmp_path / "exports"
    exports.mkdir()
    (exports / "semaine.txt").write_text(KOOKD, encoding="utf-8")
    pantry = tmp_path / "garde-manger.txt"
    pantry.write_text(PANTRY, encoding="utf-8")
    weekly = tmp_path / "courses-hebdo.txt"
    weekly.write_text("pain toast\n", encoding="utf-8")
    state = tmp_path / "ui_state.json"
    monkeypatch.setattr("comida.prep.EXPORTS_DIR", exports)
    monkeypatch.setattr("comida.ui.workflow.EXPORTS_DIR", exports)
    monkeypatch.setattr("comida.ui.workflow.UI_STATE_PATH", state)
    monkeypatch.setattr("comida.stock_lists.PANTRY_PATH", pantry)
    monkeypatch.setattr("comida.stock_lists.WEEKLY_PATH", weekly)
    monkeypatch.setitem(
        __import__("comida.stock_lists", fromlist=["KINDS"]).KINDS, "pantry", pantry
    )
    monkeypatch.setitem(
        __import__("comida.stock_lists", fromlist=["KINDS"]).KINDS, "weekly", weekly
    )
    return pantry


def test_parse_product_id():
    assert parse_product_id("https://www.migros.ch/fr/product/120110800000") == 120110800000
    assert parse_product_id("https://www.migros.ch/fr/product/mo/120110800000?utm=1") == 120110800000
    assert parse_product_id("120110800000") == 120110800000


def test_pantry_check_adds_exact_name_and_keeps_broad_rule(tmp_path, monkeypatch):
    pantry = _patch_files(tmp_path, monkeypatch)
    rows = {row["name"]: row for row in pantry_checklist("semaine.txt")["items"]}
    assert rows["Riz blanc"]["checked"] is False
    assert rows["Polenta"]["checked"] is True
    assert rows["Huile d'olive"]["checked"] is True
    assert rows["Huile d'olive"]["covered_by"] == "huile en tout genre"

    result = apply_pantry_checks(["Riz blanc", "Polenta"], "semaine.txt")
    assert result["added"] == ["Riz blanc"]
    assert result["confirmed"] is True
    text = pantry.read_text(encoding="utf-8")
    assert "Riz blanc" in text
    assert "huile en tout genre" in text
    stocks, _always = load_pantry(pantry)
    assert any(item.name == "riz blanc" for item in stocks)

    again = apply_pantry_checks(["Polenta"], "semaine.txt")
    assert "Riz blanc" not in pantry.read_text(encoding="utf-8")
    assert again["removed"] == ["Riz blanc"]
    assert "Huile d'olive" in again["still_covered"]


def test_workflow_pantry_before_analysis_and_weekly_before_push(tmp_path, monkeypatch):
    _patch_files(tmp_path, monkeypatch)
    session = {
        "recipe": "semaine.txt",
        "resolved": [{"key": "pain", "ingredient_name": "pain toast", "uid": 1}],
        "pending": [],
        "needs_favorite": [],
        "unmatched": [],
    }
    flow = compute_workflow(session)
    assert flow["current_step"] == "pantry"
    assert [step["id"] for step in flow["steps"]][:5] == [
        "kookd", "pantry", "week", "validate", "weekly",
    ]

    apply_pantry_checks(["Polenta", "Huile d'olive"], "semaine.txt")
    flow = compute_workflow(session)
    assert flow["current_step"] == "weekly"


def test_weekly_exclude_restore_and_link(monkeypatch):
    session = {
        "recipe": "semaine.txt",
        "weekly_staples": ["pain toast"],
        "resolved": [{
            "key": "pain",
            "ingredient_name": "pain toast",
            "uid": 1,
            "name": "Pain",
            "source": "favorite",
        }],
        "weekly_excluded": [],
    }
    exclude_weekly_item(session, "pain")
    assert session["resolved"] == []
    assert session["weekly_excluded"][0]["key"] == "pain"
    restore_weekly_item(session, "pain")
    assert session["resolved"][0]["uid"] == 1

    monkeypatch.setattr(
        "comida.prep._product_option",
        lambda url: {"uid": 99, "name": "Yaourt", "package": "180 g", "price_chf": 1.2, "on_promotion": False},
    )
    add_migros_link(session, "https://www.migros.ch/fr/product/99")
    added = session["resolved"][-1]
    assert added["source"] == "migros_link"
    assert added["uid"] == 99
    assert added["quantity_confidence"] == "ok"
    assert added["quantity_parsed"] == 1
