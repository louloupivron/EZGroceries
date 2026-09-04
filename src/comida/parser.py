"""Parse Kookd text export lines into structured ingredients."""

import re
from dataclasses import dataclass, replace

from comida.quantities import DEFAULT_PORTIONS

LINE_RE = re.compile(
    r"^-\s*"
    r"(?P<quantity>(?:\d+(?:[.,]\d+)?))\s+"
    r"(?P<unit>[a-zàâäéèêëïîôùûüç.]+)\s+"
    r"(?P<name>.+)$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Ingredient:
    quantity: float
    unit: str
    name: str
    raw: str


def parse_kookd_export(text: str) -> list[Ingredient]:
    ingredients: list[Ingredient] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or not line.startswith("-"):
            continue
        match = LINE_RE.match(line)
        if not match:
            continue
        qty = float(match.group("quantity").replace(",", "."))
        ingredients.append(
            Ingredient(
                quantity=qty,
                unit=match.group("unit").strip(),
                name=match.group("name").strip(),
                raw=line,
            )
        )
    return ingredients


def merge_ingredients(ingredients: list[Ingredient]) -> list[Ingredient]:
    """Combine duplicate ingredient names (sum quantities when units match)."""
    from collections import defaultdict

    groups: dict[str, list[Ingredient]] = defaultdict(list)
    for ing in ingredients:
        groups[ing.name.lower().strip()].append(ing)

    merged: list[Ingredient] = []
    for group in groups.values():
        if len(group) == 1:
            merged.append(group[0])
            continue
        units = {g.unit.lower() for g in group}
        if len(units) == 1:
            total_qty = sum(g.quantity for g in group)
            first = group[0]
            merged.append(
                Ingredient(
                    quantity=total_qty,
                    unit=first.unit,
                    name=first.name,
                    raw=f"- {total_qty:g} {first.unit} {first.name}",
                )
            )
        else:
            merged.extend(group)
    return merged


def scale_ingredients(
    ingredients: list[Ingredient],
    *,
    base_portions: int = DEFAULT_PORTIONS,
    target_portions: int = DEFAULT_PORTIONS,
) -> list[Ingredient]:
    """Scale recipe quantities from Kookd base portions to target portions."""
    if base_portions <= 0 or target_portions <= 0:
        raise ValueError("Les portions doivent être > 0")
    if base_portions == target_portions:
        return ingredients

    factor = target_portions / base_portions
    scaled: list[Ingredient] = []
    for ing in ingredients:
        new_qty = ing.quantity * factor
        qty_str = f"{new_qty:g}"
        scaled.append(
            replace(
                ing,
                quantity=new_qty,
                raw=f"- {qty_str} {ing.unit} {ing.name}",
            )
        )
    return scaled
