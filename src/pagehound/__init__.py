"""pagehound - an async, polite web scraper driven by declarative YAML recipes."""

from __future__ import annotations

__version__ = "0.1.0"

from .crawler import Crawler, CrawlStats, FetchError, crawl
from .exporters import Exporter, infer_format
from .extract import extract_items, find_next_page
from .recipe import FieldSpec, Recipe, RecipeError, Settings

__all__ = [
    "CrawlStats",
    "Crawler",
    "Exporter",
    "FetchError",
    "FieldSpec",
    "Recipe",
    "RecipeError",
    "Settings",
    "__version__",
    "crawl",
    "extract_items",
    "find_next_page",
    "infer_format",
]
