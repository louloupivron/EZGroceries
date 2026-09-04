"""Subprocess client for scripts/migros.mjs."""

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIGROS_SCRIPT = ROOT / "scripts" / "migros.mjs"


def _run(cmd: str, **kwargs: str) -> dict | list:
    args = ["node", str(MIGROS_SCRIPT), cmd]
    for key, val in kwargs.items():
        args.extend([f"--{key}", str(val)])
    proc = subprocess.run(args, capture_output=True, text=True, cwd=ROOT, check=False)
    if proc.returncode != 0:
        err = proc.stderr.strip() or proc.stdout.strip()
        try:
            payload = json.loads(err)
            raise RuntimeError(payload.get("error", err))
        except json.JSONDecodeError:
            raise RuntimeError(err)
    return json.loads(proc.stdout)


def fetch_all_promotion_ids(chunk_size: int = 100) -> list[int]:
    first = _run("promotions", **{"from": "0", "until": str(chunk_size)})
    total = first["numberOfItems"]
    ids = [item["id"] for item in first["items"]]
    start = chunk_size
    while start < total:
        batch = _run("promotions", **{"from": str(start), "until": str(start + chunk_size)})
        ids.extend(item["id"] for item in batch["items"])
        start += chunk_size
    return ids


def fetch_product_details(product_ids: list[int], batch_size: int = 40) -> list[dict]:
    products: list[dict] = []
    for i in range(0, len(product_ids), batch_size):
        chunk = product_ids[i : i + batch_size]
        data = _run("details", ids=",".join(map(str, chunk)))
        if isinstance(data, list):
            products.extend(data)
    return products


def search_products(query: str, size: int = 8) -> list[dict]:
    data = _run("search", query=query, size=str(size))
    return data.get("products", [])

