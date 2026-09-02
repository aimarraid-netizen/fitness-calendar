"""Smoke-test HTML generaatorile — render_html on ajaloos kaks korda lehe katki teinud
(fb9e57b, 59e48b3: puuduv koma ikoonikaardis). Payload peab serialiseeruma ja
template placeholderid peavad asenduma."""
import json
import re

import render_html as rh


def test_payload_serialises_and_has_analysis_fields(loaded_conn):
    payload = rh.build_payload(loaded_conn)
    json.dumps(payload, ensure_ascii=False)          # sqlite3.Row / datetime lekkeid pole
    assert payload["stats"]["total_workouts"] == 1
    assert "Bent Over Barbell Row" in payload["exercises"]
    w = payload["workouts"][0]
    assert {"pr_count", "prs", "insight", "exercises"} <= set(w)
    ex = {e["name"]: e for e in w["exercises"]}
    row = ex["Bent Over Barbell Row"]
    assert {"status", "delta_kg", "delta_reps", "pr", "first"} <= set(row)
    assert row["status"] == "uus" and row["first"] is True
    hist = payload["exercises"]["Bent Over Barbell Row"]["history"][0]
    assert (hist["sets"], hist["reps"], hist["weight"]) == (3, 6, 70.0)
    assert payload["balance_window"] == ["2026-W21", "2026-W21"]
    assert "muu" not in payload["balance"]


def test_render_writes_html_with_data(loaded_conn, tmp_path):
    out = rh.render(loaded_conn, tmp_path / "site" / "index.html")
    html = out.read_text(encoding="utf-8")
    assert "/*__DATA__*/" not in html
    assert "{{ generated }}" not in html
    m = re.search(r"const DATA = (\{.*?\});\n", html, re.S)
    assert m, "DATA const puudub"
    data = json.loads(m.group(1))
    assert data["stats"]["total_workouts"] == 1
    # vanad mustrid ei tohi tagasi tulla
    assert "sets||3" not in html and "exDelta(ex.name)" not in html
    assert "uut rekord/" not in html


def test_render_empty_db_does_not_crash(conn, tmp_path):
    out = rh.render(conn, tmp_path / "index.html")
    assert out.exists()
    payload = rh.build_payload(conn)
    assert payload["workouts"] == [] and payload["balance"] == {} and payload["balance_window"] == []
