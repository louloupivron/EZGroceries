"""Migros favorite products (Mes produits)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from comida.matcher import _display_name, _price_chf, _product_id, rank_products
from comida.parser import Ingredient
from comida.synonyms import search_terms

ROOT = Path(__file__).resolve().parents[2]
FAVORITES_SCRIPT = ROOT / "scripts" / "migros-favorites.mjs"
MIGROS_MY_PRODUCTS_URL = "https://www.migros.ch/fr/my-products"

MATCH_THRESHOLD = 65


def fetch_favorites_with_details() -> list[dict]:
    """Return enriched favorite products with full `product` dict for matching."""
    proc = subprocess.run(
        ["node", str(FAVORITES_SCRIPT)],
        capture_output=True,
        text=True,
        cwd=ROOT,
        check=False,
    )
    if proc.returncode != 0:
        err = proc.stderr.strip() or proc.stdout.strip()
        try:
            payload = json.loads(err)
            raise RuntimeError(payload.get("error", err))
        except json.JSONDecodeError:
            raise RuntimeError(err)
    data = json.loads(proc.stdout)
    products: list[dict] = []
    for item in data.get("products", []):
        product = item.get("product") or {}
        if not product.get("uid"):
            product = {**product, "uid": item.get("uid")}
        products.append(product)
    return products


def match_ingredient_to_favorite(
    ingredient_name: str,
    favorite_products: list[dict],
    promo_ids: set[int],
) -> dict | None:
    """Best favorite product for an ingredient, or None."""
    if not favorite_products:
        return None
    ingredient = Ingredient(
        quantity=1,
        unit="pièce",
        name=ingredient_name,
        raw=f"- 1 pièce {ingredient_name}",
    )
    match = rank_products(
        ingredient,
        favorite_products,
        promo_ids,
        "favorite",
        extra_terms=search_terms(ingredient_name),
    )
    if not match or match.score < MATCH_THRESHOLD:
        return None
    product = match.product
    uid = _product_id(product)
    return {
        "uid": uid,
        "name": _display_name(product),
        "package": (product.get("offer") or {}).get("quantity"),
        "price_chf": _price_chf(product),
        "on_promotion": bool(uid and uid in promo_ids),
        "score": match.score,
        "product": product,
    }


def format_favorites_list(products: list[dict]) -> str:
    if not products:
        return f"Aucun favori. Ajoutez des produits sur {MIGROS_MY_PRODUCTS_URL}"
    lines = [f"Favoris Migros ({len(products)}) :", ""]
    for p in products:
        uid = _product_id(p)
        name = _display_name(p)
        price = _price_chf(p)
        price_s = f"{price} CHF" if price is not None else "prix ?"
        lines.append(f"  • {name} — {price_s} (uid {uid})")
    return "\n".join(lines)
