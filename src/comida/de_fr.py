"""German Migros product names → French ingredient labels."""

import re
import unicodedata

# Whole-word / phrase replacements (longest first at runtime)
PHRASES: list[tuple[str, str]] = [
    ("schweinsgeschnetzeltes", "émincé de porc"),
    ("gelbflossenthunfischfilets", "filets de thon albacore"),
    ("gelbflossenthunfisch", "thon albacore"),
    ("thunfischfilets", "filets de thon"),
    ("thunfisch", "thon en conserve"),
    ("schweinsbratwurst", "saucisses de porc"),
    ("bratwurst", "saucisses de porc"),
    ("poulet ganz", "poulet entier"),
    ("gnocchi", "gnocchi"),
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
    ("speckwurfel", "lardons fumés"),
    ("speckwürfel", "lardons fumés"),
    ("poulet flugel gewurzt", "ailes de poulet épicées"),
    ("poulet flügel gewürzt", "ailes de poulet épicées"),
    ("poulet flugel", "ailes de poulet"),
    ("poulet flügel", "ailes de poulet"),
    ("pastasauce basilico", "sauce tomate au basilic"),
    ("pastasauce", "sauce tomate"),
    ("pesto basilico e limone", "pesto basilic et citron"),
    ("pesto genovese", "pesto genovese"),
    ("pesto rosso", "pesto rosso"),
    ("sugo basilico", "sauce tomate au basilic"),
    ("trauben kernlos", "raisins sans pépins"),
    ("pink lady apfel", "pommes Pink Lady"),
    ("apfel", "pommes"),
    ("trauben", "raisins"),
    ("joghurt drink", "boisson au yaourt"),
    ("kompott", "compote"),
    ("erdbeer", "fraise"),
    ("heidelbeere", "myrtille"),
    ("pfirsich", "pêche"),
    ("duschcreme", "gel douche"),
    ("backpapierbogen", "papier cuisson"),
    ("rote fruchte", "fruits rouges"),
    ("milchschokolade", "chocolat au lait"),
    ("caramel", "caramel"),
    ("mandeldrink", "boisson amande"),
    ("haferdrink", "boisson avoine"),
    ("reisdrink", "boisson riz"),
    ("sojadrink", "boisson soja"),
    ("hahnchen", "poulet"),
    ("hähnchen", "poulet"),
    ("pute", "dinde"),
    ("lamm", "agneau"),
    ("pizzateig", "pate a pizza"),
    ("tarteteig", "pate a tarte"),
    ("nudeln", "pates"),
    ("reis", "riz"),
    ("linsen", "lentilles"),
    ("grune bohnen", "haricots verts"),
    ("grüne bohnen", "haricots verts"),
    ("bohnen extrafein", "haricots verts extra-fins"),
    ("extrafeine bohnen", "haricots verts extra-fins"),
    ("bohnen", "haricots verts"),
    ("gelbflossenthunfischfilet", "filet de thon"),
    ("gelbflossenthunfisch", "thon"),
    ("bratspeck", "lard fumé"),
    ("zwetschgen", "prunes"),
    ("weisswein", "vin blanc"),
    ("kokosnussmilch", "lait de coco"),
    ("rigatoni", "pâtes rigatoni"),
    ("spaghetti", "pâtes spaghetti"),
    ("pistazien", "pistaches"),
    ("milchspezialitat", "yaourt"),
    ("milchperle", "yaourt"),
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
    "frisch": "",
    "bio": "",
    "emmi": "",
    "optigal": "",
    "barilla": "",
    "alpro": "",
    "andros": "",
    "frey": "",
    "extra": "",
    "pink": "",
    "lady": "",
    "aktifit": "",
    "skyr": "",
    "yoqua": "",
    "nature": "",
    "genovese": "",
    "rosso": "",
    "basilico": "",
    "limone": "",
    "molisana": "",
    "sugo": "",
    "marseillais": "",
    "petit": "",
    "lavendel": "",
    "ohne": "",
    "zuckerzusatz": "",
    "vegan": "",
    "stuck": "",
    "stück": "",
    "piece": "",
    "gewurzt": "épicé",
    "gewürzt": "épicé",
}


def _strip_accents(text: str) -> str:
    base = unicodedata.normalize("NFKD", text)
    return "".join(c for c in base if not unicodedata.combining(c))


def _phrase_matches(phrase: str, text: str) -> bool:
    """Match whole words/phrases only (avoids 'ei' inside 'marseillais')."""
    de = _strip_accents(phrase.lower())
    hay = _strip_accents(text.lower())
    if " " in de or len(de) > 3:
        return de in hay
    return bool(re.search(rf"\b{re.escape(de)}\b", hay))


def translate_product_name(name: str) -> str:
    """Translate a Migros product name to a French ingredient label."""
    lower = _strip_accents(name.lower())

    for de, fr in sorted(PHRASES, key=lambda x: -len(x[0])):
        if _phrase_matches(de, lower):
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
