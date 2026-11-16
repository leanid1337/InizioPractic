from pathlib import Path

import pytest
import requests
import responses

from app.providers.base import ProviderBlockedError, ProviderError
from app.providers.google_scraper import GOOGLE_URL, GoogleScraperProvider, parse_html

FIXTURE = Path(__file__).parent / "fixtures" / "google_serp.html"

EXPECTED = [
    (
        "Kávovary | Alza.cz",
        "https://www.alza.cz/kavovary/18851136.htm",
        "Kávovary skladem. Vyberte si z více než 900 kávovarů – pákové, automatické i kapslové. Doprava zdarma.",
        "https://www.alza.cz › kavovary",
    ),
    (
        "Kávovary a espressa – Datart.cz",
        "https://www.datart.cz/kavovary.html",
        "12. 3. 2026 — Široký výběr kávovarů za skvělé ceny. Kávovary DeLonghi, Philips, Sencor.",
        "https://www.datart.cz › kavovary",
    ),
    (
        "Kávovary recenze & srovnání",
        "https://www.kavovary-recenze.cz/",
        "",
        "https://www.kavovary-recenze.cz",
    ),
    (
        "Kávovary | MALL.CZ",
        "https://www.mall.cz/kavovary",
        "Kávovary od 999 Kč. Nakupujte výhodně na MALL.CZ.",
        "https://www.mall.cz › kavovary",
    ),
    (
        "Test kávovarů 2026 | dTest",
        "https://www.dtest.cz/clanek-7341/test-kavovaru",
        "Nezávislý test 25 automatických kávovarů. Který obstál nejlépe?",
        "https://www.dtest.cz › clanek-7341",
    ),
]


@pytest.fixture(scope="module")
def results():
    return parse_html(FIXTURE.read_text(encoding="utf-8"))


def test_only_organic_results_returned(results):
    assert len(results) == len(EXPECTED)
    urls = " ".join(r.url for r in results)
    for leaked in ("shop-ad", "kava-ads", "bottom-ad", "wikipedia", "heureka", "idnes", "youtube", "maps"):
        assert leaked not in urls, f"non-organic result leaked: {leaked}"


def test_positions_sequential(results):
    assert [r.position for r in results] == list(range(1, len(EXPECTED) + 1))


def test_exact_fields(results):
    actual = [(r.title, r.url, r.snippet, r.displayed_url) for r in results]
    assert actual == EXPECTED


def test_result_without_snippet(results):
    assert results[2].snippet == ""


def test_redirect_link_unwrapped(results):
    assert results[3].url == "https://www.mall.cz/kavovary"


def test_empty_page():
    assert parse_html("") == []
    assert parse_html("   ") == []
    assert parse_html("<html><body><div id='rso'></div></body></html>") == []


@pytest.mark.parametrize(
    "html",
    [
        '<html><body><form id="captcha-form" action="/sorry/index"></form></body></html>',
        "<html><body>Our systems have detected unusual traffic from your computer network.</body></html>",
        '<div class="g-recaptcha" data-sitekey="x"></div>',
        '<noscript><meta http-equiv="refresh" content="0;url=/httpservice/retry/enablejs?sei=x"></noscript>',
        '<form action="https://consent.google.com/save"><button>Přijmout vše</button></form>',
    ],
)
def test_blocked_pages_raise(html):
    with pytest.raises(ProviderBlockedError):
        parse_html(html)


def test_skips_anchor_without_title_internal_links_and_duplicates():
    html = """<div id="rso">
      <div class="g"><a href="https://a.cz/"><h3>A</h3></a></div>
      <div class="g"><a href="https://a.cz/"><h3>A again</h3></a></div>
      <div class="g"><a href="/search?q=x"><h3>Internal</h3></a></div>
      <div class="g"><a href="https://www.google.com/maps"><h3>Maps</h3></a></div>
      <div class="g"><a href="https://b.cz/"><h3> </h3></a></div>
      <div class="g"><h3>No link</h3></div>
      <span><a href="https://c.cz/x"><h3>C</h3></a></span>
    </div>"""
    res = parse_html(html)
    assert [(r.position, r.url) for r in res] == [(1, "https://a.cz/"), (2, "https://c.cz/x")]
    assert res[1].displayed_url == "c.cz"  # falls back to host when no <cite>


def test_js_wall_message():
    with pytest.raises(ProviderBlockedError, match="JavaScript"):
        parse_html('<meta http-equiv="refresh" content="0;url=/httpservice/retry/enablejs">')


# ---- fetching layer (network mocked) ----

@responses.activate
def test_search_fetches_with_locale_params_and_parses():
    responses.get(GOOGLE_URL, body=FIXTURE.read_text(encoding="utf-8"), status=200)
    res = GoogleScraperProvider(hl="cs", gl="cz").search("kávovar")
    assert len(res) == 5
    req = responses.calls[0].request
    assert "hl=cs" in req.url and "gl=cz" in req.url and "q=k%C3%A1vovar" in req.url
    assert "Chrome" in req.headers["User-Agent"]


@responses.activate
def test_http_429_raises_blocked():
    responses.get(GOOGLE_URL, status=429)
    with pytest.raises(ProviderBlockedError):
        GoogleScraperProvider().search("x")


@responses.activate
def test_redirect_to_sorry_raises_blocked():
    responses.get(GOOGLE_URL, status=302, headers={"Location": "https://www.google.com/sorry/index?continue=x"})
    responses.get("https://www.google.com/sorry/index", body="captcha", status=200)
    with pytest.raises(ProviderBlockedError):
        GoogleScraperProvider().search("x")


@responses.activate
def test_http_500_raises_provider_error():
    responses.get(GOOGLE_URL, status=500)
    with pytest.raises(ProviderError) as exc:
        GoogleScraperProvider().search("x")
    assert not isinstance(exc.value, ProviderBlockedError)


@responses.activate
def test_network_error_wrapped():
    responses.get(GOOGLE_URL, body=requests.ConnectionError("down"))
    with pytest.raises(ProviderError):
        GoogleScraperProvider().search("x")
