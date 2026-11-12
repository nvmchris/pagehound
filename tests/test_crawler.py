from __future__ import annotations

import httpx
import respx

from conftest import page
from pagehound import Crawler, Recipe


def _site(robots: str = "") -> None:
    respx.get("https://example.test/robots.txt").respond(200, text=robots)
    respx.get("https://example.test/").respond(200, html=page("page1.html"))
    respx.get("https://example.test/page/2/").respond(200, html=page("page2.html"))


@respx.mock
async def test_follows_pagination(quotes_recipe: Recipe) -> None:
    _site()
    async with Crawler(quotes_recipe) as crawler:
        items = await crawler.run()
    assert [i["author"] for i in items] == ["Albert Einstein", "J.K. Rowling", "Albert Einstein"]
    assert crawler.stats.pages_ok == 2
    assert crawler.stats.items == 3


@respx.mock
async def test_max_pages_limits_pagination(quotes_recipe: Recipe) -> None:
    _site()
    quotes_recipe.settings.max_pages = 1
    async with Crawler(quotes_recipe) as crawler:
        items = await crawler.run()
    assert len(items) == 2


@respx.mock
async def test_max_items_stops_early(quotes_recipe: Recipe) -> None:
    _site()
    quotes_recipe.settings.max_items = 1
    async with Crawler(quotes_recipe) as crawler:
        items = await crawler.run()
    assert len(items) == 1
    assert crawler.stats.items == 1


@respx.mock
async def test_retries_transient_errors(quotes_recipe: Recipe) -> None:
    respx.get("https://example.test/robots.txt").respond(404)
    respx.get("https://example.test/").mock(
        side_effect=[
            httpx.Response(503),
            httpx.ConnectError("boom"),
            httpx.Response(200, html=page("page2.html")),
        ]
    )
    async with Crawler(quotes_recipe) as crawler:
        items = await crawler.run()
    assert len(items) == 1
    assert crawler.stats.retries == 2


@respx.mock
async def test_gives_up_after_retries(quotes_recipe: Recipe) -> None:
    respx.get("https://example.test/robots.txt").respond(404)
    route = respx.get("https://example.test/").respond(500)
    async with Crawler(quotes_recipe) as crawler:
        items = await crawler.run()
    assert items == []
    assert route.call_count == 3
    assert crawler.stats.pages_failed == 1
    assert "HTTP 500" in crawler.stats.errors[0]


@respx.mock
async def test_client_errors_are_not_retried(quotes_recipe: Recipe) -> None:
    respx.get("https://example.test/robots.txt").respond(404)
    route = respx.get("https://example.test/").respond(404)
    async with Crawler(quotes_recipe) as crawler:
        await crawler.run()
    assert route.call_count == 1


@respx.mock
async def test_robots_txt_blocks_pages(quotes_recipe: Recipe) -> None:
    _site(robots="User-agent: *\nDisallow: /page/\n")
    async with Crawler(quotes_recipe) as crawler:
        items = await crawler.run()
    assert len(items) == 2
    assert crawler.stats.pages_blocked == 1


@respx.mock
async def test_robots_can_be_ignored(quotes_recipe: Recipe) -> None:
    _site(robots="User-agent: *\nDisallow: /\n")
    quotes_recipe.settings.respect_robots = False
    async with Crawler(quotes_recipe) as crawler:
        items = await crawler.run()
    assert len(items) == 3


@respx.mock
async def test_sends_user_agent(quotes_recipe: Recipe) -> None:
    _site()
    quotes_recipe.settings.user_agent = "my-bot/1.0"
    async with Crawler(quotes_recipe) as crawler:
        await crawler.run()
    assert respx.calls.last.request.headers["user-agent"] == "my-bot/1.0"
