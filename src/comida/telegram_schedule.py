"""Scheduled Telegram messages for the weekly Migros → Kookd workflow."""

from __future__ import annotations

import json
import os
from datetime import date, datetime, timezone
from pathlib import Path

from comida.basket import _load_dotenv, default_list_name
from comida.telegram import TelegramConfig, send_message
from comida.ui.access import access_urls
from comida.week_list import (
    list_exists,
    list_item_count,
    list_link_hint,
    week_key,
    week_list_name_from_env,
)

ROOT = Path(__file__).resolve().parents[2]
STATE_PATH = ROOT / "data" / "telegram_schedule.json"
DEFAULT_PORT = 8765


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_schedule_state() -> dict:
    if not STATE_PATH.exists():
        return {}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_schedule_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def ui_port() -> int:
    _load_dotenv()
    raw = os.environ.get("COMIDA_PORT", "").strip()
    return int(raw) if raw else DEFAULT_PORT


def current_week_list_name(state: dict | None = None) -> str:
    """Stable shopping list for the week. Does not allocate a new S{n}."""
    state = state if state is not None else load_schedule_state()
    key = week_key()
    list_name = week_list_name_from_env() or default_list_name()
    changed_week = state.get("week_key") != key
    if changed_week or state.get("list_name") != list_name:
        if changed_week:
            state["messages_sent"] = {}
            state["week_key"] = key
        state["list_name"] = list_name
        save_schedule_state(state)
    return list_name


def _already_sent(step: str, state: dict) -> bool:
    key = week_key()
    if state.get("week_key") != key:
        return False
    return bool(state.get("messages_sent", {}).get(step))


def _mark_sent(step: str, state: dict) -> None:
    state.setdefault("messages_sent", {})[step] = _now_iso()
    save_schedule_state(state)


def _tailscale_url(port: int) -> str | None:
    for entry in access_urls(port):
        if entry.get("label") == "tailscale":
            return entry["url"]
    return None


def _send(text: str, *, force: bool = False, step: str | None = None) -> dict:
    cfg = TelegramConfig.from_env()
    state = load_schedule_state()
    if step and not force and _already_sent(step, state):
        return {"skipped": True, "reason": f"déjà envoyé ({step}) pour {state.get('week_key')}"}
    result = send_message(text, config=cfg)
    if step:
        current_week_list_name(state)
        _mark_sent(step, state)
    return result


def send_thursday_morning(*, force: bool = False) -> dict:
    """
    Jeudi matin — nouvelles promos Migros : annoncer la liste de la semaine.
    """
    state = load_schedule_state()
    list_name = current_week_list_name(state)
    exists = list_exists(list_name)
    count = list_item_count(list_name) if exists else 0

    lines = [
        "🛒 Promos Migros",
        "",
        f"Liste cible : {list_name}",
    ]
    if exists:
        lines.append(f"✓ Liste trouvée sur Migros ({count} article(s) pour l'instant).")
    else:
        lines.append(
            f"Créez la liste « {list_name} » sur Migros Online, "
            "puis ajoutez les promos du jeudi."
        )
    lines.extend([
        "",
        list_link_hint(list_name),
    ])
    return _send("\n".join(lines), force=force, step="thu_am")


def send_thursday_evening(*, force: bool = False) -> dict:
    """Jeudi soir — rappel uniquement si la liste est encore vide."""
    state = load_schedule_state()
    list_name = current_week_list_name(state)
    count = list_item_count(list_name)

    if count > 0:
        if not force and _already_sent("thu_pm", state):
            return {"skipped": True, "reason": f"déjà envoyé (thu_pm) pour {state.get('week_key')}"}
        current_week_list_name(state)
        _mark_sent("thu_pm", state)
        return {
            "skipped": True,
            "reason": f"liste {list_name} déjà remplie ({count} article(s)) — pas de message",
        }

    text = "\n".join([
        f"⏰ Rappel — liste {list_name}",
        "",
        "Aucun article ajouté pour l'instant.",
        "Ajoutez les promos Migros du jeudi sur la liste avant demain matin.",
        "",
        list_link_hint(list_name),
    ])
    return _send(text, force=force, step="thu_pm")


def send_friday_morning(*, force: bool = False) -> dict:
    """
    Vendredi matin — rappel export Kookd + analyse Comida.
    """
    state = load_schedule_state()
    list_name = current_week_list_name(state)
    port = ui_port()
    ts_url = _tailscale_url(port)
    cmd = f'uv run python main.py week exports/semaine.txt --list "{list_name}"'

    lines = [
        "📋 Semaine — courses Comida",
        "",
        "1. Exportez vos recettes depuis Kookd → exports/semaine.txt",
        "2. Lancez l’analyse (matching + validation) :",
        "",
        f"`{cmd}`",
    ]
    if ts_url:
        lines.extend([
            "",
            "★ Interface Comida (Tailscale) :",
            f"{ts_url}",
            "→ étape « Analyse »",
            "",
            "Le Mac doit être allumé et connecté à Tailscale.",
        ])
    else:
        lines.extend([
            "",
            "Ou lancez la commande sur le Mac (Tailscale non détecté).",
        ])
    return _send("\n".join(lines), force=force, step="fri_am")


_KOOKD_FOOTER = (
    "Tu peux maintenant utiliser ces ingrédients dans Kookd pour générer tes meilleures recettes "
    "— à faire avant samedi midi !"
)


def send_kookd_instructions(
    file_path: Path,
    list_name: str,
    *,
    force: bool = False,
) -> dict:
    """Après export promos — un seul message : liste filtrée + consigne Kookd."""
    state = load_schedule_state()
    if not force and _already_sent("promos_export", state):
        return {"skipped": True, "reason": "export déjà notifié cette semaine"}

    cfg = TelegramConfig.from_env()
    content = file_path.read_text(encoding="utf-8").strip()
    text = f"{content}\n\n{_KOOKD_FOOTER}"
    if len(text) > 4000:
        send_message(content, config=cfg)
        send_message(_KOOKD_FOOTER, config=cfg)
    else:
        send_message(text, config=cfg)
    current_week_list_name(state)
    _mark_sent("promos_export", state)
    return {"ok": True}


def send_after_promos_export(file_path: Path, list_name: str) -> bool:
    """Hook after promos export — respects TELEGRAM_AUTO_SEND / schedule."""
    _load_dotenv()
    auto = os.environ.get("TELEGRAM_AUTO_SEND", "").strip().lower() in ("1", "true", "yes")
    schedule = os.environ.get("TELEGRAM_SCHEDULE_KOOKD", "true").strip().lower() in ("1", "true", "yes")
    if not auto and not schedule:
        return False
    try:
        send_kookd_instructions(file_path, list_name)
        return True
    except RuntimeError:
        return False


def run_scheduled_step(step: str | None = None, *, force: bool = False) -> dict:
    """Run one schedule step or auto-detect from weekday/time."""
    if step:
        step = step.strip().lower()
        if step in ("thu-am", "thu_am", "jeudi-matin"):
            return send_thursday_morning(force=force)
        if step in ("thu-pm", "thu_pm", "jeudi-soir"):
            return send_thursday_evening(force=force)
        if step in ("fri-am", "fri_am", "vendredi-matin"):
            return send_friday_morning(force=force)
        raise ValueError(f"Étape inconnue : {step}")

    today = date.today()
    hour = datetime.now().hour
    weekday = today.weekday()  # Mon=0 … Sun=6
    if weekday == 3 and hour < 14:
        return send_thursday_morning(force=force)
    if weekday == 3 and hour >= 18:
        return send_thursday_evening(force=force)
    if weekday == 4 and hour < 14:
        return send_friday_morning(force=force)
    return {"skipped": True, "reason": "hors créneau (jeu matin / jeu soir / ven matin)"}

