"""Tokenization shared by the indexer and the query side of BM25.

Questions paraphrase ideas ("sampler returns Pythonized results") but
also quote identifiers verbatim (``skip_sampler_cpu_output``). To match
both, every identifier is kept whole *and* split into its snake_case /
camelCase components, which are then stemmed.
"""

import re
from functools import lru_cache
from typing import List, Tuple

import snowballstemmer

IGNORED_WORDS = frozenset("""
    a about above after again against all am an and any are aren as at be
    because been before being below between both but by can cannot could
    couldn did didn do does doesn doing don down during each few for from
    further had hadn has hasn have haven having he her here hers herself
    him himself his how i if in into is isn it its itself just let ll me
    more most mustn my myself no nor not now of off on once only or other
    ought our ours ourselves out over own re same shan she should shouldn
    so some such than that the their theirs them themselves then there
    these they this those through to too under until up us very was wasn
    we were weren what when where which while who whom why will with won
    would wouldn you your yours yourself yourselves ve
    """.split())

IDENTIFIER_PATTERN = re.compile(r"[A-Za-z0-9_]+")
COMPONENT_PATTERN = re.compile(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|[0-9]+")
ENGLISH_STEMMER = snowballstemmer.stemmer("english")


@lru_cache(maxsize=1 << 20)
def stem_term(identifier: str) -> str:
    """Return the Snowball stem of a lower-case identifier."""
    return str(ENGLISH_STEMMER.stemWord(identifier))


@lru_cache(maxsize=1 << 20)
def expand_identifier(identifier: str) -> Tuple[str, ...]:
    """Turn one raw identifier into its index expanded.

    Args:
        identifier: A run of letters, digits and underscores.

    Returns:
        The whole identifier in lower case when it is a compound
        (``skip_sampler_cpu_output``, ``LLMEngine``), followed by the
        stemmed components that are not stopwords.
    """
    stripped = identifier.strip("_")
    if not stripped:
        return ()
    components = [
        p.lower()
        for section in stripped.split("_")
        for p in COMPONENT_PATTERN.findall(section)
    ]
    expanded: List[str] = []
    if len(components) > 1:
        expanded.append(stripped.lower())
    for component in components:
        if len(component) < 2 or component in IGNORED_WORDS:
            continue
        expanded.append(stem_term(component))
    return tuple(expanded)


def lexical_terms(content: str) -> List[str]:
    """Tokenize a content into BM25 expanded.

    Args:
        content: Any content (code, Markdown or a question).

    Returns:
        The list of expanded, in order, with repetitions.
    """
    expanded: List[str] = []
    for identifier in IDENTIFIER_PATTERN.findall(content):
        expanded.extend(expand_identifier(identifier))
    return expanded
