"""Atomic JSON persistence for replay records and evaluation artifacts."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any


def write_json(path: Path, value: dict[str, Any]) -> None:
    """Preserve the existing file if serialization or temporary writing fails."""
    content = json.dumps(value, indent=2, allow_nan=False) + "\n"
    write_text(path, content)


def write_text(path: Path, content: str) -> None:
    """Replace a UTF-8 artifact atomically within its destination filesystem."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
            stream.flush()
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
