"""Construeix les dades del mapa i l'informe mensual.

Entrades:  build/ucdp.json, build/hapi.json, build/acled.json, config/*.csv, editorial/*.md
Sortides:  site/data/atles_data.json, informe/darrer_informe.md
"""
import csv, glob, html, json, os, re, sys
from collections import Counter
from datetime import date

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
P = lambda *a: os.path.join(ROOT, *a)

B_LLINDAR = 100          # morts ACLED en 52 setmanes per entrar a la categoria B
LLINDAR_UCDP = 25        # criteri de l'UCDP

# ---------------------------------------------------------------- entrades
U = json.load(open(P('build', 'ucdp.json')))
H = json.load(open(P('build', 'hapi.json'))) if os.path.exists(P('build', 'hapi.json')) else {'idp': {}, 'ref': {}, 'meta': {}}
A_ = json.load(open(P('build', 'acled.json'))) if os.path.exists(P('build', 'acled.json')) else None
W = json.load(open(P('site', 'data', 'world-50m.json')))
Y0, Y1, M1 = U['meta']['year_closed'], U['meta']['year_current'], U['meta']['month_current']


def read_csv(name):
    with open(P('config', name), encoding='utf-8') as f:
        return list(csv.DictReader(f))


PAISOS = read_csv('paisos.csv')
BY_GW = {int(r['gwno']): r for r in PAISOS if r['gwno']}
BY_UCDP = {r['nom_ucdp']: r for r in PAISOS if r['nom_ucdp']}
BY_ISO3 = {r['iso3']: r for r in PAISOS if r['iso3']}
BY_ACLED = {r['nom_acled']: r for r in PAISOS if r['nom_acled']}
CA_COUNTRY = {r['nom_ucdp']: r['nom_ca'] for r in PAISOS if r['nom_ucdp']}
ACTORS = {r['nom_ucdp']: (r['nom_ca'], r['curt_ca'] or r['nom_ca']) for r in read_csv('actors.csv')}
TITOLS = {r['ucdp_id']: r['titol_ca'] for r in read_csv('titols.csv')}
REPORT = {'sense_traduccio': Counter(), 'sense_pais': Counter(), 'avisos': []}

# ---------------------------------------------------------------- centroides de país
def centroids():
    tr = W['transform']; (sx, sy), (tx, ty) = tr['scale'], tr['translate']
    arcs = []
    for a in W['arcs']:
        x = y = 0; pts = []
        for dx, dy in a:
            x += dx; y += dy; pts.append((x * sx + tx, y * sy + ty))
        arcs.append(pts)
    ring = lambda idx: [p for i in idx for p in (arcs[i] if i >= 0 else arcs[~i][::-1])]
    out = {}
    for g in W['objects']['countries']['geometries']:
        if not g.get('id') or not g.get('arcs'): continue
        polys = g['arcs'] if g['type'] == 'MultiPolygon' else [g['arcs']]
        best = max((ring(p[0]) for p in polys), key=len)
        A = cx = cy = 0
        for (x0, y0), (x1, y1) in zip(best, best[1:] + best[:1]):
            f = x0 * y1 - x1 * y0; A += f; cx += (x0 + x1) * f; cy += (y0 + y1) * f
        out[g['id']] = [round(cx / (3 * A), 2), round(cy / (3 * A), 2)] if abs(A) > 1e-9 else list(best[0])
    out.update({'250': [2.4, 46.6], '840': [-98.5, 39.5], '643': [45, 55]})
    return out
CENT = centroids()

# ---------------------------------------------------------------- traduccions
def actor(name, short=False):
    name = name.strip()
    if name in ACTORS: return ACTORS[name][1 if short else 0]
    m = re.match(r'Government of (.+)$', name)
    if m:
        c = m.group(1).strip()
        if c not in CA_COUNTRY: REPORT['sense_pais'][c] += 1
        return CA_COUNTRY.get(c, c)
    if re.search(r'[A-Za-z]', name) and not name.startswith('XXX'):
        REPORT['sense_traduccio'][name] += 1
    return name


def side_list(s, short=False):
    out = []
    for part in (s or []):
        for p in re.split(r',\s*(?=Government of )|,\s+', part) if part else []:
            if p.strip(): out.append(actor(p, short))
    return list(dict.fromkeys(out))


TOC = {1: 'Extrasistèmic', 2: 'Interestatal', 3: 'Intern', 4: 'Intern internacionalitzat'}
ORG = {1: 'grups armats organitzats', 2: 'grups de suport', 3: 'grups identitaris (ètnics, religiosos, comunals)'}
INC = {'1': 'Territori', '2': 'Govern', '3': 'Govern i territori'}


def ca_title(c):
    if c['id'] in TITOLS: return TITOLS[c['id']]
    t = c['t']; a = side_list(c.get('a'), True); b = side_list(c.get('b'), True)
    if t == 3: return f"{a[0] if a else '?'} – violència contra civils"
    if t == 2: return f"{a[0]} – {b[0]}" if a and b else (c.get('nm') or '')
    if c.get('toc') == 2 or (b and b[0] in CA_COUNTRY.values()): return f"{a[0]} – {b[0]}"
    terr = c.get('terr')
    if terr and terr != 'Islamic State' and terr.lower() not in ' '.join(b).lower():
        return f"{a[0] if a else ''} – {', '.join(b)} ({terr})"
    return f"{a[0] if a else ''} – {', '.join(b[:2])}"


def countries_of(c):
    iso = []
    for n in c.get('cc') or []:
        r = BY_UCDP.get(n)
        if r and r['iso_num'] not in iso: iso.append(r['iso_num'])
        elif not r: REPORT['sense_pais'][n] += 1
    for g in (c.get('gw') or '').split(','):
        if g.strip():
            r = BY_GW.get(int(g))
            if r and r['iso_num'] not in iso: iso.append(r['iso_num'])
    return iso


ISO_N = {r['iso_num']: r for r in PAISOS if r['iso_num']}
is_xxx = lambda c: 'XXX' in (c.get('nm') or '') + ' '.join(c.get('a') or []) + ' '.join(c.get('b') or [])

# ---------------------------------------------------------------- textos editorials
def md_to_html(t):
    t = html.escape(t.strip())
    t = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', t)
    t = re.sub(r'\*(.+?)\*', r'<i>\1</i>', t)
    t = re.sub(r'\[([^\]]+)\]\((https?://[^)\s]+)\)', r'<a href="\2" target="_blank" rel="noopener">\1</a>', t)
    return ''.join(f'<p>{p.strip()}</p>' for p in re.split(r'\n\s*\n', t) if p.strip())


EDIT = {}
for f in glob.glob(P('editorial', '*.md')):
    key = os.path.basename(f)[:-3]
    if key.startswith('_'): continue
    raw = open(f, encoding='utf-8').read()
    meta = {}
    m = re.match(r'---\s*\n(.*?)\n---\s*\n', raw, re.S)
    if m:
        for line in m.group(1).splitlines():
            if ':' in line: k, v = line.split(':', 1); meta[k.strip()] = v.strip()
        raw = raw[m.end():]
    if raw.strip(): EDIT[key] = {'html': md_to_html(raw), 'revisat': meta.get('revisat')}

# ---------------------------------------------------------------- categoria A
out, xxx = [], {'n': 0, 'deaths': 0}
for c in U['conflicts']:
    dc = c.get('dc') or [0, 0, 0]
    if is_xxx(c):
        if c.get('dc'): xxx['n'] += 1; xxx['deaths'] += dc[1]
        continue
    act_prev, act_cur = bool(c.get('act_prev')), dc[1] >= LLINDAR_UCDP
    if not (act_prev or act_cur): continue
    status = 'actiu' if act_prev and act_cur else ('nou' if act_cur else 'latent')
    iso = countries_of(c)
    if c['id'] in ('234', '483') and '275' not in iso: iso.append('275')   # Gaza i Cisjordània
    ll = c.get('ll') or (CENT.get(iso[0]) if iso else None)
    if not ll:
        REPORT['avisos'].append(f"Conflicte {c['id']} sense coordenades: no surt al mapa"); continue
    a, b = side_list(c.get('a')), side_list(c.get('b'))
    two_sided = c['t'] != 1 or c.get('toc') == 2
    key = f"A-{c['id']}"
    cc = [CA_COUNTRY.get(n, n) for n in (c.get('cc') or [])][:6] or [ISO_N[i]['nom_ca'] for i in iso if i in ISO_N]
    out.append({
        'key': key, 'id': c['id'], 't': c['t'], 'title': ca_title(c), 'ucdp': c.get('nm') or c.get('loc') or '',
        'a': a[:1], 'a2': a[1:], 'b': b[:1] if two_sided else b, 'b2': b[1:] if two_sided else [],
        'toc': TOC.get(c.get('toc')), 'inc': INC.get(c.get('inc') or ''), 'terr': c.get('terr') if c.get('terr') != 'Islamic State' else None,
        'int': c.get('int'), 'org': ORG.get(c.get('org')), 'gov': c.get('gov'), 'start': c.get('start'), 'start2': c.get('start2'),
        'fy': c.get('fy'), 'dp': c.get('dp'), 'dc': c.get('dc'), 'civ': c.get('civ', 0), 'ev': c.get('ev', 0), 'm': c.get('m'),
        'h': c.get('h'), 'll': ll, 'iso': iso, 'cc': cc, 'adm': c.get('adm'),
        'reg': ISO_N[iso[0]]['regio'] if iso and iso[0] in ISO_N else 'Altres', 'status': status, 'ed': EDIT.get(key),
    })

# violència UCDP per sota del llindar, per país (per a les fitxes B)
below = {}
for c in U['conflicts']:
    if is_xxx(c) or c.get('act_prev') or not c.get('dc') or c['dc'][1] >= LLINDAR_UCDP: continue
    iso = countries_of(c)
    if iso: below.setdefault(iso[0], []).append([ca_title(c), c['dc'][1]])
for k in below: below[k].sort(key=lambda x: -x[1])

# ---------------------------------------------------------------- ACLED
TYPE_CA = {'Battles': 'Combats', 'Explosions/Remote violence': 'Explosions i atacs a distància', 'Violence against civilians': 'Violència contra civils'}
acl, hot = {}, []
if A_:
    for cname, wk in A_['cw_fat'].items():
        r = BY_ACLED.get(cname)
        if not r:
            if not re.search(r'Ocean|Sea$', cname) and sum(wk) >= 25: REPORT['sense_pais'][f'{cname} (ACLED)'] += 1
            continue
        acl[r['iso3']] = {'fat52': sum(wk), 'ev52': sum(A_['cw_ev'][cname]), 'wk': wk, 'types': {}, 'top': []}
    for a in A_['adm']:
        r = BY_ACLED.get(a['c'])
        if r and r['iso3'] in acl:
            for k, v in a['t12'].items(): acl[r['iso3']]['types'][k] = acl[r['iso3']]['types'].get(k, 0) + v
            acl[r['iso3']]['top'].append([a['a'], a['f12'], a['e12']])
        if (a['f12'] > 0 or a['e12'] >= 3) and not re.search(r'Ocean|Sea$', a['c']):   # centroides marítims no fiables
            dom = max(a['t12'].items(), key=lambda x: x[1])[0] if a['t12'] else None
            hot.append([a['ll'][0], a['ll'][1], a['f12'], a['e12'], r['nom_ca'] if r else a['c'], a['a'], TYPE_CA.get(dom, dom)])
    for v in acl.values(): v['top'] = sorted(v['top'], key=lambda x: (-x[1], -x[2]))[:5]

# ---------------------------------------------------------------- context per país
ctx = {}
for iso3, r in BY_ISO3.items():
    e = {}
    if iso3 in acl: e['acled'] = {'fat52': acl[iso3]['fat52'], 'ev52': acl[iso3]['ev52']}
    if iso3 in H['idp']: e['idp'] = H['idp'][iso3]
    if iso3 in H['ref']: e['ref'] = H['ref'][iso3]
    if e and r['iso_num']: ctx[r['iso_num']] = dict(e, name=r['nom_ca'], iso3=iso3)

# ---------------------------------------------------------------- categoria B
isoA = {i for r in out for i in r['iso']}
bs = []
for iso3, a in acl.items():
    r = BY_ISO3[iso3]
    if r['iso_num'] in isoA or a['fat52'] < B_LLINDAR or r['iso_num'] not in CENT: continue
    key = f'B-{iso3}'
    bs.append({'key': key, 'iso3': iso3, 'isoN': r['iso_num'], 'title': f"{r['nom_ca']} – violència política", 'name': r['nom_ca'],
               'reg': r['regio'], 'll': CENT[r['iso_num']], 'fat12': a['fat52'], 'ev12': a['ev52'], 'wk': a['wk'],
               'types': [[TYPE_CA.get(k, k), v] for k, v in sorted(a['types'].items(), key=lambda x: -x[1])],
               'top': a['top'], 'below': below.get(r['iso_num'], [])[:8], 'cc': [r['nom_ca']], 'ed': EDIT.get(key)})
bs.sort(key=lambda b: -b['fat12'])

# ---------------------------------------------------------------- sortida
MESOS = ['gener', 'febrer', 'març', 'abril', 'maig', 'juny', 'juliol', 'agost', 'setembre', 'octubre', 'novembre', 'desembre']
meta = {'y0': Y0, 'y1': Y1, 'm1': M1, 'm1_name': MESOS[M1 - 1], 'ucdp_files': U['meta']['files'], 'ref_year': H['meta'].get('ref_year'),
        'b_threshold': B_LLINDAR, 'generated': date.today().isoformat()}
if A_:
    meta.update({'acled_from': A_['meta']['weeks_from'], 'acled_to': A_['meta']['weeks_to'], 'acled_w12': A_['meta']['window12_from'], 'weeks': A_['weeks']})

prev_path = P('site', 'data', 'atles_data.json')
prev = json.load(open(prev_path)) if os.path.exists(prev_path) else None
data = {'meta': meta, 'xxx': xxx, 'conflicts': out, 'b': bs, 'ctx': ctx, 'hot': hot}
json.dump(data, open(prev_path, 'w'), ensure_ascii=False, separators=(',', ':'))

# ---------------------------------------------------------------- informe
L = [f"# Informe d'actualització · {date.today().isoformat()}", '',
     f"- UCDP: any tancat {Y0}; Candidate fins a {MESOS[M1 - 1]} de {Y1} ({U['meta']['files']['candidate']})",
     f"- ACLED: {'fins a la setmana del ' + A_['meta']['weeks_to'] if A_ else 'sense dades'}",
     f"- Categoria A: {len(out)} conflictes ({Counter(r['status'] for r in out)['actiu']} actius, "
     f"{Counter(r['status'] for r in out)['nou']} nous o reactivats, {Counter(r['status'] for r in out)['latent']} sota el llindar el {Y1})",
     f"- Categoria B: {len(bs)} països ({', '.join(b['name'] for b in bs) or 'cap'})",
     f"- Morts sense actor identificat (UCDP, {Y1}): {format(xxx['deaths'], ',').replace(',', '.')}", '']
if prev:
    pk = {c.get('key') or ('A-' + c['id']): c for c in prev['conflicts']}
    nk = {c['key']: c for c in out}
    nous = [nk[k] for k in nk if k not in pk]
    fora = [pk[k] for k in pk if k not in nk]
    canvi = [(pk[k], nk[k]) for k in nk if k in pk and pk[k].get('status') != nk[k]['status']]
    L += ['## Canvis respecte de la versió anterior', '']
    L += [f"- **Nou al mapa:** {c['title']} (UCDP {c['id']})" for c in nous] or ['- Cap conflicte nou.']
    L += [f"- **Surt del mapa:** {c['title']}" for c in fora]
    L += [f"- **Canvi d'estat:** {n['title']}: {p.get('status')} → {n['status']}" for p, n in canvi]
    pb = {b['iso3'] for b in prev.get('b', [])}; nb = {b['iso3'] for b in bs}
    L += [f"- **Entra a la categoria B:** {BY_ISO3[i]['nom_ca']}" for i in nb - pb]
    L += [f"- **Surt de la categoria B:** {BY_ISO3[i]['nom_ca']}" for i in pb - nb]
    L.append('')
L += ['## Actors sense traducció (afegiu-los a config/actors.csv)', '']
L += [f'- `{k}` ({v} aparicions)' for k, v in REPORT['sense_traduccio'].most_common()] or ['- Cap.']
L += ['', '## Països desconeguts (afegiu-los a config/paisos.csv)', '']
L += [f'- `{k}`' for k in REPORT['sense_pais']] or ['- Cap.']
top = sorted(out, key=lambda c: -(c['dc'] or [0, 0])[1])[:30]
sense = [c for c in top if not c['ed']]
L += ['', f'## Fitxes sense text editorial entre els 30 conflictes amb més morts del {Y1}', '']
L += [f"- `editorial/{c['key']}.md` · {c['title']}" for c in sense] or ['- Totes tenen text.']
if REPORT['avisos']: L += ['', '## Avisos', ''] + [f'- {a}' for a in REPORT['avisos']]
os.makedirs(P('informe'), exist_ok=True)
open(P('informe', 'darrer_informe.md'), 'w', encoding='utf-8').write('\n'.join(L) + '\n')
print('\n'.join(L[:8]), file=sys.stderr)
