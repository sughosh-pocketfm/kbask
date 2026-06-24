"""Smoke tests for `kbask update-bin` release resolution helpers."""

from __future__ import annotations

from kbask import update_bin


def test_tag_candidates_try_plain_and_v_prefixed_styles():
    assert update_bin._tag_candidates("0.1.0") == ["0.1.0", "v0.1.0"]
    assert update_bin._tag_candidates("v0.1.0") == ["v0.1.0", "0.1.0"]
    assert update_bin._tag_candidates("release-candidate") == ["release-candidate"]


def test_resolve_release_falls_back_from_v_prefixed_to_plain_tag():
    calls: list[str] = []
    original = update_bin._api_get

    def fake_api_get(url: str, token: str | None) -> dict:
        calls.append(url)
        if url.endswith("/tags/v0.1.0"):
            raise update_bin.UpdateBinError("not found")
        return {"tag_name": "0.1.0"}

    update_bin._api_get = fake_api_get
    try:
        release = update_bin._resolve_release("owner/repo", "v0.1.0", None)
    finally:
        update_bin._api_get = original

    assert release == {"tag_name": "0.1.0"}
    assert calls == [
        "https://api.github.com/repos/owner/repo/releases/tags/v0.1.0",
        "https://api.github.com/repos/owner/repo/releases/tags/0.1.0",
    ]


def test_resolve_release_falls_back_from_plain_to_v_prefixed_tag():
    calls: list[str] = []
    original = update_bin._api_get

    def fake_api_get(url: str, token: str | None) -> dict:
        calls.append(url)
        if url.endswith("/tags/0.1.0"):
            raise update_bin.UpdateBinError("not found")
        return {"tag_name": "v0.1.0"}

    update_bin._api_get = fake_api_get
    try:
        release = update_bin._resolve_release("owner/repo", "0.1.0", None)
    finally:
        update_bin._api_get = original

    assert release == {"tag_name": "v0.1.0"}
    assert calls == [
        "https://api.github.com/repos/owner/repo/releases/tags/0.1.0",
        "https://api.github.com/repos/owner/repo/releases/tags/v0.1.0",
    ]


def test_resolve_release_quotes_tag_path_segment():
    calls: list[str] = []
    original = update_bin._api_get

    def fake_api_get(url: str, token: str | None) -> dict:
        calls.append(url)
        return {"tag_name": "release/0.1.0"}

    update_bin._api_get = fake_api_get
    try:
        update_bin._resolve_release("owner/repo", "release/0.1.0", None)
    finally:
        update_bin._api_get = original

    assert calls == [
        "https://api.github.com/repos/owner/repo/releases/tags/release%2F0.1.0"
    ]
