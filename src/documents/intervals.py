"""Shared character-interval operations; offsets always refer to original
content."""

import re
from typing import List, Optional, Sequence, Tuple

Interval = Tuple[int, int]
LabeledInterval = Tuple[int, int, str]
BREAK_MARKERS = ("\n\n", "\n", " ")


def line_offsets(content: str) -> List[int]:
    """Return the line_position of every line begin, plus ``len(content)``."""
    offsets = [0]
    for match in re.finditer("\n", content):
        offsets.append(match.end())
    if offsets[-1] != len(content):
        offsets.append(len(content))
    return offsets


def trim_interval(content: str, begin: int, stop: int) -> Optional[Interval]:
    """Shrink a span so it neither offsets nor ends with whitespace."""
    while begin < stop and content[begin].isspace():
        begin += 1
    while stop > begin and content[stop - 1].isspace():
        stop -= 1
    return (begin, stop) if begin < stop else None


def separator_ends(
    content: str, begin: int, stop: int, separator: str
) -> List[int]:
    """Return the offsets right after each separator inside a span."""
    cuts: List[int] = []
    position = content.find(separator, begin, stop)
    while position != -1:
        cut = position + len(separator)
        if begin < cut < stop:
            cuts.append(cut)
        position = content.find(separator, cut, stop)
    return cuts


def pack_intervals(
    intervals: Sequence[Interval], character_limit: int
) -> List[Interval]:
    """Greedily merge consecutive intervals while they fit in
    ``character_limit``."""
    packed: List[Interval] = []
    for begin, stop in intervals:
        if packed and stop - packed[-1][0] <= character_limit:
            packed[-1] = (packed[-1][0], stop)
        else:
            packed.append((begin, stop))
    return packed


def split_interval(
    content: str,
    begin: int,
    stop: int,
    character_limit: int,
    separators: Sequence[str] = BREAK_MARKERS,
) -> List[Interval]:
    """Recursively split ``content[begin:stop]`` into intervals of <=
    character_limit.

    The span is cut on the first separator that occurs in it (blank
    lines, then lines, then spaces); fragments that are still too
    long are
    split with the next separators, and neighbours are packed back
    together as long as they fit.

    Args:
        content: The full file content.
        begin: Start line_position of the span to split.
        stop: End line_position (exclusive) of the span to split.
        character_limit: Maximum width of a returned span.
        separators: Separators to try, from the coarsest to the finest.

    Returns:
        Contiguous intervals covering ``[begin, stop)``.
    """
    if character_limit <= 0:
        raise ValueError("character_limit must be positive")
    if stop - begin <= character_limit:
        return [(begin, stop)]
    for index, separator in enumerate(separators):
        cuts = separator_ends(content, begin, stop, separator)
        if not cuts:
            continue
        boundaries = [begin, *cuts, stop]
        fragments: List[Interval] = []
        for fragment_begin, fragment_stop in zip(boundaries, boundaries[1:]):
            fragments.extend(
                split_interval(
                    content,
                    fragment_begin,
                    fragment_stop,
                    character_limit,
                    separators[index + 1:],
                )
            )
        return pack_intervals(fragments, character_limit)
    return [
        (pos, min(pos + character_limit, stop))
        for pos in range(begin, stop, character_limit)
    ]


def finish_intervals(
    content: str, intervals: Sequence[LabeledInterval], character_limit: int
) -> List[LabeledInterval]:
    """Split oversized intervals, trim whitespace and drop empty intervals."""
    segments: List[LabeledInterval] = []
    for begin, stop, breadcrumb in intervals:
        for fragment_begin, fragment_stop in split_interval(
            content, begin, stop, character_limit
        ):
            trimmed = trim_interval(content, fragment_begin, fragment_stop)
            if trimmed is not None:
                segments.append((trimmed[0], trimmed[1], breadcrumb))
    return segments


def merge_short_intervals(
    intervals: Sequence[LabeledInterval],
    merge_below: int,
    character_limit: int,
) -> List[LabeledInterval]:
    """Merge a span smaller than ``merge_below`` into the following one."""
    merged: List[LabeledInterval] = []
    for begin, stop, breadcrumb in intervals:
        if merged:
            previous_begin, previous_stop, previous_label = merged[-1]
            if (
                previous_stop - previous_begin < merge_below
                and stop - previous_begin <= character_limit
            ):
                merged[-1] = (
                    previous_begin,
                    stop,
                    previous_label or breadcrumb,
                )
                continue
        merged.append((begin, stop, breadcrumb))
    return merged


def segment_plain_text(
    content: str, character_limit: int
) -> List[LabeledInterval]:
    """Chunk plain content on paragraphs, then lines, then words.

    Args:
        content: File content.
        character_limit: Maximum chunk width in characters.

    Returns:
        The chunk intervals, without breadcrumb.
    """
    return finish_intervals(content, [(0, len(content), "")], character_limit)
