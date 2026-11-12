"""HTML extraction: turn a page into items using a recipe's CSS selectors."""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any
from urllib.parse import urljoin

from selectolax.lexbor import LexborHTMLParser, LexborNode

from .recipe import FieldSpec, Recipe, Transform

_WS = re.compile(r"\s+")
_NUMBER = re.compile(r"-?\d[\d,]*(?:\.\d+)?|-?\.\d+")


def _node_value(node: LexborNode, spec: FieldSpec) -> str | None:
    if spec.attr:
        value = node.attributes.get(spec.attr)
        return None if value is None else str(value)
    return _WS.sub(" ", node.text(deep=True, separator=" ")).strip()


def apply_transforms(value: str, transforms: Iterable[Transform], base_url: str) -> Any:
    """Apply a pipeline of transforms to a raw string value."""
    result: Any = value
    for name in transforms:
        if result is None:
            break
        text = str(result)
        if name == "strip":
            result = text.strip()
        elif name == "lower":
            result = text.lower()
        elif name == "upper":
            result = text.upper()
        elif name == "url":
            result = urljoin(base_url, text.strip())
        elif name in ("int", "float", "number"):
            match = _NUMBER.search(text)
            if not match:
                result = None
                continue
            number = float(match.group().replace(",", ""))
            result = int(number) if name == "int" else number
    return result


def extract_field(root: LexborNode, spec: FieldSpec, base_url: str) -> Any:
    """Extract one field from ``root``; returns a list when ``spec.many`` is set."""
    nodes = root.css(spec.selector)
    values = []
    for node in nodes:
        raw = _node_value(node, spec)
        if raw is None:
            continue
        if spec.pattern:
            match = re.search(spec.pattern, raw)
            if not match:
                continue
            raw = match.group(1) if match.groups() else match.group(0)
        values.append(apply_transforms(raw, spec.transforms, base_url))
        if not spec.many:
            break
    if spec.many:
        return values
    return values[0] if values else spec.default


def extract_items(html: str, base_url: str, recipe: Recipe) -> list[dict[str, Any]]:
    """Return every item on the page as a dict of field name to value."""
    tree = LexborHTMLParser(html)
    if recipe.item:
        roots = tree.css(recipe.item)
    else:
        whole = tree.body or tree.root
        roots = [whole] if whole is not None else []
    items = []
    for root in roots:
        item = {name: extract_field(root, spec, base_url) for name, spec in recipe.fields.items()}
        if any(v not in (None, "", []) for v in item.values()):
            items.append(item)
    return items


def find_next_page(html: str, base_url: str, selector: str) -> str | None:
    """Resolve the absolute URL of the next page, if the selector matches a link."""
    node = LexborHTMLParser(html).css_first(selector)
    if node is None:
        return None
    href = node.attributes.get("href")
    return urljoin(base_url, str(href)) if href else None
