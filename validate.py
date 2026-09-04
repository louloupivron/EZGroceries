"""CLI for conversational validation (option C)."""

import os
import sys
from pathlib import Path

from comida.basket import _load_dotenv, list_shopping_lists, push_items, resolved_to_basket_items
from comida.migros_client import fetch_all_promotion_ids, search_products
from comida.validation import (
    accept_option,
    add_search_results,
    format_for_agent,
    load_session,
    reopen_item,
    save_session,
    validation_summary,
    reject_current,
    refresh_favorites_workflow,
    SESSION_PATH,
)
from comida.favorites import fetch_favorites_with_details, format_favorites_list

ROOT = Path(__file__).resolve().parent


def cmd_show() -> None:
    session = load_session()
    print(format_for_agent(session))
    if session.get("_last_message"):
        print(session["_last_message"])


def cmd_accept(args: list[str]) -> None:
    if len(args) < 2:
        print("Usage: validate.py accept <clé> <n°>")
        sys.exit(1)
    session = load_session()
    session = accept_option(session, args[0], int(args[1]))
    save_session(session)
    print(f"✓ Accepté : {args[0]} option {args[1]}")
    print(validation_summary(session))


def cmd_reject(args: list[str]) -> None:
    if not args:
        print("Usage: validate.py reject <clé>")
        sys.exit(1)
    session = load_session()
    session = reject_current(session, args[0])
    save_session(session)
    print(session.get("_last_message", "Refus enregistré."))
    print(validation_summary(session))


def cmd_search(args: list[str]) -> None:
    if len(args) < 2:
        print("Usage: validate.py search <clé> <terme de recherche>")
        sys.exit(1)
    key, query = args[0], " ".join(args[1:])
    session = load_session()
    products = search_products(query, size=8)
    promo_ids = set(fetch_all_promotion_ids())
    session = add_search_results(session, key, products, promo_ids)
    save_session(session)
    print(session.get("_last_message", "Recherche terminée."))
    item = next(
        (p for p in session["pending"] if args[0].lower() in p["key"] or args[0].lower() in p["ingredient_name"].lower()),
        None,
    )
    if item:
        for opt in item["options"]:
            print(f"  {opt['rank']}. {opt['name']} — {opt.get('price_chf')} CHF")


def cmd_push(args: list[str]) -> None:
    _load_dotenv()
    force = "--force" in args
    args = [a for a in args if a != "--force"]
    session = load_session()
    pending = [p for p in session.get("pending", []) if p.get("status") == "pending"]
    manual = [u for u in session.get("unmatched", []) if u.get("status") == "manual"]
    needs_fav = session.get("needs_favorite", [])
    resolved = session.get("resolved", [])

    if not resolved:
        print("Aucun produit résolu. Complétez les favoris puis : validate.py refresh")
        sys.exit(1)

    if (pending or manual or needs_fav) and not force:
        print(f"⚠ {len(needs_fav)} favori(s) manquant(s), {len(pending)} correction(s), {len(manual)} manuel(s).")
        if needs_fav:
            print("  Ajoutez les favoris sur https://www.migros.ch/fr/my-products puis : validate.py refresh")
        print("Complétez ou relancez avec : validate.py push --force")
        sys.exit(1)

    items = resolved_to_basket_items(resolved)
    print(f"Poussée de {len(items)} produit(s) vers Migros Online…")
    try:
        result = push_items(items)
    except RuntimeError as e:
        print(f"Erreur : {e}")
        print("Configurez .env (voir .env.example) puis : uv run python validate.py lists")
        sys.exit(1)

    for r in result.get("results", []):
        status = "✓" if r.get("ok") else "✗"
        label = r.get("ingredient") or r.get("productId")
        if r.get("ok"):
            print(f"  {status} {label} (uid {r['productId']}, qty {r['quantity']})")
        else:
            print(f"  {status} {label}: {r.get('error')}")

    checkout = result.get("checkout", {})
    list_id = result.get("shoppingListId")
    if list_id:
        print(f"Liste cible (shoppingListId) : {list_id}")
    if checkout.get("ok"):
        print()
        print(f"Panier : {checkout.get('itemCount')} article(s), ~{checkout.get('onlineTotal')} CHF")
        print(f"Checkout : {checkout.get('checkoutUrl')}")
        slug = os.environ.get("MIGROS_LIST_SLUG", "4SOsOT53")
        if slug:
            print(f"Liste partagée : https://www.migros.ch/list/{slug}")
        print(checkout.get("message", ""))
    else:
        print(checkout.get("message", "Checkout non disponible."))


def cmd_lists() -> None:
    _load_dotenv()
    try:
        lists = list_shopping_lists()
    except RuntimeError as e:
        print(f"Erreur : {e}")
        sys.exit(1)
    print("Listes Migros (shoppingListId pour .env) :")
    for lst in lists:
        marker = ""
        name = lst.get("shoppingListName") or lst.get("name", "")
        items = lst.get("itemsCount", lst.get("itemCount", "?"))
        env_name = os.environ.get("MIGROS_SHOPPING_LIST_NAME", "")
        env_id = os.environ.get("MIGROS_SHOPPING_LIST_ID", "")
        if env_id and str(lst.get("shoppingListId")) == env_id:
            marker = "  ← cible (.env ID)"
        elif env_name and env_name.lower() in name.lower():
            marker = "  ← cible (.env NAME)"
        print(
            f"  id={lst.get('shoppingListId')}  name={name}  "
            f"items={items}{marker}"
        )
    print()
    print("Ajoutez dans .env :")
    print("  MIGROS_SHOPPING_LIST_NAME=Les Avengers")
    print("  ou MIGROS_SHOPPING_LIST_ID=<id>")
    print("Lien partagé /list/4SOsOT53 utilise un slug public, pas cet id numérique.")


def cmd_reopen(args: list[str]) -> None:
    if not args:
        print("Usage: validate.py reopen <clé>")
        sys.exit(1)
    session = load_session()
    session = reopen_item(session, args[0])
    save_session(session)
    print(session.get("_last_message", "Rouvert."))


def cmd_summary() -> None:
    session = load_session()
    print(validation_summary(session))


def cmd_favorites() -> None:
    try:
        products = fetch_favorites_with_details()
    except RuntimeError as e:
        print(f"Erreur : {e}")
        sys.exit(1)
    print(format_favorites_list(products))


def cmd_refresh() -> None:
    try:
        session = load_session()
    except FileNotFoundError as e:
        print(e)
        sys.exit(1)
    try:
        session = refresh_favorites_workflow(session)
    except RuntimeError as e:
        print(f"Erreur : {e}")
        sys.exit(1)
    save_session(session)
    print("Favoris rechargés.")
    print(validation_summary(session))


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: validate.py show|accept|reject|search|reopen|summary|push|lists|favorites|refresh")
        sys.exit(1)
    cmd = sys.argv[1]
    args = sys.argv[2:]
    if cmd == "show":
        cmd_show()
    elif cmd == "accept":
        cmd_accept(args)
    elif cmd == "reject":
        cmd_reject(args)
    elif cmd == "search":
        cmd_search(args)
    elif cmd == "reopen":
        cmd_reopen(args)
    elif cmd == "summary":
        cmd_summary()
    elif cmd == "push":
        cmd_push(args)
    elif cmd == "lists":
        cmd_lists()
    elif cmd == "favorites":
        cmd_favorites()
    elif cmd == "refresh":
        cmd_refresh()
    else:
        print(f"Commande inconnue : {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()
