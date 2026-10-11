"""Read/write Comida UI settings (portions + text config files)."""

from __future__ import annotations

import os
import re
from pathlib import Path

from comida.basket import configured_list_slug, default_list_name, shared_list_url
from comida.quantities import DEFAULT_PORTIONS
from comida.ui.workflow import EXPORTS_DIR, load_ui_state, save_ui_state

ROOT = Path(__file__).resolve().parents[3]
ENV_PATH = ROOT / ".env"
PANTRY_PATH = ROOT / "garde-manger.txt"
WEEKLY_PATH = ROOT / "courses-hebdo.txt"
LIST_SLUG_KEY = "MIGROS_LIST_SLUG"


def _recipe_exports() -> list[str]:
    if not EXPORTS_DIR.is_dir():
        return []
    return sorted(
        p.name for p in EXPORTS_DIR.glob("*.txt")
        if not p.name.startswith("promos-")
    )


def parse_list_slug(url_or_slug: str) -> str:
    """Extract slug from a Migros list URL or accept a bare slug."""
    value = (url_or_slug or "").strip()
    if not value:
        return ""
    match = re.search(r"migros\.ch/list/([^/?#\s]+)", value, re.IGNORECASE)
    if match:
        return match.group(1)
    if "/" in value or " " in value:
        raise ValueError("URL invalide — attendu https://www.migros.ch/list/xxxxx ou le slug seul")
    return value


def _update_env_var(key: str, value: str) -> None:
    lines: list[str] = []
    if ENV_PATH.exists():
        lines = ENV_PATH.read_text(encoding="utf-8").splitlines()

    new_lines: list[str] = []
    found = False
    prefix = f"{key}="
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(prefix) or stripped.startswith(f"# {prefix}"):
            if value:
                new_lines.append(f"{key}={value}")
            found = True
        else:
            new_lines.append(line)

    if not found and value:
        if new_lines and new_lines[-1].strip():
            new_lines.append("")
        new_lines.append(f"{key}={value}")

    ENV_PATH.write_text(
        "\n".join(new_lines) + ("\n" if new_lines else ""),
        encoding="utf-8",
    )
    if value:
        os.environ[key] = value
    else:
        os.environ.pop(key, None)


def save_list_url(url_or_slug: str | None) -> str:
    slug = parse_list_slug(url_or_slug or "")
    _update_env_var(LIST_SLUG_KEY, slug)
    return slug


def get_preferences() -> dict:
    ui = load_ui_state()
    exports = _recipe_exports()
    default_recipe = ui.get("recipe_export") or (exports[-1] if exports else "semaine.txt")
    return {
        "portions": int(ui.get("portions", DEFAULT_PORTIONS)),
        "base_portions": int(ui.get("base_portions", DEFAULT_PORTIONS)),
        "recipe_export": default_recipe,
        "list_name": default_list_name(),
        "list_slug": configured_list_slug() or "",
        "list_url": shared_list_url() or "",
        "recipe_exports": exports,
    }


def save_preferences(
    *,
    portions: int | None = None,
    base_portions: int | None = None,
    recipe_export: str | None = None,
    list_url: str | None = None,
) -> dict:
    ui = load_ui_state()
    if portions is not None:
        if not 1 <= portions <= 24:
            raise ValueError("portions doit être entre 1 et 24")
        ui["portions"] = portions
    if base_portions is not None:
        if not 1 <= base_portions <= 24:
            raise ValueError("base_portions doit être entre 1 et 24")
        ui["base_portions"] = base_portions
    if recipe_export is not None:
        name = Path(recipe_export).name
        if name.startswith("promos-") or "/" in recipe_export or "\\" in recipe_export:
            raise ValueError("Export recette invalide")
        path = EXPORTS_DIR / name
        if not path.exists():
            raise ValueError(f"Fichier introuvable : exports/{name}")
        if ui.get("recipe_export") != name:
            ui["pantry_done_for"] = ""
            ui["weekly_done_for"] = ""
            ui["analysis_stale"] = True
        ui["recipe_export"] = name
    save_ui_state(ui)
    if list_url is not None:
        save_list_url(list_url)
    return get_preferences()


def read_config_files() -> dict:
    prefs = get_preferences()
    return {
        **prefs,
        "pantry_text": PANTRY_PATH.read_text(encoding="utf-8") if PANTRY_PATH.exists() else "",
        "weekly_text": WEEKLY_PATH.read_text(encoding="utf-8") if WEEKLY_PATH.exists() else "",
        "pantry_path": "garde-manger.txt",
        "weekly_path": "courses-hebdo.txt",
    }


def save_config_files(
    *,
    pantry_text: str | None = None,
    weekly_text: str | None = None,
) -> dict:
    if pantry_text is not None:
        PANTRY_PATH.write_text(pantry_text, encoding="utf-8")
    if weekly_text is not None:
        WEEKLY_PATH.write_text(weekly_text, encoding="utf-8")
    return read_config_files()
