"""Versioned passage table persisted separately from ranking algorithms."""

from pathlib import Path

from pydantic import BaseModel

from src.domain.contracts import BuildOptions, Passage
from .json_store import read_record, write_record


class IndexManifest(BaseModel):
    """Describe the corpus, configuration and ordered passage table."""

    format_version: int = 2
    corpus_root: str
    options: BuildOptions
    passages: list[Passage]
    semantic_enabled: bool = False


def save_manifest(directory: Path, manifest: IndexManifest) -> None:
    """Write the completion marker after all numeric index files exist."""
    write_record(directory / "manifest.json", manifest)


def load_manifest(directory: Path) -> IndexManifest:
    """Load only this version's validated manifest."""
    location = directory / "manifest.json"
    if not location.is_file():
        raise FileNotFoundError(
            f"no version-2 index in {directory}; run 'index' first"
        )
    manifest = read_record(location, IndexManifest)
    if manifest.format_version != 2:
        raise ValueError("unsupported index format; run 'index' again")
    return manifest
