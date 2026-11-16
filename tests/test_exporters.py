import csv
import io
import json
from datetime import datetime, timezone

from app.exporters import UTF8_BOM, build_filename, slugify, to_csv, to_json
from app.models import FIELDS, SearchResult

RESULTS = [
    SearchResult(1, "Příliš žluťoučký kůň", "https://example.cz/kun", "Úpěl ďábelské ódy.", "example.cz › kun"),
    SearchResult(2, 'Comma, "quotes"', "https://example.com/", "", "example.com"),
]
TS = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)


def test_json_schema_and_values():
    doc = json.loads(to_json(RESULTS, "kůň", "serper", timestamp=TS))
    assert set(doc) == {"query", "timestamp", "provider", "count", "results"}
    assert doc["query"] == "kůň"
    assert doc["provider"] == "serper"
    assert doc["timestamp"] == "2026-01-02T03:04:05Z"
    assert doc["count"] == 2
    assert [set(r) for r in doc["results"]] == [set(FIELDS)] * 2
    assert doc["results"][0]["title"] == "Příliš žluťoučký kůň"
    assert doc["results"][1]["position"] == 2


def test_json_keeps_diacritics_unescaped():
    assert "žluťoučký" in to_json(RESULTS, "q", "scraper", timestamp=TS)


def test_json_default_timestamp_is_utc_iso():
    doc = json.loads(to_json([], "q", "scraper"))
    assert doc["timestamp"].endswith("Z")
    datetime.fromisoformat(doc["timestamp"].replace("Z", "+00:00"))
    assert doc["results"] == [] and doc["count"] == 0


def test_csv_header_rows_and_bom():
    text = to_csv(RESULTS)
    assert text.startswith(UTF8_BOM)
    rows = list(csv.reader(io.StringIO(text[len(UTF8_BOM):])))
    assert rows[0] == list(FIELDS)
    assert len(rows) == 1 + len(RESULTS)


def test_csv_diacritics_round_trip_through_bytes():
    raw = to_csv(RESULTS).encode("utf-8")
    assert raw.startswith(b"\xef\xbb\xbf")
    decoded = raw.decode("utf-8-sig")
    rows = list(csv.DictReader(io.StringIO(decoded)))
    assert rows[0]["title"] == "Příliš žluťoučký kůň"
    assert rows[0]["snippet"] == "Úpěl ďábelské ódy."
    assert rows[1]["title"] == 'Comma, "quotes"'
    assert rows[1]["position"] == "2"


def test_slugify():
    assert slugify("Kávovar Praha!") == "kavovar-praha"
    assert slugify("???") == "query"
    assert len(slugify("a" * 100)) == 40


def test_build_filename():
    assert build_filename("Kávovar", "csv", TS) == "results_kavovar_2026-01-02.csv"
    assert build_filename("x", "json").startswith("results_x_")
