"""Pantry checklist (before analysis) and weekly edits (before push)."""

from __future__ import annotations

import re
from pathlib import Path

from comida.pantry import PantryStock, find_pantry_match, is_always_buy
from comida.parser import merge_ingredients, parse_kookd_export
from comida.stock_lists import load_lists, save_list
from comida.ui.workflow import EXPORTS_DIR, load_ui_state, save_ui_state

PRODUCT_URL_RE = re.compile(
    r"migros\.ch/(?:[a-z]{2}/)?product/(?:mo/)?(?P<id>\d{5,})",
    re.IGNORECASE,
)


def active_recipe_name(ui: dict | None = None) -> str | None:
    state = load_ui_state() if ui is None else ui
    name = state.get("recipe_export")
    if name:
        return Path(str(name)).name
    files = sorted(
        p for p in EXPORTS_DIR.glob("*.txt")
        if p.is_file() and not p.name.startswith("promos-")
    ) if EXPORTS_DIR.is_dir() else []
    return files[-1].name if files else None


def session_recipe_name(session: dict | None) -> str | None:
    if not session or not session.get("recipe"):
        return None
    return Path(str(session["recipe"])).name


def _recipe_path(recipe: str | None = None) -> Path:
    name = Path(recipe).name if recipe else active_recipe_name()
    if not name or name.startswith("promos-") or name != Path(name).name:
        raise FileNotFoundError("Export Kookd introuvable")
    path = EXPORTS_DIR / name
    if not path.is_file():
        raise FileNotFoundError(f"Export introuvable : exports/{name}")
    return path


def _stocks_from_items(items: list[dict]) -> tuple[list[PantryStock], list[PantryStock]]:
    pantry: list[PantryStock] = []
    always: list[PantryStock] = []
    for item in items:
        stock = PantryStock(
            str(item.get("name") or "").strip().lower(),
            item.get("quantity"),
            (item.get("unit") or None),
        )
        if item.get("always_buy"):
            always.append(stock)
        else:
            pantry.append(stock)
    return pantry, always


def pantry_checklist(recipe: str | None = None) -> dict:
    path = _recipe_path(recipe)
    ingredients = merge_ingredients(parse_kookd_export(path.read_text(encoding="utf-8")))
    items = load_lists()["pantry"]["items"]
    pantry, always = _stocks_from_items(items)
    rows = []
    for ing in ingredients:
        always_rule = is_always_buy(ing.name, always)
        match = None if always_rule else find_pantry_match(ing.name, pantry)
        rows.append({
            "name": ing.name,
            "quantity": f"{ing.quantity:g} {ing.unit}",
            "checked": bool(match),
            "covered_by": match.name if match else None,
            "always_buy": bool(always_rule),
        })
    ui = load_ui_state()
    return {
        "recipe": path.name,
        "items": rows,
        "confirmed": ui.get("pantry_done_for") == path.name,
    }


def _exact_indexes(items: list[dict], name: str) -> list[int]:
    target = name.lower()
    return [
        index for index, item in enumerate(items)
        if str(item.get("name") or "").strip().lower() == target and not item.get("always_buy")
    ]


def apply_pantry_checks(checked: list[str], recipe: str | None = None) -> dict:
    if not isinstance(checked, list):
        raise ValueError("checked doit être une liste")
    path = _recipe_path(recipe)
    before = pantry_checklist(path.name)
    wanted = []
    seen: set[str] = set()
    for raw in checked:
        name = str(raw or "").strip()
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        wanted.append(name)
    wanted_set = {name.lower() for name in wanted}

    items = load_lists()["pantry"]["items"]
    added: list[str] = []
    removed: list[str] = []
    still_covered: list[str] = []

    for row in before["items"]:
        name = row["name"]
        if row["always_buy"]:
            continue
        if name.lower() in wanted_set:
            pantry, _always = _stocks_from_items(items)
            if find_pantry_match(name, pantry):
                continue
            items.append({
                "name": name,
                "quantity": None,
                "unit": None,
                "always_buy": False,
            })
            added.append(name)
            continue
        indexes = _exact_indexes(items, name)
        if not indexes:
            pantry, _always = _stocks_from_items(items)
            if find_pantry_match(name, pantry):
                still_covered.append(name)
            continue
        drop = set(indexes)
        items = [item for index, item in enumerate(items) if index not in drop]
        removed.append(name)

    save_list("pantry", items)
    ui = load_ui_state()
    ui["pantry_done_for"] = path.name
    if added or removed:
        ui["analysis_stale"] = True
        ui["weekly_done_for"] = ""
    save_ui_state(ui)
    checklist = pantry_checklist(path.name)
    checklist["added"] = added
    checklist["removed"] = removed
    checklist["still_covered"] = still_covered
    return checklist


def parse_product_id(url: str) -> int:
    text = (url or "").strip()
    match = PRODUCT_URL_RE.search(text)
    if match:
        return int(match.group("id"))
    if re.fullmatch(r"\d{5,}", text):
        return int(text)
    raise ValueError(
        "Lien Migros invalide — ouvre la fiche produit et copie l’URL (…/product/123…)"
    )


def _product_option(url: str) -> dict:
    from comida.promo_cache import fetch_promotions_cached
    from comida.validation import _option_from_product_uid

    uid = parse_product_id(url)
    promo_ids = set(fetch_promotions_cached()[0])
    option = _option_from_product_uid(uid, promo_ids)
    if not option or not option.get("uid"):
        raise ValueError("Produit introuvable dans le catalogue Migros pour ce lien")
    return option


def _weekly_names(session: dict) -> set[str]:
    return {str(name).lower() for name in session.get("weekly_staples") or []}


def is_weekly_line(session: dict, item: dict) -> bool:
    if item.get("source") == "migros_link":
        return True
    return str(item.get("ingredient_name") or "").lower() in _weekly_names(session)


def weekly_board(session: dict | None) -> dict:
    if not session:
        return {"included": [], "excluded": [], "staples": []}
    included = [item for item in session.get("resolved", []) if is_weekly_line(session, item)]
    return {
        "included": included,
        "excluded": list(session.get("weekly_excluded") or []),
        "staples": list(session.get("weekly_staples") or []),
    }


def exclude_weekly_item(session: dict, key: str) -> dict:
    resolved = list(session.get("resolved", []))
    item = next((row for row in resolved if row.get("key") == key), None)
    if not item or not is_weekly_line(session, item):
        raise ValueError("Cette ligne ne fait pas partie des courses hebdo")
    session["resolved"] = [row for row in resolved if row.get("key") != key]
    excluded = [row for row in session.get("weekly_excluded") or [] if row.get("key") != key]
    excluded.append(item)
    session["weekly_excluded"] = excluded
    return session


def restore_weekly_item(session: dict, key: str) -> dict:
    excluded = list(session.get("weekly_excluded") or [])
    item = next((row for row in excluded if row.get("key") == key), None)
    if not item:
        raise ValueError("Ligne introuvable")
    session["weekly_excluded"] = [row for row in excluded if row.get("key") != key]
    resolved = list(session.get("resolved", []))
    if not any(row.get("key") == key for row in resolved):
        resolved.append(item)
    session["resolved"] = resolved
    return session


def add_migros_link(session: dict, url: str) -> dict:
    from comida.validation import _resolved_entry

    option = _product_option(url)
    uid = option["uid"]
    if any(row.get("uid") == uid for row in session.get("resolved", [])):
        raise ValueError("Ce produit est déjà dans la liste")
    name = option.get("name") or f"Produit {uid}"
    entry = _resolved_entry(f"lien-{uid}", name, "1 pièce", option, "migros_link")
    entry["quantity_parsed"] = 1
    entry["quantity_confidence"] = "ok"
    entry["quantity_note"] = ""
    entry["product_url"] = url.strip()
    session.setdefault("resolved", []).append(entry)
    return session


def confirm_weekly(session: dict) -> dict:
    name = session_recipe_name(session)
    if not name:
        raise ValueError("Aucune session à confirmer")
    ui = load_ui_state()
    ui["weekly_done_for"] = name
    save_ui_state(ui)
    return ui


def clear_weekly_confirmation() -> None:
    ui = load_ui_state()
    ui["weekly_done_for"] = ""
    save_ui_state(ui)
