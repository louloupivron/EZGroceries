"""CLI for conversational validation (option C)."""

import os
import sys
from pathlib import Path

from comida.basket import (
    _load_dotenv,
    clear_migros_session,
    default_list_name,
    list_shopping_lists,
    migros_profile,
    push_items,
    resolved_to_basket_items,
    shared_list_url,
)
from comida.migros_client import search_products
from comida.promo_cache import fetch_promotions_cached
from comida.telegram import run_telegram_setup, run_telegram_test, send_promos_export, send_text
from comida.telegram_schedule import run_scheduled_step
from comida.validation import (
    accept_option,
    add_search_results,
    basket_summary,
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
    promo_ids = set(fetch_promotions_cached()[0])
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

    revue = [r for r in resolved if r.get("quantity_confidence") == "revue"]
    items = resolved_to_basket_items(resolved)
    if revue:
        print(f"⚠ {len(revue)} quantité(s) à confirmer, non poussées :")
        for row in revue:
            note = row.get("quantity_note") or "estimation"
            print(f"  • {row.get('ingredient_name')} × {row.get('quantity_parsed')} ({note})")
    if not items:
        print("Aucun produit poussable. Confirmez les quantités en revue ou complétez les favoris.")
        sys.exit(1)
    list_name = session.get("list_name")
    target = f"liste {list_name}" if list_name else "liste .env"
    print(f"Poussée de {len(items)} produit(s) vers Migros Online ({target})…")
    try:
        result = push_items(items, list_name=list_name)
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
        label = list_name or os.environ.get("MIGROS_SHOPPING_LIST_NAME", "Migros")
        print(
            f"Liste {label} : {checkout.get('itemCount')} ligne(s), "
            f"~{checkout.get('onlineTotal')} CHF en ligne"
        )
        print(f"Checkout : {checkout.get('checkoutUrl')}")
        slug = os.environ.get("MIGROS_LIST_SLUG", "").strip()
        if slug:
            print(f"Liste partagée : https://www.migros.ch/list/{slug}")
        print(checkout.get("message", ""))
    else:
        print(checkout.get("message", "Checkout non disponible."))

    from comida.basket import record_pushed_quantities
    from comida.validation import save_session

    record_pushed_quantities(session, result.get("results", []))
    save_session(session)

    if os.environ.get("TELEGRAM_SEND_ON_PUSH", "").strip().lower() in ("1", "true", "yes"):
        _maybe_send_push_telegram(checkout, result)

    published = _maybe_publish_page()
    if published:
        from comida.week_page import publish_hint

        print(f"Page mobile générée : {published}")
        print(f"  Poussez sur GitHub : {publish_hint()}")


def _maybe_send_push_telegram(checkout: dict, result: dict) -> None:
    lines = ["🛒 Panier Migros poussé"]
    if checkout.get("ok"):
        lines.append(f"Articles : {checkout.get('itemCount', '?')}")
        lines.append(f"Total : ~{checkout.get('onlineTotal', '?')} CHF")
        if checkout.get("checkoutUrl"):
            lines.append(f"Checkout : {checkout['checkoutUrl']}")
    slug = shared_list_url()
    if slug:
        lines.append(f"Liste : {slug}")
    try:
        from comida.telegram import TelegramConfig, send_message

        send_message("\n".join(lines), config=TelegramConfig.from_env())
        print("✓ Résumé envoyé sur Telegram")
    except RuntimeError as e:
        print(f"⚠ Telegram : {e}")


def _print_migros_account() -> None:
    try:
        profile = migros_profile()
    except RuntimeError as e:
        print(f"Compte Migros : erreur ({e})")
        return
    name = f"{profile.get('firstName', '')} {profile.get('lastName', '')}".strip()
    email = profile.get("email", "?")
    print(f"Compte Migros connecté : {name} <{email}>")
    env_email = os.environ.get("MIGROS_EMAIL", "").strip().lower()
    if env_email and email.lower() != env_email:
        print(
            f"⚠  MIGROS_EMAIL={env_email} mais la session en cache est {email}. "
            "Lancez : uv run python validate.py logout"
        )


def cmd_lists() -> None:
    _load_dotenv()
    _print_migros_account()
    print()
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
    print(f"  MIGROS_SHOPPING_LIST_NAME={default_list_name()}")
    print("  ou MIGROS_SHOPPING_LIST_ID=<id>")
    slug = os.environ.get("MIGROS_LIST_SLUG", "").strip()
    if slug:
        print(f"Lien partagé : https://www.migros.ch/list/{slug} (slug ≠ shoppingListId)")
    else:
        print("Lien partagé /list/<slug> : définir MIGROS_LIST_SLUG dans .env")


def cmd_logout() -> None:
    _load_dotenv()
    try:
        result = clear_migros_session()
    except RuntimeError as e:
        print(f"Erreur : {e}")
        sys.exit(1)
    print(result.get("message", "Session Migros supprimée."))


def cmd_reopen(args: list[str]) -> None:
    if not args:
        print("Usage: validate.py reopen <clé>")
        sys.exit(1)
    session = load_session()
    session = reopen_item(session, args[0])
    save_session(session)
    print(session.get("_last_message", "Rouvert."))


def cmd_basket() -> None:
    session = load_session()
    print(basket_summary(session))


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


def cmd_telegram_setup() -> None:
    run_telegram_setup()


def cmd_telegram_test() -> None:
    try:
        run_telegram_test()
    except RuntimeError as e:
        print(f"Erreur : {e}")
        sys.exit(1)


def cmd_telegram_schedule(args: list[str]) -> None:
    force = "--force" in args
    rest = [a for a in args if a != "--force"]
    step = rest[0] if rest else None
    try:
        result = run_scheduled_step(step, force=force)
    except (RuntimeError, ValueError) as e:
        print(f"Erreur : {e}")
        sys.exit(1)
    if result.get("skipped"):
        print(f"Ignoré : {result.get('reason', 'déjà envoyé')}")
    else:
        print("✓ Message Telegram envoyé")


def cmd_send(args: list[str]) -> None:
    if not args:
        print("Usage: validate.py send <fichier.txt> [--title \"Titre\"]")
        sys.exit(1)
    path = Path(args[0])
    if not path.exists():
        print(f"Fichier introuvable : {path}")
        sys.exit(1)
    title = None
    if "--title" in args:
        idx = args.index("--title")
        if idx + 1 < len(args):
            title = args[idx + 1]
    try:
        if path.name.startswith("promos-"):
            list_name = path.stem.replace("promos-", "").upper()
            send_promos_export(path, list_name)
        else:
            send_text(path, title=title)
        print(f"✓ Envoyé sur Telegram : {path}")
    except RuntimeError as e:
        print(f"Erreur : {e}")
        sys.exit(1)


def cmd_ui_link() -> None:
    from comida.telegram import send_ui_access_link
    from comida.ui.access import print_access_urls
    from comida.ui.server import ui_port

    port = ui_port()
    try:
        session = load_session()
        recipe = Path(session.get("recipe", "")).stem or None
    except FileNotFoundError:
        recipe = None
    try:
        if send_ui_access_link(port, recipe=recipe):
            print("✓ Lien mobile envoyé sur Telegram")
        else:
            print("Non envoyé (TELEGRAM_SEND_UI_LINK=false ou Telegram non configuré)")
    except RuntimeError as e:
        print(f"Erreur : {e}")
        sys.exit(1)
    print_access_urls(port)


def cmd_publish() -> None:
    from comida.week_page import generate_week_page, publish_hint

    try:
        load_session()
    except FileNotFoundError:
        print("Aucune session. Lancez : uv run python main.py week exports/semaine.txt")
        sys.exit(1)
    path = generate_week_page()
    url = publish_hint()
    print(f"Page générée : {path}")
    print(f"URL mobile : {url}")
    print()
    print("Pour mettre en ligne :")
    print("  git add docs/index.html docs/.nojekyll")
    print("  git commit -m 'publish: semaine'")
    print("  git push")
    print()
    print("GitHub → Settings → Pages → Source : main, dossier /docs")


def _maybe_publish_page() -> Path | None:
    if os.environ.get("COMIDA_PUBLISH_ON_PUSH", "").strip().lower() not in ("1", "true", "yes"):
        return None
    try:
        from comida.week_page import generate_week_page

        return generate_week_page()
    except FileNotFoundError:
        return None


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
        print(
            "Usage: validate.py show|accept|reject|search|reopen|summary|basket|push|"
            "publish|ui-link|send|lists|logout|favorites|refresh|"
            "telegram-setup|telegram-test|telegram-schedule"
        )
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
    elif cmd == "basket":
        cmd_basket()
    elif cmd == "push":
        cmd_push(args)
    elif cmd == "publish":
        cmd_publish()
    elif cmd == "ui-link":
        cmd_ui_link()
    elif cmd == "lists":
        cmd_lists()
    elif cmd == "logout":
        cmd_logout()
    elif cmd == "favorites":
        cmd_favorites()
    elif cmd == "refresh":
        cmd_refresh()
    elif cmd == "telegram-setup":
        cmd_telegram_setup()
    elif cmd == "telegram-test":
        cmd_telegram_test()
    elif cmd == "telegram-schedule":
        cmd_telegram_schedule(args)
    elif cmd == "send":
        cmd_send(args)
    else:
        print(f"Commande inconnue : {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()
