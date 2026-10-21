"""Baixa de l'HDX HAPI (OCHA) els desplaçats interns i els refugiats per país d'origen.

Sortida: build/hapi.json

Ús:
    python scripts/fetch_hapi.py
    python scripts/fetch_hapi.py --idp FITXER.csv --ref FITXER.csv   # fitxers ja baixats
"""
import argparse, csv, io, json, os, re, sys
from datetime import date

CKAN = 'https://data.humdata.org/api/3/action/package_show?id='
OUT = os.path.join(os.path.dirname(__file__), '..', 'build', 'hapi.json')
MAX_ANYS = 3  # antiguitat màxima de les dades de desplaçats


def http_get(url):
    import requests
    r = requests.get(url, timeout=300, headers={'User-Agent': 'atles-conflictes (Estat del Mon)'})
    r.raise_for_status()
    return r.content


def resources(pkg):
    return json.loads(http_get(CKAN + pkg))['result']['resources']


def rows(b):
    return csv.DictReader(io.StringIO(b.decode('utf-8-sig', errors='replace')))


def idps(b):
    """Per a cada operació: el nivell administratiu més baix disponible i la data més recent, sumant les files."""
    op = {}
    for r in rows(b):
        key = (r['location_code'], r['operation'])
        lv = int(r['admin_level'] or 0)
        k2 = (lv, r['reference_period_end'][:10])
        d = op.setdefault(key, {})
        d[k2] = d.get(k2, 0) + int(float(r['population'] or 0))
    # Per país: de les operacions amb dades dels 18 mesos anteriors a la dada més recent, la xifra més alta
    # (evita quedar-se amb una operació regional recent i petita). Es descarten dades de més de MAX_ANYS anys.
    limit = date.today().replace(year=date.today().year - MAX_ANYS).isoformat()
    per = {}
    for (iso, oper), d in op.items():
        lv = min(k[0] for k in d)
        last = max(k for k in d if k[0] == lv)
        if last[1] >= limit:
            per.setdefault(iso, []).append({'p': d[last], 'd': last[1], 'o': oper})
    out = {}
    for iso, ops in per.items():
        newest = max(o['d'] for o in ops)
        y, m = int(newest[:4]), int(newest[5:7]) - 18
        while m <= 0: y -= 1; m += 12
        recent = [o for o in ops if o['d'] >= f'{y:04d}-{m:02d}']
        out[iso] = max(recent, key=lambda o: (o['p'], o['d']))
    return out


def refugees(b):
    data = list(rows(b))
    years = sorted({r['reference_period_start'][:4] for r in data})
    y = years[-1]
    has_all = any(r['gender'] == 'all' and r['age_range'] == 'all' for r in data)
    out = {}
    for r in data:
        if r['reference_period_start'][:4] != y: continue
        if has_all and not (r['gender'] == 'all' and r['age_range'] == 'all'): continue
        if r['population_group'] not in ('REF', 'ASY', 'OIP'): continue
        out[r['origin_location_code']] = out.get(r['origin_location_code'], 0) + int(float(r['population'] or 0))
    return {k: {'n': v, 'y': y} for k, v in out.items()}, y


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--idp'); ap.add_argument('--ref'); a = ap.parse_args()
    if a.idp:
        b_idp = open(a.idp, 'rb').read()
    else:
        res = resources('hdx-hapi-idps')
        url = next(r['url'] for r in res if r['url'].endswith('.csv'))
        print('Baixant', url, file=sys.stderr); b_idp = http_get(url)
    if a.ref:
        b_ref = open(a.ref, 'rb').read()
    else:
        res = resources('hdx-hapi-refugees')
        # el recurs que cobreix els anys més recents: ..._global_AAAA_AAAA.csv
        def span(u):
            m = re.search(r'_(\d{4})_(\d{4})\.csv', u); return int(m.group(1)) if m else 0
        url = max((r['url'] for r in res if r['url'].endswith('.csv')), key=span)
        print('Baixant', url, file=sys.stderr); b_ref = http_get(url)
    idp = idps(b_idp)
    ref, y = refugees(b_ref)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump({'meta': {'generated': date.today().isoformat(), 'ref_year': y}, 'idp': idp, 'ref': ref},
              open(OUT, 'w'), ensure_ascii=False, separators=(',', ':'))
    print(f'HAPI: {len(idp)} països amb desplaçats, {len(ref)} amb refugiats ({y})', file=sys.stderr)


if __name__ == '__main__':
    main()
