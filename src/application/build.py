"""Orchestrate corpus segmentation, lexical indexing and optional vectors."""

from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

from tqdm import tqdm

from src.documents.files import list_documents, read_document, relative_name
from src.documents.intervals import segment_plain_text
from src.documents.markdown import segment_markdown
from src.documents.python_code import segment_python
from src.domain.contracts import BuildOptions, BuildSummary, Passage
from src.infrastructure.index_store import IndexManifest, save_manifest
from src.retrieval.lexical import LexicalMatrix
from src.retrieval.semantic import DEFAULT_ENCODER, VectorCatalog
from src.retrieval.terms import lexical_terms


def build_index(
    corpus_root: Path,
    destination: Path,
    options: BuildOptions,
    semantic: bool = False,
    encoder_name: str = DEFAULT_ENCODER,
) -> BuildSummary:
    """Prepare all index files before publishing a new completion marker."""
    started = perf_counter()
    documents = list_documents(corpus_root)
    passages: list[Passage] = []
    searchable_terms: list[list[str]] = []
    embedding_texts: list[str] = []
    unreadable = 0
    for document in tqdm(documents, desc="Indexing files", unit="file"):
        try:
            content = read_document(document)
        except (OSError, UnicodeDecodeError) as failure:
            tqdm.write(f"Skipping {document}: {failure}")
            unreadable += 1
            continue
        suffix = document.suffix.lower()
        if suffix == ".py":
            intervals = segment_python(
                content, options.character_limit, options.merge_below
            )
        elif suffix == ".md":
            intervals = segment_markdown(content, options.character_limit)
        else:
            intervals = segment_plain_text(content, options.character_limit)
        for beginning, ending, breadcrumb in intervals:
            passage = Passage(
                file_path=relative_name(document),
                first_character_index=beginning,
                last_character_index=ending,
                breadcrumb=breadcrumb,
            )
            passages.append(passage)
            excerpt = content[beginning:ending]
            searchable_terms.append(
                lexical_terms(f"{passage.file_path} {breadcrumb}\n{excerpt}")
            )
            if semantic:
                embedding_texts.append(f"{breadcrumb}\n{excerpt}")
    if not passages:
        raise ValueError("no non-empty supported documents found")
    lexical = LexicalMatrix.from_documents(
        searchable_terms, options.saturation, options.length_weight
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=destination.parent) as temporary:
        staging = Path(temporary)
        lexical.persist(staging)
        if semantic:
            VectorCatalog.build(embedding_texts, encoder_name).save(staging)
        manifest = IndexManifest(
            corpus_root=relative_name(corpus_root),
            options=options,
            passages=passages,
            semantic_enabled=semantic,
        )
        save_manifest(staging, manifest)
        destination.mkdir(parents=True, exist_ok=True)
        # Invalidate the old marker before publishing the replacement files.
        (destination / "manifest.json").unlink(missing_ok=True)
        for item in staging.iterdir():
            if item.name != "manifest.json":
                item.replace(destination / item.name)
        if not semantic:
            for name in ("vectors.npy", "encoder.json"):
                (destination / name).unlink(missing_ok=True)
        (staging / "manifest.json").replace(destination / "manifest.json")
    return BuildSummary(
        discovered=len(documents),
        contributing=len({passage.file_path for passage in passages}),
        unreadable=unreadable,
        passages=len(passages),
        elapsed=perf_counter() - started,
    )
