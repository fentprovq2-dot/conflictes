"""Baixa les bases de l'UCDP i les agrega per conflicte.

Sortida: build/ucdp.json

- Bases anuals (darrera versió publicada): UCDP/PRIO Armed Conflict, Non-State,
  One-sided Violence i Battle-Related Deaths (per conflicte).
- UCDP Candidate acumulada de l'any en curs (GEDEvent_vYY_01_YY_MM.csv).

Ús:
    python scripts/fetch_ucdp.py            # baixa de ucdp.uu.se
    python scripts/fetch_ucdp.py --local D  # llegeix els fitxers d'una carpeta D
"""
import argparse, csv, io, json, os, re, sys, zipfile
from collections import defaultdict
from datetime import date

BASE = 'https://ucdp.uu.se/downloads/'
OUT = os.path.join(os.path.dirname(__file__), '..', 'build', 'ucdp.json')
HIST_FROM = 2016  # primer any de la sèrie històrica de cada fitxa

PATTERNS = {
    'acd': r'ucdpprio/ucdp-prio-acd-(\d+)-csv\.zip',
    'nonstate': r'nsos/ucdp-nonstate-(\d+)-csv\.zip',
    'onesided': r'nsos/ucdp-onesided-(\d+)-csv\.zip',
    'brd': r'brd/ucdp-brd-conf-(\d+)-csv\.zip',
}
CAND = r'candidateged/(GEDEvent_v(\d+)_01_(\d+)_(\d+)\.csv)'


def http_get(url):
    import requests
    r = requests.get(url, timeout=180, headers={'User-Agent': 'atles-conflictes (Estat del Mon)'})
    r.raise_for_status()
    return r.content


def latest(html, pattern):
    found = [(int(m.group(1)), m.group(0)) for m in re.finditer(pattern, html)]
    if not found:
        raise SystemExit(f'No trobo cap fitxer que segueixi el patró {pattern} a {BASE}')
    return max(found)[1]


def latest_candidate(html):
    found = [(int(m.group(3)), int(m.group(4)), m.group(0)) for m in re.finditer(CAND, html)]
    if not found:
        raise SystemExit('No trobo la UCDP Candidate acumulada a la pàgina de descàrregues')
    return max(found)[2]


def read_csv_bytes(b, name):
    if name.endswith('.zip'):
        z = zipfile.ZipFile(io.BytesIO(b))
        inner = next(n for n in z.namelist() if n.lower().endswith('.csv'))
        b = z.read(inner)
    text = b.decode('utf-8-sig', errors='replace')
    return list(csv.DictReader(io.StringIO(text)))


def load(args):
    files = {}
    if args.local:
        names = os.listdir(args.local)
        for k, pat in PATTERNS.items():
            pat_file = pat.split('/')[-1]
            m = sorted(n for n in names if re.fullmatch(pat_file, n))
            if not m: raise SystemExit(f'Falta el fitxer de {k} a {args.local}')
            files[k] = (m[-1], open(os.path.join(args.local, m[-1]), 'rb').read())
        m = sorted(n for n in names if re.fullmatch(CAND.split('/')[-1].replace('(', '').replace(')', ''), n))
        if not m: raise SystemExit(f'Falta la UCDP Candidate a {args.local}')
        files['candidate'] = (m[-1], open(os.path.join(args.local, m[-1]), 'rb').read())
    else:
        html = http_get(BASE).decode('utf-8', errors='replace')
        for k, pat in PATTERNS.items():
            path = latest(html, pat)
            print('Baixant', path, file=sys.stderr)
            files[k] = (path.split('/')[-1], http_get(BASE + path))
        path = latest_candidate(html)
        print('Baixant', path, file=sys.stderr)
        files['candidate'] = (path.split('/')[-1], http_get(BASE + path))
    return {k: (n, read_csv_bytes(b, n)) for k, (n, b) in files.items()}


def num(x):
    try: return float(x) if x not in ('', None) else 0.0
    except ValueError: return 0.0


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--local'); args = ap.parse_args()
    F = load(args)
    acd, ns, os_, brd, cand = (F[k][1] for k in ('acd', 'nonstate', 'onesided', 'brd', 'candidate'))
    y_closed = max(int(r['year']) for r in acd)
    cand_dates = [r['date_start'][:10] for r in cand if r.get('date_start')]
    y_cur = int(max(cand_dates)[:4]) if cand_dates else y_closed + 1
    m_cur = int(re.search(CAND.split('/')[-1], F['candidate'][0]).group(4)) if re.search(CAND.split('/')[-1], F['candidate'][0]) else 12
    Y = str(y_closed)

    R = {}
    def g(i):
        return R.setdefault(i, {'id': i})

    def hist(i, y, v):
        if int(y) >= HIST_FROM:
            h = g(i).setdefault('h', {}); h[y] = h.get(y, 0) + v

    for r in brd: hist(r['conflict_id'], r['year'], num(r['bd_best']))
    for r in ns: hist(r['conflict_id'], r['year'], num(r['best_fatality_estimate']))
    for r in os_: hist(r['conflict_id'], r['year'], num(r['best_fatality_estimate']))

    for r in acd:
        if r['year'] != Y: continue
        c = g(r['conflict_id'])
        c.update(t=1, loc=r['location'], a=[x for x in (r['side_a'], r['side_a_2nd']) if x],
                 b=[x for x in (r['side_b'], r['side_b_2nd']) if x], inc=r['incompatibility'],
                 terr=r['territory_name'], int=int(r['intensity_level']), toc=int(r['type_of_conflict']),
                 start=r['start_date'], start2=r['start_date2'], gw=r['gwno_loc'], act_prev=1)
    for r in brd:
        if r['year'] != Y: continue
        c = g(r['conflict_id']); d = c.setdefault('dp', [0, 0, 0])
        d[0] += num(r['bd_low']); d[1] += num(r['bd_best']); d[2] += num(r['bd_high'])
    for r in ns:
        if r['year'] != Y: continue
        c = g(r['conflict_id'])
        c.update(t=2, loc=r['location'], a=[r['side_a_name']], b=[r['side_b_name']], org=int(r['org'] or 0) or None,
                 start=r['start_date'], gw=r['gwno_location'], act_prev=1,
                 dp=[num(r['low_fatality_estimate']), num(r['best_fatality_estimate']), num(r['high_fatality_estimate'])])
    for r in os_:
        if r['year'] != Y: continue
        c = g(r['conflict_id'])
        c.update(t=3, loc=r['location'], a=[r['actor_name']], b=['Civilians'], gov=int(r['is_government_actor'] or 0),
                 gw=r['gwno_location'], act_prev=1,
                 dp=[num(r['low_fatality_estimate']), num(r['best_fatality_estimate']), num(r['high_fatality_estimate'])])

    for e in cand:
        c = g(e['conflict_new_id'])
        c.setdefault('t', int(e['type_of_violence'])); c['nm'] = e['conflict_name']
        c['ev'] = c.get('ev', 0) + 1
        d = c.setdefault('dc', [0, 0, 0]); d[0] += num(e['low']); d[1] += num(e['best']); d[2] += num(e['high'])
        c['civ'] = c.get('civ', 0) + num(e['deaths_civilians'])
        ds = e['date_start'][:10]
        if ds[:4] == str(y_cur):
            m = c.setdefault('m', [0] * 12); m[int(ds[5:7]) - 1] += num(e['best'])
        c['_lw'] = c.get('_lw', 0) + 1; c['_la'] = c.get('_la', 0) + num(e['latitude']); c['_lo'] = c.get('_lo', 0) + num(e['longitude'])
        cc = c.setdefault('_cc', {}); cc[e['country']] = cc.get(e['country'], 0) + 1
        if 'a' not in c: c['a'] = [e['side_a']]; c['b'] = [e['side_b']]
        if e.get('adm_1'):
            adm = c.setdefault('_adm', {}); adm[e['adm_1']] = adm.get(e['adm_1'], 0) + num(e['best']) + 0.01

    fy = {}
    for rows in (acd, ns, os_):
        for r in rows:
            fy[r['conflict_id']] = min(fy.get(r['conflict_id'], 9999), int(r['year']))

    out = []
    for c in R.values():
        if not (c.get('act_prev') or c.get('ev')): continue
        rec = {k: v for k, v in c.items() if not k.startswith('_')}
        rec['fy'] = fy.get(c['id'])
        if c.get('_lw'):
            rec['ll'] = [round(c['_lo'] / c['_lw'], 2), round(c['_la'] / c['_lw'], 2)]
            rec['cc'] = [k for k, _ in sorted(c['_cc'].items(), key=lambda x: -x[1])]
        if c.get('_adm'):
            rec['adm'] = [k for k, _ in sorted(c['_adm'].items(), key=lambda x: -x[1])[:3]]
        if 'm' in rec: rec['m'] = rec['m'][:m_cur]
        for k in ('dp', 'dc'):
            if k in rec: rec[k] = [round(x) for x in rec[k]]
        if 'civ' in rec: rec['civ'] = round(rec['civ'])
        out.append(rec)

    meta = {'year_closed': y_closed, 'year_current': y_cur, 'month_current': m_cur,
            'files': {k: F[k][0] for k in F}, 'generated': date.today().isoformat()}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump({'meta': meta, 'conflicts': out}, open(OUT, 'w'), ensure_ascii=False, separators=(',', ':'))
    print(f"UCDP: {len(out)} conflictes · any tancat {y_closed} · Candidate fins al mes {m_cur} de {y_cur}", file=sys.stderr)


if __name__ == '__main__':
    main()
