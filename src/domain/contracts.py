"""Public JSON contracts and validated internal passage records."""

import uuid
from typing import Any

from pydantic import BaseModel, Field, model_validator


class MinimalSource(BaseModel):
    """Locate a non-empty character interval in an original file."""

    file_path: str = Field(min_length=1)
    first_character_index: int = Field(ge=0, strict=True)
    last_character_index: int = Field(gt=0, strict=True)

    @model_validator(mode="after")
    def check_interval(self) -> "MinimalSource":
        """Reject reversed or empty intervals."""
        if self.last_character_index <= self.first_character_index:
            raise ValueError("source end must be greater than its start")
        return self


class UnansweredQuestion(BaseModel):
    """Carry a question and its stable identifier."""

    question_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    question: str


class AnsweredQuestion(UnansweredQuestion):
    """Carry the reference answer and reference sources."""

    sources: list[MinimalSource]
    answer: str


class RagDataset(BaseModel):
    """Read answered or unanswered questions without union fallback."""

    rag_questions: list[AnsweredQuestion | UnansweredQuestion]

    @model_validator(mode="before")
    @classmethod
    def distinguish_references(cls, payload: Any) -> Any:
        """Validate reference entries before the union can discard fields."""
        if isinstance(payload, dict):
            prepared = dict(payload)
            entries = prepared.get("rag_questions")
            if isinstance(entries, list):
                prepared["rag_questions"] = [
                    (
                        AnsweredQuestion.model_validate(entry)
                        if isinstance(entry, dict)
                        and ("sources" in entry or "answer" in entry)
                        else entry
                    )
                    for entry in entries
                ]
            return prepared
        return payload

    @model_validator(mode="after")
    def check_identifiers(self) -> "RagDataset":
        """Reject ambiguous duplicate question identifiers."""
        identifiers = [entry.question_id for entry in self.rag_questions]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("duplicate question_id in dataset")
        return self


class MinimalSearchResults(BaseModel):
    """Store the ranked sources for one question."""

    question_id: str
    question: str
    retrieved_sources: list[MinimalSource]


class MinimalAnswer(MinimalSearchResults):
    """Add generated text to a search result."""

    answer: str


class StudentSearchResults(BaseModel):
    """Validate the public search-results envelope."""

    search_results: list[MinimalSearchResults]
    k: int = Field(ge=0, strict=True)

    @model_validator(mode="after")
    def check_results(self) -> "StudentSearchResults":
        """Reject duplicate questions, too many hits and oversized sources."""
        identifiers = [entry.question_id for entry in self.search_results]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("duplicate question_id in search results")
        for entry in self.search_results:
            if len(entry.retrieved_sources) > self.k:
                raise ValueError("more sources than requested k")
            for source in entry.retrieved_sources:
                width = (
                    source.last_character_index - source.first_character_index
                )
                if width > 2000:
                    raise ValueError("a retrieved source exceeds 2000 chars")
        return self


class StudentSearchResultsAndAnswer(BaseModel):
    """Keep the public envelope while requiring generated answers."""

    search_results: list[MinimalAnswer]
    k: int = Field(ge=0, strict=True)

    @model_validator(mode="after")
    def check_answer_results(self) -> "StudentSearchResultsAndAnswer":
        """Reuse source validation without narrowing an inherited list."""
        StudentSearchResults(
            search_results=list(self.search_results), k=self.k)
        return self


class Passage(MinimalSource):
    """Add structural context without changing the original source span."""

    breadcrumb: str = ""

    def as_source(self) -> MinimalSource:
        """Expose only the three source fields required by the subject."""
        return MinimalSource(**self.model_dump(exclude={"breadcrumb"}))


class RankedPassage(BaseModel):
    """Pair a passage with its internal ranking score."""

    passage: Passage
    relevance: float


class BuildOptions(BaseModel):
    """Validate chunk limits and BM25 hyperparameters."""

    character_limit: int = Field(default=2000, ge=1, le=2000, strict=True)
    merge_below: int = Field(default=0, ge=0, strict=True)
    saturation: float = Field(default=1.2, gt=0)
    length_weight: float = Field(default=0.75, ge=0, le=1)

    @model_validator(mode="after")
    def check_merge_limit(self) -> "BuildOptions":
        """Keep the minimum merge threshold below the maximum size."""
        if self.merge_below > self.character_limit:
            raise ValueError("merge threshold exceeds character limit")
        return self


class BuildSummary(BaseModel):
    """Report observed indexing work and elapsed wall time."""

    discovered: int
    contributing: int
    unreadable: int
    passages: int
    elapsed: float
