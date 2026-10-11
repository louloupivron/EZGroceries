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
    "tranche": "piece",
    "tranches": "piece",
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


def _normalize_package_text(text: str) -> str:
    text = text.replace("\u2009", " ").replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", " ", text.strip().lower())


def _amount_in_base(amount: Amount) -> float | None:
    return amount.to_grams_or_ml()


def pieces_per_retail_pack(package: str | None) -> float | None:
    """
    Pieces in one Migros retail unit when sold as count × weight (e.g. '2 × 140 g' → 2).
    """
    if not package:
        return None
    text = _normalize_package_text(str(package))
    multipack = re.match(
        r"^(?P<count>\d+)\s*[x×]\s*(?P<qty>\d+(?:[.,]\d+)?)\s*(?P<unit>[a-zàâäéèêëïîôùûüç.]+)$",
        text,
    )
    if multipack:
        unit = normalize_unit(multipack.group("unit"))
        if unit in ("g", "kg", "ml", "cl", "l"):
            return float(multipack.group("count").replace(",", "."))
    if re.match(r"^1\s*(stück|stuck|stk|piece|pièce|pieces|pièces)$", text):
        return 1.0
    return None


def parse_package_size(package: str | None) -> Amount | None:
    """Parse Migros offer quantity, e.g. '200 g', '2 × 360 g', '170–210 g'."""
    if not package:
        return None
    text = _normalize_package_text(str(package))

    multipack = re.match(
        r"^(?P<count>\d+)\s*[x×]\s*(?P<qty>\d+(?:[.,]\d+)?)\s*(?P<unit>[a-zàâäéèêëïîôùûüç.]+)$",
        text,
    )
    if multipack:
        count = float(multipack.group("count").replace(",", "."))
        qty = float(multipack.group("qty").replace(",", "."))
        unit = normalize_unit(multipack.group("unit"))
        return Amount(count * qty, unit)

    range_match = re.match(
        r"^(?P<low>\d+(?:[.,]\d+)?)\s*-\s*(?P<high>\d+(?:[.,]\d+)?)\s*(?P<unit>[a-zàâäéèêëïîôùûüç.]+)$",
        text,
    )
    if range_match:
        # Use the lower bound so we do not under-order variable-weight packs.
        low = float(range_match.group("low").replace(",", "."))
        unit = normalize_unit(range_match.group("unit"))
        return Amount(low, unit)

    compact = re.sub(r"\s+", "", text)
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


@dataclass(frozen=True)
class BasketQuantity:
    """Pack count plus whether it is safe to push without a look."""

    packs: int
    confidence: str  # "ok" | "revue"
    note: str = ""

    @property
    def needs_review(self) -> bool:
        return self.confidence != "ok"


def compute_basket_quantity(
    quantity_str: str | None,
    package: str | None = None,
    *,
    default: int = 1,
) -> BasketQuantity:
    """Return Migros pack count. Uncertain conversions stay visible as revue."""
    needed = parse_recipe_quantity(quantity_str)
    if needed is None:
        return BasketQuantity(default, "revue", "quantité recette illisible")

    pack = parse_package_size(package)
    if pack is None or not _compatible_units(needed, pack):
        return BasketQuantity(default, "revue", "format Migros illisible")

    if needed.unit in ("g", "kg") and pack.unit in ("g", "kg"):
        needed_g = needed.to_grams_or_ml()
        pack_g = pack.to_grams_or_ml()
        if needed_g is None or pack_g is None or pack_g <= 0:
            return BasketQuantity(default, "revue", "format Migros illisible")
        return BasketQuantity(max(1, math.ceil(needed_g / pack_g)), "ok")

    if needed.unit in ("ml", "cl", "l") and pack.unit in ("ml", "cl", "l"):
        needed_ml = needed.to_grams_or_ml()
        pack_ml = pack.to_grams_or_ml()
        if needed_ml is None or pack_ml is None or pack_ml <= 0:
            return BasketQuantity(default, "revue", "format Migros illisible")
        return BasketQuantity(max(1, math.ceil(needed_ml / pack_ml)), "ok")

    if needed.unit == "piece" and pack.unit == "piece":
        if pack.value <= 0:
            return BasketQuantity(default, "revue", "format Migros illisible")
        return BasketQuantity(max(1, math.ceil(needed.value / pack.value)), "ok")

    if needed.unit == "piece":
        per_pack = pieces_per_retail_pack(package)
        if per_pack is not None and per_pack > 0:
            return BasketQuantity(max(1, math.ceil(needed.value / per_pack)), "ok")
        if pack.unit in ("g", "kg"):
            pack_grams = pack.to_grams_or_ml()
            if pack_grams is not None and 50 <= pack_grams <= 2000:
                return BasketQuantity(max(1, math.ceil(needed.value)), "ok")
            return BasketQuantity(default, "revue", "pièce contre un poids hors bande")
        return BasketQuantity(default, "revue", "format Migros illisible")

    # Recipe weight against a per-piece offer (mangue, avocat). 200 g is an estimate.
    if pack.unit == "piece" and needed.unit in ("g", "kg"):
        needed_g = needed.to_grams_or_ml()
        if needed_g is None:
            return BasketQuantity(default, "revue", "quantité recette illisible")
        packs = max(1, math.ceil(needed_g / 200.0))
        return BasketQuantity(packs, "revue", "estimation 200 g par pièce")

    return BasketQuantity(default, "revue", "unités incompatibles")


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
