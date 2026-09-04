"""Basket cost estimation and delivery minimum checks."""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_MIN_DELIVERY_CHF = 99.0


def _load_min_delivery() -> float:
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("MIGROS_MIN_DELIVERY_CHF="):
                _, _, val = line.partition("=")
                try:
                    return float(val.strip().strip("'\""))
                except ValueError:
                    break
    raw = os.environ.get("MIGROS_MIN_DELIVERY_CHF")
    if raw:
        try:
            return float(raw)
        except ValueError:
            pass
    return DEFAULT_MIN_DELIVERY_CHF


def estimate_basket(resolved: list[dict]) -> dict:
    """Estimate basket total from resolved session items."""
    lines: list[dict] = []
    total = 0.0
    priced_count = 0

    for item in resolved:
        qty = int(item.get("quantity_parsed") or 1)
        unit_price = item.get("price_chf")
        line_total = None
        if unit_price is not None:
            line_total = round(float(unit_price) * qty, 2)
            total += line_total
            priced_count += 1
        lines.append({
            "ingredient_name": item.get("ingredient_name"),
            "name": item.get("name"),
            "quantity_parsed": qty,
            "quantity": item.get("quantity"),
            "unit_price_chf": unit_price,
            "line_total_chf": line_total,
            "on_promotion": item.get("on_promotion", False),
        })

    min_delivery = _load_min_delivery()
    gap = round(max(0.0, min_delivery - total), 2) if priced_count else None

    return {
        "item_count": len(resolved),
        "priced_count": priced_count,
        "estimated_total_chf": round(total, 2) if priced_count else None,
        "min_delivery_chf": min_delivery,
        "delivery_gap_chf": gap,
        "meets_minimum": gap == 0 if gap is not None else None,
        "lines": lines,
    }


def format_budget_summary(budget: dict) -> str:
    lines: list[str] = []
    total = budget.get("estimated_total_chf")
    if total is not None:
        lines.append(f"Total estimé : {total:.2f} CHF ({budget['priced_count']}/{budget['item_count']} prix connus)")
        gap = budget.get("delivery_gap_chf")
        if gap is not None and gap > 0:
            lines.append(
                f"Minimum livraison : {budget['min_delivery_chf']:.0f} CHF "
                f"(il manque ~{gap:.2f} CHF)"
            )
        elif budget.get("meets_minimum"):
            lines.append(f"Minimum livraison ({budget['min_delivery_chf']:.0f} CHF) : OK")
    else:
        lines.append("Total estimé : prix indisponibles")
    return "\n".join(lines)


def format_basket_enriched(resolved: list[dict]) -> str:
    budget = estimate_basket(resolved)
    out = ["# Panier Comida", ""]
    out.append(format_budget_summary(budget))
    out.append("")
    out.append("## Articles")
    for line in budget["lines"]:
        qty = line["quantity_parsed"]
        qty_label = f" × {qty}" if qty > 1 else ""
        price = line.get("unit_price_chf")
        line_total = line.get("line_total_chf")
        price_bits: list[str] = []
        if price is not None:
            price_bits.append(f"{price:.2f} CHF/u")
        if line_total is not None:
            price_bits.append(f"= {line_total:.2f} CHF")
        price_s = f" — {' · '.join(price_bits)}" if price_bits else ""
        promo = " [PROMO]" if line.get("on_promotion") else ""
        needed = f" ({line['quantity']})" if line.get("quantity") else ""
        out.append(
            f"- {line['ingredient_name']}{needed} → {line['name']}{qty_label}{promo}{price_s}"
        )
    return "\n".join(out)
