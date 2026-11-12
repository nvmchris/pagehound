from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from pagehound import Exporter, infer_format

ITEMS = [
    {"name": "Ada", "tags": ["math", "code"], "age": None},
    {"name": "Grace", "tags": [], "age": 85},
]
FIELDS = ["name", "tags", "age"]


@pytest.mark.parametrize(
    ("path", "fmt"),
    [
        ("a.json", "json"),
        ("a.JSONL", "jsonl"),
        ("a.ndjson", "jsonl"),
        ("a.csv", "csv"),
        ("-", "jsonl"),
    ],
)
def test_infer_format(path: str, fmt: str) -> None:
    assert infer_format(path) == fmt


def test_infer_format_rejects_unknown() -> None:
    with pytest.raises(ValueError, match="cannot infer"):
        infer_format("out.xml")


def _export(path: Path, fmt: str, items: list[dict[str, object]]) -> str:
    with Exporter(path, fmt, FIELDS) as exporter:  # type: ignore[arg-type]
        for item in items:
            exporter.write(item)
    return path.read_text(encoding="utf-8")


def test_json_roundtrip(tmp_path: Path) -> None:
    assert json.loads(_export(tmp_path / "o.json", "json", ITEMS)) == ITEMS


def test_empty_json_is_valid(tmp_path: Path) -> None:
    assert json.loads(_export(tmp_path / "o.json", "json", [])) == []


def test_jsonl_one_object_per_line(tmp_path: Path) -> None:
    lines = _export(tmp_path / "o.jsonl", "jsonl", ITEMS).splitlines()
    assert [json.loads(line) for line in lines] == ITEMS


def test_csv_flattens_lists_and_nones(tmp_path: Path) -> None:
    text = _export(tmp_path / "nested" / "o.csv", "csv", ITEMS)
    rows = list(csv.DictReader(text.splitlines()))
    assert rows == [
        {"name": "Ada", "tags": "math; code", "age": ""},
        {"name": "Grace", "tags": "", "age": "85"},
    ]
