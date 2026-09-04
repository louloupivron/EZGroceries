"""Convert recipe amounts to Migros basket pack counts."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

# Kookd exports are scaled for this many portions by default.
DEFAULT_PORTIONS = 8

UNIT_ALIASES: dict[str, str] = {
    "g": "g",
    "gr": "g",
    "gramme": "g",
    "grammes": "g",
    "kg": "kg",
    "kilogramme": "kg",
    "kilogrammes": "kg",
    "ml": "ml",
    "millilitre": "ml",
    "millilitres": "ml",
    "cl": "cl",
    "centilitre": "cl",
    "centilitres": "cl",
    "l": "l",
    "litre": "l",
    "litres": "l",
    "pièce": "piece",
    "piece": "piece",
    "pièces": "piece",
    "pieces": "piece",
    "stk": "piece",
    "stück": "piece",
    "stuck": "piece",
    "feuille": "piece",
    "feuilles": "piece",
    "pincée": "piece",
    "pincées": "piece",
    "c.à.s": "piece",
    "cas": "piece",
    "c.à.c": "piece",
    "cac": "piece",
    "sachet": "piece",
    "sachets": "piece",
    "boîte": "piece",
    "boite": "piece",
    "boîtes": "piece",
    "boites": "piece",
    "paquet": "piece",
    "paquets": "piece",
}

# Approximate conversions for small units → treat as negligible for pack sizing.
PIECE_EQUIVALENT_GRAMS = 5.0


@dataclass(frozen=True)
class Amount:
    value: float
    unit: str  # normalized: g, kg, ml, cl, l, piece

    def to_grams_or_ml(self) -> float | None:
        if self.unit == "g":
            return self.value
        if self.unit == "kg":
            return self.value * 1000
        if self.unit == "ml":
            return self.value
        if self.unit == "cl":
            return self.value * 10
        if self.unit == "l":
            return self.value * 1000
        if self.unit == "piece":
            return self.value * PIECE_EQUIVALENT_GRAMS
        return None


def normalize_unit(unit: str) -> str:
    return UNIT_ALIASES.get(unit.lower().strip().rstrip("."), unit.lower().strip())


def parse_amount_text(text: str) -> Amount | None:
    """Parse '200 g', '1.5 kg', '3 pièces', '500ml'."""
    text = text.strip()
    if not text:
        return None
    match = re.match(
        r"^(?P<qty>\d+(?:[.,]\d+)?)\s*(?P<unit>.+)$",
        text,
        re.IGNORECASE,
    )
    if not match:
        return None
    value = float(match.group("qty").replace(",", "."))
    unit = normalize_unit(match.group("unit").strip())
    return Amount(value, unit)


def parse_recipe_quantity(quantity_str: str | None) -> Amount | None:
    if not quantity_str or quantity_str == "?":
        return None
    return parse_amount_text(quantity_str.strip())


def parse_package_size(package: str | None) -> Amount | None:
    """Parse Migros offer quantity, e.g. '200g', '1 Stück', '500 ml'."""
    if not package:
        return None
    text = str(package).strip()
    compact = re.sub(r"\s+", "", text.lower())
    match = re.match(r"^(?P<qty>\d+(?:[.,]\d+)?)(?P<unit>[a-zàâäéèêëïîôùûüç.]+)$", compact)
    if match:
        return Amount(float(match.group("qty").replace(",", ".")), normalize_unit(match.group("unit")))
    return parse_amount_text(text)


def _compatible_units(needed: Amount, package: Amount) -> bool:
    weight = {"g", "kg"}
    volume = {"ml", "cl", "l"}
    if needed.unit == package.unit:
        return True
    if needed.unit in weight and package.unit in weight:
        return True
    if needed.unit in volume and package.unit in volume:
        return True
    if needed.unit == "piece" or package.unit == "piece":
        return True
    return False


def compute_basket_quantity(
    quantity_str: str | None,
    package: str | None = None,
    *,
    default: int = 1,
) -> int:
    """Return number of Migros packs to add for a recipe line."""
    needed = parse_recipe_quantity(quantity_str)
    if needed is None:
        return default

    pack = parse_package_size(package)
    if pack is None or not _compatible_units(needed, pack):
        return default

    needed_base = needed.to_grams_or_ml()
    pack_base = pack.to_grams_or_ml()
    if needed_base is None or pack_base is None or pack_base <= 0:
        return default

    if needed.unit == "piece" and pack.unit == "piece":
        return max(1, math.ceil(needed.value / pack.value))

    return max(1, math.ceil(needed_base / pack_base))


def format_amount(amount: Amount) -> str:
    if amount.unit == "piece":
        label = "pièce" if amount.value <= 1 else "pièces"
        qty = int(amount.value) if amount.value == int(amount.value) else amount.value
        return f"{qty:g} {label}"
    return f"{amount.value:g} {amount.unit}"


def subtract_amounts(needed: Amount, stock: Amount) -> Amount | None:
    """Subtract pantry stock from needed amount; None if fully covered."""
    if not _compatible_units(needed, stock):
        return needed

    if needed.unit == "piece" and stock.unit == "piece":
        remaining = needed.value - stock.value
        if remaining <= 0:
            return None
        return Amount(remaining, "piece")

    needed_base = needed.to_grams_or_ml()
    stock_base = stock.to_grams_or_ml()
    if needed_base is None or stock_base is None:
        return needed

    remaining_base = needed_base - stock_base
    if remaining_base <= 0:
        return None

    if needed.unit in ("g", "kg"):
        unit = "g" if needed.unit == "g" or remaining_base < 1000 else "kg"
        value = remaining_base if unit == "g" else remaining_base / 1000
        return Amount(value, unit)

    if needed.unit in ("ml", "cl", "l"):
        if needed.unit == "ml" or remaining_base < 1000:
            return Amount(remaining_base, "ml")
        return Amount(remaining_base / 1000, "l")

    return needed
