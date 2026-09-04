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


def get_basket() -> dict:
    return _run_basket("basket")


def get_basket_for_list(
    *,
    list_name: str | None = None,
    list_id: int | None = None,
) -> dict:
    """Fetch basket for a specific Migros list (overrides .env for this call)."""
    _load_dotenv()
    env = os.environ.copy()
    if list_id is not None:
        env["MIGROS_SHOPPING_LIST_ID"] = str(list_id)
        env.pop("MIGROS_SHOPPING_LIST_NAME", None)
    elif list_name:
        env["MIGROS_SHOPPING_LIST_NAME"] = list_name
        env.pop("MIGROS_SHOPPING_LIST_ID", None)
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


def push_items(items: list[dict]) -> dict:
    """Each item: uid, quantity (default 1), ingredient_name optional."""
    return _run_basket("push", items=json.dumps(items))


def resolved_to_basket_items(resolved: list[dict], default_quantity: int = 1) -> list[dict]:
    out: list[dict] = []
    for r in resolved:
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
    return out

