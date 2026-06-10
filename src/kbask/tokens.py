"""Token counting helper.

Used by the MCP server to annotate every tool response with a
`_meta.tokens` block so callers know how much context they spend per call.

Strategy:
  1. If `tiktoken` is installed, use its `cl100k_base` encoder (close enough
     for Claude / GPT-4 family token math — within ~10%).
  2. Otherwise fall back to a deterministic char/4 heuristic.

Returned counts are advisory, not billing-accurate.
"""

from __future__ import annotations

from typing import Any


_encoder = None
_tried_import = False


def _get_encoder():
    global _encoder, _tried_import
    if _tried_import:
        return _encoder
    _tried_import = True
    try:
        import tiktoken  # type: ignore[import-not-found]
        _encoder = tiktoken.get_encoding("cl100k_base")
    except Exception:
        _encoder = None
    return _encoder


def count(text: str) -> int:
    """Estimate token count of `text`. Returns 0 for empty / non-str input."""
    if not text:
        return 0
    if not isinstance(text, str):
        text = str(text)
    enc = _get_encoder()
    if enc is not None:
        try:
            return len(enc.encode(text))
        except Exception:
            pass
    # Fallback: roughly 4 chars / token for English/code mix.
    return max(1, len(text) // 4)


def encoder_name() -> str:
    return "tiktoken:cl100k_base" if _get_encoder() is not None else "heuristic:chars/4"


def annotate(result: Any, *, input_text: str, output_text: str, tool: str) -> Any:
    """Inject a `_meta.tokens` block into `result` if it's a dict; else wrap it."""
    block = {
        "tool": tool,
        "tokens": {
            "input": count(input_text),
            "output": count(output_text),
            "total": count(input_text) + count(output_text),
        },
        "bytes": {
            "input": len(input_text.encode("utf-8")) if input_text else 0,
            "output": len(output_text.encode("utf-8")) if output_text else 0,
        },
        "encoder": encoder_name(),
    }
    if isinstance(result, dict):
        existing = result.get("_meta") if isinstance(result.get("_meta"), dict) else {}
        result["_meta"] = {**existing, **block}
        return result
    return {"_meta": block, "result": result}
