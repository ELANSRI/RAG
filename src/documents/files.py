"""Corpus discovery and strict, cached reads of source spans."""

import os
from functools import lru_cache
from pathlib import Path

from src.domain.contracts import MinimalSource

SUPPORTED_SUFFIXES = {".py", ".md", ".txt", ".rst"}


def list_documents(root: Path) -> list[Path]:
    """Enumerate supported files in a reproducible order."""
    if not root.is_dir():
        raise FileNotFoundError(f"raw corpus directory not found: {root}")
    return sorted(
        document
        for document in root.rglob("*")
        if document.is_file() and document.suffix.lower() in SUPPORTED_SUFFIXES
    )


def relative_name(document: Path) -> str:
    """Preserve project-relative POSIX paths used by the evaluator."""
    return Path(os.path.relpath(document.resolve(), Path.cwd())).as_posix()


def read_document(document: Path) -> str:
    """Read original UTF-8 text with Python's standard newline handling."""
    return document.read_text(encoding="utf-8")


class PassageReader:
    """Cache at most 128 files during one command."""

    def __init__(self) -> None:
        """Create a per-instance bounded cache."""
        self._read_cached = lru_cache(maxsize=128)(read_document)

    def extract(self, reference: MinimalSource) -> str:
        """Read an exact span; reject paths or offsets that are invalid."""
        content = self._read_cached(Path(reference.file_path))
        if reference.last_character_index > len(content):
            raise ValueError(f"source exceeds file: {reference.file_path}")
        return content[
            reference.first_character_index: reference.last_character_index
        ]
