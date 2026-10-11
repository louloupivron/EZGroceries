"""Cases that used to slip through: wrong food, wrong packs, pantry, refresh, push."""

from pathlib import Path

from comida.basket import merge_items_by_uid, resolved_to_basket_items
from comida.ingredient_guards import product_fits_ingredient, product_name_fits_ingredient
from comida.pantry import filter_pantry, find_pantry_match, is_always_buy, load_pantry
from comida.parser import Ingredient
from comida.quantities import compute_basket_quantity
from comida.synonyms import search_terms
from comida.validation import apply_favorites_workflow, rebuild_pending_for_refresh

ROOT = Path(__file__).resolve().parents[1]
PANTRY = ROOT / "garde-manger.txt"


def _product(name: str, brand: str = "") -> dict:
    return {"name": name, "brand": brand}


def test_identity_rejects_lookalikes():
    assert not product_fits_ingredient("riz à sushi", _product("Reisdrink", "Alnatura"))
    assert product_fits_ingredient("riz à sushi", _product("Sushi Reis", "Migros"))
    assert product_fits_ingredient("lait de riz", _product("Reisdrink", "Alnatura"))
    assert not product_fits_ingredient("curry", _product("Lessive", "Ariel"))
    assert not product_name_fits_ingredient("curry", "Lessive Ariel")
    assert not product_fits_ingredient("œufs", _product("Vorzugsbutter", "Floralp"))
    assert product_fits_ingredient("œufs", _product("Eier", "Migros"))
    assert not product_fits_ingredient("tortillas de blé", _product("Weissmehl"))
    assert not product_fits_ingredient("mangue", _product("Fanta Mango"))
    assert "reismilch" not in search_terms("riz à sushi")
    assert "reisdrink" not in search_terms("riz")
    assert "reisdrink" in search_terms("lait de riz")


def test_favorite_beats_promo_already_on_the_list():
    session = {
        "pending": [{
            "key": "framboises",
            "ingredient_name": "framboises",
            "quantity": "200 g",
            "options": [{
                "uid": 1,
                "name": "Framboises en chocolat",
                "package": "100 g",
                "on_promotion": True,
                "source": "shopping_list",
                "score": 96,
            }],
        }],
        "resolved": [],
        "unmatched": [],
        "needs_favorite": [],
        "weekly_staples": [],
    }
    favorites = [{
        "uid": 2,
        "name": "Framboises",
        "brand": "Migros",
        "offer": {"quantity": "250 g"},
    }]
    out = apply_favorites_workflow(session, favorites, set())
    assert len(out["resolved"]) == 1
    assert out["resolved"][0]["uid"] == 2
    assert out["resolved"][0]["source"] == "favorite"
    assert out["needs_favorite"] == []


def test_refresh_reopens_promo_and_list_lines():
    session = {
        "pending": [],
        "needs_favorite": [],
        "resolved": [
            {
                "key": "framboises",
                "ingredient_name": "framboises",
                "quantity": "200 g",
                "source": "promo",
                "uid": 9,
                "name": "Framboises en chocolat",
            },
            {
                "key": "cornichons",
                "ingredient_name": "cornichons",
                "quantity": "1 pièce",
                "source": "shopping_list",
                "uid": 4,
                "name": "Kit raclette",
            },
            {
                "key": "oeufs",
                "ingredient_name": "oeufs",
                "quantity": "8 pièce",
                "source": "favorite",
                "uid": 2,
                "name": "Eier",
            },
        ],
    }
    rebuild_pending_for_refresh(session)
    names = {item["ingredient_name"] for item in session["pending"]}
    assert names == {"framboises", "cornichons", "oeufs"}
    assert session["resolved"] == []


def test_pack_counts_and_confidence():
    mango = compute_basket_quantity("400 g", "1 Stück")
    assert mango.packs != 80
    assert mango.packs == 2
    assert mango.confidence == "revue"
    assert "200 g" in mango.note

    sausages = compute_basket_quantity("8 pièce", "2 × 140 g")
    assert sausages.packs == 4
    assert sausages.confidence == "ok"

    variable = compute_basket_quantity("400 g", "170–210 g")
    assert variable.packs == 3
    assert variable.confidence == "ok"

    unknown = compute_basket_quantity("200 g", "environ un filet")
    assert unknown.confidence == "revue"


def test_pantry_prefers_the_specific_spice_line():
    pantry, always_buy = load_pantry(PANTRY)
    assert find_pantry_match("épices à fajitas", pantry).name == "épices à fajitas"
    assert find_pantry_match("curry", pantry).name == "curry"
    assert is_always_buy("riz à sushi", always_buy) is not None

    fajitas = Ingredient(1, "pièce", "épices à fajitas", "- 1 pièce épices à fajitas")
    sushi = Ingredient(1, "pièce", "riz à sushi", "- 1 pièce riz à sushi")
    kept, skipped = filter_pantry([fajitas, sushi], PANTRY)
    assert [item.name for item in kept] == ["riz à sushi"]
    assert skipped[0][1] == "épices à fajitas"


def test_push_merges_uids_and_skips_review_quantities():
    merged = merge_items_by_uid([
        {"uid": 1, "quantity": 1, "ingredient_name": "saucisses"},
        {"uid": 1, "quantity": 4, "ingredient_name": "saucisses"},
    ])
    assert len(merged) == 1
    assert merged[0]["quantity"] == 5

    items = resolved_to_basket_items([
        {
            "uid": 2,
            "quantity_parsed": 2,
            "quantity_confidence": "revue",
            "ingredient_name": "mangue",
        },
        {
            "uid": 3,
            "quantity_parsed": 1,
            "quantity_confidence": "ok",
            "ingredient_name": "riz",
        },
        {
            "uid": 3,
            "quantity_parsed": 4,
            "quantity_confidence": "ok",
            "ingredient_name": "riz hebdo",
        },
    ])
    assert items == [{
        "uid": 3,
        "quantity": 5,
        "ingredient_name": "riz",
        "name": None,
    }]
