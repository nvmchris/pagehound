from __future__ import annotations

from pathlib import Path

import pytest

from pagehound import FieldSpec, Recipe, RecipeError

EXAMPLES = Path(__file__).parent.parent / "examples"


def test_shorthand_field_becomes_spec(quotes_recipe: Recipe) -> None:
    assert quotes_recipe.fields["text"] == FieldSpec(selector="span.text")


def test_attr_pseudo_selector_is_split() -> None:
    spec = FieldSpec(selector="a.next::attr(href)")
    assert spec.selector == "a.next"
    assert spec.attr == "href"


def test_text_pseudo_selector_is_stripped() -> None:
    assert FieldSpec(selector="h1::text").selector == "h1"


def test_conflicting_attr_is_rejected() -> None:
    with pytest.raises(ValueError, match="conflicts"):
        FieldSpec(selector="a::attr(href)", attr="title")


def test_invalid_regex_is_rejected() -> None:
    with pytest.raises(ValueError, match="invalid regex"):
        FieldSpec(selector="p", pattern="(")


def test_start_urls_must_be_http() -> None:
    with pytest.raises(ValueError, match="http"):
        Recipe(name="x", start_urls=["ftp://nope"], fields={"a": FieldSpec(selector="a")})


@pytest.mark.parametrize("path", sorted(EXAMPLES.glob("*.yaml")), ids=lambda p: p.name)
def test_example_recipes_are_valid(path: Path) -> None:
    recipe = Recipe.from_yaml(path)
    assert recipe.start_urls


def test_from_yaml_reports_unknown_keys(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("name: x\nstart_urls: [https://a.test]\nfields: {a: b}\nbogus: 1\n")
    with pytest.raises(RecipeError, match="bogus"):
        Recipe.from_yaml(bad)


def test_from_yaml_reports_missing_file(tmp_path: Path) -> None:
    with pytest.raises(RecipeError, match="cannot read"):
        Recipe.from_yaml(tmp_path / "missing.yaml")
