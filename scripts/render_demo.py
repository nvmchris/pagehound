"""Regenerate docs/demo.svg from a real run of the quotes example.

Usage: python scripts/render_demo.py
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from rich.console import Console
from typer.testing import CliRunner

from pagehound import cli

ROOT = Path(__file__).resolve().parent.parent


class _NoLive:
    """Stand-in for rich.live.Live so spinner frames don't end up in the recording."""

    def __init__(self, *_: Any, **__: Any) -> None: ...
    def __enter__(self) -> _NoLive:
        return self

    def __exit__(self, *_: Any) -> None: ...
    def update(self, *_: Any) -> None: ...


def main() -> None:
    cli.Live = _NoLive  # type: ignore[misc,assignment]
    cli.console = Console(record=True, width=96, force_terminal=True, color_system="truecolor")
    cli.console.print("[bold green]$[/] pagehound run examples/quotes.yaml -o quotes.json\n")
    result = CliRunner().invoke(
        cli.app,
        [
            "run",
            str(ROOT / "examples/quotes.yaml"),
            "-o",
            "/tmp/pagehound-demo.json",
            "--max-pages",
            "3",
        ],
    )
    if result.exit_code != 0:
        raise SystemExit(result.output)
    svg = cli.console.export_svg(title="pagehound")
    svg = svg.replace("/tmp/pagehound-demo.json", "quotes.json")
    (ROOT / "docs/demo.svg").write_text(svg, encoding="utf-8")
    print("wrote docs/demo.svg")


if __name__ == "__main__":
    main()
