from __future__ import annotations

from pathlib import Path

import pytest

from pagehound import Recipe

FIXTURES = Path(__file__).parent / "fixtures"


def page(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture
def quotes_recipe() -> Recipe:
    return Recipe.model_validate(
        {
            "name": "quotes",
            "start_urls": ["https://example.test/"],
            "item": "div.quote",
            "fields": {
                "text": "span.text",
                "author": "small.author",
                "author_url": {"selector": "a.author-link::attr(href)", "transforms": ["url"]},
                "tags": {"selector": "a.tag", "many": True},
            },
            "next_page": "li.next > a",
            "settings": {"delay": 0, "backoff": 0, "retries": 2},
        }
    )
