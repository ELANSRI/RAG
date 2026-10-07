"""Regression tests for offsets, contracts, retrieval and prompt budgets."""

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError

from src.application.assessment import assess_retrieval, interval_overlap
from src.application.build import build_index
from src.documents.files import PassageReader
from src.documents.intervals import segment_plain_text
from src.documents.markdown import segment_markdown
from src.documents.python_code import segment_python
from src.domain.contracts import (
    BuildOptions,
    MinimalSource,
    RagDataset,
    StudentSearchResults,
)
from src.generation.context import ContextComposer
from src.generation.local_model import LocalResponder, NO_EVIDENCE
from src.infrastructure.index_store import load_manifest
from src.retrieval.lexical import LexicalMatrix
from src.retrieval.search import SearchEngine, best_positions, blend_rankings
from src.retrieval.terms import lexical_terms


@pytest.mark.parametrize("limit", [1, 23, 100, 2000])
def test_unicode_offsets_and_limits(limit: int) -> None:
    """All strategies retain exact Unicode character slices."""
    content = '# Café\n\ndef f():\n    """été"""\n    return "salut"\n'
    for strategy in (segment_plain_text, segment_python, segment_markdown):
        pieces = strategy(content, limit)
        assert pieces
        assert all(
            0 <= left < right <= len(content) and right - left <= limit
            for left, right, _ in pieces
        )
        # Every non-whitespace character must remain covered.
        covered = {
            position
            for left, right, _ in pieces
            for position in range(left, right)
        }
        assert all(
            index in covered or char.isspace()
            for index, char in enumerate(content)
        )


def test_invalid_python_fallback() -> None:
    """An invalid Python file remains searchable as ordinary text."""
    content = "def broken(:\n    pass\n"
    assert segment_python(content, 100) == segment_plain_text(content, 100)


def test_markdown_fences() -> None:
    """Code comments inside fences must not create Markdown sections."""
    content = "# Intro\nHello\n## Run\n```sh\n# comment\necho hi\n```\n"
    pieces = segment_markdown(content, 2000)
    assert [label for _, _, label in pieces] == ["Intro", "Intro > Run"]


def test_python_decorators_and_methods() -> None:
    """Decorators remain attached and large classes get method breadcrumbs."""
    content = (
        "class Example:\n    # note\n    @property\n"
        "    def first(self):\n        return 42\n\n"
        "    def second(self):\n        return 7\n"
    )
    pieces = segment_python(content, 90)
    assert any(label == "class Example > def first" for _, _, label in pieces)
    assert any(
        "@property" in content[left:right]
        and "def first" in content[left:right]
        for left, right, _ in pieces
    )


def test_identifiers_and_stems() -> None:
    """Preserve whole identifiers, parts and English stems."""
    terms = lexical_terms("skip_sampler_cpu_output in LLMEngine")
    assert {"skip_sampler_cpu_output", "sampler", "cpu", "llmengine", "engin"}
    assert all(
        term in terms
        for term in (
            "skip_sampler_cpu_output",
            "sampler",
            "cpu",
            "llmengine",
            "engin",
        )
    )
    assert "in" not in terms
    assert lexical_terms("?!") == []


def test_bm25_save_reload(tmp_path: Path) -> None:
    """Persistence preserves scores and does not assign hits to unknown
    words."""
    documents = [lexical_terms("load lora adapter"), lexical_terms("timeout")]
    matrix = LexicalMatrix.from_documents(documents)
    matrix.persist(tmp_path)
    restored = LexicalMatrix.restore(tmp_path)
    scores = restored.scores_for(lexical_terms("lora"))
    np.testing.assert_allclose(
        scores, matrix.scores_for(lexical_terms("lora"))
    )
    assert best_positions(scores, 5).tolist() == [0]
    assert restored.scores_for(["zzzz"]).sum() == 0


def test_ties_are_deterministic() -> None:
    """Ties at the cutoff resolve by passage order, including k=0."""
    scores = np.array([2, 2, 0, 2, np.nan], dtype=np.float32)
    assert best_positions(scores, 2).tolist() == [0, 1]
    assert best_positions(scores, 0).tolist() == []


def test_hybrid_combines_evidence() -> None:
    """A document strong in both rankers can beat the lexical winner."""
    mixed = blend_rankings(
        [
            (np.array([3, 2.5, 0, 1]), 1),
            (np.array([0.1, 0.9, 0.5, 0.2]), 1),
        ]
    )
    assert int(np.argmax(mixed)) == 1


@pytest.mark.parametrize("begin,end", [(-1, 5), (4, 4), (5, 2)])
def test_bad_source_intervals(begin: int, end: int) -> None:
    """Reject intervals which could silently select incorrect source text."""
    with pytest.raises(ValidationError):
        MinimalSource(
            file_path="a.py",
            first_character_index=begin,
            last_character_index=end,
        )


def test_corrupt_reference_cannot_become_unanswered() -> None:
    """A malformed reference cannot pass through the union's simpler branch."""
    with pytest.raises(ValidationError):
        RagDataset.model_validate(
            {
                "rag_questions": [
                    {"question": "q", "answer": "a", "sources": "bad"}
                ]
            }
        )


def test_duplicates_and_oversized_results() -> None:
    """Detect ambiguous IDs and invalid result lengths."""
    with pytest.raises(ValidationError):
        RagDataset.model_validate(
            {
                "rag_questions": [
                    {"question_id": "same", "question": "a"},
                    {"question_id": "same", "question": "b"},
                ]
            }
        )
    with pytest.raises(ValidationError):
        StudentSearchResults.model_validate(
            {
                "k": 1,
                "search_results": [
                    {
                        "question_id": "q",
                        "question": "q",
                        "retrieved_sources": [
                            {
                                "file_path": "a",
                                "first_character_index": 0,
                                "last_character_index": 2001,
                            }
                        ],
                    }
                ],
            }
        )


def test_source_reader_rejects_out_of_file(tmp_path: Path) -> None:
    """Out-of-file offsets must not silently yield truncated source text."""
    path = tmp_path / "sample.py"
    path.write_text("hello", encoding="utf-8")
    reference = MinimalSource(
        file_path=str(path), first_character_index=0, last_character_index=50
    )
    with pytest.raises(ValueError):
        PassageReader().extract(reference)


class CharacterTokenizer:
    """Use one character per token for deterministic offline prompt tests."""

    def encode(
        self, content: str, add_special_tokens: bool = False
    ) -> list[int]:
        """Return one token for each input character."""
        return [ord(char) for char in content]

    def apply_chat_template(
        self, messages: list[dict[str, str]], **options: object
    ) -> str:
        """Include roles as formatting overhead."""
        return "\n".join(
            item["role"] + ":" + item["content"] for item in messages
        )


@pytest.mark.parametrize("budget", [1, 20, 100, 500])
def test_context_budget_never_negative(tmp_path: Path, budget: int) -> None:
    """Headers and the full template count toward the measured budget."""
    document = tmp_path / "context.txt"
    document.write_text("evidence " * 100, encoding="utf-8")
    source = MinimalSource(
        file_path=str(document),
        first_character_index=0,
        last_character_index=900,
    )
    composer = ContextComposer(CharacterTokenizer(), PassageReader())
    baseline = composer.measure(composer.render("question", []))
    prompt = composer.compose("question", [source], budget, baseline + 1000)
    assert prompt is None or composer.measure(prompt) <= baseline + budget


def test_question_too_long() -> None:
    """Reject the prompt even before excerpts if base instructions do not
    fit."""
    composer = ContextComposer(CharacterTokenizer(), PassageReader())
    with pytest.raises(ValueError):
        composer.compose("question", [], 50, 1)


def test_no_evidence_does_not_load_model() -> None:
    """Empty retrieval must work even when torch and model weights are
    absent."""
    responder = LocalResponder()
    assert responder.respond("question", []) == NO_EVIDENCE
    assert responder.network is None


def test_index_search_and_single_json(tmp_path: Path) -> None:
    """Exercise real CLI persistence without loading a language model."""
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "envs.py").write_text(
        "# Timeout in ms\nVLLM_RPC_TIMEOUT = 10000\n", encoding="utf-8"
    )
    destination = tmp_path / "index"
    build_index(raw, destination, BuildOptions())
    engine = SearchEngine(destination)
    assert engine.find("VLLM_RPC_TIMEOUT", 1)
    assert engine.find("VLLM_RPC_TIMEOUT", 0) == []
    assert engine.find("   ", 1) == []
    output = tmp_path / "answer.json"
    process = subprocess.run(
        [
            sys.executable,
            "-m",
            "src",
            "answer",
            "VLLM_RPC_TIMEOUT",
            "--k",
            "0",
            "--index_dir",
            str(destination),
            "--output_path",
            str(output),
            "--as_json",
            "True",
        ],
        text=True,
        capture_output=True,
    )
    assert process.returncode == 0, process.stderr
    payload = json.loads(process.stdout)
    assert payload == json.loads(output.read_text())
    assert payload["search_results"][0]["answer"] == NO_EVIDENCE
    # Corrupt the manifest: validation must fail rather than zip-truncate rows.
    manifest = json.loads((destination / "manifest.json").read_text())
    manifest["passages"][0]["last_character_index"] = -1
    (destination / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValidationError):
        load_manifest(destination)


def test_evaluation_counts_missing_questions() -> None:
    """Missing predictions reduce recall instead of shrinking its
    denominator."""
    source = {
        "file_path": "a.py",
        "first_character_index": 100,
        "last_character_index": 200,
    }
    reference = RagDataset.model_validate(
        {
            "rag_questions": [
                {
                    "question_id": str(number),
                    "question": "q",
                    "answer": "a",
                    "sources": [source],
                }
                for number in (1, 2)
            ]
        }
    )
    predictions = StudentSearchResults.model_validate(
        {
            "k": 5,
            "search_results": [
                {
                    "question_id": "1",
                    "question": "q",
                    "retrieved_sources": [source],
                }
            ],
        }
    )
    report = assess_retrieval(predictions, reference)
    assert report.recall[5] == 0.5
    assert report.missing_questions == 1
    first = MinimalSource.model_validate(source)
    second = MinimalSource(
        file_path="a.py", first_character_index=0, last_character_index=1000
    )
    assert interval_overlap(first, second) == 0.1


@pytest.mark.parametrize(
    "arguments",
    [
        ["search", "", "--k", "5"],
        ["search", "q", "--k", "-1"],
        ["index", "--max_chunk_size", "0"],
        ["search_dataset", "--dataset_path", "does-not-exist.json"],
    ],
)
def test_cli_errors_have_no_traceback(arguments: list[str]) -> None:
    """Degenerate inputs produce a concise message and nonzero status."""
    process = subprocess.run(
        [sys.executable, "-m", "src", *arguments],
        text=True,
        capture_output=True,
    )
    assert process.returncode != 0
    assert "Error:" in process.stderr
    assert "Traceback" not in process.stderr
