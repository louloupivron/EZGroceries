"""Match recipe ingredients to products on the configured Migros shopping list."""

from __future__ import annotations

from dataclasses import dataclass

from rapidfuzz import fuzz

from comida.basket import default_list_name, get_basket_for_list
from comida.kookd_export import _to_kookd_label
from comida.matcher import (
    ProductMatch,
    _is_mbudget,
    _is_non_food,
    _is_prepared_food,
    _product_id,
    _significant_tokens,
)
from comida.migros_client import fetch_product_details
from comida.parser import Ingredient
from comida.synonyms import search_terms


@dataclass(frozen=True)
class ListProduct:
    product: dict
    label: str
    uid: int


def load_shopping_list_catalog(list_name: str | None = None) -> list[ListProduct]:
    """Products on the Migros shopping list (e.g. S1) with Kookd-style labels."""
    name = list_name or default_list_name()
    basket = get_basket_for_list(list_name=name)
    uids = [int(item["productId"]) for item in basket.get("items", []) if item.get("productId")]
    if not uids:
        return []

    catalog: list[ListProduct] = []
    for product in fetch_product_details(uids):
        uid = _product_id(product)
        if uid is None:
            continue
        catalog.append(ListProduct(product=product, label=_to_kookd_label(product), uid=uid))
    return catalog


def _score_ingredient_to_label(ingredient_name: str, label: str, extra_terms: list[str]) -> float:
    target = ingredient_name.lower()
    label_low = label.lower()
    scores = [
        fuzz.token_set_ratio(target, label_low),
        fuzz.partial_ratio(target, label_low),
        fuzz.partial_ratio(label_low, target),
    ]
    for term in extra_terms:
        scores.append(fuzz.token_set_ratio(term.lower(), label_low))
    return max(scores)


def _labels_align(ingredient_name: str, label: str, extra_terms: list[str]) -> bool:
    """Require a shared meaningful token so carottes ≠ chou-fleur."""
    blobs = [ingredient_name.lower(), label.lower(), *[t.lower() for t in extra_terms]]
    token_sets = [{t for t in _significant_tokens(b) if len(t) >= 4} for b in blobs]
    if len(token_sets) >= 2 and token_sets[0] & token_sets[1]:
        return True
    for term in extra_terms:
        if len(term) >= 4 and term.lower() in label.lower():
            return True
    return False


def match_ingredient_to_list(
    ingredient: Ingredient,
    catalog: list[ListProduct],
    promo_ids: set[int],
    *,
    min_score: float = 78,
    used_uids: set[int] | None = None,
) -> ProductMatch | None:
    """Pick the best product from the shopping list for this ingredient."""
    terms = search_terms(ingredient.name)
    blocked = used_uids or set()
    candidates: list[tuple[ListProduct, float]] = []

    for item in catalog:
        if item.uid in blocked:
            continue
        product = item.product
        if _is_mbudget(product) or _is_non_food(product) or _is_prepared_food(product):
            continue
        score = _score_ingredient_to_label(ingredient.name, item.label, terms)
        if score < min_score:
            continue
        if score < 88 and not _labels_align(ingredient.name, item.label, terms):
            continue
        if item.uid in promo_ids:
            score += 5
        candidates.append((item, score))

    if not candidates:
        return None

    candidates.sort(key=lambda x: x[1], reverse=True)
    best_item, best_score = candidates[0]
    second_score = candidates[1][1] if len(candidates) > 1 else 0
    ambiguous = len(candidates) > 1 and (best_score - second_score) < 8

    return ProductMatch(
        ingredient=ingredient,
        product=best_item.product,
        score=best_score,
        source="shopping_list",
        is_promotion=best_item.uid in promo_ids,
        ambiguous=ambiguous,
        alternatives=[c.product for c, _ in candidates[1:4]],
    )
