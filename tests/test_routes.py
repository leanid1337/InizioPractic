import csv
import io
import json
import logging
import os

import pytest

from app import create_app
from app.cache import TTLCache
from app.providers import ConfigurationError
from app.providers.base import ProviderBlockedError, ProviderError


def test_index_page_loads(client):
    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'id="q"' in html and 'id="json-link"' in html and 'id="csv-link"' in html


def test_healthz(client):
    assert client.get("/healthz").get_json() == {"status": "ok", "provider": "fake"}


def test_json_response(client):
    resp = client.get("/api/search", query_string={"q": "kávovar"})
    assert resp.status_code == 200
    assert resp.content_type == "application/json; charset=utf-8"
    data = json.loads(resp.get_data(as_text=True))
    assert data["query"] == "kávovar"
    assert data["provider"] == "fake"
    assert data["count"] == 2
    assert [r["position"] for r in data["results"]] == [1, 2]
    cd = resp.headers["Content-Disposition"]
    assert cd.startswith('attachment; filename="results_kavovar_') and cd.endswith('.json"')


def test_csv_response(client):
    resp = client.get("/api/search", query_string={"q": "kávovar", "format": "csv"})
    assert resp.status_code == 200
    assert resp.content_type == "text/csv; charset=utf-8"
    assert resp.data.startswith(b"\xef\xbb\xbf")
    rows = list(csv.DictReader(io.StringIO(resp.data.decode("utf-8-sig"))))
    assert len(rows) == 2 and rows[0]["title"] == "Kávovary | Alza.cz"
    assert resp.headers["Content-Disposition"].endswith('.csv"')


def test_query_whitespace_normalised(client, fake_provider):
    client.get("/api/search", query_string={"q": "  kávovar   praha "})
    assert fake_provider.calls == ["kávovar praha"]


@pytest.mark.parametrize("params", [{}, {"q": ""}, {"q": "   "}])
def test_empty_query_400(client, params):
    resp = client.get("/api/search", query_string=params)
    assert resp.status_code == 400
    assert "empty" in resp.get_json()["error"]


def test_too_long_query_400(client):
    resp = client.get("/api/search", query_string={"q": "a" * 201})
    assert resp.status_code == 400
    assert "too long" in resp.get_json()["error"]


def test_bad_format_400(client):
    resp = client.get("/api/search", query_string={"q": "x", "format": "xml"})
    assert resp.status_code == 400


def test_blocked_provider_503(make_client):
    client, _ = make_client(error=ProviderBlockedError("CAPTCHA"))
    resp = client.get("/api/search", query_string={"q": "x"})
    assert resp.status_code == 503
    assert "blocking" in resp.get_json()["error"] and "CAPTCHA" in resp.get_json()["error"]


def test_provider_error_502(make_client):
    client, _ = make_client(error=ProviderError("boom"))
    resp = client.get("/api/search", query_string={"q": "x"})
    assert resp.status_code == 502
    assert "boom" in resp.get_json()["error"]


def test_results_cached_between_json_and_csv(client, fake_provider):
    client.get("/api/search", query_string={"q": "Kávovar"})
    client.get("/api/search", query_string={"q": "kávovar", "format": "csv"})
    assert fake_provider.calls == ["Kávovar"]


# ---- startup configuration (.env loading, logging, fail-fast) ----

ENV_VARS = ("SEARCH_PROVIDER", "SERPER_API_KEY", "SEARCH_HL", "SEARCH_GL")


@pytest.fixture
def clean_env(monkeypatch, tmp_path):
    """Run in an empty directory with no provider env vars; everything is restored after."""
    monkeypatch.chdir(tmp_path)
    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    return tmp_path


def test_create_app_uses_env_provider(clean_env, monkeypatch):
    monkeypatch.setenv("SEARCH_PROVIDER", "scraper")
    app = create_app()
    assert app.extensions["search_provider"].name == "scraper"


def test_create_app_loads_dotenv(clean_env):
    (clean_env / ".env").write_text("SEARCH_PROVIDER=serper\nSERPER_API_KEY=from-dotenv\n", encoding="utf-8")
    provider = create_app().extensions["search_provider"]
    assert provider.name == "serper"
    assert provider.api_key == "from-dotenv"


def test_real_env_wins_over_dotenv(clean_env, monkeypatch):
    (clean_env / ".env").write_text("SERPER_API_KEY=from-dotenv\n", encoding="utf-8")
    monkeypatch.setenv("SERPER_API_KEY", "from-env")
    assert create_app().extensions["search_provider"].api_key == "from-env"


def test_injected_provider_skips_dotenv(clean_env, fake_provider):
    (clean_env / ".env").write_text("SERPER_API_KEY=from-dotenv\n", encoding="utf-8")
    create_app(provider=fake_provider)
    assert "SERPER_API_KEY" not in os.environ


def test_startup_fails_fast_when_serper_key_missing(clean_env, monkeypatch):
    monkeypatch.setenv("SEARCH_PROVIDER", "serper")
    with pytest.raises(ConfigurationError, match="SERPER_API_KEY is not set"):
        create_app()


def test_startup_logs_provider_name(fake_provider, caplog):
    with caplog.at_level(logging.INFO):
        create_app(provider=fake_provider)
    assert "Search provider: fake" in caplog.text


# ---- cache unit tests ----

def test_ttl_cache_expiry_and_eviction():
    now = [0.0]
    c = TTLCache(ttl=10, max_items=2, clock=lambda: now[0])
    assert c.get("a") is None
    c.set("a", 1)
    now[0] = 1
    c.set("b", 2)
    c.set("c", 3)  # evicts oldest ("a")
    assert c.get("a") is None and c.get("b") == 2 and c.get("c") == 3
    now[0] = 20
    assert c.get("b") is None


def test_ttl_cache_disabled():
    c = TTLCache(ttl=0)
    c.set("a", 1)
    assert c.get("a") is None
