"""Conversational validation session for Cursor (option C)."""

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from comida.matcher import _display_name, _price_chf, _product_id
from comida.budget import estimate_basket, format_budget_summary, format_basket_enriched
from comida.quantities import compute_basket_quantity
from comida.mappings import (
    DEFAULT_PATH as MAPPINGS_PATH,
    get_entry,
    load_mappings,
    normalize_key,
)

SESSION_PATH = Path(__file__).resolve().parents[2] / "data" / "validation_session.json"

AGENT_INSTRUCTIONS = """
Tu aides à préparer les courses Comida (workflow favoris + promos Migros).

Fichier de session : data/validation_session.json

Règles :
- Les promos de la semaine sont prises automatiquement (favori s'il est en offre, sinon meilleure promo).
- Hors promo, les produits sont résolus via les favoris Migros (Mes produits).
- Si aucun favori ni promo : l'utilisateur doit ajouter le produit sur migros.ch/fr/my-products
  puis relancer `uv run python main.py week` ou `validate.py refresh`.
- Pas de validation manuelle produit par produit.

Quand tout est résolu : uv run python validate.py summary
Puis : uv run python validate.py push
"""

MIGROS_MY_PRODUCTS_URL = "https://www.migros.ch/fr/my-products"


@dataclass
class ProductOption:
    uid: int
    name: str
    package: str | None
    price_chf: float | None
    on_promotion: bool
    score: float
    source: str
    from_cache: bool = False

    def to_dict(self, rank: int) -> dict:
        labels = []
        if self.on_promotion:
            labels.append("PROMO")
        if self.from_cache:
            labels.append("habituel")
        return {
            "rank": rank,
            "uid": self.uid,
            "name": self.name,
            "package": self.package,
            "price_chf": self.price_chf,
            "on_promotion": self.on_promotion,
            "labels": labels,
            "score": self.score,
            "source": self.source,
        }


@dataclass
class ValidationItem:
    key: str
    ingredient_raw: str
    ingredient_name: str
    quantity: str
    status: str  # pending | accepted | rejected_all | manual
    current_rank: int
    selected_uid: int | None
    options: list[ProductOption] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "ingredient_raw": self.ingredient_raw,
            "ingredient_name": self.ingredient_name,
            "quantity": self.quantity,
            "status": self.status,
            "current_rank": self.current_rank,
            "selected_uid": self.selected_uid,
            "options": [o.to_dict(i + 1) for i, o in enumerate(self.options)],
        }


def _option_from_product(
    product: dict,
    on_promotion: bool,
    score: float,
    source: str,
    from_cache: bool = False,
) -> ProductOption | None:
    uid = _product_id(product)
    if uid is None:
        return None
    offer = product.get("offer") or {}
    return ProductOption(
        uid=uid,
        name=_display_name(product),
        package=offer.get("quantity"),
        price_chf=_price_chf(product),
        on_promotion=on_promotion,
        score=score,
        source=source,
        from_cache=from_cache,
    )


def build_options_from_match(match_dict: dict, mappings: dict) -> list[ProductOption]:
    entry = get_entry(mappings, match_dict.get("ingredient_name", ""))
    rejected = set(entry.get("rejected_uids", []))
    seen: set[int] = set()
    options: list[ProductOption] = []

    def add_uid(uid: int | None, name: str, package, price, on_promo: bool, score: float, source: str, from_cache: bool = False) -> None:
        if uid is None or uid in rejected or uid in seen:
            return
        seen.add(uid)
        options.append(
            ProductOption(
                uid=uid,
                name=name,
                package=package,
                price_chf=price,
                on_promotion=on_promo,
                score=score,
                source=source,
                from_cache=from_cache,
            )
        )

    accepted_uid = entry.get("accepted_uid")
    primary_uid = match_dict.get("product_uid")

    # Cached preference first (still requires user validation in session)
    if accepted_uid and accepted_uid not in rejected:
        for alt in match_dict.get("alternatives", []):
            if alt.get("uid") == accepted_uid:
                add_uid(accepted_uid, alt["name"], None, alt.get("price_chf"), False, 0, "cache", True)
                break
        if primary_uid == accepted_uid:
            add_uid(
                accepted_uid,
                match_dict.get("name", ""),
                match_dict.get("package"),
                match_dict.get("price_chf"),
                match_dict.get("on_promotion", False),
                match_dict.get("score", 0),
                "cache",
                True,
            )

    if primary_uid:
        add_uid(
            primary_uid,
            match_dict.get("name", ""),
            match_dict.get("package"),
            match_dict.get("price_chf"),
            match_dict.get("on_promotion", False),
            match_dict.get("score", 0),
            match_dict.get("source", "search"),
        )

    for alt in match_dict.get("alternatives", []):
        add_uid(alt.get("uid"), alt.get("name", ""), None, alt.get("price_chf"), False, 0, "alternative")

    backup_uid = entry.get("backup_uid")
    if backup_uid:
        for alt in match_dict.get("alternatives", []):
            if alt.get("uid") == backup_uid:
                add_uid(backup_uid, alt["name"], None, alt.get("price_chf"), False, 0, "cache_backup", True)
                break

    return options


def build_validation_session(pipeline_result: dict, mappings_path: Path = MAPPINGS_PATH) -> dict:
    mappings = load_mappings(mappings_path)
    pending: list[dict] = []
    resolved: list[dict] = []

    for m in pipeline_result.get("matches", []):
        ingredient_name = m.get("ingredient_name") or _ingredient_name_from_raw(m["ingredient"])
        m = {**m, "ingredient_name": ingredient_name}
        options = build_options_from_match(m, mappings)
        if not options:
            continue
        key = normalize_key(ingredient_name)
        item = ValidationItem(
            key=key,
            ingredient_raw=m["ingredient"],
            ingredient_name=ingredient_name,
            quantity=m["quantity_needed"],
            status="pending",
            current_rank=1,
            selected_uid=None,
            options=options,
        )
        pending.append(item.to_dict())

    unmatched_pending = []
    for name in pipeline_result.get("unmatched", []):
        unmatched_pending.append({
            "key": normalize_key(name),
            "ingredient_name": name,
            "status": "manual",
            "hint": "uv run python validate.py search <clé> <terme>",
        })

    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "recipe": pipeline_result.get("recipe"),
        "portions": pipeline_result.get("portions"),
        "agent_instructions": AGENT_INSTRUCTIONS.strip(),
        "promotions_total": pipeline_result.get("promotions_total"),
        "promotions_from_cache": pipeline_result.get("promotions_from_cache"),
        "pantry_skipped": pipeline_result.get("pantry_skipped", []),
        "pending": pending,
        "unmatched": unmatched_pending,
        "needs_favorite": [],
        "resolved": resolved,
    }


def _ingredient_name_from_raw(raw: str) -> str:
    if raw.startswith("- "):
        parts = raw[2:].split(None, 2)
        if len(parts) >= 3:
            return parts[2]
        if len(parts) == 2:
            return parts[1]
    return raw


def save_session(session: dict, path: Path = SESSION_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(session, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def load_session(path: Path = SESSION_PATH) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Aucune session : lancez `uv run python main.py prepare <recette>`")
    return json.loads(path.read_text(encoding="utf-8"))


def _parse_basket_quantity(quantity: str | None, package: str | None = None) -> int:
    return compute_basket_quantity(quantity, package)


def find_item_by_key(session: dict, key_fragment: str) -> tuple[dict | None, str | None]:
    """Return (item, collection) where collection is pending | resolved | unmatched | needs_favorite."""
    fragment = key_fragment.lower().replace("_", "-")
    for item in session.get("pending", []):
        if _key_matches(fragment, item):
            return item, "pending"
    for item in session.get("resolved", []):
        if _key_matches(fragment, item):
            return item, "resolved"
    for item in session.get("unmatched", []):
        if _key_matches(fragment, item):
            return item, "unmatched"
    for item in session.get("needs_favorite", []):
        if _key_matches(fragment, item):
            return item, "needs_favorite"
    return None, None


def _key_matches(fragment: str, item: dict) -> bool:
    key = item.get("key", "").lower()
    name = item.get("ingredient_name", "").lower()
    return (
        fragment in key
        or fragment in name
        or key.startswith(fragment)
        or name.startswith(fragment)
    )


def find_pending_item(session: dict, key_fragment: str) -> dict | None:
    item, collection = find_item_by_key(session, key_fragment)
    if collection == "pending" and item and item.get("status") == "pending":
        return item
    return None


def reopen_item(session: dict, key_fragment: str) -> dict:
    """Move a validated ingredient back to pending (e.g. wrong product chosen)."""
    item, collection = find_item_by_key(session, key_fragment)
    if not item or collection != "resolved":
        raise ValueError(
            f"Aucun choix validé pour « {key_fragment} ». Utilisez search seulement sur pending/reopen."
        )

    from comida.mappings import record_rejection

    record_rejection(item["ingredient_name"], item["uid"])

    pending_item = {
        "key": item["key"],
        "ingredient_raw": f"- {item['ingredient_name']}",
        "ingredient_name": item["ingredient_name"],
        "quantity": item.get("quantity", "?"),
        "status": "pending",
        "current_rank": 1,
        "selected_uid": None,
        "options": [
            {
                "rank": 1,
                "uid": item["uid"],
                "name": item["name"],
                "package": None,
                "price_chf": None,
                "on_promotion": item.get("on_promotion", False),
                "labels": ["ancien choix"],
                "score": 0,
                "source": "resolved",
            }
        ],
    }
    session["resolved"] = [r for r in session.get("resolved", []) if r["key"] != item["key"]]
    session.setdefault("pending", []).append(pending_item)
    session["_last_message"] = (
        f"Rouvert : {item['ingredient_name']} (ancien : {item['name']}, uid {item['uid']}). "
        "Utilisez reject puis search pour corriger."
    )
    return session


def format_for_agent(session: dict) -> str:
    pending_n = sum(1 for p in session["pending"] if p["status"] == "pending")
    lines = [
        "# Comida — courses (favoris + promos auto)",
        "",
        f"Recette : {session.get('recipe')}",
        f"Favoris manquants : {len(session.get('needs_favorite', []))}",
        f"Promos auto : {len(session.get('promos_resolved', []))}",
        f"Via favoris : {len(session.get('favorites_resolved', []))}",
        "",
    ]

    if session.get("pantry_skipped"):
        lines.append("## Garde-manger (ignorés)")
        for raw, rule in session["pantry_skipped"]:
            lines.append(f"- {raw} → {rule}")
        lines.append("")

    if session.get("needs_favorite"):
        lines.append("## Favoris manquants (ajouter sur Migros)")
        for item in session["needs_favorite"]:
            lines.append(f"- {item['ingredient_name']} → {MIGROS_MY_PRODUCTS_URL}")
        lines.append("Puis : `uv run python validate.py refresh`")
        lines.append("")

    if pending_n:
        lines.append("## Corrections en attente")
        lines.append("")
        for item in session["pending"]:
            if item["status"] != "pending":
                continue
            lines.append(f"### {item['ingredient_name']} ({item['quantity']})")
            lines.append(f"Clé : `{item['key']}`")
            lines.append("")
            for opt in item["options"]:
                labels = " ".join(f"[{l}]" for l in opt.get("labels", []))
                promo = " **PROMO**" if opt.get("on_promotion") else ""
                current = " ← courant" if opt["rank"] == item["current_rank"] else ""
                price = opt.get("price_chf")
                price_s = f"{price} CHF" if price is not None else "prix ?"
                lines.append(
                    f"  {opt['rank']}. {opt['name']} ({opt.get('package')}) — {price_s}{promo}{labels}{current}"
                )
            lines.append("")
            lines.append("Réponses : `accept <clé> <n°>` · `reject <clé>`")
            lines.append("")

    if session.get("unmatched"):
        lines.append("## Recherche manuelle requise")
        for u in session["unmatched"]:
            if u.get("status") == "manual":
                lines.append(f"- {u['ingredient_name']} (clé `{u['key']}`)")
        lines.append("")

    if session.get("resolved"):
        lines.append("## Validés (reopen <clé> pour corriger)")
        for r in session["resolved"]:
            source = f" [{r['source']}]" if r.get("source") else ""
            lines.append(f"- {r['ingredient_name']} → {r['name']}{source} (uid {r['uid']})")
        lines.append("")

    lines.append("---")
    lines.append("Commandes : `uv run python validate.py summary|refresh|push|favorites`")
    return "\n".join(lines)


def accept_option(session: dict, key_fragment: str, rank: int) -> dict:
    item = find_pending_item(session, key_fragment)
    if not item:
        raise ValueError(f"Aucun ingrédient en attente pour « {key_fragment} »")

    option = next((o for o in item["options"] if o["rank"] == rank), None)
    if not option:
        raise ValueError(f"Option {rank} introuvable pour « {item['ingredient_name']} »")

    backup_uid = None
    for o in item["options"]:
        if o["rank"] != rank:
            backup_uid = o["uid"]
            break

    from comida.mappings import record_acceptance

    record_acceptance(item["ingredient_name"], option["uid"], backup_uid)

    item["status"] = "accepted"
    item["selected_uid"] = option["uid"]
    session["resolved"].append({
        "key": item["key"],
        "ingredient_name": item["ingredient_name"],
        "uid": option["uid"],
        "name": option["name"],
        "on_promotion": option.get("on_promotion"),
        "quantity": item.get("quantity"),
        "package": option.get("package"),
        "price_chf": option.get("price_chf"),
        "quantity_parsed": _parse_basket_quantity(item.get("quantity"), option.get("package")),
        "source": item.get("validation_reason", "promo"),
    })
    session["pending"] = [p for p in session["pending"] if p["key"] != item["key"]]
    return session


def reject_current(session: dict, key_fragment: str) -> dict:
    item = find_pending_item(session, key_fragment)
    if not item:
        raise ValueError(f"Aucun ingrédient en attente pour « {key_fragment} »")

    favorite = item.get("favorite_fallback")
    if favorite and item.get("validation_reason") == "promo":
        from comida.mappings import record_rejection

        current = next((o for o in item["options"] if o["rank"] == item["current_rank"]), None)
        if current and current.get("on_promotion"):
            record_rejection(item["ingredient_name"], current["uid"])
        session = _resolve_with_favorite(session, item, favorite, source="favorite_fallback")
        session["_last_message"] = f"Favori conservé : {favorite['name']} (uid {favorite['uid']})"
        return session

    current = next((o for o in item["options"] if o["rank"] == item["current_rank"]), None)
    if not current:
        raise ValueError("Aucune option courante")

    from comida.mappings import record_rejection

    record_rejection(item["ingredient_name"], current["uid"])

    item["options"] = [o for o in item["options"] if o["uid"] != current["uid"]]
    for i, o in enumerate(item["options"]):
        o["rank"] = i + 1

    if not item["options"]:
        favorite = item.get("favorite_fallback")
        if favorite:
            session = _resolve_with_favorite(session, item, favorite, source="favorite_fallback")
            session["_last_message"] = (
                f"Promo refusée — favori conservé : {favorite['name']} (uid {favorite['uid']})"
            )
            return session
        item["status"] = "rejected_all"
        session["unmatched"].append({
            "key": item["key"],
            "ingredient_name": item["ingredient_name"],
            "status": "manual",
            "hint": f"uv run python validate.py search {item['key']} <terme>",
        })
        session["pending"] = [p for p in session["pending"] if p["key"] != item["key"]]
        return session

    item["current_rank"] = 1
    backup = item["options"][0]
    if backup.get("labels") and "favori" in backup.get("labels", []):
        session = accept_option(session, item["key"], backup["rank"])
        session["_last_message"] = f"Promo refusée — favori conservé : {backup['name']}"
        return session
    session["_last_message"] = (
        f"Refusé : {current['name']}. "
        f"Backup : {backup['name']} (uid {backup['uid']}) — {backup.get('price_chf')} CHF"
    )
    return session


def add_search_results(session: dict, key_fragment: str, products: list[dict], promo_ids: set[int]) -> dict:
    item, collection = find_item_by_key(session, key_fragment)

    if collection == "resolved" and item:
        session = reopen_item(session, key_fragment)
        item = find_pending_item(session, key_fragment)
        if item:
            item["options"] = []

    if not item:
        for u in session.get("unmatched", []):
            if _key_matches(key_fragment.lower().replace("_", "-"), u):
                item = {
                    "key": u["key"],
                    "ingredient_raw": f"- {u['ingredient_name']}",
                    "ingredient_name": u["ingredient_name"],
                    "quantity": "?",
                    "status": "pending",
                    "current_rank": 1,
                    "selected_uid": None,
                    "options": [],
                }
                session["pending"].append(item)
                session["unmatched"] = [x for x in session["unmatched"] if x["key"] != u["key"]]
                break

    if not item:
        resolved_keys = [r["key"] for r in session.get("resolved", [])]
        pending_keys = [p["key"] for p in session.get("pending", [])]
        raise ValueError(
            f"Ingrédient introuvable : {key_fragment}. "
            f"En attente : {pending_keys}. Validés : {resolved_keys}. "
            "Pour corriger un validé : validate.py reopen <clé>"
        )

    mappings = load_mappings()
    entry = get_entry(mappings, item["ingredient_name"])
    rejected = set(entry.get("rejected_uids", []))
    existing_uids = {o["uid"] for o in item.get("options", [])}

    for product in products:
        uid = _product_id(product)
        if not uid or uid in rejected or uid in existing_uids:
            continue
        opt = _option_from_product(
            product,
            uid in promo_ids,
            0,
            "manual_search",
        )
        if opt:
            item.setdefault("options", []).append(opt.to_dict(len(existing_uids) + 1))
            existing_uids.add(uid)

    item["status"] = "pending"
    item["current_rank"] = 1
    session["_last_message"] = f"{len(item['options'])} options pour {item['ingredient_name']}"
    return session


def _resolve_with_favorite(
    session: dict,
    item: dict,
    favorite: dict,
    *,
    source: str = "favorite",
) -> dict:
    session["resolved"].append(_resolved_entry(
        item["key"],
        item["ingredient_name"],
        item.get("quantity"),
        favorite,
        source,
    ))
    session["pending"] = [p for p in session.get("pending", []) if p["key"] != item["key"]]
    return session


def _resolved_entry(
    key: str,
    ingredient_name: str,
    quantity: str | None,
    product: dict,
    source: str,
) -> dict:
    package = product.get("package")
    return {
        "key": key,
        "ingredient_name": ingredient_name,
        "uid": product["uid"],
        "name": product["name"],
        "on_promotion": product.get("on_promotion", False),
        "quantity": quantity,
        "package": package,
        "price_chf": product.get("price_chf"),
        "quantity_parsed": _parse_basket_quantity(quantity, package),
        "source": source,
    }


def apply_favorites_workflow(
    session: dict,
    favorite_products: list[dict],
    promo_ids: set[int],
) -> dict:
    """Auto-resolve promos, then favorites. Only unmatched items need a new favorite."""
    from comida.favorites import match_ingredient_to_favorite

    needs_favorite: list[dict] = []
    resolved = list(session.get("resolved", []))

    def process_ingredient(
        key: str,
        ingredient_name: str,
        quantity: str,
        pipeline_options: list[dict],
    ) -> None:
        favorite = match_ingredient_to_favorite(ingredient_name, favorite_products, promo_ids)
        promo_options = [o for o in pipeline_options if o.get("on_promotion")]

        if favorite and favorite.get("on_promotion"):
            resolved.append(_resolved_entry(key, ingredient_name, quantity, favorite, "promo_favorite"))
            return

        if promo_options:
            resolved.append(_resolved_entry(key, ingredient_name, quantity, promo_options[0], "promo"))
            return

        if favorite:
            resolved.append(_resolved_entry(key, ingredient_name, quantity, favorite, "favorite"))
            return

        needs_favorite.append({
            "key": key,
            "ingredient_name": ingredient_name,
            "quantity": quantity,
            "status": "needs_favorite",
            "hint": f"Ajoutez un produit sur {MIGROS_MY_PRODUCTS_URL} puis relancez week ou validate.py refresh",
        })

    for item in list(session.get("pending", [])):
        process_ingredient(
            item["key"],
            item["ingredient_name"],
            item.get("quantity", "?"),
            item.get("options", []),
        )

    for item in list(session.get("unmatched", [])):
        if item.get("status") != "manual":
            continue
        process_ingredient(
            item["key"],
            item["ingredient_name"],
            item.get("quantity", "?"),
            [],
        )

    session["pending"] = []
    session["needs_favorite"] = needs_favorite
    session["unmatched"] = []
    session["resolved"] = resolved
    session["favorites_resolved"] = [
        r["ingredient_name"] for r in resolved if r.get("source") == "favorite"
    ]
    session["promos_resolved"] = [
        r["ingredient_name"] for r in resolved if r.get("source") in ("promo", "promo_favorite")
    ]
    session["favorites_count"] = len(favorite_products)
    return session


def refresh_favorites_workflow(session: dict) -> dict:
    """Re-fetch favorites and re-apply workflow on current session."""
    from comida.promo_cache import fetch_promotions_cached

    favorite_products = fetch_favorites_with_details()
    promo_ids = set(fetch_promotions_cached()[0])

    # Rebuild pending from resolved favorites + needs_favorite + pending promos
    rebuilt_pending: list[dict] = []
    for item in session.get("pending", []):
        rebuilt_pending.append(item)
    for item in session.get("needs_favorite", []):
        rebuilt_pending.append({
            "key": item["key"],
            "ingredient_raw": f"- {item['ingredient_name']}",
            "ingredient_name": item["ingredient_name"],
            "quantity": item.get("quantity", "?"),
            "status": "pending",
            "current_rank": 1,
            "selected_uid": None,
            "options": [],
        })
    for item in session.get("resolved", []):
        if item.get("source") == "favorite":
            rebuilt_pending.append({
                "key": item["key"],
                "ingredient_raw": f"- {item['ingredient_name']}",
                "ingredient_name": item["ingredient_name"],
                "quantity": item.get("quantity", "?"),
                "status": "pending",
                "current_rank": 1,
                "selected_uid": None,
                "options": [],
            })

    session["pending"] = rebuilt_pending
    session["needs_favorite"] = []
    session["resolved"] = [
        r for r in session.get("resolved", []) if r.get("source") not in ("favorite", "favorite_fallback")
    ]
    return apply_favorites_workflow(session, favorite_products, promo_ids)


def auto_accept_from_mappings(session: dict, mappings_path: Path = MAPPINGS_PATH) -> dict:
    """Auto-accept known habits (mappings.json). Promos always stay manual."""
    mappings = load_mappings(mappings_path)
    auto_accepted: list[str] = []

    for item in list(session.get("pending", [])):
        if item.get("status") != "pending":
            continue
        entry = get_entry(mappings, item["ingredient_name"])
        accepted_uid = entry.get("accepted_uid")
        if not accepted_uid:
            continue
        option = next((o for o in item["options"] if o["uid"] == accepted_uid), None)
        if not option:
            continue
        if option.get("on_promotion"):
            continue
        session = accept_option(session, item["key"], option["rank"])
        auto_accepted.append(item["ingredient_name"])

    session["auto_accepted"] = auto_accepted
    return session


def validation_summary(session: dict) -> str:
    resolved = session.get("resolved", [])
    pending = [p for p in session.get("pending", []) if p["status"] == "pending"]
    needs_fav = session.get("needs_favorite", [])
    manual = [u for u in session.get("unmatched", []) if u.get("status") == "manual"]
    fav_resolved = session.get("favorites_resolved", [])
    total = len(resolved) + len(pending) + len(needs_fav) + len(manual)
    promos_resolved = session.get("promos_resolved", [])
    lines = [
        f"Validés : {len(resolved)}/{total}",
        f"Favoris manquants : {len(needs_fav)}",
    ]
    if pending:
        lines.append(f"Corrections en attente : {len(pending)}")
    if promos_resolved:
        lines.append(f"Via promos : {len(promos_resolved)}")
    if fav_resolved:
        lines.append(f"Via favoris Migros : {len(fav_resolved)}")
    if manual:
        lines.append(f"Recherche manuelle : {len(manual)}")
    if resolved:
        lines.append("")
        lines.append("Liste panier :")
        for r in resolved:
            promo = " [PROMO]" if r.get("on_promotion") else ""
            qty = r.get("quantity_parsed", 1)
            qty_s = f" × {qty}" if qty and qty > 1 else ""
            lines.append(
                f"  • {r['ingredient_name']} → {r['name']}{qty_s}{promo} (uid {r['uid']})"
            )
        budget = estimate_basket(resolved)
        lines.append("")
        lines.append(format_budget_summary(budget))
    return "\n".join(lines)


def basket_summary(session: dict) -> str:
    return format_basket_enriched(session.get("resolved", []))
