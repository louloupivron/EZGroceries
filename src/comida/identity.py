"""Ingredient identity: a product must name the same food before any fuzzy score."""

from __future__ import annotations

import re

from comida.synonyms import EXTRA_TERMS, significant_tokens


def head_token(ingredient_name: str) -> str | None:
    """French head noun: the first significant token (tortillas de blé → tortillas)."""
    tokens = significant_tokens(ingredient_name)
    return tokens[0] if tokens else None


def identity_terms(ingredient_name: str) -> list[str]:
    """Whole-word terms that mean this ingredient, including same-food translations."""
    token = head_token(ingredient_name)
    if not token:
        return []
    terms = [token]
    for key, extras in EXTRA_TERMS.items():
        if token == key or token.startswith(key):
            terms.extend(extras)
    seen: set[str] = set()
    out: list[str] = []
    for term in terms:
        low = term.lower()
        if low and low not in seen:
            seen.add(low)
            out.append(low)
    return out


def text_has_identity(ingredient_name: str, text: str) -> bool:
    """True when the display text contains an identity term as a whole word."""
    if not text:
        return False
    folded = text.lower()
    for term in identity_terms(ingredient_name):
        if re.search(rf"(?<!\w){re.escape(term)}(?!\w)", folded):
            return True
    return False
