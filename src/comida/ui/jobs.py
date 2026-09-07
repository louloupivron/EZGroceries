"""Background jobs for promos export and week analysis."""

from __future__ import annotations

import threading
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path

from comida.basket import default_list_name
from comida.kookd_export import promos_no_filter_from_env, run_promos_export
from comida.ui.settings import EXPORTS_DIR, get_preferences

ROOT = Path(__file__).resolve().parents[3]
MAX_LOG_LINES = 80


class JobManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, dict] = {}
        self._current_id: str | None = None

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _append_log(self, job_id: str, line: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            logs = job.setdefault("logs", [])
            logs.append(line)
            if len(logs) > MAX_LOG_LINES:
                job["logs"] = logs[-MAX_LOG_LINES:]

    def _set_status(self, job_id: str, status: str, **extra) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            job["status"] = status
            job["updated_at"] = self._now()
            job.update(extra)
            if status in ("done", "error"):
                self._current_id = None

    def start(self, job_type: str, **options) -> dict:
        job_type = job_type.strip().lower()
        if job_type not in ("promos", "week"):
            raise ValueError(f"Type de job inconnu : {job_type}")

        with self._lock:
            if self._current_id:
                cur = self._jobs.get(self._current_id, {})
                if cur.get("status") == "running":
                    raise RuntimeError("Un job est déjà en cours")

            job_id = uuid.uuid4().hex[:12]
            job = {
                "id": job_id,
                "type": job_type,
                "status": "running",
                "options": options,
                "logs": [],
                "started_at": self._now(),
                "updated_at": self._now(),
                "result": None,
                "error": None,
            }
            self._jobs[job_id] = job
            self._current_id = job_id

        thread = threading.Thread(
            target=self._run,
            args=(job_id, job_type, options),
            daemon=True,
        )
        thread.start()
        return self.snapshot(job_id)

    def snapshot(self, job_id: str | None = None) -> dict | None:
        with self._lock:
            jid = job_id or self._current_id
            if not jid:
                # last finished job
                if not self._jobs:
                    return None
                jid = max(self._jobs, key=lambda k: self._jobs[k].get("updated_at", ""))
            job = self._jobs.get(jid)
            return dict(job) if job else None

    def current(self) -> dict | None:
        with self._lock:
            if self._current_id:
                job = self._jobs.get(self._current_id)
                return dict(job) if job else None
        return self.snapshot()

    def _run(self, job_id: str, job_type: str, options: dict) -> None:
        try:
            if job_type == "promos":
                result = self._run_promos(job_id, options)
            else:
                result = self._run_week(job_id, options)
            self._append_log(job_id, "Terminé.")
            self._set_status(job_id, "done", result=result)
        except Exception as e:
            self._append_log(job_id, f"Erreur : {e}")
            self._append_log(job_id, traceback.format_exc().splitlines()[-1])
            self._set_status(job_id, "error", error=str(e))

    def _run_promos(self, job_id: str, options: dict) -> dict:
        prefs = get_preferences()
        list_name = options.get("list_name") or prefs["list_name"] or default_list_name()
        self._append_log(job_id, f"Export promos — liste {list_name}…")
        apply_filters = None if options.get("no_filter") is None else not options["no_filter"]
        if apply_filters is None:
            apply_filters = not promos_no_filter_from_env()

        out = run_promos_export(
            list_name,
            apply_pantry=bool(options.get("apply_pantry")),
            apply_filters=apply_filters,
        )
        self._append_log(job_id, f"Fichier : {out.name}")
        return {"output": str(out.relative_to(ROOT)), "list_name": list_name}

    def _run_week(self, job_id: str, options: dict) -> dict:
        prefs = get_preferences()
        recipe_name = options.get("recipe_export") or prefs["recipe_export"]
        recipe_path = EXPORTS_DIR / Path(recipe_name).name
        if not recipe_path.exists():
            raise FileNotFoundError(f"Export introuvable : exports/{recipe_name}")

        portions = int(options.get("portions", prefs["portions"]))
        base_portions = int(options.get("base_portions", prefs["base_portions"]))
        refresh_promos = bool(options.get("refresh_promos", False))

        self._append_log(job_id, f"Analyse {recipe_path.name} ({portions} portions)…")
        if refresh_promos:
            self._append_log(job_id, "Rafraîchissement du cache promos…")

        from comida.week import run_week

        session = run_week(
            [recipe_path],
            open_ui=False,
            portions=portions,
            base_portions=base_portions,
            refresh_promos=refresh_promos,
        )

        resolved = len(session.get("resolved", []))
        needs_fav = len(session.get("needs_favorite", []))
        pending = sum(1 for p in session.get("pending", []) if p.get("status") == "pending")
        self._append_log(job_id, f"{resolved} validé(s), {needs_fav} favori(s) manquant(s), {pending} promo(s)")

        return {
            "recipe": session.get("recipe"),
            "resolved": resolved,
            "needs_favorite": needs_fav,
            "pending": pending,
        }


job_manager = JobManager()
