from __future__ import annotations

import httpx
import pytest
import respx

from pagehound.politeness import HostRateLimiter, RobotsCache


async def test_rate_limiter_spaces_requests_per_host() -> None:
    now = 100.0
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        nonlocal now
        sleeps.append(seconds)
        now += seconds

    limiter = HostRateLimiter(1.5, clock=lambda: now, sleep=fake_sleep)
    await limiter.wait("https://a.test/1")
    await limiter.wait("https://a.test/2")
    await limiter.wait("https://b.test/1")  # other host: no wait
    await limiter.wait("https://a.test/3")
    assert sleeps == [1.5, 1.5]


@respx.mock
async def test_robots_disallow_rules_are_honoured() -> None:
    respx.get("https://site.test/robots.txt").respond(
        200, text="User-agent: *\nDisallow: /private\n"
    )
    async with httpx.AsyncClient() as client:
        robots = RobotsCache(client, "pagehound")
        assert await robots.allowed("https://site.test/public")
        assert not await robots.allowed("https://site.test/private/x")


@pytest.mark.parametrize(("status", "allowed"), [(404, True), (403, False), (503, False)])
@respx.mock
async def test_robots_status_handling(status: int, allowed: bool) -> None:
    route = respx.get("https://site.test/robots.txt").respond(status)
    async with httpx.AsyncClient() as client:
        robots = RobotsCache(client, "pagehound")
        assert await robots.allowed("https://site.test/a") is allowed
        await robots.allowed("https://site.test/b")
    assert route.call_count == 1  # cached per origin
