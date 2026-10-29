import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from ma_regel import backtest, break_even_fee, max_drawdown  # noqa: E402

IDX = pd.bdate_range("2000-01-03", periods=600)
NO_CASH = pd.Series(0.0, index=IDX)


def test_rising_market_stays_in_after_one_buy():
    close = pd.Series(np.linspace(100, 200, len(IDX)), index=IDX)
    rule, hold, trades, out = backtest(close, NO_CASH, 30, IDX[40], 1000, 0.0, 0.0)
    assert trades == 1
    assert out == 0
    assert abs(rule.iloc[-1] - hold.iloc[-1]) / hold.iloc[-1] < 0.01


def test_rule_avoids_crash():
    # Upp, krasch, sakta tillbaka: regeln ska gå ur och sluta före behåll
    up = np.linspace(100, 200, 200)
    crash = np.linspace(200, 80, 100)
    back = np.linspace(80, 150, 300)
    close = pd.Series(np.concatenate([up, crash, back]), index=IDX)
    rule, hold, trades, _ = backtest(close, NO_CASH, 30, IDX[40], 1000, 0.0, 0.0)
    assert rule.iloc[-1] > hold.iloc[-1]
    assert max_drawdown(rule) > max_drawdown(hold)  # mindre negativt
    assert trades >= 3


def test_fees_are_charged_per_trade():
    rng = np.random.default_rng(0)
    close = pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.01, len(IDX)))), index=IDX)
    free, _, trades, _ = backtest(close, NO_CASH, 30, IDX[40], 1000, 0.0, 0.0)
    paid, _, trades2, _ = backtest(close, NO_CASH, 30, IDX[40], 1000, 0.1, 0.0)
    assert trades == trades2 > 5
    assert abs(paid.iloc[-1] / free.iloc[-1] - 0.999 ** trades) < 1e-9


def test_fixed_courtage_hurts_small_accounts_more():
    rng = np.random.default_rng(1)
    close = pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.01, len(IDX)))), index=IDX)
    small, _, _, _ = backtest(close, NO_CASH, 30, IDX[40], 1_000, 0.0, 10)
    big, _, _, _ = backtest(close, NO_CASH, 30, IDX[40], 1_000_000, 0.0, 10)
    assert small.iloc[-1] / 1_000 < big.iloc[-1] / 1_000_000


def test_cash_rate_earned_when_out():
    close = pd.Series(np.linspace(200, 100, len(IDX)), index=IDX)  # bara nedåt: regeln ligger ute
    cash = pd.Series(0.0001, index=IDX)
    rule, _, trades, out = backtest(close, cash, 30, IDX[40], 1000, 0.0, 0.0)
    assert trades == 0 and out == 1
    assert rule.iloc[-1] > 1000


def test_next_day_execution_is_not_better_than_same_day_on_crash():
    up = np.linspace(100, 200, 200)
    crash = 200 * 0.97 ** np.arange(1, 101)
    close = pd.Series(np.concatenate([up, crash, np.full(300, crash[-1])]), index=IDX)
    same, _, _, _ = backtest(close, NO_CASH, 30, IDX[40], 1000, 0.0, 0.0, same_day=True)
    nxt, _, _, _ = backtest(close, NO_CASH, 30, IDX[40], 1000, 0.0, 0.0, same_day=False)
    assert nxt.iloc[-1] <= same.iloc[-1]


def test_break_even_fee_matches_definition():
    # Krasch med svängningar ovanpå, så att regeln gör många affärer
    trend = np.concatenate([np.linspace(100, 200, 200), np.linspace(200, 80, 100), np.linspace(80, 150, 300)])
    close = pd.Series(trend * (1 + 0.04 * np.sin(np.arange(len(IDX)) / 4)), index=IDX)
    be = break_even_fee(close, NO_CASH, 30, IDX[40], 1000, 0.0, False)
    rule, hold, trades, _ = backtest(close, NO_CASH, 30, IDX[40], 1000, be, 0.0)
    assert trades > 10
    assert 0 < be < 50
    assert abs(rule.iloc[-1] / hold.iloc[-1] - 1) < 1e-3
