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
    "tomate": ["tomaten", "passata", "tomatensauce"],
    "carotte": ["karotte", "karotten", "migros bio"],
    "carottes": ["karotte", "karotten", "migros bio"],
    "toast": ["toast", "toastbrot"],
    "banane": ["banane", "bananen", "platanos"],
    "bananes": ["banane", "bananen", "platanos"],
    "riz": ["reis", "reismilch", "reisdrink"],
    "soja": ["soja", "sojasauce"],
    "origan": ["oregano", "origano", "oregan"],
    "concombre": ["gurke", "gurken"],
    "courgette": ["zucchetti", "zucchini"],
    "lardons": ["speck", "speckwürfel", "bacon"],
    "saumon": ["lachs", "salmon"],
    "crème": ["rahm", "creme"],
    "algue": ["nori", "algae"],
    "nori": ["nori"],
    "sésame": ["sesam", "sesame"],
    "avocat": ["avocado"],
}


def significant_tokens(name: str) -> list[str]:
    stop = {"de", "du", "la", "le", "les", "d", "et", "en", "feuilles", "frais", "fraîche", "pièce"}
    tokens = re.findall(r"[a-zàâäéèêëïîôùûüç]+", name.lower())
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
    # unique, preserve order
    seen: set[str] = set()
    out: list[str] = []
    for t in terms:
        low = t.lower()
        if low not in seen:
            seen.add(low)
            out.append(t)
    return out
