"""Structured read/write for garde-manger.txt and courses-hebdo.txt."""

from __future__ import annotations

from pathlib import Path

from comida.pantry import _parse_pantry_line

ROOT = Path(__file__).resolve().parents[2]
PANTRY_PATH = ROOT / "garde-manger.txt"
WEEKLY_PATH = ROOT / "courses-hebdo.txt"

ALWAYS_BUY_NOTE = "# Toujours acheter (+), même si un article garde-manger correspond"

KINDS = {
    "pantry": PANTRY_PATH,
    "weekly": WEEKLY_PATH,
}


def parse_entry_line(line: str, *, allow_always_buy: bool) -> dict:
    text = line.strip()
    always = False
    if allow_always_buy and text.startswith("+"):
        always = True
        text = text[1:].strip()
    if not text:
        raise ValueError("Nom vide")
    name, qty, unit = _parse_pantry_line(text, preserve_case=True)
    if not name:
        raise ValueError("Nom vide")
    return {
        "name": name,
        "quantity": qty,
        "unit": unit,
        "always_buy": always,
    }


def _format_qty(qty: float) -> str:
    if qty == int(qty):
        return str(int(qty))
    text = f"{qty:g}"
    return text


def _same_item(parsed: dict, item: dict, *, allow_always_buy: bool) -> bool:
    name = str(item.get("name") or "").strip()
    if parsed["name"] != name:
        return False
    always = bool(item.get("always_buy")) if allow_always_buy else False
    if parsed["always_buy"] != always:
        return False
    raw_qty = item.get("quantity")
    unit = str(item.get("unit") or "").strip()
    if raw_qty is None or raw_qty == "":
        return parsed["quantity"] is None and not unit
    try:
        qty = float(str(raw_qty).replace(",", "."))
    except (TypeError, ValueError):
        return False
    return parsed["quantity"] == qty and (parsed["unit"] or "") == unit


def entry_line(item: dict, *, allow_always_buy: bool) -> str:
    original = item.get("line")
    if isinstance(original, str) and original.strip():
        parsed = parse_entry_line(original.strip(), allow_always_buy=allow_always_buy)
        if _same_item(parsed, item, allow_always_buy=allow_always_buy):
            return original.rstrip("\r")
    return format_entry(item, allow_always_buy=allow_always_buy)


def format_entry(item: dict, *, allow_always_buy: bool) -> str:
    name = str(item.get("name") or "").strip()
    if not name or any(ch in name for ch in "\n\r"):
        raise ValueError("Nom invalide")
    if len(name) > 120:
        raise ValueError("Nom trop long")

    raw_qty = item.get("quantity")
    unit = str(item.get("unit") or "").strip()
    if raw_qty is None or raw_qty == "":
        if unit:
            raise ValueError(f"Unité sans quantité pour « {name} »")
        body = name
    else:
        try:
            qty = float(str(raw_qty).replace(",", "."))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Quantité invalide pour « {name} »") from exc
        if qty <= 0:
            raise ValueError(f"Quantité invalide pour « {name} »")
        if not unit or any(ch in unit for ch in "\n\r "):
            raise ValueError(f"Unité manquante pour « {name} »")
        body = f"{name} {_format_qty(qty)} {unit}"

    if allow_always_buy and bool(item.get("always_buy")):
        return f"+ {body}"
    return body


def _split_preamble(text: str) -> tuple[str, list[str]]:
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        stripped = lines[index].strip()
        if stripped and not stripped.startswith("#"):
            break
        index += 1
    preamble = "\n".join(lines[:index]).strip("\n")
    return preamble, lines[index:]


def parse_stock_text(text: str, *, allow_always_buy: bool) -> tuple[str, list[dict]]:
    preamble, body = _split_preamble(text)
    items: list[dict] = []
    for line in body:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        item = parse_entry_line(stripped, allow_always_buy=allow_always_buy)
        item["line"] = line
        items.append(item)
    return preamble, items


def render_stock_text(
    preamble: str,
    items: list[dict],
    *,
    allow_always_buy: bool,
) -> str:
    regular = [item for item in items if not (allow_always_buy and item.get("always_buy"))]
    always = [item for item in items if allow_always_buy and item.get("always_buy")]
    lines: list[str] = []
    if preamble.strip():
        lines.append(preamble.strip("\n"))
        lines.append("")
    lines.extend(entry_line(item, allow_always_buy=False) for item in regular)
    if always:
        if lines and lines[-1] != "":
            lines.append("")
        lines.append(ALWAYS_BUY_NOTE)
        lines.extend(entry_line(item, allow_always_buy=True) for item in always)
    rendered = "\n".join(lines).rstrip() + "\n"
    return rendered


def normalize_items(raw: list, *, allow_always_buy: bool) -> list[dict]:
    if not isinstance(raw, list):
        raise ValueError("items doit être une liste")
    items: list[dict] = []
    for entry in raw:
        if isinstance(entry, str):
            items.append(parse_entry_line(entry, allow_always_buy=allow_always_buy))
            continue
        if not isinstance(entry, dict):
            raise ValueError("Entrée invalide")
        item = {
            "name": entry.get("name"),
            "quantity": entry.get("quantity"),
            "unit": entry.get("unit"),
            "always_buy": bool(entry.get("always_buy")) if allow_always_buy else False,
        }
        # Re-parse through the formatter so the stored shape matches the file.
        parsed = parse_entry_line(
            format_entry(item, allow_always_buy=allow_always_buy),
            allow_always_buy=allow_always_buy,
        )
        if isinstance(entry, dict) and isinstance(entry.get("line"), str):
            parsed["line"] = entry["line"]
        items.append(parsed)
    return items


def load_lists() -> dict:
    payload = {}
    for kind, path in KINDS.items():
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        _preamble, items = parse_stock_text(text, allow_always_buy=kind == "pantry")
        payload[kind] = {"items": items}
    return payload


def save_list(kind: str, raw_items: list) -> dict:
    path = KINDS.get(kind)
    if path is None:
        raise ValueError("Liste inconnue")
    allow_always_buy = kind == "pantry"
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    preamble, _items = parse_stock_text(text, allow_always_buy=allow_always_buy)
    items = normalize_items(raw_items, allow_always_buy=allow_always_buy)
    rendered = render_stock_text(preamble, items, allow_always_buy=allow_always_buy)
    path.write_text(rendered, encoding="utf-8")
    return load_lists()
