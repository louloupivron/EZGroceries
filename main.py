"""CLI entrypoint for Comida promo-first + validation session."""

import sys
from pathlib import Path

from comida.pipeline import run_promo_first
from comida.quantities import DEFAULT_PORTIONS
from comida.validation import build_validation_session, format_for_agent, save_session

ROOT = Path(__file__).resolve().parent


def _parse_common_flags(args: list[str]) -> tuple[list[str], dict]:
    """Extract shared flags; return (remaining args, options dict)."""
    rest: list[str] = []
    options = {
        "open_ui": True,
        "port": 8765,
        "portions": DEFAULT_PORTIONS,
        "base_portions": DEFAULT_PORTIONS,
        "refresh_promos": False,
        "apply_pantry": False,
        "list_name": "S1",
        "output": None,
    }
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--no-ui":
            options["open_ui"] = False
        elif arg == "--refresh-promos":
            options["refresh_promos"] = True
        elif arg == "--pantry":
            options["apply_pantry"] = True
        elif arg == "--port" and i + 1 < len(args):
            options["port"] = int(args[i + 1])
            i += 1
        elif arg == "--portions" and i + 1 < len(args):
            options["portions"] = int(args[i + 1])
            i += 1
        elif arg == "--base-portions" and i + 1 < len(args):
            options["base_portions"] = int(args[i + 1])
            i += 1
        elif arg == "--list" and i + 1 < len(args):
            options["list_name"] = args[i + 1]
            i += 1
        elif arg in ("-o", "--output") and i + 1 < len(args):
            options["output"] = Path(args[i + 1])
            i += 1
        elif not arg.startswith("-"):
            rest.append(arg)
        i += 1
    return rest, options


def cmd_prepare(recipe: Path, *, portions: int = DEFAULT_PORTIONS, refresh_promos: bool = False) -> None:
    from comida.favorites import fetch_favorites_with_details
    from comida.promo_cache import fetch_promotions_cached
    from comida.validation import apply_favorites_workflow

    pantry = ROOT / "garde-manger.txt"
    print("Analyse Migros en cours (promos + matching)…")
    result = run_promo_first(
        recipe,
        pantry,
        portions=portions,
        refresh_promos=refresh_promos,
    )
    session = build_validation_session(result)
    print("Chargement des favoris Migros…")
    favorite_products = fetch_favorites_with_details()
    promo_ids_list, _, _ = fetch_promotions_cached(force_refresh=refresh_promos)
    session = apply_favorites_workflow(session, favorite_products, set(promo_ids_list))
    path = save_session(session)
    print(f"Session créée : {path}")
    print()
    print(format_for_agent(session))


def cmd_week(args: list[str]) -> None:
    from comida.week import run_week

    rest, options = _parse_common_flags(args)
    paths = [Path(p) for p in rest]
    run_week(
        paths or None,
        open_ui=options["open_ui"],
        port=options["port"],
        portions=options["portions"],
        base_portions=options["base_portions"],
        refresh_promos=options["refresh_promos"],
    )


def cmd_ui(args: list[str]) -> None:
    from comida.week import run_ui

    _, options = _parse_common_flags(args)
    run_ui(port=options["port"])


def cmd_promos(args: list[str]) -> None:
    from comida.kookd_export import run_promos_export

    rest, options = _parse_common_flags(args)
    list_name = options["list_name"]
    if rest and not rest[0].startswith("-"):
        list_name = rest[0]

    try:
        run_promos_export(
            list_name,
            output=options["output"],
            apply_pantry=options["apply_pantry"],
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
        rest, options = _parse_common_flags(rest)
        recipe = Path(rest[0]) if rest else ROOT / "examples" / "sushi_bowl.txt"
        cmd_prepare(
            recipe,
            portions=options["portions"],
            refresh_promos=options["refresh_promos"],
        )
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
