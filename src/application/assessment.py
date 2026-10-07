"""Local retrieval metrics; the official moulinette remains external."""

from pydantic import BaseModel

from src.domain.contracts import (
    AnsweredQuestion,
    MinimalSource,
    RagDataset,
    StudentSearchResults,
)


class Assessment(BaseModel):
    """Report local recall and missing results without claiming official
    status."""

    evaluated_questions: int
    missing_questions: int
    recall: dict[int, float]


def interval_overlap(
    expected: MinimalSource, proposed: MinimalSource
) -> float:
    """Compute intersection over union for two spans in exactly the same
    file."""
    if expected.file_path != proposed.file_path:
        return 0.0
    overlap = max(
        0,
        min(expected.last_character_index, proposed.last_character_index)
        - max(expected.first_character_index, proposed.first_character_index),
    )
    union = (
        expected.last_character_index
        - expected.first_character_index
        + proposed.last_character_index
        - proposed.first_character_index
        - overlap
    )
    return overlap / union


def assess_retrieval(
    predictions: StudentSearchResults,
    reference: RagDataset,
    source_limit: int = 2000,
) -> Assessment:
    """Compare predicted spans with answered questions at several cutoffs."""
    if not reference.rag_questions:
        raise ValueError("reference dataset is empty")
    if any(
        not isinstance(question, AnsweredQuestion)
        for question in reference.rag_questions
    ):
        raise ValueError("evaluation requires AnsweredQuestions references")
    for prediction in predictions.search_results:
        for source in prediction.retrieved_sources:
            if (
                source.last_character_index - source.first_character_index
                > source_limit
            ):
                raise ValueError("retrieved source exceeds evaluation limit")
    results_by_id = {
        result.question_id: result for result in predictions.search_results
    }
    cutoffs = sorted(
        {
            limit
            for limit in (1, 3, 5, 10, predictions.k)
            if 0 < limit <= predictions.k
        }
    )
    totals = {limit: 0.0 for limit in cutoffs}
    missing = 0
    for question in reference.rag_questions:
        if not isinstance(question, AnsweredQuestion):
            continue
        if not question.sources:
            raise ValueError("a reference question has no expected sources")
        result = results_by_id.get(question.question_id)
        if result is None:
            missing += 1
            continue
        if result.question != question.question:
            raise ValueError(f"question text mismatch: {question.question_id}")
        for cutoff in cutoffs:
            matched = sum(
                any(
                    interval_overlap(source, hit) >= 0.05
                    for hit in result.retrieved_sources[:cutoff]
                )
                for source in question.sources
            )
            totals[cutoff] += matched / len(question.sources)
    return Assessment(
        evaluated_questions=len(reference.rag_questions),
        missing_questions=missing,
        recall={
            cutoff: value / len(reference.rag_questions)
            for cutoff, value in totals.items()
        },
    )
