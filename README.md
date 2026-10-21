# Atles de conflictes armats · Estat del Món

Mapa interactiu de tots els conflictes armats del món, amb una fitxa per a cadascun.
Lloc estàtic (carpeta `site/`) publicat a Render; les dades s'actualitzen amb una GitHub Action.

El manual complet del producte (posada en marxa, rutina mensual, metodologia i llicències)
és al document *Atles de conflictes armats · Manual de producte*.

## Estructura

| Carpeta | Contingut | Qui la toca |
| --- | --- | --- |
| `site/` | Pàgina del mapa i dades generades | L'Action (dades); tu, només per canviar el disseny |
| `raw/acled/` | Els 6 fitxers regionals agregats d'ACLED (.xlsx) | Tu, cada mes |
| `editorial/` | Un text per fitxa: `A-<id UCDP>.md` o `B-<ISO3>.md` | Tu |
| `config/` | Diccionaris: `actors.csv`, `titols.csv`, `paisos.csv` | Tu, segons l'informe |
| `scripts/` | Procés de dades en Python | — |
| `build/` | Dades intermèdies (memòria cau entre execucions) | L'Action |
| `informe/` | `darrer_informe.md`: novetats i tasques pendents | L'Action |

## Execució local

```bash
pip install -r requirements.txt
python scripts/fetch_ucdp.py      # UCDP (anual + Candidate)
python scripts/fetch_hapi.py      # desplaçats i refugiats (HDX HAPI)
python scripts/parse_acled.py     # llegeix raw/acled/*.xlsx
python scripts/build.py           # site/data/atles_data.json + informe
cd site && python -m http.server  # http://localhost:8000
```

## Regles

- **Categoria A**: conflictes amb almenys 25 morts en un any segons l'UCDP (any tancat o any en curs).
- **Categoria B**: països amb almenys 100 morts per violència política en 52 setmanes segons ACLED i cap conflicte A (`B_LLINDAR` a `scripts/build.py`).
- Les xifres de l'UCDP i d'ACLED no se sumen ni es comparen.

## Fonts

UCDP (Universitat d'Uppsala) · ACLED (acleddata.com) · OCHA HDX HAPI (desplaçats de l'OIM, refugiats d'ACNUR) · Natural Earth (fronteres).
