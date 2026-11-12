from __future__ import annotations

import pytest

from conftest import page
from pagehound import FieldSpec, Recipe, extract_items, find_next_page
from pagehound.extract import apply_transforms

BASE = "https://example.test/"


def test_extracts_all_items(quotes_recipe: Recipe) -> None:
    items = extract_items(page("page1.html"), BASE, quotes_recipe)
    assert len(items) == 2
    assert items[0] == {
        "text": "“The world as we have created it is a process of our thinking.”",
        "author": "Albert Einstein",
        "author_url": "https://example.test/author/Albert-Einstein",
        "tags": ["change", "thinking"],
    }


def test_whitespace_is_collapsed(quotes_recipe: Recipe) -> None:
    items = extract_items(page("page1.html"), BASE, quotes_recipe)
    assert items[1]["text"] == "“It is our choices, Harry, that show what we truly are.”"


def test_many_field_with_no_matches_is_empty_list(quotes_recipe: Recipe) -> None:
    items = extract_items(page("page2.html"), BASE, quotes_recipe)
    assert items[0]["tags"] == []


def test_whole_page_item_when_no_item_selector() -> None:
    recipe = Recipe(
        name="x", start_urls=[BASE], fields={"first": FieldSpec(selector="small.author")}
    )
    assert extract_items(page("page1.html"), BASE, recipe) == [{"first": "Albert Einstein"}]


def test_default_used_when_missing() -> None:
    recipe = Recipe(
        name="x",
        start_urls=[BASE],
        item="div.quote",
        fields={
            "author": FieldSpec(selector="small.author"),
            "rating": FieldSpec(selector=".rating", default="n/a"),
        },
    )
    assert extract_items(page("page1.html"), BASE, recipe)[0]["rating"] == "n/a"


def test_pattern_keeps_first_group() -> None:
    recipe = Recipe(
        name="x",
        start_urls=[BASE],
        item="div.quote",
        fields={"slug": FieldSpec(selector="a.author-link::attr(href)", pattern=r"/author/(.+)")},
    )
    assert extract_items(page("page1.html"), BASE, recipe)[1]["slug"] == "J-K-Rowling"


def test_next_page_is_absolute() -> None:
    assert find_next_page(page("page1.html"), BASE, "li.next > a") == "https://example.test/page/2/"
    assert find_next_page(page("page2.html"), BASE, "li.next > a") is None


@pytest.mark.parametrize(
    ("value", "transforms", "expected"),
    [
        ("£51.77", ["float"], 51.77),
        ("1,234 reviews", ["int"], 1234),
        ("In stock (22 available)", ["number"], 22.0),
        ("no digits", ["int"], None),
        ("  Hello ", ["strip", "upper"], "HELLO"),
        ("/a/b", ["url"], "https://example.test/a/b"),
    ],
)
def test_transforms(value: str, transforms: list[str], expected: object) -> None:
    assert apply_transforms(value, transforms, BASE) == expected  # type: ignore[arg-type]
