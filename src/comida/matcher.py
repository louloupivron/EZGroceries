"""Match ingredients to Migros products (promo-first, exclude M-Budget)."""

import re

from dataclasses import dataclass
from rapidfuzz import fuzz

from comida.parser import Ingredient

MBUDGET_MARKERS = ("m-budget", "mbudget", "m budget")


@dataclass
class ProductMatch:
    ingredient: Ingredient
    product: dict
    score: float
    source: str  # "promotion" | "search"
    is_promotion: bool
    ambiguous: bool
    alternatives: list[dict]


def _product_id(product: dict) -> int | None:
    uid = product.get("uid")
    if uid is not None:
        return int(uid)
    online = product.get("migrosOnlineId")
    if online is not None:
        return int(online)
    pid = product.get("productId")
    return int(pid) if pid is not None else None


def _display_name(product: dict) -> str:
    brand = product.get("brand") or ""
    name = product.get("name") or product.get("description") or ""
    return f"{brand} {name}".strip()


def _is_mbudget(product: dict) -> bool:
    brand = (product.get("brand") or "").lower()
    slug = (product.get("productInformation", {}).get("mainInformation", {}).get("brand", {}).get("slug") or "").lower()
    text = _display_name(product).lower()
    return any(m in brand or m in slug or m in text for m in MBUDGET_MARKERS)


def _price_chf(product: dict) -> float | None:
    offer = product.get("offer") or {}
    price = offer.get("price") or {}
    return price.get("effectiveValue") or price.get("advertisedValue")


def _score_name(ingredient_name: str, product: dict, extra_terms: list[str] | None = None) -> float:
    target = ingredient_name.lower()
    text = _display_name(product).lower()
    candidates = [
        product.get("name") or "",
        product.get("description") or "",
        _display_name(product),
    ]
    scores = [fuzz.token_set_ratio(target, c.lower()) for c in candidates]
    for term in extra_terms or []:
        scores.append(fuzz.partial_ratio(term.lower(), text))
    return max(scores)


def _significant_tokens(name: str) -> list[str]:
    stop = {"de", "du", "la", "le", "les", "d", "et", "en", "feuilles", "frais", "fraîche", "pièce"}
    tokens = re.findall(r"[a-zàâäéèêëïîôùûüç]+", name.lower())
    return [t for t in tokens if len(t) > 2 and t not in stop]


def search_query(ingredient_name: str) -> str:
    tokens = _significant_tokens(ingredient_name)
    if tokens:
        return tokens[0]
    return ingredient_name


def _promo_candidates(ingredient_name: str, products: list[dict]) -> list[dict]:
    tokens = _significant_tokens(ingredient_name)
    if not tokens:
        return products
    out: list[dict] = []
    for product in products:
        text = _display_name(product).lower()
        if any(t in text for t in tokens):
            out.append(product)
        elif _score_name(ingredient_name, product) >= 80:
            out.append(product)
    return out


def _is_non_food(product: dict) -> bool:
    text = _display_name(product).lower()
    markers = (
        "shampoo", "conditioner", "maske", "dreamies", "edgard",
        "für katzen", "hundefutter", "tier",
    )
    return any(m in text for m in markers)


def _is_prepared_food(product: dict) -> bool:
    text = _display_name(product).lower()
    markers = (
        "parmentier", "bagel", "snack", "cracker", "plat ", "préparé",
        "chüechli", "chuechli", "gewürzgurken",
    )
    return any(m in text for m in markers)


def rank_products(
    ingredient: Ingredient,
    products: list[dict],
    promo_ids: set[int],
    source: str,
    ambiguity_gap: float = 8.0,
    extra_terms: list[str] | None = None,
) -> ProductMatch | None:
    candidates: list[tuple[dict, float]] = []
    wants_fresh = "frais" in ingredient.name.lower() or "fraîche" in ingredient.name.lower()
    for product in products:
        if _is_mbudget(product):
            continue
        if _is_non_food(product):
            continue
        if _is_prepared_food(product):
            continue
        if wants_fresh and "rauch" in _display_name(product).lower():
            continue
        score = _score_name(ingredient.name, product, extra_terms)
        if score < 55:
            continue
        pid = _product_id(product)
        if pid and pid in promo_ids:
            score += 8
        candidates.append((product, score))

    if not candidates:
        return None

    candidates.sort(key=lambda x: x[1], reverse=True)
    best_product, best_score = candidates[0]
    second_score = candidates[1][1] if len(candidates) > 1 else 0
    ambiguous = len(candidates) > 1 and (best_score - second_score) < ambiguity_gap

    pid = _product_id(best_product)
    return ProductMatch(
        ingredient=ingredient,
        product=best_product,
        score=best_score,
        source=source,
        is_promotion=bool(pid and pid in promo_ids),
        ambiguous=ambiguous,
        alternatives=[p for p, _ in candidates[1:4]],
    )


