"""Filter a Migros shopping list into a Kookd ingredient export (format A)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from comida.basket import get_basket_for_list, resolve_list_target, shared_list_url
from comida.de_fr import translate_product_name
from comida.matcher import _display_name, _is_mbudget, _is_non_food, _is_prepared_food
from comida.migros_client import fetch_product_details
from comida.pantry import filter_pantry
from comida.parser import Ingredient

ROOT = Path(__file__).resolve().parents[2]
FILTER_OVERRIDES = ROOT / "promo-filter.txt"

# Migros breadcrumb L1 names (DE)
DRINKS_SNACKS_L1 = {
    "getränke, kaffee & tee",
    "snacks & süssigkeiten",
}

FRUIT_BREADCRUMB = {"früchte", "fruchte"}
VEGETABLE_HINTS = {
    "gemüse", "gemuse", "kartoffel", "karotte", "salat", "zwiebel", "tomate",
    "paprika", "zucchetti", "zucchini", "gurke", "spinat", "brokkoli",
    "champignon", "knoblauch", "lauch", "sellerie",
}

FRUIT_NAME_HINTS = {
    "melone", "banane", "apfel", "birne", "orange", "mandarine",
    "papaya", "mango", "ananas", "kiwi", "beere", "beeren", "traube",
    "zitrone", "limette", "pflaume", "kirsche", "pfirsich", "nektarine",
}

# Fruits utilisés comme ingrédient salé (salade, guacamole, etc.)
SAVORY_FRUIT_EXCEPTIONS = {"avocado", "avocat"}

BREAD_HINTS = {
    "brot", "baguette", "toast", "brötchen", "brotchen", "croissant",
    "gipfel", "zopf", "semmel",
}
DOUGH_KEEP_HINTS = {"pizzateig", "pizza teig", "tarteteig", "tarte", "pâte à pizza", "pate a pizza"}

SAUCE_CONDIMENT_HINTS = {
    "ketchup", "mayonnaise", "mayo", "senf", "moutarde", "bbq", "sriracha",
    "chilisauce", "sojasauce", "fertigsauce", "salatsauce", "dressing",
    "tabasco", "worcester",
}

YOGURT_HINTS = {"joghurt", "yoghurt", "yogurt", "bifidus", "skyr", "dessert"}

PREPARED_HINTS = {
    "fertiggericht", "fertig", "salatbowl", "sandwich", "wrap", "lasagne",
    "pizza ", "burger menu", "nuggets", "fingers", "cordons", "cordon bleu",
    "ravioli fertig", "gnocchi fertig",
}
MOMO_HINTS = {"momo", "momos"}

CHEESE_HINTS: list[tuple[str, str]] = [
    ("mozzarella", "mozzarella pour pizza"),
    ("parmesan", "parmesan"),
    ("gruyère", "gruyère"),
    ("gruyere", "gruyère"),
    ("emmental", "emmental"),
    ("cheddar", "cheddar"),
    ("raclette", "fromage à raclette"),
    ("feta", "feta"),
    ("brie", "brie"),
    ("camembert", "camembert"),
    ("comté", "comté"),
    ("comte", "comté"),
]


@dataclass
class ExportLine:
    label: str
    source_name: str
    uid: int | None


@dataclass
class ExcludedItem:
    name: str
    reason: str
    uid: int | None


def _normalize(text: str) -> str:
    return text.lower().strip()


def _breadcrumb_names(product: dict) -> list[str]:
    return [_normalize(b.get("name", "")) for b in (product.get("breadcrumb") or [])]


def _name_blob(product: dict) -> str:
    return _normalize(_display_name(product))


def _load_overrides() -> tuple[set[str], set[str]]:
    force_include: set[str] = set()
    force_exclude: set[str] = set()
    if not FILTER_OVERRIDES.exists():
        return force_include, force_exclude
    for line in FILTER_OVERRIDES.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("+"):
            force_include.add(_normalize(line[1:]))
        elif line.startswith("-"):
            force_exclude.add(_normalize(line[1:]))
    return force_include, force_exclude


def _is_fruit(product: dict) -> bool:
    blob = _name_blob(product)
    if any(x in blob for x in SAVORY_FRUIT_EXCEPTIONS):
        return False
    if any(h in blob for h in FRUIT_NAME_HINTS):
        if not any(v in blob for v in VEGETABLE_HINTS):
            return True
    for crumb in _breadcrumb_names(product):
        if crumb in FRUIT_BREADCRUMB:
            return True
    return False


def _is_bread_not_dough(product: dict) -> bool:
    blob = _name_blob(product)
    if any(k in blob for k in DOUGH_KEEP_HINTS):
        return False
    crumbs = _breadcrumb_names(product)
    if any("brot" in c or "backwaren" in c or "frühstück" in c for c in crumbs):
        if any(k in blob for k in BREAD_HINTS):
            return True
    return any(k in blob for k in BREAD_HINTS)


def _is_table_sauce(product: dict) -> bool:
    blob = _name_blob(product)
    return any(k in blob for k in SAUCE_CONDIMENT_HINTS)


def _is_yogurt_or_dessert_dairy(product: dict) -> bool:
    blob = _name_blob(product)
    return any(k in blob for k in YOGURT_HINTS)


CANNED_BASE_HINTS = {"tomaten", "tomate", "passata", "pelati", "dosentomaten", "mais", "maïs", "kidney", "kichererbsen"}


def _is_canned_base_ingredient(product: dict) -> bool:
    return any(h in _name_blob(product) for h in CANNED_BASE_HINTS)


def _is_prepared_not_momo(product: dict) -> bool:
    blob = _name_blob(product)
    if any(k in blob for k in MOMO_HINTS):
        return False
    if _is_canned_base_ingredient(product):
        return False
    if _is_prepared_food(product):
        return True
    crumbs = _breadcrumb_names(product)
    for crumb in crumbs[1:]:
        if "fertiggericht" in crumb:
            return True
    return any(k in blob for k in PREPARED_HINTS)


def _exclusion_reason(
    product: dict,
    force_include: set[str],
    force_exclude: set[str],
    *,
    apply_filters: bool = True,
) -> str | None:
    blob = _name_blob(product)
    if any(x in blob for x in force_include):
        return None
    if any(x in blob for x in force_exclude):
        return "exclu (promo-filter.txt)"

    if _is_mbudget(product):
        return "M-Budget"
    if _is_non_food(product):
        return "non alimentaire"

    if not apply_filters:
        return None

    l1 = _breadcrumb_names(product)[0] if _breadcrumb_names(product) else ""
    if l1 in DRINKS_SNACKS_L1:
        return f"categorie exclue ({l1})"

    if _is_fruit(product):
        return "fruit"
    if _is_bread_not_dough(product):
        return "pain"
    if _is_table_sauce(product):
        return "sauce condiment"
    if _is_yogurt_or_dessert_dairy(product):
        return "yaourt / dessert"
    if _is_prepared_not_momo(product):
        return "plat prepare"

    return None


def _refine_cheese_label(label: str, product: dict) -> str:
    blob = _name_blob(product)
    for key, refined in CHEESE_HINTS:
        if key in blob or key in label:
            return refined
    if "kase" in blob or "käse" in blob or "fromage" in label:
        return label if label else "fromage"
    return label


def _refine_canned_tomato_label(product: dict) -> str | None:
    """Use Migros breadcrumb/package to distinguish canned vs fresh tomatoes."""
    crumbs = _breadcrumb_names(product)
    blob = _name_blob(product)
    crumb_text = " ".join(crumbs)

    is_canned = (
        "tomatenkonserv" in crumb_text
        or ("konserv" in crumb_text and "tomaten" in blob)
        or ("tomaten" in blob and any(k in crumb_text for k in ("konserven", "konserve")))
    )
    if not is_canned:
        return None

    if "passata" in blob:
        return "passata (tomates en conserve)"
    if "geschält" in crumb_text or "gehackt" in crumb_text or "gehackt" in blob:
        return "tomates en conserve pelées et hachées"
    if "pelati" in blob or "ganze" in blob or "enti" in crumb_text:
        return "tomates en conserve entières"
    return "tomates en conserve"


def _translation_source(product: dict) -> str:
    """Prefer Migros title (package/format) over short product name."""
    title = (product.get("title") or "").replace("·", " ")
    name = product.get("name") or product.get("description") or ""
    return " ".join(p for p in (title, name) if p).strip() or _name_blob(product)


def _refine_mozzarella_label(label: str, product: dict) -> str:
    blob = _normalize(f"{product.get('title') or ''} {_name_blob(product)}")
    if "stange" in blob or "block" in blob or "bloc" in blob:
        return "mozzarella en bloc"
    if "mozzarella" in blob or "mozzarella" in _normalize(label):
        return "mozzarella fraîche"
    return label


def _to_kookd_label(product: dict) -> str:
    name = _display_name(product)
    source = _translation_source(product)
    canned_tomato = _refine_canned_tomato_label(product)
    if canned_tomato:
        label = canned_tomato
    else:
        label = translate_product_name(source or name)
    label = _refine_cheese_label(label, product)
    label = _refine_mozzarella_label(label, product)
    if any(k in _name_blob(product) for k in MOMO_HINTS):
        label = "momos à accompagner de riz et sauce"
    label = label.strip()
    if not label:
        label = translate_product_name(product.get("name") or name)
    return label


def _dedupe_key(label: str) -> str:
    return re.sub(r"\s+", " ", _normalize(label))


def export_list_to_kookd(
    list_name: str,
    *,
    pantry_path: Path | None = None,
    apply_pantry: bool = False,
    apply_filters: bool = True,
) -> tuple[list[ExportLine], list[ExcludedItem]]:
    basket = get_basket_for_list(list_name=list_name)
    uids = [int(item["productId"]) for item in basket.get("items", []) if item.get("productId")]
    if not uids:
        return [], []

    products = fetch_product_details(uids)
    force_include, force_exclude = _load_overrides()

    included: list[ExportLine] = []
    excluded: list[ExcludedItem] = []
    seen: set[str] = set()

    for product in products:
        uid = product.get("uid")
        source = _display_name(product)
        reason = _exclusion_reason(
            product, force_include, force_exclude, apply_filters=apply_filters
        )
        if reason:
            excluded.append(ExcludedItem(name=source, reason=reason, uid=uid))
            continue

        label = _to_kookd_label(product)
        key = _dedupe_key(label)
        if key in seen:
            excluded.append(ExcludedItem(name=source, reason="doublon (même libellé)", uid=uid))
            continue
        seen.add(key)
        included.append(ExportLine(label=label, source_name=source, uid=uid))

    if apply_pantry:
        pantry = pantry_path or (ROOT / "garde-manger.txt")
        fake = [
            Ingredient(1, "pièce", line.label, f"- 1 pièce {line.label}") for line in included
        ]
        kept, skipped = filter_pantry(fake, pantry)
        skipped_labels = {_normalize(i.name) for i, _ in skipped}
        included = [line for line in included if _normalize(line.label) not in skipped_labels]
        for ing, rule in skipped:
            excluded.append(ExcludedItem(name=ing.name, reason=f"garde-manger ({rule})", uid=None))

    return included, excluded


def format_kookd_export(lines: list[ExportLine]) -> str:
    return "\n".join(line.label for line in lines) + ("\n" if lines else "")


def promos_no_filter_from_env() -> bool:
    import os

    from comida.basket import _load_dotenv

    _load_dotenv()
    return os.environ.get("MIGROS_PROMOS_NO_FILTER", "").strip().lower() in ("1", "true", "yes")


def describe_list_inventory(
    list_name: str,
    *,
    apply_filters: bool = True,
) -> tuple[int, list[tuple[str, str, str | None]]]:
    """Return (api_count, rows of (product_name, status, detail))."""
    basket = get_basket_for_list(list_name=list_name)
    uids = [int(item["productId"]) for item in basket.get("items", []) if item.get("productId")]
    if not uids:
        return 0, []

    products = fetch_product_details(uids)
    force_include, force_exclude = _load_overrides()
    rows: list[tuple[str, str, str | None]] = []

    for product in products:
        source = _display_name(product)
        reason = _exclusion_reason(
            product, force_include, force_exclude, apply_filters=apply_filters
        )
        if reason:
            rows.append((source, "exclu", reason))
        else:
            rows.append((source, "inclus", _to_kookd_label(product)))

    return len(uids), rows


def run_promos_export(
    list_name: str,
    output: Path | None = None,
    *,
    pantry_path: Path | None = None,
    apply_pantry: bool | None = None,
    apply_filters: bool | None = None,
) -> Path:
    use_filters = apply_filters if apply_filters is not None else not promos_no_filter_from_env()
    use_pantry = apply_pantry if apply_pantry is not None else pantry_path is not None

    api_count, inventory = describe_list_inventory(list_name, apply_filters=use_filters)
    included, excluded = export_list_to_kookd(
        list_name,
        pantry_path=pantry_path,
        apply_pantry=use_pantry,
        apply_filters=use_filters,
    )
    _, list_id = resolve_list_target(list_name)
    content = format_kookd_export(included)
    out = output or (ROOT / "exports" / f"promos-{list_name.lower()}.txt")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(content, encoding="utf-8")

    print(f"Liste Migros : {list_name}" + (f" (id {list_id})" if list_id else ""))
    link = shared_list_url()
    if link:
        print(f"  Lien partagé : {link}")
    print(f"  {api_count} produit(s) dans la liste (API Migros)")
    if not use_filters:
        print("  Filtres promo : désactivés (liste curatée)")
    print(f"  {len(included)} ingrédient(s) exporté(s) → {out}")
    if inventory:
        print("  Détail :")
        for name, status, detail in inventory:
            if status == "inclus":
                print(f"    ✓ {name} → {detail}")
            else:
                print(f"    ✗ {name} — {detail}")
    if excluded and use_filters:
        print(f"  {len(excluded)} exclu(s) par les filtres :")
        for item in excluded:
            print(f"    • {item.name} — {item.reason}")
    print()
    print("--- Export Kookd (format A) ---")
    print(content)
    return out
