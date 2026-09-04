"""French ingredient → Migros search terms (often German on migros.ch)."""

from comida.matcher import _significant_tokens

EXTRA_TERMS: dict[str, list[str]] = {
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


def search_terms(ingredient_name: str) -> list[str]:
    tokens = _significant_tokens(ingredient_name)
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
