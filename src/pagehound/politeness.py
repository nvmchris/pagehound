"""Politeness primitives: per-host rate limiting and robots.txt compliance."""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from collections.abc import Awaitable, Callable
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx

ALLOW_ALL: list[str] = []
DISALLOW_ALL = ["User-agent: *", "Disallow: /"]


class HostRateLimiter:
    """Guarantees at least ``delay`` seconds between request starts to the same host."""

    def __init__(
        self,
        delay: float,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.delay = delay
        self._clock = clock
        self._sleep = sleep
        self._next_slot: dict[str, float] = {}
        self._locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def wait(self, url: str) -> None:
        if self.delay <= 0:
            return
        host = urlsplit(url).netloc
        async with self._locks[host]:
            now = self._clock()
            slot = self._next_slot.get(host, now)
            if slot > now:
                await self._sleep(slot - now)
                now = slot
            self._next_slot[host] = now + self.delay


class RobotsCache:
    """Fetches and caches robots.txt per origin.

    Follows RFC 9309: an unavailable robots.txt (4xx) allows everything, while an
    unreachable one (5xx) disallows everything. 401/403 are treated as a full disallow
    to stay on the safe side; pure network errors fail open.
    """

    def __init__(self, client: httpx.AsyncClient, user_agent: str) -> None:
        self._client = client
        self._user_agent = user_agent
        self._parsers: dict[str, RobotFileParser] = {}
        self._locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def allowed(self, url: str) -> bool:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        async with self._locks[origin]:
            if origin not in self._parsers:
                self._parsers[origin] = await self._load(origin)
        return self._parsers[origin].can_fetch(self._user_agent, url)

    async def _load(self, origin: str) -> RobotFileParser:
        parser = RobotFileParser(f"{origin}/robots.txt")
        try:
            response = await self._client.get(f"{origin}/robots.txt", follow_redirects=True)
        except httpx.HTTPError:
            parser.parse(ALLOW_ALL)
            return parser
        if response.status_code in (401, 403) or response.status_code >= 500:
            parser.parse(DISALLOW_ALL)
        elif response.status_code >= 400:
            parser.parse(ALLOW_ALL)
        else:
            parser.parse(response.text.splitlines())
        return parser
