"""A wildcard route registered before a fixed one swallows it: FastAPI tries
routes in registration order. /signals/{symbol} did this to ten fixed
/signals/<name> routes, which then ran the per-symbol handler with the route
name as a ticker (and returned 500 for the hyphenated ones)."""

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.routing import Match

from src.api import routes
from src.api.routes import router


def _first_match(path: str, method: str):
    scope = {"type": "http", "path": path, "method": method}
    for route in router.routes:
        if route.matches(scope)[0] == Match.FULL:
            return route
    return None


def test_no_fixed_route_is_shadowed_by_a_wildcard():
    shadowed = [
        (method, r.path, _first_match(r.path, method).path)
        for r in router.routes if "{" not in r.path
        for method in r.methods
        if _first_match(r.path, method) is not r
    ]
    assert shadowed == []


def test_fixed_signal_routes_reach_their_own_handlers():
    expected = {
        "/signals/vix", "/signals/gaps", "/signals/extended-hours",
        "/signals/unusual-volume", "/signals/short-squeeze",
        "/signals/bollinger-squeeze", "/signals/macd-divergence",
        "/signals/ema-crosses", "/signals/atr-ranking", "/signals/anomalies",
    }
    for path in expected:
        assert _first_match(path, "GET").path == path


def test_symbol_route_still_works_and_survives_a_bad_symbol(monkeypatch):
    assert _first_match("/signals/NVDA", "GET").path == "/signals/{symbol}"
    asked = []
    def refuse(symbol, days=200):
        asked.append(symbol)
        raise RuntimeError("400 Bad Request: invalid symbol")
    monkeypatch.setattr(routes.client, "get_bars", refuse)
    app = FastAPI()
    app.include_router(router)
    resp = TestClient(app).get("/signals/not-a-ticker")
    assert resp.status_code == 200 and resp.json() == []
    assert asked == ["NOT-A-TICKER"]
