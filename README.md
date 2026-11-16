# Google SERP Scraper

[![tests](https://github.com/<OWNER>/<REPO>/actions/workflows/tests.yml/badge.svg)](https://github.com/<OWNER>/<REPO>/actions/workflows/tests.yml)

A small web app: type a keyword phrase, get the **organic** results from Google page 1
(no ads, featured snippets, "People also ask", maps, videos or knowledge panel), and
download them as **JSON** or **CSV**.

**Live demo:** `https://<your-service>.onrender.com` (see [Deploy](#deploy-to-render))

## Features

- Single page (`/`, Czech UI) with one input, a results table and two download links.
- REST endpoint `GET /api/search?q=<phrase>&format=json|csv`.
- Two interchangeable providers behind one interface:
  - `serper`: [Serper.dev](https://serper.dev) Google SERP API (production default).
  - `scraper`: direct Google scraping with `requests` + BeautifulSoup.
- JSON contains `query`, `timestamp` (ISO 8601, UTC), `provider`, `count`, `results[]`.
- CSV is UTF-8 **with BOM**, so Excel shows Czech diacritics correctly.
- Downloads are named `results_<slug>_<YYYY-MM-DD>.json|csv` via `Content-Disposition`.
- Input validation (`400` for empty / >200 chars), `503` when the provider is blocked
  (CAPTCHA, HTTP 429, JS wall), `502` for other upstream errors; the UI shows the message.
- 5-minute in-memory cache so the table and both downloads cost one upstream call.
- 63 unit tests, 100 % line and branch coverage, no real network calls.

Result schema (one item):

```json
{
  "position": 1,
  "title": "Kávovary | Alza.cz",
  "url": "https://www.alza.cz/kavovary/18851136.htm",
  "snippet": "Kávovary skladem. ...",
  "displayed_url": "https://www.alza.cz › kavovary"
}
```

## Project layout

```
app/
  __init__.py          Flask app factory (create_app)
  routes.py            GET /, GET /healthz, GET /api/search
  models.py            SearchResult dataclass
  exporters.py         to_json, to_csv, filename helpers
  cache.py             small thread-safe TTL cache
  static/index.html    vanilla JS + CSS frontend
  providers/
    base.py            SearchProvider ABC, ProviderError, ProviderBlockedError
    google_scraper.py  fetch() + pure parse_html()
    serper.py          Serper.dev API client + pure map_organic()
    __init__.py        get_provider() factory driven by env vars
tests/                 pytest suite + fixtures/google_serp.html
```

## Configuration

| Variable          | Default                                        | Meaning                        |
|-------------------|------------------------------------------------|--------------------------------|
| `SEARCH_PROVIDER` | `serper` if `SERPER_API_KEY` is set, else `scraper` | which provider to use     |
| `SERPER_API_KEY`  | empty                                          | API key from serper.dev        |
| `SEARCH_HL`       | `cs`                                           | Google interface language      |
| `SEARCH_GL`       | `cz`                                           | Google country                 |
| `LOG_LEVEL`       | `INFO`                                         | app log level                  |

Copy `.env.example` to `.env` and fill it in. The app factory loads `.env` from the current
working directory with python-dotenv; variables already set in the real environment
(shell, Docker, Render) take precedence.

At startup the app logs the selected provider (`Search provider: serper`). Invalid
configuration stops startup with a clear error instead of silently falling back:
`SEARCH_PROVIDER=serper` without `SERPER_API_KEY`, or an unknown `SEARCH_PROVIDER` value.

## Run locally

### Python venv

```bash
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
flask --app "app:create_app" run --port 8000
```

Open http://localhost:8000. Settings come from `.env` in the project root (see above) or
from the shell (e.g. `export SERPER_API_KEY=...`).

### Docker Compose

```bash
cp .env.example .env                 # optional, add SERPER_API_KEY
docker compose up --build
```

The app is served by gunicorn on http://localhost:8000.

## Tests

```bash
python -m pytest                     # prints coverage per file
docker compose run --rm tests        # same suite inside the container
```

The `tests` service is behind a compose profile, so `docker compose up` starts only the app.
CI (GitHub Actions, `.github/workflows/tests.yml`) runs the suite on every push and fails
below 90 % coverage.

What is covered:

- **Parser** against a realistic saved SERP (`tests/fixtures/google_serp.html`) containing
  organic results plus top and bottom ads, a featured snippet, "People also ask", a video
  carousel, a local/maps pack and a knowledge panel. Asserts only the 5 organic results
  are returned, positions are `1..5`, and every title / URL / snippet / displayed URL is exact.
- Parser edge cases: empty page, CAPTCHA / "unusual traffic" / reCAPTCHA / consent / JS wall
  pages raise `ProviderBlockedError`, result without snippet, `/url?q=` redirect links,
  duplicates, internal Google links.
- Fetching layer with mocked HTTP (`responses`): locale params, headers, 429, `/sorry/`
  redirect, 5xx, network errors.
- Serper provider with mocked HTTP: request body and API key header, mapping of `organic`,
  ignoring `answerBox` / `peopleAlsoAsk`, 401/403/429/500, invalid JSON, missing key.
- Exporters: JSON keys and values, ISO UTC timestamp, CSV header, row count, BOM, diacritics
  round-trip through bytes.
- Flask routes via test client with a fake provider: page loads, content types,
  `Content-Disposition`, 400/502/503, caching.

## Deploy to Render

1. Push the repo to GitHub.
2. In Render: **New > Blueprint**, select the repo. `render.yaml` defines a Docker web
   service with a `/healthz` health check.
3. Set the secret `SERPER_API_KEY` in the dashboard (free tier at serper.dev).
4. Render injects `$PORT`; the Dockerfile binds gunicorn to it.

## Design decisions

### Why direct Google scraping is unreliable, especially from cloud IPs

- **Bot detection by IP reputation.** Render, Heroku, AWS, GCP etc. use well-known
  datacenter IP ranges. Google treats traffic from them as automated and quickly answers
  with HTTP 429 or a redirect to `/sorry/index` (reCAPTCHA). Shared egress IPs are often
  already flagged by other tenants before your first request.
- **JavaScript requirement.** Google now serves a non-browser client a page that only
  redirects to `/httpservice/retry/enablejs`, with no results in it. While building this
  project, a plain `requests` call from a residential Czech connection received exactly
  that page. Getting real HTML would need a headless browser (Playwright), which is heavy,
  slow and still fingerprintable.
- **Consent wall in the EU.** Without consent cookies, EU visitors are redirected to
  `consent.google.com`.
- **Unstable markup.** Class names like `VwiC3b` or `MjjYud` are obfuscated and change
  without notice, so any HTML parser needs ongoing maintenance.
- **Terms of Service.** Automated querying is against Google's ToS; a SERP API vendor
  takes on that operational burden (proxy pools, CAPTCHA solving, parsing upkeep).

### Why Serper is the production default, and why the scraper is still here

The public demo must work every time a reviewer opens it, so the deployed instance uses a
SERP API that returns structured JSON. Its `organic` array is already free of ads and
SERP features; `map_organic()` only normalises it to our `SearchResult` model.

The scraper is kept to show the scraping part of the task properly:

- `fetch()` (I/O) is separated from `parse_html()` (a **pure function**: HTML in, list out).
  This makes the parser fully testable offline against saved pages and reusable with any
  HTML source (Playwright, a proxy service, a saved file).
- Non-organic blocks are **removed from the tree first** (ads, featured snippet, PAA,
  maps, videos, knowledge panel), then results are found by the stable pattern
  "`<a href>` containing an `<h3>`". Positions are assigned after filtering, so they are
  always `1..N`.
- Blocks are detected explicitly (`ProviderBlockedError` -> HTTP 503) instead of silently
  returning an empty list, so the user sees why there are no results.
- Realistic headers, `hl`/`gl` params and consent cookies are sent; it works from some
  residential IPs at low volume and is the default when no API key is configured.

### Other choices

- **Provider abstraction** (`SearchProvider` ABC + env-driven factory): adding Bing or
  SerpAPI means one new class, no change to routes or exporters.
- **App factory with dependency injection**: tests pass a fake provider into `create_app()`,
  so route tests never touch the network.
- **CSV with BOM**: Excel on Windows assumes a legacy code page for CSV without BOM and
  garbles `ř`, `ů`, `ě`.
- **Small TTL cache**: viewing results and downloading two formats would otherwise make
  three upstream calls (cost for Serper, block risk for scraping).
- **Minimal frontend**: one static page, plain JS, no build step. Results are rendered with
  `textContent` (no `innerHTML`), so titles and snippets from Google cannot inject markup.
- **Downloads are plain links** to `/api/search?...&format=json|csv`. The server's
  `Content-Disposition: attachment` header makes the browser save the file with the right
  name, and the cache means the download returns the same results the table showed.
  Trade-off: if the provider fails at download time (e.g. 503), the browser saves the JSON
  error body as the file instead of showing the message on the page.
