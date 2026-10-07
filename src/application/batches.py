"""Batch answer generation reuses one responder and preserves search
results."""

from tqdm import tqdm

from src.domain.contracts import (
    MinimalAnswer,
    StudentSearchResults,
    StudentSearchResultsAndAnswer,
)
from src.generation.local_model import LocalResponder


def answer_results(
    results: StudentSearchResults, responder: LocalResponder
) -> StudentSearchResultsAndAnswer:
    """Add an answer to each result without using reference dataset answers."""
    answered: list[MinimalAnswer] = []
    for result in tqdm(
        results.search_results, desc="Answering", unit="question"
    ):
        answered.append(
            MinimalAnswer(
                **result.model_dump(),
                answer=responder.respond(
                    result.question, result.retrieved_sources
                )
            )
        )
    return StudentSearchResultsAndAnswer(search_results=answered, k=results.k)
