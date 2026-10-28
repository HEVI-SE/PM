# PM: kalibreringsanalys av Polymarket

Finns det kontrakt på Polymarket som systematiskt är felprissatta, så att en långsam aktör kan tjäna pengar på andras optimism eller övertro?

Projektet testar det med historisk data: **när ett kontrakt kostade X öre, vann det verkligen X % av gångerna?** En avvikelse är bara intressant om den är större än avgifter och spread, statistiskt säker och finns kvar över tid.

Allt är läsning av offentlig data. Inga konton, nycklar eller order.

## Kom igång

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
jupyter lab notebooks/kalibrering.ipynb
```

Börja med `N_MARKETS = 50` i notebooken för att se att hämtningen fungerar, och öka sedan.

## Innehåll

| Sökväg | Vad |
|---|---|
| `notebooks/kalibrering.ipynb` | Själva analysen: hämtning, kalibreringstabell, kurvor, EV efter avgifter, stabilitet över tid |
| `pmcal/api.py` | Hämtning från Polymarkets Gamma- och CLOB-API:er, med cache i `.pm_cache/` |
| `pmcal/analysis.py` | Kalibrering, konfidensintervall (Wilson), EV, Brier-poäng |
| `tests/` | Tester av analysdelen med syntetisk data |

```bash
python3 -m pytest -q
```

## Läsa resultatet

- **avvikelse** = vinstfrekvens − pris. Positivt betyder att kontrakten var för billiga.
- **ev_per_krona** = avkastning per insatt krona efter avgift och spread.
- **edge** = positivt EV *och* hela 95 %-konfidensintervallet över priset. Lita bara på den kolumnen: i de billigaste intervallen ger slumpen ofta högt EV utan någon verklig fördel.
- Notebooken delar också datan i äldre och nyare halva. En fördel som bara finns i den ena halvan är troligen slump.

## Begränsningar

- **API-fälten är inte verifierade mot live-data än.** Koden bygger på hur Polymarkets publika API:er brukar svara. Om något fält har ändrats är det `pmcal/api.py` som ska justeras.
- **Senaste handlade pris är inte samma sak som det pris du kan köpa till.** Spread och orderbokens djup modelleras bara grovt med `SLIPPAGE`.
- **Avgifter ändras.** Kontrollera Polymarkets aktuella avgifter, särskilt för snabba kryptomarknader.
- **Utfallsrisk:** marknader kan avgöras på oväntade sätt eller via tvister. Det syns inte i en kalibrering.
- **Många samtidiga tester** ger enstaka falska träffar.

Det här är ett analysverktyg, inte finansiell rådgivning.
