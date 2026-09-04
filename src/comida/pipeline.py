"""Promo-first shopping list generation from Kookd exports."""

from pathlib import Path

from comida.matcher import (
    ProductMatch,
    rank_products,
    _display_name,
    _is_mbudget,
    _price_chf,
    _product_id,
    _promo_candidates,
)
from comida.migros_client import search_products
from comida.pantry import filter_pantry
from comida.parser import Ingredient, merge_ingredients, parse_kookd_export, scale_ingredients
from comida.promo_cache import fetch_promotions_cached
from comida.quantities import DEFAULT_PORTIONS
from comida.synonyms import search_terms


def run_promo_first(
    recipe_path: Path,
    pantry_path: Path,
    max_promo_products: int = 1224,
    *,
    portions: int = DEFAULT_PORTIONS,
    base_portions: int = DEFAULT_PORTIONS,
    refresh_promos: bool = False,
) -> dict:
    text = recipe_path.read_text(encoding="utf-8")
    ingredients = parse_kookd_export(text)
    ingredients = scale_ingredients(
        ingredients,
        base_portions=base_portions,
        target_portions=portions,
    )
    return _run_promo_first_on_ingredients(
        ingredients,
        pantry_path,
        recipe_label=str(recipe_path),
        max_promo_products=max_promo_products,
        refresh_promos=refresh_promos,
        portions=portions,
    )


def run_promo_first_multi(
    recipe_paths: list[Path],
    pantry_path: Path,
    max_promo_products: int = 1224,
    *,
    portions: int = DEFAULT_PORTIONS,
    base_portions: int = DEFAULT_PORTIONS,
    refresh_promos: bool = False,
) -> dict:
    all_ingredients: list[Ingredient] = []
    labels: list[str] = []
    for path in recipe_paths:
        text = path.read_text(encoding="utf-8")
        all_ingredients.extend(parse_kookd_export(text))
        labels.append(path.name)
    merged = merge_ingredients(all_ingredients)
    merged = scale_ingredients(
        merged,
        base_portions=base_portions,
        target_portions=portions,
    )
    recipe_label = ", ".join(labels) if len(labels) > 1 else (labels[0] if labels else "?")
    return _run_promo_first_on_ingredients(
        merged,
        pantry_path,
        recipe_label=recipe_label,
        max_promo_products=max_promo_products,
        refresh_promos=refresh_promos,
        portions=portions,
    )


def _run_promo_first_on_ingredients(
    ingredients: list[Ingredient],
    pantry_path: Path,
    recipe_label: str,
    max_promo_products: int = 1224,
    *,
    refresh_promos: bool = False,
    portions: int = DEFAULT_PORTIONS,
) -> dict:
    to_buy, skipped = filter_pantry(ingredients, pantry_path)

    promo_ids_list, promo_products, promo_meta = fetch_promotions_cached(
        force_refresh=refresh_promos,
        max_promo_products=max_promo_products,
    )
    promo_ids = set(promo_ids_list)

    matches: list[ProductMatch] = []
    unmatched: list[str] = []
    ambiguous: list[ProductMatch] = []

    for ingredient in to_buy:
        terms = search_terms(ingredient.name)
        promo_pool = _promo_candidates(ingredient.name, promo_products)
        match = rank_products(ingredient, promo_pool, promo_ids, "promotion", extra_terms=terms)
        if match and match.score >= 78 and match.is_promotion:
            matches.append(match)
            if match.ambiguous:
                ambiguous.append(match)
            continue

        terms = search_terms(ingredient.name)
        search_hits: list[dict] = []
        seen_uids: set[int] = set()
        for term in terms:
            for product in search_products(term):
                uid = _product_id(product)
                if uid and uid not in seen_uids:
                    seen_uids.add(uid)
                    search_hits.append(product)
        search_hits = [p for p in search_hits if not _is_mbudget(p)]
        match = rank_products(ingredient, search_hits, promo_ids, "search", extra_terms=terms)
        if match and match.score >= 65:
            matches.append(match)
            if match.ambiguous:
                ambiguous.append(match)
        else:
            unmatched.append(ingredient.name)

    return {
        "recipe": recipe_label,
        "portions": portions,
        "ingredients_total": len(ingredients),
        "pantry_skipped": [(i.raw, rule) for i, rule in skipped],
        "to_buy_count": len(to_buy),
        "promotions_indexed": promo_meta["promotions_indexed"],
        "promotions_total": promo_meta["promotions_total"],
        "promotions_from_cache": promo_meta["from_cache"],
        "promotions_fetched_at": promo_meta.get("fetched_at"),
        "matches": [_format_match(m) for m in matches],
        "ambiguous": [_format_match(m) for m in ambiguous],
        "unmatched": unmatched,
    }


def _format_match(match: ProductMatch) -> dict:
    product = match.product
    offer = product.get("offer") or {}
    return {
        "ingredient": match.ingredient.raw,
        "ingredient_name": match.ingredient.name,
        "quantity_needed": f"{match.ingredient.quantity:g} {match.ingredient.unit}",
        "product_uid": _product_id(product),
        "name": _display_name(product),
        "package": offer.get("quantity"),
        "price_chf": _price_chf(product),
        "on_promotion": match.is_promotion,
        "source": match.source,
        "score": round(match.score, 1),
        "ambiguous": match.ambiguous,
        "alternatives": [
            {
                "uid": _product_id(alt),
                "name": _display_name(alt),
                "price_chf": _price_chf(alt),
                "package": (alt.get("offer") or {}).get("quantity"),
            }
            for alt in match.alternatives
        ],
    }
