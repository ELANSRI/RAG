"""Rank passages deterministically with lexical, semantic or hybrid scores."""

from pathlib import Path
from typing import Sequence

import numpy as np
from tqdm import tqdm

from src.domain.contracts import (
    MinimalSearchResults,
    RankedPassage,
    StudentSearchResults,
    UnansweredQuestion,
)
from src.infrastructure.index_store import load_manifest
from .lexical import LexicalMatrix
from .semantic import VectorCatalog
from .terms import lexical_terms


def best_positions(values: np.ndarray, requested: int) -> np.ndarray:
    """Sort positive finite scores; resolve ties by stable passage position."""
    candidates = np.flatnonzero(np.isfinite(values) & (values > 0))
    if requested <= 0 or candidates.size == 0:
        return np.empty(0, dtype=np.int64)
    order = np.lexsort((candidates, -values[candidates]))
    return np.asarray(candidates[order[:requested]], dtype=np.int64)


def blend_rankings(
    weighted: Sequence[tuple[np.ndarray, float]], depth: int = 100
) -> np.ndarray:
    """Normalize top scores and combine lexical and semantic evidence."""
    if not weighted:
        return np.empty(0, dtype=np.float32)
    combined = np.zeros(len(weighted[0][0]), dtype=np.float32)
    for values, influence in weighted:
        positions = best_positions(values, depth)
        if positions.size:
            selected = values[positions]
            spread = float(selected.max() - selected.min()) or 1.0
            combined[positions] += influence * (
                (selected - selected.min()) / spread + 0.001
            )
    return combined


class SearchEngine:
    """Load one index and reuse it for all questions of a command."""

    def __init__(self, directory: Path, strategy: str = "bm25") -> None:
        """Validate index alignment and optionally load semantic vectors."""
        if strategy not in {"bm25", "semantic", "hybrid"}:
            raise ValueError("mode must be bm25, semantic or hybrid")
        self.manifest = load_manifest(directory)
        self.lexical = LexicalMatrix.restore(directory)
        self.strategy = strategy
        self.vector_catalog: VectorCatalog | None = None
        if self.lexical.coefficients.shape[0] != len(self.manifest.passages):
            raise ValueError("passage table and lexical matrix are misaligned")
        if strategy != "bm25":
            if not self.manifest.semantic_enabled:
                raise ValueError("run index --semantic True first")
            self.vector_catalog = VectorCatalog.load(directory)
            if len(self.vector_catalog.representations) != len(
                self.manifest.passages
            ):
                raise ValueError(
                    "semantic vectors and passages are misaligned"
                )

    def find(self, question_text: str, requested: int) -> list[RankedPassage]:
        """Return the best matching source locations without loading Qwen."""
        if requested <= 0 or not question_text.strip():
            return []
        lexical_scores = self.lexical.scores_for(lexical_terms(question_text))
        final_scores = lexical_scores
        if self.vector_catalog is not None:
            semantic_scores = self.vector_catalog.score(question_text)
            final_scores = (
                semantic_scores
                if self.strategy == "semantic"
                else (
                    blend_rankings(
                        [(lexical_scores, 1.0), (semantic_scores, 0.25)]
                    )
                )
            )
        return [
            RankedPassage(
                passage=self.manifest.passages[position],
                relevance=float(final_scores[position]),
            )
            for position in best_positions(final_scores, requested)
        ]

    def run_batch(
        self, questions: Sequence[UnansweredQuestion], requested: int
    ) -> StudentSearchResults:
        """Preserve dataset IDs while processing questions independently."""
        collected: list[MinimalSearchResults] = []
        for question in tqdm(questions, desc="Searching", unit="question"):
            matches = self.find(question.question, requested)
            collected.append(
                MinimalSearchResults(
                    question_id=question.question_id,
                    question=question.question,
                    retrieved_sources=[
                        match.passage.as_source() for match in matches
                    ],
                )
            )
        return StudentSearchResults(search_results=collected, k=requested)
