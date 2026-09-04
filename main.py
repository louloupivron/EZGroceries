"""CLI entrypoint for Comida promo-first + validation session."""

import sys
from pathlib import Path

from comida.pipeline import run_promo_first
from comida.validation import build_validation_session, format_for_agent, save_session

ROOT = Path(__file__).resolve().parent


def cmd_prepare(recipe: Path) -> None:
    from comida.favorites import fetch_favorites_with_details
    from comida.migros_client import fetch_all_promotion_ids
    from comida.validation import apply_favorites_workflow

    pantry = ROOT / "garde-manger.txt"
    print("Analyse Migros en cours (promos + matching)…")
    result = run_promo_first(recipe, pantry)
    session = build_validation_session(result)
    print("Chargement des favoris Migros…")
    favorite_products = fetch_favorites_with_details()
    promo_ids = set(fetch_all_promotion_ids())
    session = apply_favorites_workflow(session, favorite_products, promo_ids)
    path = save_session(session)
    print(f"Session créée : {path}")
    print()
    print(format_for_agent(session))


def cmd_week(args: list[str]) -> None:
    from comida.week import run_week

    paths: list[Path] = []
    open_ui = True
    port = 8765
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--no-ui":
            open_ui = False
        elif arg == "--port" and i + 1 < len(args):
            port = int(args[i + 1])
            i += 1
        elif not arg.startswith("-"):
            paths.append(Path(arg))
        i += 1

    run_week(paths or None, open_ui=open_ui, port=port)


def cmd_ui(args: list[str]) -> None:
    from comida.week import run_ui

    port = 8765
    if "--port" in args:
        port = int(args[args.index("--port") + 1])
    run_ui(port=port)


def cmd_promos(args: list[str]) -> None:
    from comida.kookd_export import run_promos_export

    list_name = "S1"
    apply_pantry = "--pantry" in args
    args = [a for a in args if a != "--pantry"]
    output: Path | None = None
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--list" and i + 1 < len(args):
            list_name = args[i + 1]
            i += 2
            continue
        if arg in ("-o", "--output") and i + 1 < len(args):
            output = Path(args[i + 1])
            i += 2
            continue
        if not arg.startswith("-"):
            list_name = arg
        i += 1

    try:
        run_promos_export(
            list_name,
            output=output,
            apply_pantry=apply_pantry,
        )
    except RuntimeError as e:
        print(f"Erreur : {e}")
        sys.exit(1)


def main() -> None:
    args = sys.argv[1:]
    if not args:
        print("Usage: main.py prepare|week|ui|promos [options]")
        sys.exit(1)

    cmd = args[0]
    rest = args[1:]

    if cmd == "prepare":
        recipe = Path(rest[0]) if rest else ROOT / "examples" / "sushi_bowl.txt"
        cmd_prepare(recipe)
        return

    if cmd == "week":
        cmd_week(rest)
        return

    if cmd == "ui":
        cmd_ui(rest)
        return

    if cmd == "promos":
        cmd_promos(rest)
        return

    if cmd == "show":
        from comida.validation import load_session

        session = load_session()
        print(format_for_agent(session))
        return

    # Legacy: main.py <recipe.txt>
    cmd_prepare(Path(cmd))


if __name__ == "__main__":
    main()
