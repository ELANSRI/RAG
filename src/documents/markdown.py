"""Segment Markdown at headings outside fenced code blocks."""

import re
from typing import List, Optional, Tuple

from .intervals import LabeledInterval, finish_intervals, line_offsets

HEADING_PATTERN = re.compile(r"#{1,6}(?=\s)")
FENCE_PATTERN = re.compile(r"[ \t]*(`{3,}|~{3,})")


def segment_markdown(
    content: str, character_limit: int
) -> List[LabeledInterval]:
    """Chunk Markdown on its heading_stack, then on paragraphs.

    Each heading opens a new section; heading_stack inside fenced code blocks
    are ignored. A section keeps its heading path (``Title > Sub``) as
    breadcrumb. Sections that are too long are split on blank lines,
    then
    lines.

    Args:
        content: Markdown content.
        character_limit: Maximum chunk width in characters.

    Returns:
        The chunk intervals with their heading path.
    """
    sections: List[LabeledInterval] = []
    heading_stack: List[Tuple[int, str]] = []
    section_begin = 0
    breadcrumb = ""
    fence: Optional[str] = None
    offsets = line_offsets(content)
    for line_begin, line_stop in zip(offsets, offsets[1:]):
        line = content[line_begin:line_stop]
        fence_match = FENCE_PATTERN.match(line)
        if fence is not None:
            if fence_match and fence_match.group(1).startswith(fence):
                fence = None
            continue
        if fence_match:
            fence = fence_match.group(1)
            continue
        heading = HEADING_PATTERN.match(line)
        if heading is None:
            continue
        sections.append((section_begin, line_begin, breadcrumb))
        level = len(heading.group(0))
        title = line[level:].strip().strip("#").strip()
        heading_stack = [h for h in heading_stack if h[0] < level] + [
            (level, title)
        ]
        breadcrumb = " > ".join(h[1] for h in heading_stack)
        section_begin = line_begin
    sections.append((section_begin, len(content), breadcrumb))
    return finish_intervals(content, sections, character_limit)
