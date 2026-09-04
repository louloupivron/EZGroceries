"""Local cache for Migros weekly promotions (~24h TTL)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from comida.migros_client import fetch_all_promotion_ids, fetch_product_details

ROOT = Path(__file__).resolve().parents[2]
CACHE_PATH = ROOT / "data" / "promo_cache.json"
DEFAULT_TTL_HOURS = 24


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def load_cache(path: Path = CACHE_PATH) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def save_cache(promo_ids: list[int], products: list[dict], path: Path = CACHE_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "fetched_at": _utc_now().isoformat(),
        "promo_ids": promo_ids,
        "products": products,
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def cache_is_fresh(cache: dict | None, ttl_hours: int = DEFAULT_TTL_HOURS) -> bool:
    if not cache or "fetched_at" not in cache:
        return False
    fetched = _parse_iso(cache["fetched_at"])
    age_hours = (_utc_now() - fetched).total_seconds() / 3600
    return age_hours < ttl_hours


def fetch_promotions_cached(
    *,
    force_refresh: bool = False,
    max_promo_products: int = 1224,
    ttl_hours: int = DEFAULT_TTL_HOURS,
    cache_path: Path = CACHE_PATH,
) -> tuple[list[int], list[dict], dict]:
    """
    Return (all_promo_ids, sampled_promo_products, meta).
    meta keys: from_cache, fetched_at, promotions_total, promotions_indexed
    """
    cache = load_cache(cache_path)
    if not force_refresh and cache_is_fresh(cache, ttl_hours):
        promo_ids = [int(x) for x in cache.get("promo_ids", [])]
        products = cache.get("products", [])
        return promo_ids, products, {
            "from_cache": True,
            "fetched_at": cache.get("fetched_at"),
            "promotions_total": len(promo_ids),
            "promotions_indexed": len(products),
        }

    promo_ids = fetch_all_promotion_ids()
    sample_ids = promo_ids[:max_promo_products]
    products = fetch_product_details(sample_ids)
    fetched_at = _utc_now().isoformat()
    save_cache(promo_ids, products, cache_path)

    return promo_ids, products, {
        "from_cache": False,
        "fetched_at": fetched_at,
        "promotions_total": len(promo_ids),
        "promotions_indexed": len(products),
    }
