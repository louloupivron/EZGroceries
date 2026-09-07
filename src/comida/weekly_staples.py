"""Weekly staples added to every shopping run (outside Kookd exports)."""

from __future__ import annotations

from pathlib import Path

from comida.pantry import _parse_pantry_line
from comida.parser import Ingredient, merge_ingredients

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PATH = ROOT / "courses-hebdo.txt"


def load_weekly_staples(path: Path | None = None) -> list[Ingredient]:
    """Parse courses-hebdo.txt into ingredients (1 pièce if no quantity)."""
    file_path = path or DEFAULT_PATH
    if not file_path.exists():
        return []

    staples: list[Ingredient] = []
    for line in file_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, qty, unit = _parse_pantry_line(line)
        if qty is None:
            qty, unit = 1.0, "pièce"
        raw = f"- {qty:g} {unit} {name}"
        staples.append(Ingredient(quantity=qty, unit=unit, name=name, raw=raw))
    return staples


def merge_with_weekly_staples(
    recipe_items: list[Ingredient],
    staples: list[Ingredient],
) -> tuple[list[Ingredient], list[str]]:
    """
    Append weekly staples to the recipe shopping list (staples bypass pantry).
    Returns (combined list, staple ingredient names added or merged).
    """
    if not staples:
        return recipe_items, []

    recipe_names = {item.name.lower().strip() for item in recipe_items}
    added_names: list[str] = []
    for staple in staples:
        key = staple.name.lower().strip()
        if key not in recipe_names:
            added_names.append(staple.name)
        elif staple.name not in added_names:
            added_names.append(staple.name)

    combined = merge_ingredients(recipe_items + staples)
    return combined, added_names
