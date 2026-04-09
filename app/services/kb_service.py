from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..kb import KBEntry, load_from_raw_folder, retrieve_scored
from .types import KnowledgeBaseSearchResult


@dataclass(frozen=True, slots=True)
class KnowledgeBaseService:
    raw_dir: Path
    entries: tuple[KBEntry, ...]

    @classmethod
    def load(cls, raw_dir: str | Path) -> "KnowledgeBaseService":
        path = Path(raw_dir).expanduser().resolve()
        entries = tuple(load_from_raw_folder(path))
        return cls(raw_dir=path, entries=entries)

    @property
    def is_loaded(self) -> bool:
        return bool(self.entries)

    def search(self, query: str, *, role: str, k: int = 5) -> tuple[KnowledgeBaseSearchResult, ...]:
        scored = retrieve_scored(list(self.entries), query, role=role, k=k)
        return tuple(KnowledgeBaseSearchResult.from_scored_entry(item) for item in scored)

    def hits_for_ui(self, results: tuple[KnowledgeBaseSearchResult, ...]) -> tuple[dict[str, str], ...]:
        return tuple(result.to_public_dict() for result in results)
