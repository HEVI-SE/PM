import json

import pmcal.api as api


def market(i, end, slug=None, question="Q", win=True):
    return {"id": str(i), "slug": slug or f"m{i}", "question": question, "endDate": api._iso(end),
            "outcomes": '["Up","Down"]', "outcomePrices": json.dumps(["1", "0"] if win else ["0", "1"]),
            "clobTokenIds": json.dumps([f"{i}a", f"{i}b"]), "volumeNum": 500}


def fake_api(monkeypatch, markets):
    """Svarar som Gamma: filtrerar på slug och end_date_max, nyast först, ingen offset."""
    calls = []

    def get_json(url, params=None, cache=True, **kw):
        calls.append(params)
        if "slug" in params:
            return [m for m in markets if m["slug"] == params["slug"]]
        rows = [m for m in markets if m["endDate"] <= params["end_date_max"]]
        rows.sort(key=lambda m: m["endDate"], reverse=True)
        return rows[: params["limit"]]

    monkeypatch.setattr(api, "get_json", get_json)
    return calls


def test_fetch_markets_pages_backwards_by_date(monkeypatch):
    now = 1_800_000_000
    monkeypatch.setattr(api.time, "time", lambda: now)
    ms = [market(i, now - i * 3600, question="bitcoin up or down" if i % 3 == 0 else "other")
          for i in range(1, 300)]
    calls = fake_api(monkeypatch, ms)
    out = api.fetch_markets(n=50, contains="bitcoin", page=40, verbose=False)
    assert len(out) == 50
    assert all("bitcoin" in m["question"] for m in out)
    assert len(calls) > 1 and all("offset" not in c for c in calls)
    assert [m["end"] for m in out] == sorted((m["end"] for m in out), reverse=True)


def test_fetch_markets_stops_when_exhausted(monkeypatch):
    now = 1_800_000_000
    monkeypatch.setattr(api.time, "time", lambda: now)
    fake_api(monkeypatch, [market(i, now - i * 60) for i in range(1, 30)])
    assert len(api.fetch_markets(n=1000, page=10, verbose=False)) == 29


def test_fetch_updown_uses_aligned_slugs(monkeypatch):
    now = 1_800_000_123
    monkeypatch.setattr(api.time, "time", lambda: now)
    base = (now // 300 - 2) * 300
    ms = [market(k, base - k * 300 + 300, slug=f"btc-updown-5m-{base - k * 300}") for k in range(20)]
    fake_api(monkeypatch, ms)
    out = api.fetch_updown("btc", "5m", n=10, verbose=False)
    assert [m["slug"] for m in out] == [f"btc-updown-5m-{base - k * 300}" for k in range(10)]


def test_fetch_updown_gives_up_on_wrong_slug(monkeypatch):
    monkeypatch.setattr(api.time, "time", lambda: 1_800_000_000)
    calls = fake_api(monkeypatch, [])
    assert api.fetch_updown("btc", "5m", n=10, verbose=False, max_misses=7) == []
    assert len(calls) == 7


def test_end_is_earliest_of_end_and_close():
    m = market(1, 1_800_000_000)
    m["closedTime"] = api._iso(1_799_990_000)
    assert api._parse_market(m)["end"] == 1_799_990_000
