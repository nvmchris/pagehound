# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [0.1.0] - 2026-11-12

### Added
- Async crawl engine on `httpx` with a worker pool, per-host rate limiting and
  exponential-backoff retries for transient failures (429, 5xx, network errors).
- robots.txt support following RFC 9309, cached per origin.
- Declarative YAML recipes: item selectors, field specs with `::attr()` shorthand,
  regex `pattern`, transforms (`strip`, `lower`, `upper`, `int`, `float`, `number`, `url`),
  defaults, multi-value fields and pagination.
- Streaming exporters for JSON, JSON Lines and CSV.
- `pagehound run`, `fetch` and `validate` commands with Rich output.
- Example recipes for quotes.toscrape.com and books.toscrape.com.
