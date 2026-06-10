"""meta.json schema and IO. Tracks per-file content hashes and build metadata."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional


SCHEMA_VERSION = 1


@dataclass
class FileEntry:
    structural_hash: str
    semantic_hash: Optional[str] = None
    semantic_built_at: Optional[str] = None


@dataclass
class Meta:
    schema_version: int = SCHEMA_VERSION
    askme_version: str = ""
    graphify_version: str = ""
    understand_version: str = ""
    git_sha: str = ""
    built_at: str = ""
    files: Dict[str, FileEntry] = field(default_factory=dict)

    def to_json(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "askme_version": self.askme_version,
            "graphify_version": self.graphify_version,
            "understand_version": self.understand_version,
            "git_sha": self.git_sha,
            "built_at": self.built_at,
            "files": {path: asdict(entry) for path, entry in self.files.items()},
        }

    @classmethod
    def from_json(cls, data: dict) -> "Meta":
        files = {path: FileEntry(**entry) for path, entry in data.get("files", {}).items()}
        return cls(
            schema_version=data.get("schema_version", SCHEMA_VERSION),
            askme_version=data.get("askme_version", ""),
            graphify_version=data.get("graphify_version", ""),
            understand_version=data.get("understand_version", ""),
            git_sha=data.get("git_sha", ""),
            built_at=data.get("built_at", ""),
            files=files,
        )


def load(path: Path) -> Meta:
    if not path.exists():
        return Meta()
    return Meta.from_json(json.loads(path.read_text(encoding="utf-8")))


def save(path: Path, meta: Meta) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(meta.to_json(), indent=2, sort_keys=True), encoding="utf-8")


def hash_file(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            sha.update(chunk)
    return f"sha256:{sha.hexdigest()}"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
