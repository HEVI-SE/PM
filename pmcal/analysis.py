"""Kalibrering: när ett kontrakt kostade X, vann det X % av gångerna?"""
import math

import pandas as pd

BUCKETS = [0.0, 0.05, 0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90, 0.95, 1.0]


def wilson(k, n, z=1.96):
    """95 % konfidensintervall för en andel."""
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    r = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - r) / d, (c + r) / d)


def calibrate(df, fee=0.0, slippage=0.01, by=None):
    """
    df: kolumner 'price' och 'won'. Returnerar en rad per prisintervall (och per grupp i `by`).

    ev_per_krona är avkastningen per insatt krona om man köper till pris + slippage och betalar
    avgift. 'edge' är True bara när EV är positivt OCH hela konfidensintervallet ligger över priset.
    """
    groups = df.groupby(by) if by else [(None, df)]
    out = []
    for key, g in groups:
        g = g.assign(bucket=pd.cut(g["price"], BUCKETS, right=False, include_lowest=True))
        for bucket, b in g.groupby("bucket", observed=True):
            n, wins = len(b), int(b["won"].sum())
            lo, hi = wilson(wins, n)
            cost = (b["price"] + slippage).clip(upper=0.999)
            row = {
                "intervall": str(bucket), "n": n, "snittpris": b["price"].mean(),
                "vinstfrekvens": wins / n, "ki_lag": lo, "ki_hog": hi,
                "ev_per_krona": (b["won"] / cost).mean() - 1 - fee,
            }
            row["avvikelse"] = row["vinstfrekvens"] - row["snittpris"]
            row["edge"] = row["ev_per_krona"] > 0 and lo > row["snittpris"] + slippage
            if by:
                row = {by: key, **row}
            out.append(row)
    return pd.DataFrame(out)


def brier(df):
    """Brier-poäng: medelkvadratfel mellan pris och utfall. Lägre = bättre prissatt."""
    return float(((df["price"] - df["won"]) ** 2).mean())
