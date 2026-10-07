"""Public Fire commands: parameters and JSON keys follow the assignment."""

import sys
from pathlib import Path

from src.application.arguments import checked, positive_integer, query_text
from src.application.assessment import assess_retrieval
from src.application.batches import answer_results
from src.application.build import build_index
from src.domain.contracts import (
    BuildOptions,
    MinimalSearchResults,
    RagDataset,
    StudentSearchResults,
    UnansweredQuestion,
)
from src.generation.local_model import DEFAULT_MODEL, LocalResponder
from src.infrastructure.json_store import read_record, write_record
from src.retrieval.search import SearchEngine
from src.retrieval.semantic import DEFAULT_ENCODER


class Commands:
    """Index the corpus, retrieve evidence, generate answers and evaluate."""

    @checked
    def index(
        self,
        max_chunk_size: int = 2000,
        raw_dir: str = "data/raw",
        index_dir: str = "data/processed",
        min_chunk_size: int = 0,
        semantic: bool = False,
        embedding_model: str = DEFAULT_ENCODER,
    ) -> None:
        """Build BM25, optionally adding semantic vectors."""
        if not isinstance(semantic, bool):
            raise ValueError("semantic must be True or False")
        settings = BuildOptions(
            character_limit=max_chunk_size, merge_below=min_chunk_size
        )
        summary = build_index(
            Path(raw_dir), Path(index_dir), settings, semantic, embedding_model
        )
        print(
            f"Indexed {summary.passages} chunks from "
            f"{summary.contributing}/{summary.discovered} files "
            f"({summary.unreadable} unreadable) in {summary.elapsed:.2f}s"
        )
        print(f"Ingestion complete! Indices saved under {index_dir}")

    @checked
    def search(
        self,
        query: str,
        k: int = 10,
        index_dir: str = "data/processed",
        mode: str = "bm25",
        as_json: bool = False,
        output_path: str = "data/output/single/search.json",
    ) -> None:
        """Search one question and always save the public JSON envelope."""
        wording = query_text(query)
        requested = positive_integer(k, "k", minimum=0)
        matches = SearchEngine(Path(index_dir), mode).find(wording, requested)
        question = UnansweredQuestion(question=wording)
        result = MinimalSearchResults(
            question_id=question.question_id,
            question=wording,
            retrieved_sources=[match.passage.as_source() for match in matches],
        )
        envelope = StudentSearchResults(search_results=[result], k=requested)
        target = write_record(Path(output_path), envelope)
        if as_json:
            print(envelope.model_dump_json(indent=2))
        else:
            print(f"Top {len(matches)} sources for: {wording}")
            for rank, match in enumerate(matches, start=1):
                passage = match.passage
                print(
                    f"{rank}. {passage.file_path} "
                    f"[{passage.first_character_index}:"
                    f"{passage.last_character_index}] "
                    f"score={match.relevance:.2f} ({passage.breadcrumb})"
                )
        print(f"Saved search results to {target}", file=sys.stderr)

    @checked
    def search_dataset(
        self,
        dataset_path: str,
        k: int = 10,
        save_directory: str = "data/output/search_results",
        index_dir: str = "data/processed",
        mode: str = "bm25",
    ) -> None:
        """Search questions only, even when the input also contains answers."""
        requested = positive_integer(k, "k", minimum=0)
        dataset = read_record(Path(dataset_path), RagDataset)
        questions = [
            UnansweredQuestion(
                question_id=entry.question_id, question=entry.question
            )
            for entry in dataset.rag_questions
        ]
        envelope = SearchEngine(Path(index_dir), mode).run_batch(
            questions, requested
        )
        target = write_record(
            Path(save_directory) / Path(dataset_path).name, envelope
        )
        print(f"Saved student_search_results to {target}")

    @checked
    def answer(
        self,
        query: str,
        k: int = 5,
        index_dir: str = "data/processed",
        mode: str = "bm25",
        model_name: str = DEFAULT_MODEL,
        max_context_tokens: int = 3000,
        max_new_tokens: int = 256,
        as_json: bool = False,
        output_path: str = "data/output/single/answer.json",
        device: str | None = None,
    ) -> None:
        """Retrieve evidence, generate locally and save the answer JSON."""
        wording = query_text(query)
        requested = positive_integer(k, "k", minimum=0)
        question = UnansweredQuestion(question=wording)
        retrieved = SearchEngine(Path(index_dir), mode).run_batch(
            [question], requested
        )
        responder = LocalResponder(
            model_name,
            positive_integer(max_context_tokens, "context tokens"),
            positive_integer(max_new_tokens, "answer tokens"),
            device,
        )
        envelope = answer_results(retrieved, responder)
        target = write_record(Path(output_path), envelope)
        if as_json:
            print(envelope.model_dump_json(indent=2))
        else:
            print(
                f"Question: {wording}\n\n"
                f"Answer: {envelope.search_results[0].answer}\n\nSources:"
            )
            for source in envelope.search_results[0].retrieved_sources:
                print(
                    f"  {source.file_path} "
                    f"[{source.first_character_index}:"
                    f"{source.last_character_index}]"
                )
        print(f"Saved answers to {target}", file=sys.stderr)

    @checked
    def answer_dataset(
        self,
        student_search_results_path: str,
        save_directory: str = "data/output/search_results_and_answer",
        model_name: str = DEFAULT_MODEL,
        max_context_tokens: int = 3000,
        max_new_tokens: int = 256,
        device: str | None = None,
    ) -> None:
        """Generate from saved retrieval results, without re-running search."""
        retrieved = read_record(
            Path(student_search_results_path), StudentSearchResults
        )
        responder = LocalResponder(
            model_name,
            positive_integer(max_context_tokens, "context tokens"),
            positive_integer(max_new_tokens, "answer tokens"),
            device,
        )
        envelope = answer_results(retrieved, responder)
        target = write_record(
            Path(save_directory) / Path(student_search_results_path).name,
            envelope,
        )
        print(f"Saved student_search_results_and_answer to {target}")

    @checked
    def evaluate(
        self,
        student_search_results_path: str,
        dataset_path: str,
        max_context_length: int = 2000,
        output_path: str = "data/output/evaluation/report.json",
    ) -> None:
        """Calculate local recall; never import or call the moulinette."""
        predictions = read_record(
            Path(student_search_results_path), StudentSearchResults
        )
        reference = read_record(Path(dataset_path), RagDataset)
        report = assess_retrieval(
            predictions,
            reference,
            positive_integer(max_context_length, "max_context_length"),
        )
        write_record(Path(output_path), report)
        print(
            f"Local evaluation: {report.evaluated_questions} questions, "
            f"{report.missing_questions} missing"
        )
        for cutoff, recall in report.recall.items():
            print(f"Recall@{cutoff}: {recall:.3f}")
        print(
            "Official validation must be run separately with the moulinette."
        )
