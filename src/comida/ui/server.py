"""HTTP server for the Comida validation UI."""

from __future__ import annotations

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from comida.basket import push_items, resolved_to_basket_items
from comida.budget import estimate_basket
from comida.migros_client import search_products
from comida.promo_cache import fetch_promotions_cached
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


class ComidaHandler(BaseHTTPRequestHandler):
    server_version = "ComidaUI/1.0"

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

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            self._serve_index()
        elif path == "/api/session":
            self._api_session()
        elif path == "/api/summary":
            session = load_session()
            self._send_json({"summary": validation_summary(session)})
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
        session = load_session()
        pending = [p for p in session.get("pending", []) if p.get("status") == "pending"]
        manual = [u for u in session.get("unmatched", []) if u.get("status") == "manual"]
        needs_favorite = session.get("needs_favorite", [])
        resolved = session.get("resolved", [])
        total = len(pending) + len(manual) + len(needs_favorite) + len(resolved)
        budget = estimate_basket(resolved) if resolved else None
        self._send_json({
            "recipe": session.get("recipe"),
            "portions": session.get("portions"),
            "favorites_resolved": session.get("favorites_resolved", []),
            "promos_resolved": session.get("promos_resolved", []),
            "favorites_count": session.get("favorites_count", 0),
            "pantry_skipped": session.get("pantry_skipped", []),
            "pending": pending,
            "manual": manual,
            "needs_favorite": needs_favorite,
            "resolved": resolved,
            "budget": budget,
            "my_products_url": "https://www.migros.ch/fr/my-products",
            "summary": validation_summary(session),
            "stats": {
                "resolved": len(resolved),
                "pending": len(pending),
                "manual": len(manual),
                "needs_favorite": len(needs_favorite),
                "total": total,
            },
        })

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
        self._send_json({"ok": True, "result": result})

    def _api_refresh(self) -> None:
        session = load_session()
        session = refresh_favorites_workflow(session)
        save_session(session)
        self._send_json({
            "ok": True,
            "summary": validation_summary(session),
            "needs_favorite": len(session.get("needs_favorite", [])),
        })


def serve(port: int = DEFAULT_PORT, open_browser: bool = True) -> None:
    if open_browser:
        import webbrowser
        webbrowser.open(f"http://127.0.0.1:{port}")

    server = ThreadingHTTPServer(("127.0.0.1", port), ComidaHandler)
    print(f"Comida UI — http://127.0.0.1:{port}  (Ctrl+C pour arrêter)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nArrêt.")
        server.shutdown()


def serve_background(port: int = DEFAULT_PORT) -> threading.Thread:
    server = ThreadingHTTPServer(("127.0.0.1", port), ComidaHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return thread
