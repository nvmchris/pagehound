"""Declarative scraping recipes, loaded from YAML and validated with pydantic."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Transform = Literal["strip", "lower", "upper", "int", "float", "number", "url"]

# "h1.title::text" or "a.next::attr(href)"
_PSEUDO = re.compile(r"^(?P<css>.+?)::(?:(?P<text>text)|attr\((?P<attr>[^)]+)\))\s*$")

DEFAULT_USER_AGENT = "pagehound/0.1 (+https://github.com/nvmchris/pagehound)"


class RecipeError(ValueError):
    """Raised when a recipe file cannot be loaded or is invalid."""


class FieldSpec(BaseModel):
    """How to extract a single field from an item node."""

    model_config = ConfigDict(extra="forbid")

    selector: str
    attr: str | None = None
    many: bool = False
    pattern: str | None = Field(None, description="Regex; keeps group 1 (or the whole match)")
    default: Any = None
    transforms: list[Transform] = Field(default_factory=list)

    @field_validator("pattern")
    @classmethod
    def _check_pattern(cls, pattern: str | None) -> str | None:
        if pattern is not None:
            try:
                re.compile(pattern)
            except re.error as exc:
                raise ValueError(f"invalid regex {pattern!r}: {exc}") from exc
        return pattern

    @model_validator(mode="after")
    def _split_pseudo(self) -> FieldSpec:
        match = _PSEUDO.match(self.selector)
        if match:
            self.selector = match["css"].strip()
            if match["attr"]:
                if self.attr and self.attr != match["attr"]:
                    raise ValueError("selector ::attr() conflicts with 'attr'")
                self.attr = match["attr"].strip()
        return self


class Settings(BaseModel):
    """Crawl behaviour. Defaults are deliberately polite."""

    model_config = ConfigDict(extra="forbid")

    concurrency: int = Field(4, ge=1, le=64)
    delay: float = Field(0.5, ge=0, description="Minimum seconds between requests to one host")
    timeout: float = Field(15.0, gt=0)
    retries: int = Field(3, ge=0, le=10)
    backoff: float = Field(0.5, ge=0, description="Base seconds for exponential retry backoff")
    max_pages: int = Field(10, ge=1)
    max_items: int | None = Field(None, ge=1)
    respect_robots: bool = True
    user_agent: str = DEFAULT_USER_AGENT
    headers: dict[str, str] = Field(default_factory=dict)


class Recipe(BaseModel):
    """A complete scraping job: where to start, what to extract and how to paginate."""

    model_config = ConfigDict(extra="forbid")

    name: str
    description: str | None = None
    start_urls: list[str] = Field(min_length=1)
    item: str | None = Field(None, description="CSS selector for each item; omit for one item/page")
    fields: dict[str, FieldSpec] = Field(min_length=1)
    next_page: str | None = Field(None, description="CSS selector of the 'next page' link")
    settings: Settings = Field(default_factory=Settings)

    @field_validator("start_urls")
    @classmethod
    def _check_urls(cls, urls: list[str]) -> list[str]:
        for url in urls:
            if not url.startswith(("http://", "https://")):
                raise ValueError(f"start URL must be http(s): {url!r}")
        return urls

    @field_validator("fields", mode="before")
    @classmethod
    def _expand_shorthand(cls, raw: Any) -> Any:
        if isinstance(raw, dict):
            return {k: {"selector": v} if isinstance(v, str) else v for k, v in raw.items()}
        return raw

    @classmethod
    def from_yaml(cls, source: str | Path) -> Recipe:
        """Load a recipe from a YAML file path."""
        path = Path(source)
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise RecipeError(f"cannot read recipe {path}: {exc}") from exc
        except yaml.YAMLError as exc:
            raise RecipeError(f"invalid YAML in {path}: {exc}") from exc
        if not isinstance(data, dict):
            raise RecipeError(f"recipe {path} must be a mapping at the top level")
        try:
            return cls.model_validate(data)
        except ValueError as exc:
            raise RecipeError(f"invalid recipe {path}:\n{exc}") from exc
