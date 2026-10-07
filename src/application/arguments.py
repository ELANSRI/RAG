"""Validate Fire arguments and turn expected failures into readable
messages."""

import functools
import sys
from typing import Callable, ParamSpec

Parameters = ParamSpec("Parameters")


def checked(command: Callable[Parameters, None]) -> Callable[Parameters, None]:
    """Protect the command boundary while preserving Fire's signature."""

    @functools.wraps(command)
    def invoke(*args: Parameters.args, **kwargs: Parameters.kwargs) -> None:
        """Run one command and report an actionable failure."""
        try:
            command(*args, **kwargs)
        except KeyboardInterrupt:
            print("Interrupted.", file=sys.stderr)
            raise SystemExit(130) from None
        except Exception as failure:
            print(f"Error: {failure}", file=sys.stderr)
            raise SystemExit(1) from None

    return invoke


def positive_integer(value: object, label: str, minimum: int = 1) -> int:
    """Accept integers while explicitly excluding Python booleans."""
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < minimum
    ):
        raise ValueError(f"{label} must be an integer >= {minimum}")
    return value


def query_text(value: object) -> str:
    """Reject empty text but allow numeric queries parsed by Fire."""
    wording = "" if value is None else str(value).strip()
    if not wording:
        raise ValueError("the query is empty")
    return wording
