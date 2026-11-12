"""Command-line interface: ``pagehound run|fetch|validate``."""

from __future__ import annotations

import asyncio
import contextlib
import json
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

from . import __version__
from .crawler import Crawler, CrawlStats
from .exporters import FORMATS, Exporter, Format, infer_format
from .extract import extract_field
from .recipe import FieldSpec, Recipe, RecipeError

app = typer.Typer(
    name="pagehound",
    help="[bold]pagehound[/] - sniff out structured data from the web. :dog:",
    rich_markup_mode="rich",
    no_args_is_help=True,
    add_completion=False,
)
console = Console(stderr=True)
ACCENT = "dark_orange"


def _version(value: bool) -> None:
    if value:
        console.print(f"pagehound [bold {ACCENT}]{__version__}[/]")
        raise typer.Exit


@app.callback()
def main(
    version: Annotated[
        bool | None,
        typer.Option("--version", "-V", callback=_version, is_eager=True, help="Show version."),
    ] = None,
) -> None:
    """Async, polite web scraper driven by declarative YAML recipes."""


def _load(recipe_path: Path) -> Recipe:
    try:
        return Recipe.from_yaml(recipe_path)
    except RecipeError as exc:
        console.print(Panel(str(exc), title="[red]Recipe error", border_style="red"))
        raise typer.Exit(2) from exc


def _status(stats: CrawlStats, last_url: str) -> Group:
    line = Text.assemble(
        ("pages ", "dim"),
        (str(stats.pages_ok), "bold green"),
        ("  items ", "dim"),
        (str(stats.items), f"bold {ACCENT}"),
        ("  failed ", "dim"),
        (str(stats.pages_failed), "bold red" if stats.pages_failed else "dim"),
        ("  ", ""),
        (f"{stats.elapsed:5.1f}s", "dim"),
    )
    return Group(Spinner("dots", text=line, style=ACCENT), Text(f"  {last_url}", style="dim"))


def _summary(stats: CrawlStats, output: str | None) -> Table:
    table = Table.grid(padding=(0, 2))
    table.add_column(style="dim")
    table.add_column(style="bold")
    table.add_row("Items", f"[{ACCENT}]{stats.items}[/]")
    table.add_row("Pages", f"[green]{stats.pages_ok}[/] ok, [red]{stats.pages_failed}[/] failed")
    if stats.pages_blocked:
        table.add_row("Robots", f"[yellow]{stats.pages_blocked}[/] blocked")
    table.add_row("Retries", str(stats.retries))
    rate = stats.items / stats.elapsed if stats.elapsed else 0
    table.add_row("Time", f"{stats.elapsed:.2f}s ({rate:.1f} items/s)")
    if output:
        table.add_row("Output", output)
    return table


def _preview(items: list[dict[str, Any]], fields: list[str]) -> Table:
    table = Table(
        title="Preview",
        title_style="bold",
        header_style=f"bold {ACCENT}",
        expand=len(fields) > 3,
    )
    for name in fields:
        table.add_column(name, overflow="ellipsis", ratio=1, no_wrap=True)
    for item in items:
        table.add_row(*(_short(item.get(name)) for name in fields))
    return table


def _short(value: Any) -> str:
    if isinstance(value, list):
        return ", ".join(map(str, value))
    return "" if value is None else str(value)


@app.command()
def run(
    recipe_path: Annotated[Path, typer.Argument(metavar="RECIPE", help="Path to a YAML recipe.")],
    output: Annotated[
        str | None, typer.Option("--output", "-o", help="Output file, or '-' for stdout.")
    ] = None,
    fmt: Annotated[
        str | None, typer.Option("--format", "-f", help=f"One of {', '.join(FORMATS)}.")
    ] = None,
    max_pages: Annotated[int | None, typer.Option(help="Override max pages per start URL.")] = None,
    max_items: Annotated[int | None, typer.Option(help="Stop after this many items.")] = None,
    concurrency: Annotated[int | None, typer.Option("--concurrency", "-c")] = None,
    delay: Annotated[float | None, typer.Option(help="Seconds between requests per host.")] = None,
    no_robots: Annotated[bool, typer.Option("--no-robots", help="Ignore robots.txt.")] = False,
    preview: Annotated[int, typer.Option(help="Rows to preview after the crawl.")] = 5,
) -> None:
    """Run a [bold]recipe[/] and export the items."""
    recipe = _load(recipe_path)
    overrides: dict[str, Any] = {
        "max_pages": max_pages,
        "max_items": max_items,
        "concurrency": concurrency,
        "delay": delay,
    }
    overrides = {k: v for k, v in overrides.items() if v is not None}
    if no_robots:
        overrides["respect_robots"] = False
    if overrides:
        recipe = recipe.model_copy(
            update={"settings": recipe.settings.model_copy(update=overrides)}
        )

    export_format: Format | None = None
    if output:
        try:
            export_format = fmt if fmt in FORMATS else infer_format(output)
        except ValueError as exc:
            console.print(f"[red]error:[/] {exc}")
            raise typer.Exit(2) from exc
    elif fmt:
        console.print("[red]error:[/] --format requires --output")
        raise typer.Exit(2)

    console.print(
        Panel.fit(
            f"[bold]{recipe.name}[/]\n[dim]{recipe.description or recipe.start_urls[0]}[/]",
            title=f"[{ACCENT}]pagehound[/]",
            border_style=ACCENT,
        )
    )
    stats = asyncio.run(_run(recipe, output, export_format, preview))
    if stats.errors:
        console.print(f"[yellow]{len(stats.errors)} problem(s):[/]")
        for err in stats.errors[:10]:
            console.print(f"  [dim]-[/] {err}")
    if stats.items == 0:
        raise typer.Exit(1)


async def _run(recipe: Recipe, output: str | None, fmt: Format | None, preview: int) -> CrawlStats:
    fields = list(recipe.fields)
    sample: list[dict[str, Any]] = []
    last_url = recipe.start_urls[0]

    def on_page(url: str, _page: int) -> None:
        nonlocal last_url
        last_url = url

    async with Crawler(recipe, on_page=on_page) as crawler:
        exporter = Exporter(output, fmt, fields) if output and fmt else None
        with (
            Live(console=console, transient=True, refresh_per_second=12) as live,
            exporter or contextlib.nullcontext(),
        ):
            live.update(_status(crawler.stats, last_url))
            async for item in crawler.stream():
                if exporter:
                    exporter.write(item)
                if len(sample) < preview:
                    sample.append(item)
                live.update(_status(crawler.stats, last_url))
        stats = crawler.stats

    if sample:
        console.print(_preview(sample, fields))
    if not output and stats.items:
        console.print("[dim]tip: add[/] -o items.json [dim]to save the results[/]")
    console.print(Panel(_summary(stats, output), title="Done", border_style="green", expand=False))
    return stats


@app.command()
def fetch(
    url: Annotated[str, typer.Argument(help="Page to fetch.")],
    select: Annotated[str, typer.Option("--select", "-s", help="CSS selector (::attr() ok).")],
    attr: Annotated[str | None, typer.Option("--attr", "-a", help="Attribute to read.")] = None,
    as_json: Annotated[bool, typer.Option("--json", help="Print a JSON array.")] = False,
) -> None:
    """Fetch one page and print every match of a CSS selector. Great for exploring a site."""
    spec = FieldSpec(selector=select, attr=attr, many=True, transforms=["url"] if attr else [])
    recipe = Recipe(name="fetch", start_urls=[url], fields={"value": spec})

    async def go() -> list[Any]:
        from selectolax.lexbor import LexborHTMLParser

        async with Crawler(recipe) as crawler:
            response = await crawler.fetch(url)
            tree = LexborHTMLParser(response.text)
            root = tree.body or tree.root
            return list(extract_field(root, spec, str(response.url))) if root else []

    try:
        values = asyncio.run(go())
    except Exception as exc:
        console.print(f"[red]error:[/] {exc}")
        raise typer.Exit(1) from exc
    if as_json:
        typer.echo(json.dumps(values, ensure_ascii=False, indent=2))
        return
    for i, value in enumerate(values, 1):
        console.print(f"[dim]{i:>3}[/] {value}", highlight=False, soft_wrap=True)
    console.print(f"[{ACCENT}]{len(values)}[/] match(es) for [bold]{select}[/]")


@app.command()
def validate(
    recipe_path: Annotated[Path, typer.Argument(metavar="RECIPE", help="Path to a YAML recipe.")],
) -> None:
    """Check a recipe and show how pagehound understood it."""
    recipe = _load(recipe_path)
    tree = Tree(f"[bold green]✔[/] [bold]{recipe.name}[/]")
    urls = tree.add("[dim]start_urls[/]")
    for u in recipe.start_urls:
        urls.add(u)
    tree.add(f"[dim]item[/] {recipe.item or '(whole page)'}")
    fields = tree.add("[dim]fields[/]")
    for name, spec in recipe.fields.items():
        bits = [f"[{ACCENT}]{name}[/]", spec.selector]
        if spec.attr:
            bits.append(f"[cyan]@{spec.attr}[/]")
        if spec.many:
            bits.append("[magenta]\\[many][/]")
        if spec.transforms:
            bits.append("[dim]| " + " | ".join(spec.transforms) + "[/]")
        fields.add(" ".join(bits))
    if recipe.next_page:
        tree.add(f"[dim]next_page[/] {recipe.next_page}")
    s = recipe.settings
    tree.add(
        f"[dim]settings[/] concurrency={s.concurrency} delay={s.delay}s "
        f"max_pages={s.max_pages} robots={'on' if s.respect_robots else 'off'}"
    )
    console.print(tree)
