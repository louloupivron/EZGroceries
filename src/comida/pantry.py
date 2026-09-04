"""Filter ingredients covered by the household pantry list."""

import re
from pathlib import Path

from rapidfuzz import fuzz

from comida.parser import Ingredient


def load_pantry(path: Path) -> tuple[list[str], list[str]]:
    pantry: list[str] = []
    always_buy: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("+"):
            always_buy.append(line[1:].strip().lower())
        else:
            pantry.append(line.lower())
    return pantry, always_buy


def _word_match(pantry_term: str, ingredient_name: str) -> bool:
    """Avoid false positives like nori ↔ riz."""
    if len(pantry_term) <= 4:
        return bool(re.search(rf"\b{re.escape(pantry_term)}\b", ingredient_name))
    return pantry_term in ingredient_name or ingredient_name in pantry_term


def _pantry_keywords(item: str) -> list[str]:
    parts = re.split(r"\s+et\s+|/|\s+de\s+", item)
    keywords: list[str] = []
    for part in parts:
        words = part.strip().split()
        if words:
            keywords.append(words[0])
    return keywords


def is_always_buy(ingredient_name: str, always_buy: list[str], threshold: int = 80) -> bool:
    name = ingredient_name.lower()
    for rule in always_buy:
        if rule in name or name in rule:
            return True
        if fuzz.partial_ratio(rule, name) >= threshold:
            return True
    return False


def is_pantry_item(ingredient_name: str, pantry: list[str], threshold: int = 72) -> tuple[bool, str | None]:
    name = ingredient_name.lower()
    for item in pantry:
        for keyword in _pantry_keywords(item):
            if _word_match(keyword, name):
                return True, item
        if len(item) > 4 and fuzz.partial_ratio(item, name) >= threshold:
            return True, item
    return False, None


def filter_pantry(
    ingredients: list[Ingredient], pantry_path: Path
) -> tuple[list[Ingredient], list[tuple[Ingredient, str]]]:
    pantry, always_buy = load_pantry(pantry_path)
    kept: list[Ingredient] = []
    skipped: list[tuple[Ingredient, str]] = []
    for ing in ingredients:
        if is_always_buy(ing.name, always_buy):
            kept.append(ing)
            continue
        covered, match = is_pantry_item(ing.name, pantry)
        if covered:
            skipped.append((ing, match or ""))
        else:
            kept.append(ing)
    return kept, skipped
