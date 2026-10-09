*This project has been created as part of the 42 curriculum by eanass.*

# RAG against the machine — reorganized teaching version

## Description

A refactoring of the supplied student project: structure-aware Python and
Markdown segmentation, sparse BM25 search, local Qwen/Qwen3-0.6B generation,
validated JSON outputs, and local retrieval evaluation. Optional semantic and
hybrid retrieval are retained. Replace `<login>` before submission.

The French guides in `docs/` explain the original code, the new architecture,
and every line of the delivered Python source. This version is derived from
the original; the segmentation and tokenization algorithms are deliberately
preserved rather than claimed as new inventions.

## Instructions

Use Python 3.10+ and uv. `.python-version` selects 3.12 for development.
Dependencies and the original lockfile are retained. Linux uses CPU torch wheels.
Prepare enough disk space for dependencies and local model weights.

```bash
uv sync
mkdir -p data/raw data/datasets
# Extract vllm-0.10.1/ under data/raw/.
# Copy datasets_public/public/{AnsweredQuestions,UnansweredQuestions}
# under data/datasets/.
uv run python -m src index --max_chunk_size 2000
uv run python -m src search "What is VLLM_RPC_TIMEOUT?" --k 5
uv run python -m src answer "What is VLLM_RPC_TIMEOUT?" --k 5
```

Rebuild the index: the new version-2 manifest is not compatible with the old
index format. Paths are project-relative; run from the repository root.
No corpus, model weights or generated indexes are included in this archive.

Single-query commands always write a public Student envelope:
`data/output/single/search.json` and `data/output/single/answer.json`.
Use `--output_path PATH` to change either destination. Existing outputs at the
same path are replaced. `--as_json True` prints that envelope on stdout;
progress and save messages use stderr where applicable.

## Example usage

```bash
uv run python -m src search_dataset \
  --dataset_path data/datasets/UnansweredQuestions/dataset_docs_public.json \
  --k 10 --save_directory data/output/search_results/UnansweredQuestions

uv run python -m src evaluate \
  --student_search_results_path data/output/search_results/UnansweredQuestions/dataset_docs_public.json \
  --dataset_path data/datasets/AnsweredQuestions/dataset_docs_public.json \
  --output_path data/output/evaluation/docs.json

uv run python -m src answer_dataset \
  --student_search_results_path data/output/search_results/UnansweredQuestions/dataset_docs_public.json \
  --save_directory data/output/search_results_and_answer/UnansweredQuestions
```

Repeat with `dataset_code_public.json` for code questions. Keep dataset scopes
in output directory names to avoid overwriting identically named datasets.
All six commands remain available. `index` accepts `--raw_dir`, `--index_dir`,
`--max_chunk_size` (1–2000), `--min_chunk_size`, `--semantic` and
`--embedding_model`. Search commands accept `--index_dir` and `--mode`.
Answer commands accept `--model_name`, `--max_context_tokens`,
`--max_new_tokens`, and `--device cpu|mps|cuda`. `--k 0` produces no sources.

```bash
uv run python -m src index --semantic True
uv run python -m src search "LoRA adapters" --k 5 --mode hybrid
```

Run the supplied official executable separately when available:

```bash
./moulinette evaluate_student_search_results \
  data/output/search_results/UnansweredQuestions/dataset_docs_public.json \
  data/datasets/AnsweredQuestions/dataset_docs_public.json \
  --k 10 --max_context_length 2000
```

The application never imports or calls the moulinette.

## System architecture

| Package | Responsibility |
|---|---|
| domain | Pydantic contracts and invariants |
| documents | Original text, offsets, Python AST and Markdown chunking |
| retrieval | Lexical terms, BM25, top-k, optional vectors and fusion |
| generation | Exact chat-template budgeting and local inference |
| infrastructure | JSON persistence and versioned index manifest |
| application | Indexing, batches, argument guards and local evaluation |

`manifest.json` holds the validated passage table, corpus path and options.
`lexical.npz` holds BM25 weights, `vocabulary.json` maps terms to columns.
Optional `vectors.npy` and `encoder.json` hold the semantic index. A completed
manifest is published last. Concurrent indexing/search is not supported.

## Chunking strategy

Python definitions use AST line numbers, decorators and preceding comments.
Large classes split into methods. Markdown splits at headings outside fences.
Long intervals split at paragraphs, lines and spaces, with a strict fallback.
Offsets reference original text; every retrieved span is <=2000 characters.
Paths and structural breadcrumbs contribute to search, not to source offsets.
All 25298 default passage intervals match the original algorithm on 1847 files.

## Retrieval method

BM25 uses k1=1.2 and b=0.75, precomputed in a sparse matrix. Whole identifiers
and their split/stemmed components are indexed. Positive scores are sorted by
score and then passage position for deterministic ties. TF-IDF is not used.
Hybrid ranking combines min-max-normalized top-100 scores with lexical weight
1 and semantic weight 0.25, inherited from the original implementation.

## Performance analysis

Measured locally in this execution environment, not on the user's Mac:

| Dataset | Questions | R@1 | R@3 | R@5 | R@10 |
|---|---:|---:|---:|---:|---:|
| Docs | 100 | .650 | .850 | .890 | .930 |
| Code | 99 | .586 | .818 | .869 | .919 |

Indexing: 5.92 s, 1969 discovered files, 1847 contributing files, 25298 passages.
Batch throughput: 200 questions in about 0.82 s including subprocess startup
and index loading (199 public questions plus one repeated question with a new
ID). These are local measurements using IoU >=0.05, not official certification.
The original README's official and semantic scores are not repeated as verified
claims. Tie-breaking explains small differences at recall@1 and recall@3.

## Validation and limitations

- 29 offline tests pass, including offsets, Unicode, malformed references,
  duplicate IDs, out-of-file spans, prompt budgets, persistence and CLI errors.
- Flake8 and mypy with the assignment's mandatory flags pass.
- Real lexical indexing/search/evaluation ran on both supplied datasets.
- Qwen generation and actual embedding inference were NOT run here: model
  weights and the deep-learning stack were not installed for these checks.
- Prompt budgeting was tested with an injected deterministic tokenizer.
- The official moulinette was not supplied and was NOT executed.
- The dependency lockfile was retained; a complete uv sync with torch was not
  executed in this environment. Tests used an isolated lightweight environment.
- Corpus changes require reindexing. Existing source spans are not hash-checked.
- `retrieved_sources` reports retrieval candidates; the prompt may contain only
  a fitting prefix/subset. It is not a list of independently verified citations.
- Small context limits can leave no usable evidence. The program then returns
  a clear no-evidence answer without claiming a factual result.

## Design decisions and challenges

Separate disk I/O from search, and prompt composition from model execution,
so each can be understood and tested independently. Keep official public
field names while renaming internal concepts. Reject malformed answered
entries before union validation can silently discard their reference fields.
Count full formatted prompts rather than estimating a fixed source-header cost.
Use atomic single-file JSON replacement and publish index completion last.
A stable full sort replaces argpartition; it remains fast on the measured corpus.

Make targets: install, run, debug, clean, lint, lint-strict and test.
`make run` defaults to indexing; override with `ARGS='search "LoRA" --k 5'`.
Tests are development aids; follow the subject's submission policy for tests.
No API, incremental indexing or complete query-result caching bonus is claimed.

## Resources and AI use

- The supplied RAG subject (version 2.0), datasets, vLLM 0.10.1 and rag.zip.
- https://huggingface.co/Qwen/Qwen3-0.6B
- https://docs.pydantic.dev/latest/concepts/validators/
- https://nlp.stanford.edu/IR-book/
- https://docs.astral.sh/uv/

An AI coding assistant analyzed the supplied implementation, reorganized its
modules, renamed internal concepts, rewrote persistence/CLI/context handling,
added regression tests and produced the French teaching guide. Understand,
review and adapt every part before evaluation; do not claim tests or official
results that were not performed. The original algorithmic provenance is
preserved in the accompanying analysis.
