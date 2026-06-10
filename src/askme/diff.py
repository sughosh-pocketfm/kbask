"""Compute per-file delta between previous and current build."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Set

from askme.meta import FileEntry, Meta


@dataclass
class Delta:
    added: Set[str] = field(default_factory=set)
    modified: Set[str] = field(default_factory=set)
    removed: Set[str] = field(default_factory=set)
    unchanged: Set[str] = field(default_factory=set)

    @property
    def dirty(self) -> Set[str]:
        return self.added | self.modified

    def summary(self) -> str:
        return (
            f"added={len(self.added)} modified={len(self.modified)} "
            f"removed={len(self.removed)} unchanged={len(self.unchanged)}"
        )


def compute(previous: Meta, current_hashes: Dict[str, str]) -> Delta:
    """Diff current per-file structural hashes against the previous build's meta."""
    delta = Delta()
    prev_files = previous.files

    for path, new_hash in current_hashes.items():
        prev = prev_files.get(path)
        if prev is None:
            delta.added.add(path)
        elif prev.structural_hash != new_hash:
            delta.modified.add(path)
        elif prev.semantic_hash is None:
            # Structural unchanged but no semantic entry yet — treat as needing semantic build.
            delta.added.add(path)
        else:
            delta.unchanged.add(path)

    for path in prev_files:
        if path not in current_hashes:
            delta.removed.add(path)

    return delta


def carry_forward(previous: Meta, delta: Delta, new_hashes: Dict[str, str]) -> Dict[str, FileEntry]:
    """Build the new file-entry map by carrying over preserved semantic results."""
    out: Dict[str, FileEntry] = {}
    for path, structural_hash in new_hashes.items():
        if path in delta.unchanged:
            prev_entry = previous.files[path]
            out[path] = FileEntry(
                structural_hash=structural_hash,
                semantic_hash=prev_entry.semantic_hash,
                semantic_built_at=prev_entry.semantic_built_at,
            )
        else:
            out[path] = FileEntry(structural_hash=structural_hash)
    return out
