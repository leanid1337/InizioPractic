import pytest

from app import create_app
from app.models import SearchResult
from app.providers.base import SearchProvider


class FakeProvider(SearchProvider):
    name = "fake"

    def __init__(self, results=None, error: Exception | None = None):
        self.results = results or []
        self.error = error
        self.calls: list[str] = []

    def search(self, query):
        self.calls.append(query)
        if self.error:
            raise self.error
        return list(self.results)


SAMPLE = [
    SearchResult(1, "Kávovary | Alza.cz", "https://www.alza.cz/kavovary", "Kávovary skladem.", "https://www.alza.cz › kavovary"),
    SearchResult(2, "Datart", "https://www.datart.cz/", "", "https://www.datart.cz"),
]


@pytest.fixture
def fake_provider():
    return FakeProvider(SAMPLE)


@pytest.fixture
def client(fake_provider):
    return create_app(provider=fake_provider).test_client()


@pytest.fixture
def make_client():
    def _make(**kwargs):
        provider = FakeProvider(**kwargs)
        return create_app(provider=provider).test_client(), provider
    return _make

