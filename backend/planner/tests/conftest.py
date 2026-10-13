import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def isolated_settings(settings):
    """Every test gets an empty in-memory cache and a fake API key; no real network keys are used."""
    settings.CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
    settings.ORS_API_KEY = "test-key"
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


class FakeResponse:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self._body = body
        self.text = body if isinstance(body, (str, Exception)) else json.dumps(body)

    def json(self):
        if isinstance(self._body, str):
            raise ValueError("not json")
        return self._body


@pytest.fixture
def fake_http(monkeypatch):
    """
    Replace the shared HTTP session. Tests queue responses with
    fake_http.add(status, body); every request made is recorded in fake_http.calls.
    """

    class FakeHttp:
        def __init__(self):
            self.responses = []
            self.calls = []

        def add(self, status_code, body):
            self.responses.append(FakeResponse(status_code, body))

        def request(self, method, url, **kwargs):
            self.calls.append({"method": method, "url": url, **kwargs})
            if not self.responses:
                raise AssertionError(f"Unexpected request: {method} {url}")
            response = self.responses.pop(0)
            if isinstance(response._body, Exception):
                raise response._body
            return response

    fake = FakeHttp()
    from planner.clients import http

    monkeypatch.setattr(http._session, "request", fake.request)
    return fake
