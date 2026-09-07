"""Workflow stepper state for the Comida UI."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
EXPORTS_DIR = ROOT / "exports"
UI_STATE_PATH = ROOT / "data" / "ui_state.json"
SESSION_PATH = ROOT / "data" / "validation_session.json"

STEPS = (
    {"id": "promos", "label": "Promos", "short": "1"},
    {"id": "kookd", "label": "Kookd", "short": "2"},
    {"id": "week", "label": "Analyse", "short": "3"},
    {"id": "validate", "label": "Favoris", "short": "4"},
    {"id": "push", "label": "Push", "short": "5"},
    {"id": "checkout", "label": "Checkout", "short": "6"},
)


def load_ui_state() -> dict:
    if not UI_STATE_PATH.exists():
        return {}
    try:
        return json.loads(UI_STATE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_ui_state(state: dict) -> None:
    UI_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    UI_STATE_PATH.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def set_kookd_done(done: bool = True) -> dict:
    state = load_ui_state()
    state["kookd_done"] = done
    state["kookd_done_at"] = datetime.now(timezone.utc).isoformat()
    save_ui_state(state)
    return state


def record_push_result(result: dict) -> dict:
    state = load_ui_state()
    checkout = result.get("checkout") or {}
    state["last_push"] = {
        "at": datetime.now(timezone.utc).isoformat(),
        "shopping_list_id": result.get("shoppingListId"),
        "checkout": checkout,
        "pushed_count": len([r for r in result.get("results", []) if r.get("ok")]),
    }
    save_ui_state(state)
    return state


def _recipe_exports() -> list[Path]:
    if not EXPORTS_DIR.is_dir():
        return []
    return sorted(
        p for p in EXPORTS_DIR.glob("*.txt")
        if not p.name.startswith("promos-")
    )


def _promo_exports() -> list[Path]:
    if not EXPORTS_DIR.is_dir():
        return []
    return sorted(EXPORTS_DIR.glob("promos-*.txt"))


def compute_workflow(session: dict | None) -> dict:
    ui = load_ui_state()
    promos_files = _promo_exports()
    recipe_files = _recipe_exports()

    promos_done = bool(promos_files)
    kookd_done = bool(ui.get("kookd_done")) or bool(recipe_files)
    has_session = bool(session and session.get("resolved"))
    needs_fav = len(session.get("needs_favorite", [])) if session else 0
    pending = sum(
        1 for p in session.get("pending", []) if p.get("status") == "pending"
    ) if session else 0
    manual = sum(
        1 for u in session.get("unmatched", []) if u.get("status") == "manual"
    ) if session else 0
    resolved_count = len(session.get("resolved", [])) if session else 0

    validate_done = has_session and needs_fav == 0 and pending == 0 and manual == 0 and resolved_count > 0
    week_done = has_session and resolved_count > 0

    last_push = ui.get("last_push") or {}
    push_done = bool(last_push.get("at")) and last_push.get("checkout", {}).get("ok")
    checkout_done = push_done and bool(last_push.get("checkout", {}).get("checkoutUrl"))

    flags = {
        "promos": promos_done,
        "kookd": kookd_done,
        "week": week_done,
        "validate": validate_done,
        "push": push_done,
        "checkout": checkout_done,
    }

    current_id = "promos"
    for step in STEPS:
        if not flags[step["id"]]:
            current_id = step["id"]
            break
    else:
        current_id = "checkout"

    steps_out = []
    for step in STEPS:
        sid = step["id"]
        if flags[sid]:
            status = "done"
        elif sid == current_id:
            status = "current"
        else:
            status = "upcoming"
        steps_out.append({**step, "status": status, "done": flags[sid]})

    return {
        "current_step": current_id,
        "steps": steps_out,
        "ui_state": {
            "kookd_done": bool(ui.get("kookd_done")),
            "recipe_exports": [p.name for p in recipe_files],
            "promo_exports": [p.name for p in promos_files],
            "last_push": last_push,
            "portions": ui.get("portions"),
            "base_portions": ui.get("base_portions"),
            "recipe_export": ui.get("recipe_export"),
        },
    }
