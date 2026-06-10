"""MCP tool registrations for semantic (Understand-Anything) queries."""

from __future__ import annotations

from typing import Any, Dict, Optional

from askme.backends import understand


def semantic_explain(target: str) -> Dict[str, Any]:
    """Narrative explanation for a file path or symbol."""
    return understand.semantic_explain(target=target)


def semantic_chat(question: str, scope: Optional[str] = None) -> Dict[str, Any]:
    """Free-form question against the knowledge graph."""
    return understand.semantic_chat(question=question, scope=scope)


def semantic_diff(base: str, head: str = "HEAD") -> Dict[str, Any]:
    """Explain what a git diff changes and why."""
    return understand.semantic_diff(base=base, head=head)


def semantic_onboard(area: str) -> Dict[str, Any]:
    """Generate an onboarding guide for a module / directory."""
    return understand.semantic_onboard(area=area)


def semantic_domain(area: Optional[str] = None) -> Dict[str, Any]:
    """Map the business-domain knowledge for the repo or a sub-area."""
    return understand.semantic_domain(area=area)
