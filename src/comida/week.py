"""Unified weekly workflow: promo + favorites auto-resolve, optional UI."""

from __future__ import annotations

import webbrowser
from pathlib import Path

from comida.pipeline import run_promo_first, run_promo_first_multi
from comida.ui.server import serve
from comida.favorites import fetch_favorites_with_details
from comida.migros_client import fetch_all_promotion_ids
from comida.validation import (
    apply_favorites_workflow,
    build_validation_session,
    load_session,
    save_session,
    validation_summary,
)

ROOT = Path(__file__).resolve().parents[2]


def resolve_recipe_paths(paths: list[Path]) -> list[Path]:
    if paths:
        resolved = []
        for p in paths:
            if not p.exists():
                raise FileNotFoundError(f"Fichier introuvable : {p}")
            resolved.append(p.resolve())
        return resolved

    exports = ROOT / "exports"
    if exports.is_dir():
        files = sorted(exports.glob("*.txt"))
        if files:
            return files

    return [ROOT / "examples" / "sushi_bowl.txt"]


def run_week(
    recipe_paths: list[Path] | None = None,
    *,
    pantry_path: Path | None = None,
    open_ui: bool = True,
    port: int = 8765,
) -> dict:
    pantry = pantry_path or (ROOT / "garde-manger.txt")
    paths = resolve_recipe_paths(recipe_paths or [])

    print("Analyse Migros en cours (promos + favoris)…")
    if len(paths) == 1:
        result = run_promo_first(paths[0], pantry)
    else:
        print(f"  {len(paths)} export(s) Kookd fusionnés")
        result = run_promo_first_multi(paths, pantry)

    print("Chargement des favoris Migros…")
    favorite_products = fetch_favorites_with_details()
    promo_ids = set(fetch_all_promotion_ids())

    session = build_validation_session(result)
    session = apply_favorites_workflow(session, favorite_products, promo_ids)
    path = save_session(session)

    fav_resolved = session.get("favorites_resolved", [])
    promo_resolved = session.get("promos_resolved", [])
    needs_fav = session.get("needs_favorite", [])
    pending = sum(1 for p in session["pending"] if p["status"] == "pending")

    print(f"Session créée : {path}")
    print(f"  {session.get('favorites_count', 0)} favori(s) Migros chargé(s)")
    if promo_resolved:
        print(f"✓ {len(promo_resolved)} via promos : {', '.join(promo_resolved)}")
    if fav_resolved:
        print(f"✓ {len(fav_resolved)} via favoris : {', '.join(fav_resolved)}")
    if needs_fav:
        print(f"⚠ {len(needs_fav)} favori(s) manquant(s) : {', '.join(i['ingredient_name'] for i in needs_fav)}")
        print("  → Ajoutez-les sur https://www.migros.ch/fr/my-products puis validate.py refresh")
    if pending:
        print(f"→ {pending} correction(s) en attente")
    elif not needs_fav:
        print("→ Tout est résolu — prêt pour le push Migros")
    print()
    print(validation_summary(session))

    if open_ui and (pending or needs_fav or session.get("resolved")):
        url = f"http://127.0.0.1:{port}"
        print(f"\nInterface : {url}")
        webbrowser.open(url)
        serve(port=port, open_browser=False)

    return session


def run_ui(port: int = 8765) -> None:
    session = load_session()
    pending = sum(1 for p in session["pending"] if p["status"] == "pending")
    print(f"Session : {session.get('recipe')}")
    print(f"  {pending} en attente, {len(session.get('resolved', []))} validé(s)")
    url = f"http://127.0.0.1:{port}"
    print(f"\nInterface : {url}")
    webbrowser.open(url)
    serve(port=port, open_browser=False)
