"""German Migros product names → French ingredient labels."""

import re
import unicodedata

# Whole-word / phrase replacements (longest first at runtime)
PHRASES: list[tuple[str, str]] = [
    ("schweinsgeschnetzeltes", "émincé de porc"),
    ("gelbflossenthunfischfilets", "filets de thon albacore"),
    ("gelbflossenthunfisch", "thon albacore"),
    ("thunfischfilets", "filets de thon"),
    ("thunfisch", "thon"),
    ("blumenkohl-roschen", "rosettes de chou-fleur"),
    ("blumenkohl roschen", "rosettes de chou-fleur"),
    ("blumenkohl", "chou-fleur"),
    ("brokkoli", "brocolis"),
    ("broccoli", "brocolis"),
    ("rind burger classic", "bœuf haché"),
    ("rind burger", "bœuf haché"),
    ("rindshuft", "rumsteck de boeuf"),
    ("schweinshohruckensteak", "steak de porc"),
    ("schweinssteak", "steak de porc"),
    ("schweinshals", "collier de porc"),
    ("spare ribs", "travers de porc"),
    ("kartoffeln", "pommes de terre"),
    ("tomaten", "tomates"),
    ("mozzarella", "mozzarella pour pizza"),
    ("parmesan", "parmesan"),
    ("gruyere", "gruyere"),
    ("gruyère", "gruyère"),
    ("emmental", "emmental"),
    ("bifidus joghurt", "yaourt"),
    ("joghurt", "yaourt"),
    ("momos", "momos"),
    ("gemusemix", "melange de legumes"),
    ("gemüsemix", "melange de legumes"),
    ("gurken", "concombres"),
    ("gurke", "concombre"),
    ("zucchetti", "courgettes"),
    ("zucchini", "courgettes"),
    ("lachs", "saumon"),
    ("speckwurfel", "lardons fumes"),
    ("speckwürfel", "lardons fumes"),
    ("hahnchen", "poulet"),
    ("hähnchen", "poulet"),
    ("pute", "dinde"),
    ("lamm", "agneau"),
    ("pizzateig", "pate a pizza"),
    ("tarteteig", "pate a tarte"),
    ("nudeln", "pates"),
    ("reis", "riz"),
    ("linsen", "lentilles"),
    ("kichererbsen", "pois chiches"),
    ("bohnen", "haricots"),
    ("champignons", "champignons"),
    ("zwiebeln", "oignons"),
    ("knoblauch", "ail"),
    ("paprika", "poivrons"),
    ("karotten", "carottes"),
    ("salat", "salade"),
    ("rahm", "creme"),
    ("creme fraiche", "creme fraiche"),
    ("eier", "oeufs"),
    ("ei", "oeuf"),
    ("melone", "melon"),
    ("avocado", "avocat"),
    ("bananen", "bananes"),
    ("banane", "banane"),
    ("papaya", "papaye"),
    ("kokosnuss", "noix de coco"),
    ("gewurzgurken", "cornichons"),
    ("ketchup", "ketchup"),
    ("mayonnaise", "mayonnaise"),
    ("senf", "moutarde"),
    ("brot", "pain"),
    ("baguette", "baguette"),
    ("toast", "pain de mie"),
    ("burger", "burger"),
    ("garnelen", "crevettes"),
    ("tofu", "tofu"),
]

WORDS: dict[str, str] = {
    "migros": "",
    "anna's": "",
    "annas": "",
    "farmer's": "",
    "farmers": "",
    "farmer": "",
    "best": "",
    "fidelio": "",
    "longobardi": "",
    "alfredo": "",
    "condy": "",
    "eisberg": "",
    "gourmet": "",
    "classic": "",
    "filet": "",
    "am": "",
    "stuck": "piece",
    "stück": "piece",
    "frisch": "",
    "bio": "",
}


def _strip_accents(text: str) -> str:
    base = unicodedata.normalize("NFKD", text)
    return "".join(c for c in base if not unicodedata.combining(c))


def translate_product_name(name: str) -> str:
    """Translate a Migros product name to a French ingredient label."""
    lower = _strip_accents(name.lower())

    for de, fr in sorted(PHRASES, key=lambda x: -len(x[0])):
        if _strip_accents(de) in lower:
            return fr

    tokens = re.findall(r"[a-z0-9']+", lower)
    out: list[str] = []
    for token in tokens:
        if token in WORDS:
            mapped = WORDS[token]
            if mapped:
                out.append(mapped)
            continue
        out.append(token)

    label = " ".join(out)
    label = re.sub(r"\s+", " ", label).strip()
    return label
