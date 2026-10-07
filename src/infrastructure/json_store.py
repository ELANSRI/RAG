"""Typed JSON reads and atomic file replacement."""

import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import TypeVar

from pydantic import BaseModel

Record = TypeVar("Record", bound=BaseModel)


def read_record(location: Path, schema: type[Record]) -> Record:
    """Read UTF-8 JSON and validate the entire structure."""
    return schema.model_validate_json(location.read_text(encoding="utf-8"))


def write_record(location: Path, record: BaseModel) -> Path:
    """Publish a complete JSON document with one atomic replacement."""
    location.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=location.parent,
            prefix=".pending-",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(record.model_dump_json(indent=2))
            stream.write("\n")
        os.replace(temporary, location)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return location
