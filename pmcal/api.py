"""Läsning från Polymarkets öppna API:er (Gamma och CLOB), med lokal cache.

Inga konton eller nycklar behövs. Fältnamnen bygger på API:ernas publika svar;
om Polymarket ändrar något är det här filen som behöver justeras.
"""
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

GAMMA = "https://gamma-api.polymarket.com"
CLOB = "https://clob.polymarket.com"
CACHE_DIR = os.environ.get("PMCAL_CACHE", ".pm_cache")


def get_json(url, params=None, cache=True, pause=0.15, retries=5):
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    path = os.path.join(CACHE_DIR, urllib.parse.quote(url, safe="")[:240] + ".json")
    if cache and os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "pmcal/0.1"})
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.load(r)
            break
        except urllib.error.HTTPError as e:
            # Klientfel (4xx) blir inte bättre av att försöka igen, utom rate limit
            if (400 <= e.code < 500 and e.code != 429) or attempt == retries - 1:
                raise
            time.sleep(2 ** attempt)
        except Exception:
            # Nätverksfel: vänta och försök igen
            if attempt == retries - 1:
                raise
            time.sleep(2 ** attempt)
    time.sleep(pause)
    if cache:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f)
    return data


def parse_horizon(s):
    """'2m', '1h', '7d' -> sekunder."""
    units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    return int(float(s[:-1]) * units[s[-1]])


def parse_ts(s):
    if not s:
        return None
    s = s.replace("Z", "+00:00").replace(" ", "T")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def _as_list(v):
    return json.loads(v) if isinstance(v, str) else (v or [])


def _parse_market(m, category=None):
    """Binär marknad med entydigt utfall (ett ben = 1), annars None."""
    try:
        prices = [float(p) for p in _as_list(m.get("outcomePrices"))]
    except (TypeError, ValueError):
        return None
    tokens = _as_list(m.get("clobTokenIds"))
    outcomes = _as_list(m.get("outcomes"))
    if len(prices) != 2 or len(tokens) != 2 or sorted(prices) != [0.0, 1.0]:
        return None  # ogiltiga, 50/50-avgjorda och flerutfallsmarknader hoppas över
    # Handeln slutar vid det som kommer först av planerat slut och faktisk stängning
    ends = [t for t in (parse_ts(m.get("endDate")), parse_ts(m.get("closedTime"))) if t]
    if not ends:
        return None
    return {
        "id": m.get("id"),
        "question": m.get("question"),
        "slug": m.get("slug"),
        "category": category,
        "end": min(ends),
        "tokens": tokens,
        "outcomes": outcomes,
        "result": prices,
        "volume": float(m.get("volumeNum") or m.get("volume") or 0),
    }


def _iso(ts):
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _paged(url, params, consume, verbose, label, page):
    """
    Bläddrar bakåt i tiden med end_date_max istället för offset (API:t vägrar stora offset).
    `consume(sida)` anropas en gång per sida och returnerar True så länge fler sidor behövs.
    """
    end_max, seen = int(time.time()), set()
    while True:
        try:
            batch = get_json(url, {**params, "limit": page, "end_date_max": _iso(end_max),
                                   "order": "endDate", "ascending": "false"}, cache=False)
        except urllib.error.HTTPError as e:
            print(f"  [{label}] API-fel {e.code}, avbryter hämtningen")
            return
        fresh = [b for b in batch if b.get("id") not in seen]
        if not fresh:
            return
        seen.update(b.get("id") for b in fresh)
        ends = [parse_ts(b.get("endDate")) for b in fresh]
        ends = [t for t in ends if t]
        if not ends:
            return
        if verbose:
            print(f"  [{label}] sida med slutdatum {_iso(min(ends))[:10]} – {_iso(max(ends))[:10]}")
        if not consume(fresh):
            return
        end_max = min(ends) if min(ends) < end_max else end_max - 1


def fetch_markets(n=1000, contains=None, min_volume=0, page=500, verbose=True):
    """Avslutade binära marknader, nyast först, valfritt filtrerade på text i fråga/slug."""
    needle = contains.lower() if contains else None
    out = []

    def consume(batch):
        for m in batch:
            if needle and needle not in f"{m.get('question', '')} {m.get('slug', '')}".lower():
                continue
            pm = _parse_market(m, category=contains)
            if pm and pm["volume"] >= min_volume:
                out.append(pm)
        return len(out) < n

    _paged(f"{GAMMA}/markets", {"closed": "true"}, consume, verbose, contains or "alla", page)
    if verbose:
        print(f"  {len(out[:n])} marknader")
    return out[:n]


def fetch_markets_by_tag(tag_slug, n=1000, min_volume=0, page=100, verbose=True):
    """Avslutade binära marknader i en kategori, via events-endpointen (t.ex. 'politics', 'sports')."""
    out = []

    def consume(events):
        for e in events:
            for m in e.get("markets", []):
                pm = _parse_market(m, category=tag_slug)
                if pm and pm["volume"] >= min_volume:
                    out.append(pm)
        return len(out) < n

    _paged(f"{GAMMA}/events", {"closed": "true", "tag_slug": tag_slug}, consume, verbose, tag_slug, page)
    if verbose:
        print(f"  [{tag_slug}] {len(out[:n])} marknader")
    return out[:n]


def fetch_updown(asset="btc", interval="5m", n=500, min_volume=0, verbose=True, max_misses=50):
    """
    Korta upp/ner-marknader hämtas direkt via slug, t.ex. 'btc-updown-5m-<starttid>',
    där starttiden är en unix-tid jämnt delbar med intervallet. Kontrollera formatet i
    adressfältet på polymarket.com om inget hittas.
    """
    step = parse_horizon(interval)
    ts = (int(time.time()) // step - 2) * step  # senaste fönster som säkert är avgjort
    out, misses, tried = [], 0, 0
    while len(out) < n and misses < max_misses:
        slug = f"{asset}-updown-{interval}-{ts}"
        ts -= step
        tried += 1
        try:
            res = get_json(f"{GAMMA}/markets", {"slug": slug})
        except urllib.error.HTTPError:
            res = []
        pm = _parse_market(res[0], category=f"{asset} {interval}") if res else None
        if pm and pm["volume"] >= min_volume:
            out.append(pm)
            misses = 0
        else:
            misses += 1
        if verbose and tried % 50 == 0:
            print(f"  [{asset} {interval}] {len(out)} marknader ({tried} fönster provade)")
    if verbose:
        print(f"  [{asset} {interval}] {len(out)} marknader")
        if not out:
            print(f"  Hittade inga marknader med slug '{asset}-updown-{interval}-<tid>'. "
                  "Öppna en sådan marknad på polymarket.com och kolla adressen.")
    return out


def peek(**params):
    """Visar några rader ur /markets som de ser ut, för felsökning."""
    rows = get_json(f"{GAMMA}/markets", {"limit": 5, **params}, cache=False)
    keep = ("id", "slug", "question", "endDate", "closedTime", "closed", "outcomePrices", "volumeNum")
    return [{k: r.get(k) for k in keep} for r in rows]


def price_before(token, end, horizon):
    """Senaste handlade pris vid (end - horizon) sekunder, eller None om ingen handel nära den tiden."""
    target = end - horizon
    window = max(horizon, 3600)
    fidelity = 1 if horizon <= 6 * 3600 else 60  # minuter per punkt
    data = get_json(f"{CLOB}/prices-history", {
        "market": token, "startTs": target - window, "endTs": target, "fidelity": fidelity,
    })
    hist = [h for h in data.get("history", []) if h.get("t", 0) <= target]
    if not hist:
        return None
    last = max(hist, key=lambda h: h["t"])
    return float(last["p"])


def contracts(markets, horizon, verbose=True):
    """En rad per kontrakt (båda benen i varje marknad) med pris vid horisonten och utfall."""
    secs = parse_horizon(horizon)
    rows = []
    for i, m in enumerate(markets):
        for side, (token, y) in enumerate(zip(m["tokens"], m["result"])):
            try:
                p = price_before(token, m["end"], secs)
            except Exception as e:
                if verbose:
                    print(f"  fel för {m['id']}: {e}")
                continue
            if p is not None and 0 < p < 1:
                rows.append({
                    "market_id": m["id"], "question": m["question"], "category": m["category"],
                    "outcome": m["outcomes"][side] if side < len(m["outcomes"]) else side,
                    "horizon": horizon, "end": m["end"], "price": p, "won": int(y),
                    "volume": m["volume"],
                })
        if verbose and i % 100 == 0:
            print(f"  [{horizon}] {i}/{len(markets)} marknader, {len(rows)} kontrakt")
    return rows
