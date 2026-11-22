"""French ingredient → Migros search terms (often German on migros.ch)."""

import re

EXTRA_TERMS: dict[str, list[str]] = {
    "haricots": ["bohnen", "grüne bohnen", "grune bohnen"],
    "verts": ["grün", "grune", "extrafein"],
    "jambon": ["schinken", "vorderschinken"],
    "parmesan": ["emilio", "parmigiano", "grana"],
    "câpres": ["kapern"],
    "capres": ["kapern"],
    "oignon": ["zwiebel", "zwiebeln"],
    "oignons": ["zwiebel", "zwiebeln"],
    "ail": ["knoblauch", "knoblauchzehe", "garlic"],
    "gousses": ["knoblauch", "knoblauchzehe"],
    "tomate": ["tomaten", "passata", "tomatensauce"],
    "cerises": ["datteltomaten", "cherrytomaten", "cocktailtomaten"],
    "cerise": ["dattel", "cherry", "cocktail"],
    "pulpe": ["passata", "tomatenpüree", "tomatenpueree", "gehackte tomaten"],
    "carotte": ["karotte", "karotten", "migros bio"],
    "carottes": ["karotte", "karotten", "migros bio"],
    "toast": ["toast", "toastbrot"],
    "banane": ["banane", "bananen", "platanos"],
    "bananes": ["banane", "bananen", "platanos"],
    "riz": ["reis"],
    "oeufs": ["eier", "ei"],
    "oeuf": ["eier", "ei"],
    "cacahu": ["erdnuss", "erdnussbutter"],
    "terre": ["kartoffel", "kartoffeln"],
    "poivron": ["peperoni", "paprika"],
    "poivrons": ["peperoni", "paprika"],
    "soja": ["soja", "sojasauce"],
    "origan": ["oregano", "origano", "oregan"],
    "concombre": ["gurke", "gurken"],
    "roquette": ["rucola", "rukkola", "rocket"],
    "courgette": ["zucchetti", "zucchini"],
    "lardons": ["speck", "speckwürfel", "bacon"],
    "saucisse": ["bratwurst", "schweinsbratwurst", "saucisse", "saucisses"],
    "saucisses": ["bratwurst", "schweinsbratwurst", "saucisse"],
    "saumon": ["lachs", "salmon"],
    "crème": ["rahm", "creme"],
    "algue": ["nori", "algae"],
    "nori": ["nori"],
    "sésame": ["sesam", "sesame"],
    "avocat": ["avocado"],
    "farine": ["weissmehl", "mehl", "weizenmehl", "frione"],
    "blé": ["weizen", "weissmehl"],
}


def significant_tokens(name: str) -> list[str]:
    stop = {"de", "du", "la", "le", "les", "d", "et", "en", "feuilles", "frais", "fraîche", "pièce"}
    folded = name.lower().replace("œ", "oe").replace("æ", "ae")
    tokens = re.findall(r"[a-zàâäéèêëïîôùûüç]+", folded)
    return [t for t in tokens if len(t) > 2 and t not in stop]


def search_terms(ingredient_name: str) -> list[str]:
    tokens = significant_tokens(ingredient_name)
    terms: list[str] = []
    if tokens:
        terms.append(tokens[0])
        if len(tokens) > 1:
            terms.append(" ".join(tokens[:2]))
    terms.append(ingredient_name)
    for token in tokens:
        for key, extras in EXTRA_TERMS.items():
            if token == key or key in token:
                terms.extend(extras)
    low_name = ingredient_name.lower()
    if "lait de riz" in low_name or "boisson de riz" in low_name or "boisson au riz" in low_name:
        terms.extend(["reisdrink", "reismilch", "rice drink"])
    if "chou-fleur" in low_name or "choufleur" in low_name or "chou fleur" in low_name:
        terms.extend(["blumenkohl", "chou-fleur"])
    if "edamame" in low_name:
        terms.extend(["edamame"])
    if "brocoli" in low_name:
        terms.extend(["brokkoli", "broccoli"])
    if any(token in low_name for token in ("rösti", "rosti", "röschti")):
        terms.extend(["rösti", "rosti"])
    if "poulet entier" in low_name:
        terms.extend(["poulet ganz", "ganz"])
    if "saumon fum" in low_name:
        terms.extend(["rauchlachs"])

    # unique, preserve order
    seen: set[str] = set()
    out: list[str] = []
    for t in terms:
        low = t.lower()
        if low not in seen:
            seen.add(low)
            out.append(t)
    return out
