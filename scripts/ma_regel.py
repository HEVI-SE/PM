#!/usr/bin/env python3
"""
Backtest av glidande medelvärde-regeln mot att bara behålla (köp och behåll).

Regeln: ligg i aktiemarknaden när den stänger över sitt N-dagars glidande medelvärde,
gå ur när den stänger under, och ligg i statsskuldväxlar (ränta) när du är ute.

Signalen syns vid stängning, så affären görs som standard vid NÄSTA dags stängning
(--samma-dag ger det optimistiska antagandet att man hinner handla på signalens stängning).

Exempel:
  python3 scripts/ma_regel.py
  python3 scripts/ma_regel.py --start 1990 --kapital 100000 --avgift 0.05 --courtage 1
  python3 scripts/ma_regel.py --ma 30 --ma 50 --ma 200 --start 1960 --avgift 0.2
  python3 scripts/ma_regel.py --ticker ^OMX --start 2000      # annat index

Avgift är i procent per affär (spread + procentuellt courtage). Courtage är ett fast
belopp per affär i samma valuta som kapitalet. Ett byte (sälj eller köp) räknas som en affär.
"""
import argparse
import math
import sys

import numpy as np
import pandas as pd

TRADING_DAYS = 252


def load_prices(ticker, start_year):
    import yfinance as yf

    if ticker is None:
        # Totalavkastning (med utdelningar) finns från 1988, prisindex från 1927
        ticker = "^SP500TR" if start_year >= 1988 else "^GSPC"
    # Hämta extra historik före start så att medelvärdet finns från dag ett
    df = yf.download(ticker, start=f"{start_year - 2}-01-01", progress=False, auto_adjust=True)
    if df.empty:
        sys.exit(f"Ingen data för {ticker}.")
    close = df["Close"].squeeze().dropna()
    close.name = ticker
    return close


def load_cash_rate(index, fallback):
    """Daglig ränta från 13-veckors statsskuldväxlar (^IRX, från 1960), annars fast årsränta."""
    import yfinance as yf

    daily_fallback = (1 + fallback / 100) ** (1 / TRADING_DAYS) - 1
    try:
        irx = yf.download("^IRX", start=index[0], progress=False, auto_adjust=True)["Close"].squeeze()
    except Exception:
        irx = pd.Series(dtype=float)
    yearly = irx.reindex(index).ffill() / 100
    daily = (1 + yearly) ** (1 / TRADING_DAYS) - 1
    return daily.fillna(daily_fallback)


def backtest(close, cash_daily, ma, start, capital, fee_pct, courtage, same_day=False):
    """
    Returnerar (dagliga värden för regeln, för köp och behåll, antal affärer, andel dagar ute).
    Avgiften dras vid varje byte, både procent och fast courtage.
    """
    fee = fee_pct / 100
    signal = (close > close.rolling(ma).mean()).astype(int)
    position = signal if same_day else signal.shift(1)  # 1 = i marknaden under dagen

    mask = close.index >= start
    close, position, cash_daily = close[mask], position[mask].fillna(0), cash_daily[mask]
    ret = close.pct_change().fillna(0)

    rule = np.empty(len(close))
    value, prev = capital, 0  # börjar ute, så första dagen i marknaden räknas som ett köp
    trades = 0
    for i, (r, c, pos) in enumerate(zip(ret.values, cash_daily.values, position.values)):
        if i > 0:
            value *= 1 + (r if prev == 1 else c)
        if pos != prev:
            value = value * (1 - fee) - courtage
            trades += 1
            prev = pos
        rule[i] = max(value, 0)
        if value <= 0:
            value = 0

    hold_start = capital * (1 - fee) - courtage
    hold = hold_start * close / close.iloc[0]
    out_share = 1 - position.mean()
    return pd.Series(rule, index=close.index), hold, trades, out_share


def cagr(series):
    years = (series.index[-1] - series.index[0]).days / 365.25
    if years <= 0 or series.iloc[0] <= 0 or series.iloc[-1] <= 0:
        return float("nan")
    return (series.iloc[-1] / series.iloc[0]) ** (1 / years) - 1


def max_drawdown(series):
    return float((series / series.cummax() - 1).min())


def per_decade(rule, hold):
    rows = []
    for decade, idx in rule.groupby(rule.index.year // 10 * 10).groups.items():
        r, h = rule.loc[idx], hold.loc[idx]
        if len(r) < 60:
            continue
        rows.append({"decennium": f"{decade}-talet", "regel": cagr(r), "behåll": cagr(h),
                     "skillnad": cagr(r) - cagr(h)})
    return pd.DataFrame(rows)


def break_even_fee(close, cash_daily, ma, start, capital, courtage, same_day):
    """Avgift i procent där regeln och köp och behåll slutar lika."""
    def gap(f):
        rule, hold, _, _ = backtest(close, cash_daily, ma, start, capital, f, courtage, same_day)
        return rule.iloc[-1] - hold.iloc[-1]

    lo, hi = 0.0, 50.0
    if gap(lo) <= 0:
        return 0.0
    if gap(hi) > 0:
        return float("inf")
    for _ in range(40):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if gap(mid) > 0 else (lo, mid)
    return (lo + hi) / 2


def money(x):
    return f"{x:,.0f}".replace(",", " ")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", type=int, default=1990, help="startår (standard 1990)")
    ap.add_argument("--kapital", type=float, default=10_000, help="startkapital (standard 10 000)")
    ap.add_argument("--avgift", type=float, default=0.05,
                    help="avgift i procent per affär, spread + procentuellt courtage (standard 0.05)")
    ap.add_argument("--courtage", type=float, default=0.0, help="fast courtage per affär (standard 0)")
    ap.add_argument("--ma", type=int, action="append", help="medelvärde i dagar, kan anges flera gånger (standard 30)")
    ap.add_argument("--ticker", help="Yahoo-ticker, standard S&P 500 (^SP500TR från 1988, annars ^GSPC)")
    ap.add_argument("--ranta", type=float, default=3.0,
                    help="årsränta i procent när ränta saknas, före 1960 (standard 3)")
    ap.add_argument("--samma-dag", action="store_true",
                    help="handla på signalens stängning (optimistiskt, som i de flesta inlägg)")
    ap.add_argument("--graf", help="spara en graf till denna fil, t.ex. resultat.png")
    a = ap.parse_args()
    mas = a.ma or [30]

    close = load_prices(a.ticker, a.start)
    cash = load_cash_rate(close.index, a.ranta)
    start = pd.Timestamp(f"{a.start}-01-01")
    if close.index[0] > start:
        print(f"Obs: data för {close.name} börjar {close.index[0].date()}.")
    if close.name == "^GSPC":
        print("Obs: ^GSPC är ett prisindex utan utdelningar. Det missgynnar köp och behåll, "
              "eftersom regeln får ränta när den är ute men behåll inte får utdelningar. "
              "Starta 1988 eller senare för totalavkastning.")

    first = close[close.index >= start].index[0].date()
    last = close.index[-1].date()
    print(f"\n{close.name}  {first} – {last}  |  kapital {money(a.kapital)}  |  "
          f"avgift {a.avgift}% + courtage {money(a.courtage)} per affär  |  "
          f"{'samma dag' if a.samma_dag else 'handel dagen efter signal'}\n")

    results = {}
    for ma in mas:
        rule, hold, trades, out = backtest(close, cash, ma, start, a.kapital, a.avgift, a.courtage, a.samma_dag)
        results[ma] = rule
        be = break_even_fee(close, cash, ma, start, a.kapital, a.courtage, a.samma_dag)
        winner = "REGELN" if rule.iloc[-1] > hold.iloc[-1] else "BEHÅLL"
        print(f"=== {ma}-dagars medelvärde: {winner} vinner ===")
        print(f"  Slutvärde      regel {money(rule.iloc[-1]):>15}   behåll {money(hold.iloc[-1]):>15}"
              f"   ({rule.iloc[-1] / hold.iloc[-1]:.2f}x)")
        print(f"  Årlig avk.     regel {cagr(rule):>14.2%}   behåll {cagr(hold):>14.2%}")
        print(f"  Värsta fall    regel {max_drawdown(rule):>14.2%}   behåll {max_drawdown(hold):>14.2%}")
        print(f"  Affärer {trades}, ute {out:.1%} av dagarna, "
              f"brytpunkt för avgift ≈ {be:.3f}% per affär (med courtage {money(a.courtage)})")
        dec = per_decade(rule, hold)
        if not dec.empty:
            print("  Per decennium (årlig avkastning):")
            for _, r in dec.iterrows():
                print(f"    {r['decennium']:<11} regel {r['regel']:>7.2%}   behåll {r['behåll']:>7.2%}"
                      f"   skillnad {r['skillnad']:>+7.2%}")
        print()

    if a.graf:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(11, 6))
        ax.plot(hold.index, hold.values, label="Behåll", color="#2b6cb0", lw=1.5)
        for ma, rule in results.items():
            ax.plot(rule.index, rule.values, label=f"{ma}-dagarsregeln", lw=1.2)
        ax.set_yscale("log")
        ax.set(title=f"{close.name}: avgift {a.avgift}% + courtage {money(a.courtage)} per affär",
               ylabel="Värde (log)")
        ax.legend()
        ax.grid(alpha=0.3)
        fig.tight_layout()
        fig.savefig(a.graf, dpi=120)
        print(f"Graf sparad: {a.graf}")


if __name__ == "__main__":
    main()
