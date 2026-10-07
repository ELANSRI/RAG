"""Segment Python at definitions using AST line numbers, never byte offsets."""

import ast
from typing import List, Sequence, Tuple

from .intervals import (
    LabeledInterval,
    finish_intervals,
    line_offsets,
    merge_short_intervals,
    segment_plain_text,
)

DEFINITION_NODES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


def first_definition_line(statement: ast.stmt) -> int:
    """Return the first line of a statement, decorators included (1-based)."""
    decorators: List[ast.expr] = getattr(statement, "decorator_list", [])
    return min([statement.lineno, *(d.lineno for d in decorators)])


def include_leading_comments(source_lines: Sequence[str], line: int) -> int:
    """Move a 0-based begin line up over the comments right above it."""
    while line > 0 and source_lines[line - 1].lstrip().startswith("#"):
        line -= 1
    return line


def describe_definition(statement: ast.stmt) -> str:
    """Return a short label such as ``class Foo`` or ``def bar``."""
    if isinstance(statement, ast.ClassDef):
        return f"class {statement.name}"
    if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return f"def {statement.name}"
    return ""


def segment_python(
    content: str, character_limit: int, merge_below: int = 0
) -> List[LabeledInterval]:
    """Chunk Python source on its syntactic structure.

    Top-level functions and classes become their own chunks, together
    with the comments written right above them. A class that does not
    fit in ``character_limit`` is split into its header and one chunk per
    method. Module-level code between definitions forms its own chunks.
    Anything still too long is split on blank lines, then lines. Files
    that do not parse fall back to :func:`segment_plain_text`.

    Args:
        content: Python source.
        character_limit: Maximum chunk width in characters.
        merge_below: Chunks smaller than this are merged with the next one.

    Returns:
        The chunk intervals with their ``class X > def y`` breadcrumb.
    """
    try:
        syntax_tree = ast.parse(content)
    except (SyntaxError, ValueError):
        return segment_plain_text(content, character_limit)
    source_lines = content.splitlines(keepends=True)
    offsets = line_offsets(content)

    def line_position(line: int) -> int:
        """Convert a line boundary into a character offset."""
        return offsets[min(line, len(offsets) - 1)]

    boundaries: List[Tuple[int, str]] = [(0, "")]

    def visit_definition(statement: ast.stmt, enclosing: str) -> None:
        """Record the beginning, nested definitions and end of a node."""
        label = describe_definition(statement)
        breadcrumb = f"{enclosing} > {label}" if enclosing else label
        first = include_leading_comments(
            source_lines, first_definition_line(statement) - 1
        )
        end_line = statement.end_lineno or statement.lineno
        boundaries.append((line_position(first), breadcrumb))
        if (
            isinstance(statement, ast.ClassDef)
            and line_position(end_line) - line_position(first)
            > character_limit
        ):
            for child in statement.body:
                if isinstance(child, DEFINITION_NODES):
                    visit_definition(child, breadcrumb)
        boundaries.append((line_position(end_line), enclosing))

    for statement in syntax_tree.body:
        if isinstance(statement, DEFINITION_NODES):
            visit_definition(statement, "")
    boundaries.append((len(content), ""))
    boundaries.sort(key=lambda bound: bound[0])
    intervals: List[LabeledInterval] = []
    for (begin, breadcrumb), (stop, _) in zip(boundaries, boundaries[1:]):
        if stop > begin:
            intervals.append((begin, stop, breadcrumb))
    return merge_short_intervals(
        finish_intervals(content, intervals, character_limit),
        merge_below,
        character_limit,
    )
