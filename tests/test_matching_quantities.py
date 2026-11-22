"""Cases that used to slip through: wrong food, wrong packs, pantry, refresh, push."""

from pathlib import Path

from comida.basket import merge_items_by_uid, resolved_to_basket_items
from comida.ingredient_guards import product_fits_ingredient, product_name_fits_ingredient
from comida.pantry import filter_pantry, find_pantry_match, is_always_buy, load_pantry
from comida.parser import Ingredient
from comida.quantities import compute_basket_quantity
from comida.synonyms import search_terms
from comida.list_catalog import ListProduct
from comida.validation import apply_favorites_workflow, confirm_quantity, rebuild_pending_for_refresh

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
    assert product_fits_ingredient(
        "Pain brioché pour burger", _product("Burger Buns", "Pasquier")
    )
    assert not product_fits_ingredient(
        "Pain brioché pour burger",
        _product("Brioche Hot Dog Buns", "American Favorites"),
    )
    assert product_name_fits_ingredient("Pain brioché pour burger", "Pasquier Burger Buns")
    assert "rucola" in search_terms("Roquette")
    assert "reismilch" not in search_terms("riz à sushi")
    assert "reisdrink" not in search_terms("riz")
    assert "reisdrink" in search_terms("lait de riz")


def test_favorite_roquette_matches_rucola_in_favorites():
    from comida.favorites import match_ingredient_to_favorite

    favorites = [{
        "uid": 100005580,
        "name": "Rucola",
        "brand": "Migros",
        "offer": {"quantity": "125 g"},
    }]
    match = match_ingredient_to_favorite("Roquette", favorites, set())
    assert match is not None
    assert match["uid"] == 100005580


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


def test_sausages_already_on_the_list_are_not_a_missing_favorite():
    product = {
        "uid": 42,
        "name": "Schweinsbratwurst",
        "brand": "Migros",
        "offer": {"quantity": "4 Stück"},
    }
    catalog = [ListProduct(product=product, label="saucisses de porc", uid=42)]
    session = {
        "pending": [],
        "resolved": [],
        "needs_favorite": [],
        "unmatched": [{
            "key": "saucisses-rotir",
            "ingredient_name": "Saucisses à rôtir",
            "quantity": "4 unités",
            "status": "manual",
        }],
        "weekly_staples": [],
    }
    out = apply_favorites_workflow(session, [], set(), catalog)
    assert out["needs_favorite"] == []
    assert out["resolved"][0]["source"] == "shopping_list"
    assert out["resolved"][0]["uid"] == 42


def test_confirm_lait_does_not_hit_lait_de_riz():
    session = {
        "resolved": [
            {
                "key": "lait-riz",
                "ingredient_name": "lait de riz",
                "quantity_parsed": 1,
                "quantity_confidence": "ok",
            },
            {
                "key": "lait",
                "ingredient_name": "lait",
                "quantity_parsed": 1,
                "quantity_confidence": "revue",
            },
        ]
    }
    confirm_quantity(session, "lait")
    by_key = {item["key"]: item for item in session["resolved"]}
    assert by_key["lait"]["quantity_confidence"] == "ok"
    assert by_key["lait-riz"]["quantity_confidence"] == "ok"


def test_list_prefers_whole_chicken_and_smoked_salmon():
    catalog = [
        ListProduct(
            product={"uid": 1, "name": "Poulet Geschnetzeltes", "brand": "Optigal", "offer": {"quantity": "400 g"}},
            label="poulet geschnetzeltes",
            uid=1,
        ),
        ListProduct(
            product={"uid": 2, "name": "Poulet ganz", "brand": "Optigal", "offer": {"quantity": "1.1 kg"}},
            label="poulet entier",
            uid=2,
        ),
        ListProduct(
            product={"uid": 3, "name": "Graved Lachs", "brand": "Migros", "offer": {"quantity": "100 g"}},
            label="saumon",
            uid=3,
        ),
        ListProduct(
            product={"uid": 4, "name": "Rauchlachs", "brand": "Migros", "offer": {"quantity": "100 g"}},
            label="saumon",
            uid=4,
        ),
    ]
    session = {
        "pending": [
            {
                "key": "poulet-entier",
                "ingredient_name": "Poulet entier",
                "quantity": "1.5 kg",
                "status": "pending",
                "options": [{
                    "uid": 1,
                    "name": "Optigal Poulet Geschnetzeltes",
                    "on_promotion": True,
                    "source": "promo",
                }],
            },
            {
                "key": "saumon-fume",
                "ingredient_name": "Saumon fumé",
                "quantity": "800 g",
                "status": "pending",
                "options": [{
                    "uid": 3,
                    "name": "Migros Graved Lachs",
                    "on_promotion": False,
                    "source": "search",
                }],
            },
        ],
        "resolved": [],
        "needs_favorite": [],
        "unmatched": [],
        "weekly_staples": [],
    }
    out = apply_favorites_workflow(session, [], set(), catalog)
    by_name = {item["ingredient_name"]: item for item in out["resolved"]}
    assert by_name["Poulet entier"]["uid"] == 2
    assert by_name["Poulet entier"]["source"] == "shopping_list"
    assert by_name["Saumon fumé"]["uid"] == 4
    assert by_name["Saumon fumé"]["source"] == "shopping_list"


def test_pending_search_can_still_become_a_favorite():
    favorites = [
        {"uid": 9, "name": "Mango", "brand": "Migros", "offer": {"quantity": "1 Stück"}},
        {"uid": 10, "name": "Blumenkohl", "brand": "Migros", "offer": {"quantity": "1 Stück"}},
        {"uid": 11, "name": "Edamame", "brand": "Migros", "offer": {"quantity": "200 g"}},
        {"uid": 12, "name": "Original Rösti", "brand": "M-Classic", "offer": {"quantity": "500 g"}},
    ]
    session = {
        "pending": [],
        "resolved": [],
        "needs_favorite": [
            {"key": "chou-fleur", "ingredient_name": "Chou-fleur", "quantity": "300 g", "status": "needs_favorite"},
            {"key": "edamames", "ingredient_name": "Edamames", "quantity": "240 g", "status": "needs_favorite"},
            {"key": "rosti", "ingredient_name": "Rösti déjà préparés", "quantity": "4 unités", "status": "needs_favorite"},
        ],
        "unmatched": [{
            "key": "mangue",
            "ingredient_name": "Mangue",
            "quantity": None,
            "status": "pending",
        }],
        "weekly_staples": [],
    }
    rebuild_pending_for_refresh(session)
    out = apply_favorites_workflow(session, favorites, set(), [])
    by_name = {item["ingredient_name"]: item for item in out["resolved"]}
    assert by_name["Mangue"]["uid"] == 9
    assert by_name["Chou-fleur"]["uid"] == 10
    assert by_name["Edamames"]["uid"] == 11
    assert by_name["Rösti déjà préparés"]["uid"] == 12
    assert out["needs_favorite"] == []
    assert out["unmatched"] == []
    assert not product_name_fits_ingredient("Concombre", "Chirat Gurken")
    assert product_name_fits_ingredient("Brocolis", "Farmer's Best Broccoli")
    assert product_name_fits_ingredient("Concombre", "Migros Gurken")
    assert not product_name_fits_ingredient("Concombre", "Migros Cornichons")
