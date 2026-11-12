"""The async crawl engine."""

from __future__ import annotations

import asyncio
import contextlib
import random
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Any

import httpx

from .extract import extract_items, find_next_page
from .politeness import HostRateLimiter, RobotsCache
from .recipe import Recipe

RETRYABLE_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})

Item = dict[str, Any]


@dataclass
class CrawlStats:
    """Live counters for a crawl; safe to read while the crawl is running."""

    pages_ok: int = 0
    pages_failed: int = 0
    pages_blocked: int = 0
    items: int = 0
    retries: int = 0
    errors: list[str] = field(default_factory=list)
    started: float = field(default_factory=time.perf_counter)
    finished: float | None = None

    @property
    def elapsed(self) -> float:
        return (self.finished or time.perf_counter()) - self.started


class FetchError(RuntimeError):
    """Raised when a page cannot be fetched after all retries."""


@dataclass(frozen=True)
class _Task:
    url: str
    page: int


_DONE = object()


class Crawler:
    """Crawls a :class:`Recipe` and streams extracted items.

    Example::

        async with Crawler(recipe) as crawler:
            async for item in crawler.stream():
                print(item)
    """

    def __init__(
        self,
        recipe: Recipe,
        *,
        client: httpx.AsyncClient | None = None,
        on_page: Callable[[str, int], None] | None = None,
    ) -> None:
        self.recipe = recipe
        self.settings = recipe.settings
        self.stats = CrawlStats()
        self._on_page = on_page
        self._owns_client = client is None
        headers = {"User-Agent": self.settings.user_agent, **self.settings.headers}
        self._client = client or httpx.AsyncClient(
            headers=headers,
            timeout=self.settings.timeout,
            follow_redirects=True,
        )
        self._limiter = HostRateLimiter(self.settings.delay)
        self._robots = RobotsCache(self._client, self.settings.user_agent)
        self._seen: set[str] = set()

    async def __aenter__(self) -> Crawler:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def fetch(self, url: str) -> httpx.Response:
        """GET ``url`` with rate limiting and exponential-backoff retries."""
        last_error = "unknown error"
        for attempt in range(self.settings.retries + 1):
            if attempt:
                self.stats.retries += 1
                pause = self.settings.backoff * (2 ** (attempt - 1))
                await asyncio.sleep(pause + random.uniform(0, pause / 2))
            await self._limiter.wait(url)
            try:
                response = await self._client.get(url)
            except httpx.TransportError as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                continue
            if response.status_code in RETRYABLE_STATUS:
                last_error = f"HTTP {response.status_code}"
                continue
            if response.is_error:
                raise FetchError(f"{url}: HTTP {response.status_code}")
            return response
        raise FetchError(f"{url}: {last_error} (after {self.settings.retries + 1} attempts)")

    async def stream(self) -> AsyncIterator[Item]:
        """Yield items as soon as they are extracted."""
        work: asyncio.Queue[_Task] = asyncio.Queue()
        out: asyncio.Queue[Any] = asyncio.Queue()
        for url in self.recipe.start_urls:
            self._enqueue(work, url, 1)

        async def worker() -> None:
            while True:
                task = await work.get()
                try:
                    await self._process(task, work, out)
                finally:
                    work.task_done()

        async def closer() -> None:
            await work.join()
            await out.put(_DONE)

        tasks = [asyncio.create_task(worker()) for _ in range(self.settings.concurrency)]
        tasks.append(asyncio.create_task(closer()))
        limit = self.settings.max_items
        try:
            while (item := await out.get()) is not _DONE:
                self.stats.items += 1
                yield item
                if limit is not None and self.stats.items >= limit:
                    break
        finally:
            for task in tasks:
                task.cancel()
            for task in tasks:
                with contextlib.suppress(asyncio.CancelledError):
                    await task
            self.stats.finished = time.perf_counter()

    async def run(self) -> list[Item]:
        """Crawl to completion and return every item."""
        return [item async for item in self.stream()]

    def _enqueue(self, work: asyncio.Queue[_Task], url: str, page: int) -> None:
        if url in self._seen or page > self.settings.max_pages:
            return
        self._seen.add(url)
        work.put_nowait(_Task(url, page))

    async def _process(
        self, task: _Task, work: asyncio.Queue[_Task], out: asyncio.Queue[Any]
    ) -> None:
        if self.settings.respect_robots and not await self._robots.allowed(task.url):
            self.stats.pages_blocked += 1
            self.stats.errors.append(f"{task.url}: disallowed by robots.txt")
            return
        try:
            response = await self.fetch(task.url)
        except FetchError as exc:
            self.stats.pages_failed += 1
            self.stats.errors.append(str(exc))
            return

        self.stats.pages_ok += 1
        if self._on_page:
            self._on_page(task.url, task.page)

        base_url = str(response.url)
        html = response.text
        for item in extract_items(html, base_url, self.recipe):
            await out.put(item)
        if self.recipe.next_page:
            next_url = find_next_page(html, base_url, self.recipe.next_page)
            if next_url:
                self._enqueue(work, next_url, task.page + 1)


async def crawl(recipe: Recipe) -> list[Item]:
    """Convenience wrapper: crawl ``recipe`` and return all items."""
    async with Crawler(recipe) as crawler:
        return await crawler.run()


__all__ = ["CrawlStats", "Crawler", "FetchError", "Item", "crawl"]
