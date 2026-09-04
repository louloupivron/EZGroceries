"""Persist validated product choices and rejected UIDs per ingredient."""

import json
import re
import unicodedata
from pathlib import Path

from comida.matcher import _significant_tokens

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "mappings.json"


def normalize_key(ingredient_name: str) -> str:
    tokens = _significant_tokens(ingredient_name)
    if not tokens:
        base = ingredient_name.lower().strip()
    else:
        base = "-".join(tokens)
    base = unicodedata.normalize("NFKD", base)
    base = "".join(c for c in base if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9-]+", "", base)


def load_mappings(path: Path = DEFAULT_PATH) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_mappings(data: dict, path: Path = DEFAULT_PATH) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def get_entry(mappings: dict, ingredient_name: str) -> dict:
    key = normalize_key(ingredient_name)
    return mappings.get(key, {
        "ingredient_label": ingredient_name,
        "accepted_uid": None,
        "backup_uid": None,
        "rejected_uids": [],
    })


def record_acceptance(
    ingredient_name: str,
    accepted_uid: int,
    backup_uid: int | None,
    path: Path = DEFAULT_PATH,
) -> None:
    mappings = load_mappings(path)
    key = normalize_key(ingredient_name)
    entry = get_entry(mappings, ingredient_name)
    entry["ingredient_label"] = ingredient_name
    entry["accepted_uid"] = accepted_uid
    entry["backup_uid"] = backup_uid
    rejected = set(entry.get("rejected_uids", []))
    rejected.discard(accepted_uid)
    if backup_uid:
        rejected.discard(backup_uid)
    entry["rejected_uids"] = sorted(rejected)
    mappings[key] = entry
    save_mappings(mappings, path)


def record_rejection(ingredient_name: str, rejected_uid: int, path: Path = DEFAULT_PATH) -> None:
    mappings = load_mappings(path)
    key = normalize_key(ingredient_name)
    entry = get_entry(mappings, ingredient_name)
    entry["ingredient_label"] = ingredient_name
    rejected = set(entry.get("rejected_uids", []))
    rejected.add(rejected_uid)
    if entry.get("accepted_uid") == rejected_uid:
        entry["accepted_uid"] = None
    if entry.get("backup_uid") == rejected_uid:
        entry["backup_uid"] = None
    entry["rejected_uids"] = sorted(rejected)
    mappings[key] = entry
    save_mappings(mappings, path)


def filter_rejected_uids(options: list[dict], rejected: list[int]) -> list[dict]:
    blocked = set(rejected)
    return [o for o in options if o.get("uid") not in blocked]
