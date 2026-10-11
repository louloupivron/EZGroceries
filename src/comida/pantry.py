"""Filter ingredients covered by the household pantry list."""

import re
from dataclasses import dataclass
from pathlib import Path

from rapidfuzz import fuzz

from comida.parser import Ingredient
from comida.quantities import Amount, format_amount, parse_amount_text, subtract_amounts


@dataclass(frozen=True)
class PantryStock:
    name: str
    quantity: float | None = None
    unit: str | None = None

    @property
    def unlimited(self) -> bool:
        return self.quantity is None

    def as_amount(self) -> Amount | None:
        if self.unlimited or self.unit is None:
            return None
        return Amount(self.quantity, self.unit)


def _parse_pantry_line(line: str) -> tuple[str, float | None, str | None]:
    """
    Parse pantry lines:
      riz 2 kg
      500 g farine
      huile en tout genre
    """
    text = line.strip()
    leading_qty = re.match(
        r"^(?P<qty>\d+(?:[.,]\d+)?)\s+(?P<unit>[a-zàâäéèêëïîôùûüç.]+)\s+(?P<name>.+)$",
        text,
        re.IGNORECASE,
    )
    if leading_qty:
        return (
            leading_qty.group("name").strip().lower(),
            float(leading_qty.group("qty").replace(",", ".")),
            leading_qty.group("unit").strip().lower(),
        )

    trailing_qty = re.match(
        r"^(?P<name>.+?)\s+(?P<qty>\d+(?:[.,]\d+)?)\s*(?P<unit>[a-zàâäéèêëïîôùûüç.]+)$",
        text,
        re.IGNORECASE,
    )
    if trailing_qty:
        return (
            trailing_qty.group("name").strip().lower(),
            float(trailing_qty.group("qty").replace(",", ".")),
            trailing_qty.group("unit").strip().lower(),
        )

    return text.lower(), None, None


def load_pantry(path: Path) -> tuple[list[PantryStock], list[PantryStock]]:
    pantry: list[PantryStock] = []
    always_buy: list[PantryStock] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("+"):
            name, qty, unit = _parse_pantry_line(line[1:].strip())
            always_buy.append(PantryStock(name, qty, unit))
        else:
            name, qty, unit = _parse_pantry_line(line)
            pantry.append(PantryStock(name, qty, unit))
    return pantry, always_buy


def _word_match(pantry_term: str, ingredient_name: str) -> bool:
    """Avoid false positives like nori ↔ riz, thon ↔ jus, chou-fleur ↔ levure."""
    if len(pantry_term) <= 4:
        return bool(re.search(rf"\b{re.escape(pantry_term)}\b", ingredient_name))
    if pantry_term in ingredient_name or ingredient_name in pantry_term:
        return True
    # Require a shared token of 5+ chars — partial_ratio alone is too loose.
    ing_tokens = {t for t in re.findall(r"[a-zàâäéèêëïîôùûüç]+", ingredient_name) if len(t) >= 5}
    for token in re.findall(r"[a-zàâäéèêëïîôùûüç]+", pantry_term):
        if len(token) >= 5 and token in ing_tokens:
            return True
    return False


def _pantry_keywords(item: str) -> list[str]:
    parts = re.split(r"\s+et\s+|/|\s+de\s+", item)
    keywords: list[str] = []
    for part in parts:
        words = part.strip().split()
        if words:
            keywords.append(words[0])
    return keywords


def is_always_buy(ingredient_name: str, always_buy: list[PantryStock], threshold: int = 80) -> PantryStock | None:
    name = ingredient_name.lower()
    for rule in always_buy:
        if rule.name in name or name in rule.name:
            return rule
        if fuzz.partial_ratio(rule.name, name) >= threshold:
            return rule
    return None


def _match_specificity(
    item: PantryStock,
    ingredient_name: str,
    threshold: int,
) -> tuple[int, int] | None:
    """Higher tuple wins. A broad « et » / « / » line loses to a more precise stock line."""
    name = ingredient_name.lower()
    pantry_name = item.name.lower()
    tokens = [t for t in re.findall(r"[a-zàâäéèêëïîôùûüç]+", pantry_name) if len(t) >= 3]
    if "en tout genre" in pantry_name:
        if tokens and tokens[0] in name:
            return (1, len(pantry_name))
        return None
    broad = bool(re.search(r"\s+et\s+|/", pantry_name))
    if len(tokens) >= 2:
        matched = [t for t in tokens if t in name]
        if len(matched) == len(tokens):
            return (80 + len(tokens), len(pantry_name))
        if broad and matched:
            return (10 + len(matched), len(pantry_name))
        return None
    for keyword in _pantry_keywords(item.name):
        if _word_match(keyword, name):
            return (50, len(pantry_name))
    if len(item.name) > 4 and fuzz.token_set_ratio(item.name, name) >= threshold:
        return (5, int(fuzz.token_set_ratio(item.name, name)))
    return None


def find_pantry_match(
    ingredient_name: str,
    pantry: list[PantryStock],
    threshold: int = 72,
) -> PantryStock | None:
    best: PantryStock | None = None
    best_score: tuple[int, int] | None = None
    for item in pantry:
        score = _match_specificity(item, ingredient_name, threshold)
        if score is None:
            continue
        if best_score is None or score > best_score:
            best = item
            best_score = score
    return best


def apply_pantry_stock(
    ingredient: Ingredient,
    stock: PantryStock,
) -> tuple[Ingredient | None, str]:
    """
    Return (ingredient_to_buy, pantry_rule_label).
    None ingredient means fully covered by pantry.
    """
    if stock.unlimited:
        return None, stock.name

    needed = parse_amount_text(f"{ingredient.quantity:g} {ingredient.unit}")
    pantry_amount = stock.as_amount()
    if needed is None or pantry_amount is None:
        return None, f"{stock.name} (stock illimité)"

    remaining = subtract_amounts(needed, pantry_amount)
    if remaining is None:
        return None, f"{stock.name} ({format_amount(pantry_amount)} en stock)"

    qty_str = f"{remaining.value:g}"
    updated = Ingredient(
        quantity=remaining.value,
        unit=remaining.unit if remaining.unit != "piece" else ingredient.unit,
        name=ingredient.name,
        raw=f"- {qty_str} {ingredient.unit} {ingredient.name}",
    )
    return updated, f"{stock.name} (reste {format_amount(remaining)} à acheter)"


def filter_pantry(
    ingredients: list[Ingredient], pantry_path: Path
) -> tuple[list[Ingredient], list[tuple[Ingredient, str]]]:
    pantry, always_buy = load_pantry(pantry_path)
    kept: list[Ingredient] = []
    skipped: list[tuple[Ingredient, str]] = []

    for ing in ingredients:
        always_rule = is_always_buy(ing.name, always_buy)
        if always_rule:
            if always_rule.unlimited:
                kept.append(ing)
                continue
            needed = parse_amount_text(f"{ing.quantity:g} {ing.unit}")
            pantry_amount = always_rule.as_amount()
            if needed and pantry_amount:
                remaining = subtract_amounts(needed, pantry_amount)
                if remaining is None:
                    skipped.append((ing, f"+ {always_rule.name} (stock suffisant)"))
                    continue
                qty_str = f"{remaining.value:g}"
                kept.append(
                    Ingredient(
                        quantity=remaining.value,
                        unit=remaining.unit if remaining.unit != "piece" else ing.unit,
                        name=ing.name,
                        raw=f"- {qty_str} {ing.unit} {ing.name}",
                    )
                )
                continue
            kept.append(ing)
            continue

        stock = find_pantry_match(ing.name, pantry)
        if not stock:
            kept.append(ing)
            continue

        to_buy, label = apply_pantry_stock(ing, stock)
        if to_buy is None:
            skipped.append((ing, label))
        else:
            kept.append(to_buy)

    return kept, skipped
