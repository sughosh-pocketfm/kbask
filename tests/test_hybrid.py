from __future__ import annotations

from kbask import state
from kbask.backends import understand
from kbask.tools import hybrid


def test_understand_availability_requires_valid_object_json(tmp_path):
    state.set_out_dir(tmp_path)
    kg_path = tmp_path / "knowledge-graph.json"

    assert understand.is_available() is False

    kg_path.write_text("{not json", encoding="utf-8")
    assert understand.is_available() is False

    kg_path.write_text("[]", encoding="utf-8")
    assert understand.is_available() is False

    kg_path.write_text("{}", encoding="utf-8")
    assert understand.is_available() is True


def test_ask_graphify_only_bundle_has_prompt_candidates_and_next_steps(monkeypatch):
    monkeypatch.setattr(hybrid.understand, "is_available", lambda: False)
    monkeypatch.setattr(
        hybrid.graphify,
        "query_graph",
        lambda **_: {"starts": [{"label": "AuthController"}], "node_count": 1},
    )
    monkeypatch.setattr(
        hybrid,
        "_file_candidates",
        lambda question, limit=12: [
            {"source_file": "src/auth.py", "label": "AuthController", "term_hits": 1}
        ],
    )

    out = hybrid.ask("auth flow")

    assert out["mode"] == "graphify-only"
    assert out["structural"]["starts"][0]["label"] == "AuthController"
    assert out["file_candidates"][0]["source_file"] == "src/auth.py"
    assert "prompt_hint" in out
    assert "next_steps" in out
    assert out["stages_used"] == ["structural", "file_candidates"]


def test_trace_graphify_only_bundle_keeps_path_and_adds_fallback_fields(monkeypatch):
    path = {
        "hops": 1,
        "path": [
            {
                "from": {"label": "Controller", "source_file": "src/controller.py"},
                "to": {"label": "Repo", "source_file": "src/repo.py"},
                "relation": "calls",
            }
        ],
    }
    monkeypatch.setattr(hybrid.understand, "is_available", lambda: False)
    monkeypatch.setattr(
        hybrid.understand,
        "semantic_explain",
        lambda **_: (_ for _ in ()).throw(AssertionError),
    )
    monkeypatch.setattr(hybrid.graphify, "shortest_path", lambda **_: path)
    monkeypatch.setattr(
        hybrid,
        "_file_candidates",
        lambda question, limit=12: [
            {"source_file": "src/repo.py", "label": "Repo", "term_hits": 1}
        ],
    )

    out = hybrid.trace("Controller", "Repo")

    assert out["mode"] == "graphify-only"
    assert out["structural"] == path
    assert out["hops"] == 1
    assert out["annotated_path"][0]["gloss"] is None
    assert out["file_candidates"][0]["source_file"] == "src/repo.py"
    assert "prompt_hint" in out
    assert "next_steps" in out


def test_onboard_graphify_only_bundle_adds_candidates_and_next_steps(monkeypatch):
    struct = {"starts": [{"label": "Auth"}], "node_count": 1}
    monkeypatch.setattr(hybrid.understand, "is_available", lambda: False)
    monkeypatch.setattr(hybrid.graphify, "query_graph", lambda **_: struct)
    monkeypatch.setattr(
        hybrid,
        "_file_candidates",
        lambda question, limit=12: [
            {"source_file": "src/auth.py", "label": "Auth", "term_hits": 1}
        ],
    )

    out = hybrid.onboard("auth")

    assert out["mode"] == "graphify-only"
    assert out["structural_map"] == struct
    assert out["semantic_guide"] is None
    assert out["file_candidates"][0]["source_file"] == "src/auth.py"
    assert "prompt_hint" in out
    assert "next_steps" in out
