import json

import pytest
import requests
import responses

from app.providers import ConfigurationError, GoogleScraperProvider, SerperProvider, get_provider
from app.providers.base import ProviderBlockedError, ProviderError
from app.providers.serper import SERPER_URL, displayed_url_from, map_organic

PAYLOAD = {
    "searchParameters": {"q": "kávovar", "gl": "cz", "hl": "cs"},
    "answerBox": {"title": "Kávovar – Wikipedie", "link": "https://cs.wikipedia.org/wiki/K%C3%A1vovar"},
    "peopleAlsoAsk": [{"question": "Jaký kávovar je nejlepší?", "link": "https://www.heureka.cz/"}],
    "organic": [
        {"title": "Kávovary | Alza.cz", "link": "https://www.alza.cz/kavovary/18851136.htm",
         "snippet": "Kávovary skladem.", "position": 1},
        {"title": "Datart", "link": "https://www.datart.cz/", "position": 2},
        {"title": "", "link": "https://broken.cz/", "position": 3},
        {"title": "No link", "position": 4},
        {"title": "dTest", "link": "https://www.dtest.cz/a/b/c", "snippet": " Test. ", "position": 5},
    ],
}


def test_map_organic_ignores_non_organic_and_invalid():
    res = map_organic(PAYLOAD)
    assert [r.position for r in res] == [1, 2, 3]
    assert [r.url for r in res] == [
        "https://www.alza.cz/kavovary/18851136.htm",
        "https://www.datart.cz/",
        "https://www.dtest.cz/a/b/c",
    ]
    assert res[0].title == "Kávovary | Alza.cz"
    assert res[1].snippet == ""
    assert res[2].snippet == "Test."
    assert map_organic({}) == []


def test_displayed_url_from():
    assert displayed_url_from("https://www.alza.cz/kavovary/x.htm") == "https://www.alza.cz › kavovary › x.htm"
    assert displayed_url_from("https://www.dtest.cz/a/b/c") == "https://www.dtest.cz › a › b"
    assert displayed_url_from("https://a.cz") == "https://a.cz"


@responses.activate
def test_search_posts_query_with_key():
    responses.post(SERPER_URL, json=PAYLOAD, status=200)
    res = SerperProvider(api_key="secret", hl="cs", gl="cz").search("kávovar")
    assert len(res) == 3
    req = responses.calls[0].request
    assert req.headers["X-API-KEY"] == "secret"
    assert json.loads(req.body) == {"q": "kávovar", "hl": "cs", "gl": "cz", "num": 10}


@pytest.mark.parametrize(
    "status,exc",
    [(429, ProviderBlockedError), (401, ProviderError), (403, ProviderError), (500, ProviderError)],
)
@responses.activate
def test_api_errors(status, exc):
    responses.post(SERPER_URL, json={"message": "err"}, status=status)
    with pytest.raises(exc):
        SerperProvider(api_key="k").search("x")


@responses.activate
def test_invalid_json():
    responses.post(SERPER_URL, body="not json", status=200)
    with pytest.raises(ProviderError, match="invalid JSON"):
        SerperProvider(api_key="k").search("x")


@responses.activate
def test_network_error():
    responses.post(SERPER_URL, body=requests.Timeout("slow"))
    with pytest.raises(ProviderError, match="Network error"):
        SerperProvider(api_key="k").search("x")


def test_missing_key():
    with pytest.raises(ProviderError, match="SERPER_API_KEY"):
        SerperProvider(api_key="").search("x")


# ---- provider factory ----

def test_factory_defaults_to_serper_when_key_present():
    p = get_provider({"SERPER_API_KEY": "k"})
    assert isinstance(p, SerperProvider) and p.api_key == "k"


def test_factory_defaults_to_scraper_without_key():
    assert isinstance(get_provider({}), GoogleScraperProvider)


def test_factory_explicit_choice_and_locale():
    p = get_provider({"SERPER_API_KEY": "k", "SEARCH_PROVIDER": "Scraper", "SEARCH_HL": "en", "SEARCH_GL": "us"})
    assert isinstance(p, GoogleScraperProvider) and (p.hl, p.gl) == ("en", "us")


def test_factory_unknown_provider():
    with pytest.raises(ConfigurationError, match="bing"):
        get_provider({"SEARCH_PROVIDER": "bing"})


@pytest.mark.parametrize("key", ["", "   "])
def test_factory_serper_without_key_fails_fast(key):
    with pytest.raises(ConfigurationError, match="SERPER_API_KEY is not set"):
        get_provider({"SEARCH_PROVIDER": "serper", "SERPER_API_KEY": key})


def test_factory_reads_os_environ(monkeypatch):
    monkeypatch.setenv("SEARCH_PROVIDER", "serper")
    monkeypatch.setenv("SERPER_API_KEY", "envkey")
    assert get_provider().api_key == "envkey"
