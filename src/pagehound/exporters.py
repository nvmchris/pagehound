"""Streaming exporters: items are written as they arrive, never buffered in memory."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from types import TracebackType
from typing import IO, Any, Literal

Format = Literal["json", "jsonl", "csv"]
FORMATS: tuple[Format, ...] = ("json", "jsonl", "csv")


def infer_format(path: str | Path) -> Format:
    """Guess the export format from a file extension (``-`` means stdout as JSON Lines)."""
    if str(path) == "-":
        return "jsonl"
    suffix = Path(path).suffix.lower().lstrip(".")
    if suffix == "ndjson":
        return "jsonl"
    if suffix in FORMATS:
        return suffix
    raise ValueError(f"cannot infer format from {path!r}; use one of: {', '.join(FORMATS)}")


def _cell(value: Any) -> Any:
    if isinstance(value, list):
        return "; ".join(str(v) for v in value)
    return "" if value is None else value


class Exporter:
    """Context manager that writes items to a file (or stdout) in the chosen format."""

    def __init__(self, path: str | Path, fmt: Format, fieldnames: list[str]) -> None:
        self.path = path
        self.fmt = fmt
        self.fieldnames = fieldnames
        self.count = 0
        self._fh: IO[str] | None = None
        self._csv: csv.DictWriter[str] | None = None

    def __enter__(self) -> Exporter:
        if str(self.path) == "-":
            self._fh = sys.stdout
        else:
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
            self._fh = open(self.path, "w", encoding="utf-8", newline="")
        if self.fmt == "json":
            self._fh.write("[")
        elif self.fmt == "csv":
            self._csv = csv.DictWriter(self._fh, fieldnames=self.fieldnames, extrasaction="ignore")
            self._csv.writeheader()
        return self

    def write(self, item: dict[str, Any]) -> None:
        assert self._fh is not None, "Exporter used outside of a with-block"
        if self.fmt == "json":
            prefix = "\n  " if self.count == 0 else ",\n  "
            self._fh.write(prefix + json.dumps(item, ensure_ascii=False))
        elif self.fmt == "jsonl":
            self._fh.write(json.dumps(item, ensure_ascii=False) + "\n")
        else:
            assert self._csv is not None
            self._csv.writerow({k: _cell(item.get(k)) for k in self.fieldnames})
        self.count += 1

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._fh is None:
            return
        if self.fmt == "json":
            self._fh.write("\n]\n" if self.count else "]\n")
        self._fh.flush()
        if self._fh is not sys.stdout:
            self._fh.close()
