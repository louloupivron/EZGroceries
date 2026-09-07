"""Reject obviously wrong Migros products for a given ingredient name."""

from __future__ import annotations


def _display_name(product: dict) -> str:
    brand = product.get("brand") or ""
    name = product.get("name") or product.get("description") or ""
    return f"{brand} {name}".strip()

# (ingredient triggers, any required in product blob, forbidden substrings)
_RULES: list[tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]] = [
    (
        ("parmesan",),
        ("parmesan", "parmigiano", "grana", "emilio", "pecorino", "käse", "kase"),
        ("wein", "wine", "rotwein", "weisswein", "rosé", "bier", "rivella", "whisky"),
    ),
    (
        ("oignon", "oignons", "échalote"),
        ("zwiebel", "onion", "oignon", "échalote", "echalote"),
        ("champignon", "pilz", "pilze", "champi"),
    ),
    (
        ("champignon",),
        ("champignon", "pilz", "pilze", "champi"),
        ("zwiebel", "onion", "oignon"),
    ),
    (
        ("sauce tomate",),
        ("passata", "tomatensauce", "pummar", "pummaro", "mutti", "arrabbiata", "bolognese", "sugo"),
        ("chimichurri", "ketchup", "mayonnaise", "mayo", "wein", "soja", "soy"),
    ),
    (
        ("sauce soja",),
        ("sojasauce", "sojasaus", "ketjap", "soy sauce", "sojasosse"),
        ("chimichurri", "ketchup", "tomat", "passata", "wein", "chipotle", "adobo", "pepper",
         "bolognese", "marinara", "arrabbiata", "pesto"),
    ),
    (
        ("origan", "oregano"),
        ("origan", "oregano", "kräuter", "krauter", "gewürz", "gewurz", "herb"),
        ("pringles", "chips", "crisp", "snack", "popcorn"),
    ),
    (
        ("passata",),
        ("passata", "tomatensauce", "pummar", "pummaro", "mutti", "arrabbiata", "bolognese", "sugo"),
        ("chimichurri", "ketchup", "mayonnaise", "mayo", "wein", "soja", "soy"),
    ),
    (
        ("carotte", "carottes"),
        ("karotte", "carotte", "carrot"),
        ("erbsen", "gartenerbsen", "pois", "peas", "sterilcat", "katzen", "snack",
         "terrine", "tiernahrung", "hundefutter", "natural selection"),
    ),
    (
        ("pain toast", "toast"),
        ("toast", "toastbrot", "brot"),
        ("pizza", "pizzateig", "teig", "pâte"),
    ),
    (
        ("banane", "bananes"),
        ("banane", "banana", "platanos", "bananen"),
        ("salat", "salad", "avocat"),
    ),
    (
        ("lait de riz",),
        ("reis", "rice", "reismilch", "reisdrink", "lait de riz", "boisson de riz"),
        ("salat", "salad", "fromage", "käse", "kase"),
    ),
]

_GENERIC_MATCH_TERMS = frozenset({"sauce", "tomate", "tomates", "blanc", "vert", "verts"})
_BEVERAGE_MARKERS = (
    "wein", "wine", "rotwein", "weisswein", "rosé", "rosewein", "bier", "rivella",
    "whisky", "gin ", "vodka", "prosecco", "champagner", "cava", "aperol",
)
_SNACK_MARKERS = ("pringles", "popcorn", "doritos", "lays ", "crisp", "chips ")


def _product_blob(product: dict) -> str:
    title = (product.get("title") or "").replace("·", " ").lower()
    return f"{_display_name(product).lower()} {title} {(product.get('name') or '').lower()}"


def _name_blob(product_name: str) -> str:
    return product_name.lower()


def _rule_for(ingredient_name: str) -> tuple[tuple[str, ...], tuple[str, ...]] | None:
    low = ingredient_name.lower()
    for triggers, required, forbidden in _RULES:
        if any(t in low for t in triggers):
            return required, forbidden
    return None


def product_fits_ingredient(
    ingredient_name: str,
    product: dict,
    extra_terms: list[str] | None = None,
) -> bool:
    blob = _product_blob(product)
    if any(m in blob for m in _BEVERAGE_MARKERS):
        # Cheese/meat names sometimes contain "blanc" — only block clear beverages.
        if not any(k in blob for k in ("käse", "kase", "fromage", "schinken", "jambon", "ham")):
            if any(k in ingredient_name.lower() for k in ("parmesan", "jambon", "mozzarella", "fromage")):
                return False
            if any(k in ingredient_name.lower() for k in ("sauce", "origan", "oignon", "carotte", "thon")):
                return False
    if any(m in blob for m in _SNACK_MARKERS):
        if "origan" in ingredient_name.lower() or "oregano" in ingredient_name.lower():
            return False

    rule = _rule_for(ingredient_name)
    if not rule:
        return True
    required, forbidden = rule
    if any(f in blob for f in forbidden):
        return False
    if any(r in blob for r in required):
        return True
    from comida.synonyms import search_terms

    for term in extra_terms or search_terms(ingredient_name):
        low = term.lower()
        if len(low) < 4 or low in _GENERIC_MATCH_TERMS:
            continue
        if low in blob and (low in required or any(low in r for r in required)):
            return True
    return False


def product_name_fits_ingredient(ingredient_name: str, product_name: str) -> bool:
    """Lightweight check when only the display name is available (validation options)."""
    blob = _name_blob(product_name)
    rule = _rule_for(ingredient_name)
    if any(m in blob for m in _BEVERAGE_MARKERS):
        if any(k in ingredient_name.lower() for k in ("parmesan", "sauce", "origan", "oignon")):
            return False
    if any(m in blob for m in _SNACK_MARKERS) and "origan" in ingredient_name.lower():
        return False
    if not rule:
        return True
    required, forbidden = rule
    if any(f in blob for f in forbidden):
        return False
    from comida.synonyms import search_terms

    return any(r in blob for r in required) or any(
        t.lower() in blob for t in search_terms(ingredient_name) if len(t) >= 4
    )
