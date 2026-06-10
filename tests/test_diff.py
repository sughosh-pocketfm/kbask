"""Smoke tests for the incremental-update delta logic."""

from __future__ import annotations

from askme.diff import compute, carry_forward
from askme.meta import FileEntry, Meta


def _meta_with(files: dict[str, tuple[str, str | None]]) -> Meta:
    meta = Meta()
    for path, (structural, semantic) in files.items():
        meta.files[path] = FileEntry(structural_hash=structural, semantic_hash=semantic)
    return meta


def test_added_and_removed_files_are_detected():
    previous = _meta_with({"a.kt": ("h1", "s1"), "b.kt": ("h2", "s2")})
    current = {"b.kt": "h2", "c.kt": "h3"}
    delta = compute(previous, current)
    assert delta.added == {"c.kt"}
    assert delta.removed == {"a.kt"}
    assert delta.unchanged == {"b.kt"}
    assert delta.modified == set()


def test_modified_file_invalidates_semantic():
    previous = _meta_with({"a.kt": ("h1", "s1")})
    current = {"a.kt": "h_new"}
    delta = compute(previous, current)
    assert delta.modified == {"a.kt"}
    assert delta.unchanged == set()


def test_carry_forward_preserves_semantic_for_unchanged_files():
    previous = _meta_with({"a.kt": ("h1", "s1"), "b.kt": ("h2", "s2")})
    current = {"a.kt": "h1", "b.kt": "h2_new"}
    delta = compute(previous, current)
    files = carry_forward(previous, delta, current)
    assert files["a.kt"].semantic_hash == "s1"
    assert files["b.kt"].semantic_hash is None


def test_structural_unchanged_but_semantic_missing_is_added():
    previous = _meta_with({"a.kt": ("h1", None)})
    current = {"a.kt": "h1"}
    delta = compute(previous, current)
    assert delta.added == {"a.kt"}
