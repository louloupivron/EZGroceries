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
    {"id": "kookd", "label": "Kookd", "short": "1"},
    {"id": "pantry", "label": "Garde-manger", "short": "2"},
    {"id": "week", "label": "Analyse", "short": "3"},
    {"id": "validate", "label": "Validation", "short": "4"},
    {"id": "weekly", "label": "Hebdo", "short": "5"},
    {"id": "push", "label": "Push", "short": "6"},
    {"id": "checkout", "label": "Checkout", "short": "7"},
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


def _drop_session_file() -> None:
    if SESSION_PATH.exists():
        SESSION_PATH.unlink()


def reset_week_session() -> None:
    """Drop the previous week's matches so a new export starts from a clean list."""
    _drop_session_file()
    state = load_ui_state()
    state["pantry_done_for"] = ""
    state["weekly_done_for"] = ""
    state["analysis_stale"] = True
    state.pop("last_push", None)
    save_ui_state(state)


def discard_other_week_session() -> bool:
    """Delete a validation session that belongs to another Kookd export.

    The pantry check for the new export is kept.
    """
    if not SESSION_PATH.exists():
        return False
    try:
        session = json.loads(SESSION_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    recipe = Path(str(session.get("recipe") or "")).name
    active = Path(str(load_ui_state().get("recipe_export") or "")).name
    if not active or not recipe or recipe == active:
        return False
    _drop_session_file()
    state = load_ui_state()
    state["weekly_done_for"] = ""
    state["analysis_stale"] = True
    state.pop("last_push", None)
    save_ui_state(state)
    return True


def stale_week_reason(session: dict | None) -> str | None:
    """Why this session must not be pushed, if it must not."""
    ui = load_ui_state()
    active = Path(str(ui.get("recipe_export") or "")).name
    if not session:
        if active:
            return f"Aucune liste pour {active}. Lance l'analyse."
        return "Aucune liste analysée."
    recipe = Path(str(session.get("recipe") or "")).name
    if active and recipe and active != recipe:
        return f"La liste affichée est encore {recipe}. Lance l'analyse de {active}."
    if ui.get("analysis_stale"):
        return "L'analyse n'est plus à jour. Relance-la avant le push."
    return None


def set_kookd_done(done: bool = True) -> dict:
    if done:
        reset_week_session()
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


def compute_workflow(session: dict | None) -> dict:
    ui = load_ui_state()
    recipe_files = _recipe_exports()

    kookd_done = bool(ui.get("kookd_done")) or bool(recipe_files)
    recipe_name = ui.get("recipe_export") or (recipe_files[-1].name if recipe_files else None)
    if recipe_name:
        recipe_name = Path(str(recipe_name)).name
    session_name = None
    if session and session.get("recipe"):
        session_name = Path(str(session["recipe"])).name
    pantry_done = bool(recipe_name) and ui.get("pantry_done_for") == recipe_name
    has_session = bool(session and session.get("resolved"))
    needs_fav = len(session.get("needs_favorite", [])) if session else 0
    pending = sum(
        1 for p in session.get("pending", []) if p.get("status") == "pending"
    ) if session else 0
    manual = sum(
        1 for u in session.get("unmatched", []) if u.get("status") == "manual"
    ) if session else 0
    resolved_count = len(session.get("resolved", [])) if session else 0

    week_done = (
        pantry_done
        and has_session
        and resolved_count > 0
        and not ui.get("analysis_stale")
    )
    validate_done = week_done and needs_fav == 0 and pending == 0 and manual == 0 and resolved_count > 0
    weekly_done = validate_done and bool(session_name) and ui.get("weekly_done_for") == session_name

    last_push = ui.get("last_push") or {}
    push_done = weekly_done and bool(last_push.get("at")) and last_push.get("checkout", {}).get("ok")
    checkout_done = push_done and bool(last_push.get("checkout", {}).get("checkoutUrl"))

    flags = {
        "kookd": kookd_done,
        "pantry": pantry_done,
        "week": week_done,
        "validate": validate_done,
        "weekly": weekly_done,
        "push": push_done,
        "checkout": checkout_done,
    }

    current_id = "kookd"
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
            "last_push": last_push,
            "portions": ui.get("portions"),
            "base_portions": ui.get("base_portions"),
            "recipe_export": ui.get("recipe_export"),
            "pantry_done_for": ui.get("pantry_done_for") or "",
            "weekly_done_for": ui.get("weekly_done_for") or "",
            "analysis_stale": bool(ui.get("analysis_stale")),
        },
    }
