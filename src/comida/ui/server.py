"""HTTP server for the Comida validation UI."""

from __future__ import annotations

import json
import os
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from comida.basket import push_items, resolved_to_basket_items, shared_list_url
from comida.budget import estimate_basket
from comida.matcher import _display_name, _price_chf, _product_id
from comida.migros_client import search_products
from comida.promo_cache import fetch_promotions_cached
from comida.ui.jobs import job_manager
from comida.ui.settings import read_config_files, save_config_files, save_preferences
from comida.ui.workflow import compute_workflow, record_push_result, set_kookd_done
from comida.week_page import generate_week_page, publish_hint
from comida.validation import (
    accept_option,
    add_search_results,
    load_session,
    reopen_item,
    reject_current,
    refresh_favorites_workflow,
    save_session,
    validation_summary,
)

STATIC_DIR = Path(__file__).resolve().parent / "static"
DEFAULT_PORT = 8765
DEFAULT_HOST = "0.0.0.0"
MIGROS_MY_PRODUCTS_URL = "https://www.migros.ch/fr/my-products"


def ui_host() -> str:
    return os.environ.get("COMIDA_UI_HOST", DEFAULT_HOST).strip() or DEFAULT_HOST


def local_urls(port: int) -> list[str]:
    urls = [f"http://127.0.0.1:{port}"]
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            lan_ip = sock.getsockname()[0]
        if lan_ip and lan_ip != "127.0.0.1":
            urls.append(f"http://{lan_ip}:{port}")
    except OSError:
        pass
    return urls


def _product_url(product: dict) -> str | None:
    online_id = product.get("migrosOnlineId")
    if online_id:
        return f"https://www.migros.ch/fr/product/{online_id}"
    urls = product.get("productUrls") or product.get("product_urls")
    if urls:
        return str(urls).split()[0] if isinstance(urls, str) else urls[0]
    return None


def _format_search_hit(product: dict, promo_ids: set[int]) -> dict:
    uid = _product_id(product)
    offer = product.get("offer") or {}
    return {
        "uid": uid,
        "name": _display_name(product),
        "package": offer.get("quantity"),
        "price_chf": _price_chf(product),
        "on_promotion": bool(uid and uid in promo_ids),
        "url": _product_url(product),
    }


class ComidaHandler(BaseHTTPRequestHandler):
    server_version = "ComidaUI/2.0"

    def log_message(self, format: str, *args) -> None:
        pass

    def _send_json(self, data: dict, status: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        if not length:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def _load_session_safe(self) -> dict | None:
        try:
            return load_session()
        except FileNotFoundError:
            return None

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            self._serve_index()
        elif path == "/api/session":
            self._api_session()
        elif path == "/api/summary":
            session = self._load_session_safe()
            if not session:
                self._send_json({"summary": "Aucune session."})
                return
            self._send_json({"summary": validation_summary(session)})
        elif path == "/api/favorite-hints":
            self._api_favorite_hints()
        elif path == "/api/settings":
            self._api_get_settings()
        elif path == "/api/jobs":
            self._api_get_job()
        else:
            self.send_error(404)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        try:
            if path == "/api/accept":
                self._api_accept()
            elif path == "/api/reject":
                self._api_reject()
            elif path == "/api/search":
                self._api_search()
            elif path == "/api/reopen":
                self._api_reopen()
            elif path == "/api/push":
                self._api_push()
            elif path == "/api/refresh":
                self._api_refresh()
            elif path == "/api/kookd-done":
                self._api_kookd_done()
            elif path == "/api/settings":
                self._api_save_settings()
            elif path == "/api/jobs":
                self._api_start_job()
            elif path == "/api/publish":
                self._api_publish()
            else:
                self.send_error(404)
        except (ValueError, FileNotFoundError) as e:
            self._send_json({"ok": False, "error": str(e)}, 400)
        except RuntimeError as e:
            self._send_json({"ok": False, "error": str(e)}, 500)

    def _serve_index(self) -> None:
        html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _api_session(self) -> None:
        session = self._load_session_safe()
        if not session:
            workflow = compute_workflow(None)
            self._send_json({
                "recipe": None,
                "workflow": workflow,
                "settings": read_config_files(),
                "job": job_manager.current(),
                "my_products_url": MIGROS_MY_PRODUCTS_URL,
                "shared_list_url": shared_list_url(),
                "publish_url": publish_hint(),
                "stats": {"resolved": 0, "pending": 0, "manual": 0, "needs_favorite": 0, "total": 0},
            })
            return

        pending = [p for p in session.get("pending", []) if p.get("status") == "pending"]
        manual = [u for u in session.get("unmatched", []) if u.get("status") == "manual"]
        needs_favorite = session.get("needs_favorite", [])
        resolved = session.get("resolved", [])
        total = len(pending) + len(manual) + len(needs_favorite) + len(resolved)
        budget = estimate_basket(resolved) if resolved else None
        workflow = compute_workflow(session)

        self._send_json({
            "recipe": session.get("recipe"),
            "portions": session.get("portions"),
            "favorites_resolved": session.get("favorites_resolved", []),
            "promos_resolved": session.get("promos_resolved", []),
            "list_resolved": session.get("list_resolved", []),
            "weekly_staples": session.get("weekly_staples", []),
            "favorites_count": session.get("favorites_count", 0),
            "pantry_skipped": session.get("pantry_skipped", []),
            "pending": pending,
            "manual": manual,
            "needs_favorite": needs_favorite,
            "resolved": resolved,
            "budget": budget,
            "workflow": workflow,
            "settings": read_config_files(),
            "job": job_manager.current(),
            "my_products_url": MIGROS_MY_PRODUCTS_URL,
            "shared_list_url": shared_list_url(),
            "publish_url": publish_hint(),
            "summary": validation_summary(session),
            "stats": {
                "resolved": len(resolved),
                "pending": len(pending),
                "manual": len(manual),
                "needs_favorite": len(needs_favorite),
                "total": total,
            },
        })

    def _api_favorite_hints(self) -> None:
        query = parse_qs(urlparse(self.path).query).get("q", [""])[0].strip()
        if not query:
            self._send_json({"ok": False, "error": "Paramètre q requis"}, 400)
            return
        promo_ids = set(fetch_promotions_cached()[0])
        products = search_products(query, size=6)
        hits = [_format_search_hit(p, promo_ids) for p in products if _product_id(p)]
        self._send_json({"ok": True, "query": query, "products": hits})

    def _api_accept(self) -> None:
        data = self._read_json()
        session = load_session()
        session = accept_option(session, data["key"], int(data["rank"]))
        save_session(session)
        self._send_json({"ok": True, "summary": validation_summary(session)})

    def _api_reject(self) -> None:
        data = self._read_json()
        session = load_session()
        session = reject_current(session, data["key"])
        save_session(session)
        self._send_json({
            "ok": True,
            "message": session.get("_last_message", ""),
            "summary": validation_summary(session),
        })

    def _api_search(self) -> None:
        data = self._read_json()
        session = load_session()
        products = search_products(data["query"], size=8)
        promo_ids = set(fetch_promotions_cached()[0])
        session = add_search_results(session, data["key"], products, promo_ids)
        save_session(session)
        self._send_json({
            "ok": True,
            "message": session.get("_last_message", ""),
            "summary": validation_summary(session),
        })

    def _api_reopen(self) -> None:
        data = self._read_json()
        session = load_session()
        session = reopen_item(session, data["key"])
        save_session(session)
        self._send_json({
            "ok": True,
            "message": session.get("_last_message", ""),
            "summary": validation_summary(session),
        })

    def _api_push(self) -> None:
        data = self._read_json()
        force = data.get("force", False)
        session = load_session()
        pending = [p for p in session.get("pending", []) if p.get("status") == "pending"]
        manual = [u for u in session.get("unmatched", []) if u.get("status") == "manual"]
        needs_favorite = session.get("needs_favorite", [])
        resolved = session.get("resolved", [])

        if not resolved:
            self._send_json({"ok": False, "error": "Aucun produit validé."}, 400)
            return
        if (pending or manual or needs_favorite) and not force:
            self._send_json({
                "ok": False,
                "error": (
                    f"{len(needs_favorite)} favori(s) manquant(s). "
                    "Ajoutez-les ou poussez avec force."
                ),
            }, 400)
            return

        items = resolved_to_basket_items(resolved)
        result = push_items(items)
        ui_state = record_push_result(result)
        publish_path = None
        publish_url = publish_hint()
        if os.environ.get("COMIDA_PUBLISH_ON_PUSH", "").strip().lower() in ("1", "true", "yes"):
            try:
                publish_path = str(generate_week_page(session).relative_to(
                    Path(__file__).resolve().parents[3]
                ))
            except OSError:
                pass
        self._send_json({
            "ok": True,
            "result": result,
            "workflow": compute_workflow(session),
            "ui_state": ui_state,
            "publish_path": publish_path,
            "publish_url": publish_url,
        })

    def _api_refresh(self) -> None:
        session = load_session()
        session = refresh_favorites_workflow(session)
        save_session(session)
        self._send_json({
            "ok": True,
            "summary": validation_summary(session),
            "needs_favorite": len(session.get("needs_favorite", [])),
            "workflow": compute_workflow(session),
        })

    def _api_kookd_done(self) -> None:
        data = self._read_json()
        state = set_kookd_done(bool(data.get("done", True)))
        session = self._load_session_safe()
        self._send_json({
            "ok": True,
            "ui_state": state,
            "workflow": compute_workflow(session),
        })

    def _api_get_settings(self) -> None:
        self._send_json({"ok": True, "settings": read_config_files()})

    def _api_save_settings(self) -> None:
        data = self._read_json()
        prefs = save_preferences(
            portions=data.get("portions"),
            base_portions=data.get("base_portions"),
            recipe_export=data.get("recipe_export"),
            list_url=data.get("list_url"),
        )
        files = save_config_files(
            pantry_text=data.get("pantry_text"),
            weekly_text=data.get("weekly_text"),
        )
        self._send_json({"ok": True, "settings": {**prefs, **files}})

    def _api_get_job(self) -> None:
        job_id = parse_qs(urlparse(self.path).query).get("id", [None])[0]
        job = job_manager.snapshot(job_id) if job_id else job_manager.current()
        self._send_json({"ok": True, "job": job})

    def _api_start_job(self) -> None:
        data = self._read_json()
        job_type = data.get("type", "").strip().lower()
        if not job_type:
            self._send_json({"ok": False, "error": "type requis (promos|week)"}, 400)
            return
        job = job_manager.start(job_type, **{k: v for k, v in data.items() if k != "type"})
        self._send_json({"ok": True, "job": job})

    def _api_publish(self) -> None:
        session = self._load_session_safe()
        if not session:
            self._send_json({"ok": False, "error": "Aucune session."}, 400)
            return
        path = generate_week_page(session)
        root = Path(__file__).resolve().parents[3]
        self._send_json({
            "ok": True,
            "path": str(path.relative_to(root)),
            "publish_url": publish_hint(),
        })


def serve(port: int = DEFAULT_PORT, open_browser: bool = True, host: str | None = None) -> None:
    bind_host = host or ui_host()
    if open_browser and os.environ.get("COMIDA_NO_BROWSER", "").strip().lower() not in (
        "1",
        "true",
        "yes",
    ):
        import webbrowser
        webbrowser.open(f"http://127.0.0.1:{port}")

    server = ThreadingHTTPServer((bind_host, port), ComidaHandler)
    urls = local_urls(port)
    print(f"Comida UI — {urls[0]}  (Ctrl+C pour arrêter)")
    if len(urls) > 1:
        print(f"  Téléphone (même Wi‑Fi) : {urls[1]}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nArrêt.")
        server.shutdown()


def serve_background(port: int = DEFAULT_PORT, host: str | None = None) -> threading.Thread:
    bind_host = host or ui_host()
    server = ThreadingHTTPServer((bind_host, port), ComidaHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return thread
