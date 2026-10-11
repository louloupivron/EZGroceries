"""Migros shopping list naming and lookup for the weekly workflow."""

from __future__ import annotations

import os
from datetime import date

from comida.basket import _load_dotenv, get_basket_for_list, list_shopping_lists
from comida.kookd_export import _to_kookd_label
from comida.migros_client import fetch_product_details

_MIGROS_LISTS_URL = "https://www.migros.ch/fr/shopping-list"


def week_key(d: date | None = None) -> str:
    """ISO year-week identifier, e.g. 2026-W37."""
    when = d or date.today()
    year, week, _ = when.isocalendar()
    return f"{year}-W{week:02d}"


def week_list_name_from_env() -> str | None:
    _load_dotenv()
    raw = os.environ.get("COMIDA_WEEK_LIST_NAME", "").strip()
    return raw or None


def find_list(name: str) -> dict | None:
    needle = name.strip().lower()
    for lst in list_shopping_lists():
        list_name = (lst.get("shoppingListName") or lst.get("name") or "").strip()
        if list_name.lower() == needle:
            return lst
    return None


def list_exists(name: str) -> bool:
    return find_list(name) is not None


def list_item_count(name: str) -> int:
    lst = find_list(name)
    if not lst:
        return 0
    return int(lst.get("itemsCount") or lst.get("itemCount") or 0)


def list_products_raw(list_name: str) -> list[str]:
    """All products on the list, labels in French (no Comida filters)."""
    basket = get_basket_for_list(list_name=list_name)
    uids = [int(item["productId"]) for item in basket.get("items", []) if item.get("productId")]
    if not uids:
        return []
    return [_to_kookd_label(p) for p in fetch_product_details(uids)]


def list_link_hint(list_name: str) -> str:
    """Best-effort link text for Telegram (slug rarely available via API)."""
    from comida.basket import shared_list_url

    slug_url = shared_list_url()
    lst = find_list(list_name)
    if lst:
        list_id = lst.get("shoppingListId") or lst.get("id")
        lines = [f"Liste « {list_name} » — {list_item_count(list_name)} article(s)"]
        if slug_url:
            lines.append(slug_url)
        else:
            lines.append(_MIGROS_LISTS_URL)
            if list_id:
                lines.append(f"(id Migros {list_id})")
        return "\n".join(lines)
    return f"{_MIGROS_LISTS_URL}\n(cherchez la liste « {list_name} »)"
