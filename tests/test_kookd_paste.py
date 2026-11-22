import json

import pytest

from comida.ui.settings import save_kookd_paste


def _patch(tmp_path, monkeypatch):
    exports = tmp_path / "exports"
    state = tmp_path / "ui_state.json"
    session = tmp_path / "validation_session.json"
    monkeypatch.setattr("comida.ui.settings.EXPORTS_DIR", exports)
    monkeypatch.setattr("comida.ui.workflow.UI_STATE_PATH", state)
    monkeypatch.setattr("comida.ui.workflow.SESSION_PATH", session)
    return exports, state, session


def test_save_kookd_paste_selects_the_export(tmp_path, monkeypatch):
    exports, state, _session = _patch(tmp_path, monkeypatch)
    out = save_kookd_paste("• 500 g Riz blanc\n• 2 pièces Oignon\n", day="2026-10-11")
    assert out == {"filename": "semaine-2026-10-11.txt", "ingredient_count": 2}
    assert (exports / "semaine-2026-10-11.txt").read_text(encoding="utf-8").startswith("• 500 g")
    ui = json.loads(state.read_text(encoding="utf-8"))
    assert ui["recipe_export"] == "semaine-2026-10-11.txt"
    assert ui["kookd_done"] is True
    assert ui["analysis_stale"] is True
    assert ui["pantry_done_for"] == ""


def test_save_kookd_paste_rejects_text_without_ingredients(tmp_path, monkeypatch):
    _patch(tmp_path, monkeypatch)


def test_new_week_clears_the_previous_session(tmp_path, monkeypatch):
    from comida.ui.workflow import discard_other_week_session

    exports, state, session = _patch(tmp_path, monkeypatch)
    exports.mkdir()
    (exports / "semaine-s3.txt").write_text("• 800 g Pâtes spaghetti\n", encoding="utf-8")
    state.write_text(
        json.dumps({
            "recipe_export": "semaine-s3.txt",
            "pantry_done_for": "semaine-s3.txt",
            "weekly_done_for": "semaine-s3.txt",
            "last_push": {"at": "2026-10-10T00:00:00+00:00"},
        }),
        encoding="utf-8",
    )
    session.write_text(
        json.dumps({"recipe": str(exports / "semaine-s3.txt"), "resolved": [{"key": "pates"}]}),
        encoding="utf-8",
    )

    save_kookd_paste("• 1.6 kg Cabillaud\n• 800 g Potimarron\n", day="2026-10-16")

    assert not session.exists()
    ui = json.loads(state.read_text(encoding="utf-8"))
    assert ui["recipe_export"] == "semaine-2026-10-16.txt"
    assert ui["pantry_done_for"] == ""
    assert ui["weekly_done_for"] == ""
    assert "last_push" not in ui
    assert ui["analysis_stale"] is True

    ui["recipe_export"] = "semaine-2026-10-16.txt"
    ui["pantry_done_for"] = "semaine-2026-10-16.txt"
    state.write_text(json.dumps(ui), encoding="utf-8")
    session.write_text(
        json.dumps({"recipe": "exports/semaine-s3.txt", "resolved": []}),
        encoding="utf-8",
    )
    assert discard_other_week_session() is True
    assert not session.exists()
    kept = json.loads(state.read_text(encoding="utf-8"))
    assert kept["pantry_done_for"] == "semaine-2026-10-16.txt"
    with pytest.raises(ValueError, match="Aucune ligne"):
        save_kookd_paste("bonjour")
