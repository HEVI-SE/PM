import random

import pandas as pd

from pmcal.analysis import brier, calibrate, wilson
from pmcal.api import _parse_market, parse_horizon, parse_ts


def synthetic(n, bias=0.0, seed=1):
    """Kontrakt där sann vinstchans = pris + bias."""
    rnd = random.Random(seed)
    rows = []
    for _ in range(n):
        p = rnd.uniform(0.02, 0.98)
        rows.append({"price": p, "won": int(rnd.random() < min(max(p + bias, 0), 1))})
    return pd.DataFrame(rows)


def test_wilson_contains_true_rate():
    lo, hi = wilson(50, 100)
    assert lo < 0.5 < hi
    assert wilson(0, 0) == (0.0, 0.0)


def test_calibrated_prices_show_no_edge():
    t = calibrate(synthetic(20000), fee=0.0, slippage=0.0)
    assert not t["edge"].any()
    assert (t["avvikelse"].abs() < 0.05).all()


def test_mispriced_market_is_detected():
    # Sann chans 10 procentenheter över priset: ska ge edge i mittenintervallen
    t = calibrate(synthetic(20000, bias=0.10), fee=0.0, slippage=0.0)
    assert t["edge"].sum() >= 5


def test_fee_removes_small_edge():
    t = calibrate(synthetic(20000, bias=0.01), fee=0.05, slippage=0.01)
    assert not t["edge"].any()


def test_group_by_category():
    df = pd.concat([synthetic(2000).assign(category="a"), synthetic(2000, seed=2).assign(category="b")])
    t = calibrate(df, by="category")
    assert set(t["category"]) == {"a", "b"}


def test_brier_perfect_and_worst():
    assert brier(pd.DataFrame({"price": [1.0, 0.0], "won": [1, 0]})) == 0.0
    assert brier(pd.DataFrame({"price": [0.0, 1.0], "won": [1, 0]})) == 1.0


def test_parse_helpers():
    assert parse_horizon("2m") == 120
    assert parse_horizon("7d") == 7 * 86400
    assert parse_ts("2026-01-07T12:00:00Z") == parse_ts("2026-01-07 12:00:00+00") == 1767787200


def test_parse_market_keeps_only_resolved_binary():
    base = {"id": "1", "question": "Q?", "endDate": "2026-01-07T12:00:00Z",
            "outcomes": '["Yes","No"]', "clobTokenIds": '["a","b"]', "volumeNum": 100}
    assert _parse_market({**base, "outcomePrices": '["1","0"]'})["result"] == [1.0, 0.0]
    assert _parse_market({**base, "outcomePrices": '["0.5","0.5"]'}) is None
    assert _parse_market({**base, "outcomePrices": '["0.6","0.4"]'}) is None
