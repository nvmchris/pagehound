from __future__ import annotations

import json
from pathlib import Path

import respx
from typer.testing import CliRunner

from conftest import page
from pagehound import __version__
from pagehound.cli import app

runner = CliRunner()
RECIPE = """
name: test quotes
start_urls: [https://example.test/]
item: div.quote
fields:
  author: small.author
  tags: {selector: a.tag, many: true}
next_page: li.next > a
settings: {delay: 0, backoff: 0}
"""


def _recipe(tmp_path: Path) -> Path:
    path = tmp_path / "r.yaml"
    path.write_text(RECIPE)
    return path


def _site() -> None:
    respx.get("https://example.test/robots.txt").respond(404)
    respx.get("https://example.test/").respond(200, html=page("page1.html"))
    respx.get("https://example.test/page/2/").respond(200, html=page("page2.html"))


def test_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output


@respx.mock
def test_run_writes_output(tmp_path: Path) -> None:
    _site()
    out = tmp_path / "items.json"
    result = runner.invoke(app, ["run", str(_recipe(tmp_path)), "-o", str(out)])
    assert result.exit_code == 0, result.output
    assert [i["author"] for i in json.loads(out.read_text())] == [
        "Albert Einstein",
        "J.K. Rowling",
        "Albert Einstein",
    ]


@respx.mock
def test_run_exits_nonzero_without_items(tmp_path: Path) -> None:
    respx.get("https://example.test/robots.txt").respond(404)
    respx.get("https://example.test/").respond(200, html="<html><body></body></html>")
    result = runner.invoke(app, ["run", str(_recipe(tmp_path))])
    assert result.exit_code == 1


def test_validate_shows_fields(tmp_path: Path) -> None:
    result = runner.invoke(app, ["validate", str(_recipe(tmp_path))])
    assert result.exit_code == 0, result.output
    assert "author" in result.output
    assert "many" in result.output


def test_validate_reports_errors(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("name: x\n")
    result = runner.invoke(app, ["validate", str(bad)])
    assert result.exit_code == 2
    assert "Recipe error" in result.output


@respx.mock
def test_fetch_json(tmp_path: Path) -> None:
    _site()
    result = runner.invoke(app, ["fetch", "https://example.test/", "-s", "a.tag", "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == ["change", "thinking", "choices"]
