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

### Google Colab

1. Öppna [colab.research.google.com](https://colab.research.google.com) → **GitHub**, kryssa i *Include private repos*.
2. Välj repot `HEVI-SE/PM` och branchen `claude/hopeful-mccarthy-bkmowc`, och klicka på `notebooks/kalibrering.ipynb`.
3. Colab hämtar bara notebooken, så setup-cellen klonar repot för att få med `pmcal/`. Eftersom repot är privat behövs en GitHub-token med läsrätt, sparad som Colab-secret med namnet `colab-pm` (eller `GITHUB_TOKEN`) (nyckelikonen 🔑 i vänstermenyn, med *Notebook access* påslagen).

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

## Glidande medelvärde-regeln (`scripts/ma_regel.py`)

Testar regeln "sälj när börsen stänger under sitt N-dagars medelvärde, köp när den stänger över, ligg i statsskuldväxlar däremellan" mot att bara behålla. Data hämtas från Yahoo: S&P 500 med utdelningar från 1988 (`^SP500TR`), prisindex från 1928 (`^GSPC`), och ränta från `^IRX` från 1960.

```bash
python3 scripts/ma_regel.py --start 1990 --kapital 10000 --avgift 0.05 --courtage 1
python3 scripts/ma_regel.py --ma 30 --ma 200 --graf resultat.png
python3 scripts/ma_regel.py --help
```

| Inställning | Betydelse |
|---|---|
| `--start` | Startår |
| `--kapital` | Startkapital |
| `--avgift` | Procent per affär (spread + procentuellt courtage) |
| `--courtage` | Fast belopp per affär |
| `--ma` | Medelvärde i dagar, kan anges flera gånger |
| `--ticker` | Annat index, t.ex. `^OMX` |
| `--samma-dag` | Handla på signalens stängning (optimistiskt). Standard är dagen efter. |
| `--graf` | Spara en graf |

Skriptet visar slutvärde, årlig avkastning, värsta fall, antal affärer, avgiften där regeln går jämnt upp, och resultatet per decennium.

## Begränsningar

- **API-fälten är inte verifierade mot live-data än.** Koden bygger på hur Polymarkets publika API:er brukar svara. Om något fält har ändrats är det `pmcal/api.py` som ska justeras.
- **Senaste handlade pris är inte samma sak som det pris du kan köpa till.** Spread och orderbokens djup modelleras bara grovt med `SLIPPAGE`.
- **Avgifter ändras.** Kontrollera Polymarkets aktuella avgifter, särskilt för snabba kryptomarknader.
- **Utfallsrisk:** marknader kan avgöras på oväntade sätt eller via tvister. Det syns inte i en kalibrering.
- **Många samtidiga tester** ger enstaka falska träffar.

Det här är ett analysverktyg, inte finansiell rådgivning.
