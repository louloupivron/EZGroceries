"""Push validated products to Migros Online shopping list."""

import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASKET_SCRIPT = ROOT / "scripts" / "migros-basket.mjs"


def _load_dotenv() -> None:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = val


DEFAULT_LIST_NAME = "les Avengers"


def default_list_name() -> str:
    _load_dotenv()
    return os.environ.get("MIGROS_SHOPPING_LIST_NAME", DEFAULT_LIST_NAME).strip() or DEFAULT_LIST_NAME


def configured_list_id() -> int | None:
    _load_dotenv()
    raw = os.environ.get("MIGROS_SHOPPING_LIST_ID", "").strip()
    return int(raw) if raw else None


def configured_list_slug() -> str | None:
    _load_dotenv()
    slug = os.environ.get("MIGROS_LIST_SLUG", "").strip()
    return slug or None


def shared_list_url() -> str | None:
    slug = configured_list_slug()
    return f"https://www.migros.ch/list/{slug}" if slug else None


def resolve_list_target(list_name: str | None = None) -> tuple[str | None, int | None]:
    """
    Resolve Migros list for API calls.
    When list_name matches MIGROS_SHOPPING_LIST_NAME, prefer MIGROS_SHOPPING_LIST_ID.
    """
    _load_dotenv()
    name = (list_name or default_list_name()).strip()
    env_name = os.environ.get("MIGROS_SHOPPING_LIST_NAME", "").strip()
    env_id = configured_list_id()
    if env_id and env_name and name.lower() == env_name.lower():
        return None, env_id
    return name, None


def _run_basket(cmd: str, **kwargs: str) -> dict:
    _load_dotenv()
    env = os.environ.copy()
    args = ["node", str(BASKET_SCRIPT), cmd]
    for key, val in kwargs.items():
        args.extend([f"--{key}", str(val)])
    proc = subprocess.run(args, capture_output=True, text=True, cwd=ROOT, check=False, env=env)
    if proc.returncode != 0:
        err = proc.stderr.strip() or proc.stdout.strip()
        try:
            payload = json.loads(err)
            raise RuntimeError(payload.get("error", err))
        except json.JSONDecodeError:
            raise RuntimeError(err)
    return json.loads(proc.stdout)


def list_shopping_lists() -> list:
    return _run_basket("lists")


def migros_profile() -> dict:
    """Logged-in Migros customer (cached session or fresh .env login)."""
    return _run_basket("profile")


def clear_migros_session() -> dict:
    """Remove migros-mcp session cache so the next call re-logs in via MIGROS_EMAIL."""
    return _run_basket("logout")


def get_basket() -> dict:
    return _run_basket("basket")


def _env_for_list(
    *,
    list_name: str | None = None,
    list_id: int | None = None,
) -> dict[str, str]:
    _load_dotenv()
    env = os.environ.copy()
    if list_id is not None:
        env["MIGROS_SHOPPING_LIST_ID"] = str(list_id)
        env.pop("MIGROS_SHOPPING_LIST_NAME", None)
    elif list_name:
        resolved_name, resolved_id = resolve_list_target(list_name)
        if resolved_id is not None:
            env["MIGROS_SHOPPING_LIST_ID"] = str(resolved_id)
            env["MIGROS_SHOPPING_LIST_NAME"] = ""
        else:
            env["MIGROS_SHOPPING_LIST_NAME"] = resolved_name or list_name
            # Empty string blocks migros-basket.mjs loadDotenv from re-injecting .env ID.
            env["MIGROS_SHOPPING_LIST_ID"] = ""
    return env


def get_basket_for_list(
    *,
    list_name: str | None = None,
    list_id: int | None = None,
) -> dict:
    """Fetch basket for a specific Migros list (overrides .env for this call)."""
    env = _env_for_list(list_name=list_name, list_id=list_id)
    args = ["node", str(BASKET_SCRIPT), "basket"]
    proc = subprocess.run(args, capture_output=True, text=True, cwd=ROOT, check=False, env=env)
    if proc.returncode != 0:
        err = proc.stderr.strip() or proc.stdout.strip()
        try:
            payload = json.loads(err)
            raise RuntimeError(payload.get("error", err))
        except json.JSONDecodeError:
            raise RuntimeError(err)
    return json.loads(proc.stdout)


def push_items(
    items: list[dict],
    *,
    list_name: str | None = None,
    list_id: int | None = None,
) -> dict:
    """Each item: uid, quantity (default 1), ingredient_name optional."""
    _load_dotenv()
    env = _env_for_list(list_name=list_name, list_id=list_id)
    args = ["node", str(BASKET_SCRIPT), "push", "--items", json.dumps(items)]
    proc = subprocess.run(args, capture_output=True, text=True, cwd=ROOT, check=False, env=env)
    if proc.returncode != 0:
        err = proc.stderr.strip() or proc.stdout.strip()
        try:
            payload = json.loads(err)
            raise RuntimeError(payload.get("error", err))
        except json.JSONDecodeError:
            raise RuntimeError(err)
    return json.loads(proc.stdout)


def merge_items_by_uid(items: list[dict]) -> list[dict]:
    """One target quantity per product. Later lines of the same uid are summed."""
    merged: dict[int, dict] = {}
    order: list[int] = []
    for item in items:
        uid = item.get("uid")
        if not uid:
            continue
        uid = int(uid)
        qty = int(item.get("quantity") or 1)
        if uid not in merged:
            merged[uid] = {**item, "uid": uid, "quantity": qty}
            order.append(uid)
        else:
            merged[uid]["quantity"] += qty
    return [merged[uid] for uid in order]


def resolved_to_basket_items(resolved: list[dict], default_quantity: int = 1) -> list[dict]:
    out: list[dict] = []
    for r in resolved:
        if r.get("quantity_confidence") == "revue":
            continue
        uid = r.get("uid")
        if not uid:
            continue
        qty = r.get("quantity_parsed", default_quantity)
        out.append(
            {
                "uid": uid,
                "quantity": qty,
                "ingredient_name": r.get("ingredient_name"),
                "name": r.get("name"),
            }
        )
    return merge_items_by_uid(out)


def record_pushed_quantities(session: dict, results: list[dict]) -> dict:
    """Remember the quantities last sent, which replace whatever was on the list."""
    session["pushed"] = [
        {
            "uid": r.get("productId") or r.get("uid"),
            "quantity": r.get("quantity"),
            "ingredient_name": r.get("ingredient") or r.get("ingredient_name"),
        }
        for r in results
        if r.get("ok", True) and (r.get("productId") or r.get("uid"))
    ]
    return session
