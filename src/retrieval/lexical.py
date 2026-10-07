"""Precompute BM25 weights in a sparse matrix for fast batch retrieval."""

import json
from collections import Counter
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np
from scipy import sparse


class LexicalMatrix:
    """Associate passage rows with vocabulary columns and BM25 weights."""

    def __init__(
        self, coefficients: sparse.csc_matrix, term_columns: dict[str, int]
    ) -> None:
        """Wrap an existing sparse matrix and its vocabulary."""
        self.coefficients = coefficients
        self.term_columns = term_columns

    @classmethod
    def from_documents(
        cls,
        documents: Iterable[Sequence[str]],
        saturation: float = 1.2,
        length_weight: float = 0.75,
    ) -> "LexicalMatrix":
        """Compute each term's BM25 contribution once during indexing."""
        lexicon: dict[str, int] = {}
        row_boundaries = [0]
        column_numbers: list[int] = []
        frequencies: list[int] = []
        for document_terms in documents:
            for term, occurrences in Counter(document_terms).items():
                column_numbers.append(lexicon.setdefault(term, len(lexicon)))
                frequencies.append(occurrences)
            row_boundaries.append(len(column_numbers))
        passage_count = len(row_boundaries) - 1
        counts = sparse.csr_matrix(
            (
                np.asarray(frequencies, dtype=np.float32),
                np.asarray(column_numbers, dtype=np.int32),
                np.asarray(row_boundaries, dtype=np.int64),
            ),
            shape=(passage_count, max(1, len(lexicon))),
        )
        lengths = np.asarray(counts.sum(axis=1)).ravel()
        mean_length = max(float(lengths.mean()), 1e-9) if passage_count else 1
        document_frequency = np.bincount(
            counts.indices, minlength=counts.shape[1]
        )
        rarity = np.log1p(
            (passage_count - document_frequency + 0.5)
            / (document_frequency + 0.5)
        ).astype(np.float32)
        penalties = saturation * (
            1 - length_weight + length_weight * lengths / mean_length
        )
        row_numbers = np.repeat(
            np.arange(passage_count), np.diff(counts.indptr)
        )
        contributions = (
            rarity[counts.indices]
            * counts.data
            * (saturation + 1)
            / (counts.data + penalties[row_numbers])
        ).astype(np.float32)
        prepared = sparse.csr_matrix(
            (contributions, counts.indices, counts.indptr), shape=counts.shape
        )
        return cls(sparse.csc_matrix(prepared), lexicon)

    def scores_for(self, query_terms: Sequence[str]) -> np.ndarray:
        """Sum the stored contributions for terms present in a query."""
        repetitions = Counter(
            term for term in query_terms if term in self.term_columns
        )
        if not repetitions:
            return np.zeros(self.coefficients.shape[0], dtype=np.float32)
        selected_columns = [self.term_columns[term] for term in repetitions]
        multipliers = np.asarray(list(repetitions.values()), dtype=np.float32)
        return np.asarray(
            self.coefficients[:, selected_columns] @ multipliers,
            dtype=np.float32,
        ).ravel()

    def persist(self, destination: Path) -> None:
        """Save numeric weights and the term-to-column mapping."""
        destination.mkdir(parents=True, exist_ok=True)
        sparse.save_npz(destination / "lexical.npz", self.coefficients)
        (destination / "vocabulary.json").write_text(
            json.dumps(self.term_columns), encoding="utf-8"
        )

    @classmethod
    def restore(cls, directory: Path) -> "LexicalMatrix":
        """Load a persisted lexical index with vocabulary validation."""
        coefficients = sparse.csc_matrix(
            sparse.load_npz(directory / "lexical.npz")
        )
        payload = json.loads(
            (directory / "vocabulary.json").read_text(encoding="utf-8")
        )
        if not isinstance(payload, dict) or any(
            not isinstance(term, str) or type(column) is not int
            for term, column in payload.items()
        ):
            raise ValueError("invalid vocabulary mapping; rebuild the index")
        if sorted(payload.values()) != list(range(len(payload))):
            raise ValueError("vocabulary columns are not contiguous")
        if coefficients.shape[1] != max(1, len(payload)):
            raise ValueError("matrix and vocabulary dimensions differ")
        return cls(coefficients, payload)
