from pathlib import Path

from comida.stock_lists import load_lists, parse_entry_line, parse_stock_text, render_stock_text, save_list

PANTRY = """\
Huile en tout genre
riz 2 kg
+ riz à sushi

# Toujours acheter (+), même si un article garde-manger correspond
+ riz sushi
"""

WEEKLY = """\
# Ingrédients ajoutés à chaque semaine (en plus de l'export Kookd).
# Formats :
#   pain toast              → 1 pièce
#   6 pièces bananes

pain toast
6 pièces bananes
"""


def test_parse_keeps_case_quantity_and_always_buy():
    item = parse_entry_line("+ Riz à sushi", allow_always_buy=True)
    assert item == {
        "name": "Riz à sushi",
        "quantity": None,
        "unit": None,
        "always_buy": True,
    }
    qty = parse_entry_line("6 pièces Bananes", allow_always_buy=False)
    assert qty["name"] == "Bananes"
    assert qty["quantity"] == 6
    assert qty["unit"] == "pièces"
    assert qty["always_buy"] is False


def test_pantry_round_trip_groups_always_buy():
    _preamble, items = parse_stock_text(PANTRY, allow_always_buy=True)
    names = [(i["name"], i["always_buy"], i["quantity"]) for i in items]
    assert ("Huile en tout genre", False, None) in names
    assert ("riz", False, 2) in names
    assert ("riz à sushi", True, None) in names
    assert ("riz sushi", True, None) in names

    rendered = render_stock_text("", items, allow_always_buy=True)
    again = parse_stock_text(rendered, allow_always_buy=True)[1]
    assert [(i["name"], i["always_buy"]) for i in again] == [
        ("Huile en tout genre", False),
        ("riz", False),
        ("riz à sushi", True),
        ("riz sushi", True),
    ]
    assert "# Toujours acheter" in rendered
    assert rendered.index("riz 2 kg") < rendered.index("+ riz à sushi")


def test_weekly_keeps_header(tmp_path, monkeypatch):
    weekly = tmp_path / "courses-hebdo.txt"
    pantry = tmp_path / "garde-manger.txt"
    weekly.write_text(WEEKLY, encoding="utf-8")
    pantry.write_text("sel\n", encoding="utf-8")
    monkeypatch.setattr("comida.stock_lists.WEEKLY_PATH", weekly)
    monkeypatch.setattr("comida.stock_lists.PANTRY_PATH", pantry)
    monkeypatch.setitem(
        __import__("comida.stock_lists", fromlist=["KINDS"]).KINDS,
        "weekly",
        weekly,
    )
    monkeypatch.setitem(
        __import__("comida.stock_lists", fromlist=["KINDS"]).KINDS,
        "pantry",
        pantry,
    )

    saved = save_list("weekly", [
        {"name": "pain toast", "quantity": None, "unit": None},
        {"name": "lait", "quantity": 1, "unit": "l"},
    ])
    text = weekly.read_text(encoding="utf-8")
    assert text.startswith("# Ingrédients ajoutés")
    assert "pain toast" in text
    assert "lait 1 l" in text
    assert [item["name"] for item in saved["weekly"]["items"]] == ["pain toast", "lait"]
    assert Path(pantry).read_text(encoding="utf-8") == "sel\n"


def test_load_real_files_round_trip_shape():
    data = load_lists()
    assert data["pantry"]["items"]
    assert data["weekly"]["items"]
    assert any(item["always_buy"] for item in data["pantry"]["items"])
    assert all(not item["always_buy"] for item in data["weekly"]["items"])
