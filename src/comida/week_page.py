"""Generate a mobile-friendly static page for the weekly basket (GitHub Pages)."""

from __future__ import annotations

import html
from datetime import datetime, timezone
from pathlib import Path

from comida.basket import shared_list_url
from comida.budget import estimate_basket
from comida.ui.workflow import load_ui_state
from comida.validation import MIGROS_MY_PRODUCTS_URL, load_session

ROOT = Path(__file__).resolve().parents[2]
DOCS_DIR = ROOT / "docs"
DEFAULT_OUTPUT = DOCS_DIR / "index.html"
CHECKOUT_URL = "https://www.migros.ch/fr?context=ecommerce"


def _esc(value: object) -> str:
    return html.escape(str(value) if value is not None else "", quote=True)


def _recipe_label(session: dict) -> str:
    recipe = session.get("recipe") or "Semaine"
    return Path(recipe).stem if "/" in recipe or "\\" in recipe else recipe


def _format_chf(amount: float | None) -> str:
    if amount is None:
        return "—"
    return f"{amount:.2f} CHF"


def generate_week_page(
    session: dict | None = None,
    *,
    output: Path | None = None,
) -> Path:
    """Write docs/index.html from the current validation session."""
    session = session or load_session()
    ui = load_ui_state()
    out = output or DEFAULT_OUTPUT
    out.parent.mkdir(parents=True, exist_ok=True)
    (DOCS_DIR / ".nojekyll").touch(exist_ok=True)

    resolved = session.get("resolved", [])
    needs_favorite = session.get("needs_favorite", [])
    pending = [p for p in session.get("pending", []) if p.get("status") == "pending"]
    pantry = session.get("pantry_skipped", [])
    budget = estimate_basket(resolved) if resolved else None
    last_push = ui.get("last_push") or {}
    checkout = last_push.get("checkout") or {}
    list_url = shared_list_url()
    generated = datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M UTC")

    checkout_total = ""
    checkout_btn = ""
    if checkout.get("ok"):
        total = checkout.get("onlineTotal")
        checkout_total = f'<div class="hero-total">{_esc(_format_chf(total))}</div>'
        checkout_total += f'<div class="hero-sub">{checkout.get("itemCount", "?")} article(s) sur Migros Online</div>'
        checkout_btn = (
            f'<a class="btn btn-primary" href="{_esc(CHECKOUT_URL)}" rel="noopener">'
            "Checkout Migros →</a>"
        )
    elif resolved:
        est = budget.get("estimated_total_chf") if budget else None
        checkout_total = f'<div class="hero-total">~{_esc(_format_chf(est))}</div>'
        checkout_total += '<div class="hero-sub">Estimation locale (avant push)</div>'

    items_html = ""
    for item in resolved:
        promo = '<span class="tag promo">Promo</span>' if item.get("on_promotion") else ""
        qty = item.get("quantity_parsed", 1)
        qty_label = f" × {qty}" if qty and qty > 1 else ""
        price = _format_chf(item.get("price_chf"))
        items_html += f"""
        <li class="item">
          <div class="item-main">
            <strong>{_esc(item.get("ingredient_name"))}</strong>{promo}
            <div class="muted">{_esc(item.get("name"))}{qty_label} · {price}</div>
          </div>
        </li>"""

    needs_html = ""
    if needs_favorite:
        needs_html = '<section><h2>Favoris manquants</h2><ul class="warn-list">'
        for item in needs_favorite:
            needs_html += f'<li>{_esc(item.get("ingredient_name"))} <span class="muted">{_esc(item.get("quantity", ""))}</span></li>'
        needs_html += f'</ul><p><a href="{_esc(MIGROS_MY_PRODUCTS_URL)}">Mes produits Migros</a></p></section>'

    pending_html = ""
    if pending:
        pending_html = '<section><h2>Promos à valider</h2><ul class="warn-list">'
        for item in pending:
            pending_html += f'<li>{_esc(item.get("ingredient_name"))}</li>'
        pending_html += "</ul></section>"

    pantry_html = ""
    if pantry:
        pantry_html = '<section><h2>Garde-manger</h2><ul class="muted-list">'
        for raw, rule in pantry:
            pantry_html += f"<li>{_esc(raw)} → {_esc(rule)}</li>"
        pantry_html += "</ul></section>"

    links_html = ""
    if list_url:
        links_html += f'<a class="btn btn-secondary" href="{_esc(list_url)}">Liste S1</a> '
    links_html += f'<a class="btn btn-secondary" href="{_esc(MIGROS_MY_PRODUCTS_URL)}">Favoris</a>'

    budget_html = ""
    if budget and budget.get("estimated_total_chf") is not None:
        gap = budget.get("delivery_gap_chf", 0)
        gap_line = (
            f'<p class="warn">Minimum livraison : il manque ~{gap:.2f} CHF</p>'
            if gap and gap > 0
            else f"<p class=\"ok\">Minimum livraison ({budget.get('min_delivery_chf')} CHF) : OK</p>"
        )
        budget_html = f"""
        <section class="budget">
          <strong>~{budget["estimated_total_chf"]:.2f} CHF</strong>
          <span class="muted"> ({budget.get("priced_count")}/{budget.get("item_count")} prix)</span>
          {gap_line}
        </section>"""

    status = "Prêt" if not needs_favorite and not pending else "Action requise"
    if last_push.get("at"):
        status = "Poussé sur Migros"

    page = f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <meta name="apple-mobile-web-app-capable" content="yes">
  <title>Comida — {_esc(_recipe_label(session))}</title>
  <style>
    :root {{
      --bg: #f6f4f0; --card: #fff; --text: #1a1a1a; --muted: #6b6560;
      --accent: #e85d04; --green: #2d6a4f; --green-bg: #d8f3dc;
      --promo: #9d0208; --promo-bg: #ffe5e5; --border: #e8e4de;
      --radius: 12px; --safe-bottom: env(safe-area-inset-bottom, 0px);
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: var(--bg); color: var(--text); line-height: 1.5;
      padding: 1rem 1rem calc(1.5rem + var(--safe-bottom));
      max-width: 480px; margin: 0 auto;
    }}
    header {{ margin-bottom: 1rem; }}
    h1 {{ font-size: 1.25rem; }}
    .meta {{ color: var(--muted); font-size: .85rem; margin-top: .25rem; }}
    .status {{
      display: inline-block; margin-top: .5rem; font-size: .75rem; font-weight: 600;
      padding: .2rem .5rem; border-radius: 6px; background: var(--green-bg); color: var(--green);
    }}
    .status.warn {{ background: #fff3cd; color: #856404; }}
    .hero {{
      background: var(--green); color: #fff; border-radius: var(--radius);
      padding: 1.25rem; text-align: center; margin-bottom: 1rem;
    }}
    .hero-total {{ font-size: 2rem; font-weight: 700; }}
    .hero-sub {{ opacity: .9; font-size: .875rem; margin-top: .25rem; }}
    .btn {{
      display: inline-block; margin: .75rem .25rem 0; padding: .65rem 1rem;
      border-radius: 10px; font-weight: 600; text-decoration: none; font-size: .9rem;
    }}
    .btn-primary {{ background: #fff; color: var(--green); }}
    .btn-secondary {{ background: var(--card); color: var(--text); border: 1px solid var(--border); }}
    section {{ margin-bottom: 1.25rem; }}
    section h2 {{
      font-size: .7rem; text-transform: uppercase; letter-spacing: .06em;
      color: var(--muted); margin-bottom: .5rem;
    }}
    .card {{
      background: var(--card); border: 1px solid var(--border);
      border-radius: var(--radius); padding: .75rem 1rem;
    }}
    ul {{ list-style: none; }}
    .item {{ padding: .5rem 0; border-bottom: 1px solid var(--border); }}
    .item:last-child {{ border-bottom: none; }}
    .muted {{ color: var(--muted); font-size: .8rem; }}
    .tag {{
      font-size: .6rem; font-weight: 700; text-transform: uppercase;
      padding: .1rem .35rem; border-radius: 4px; margin-left: .35rem;
      vertical-align: middle;
    }}
    .tag.promo {{ background: var(--promo-bg); color: var(--promo); }}
    .budget {{ background: #e8f4fd; border-radius: var(--radius); padding: .75rem 1rem; font-size: .9rem; }}
    .budget .warn {{ color: var(--promo); font-weight: 600; margin-top: .35rem; }}
    .budget .ok {{ color: var(--green); margin-top: .35rem; font-size: .85rem; }}
    .warn-list li {{ padding: .35rem 0; }}
    .muted-list {{ font-size: .85rem; color: var(--muted); }}
    .muted-list li {{ margin-left: 1rem; margin-bottom: .25rem; }}
    footer {{ margin-top: 1.5rem; font-size: .7rem; color: var(--muted); text-align: center; }}
    .links {{ text-align: center; margin: 1rem 0; }}
  </style>
</head>
<body>
  <header>
    <h1>Comida</h1>
    <div class="meta">{_esc(_recipe_label(session))} · {_esc(session.get("portions", 8))} portions</div>
    <div class="status {"warn" if needs_favorite or pending else ""}">{_esc(status)}</div>
  </header>

  <div class="hero">
    {checkout_total}
    {checkout_btn}
  </div>

  <div class="links">{links_html}</div>

  {budget_html}

  <section>
    <h2>Panier ({len(resolved)} articles)</h2>
    <div class="card"><ul>{items_html or '<li class="muted">Aucun article</li>'}</ul></div>
  </section>

  {needs_html}
  {pending_html}
  {pantry_html}

  <footer>Généré le {_esc(generated)} · lecture seule</footer>
</body>
</html>
"""
    out.write_text(page, encoding="utf-8")
    return out


def publish_hint() -> str:
    """Guess GitHub Pages URL from git remote origin."""
    import re
    import subprocess

    try:
        proc = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            cwd=ROOT,
            check=False,
        )
        remote = proc.stdout.strip()
        match = re.search(r"github\.com[:/]([^/]+)/([^/.]+)", remote)
        if match:
            user, repo = match.group(1), match.group(2)
            return f"https://{user}.github.io/{repo}/"
    except OSError:
        pass
    return "https://<user>.github.io/<repo>/"
