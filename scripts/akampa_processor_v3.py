#!/usr/bin/env python3
"""
akampa_processor_v3.py
──────────────────────────────────────────────────────────────────────
Lee el reporte semanal de Cloudbeds (1 archivo XLSX con 4 pestañas)
y el reporte de WeTravel (opcional), y actualiza akampa-data-v3.js
acumulando el histórico semana a semana.

Uso:
  python3 akampa_processor_v3.py \
    --reporte    Reporte_Sales_Intelligence.xlsx \
    --existing   akampa-data-v3.js \
    --output     akampa-data-v3.js \
    --netlify_site  TU_SITE_ID \
    --netlify_token TU_TOKEN

  # Con WeTravel (opcional):
    --wetravel_lv  Reporting_Payments_WeTravel_LaVentana.xlsx
    --wetravel_yuc Reporting_Payments_WeTravel_Yucatan.xlsx
"""

import argparse, json, sys, re
from collections import defaultdict
from datetime import datetime, date as ddate
from pathlib import Path

try:
    from openpyxl import load_workbook
except ImportError:
    sys.exit("ERROR: pip install openpyxl")

# ── Catálogo de viajes Bahía Mag (fechas fijas) ───────────────────
TRIP_CATALOG = [
    (1,"Ballena Jorobada","2025-2026","2026-01-04","2026-01-07"),
    (2,"Ballena Jorobada","2025-2026","2026-01-08","2026-01-11"),
    (3,"Ballena Jorobada","2025-2026","2026-01-11","2026-01-14"),
    (4,"Ballena Gris","2025-2026","2026-01-15","2026-01-18"),
    (5,"Ballena Gris","2025-2026","2026-01-18","2026-01-21"),
    (6,"Ballena Gris","2025-2026","2026-01-22","2026-01-25"),
    (7,"Ballena Gris","2025-2026","2026-01-25","2026-01-28"),
    (8,"Ballena Gris","2025-2026","2026-01-30","2026-02-02"),
    (9,"Ballena Gris","2025-2026","2026-02-02","2026-02-05"),
    (10,"Ballena Gris","2025-2026","2026-02-05","2026-02-08"),
    (11,"Ballena Gris","2025-2026","2026-02-08","2026-02-11"),
    (12,"Ballena Gris x Kēntro","2025-2026","2026-02-12","2026-02-15"),
    (13,"Ballena Gris","2025-2026","2026-02-15","2026-02-18"),
    (14,"Ballena Gris","2025-2026","2026-02-19","2026-02-22"),
    (15,"Ballena Gris","2025-2026","2026-02-22","2026-02-25"),
    (16,"Ballena Gris","2025-2026","2026-02-26","2026-03-01"),
    (17,"Ballena Gris","2025-2026","2026-03-01","2026-03-04"),
    (18,"Ballena Gris","2025-2026","2026-03-05","2026-03-08"),
    (19,"Ballena Gris","2025-2026","2026-03-08","2026-03-11"),
    (20,"Mi Compa Chava 3.0","2025-2026","2026-03-13","2026-03-16"),
    (21,"Ballena Gris","2025-2026","2026-03-16","2026-03-19"),
    (22,"Ballena Gris","2025-2026","2026-03-19","2026-03-22"),
    (23,"Ballena Gris","2025-2026","2026-03-22","2026-03-25"),
    (24,"Ballena Gris","2025-2026","2026-03-26","2026-03-29"),
    (25,"Ballena Gris","2025-2026","2026-03-29","2026-04-01"),
    (26,"Ocean Safari","2025-2026","2026-04-02","2026-04-05"),
    (27,"Ocean Safari","2025-2026","2026-04-05","2026-04-08"),
    (28,"Retiro Kalea x La Magia del Caos","2025-2026","2026-04-09","2026-04-12"),
    (29,"Ocean Safari","2025-2026","2026-04-12","2026-04-15"),
    (30,"Marlin & Sardine Run","2026-2027","2026-10-15","2026-10-18"),
    (31,"Marlin & Sardine Run","2026-2027","2026-10-18","2026-10-21"),
    (32,"Marlin & Sardine Run","2026-2027","2026-10-22","2026-10-25"),
    (33,"Marlin & Sardine Run","2026-2027","2026-10-25","2026-10-28"),
    (34,"Marlin & Sardine Run","2026-2027","2026-10-29","2026-11-01"),
    (35,"Marlin & Sardine Run","2026-2027","2026-11-01","2026-11-04"),
    (36,"Marlin & Sardine Run","2026-2027","2026-11-05","2026-11-08"),
    (37,"Marlin & Sardine Run","2026-2027","2026-11-08","2026-11-11"),
    (38,"Marlin & Sardine Run","2026-2027","2026-11-12","2026-11-15"),
    (39,"Marlin & Sardine Run","2026-2027","2026-11-15","2026-11-18"),
    (40,"Marlin & Sardine Run","2026-2027","2026-11-19","2026-11-22"),
    (41,"Marlin & Sardine Run","2026-2027","2026-11-22","2026-11-25"),
    (42,"Marlin & Sardine Run","2026-2027","2026-11-26","2026-11-29"),
    (43,"Marlin & Sardine Run","2026-2027","2026-11-29","2026-12-02"),
    (44,"Marlin & Sardine Run","2026-2027","2026-12-03","2026-12-06"),
    (45,"Marlin & Sardine Run","2026-2027","2026-12-06","2026-12-09"),
    (46,"Marlin & Sardine Run","2026-2027","2026-12-10","2026-12-13"),
    (47,"Ballena Jorobada","2026-2027","2026-12-17","2026-12-20"),
    (48,"Ballena Jorobada","2026-2027","2026-12-23","2026-12-26"),
    (49,"Ballena Jorobada","2026-2027","2026-12-30","2027-01-02"),
    (50,"Ballena Jorobada","2026-2027","2027-01-07","2027-01-10"),
    (51,"Ballena Jorobada","2026-2027","2027-01-14","2027-01-17"),
    (52,"Ballena Gris","2026-2027","2027-01-21","2027-01-24"),
    (53,"Ballena Gris","2026-2027","2027-01-28","2027-01-31"),
    (54,"Ballena Gris","2026-2027","2027-02-04","2027-02-07"),
    (55,"Ballena Gris","2026-2027","2027-02-11","2027-02-14"),
    (56,"Ballena Gris","2026-2027","2027-02-18","2027-02-21"),
    (57,"Ballena Gris","2026-2027","2027-02-25","2027-02-28"),
    (58,"Ballena Gris","2026-2027","2027-03-04","2027-03-07"),
    (59,"Ballena Gris","2026-2027","2027-03-18","2027-03-21"),
    (60,"Ballena Gris","2026-2027","2027-03-25","2027-03-28"),
    (61,"Ballena Gris","2026-2027","2027-04-01","2027-04-04"),
    (62,"Ballena Gris","2026-2027","2027-04-08","2027-04-11"),
    (63,"Ballena Gris","2026-2027","2027-04-15","2027-04-18"),
    (64,"Ballena Gris","2026-2027","2027-04-22","2027-04-25"),
]
BUYOUT_IDS = {28}

# ── Helpers ──────────────────────────────────────────────────────
def xl_rows(wb, sheet):
    return list(wb[sheet].iter_rows(values_only=True))

def find_header(rows, col0):
    return next(i for i, r in enumerate(rows) if r[0] == col0)

def parse_date(v):
    if not v: return None
    try: return datetime.strptime(str(v)[:10], '%Y-%m-%d').date()
    except: return None

def iso_week(d):
    iso = d.isocalendar()
    return f"{iso[0]}-W{str(iso[1]).zfill(2)}"

# ── Parse single XLSX with 4 sheets ──────────────────────────────
def parse_cloudbeds(path):
    wb = load_workbook(path, read_only=True)

    # 1. ReservationBalanceDue — clean format: Grand Total / Paid / Balance Due
    rows = xl_rows(wb, 'ReservationBalanceDue')
    hi   = find_header(rows, 'Reservation Number')
    bal  = defaultdict(lambda: {'cobrado':0,'pend':0,'total':0})
    for r in rows[hi+1:]:
        if not r[0] or not r[3]: continue
        ci = parse_date(r[3])
        if not ci: continue
        try:
            bal[ci]['total']   += float(r[6] or 0)
            bal[ci]['cobrado'] += float(r[7] or 0)
            bal[ci]['pend']    += float(r[8] or 0)
        except: pass

    # 2. CheckinReview — guest and room counts
    rows2 = xl_rows(wb, 'CheckinReview')
    hi2   = find_header(rows2, 'Check-In Date')
    ci_data = defaultdict(lambda: {'guests':0,'rooms':0})
    curr = None
    for r in rows2[hi2+1:]:
        if r[0]: curr = parse_date(r[0])
        if curr and r[9] is not None:
            try:
                ci_data[curr]['guests'] += int(r[9] or 0)
                ci_data[curr]['rooms']  += int(r[11] or 0)
            except: pass

    # 3. TotalRevenuePerGuest — monthly summary
    rows3  = xl_rows(wb, 'TotalRevenuePerGuest')
    hi3    = find_header(rows3, 'Stay Date')
    MN     = ['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic']
    monthly_new = {}
    for r in rows3[hi3+1:]:
        if not r[0] or not str(r[0])[:4].isdigit(): continue
        if not r[1] or r[1] == 0: continue
        ym = str(r[0])[:7]
        yr, mo = ym.split('-')
        season = '2025-2026' if int(yr)==2026 and int(mo)<=9 else '2026-2027'
        monthly_new.setdefault(season, {})[MN[int(mo)-1]] = {
            'm':   MN[int(mo)-1],
            'g':   int(r[2] or 0),
            'occ': round(float(r[6] or 0), 2),
            'rpg': round(float(r[4])) if r[4] and r[4] != '-' else 0,
            'rev': round(float(r[3] or 0))
        }

    return bal, ci_data, monthly_new

# ── Merge monthly: new data wins, old data preserved ─────────────
def merge_monthly(existing_monthly, new_monthly):
    """
    new_monthly wins for months it contains.
    Months not in new_monthly are kept from existing.
    """
    result = {}
    all_seasons = set(list(existing_monthly.keys()) + list(new_monthly.keys()))
    for season in all_seasons:
        old = {m['m']: m for m in existing_monthly.get(season, [])}
        new = new_monthly.get(season, {})  # dict keyed by month abbr
        # new wins for its months, old kept for the rest
        merged = {**old, **new}
        result[season] = list(merged.values())
    return result

# ── Build trips: new data wins, historical preserved ─────────────
def build_trips(bal, ci_data, existing_trips):
    """
    For each trip in catalog:
    - If new report has data for that check-in date → use it
    - If not → keep existing data from previous JSON
    """
    today = ddate.today()
    existing_map = {t['id']: t for t in existing_trips}

    trips = []
    weekly = defaultdict(float)

    for tid, name, season, start_s, end_s in TRIP_CATALOG:
        start = datetime.strptime(start_s, '%Y-%m-%d').date()
        end   = datetime.strptime(end_s,   '%Y-%m-%d').date()
        status = 'past' if end < today else 'next' if start <= today else 'future'

        # Check if new report has data for this trip
        ci    = ci_data.get(start)
        fin   = bal.get(start)
        prev  = existing_map.get(tid, {})

        if fin:
            # New data available — use it
            rooms   = ci['rooms']  if ci  else prev.get('rooms', 0)
            guests  = ci['guests'] if ci  else prev.get('guests', 0)
            cap     = 17 if rooms > 15 else 15
            occ     = round((rooms / cap) * 100, 1) if rooms else 0
            cobrado = round(max(0, fin['cobrado']))
            pend    = round(max(0, fin['pend']))
            total   = round(fin['total']) if fin['total'] > 0 else cobrado + pend
        elif prev:
            # No new data — preserve existing
            rooms   = prev.get('rooms', 0)
            guests  = prev.get('guests', 0)
            cap     = prev.get('cap', 15)
            occ     = prev.get('occ', 0)
            cobrado = prev.get('cobrado', 0)
            pend    = prev.get('pend', 0)
            total   = prev.get('total', 0)
        else:
            # Brand new trip with no data yet
            rooms = guests = cobrado = pend = total = 0
            cap = 15; occ = 0

        t = {'id':tid,'name':name,'s':season,'start':start_s,'end':end_s,
             'rooms':rooms,'cap':cap,'occ':occ,'guests':guests,'status':status,
             'cobrado':cobrado,'pend':pend,'total':total}

        if tid in BUYOUT_IDS:
            t.update({'buyout':True,'rooms':15,'cap':15,'occ':100,'guests':30})

        trips.append(t)

        # Weekly accumulation
        if cobrado > 0:
            weekly[iso_week(start)] += cobrado

    return trips, dict(weekly)

# ── WeTravel parser ───────────────────────────────────────────────
def parse_wetravel(path, dest_label, existing_trips):
    wb   = load_workbook(path, read_only=True)
    rows = list(wb.active.iter_rows(values_only=True))
    hi   = next(i for i, r in enumerate(rows) if r[0] == 'Date created (UTC)')
    today = ddate.today()

    MES = {'enero':'01','febrero':'02','marzo':'03','abril':'04','mayo':'05',
           'junio':'06','julio':'07','agosto':'08','septiembre':'09',
           'octubre':'10','noviembre':'11','diciembre':'12'}

    by_trip = defaultdict(list)
    for r in rows[hi+1:]:
        if not r[0] or r[4] != 'Successful': continue
        trip_name = str(r[21]) if r[21] else 'Sin nombre'
        pdate = parse_date(str(r[0])[:10].replace('/','-'))
        participants = [p.strip() for p in str(r[20]).split(',') if p.strip()] if r[20] else []
        by_trip[trip_name].append({
            'date': str(pdate), 'amount': float(r[3] or 0),
            'participants': participants
        })

    def extract_dates(name):
        m = re.search(r'\((\d+)[- ]+(?:(\d+)\s+)?(\w+)\s+(\d{4})', name, re.IGNORECASE)
        if not m: return None, None
        d1, d2, mes, yr = m.group(1), m.group(2), m.group(3).lower(), m.group(4)
        mo = MES.get(mes)
        if not mo: return None, None
        return f"{yr}-{mo}-{d1.zfill(2)}", f"{yr}-{mo}-{(d2 or d1).zfill(2)}"

    # Build trip list — merge with existing to preserve historical payments
    existing_map = {f"{t['start']}_{t['name']}": t for t in existing_trips}
    trips = []
    for i, (trip_name, payments) in enumerate(by_trip.items(), 1):
        start_s, end_s = extract_dates(trip_name)
        if not start_s:
            start_s = payments[0]['date'] if payments else str(today)
            end_s   = start_s
        start  = datetime.strptime(start_s, '%Y-%m-%d').date()
        end    = datetime.strptime(end_s,   '%Y-%m-%d').date()
        status = 'past' if end < today else 'next' if start <= today else 'future'
        clean  = re.sub(r'\s*\(.*?\)\s*$', '', trip_name).strip()
        clean  = re.sub(r'^[^:]+:\s*', '', clean)
        trips.append({'id':i,'name':clean,'dest':dest_label,'start':start_s,
                      'end':end_s,'cap':30,'status':status,'payments':payments})

    trips.sort(key=lambda t: t['start'])
    return trips

# ── Netlify deploy ────────────────────────────────────────────────
def deploy_to_netlify(js_path, site_id, token):
    """Upload both index.html and akampa-data-v3.js via Netlify deploy API."""
    import urllib.request, urllib.error, hashlib
    from pathlib import Path as _P

    # Load both files
    js_content   = _P(js_path).read_bytes()
    js_sha1      = hashlib.sha1(js_content).hexdigest()

    # Find index.html — same folder as the .js file
    html_path = _P(js_path).parent / 'akampa-dashboard-v3.html'
    if not html_path.exists():
        # Try common locations
        for candidate in [
            _P.home() / 'Desktop' / 'akampa-deploy' / 'index.html',
            _P.home() / 'Documents' / 'Cowork' / 'akampa' / 'akampa-dashboard-v3.html',
        ]:
            if candidate.exists():
                html_path = candidate
                break

    if html_path.exists():
        html_content = html_path.read_bytes()
        html_sha1    = hashlib.sha1(html_content).hexdigest()
        files_manifest = {
            '/index.html':         html_sha1,
            '/akampa-data-v3.js':  js_sha1,
        }
        print(f"   Subiendo index.html + akampa-data-v3.js")
    else:
        html_content = None
        files_manifest = {'/akampa-data-v3.js': js_sha1}
        print(f"   ⚠ index.html no encontrado — subiendo solo .js")

    base = 'https://api.netlify.com/api/v1'

    def req(method, url, body=None, raw=None, ct='application/json'):
        data = raw if raw else (json.dumps(body).encode() if body else None)
        r = urllib.request.Request(url, data=data, method=method)
        r.add_header('Authorization', f'Bearer {token}')
        r.add_header('Content-Type',  ct)
        try:
            with urllib.request.urlopen(r, timeout=30) as resp:
                return json.loads(resp.read()), resp.status
        except urllib.error.HTTPError as e:
            return json.loads(e.read().decode() or '{}'), e.code

    # 1. Create deploy with file manifest
    resp, status = req('POST', f'{base}/sites/{site_id}/deploys',
                       body={'files': files_manifest, 'async': False})
    if status not in (200, 201):
        print(f"❌ Netlify error {status}: {resp}")
        return False

    deploy_id = resp['id']
    required  = resp.get('required', [])
    print(f"   Deploy {deploy_id[:12]}... creado ({len(required)} archivos requeridos)")

    # 2. Upload required files
    for sha, content_bytes, filename in [
        (js_sha1,   js_content,   'akampa-data-v3.js'),
        (html_sha1 if html_content else None, html_content, 'index.html'),
    ]:
        if not content_bytes: continue
        if required and sha not in required: continue
        resp2, s2 = req('PUT', f'{base}/deploys/{deploy_id}/files/{filename}',
                        raw=content_bytes, ct='application/octet-stream')
        if s2 not in (200, 201):
            print(f"❌ Upload error {filename} {s2}: {resp2}")
            return False
        print(f"   ✓ {filename} subido")

    print(f"✅ Netlify actualizado — https://akampa-sales.netlify.app")
    return True

# ── Main ─────────────────────────────────────────────────────────
def main():
    p = argparse.ArgumentParser(description='Akampa v3 weekly processor')
    p.add_argument('--reporte',       required=True,  help='XLSX con 4 pestañas de Cloudbeds')
    p.add_argument('--wetravel_lv',   default=None)
    p.add_argument('--wetravel_yuc',  default=None)
    p.add_argument('--existing',      default=None,   help='akampa-data-v3.js anterior')
    p.add_argument('--output',        default='akampa-data-v3.js')
    p.add_argument('--netlify_site',  default=None)
    p.add_argument('--netlify_token', default=None)
    args = p.parse_args()

    # ── Load existing data ────────────────────────────────────────
    existing = {'bahia_mag':{'trips':[],'monthly':{},'weekly':{}},'la_ventana':{'trips':[]},'yucatan':{'trips':[]}}
    if args.existing:
        ep = Path(args.existing).expanduser()
        if ep.exists():
            raw = ep.read_text(encoding='utf-8')
            # Strip JS wrapper: window.AKAMPA_DATA = {...};
            raw = re.sub(r'^window\.AKAMPA_DATA\s*=\s*', '', raw.strip()).rstrip(';')
            try:
                existing = json.loads(raw)
                print(f"📂 Histórico cargado: {len(existing['bahia_mag']['trips'])} viajes BM")
            except Exception as e:
                print(f"⚠ No se pudo leer histórico: {e} — comenzando desde cero")

    # ── Parse new Cloudbeds report ────────────────────────────────
    print(f"📂 Procesando reporte Cloudbeds: {args.reporte}")
    bal, ci_data, monthly_new = parse_cloudbeds(args.reporte)
    print(f"   Balance Due: {len(bal)} fechas · Check-in: {len(ci_data)} fechas · Monthly: {sum(len(v) for v in monthly_new.values())} meses")

    # Merge monthly (new wins for its months)
    merged_monthly = merge_monthly(existing['bahia_mag'].get('monthly',{}), monthly_new)

    # Build trips (new wins, historical preserved)
    trips, new_weekly = build_trips(bal, ci_data, existing['bahia_mag'].get('trips',[]))

    # Merge weekly (accumulate)
    old_weekly = existing['bahia_mag'].get('weekly', {})
    merged_weekly = {**old_weekly, **new_weekly}  # new wins for overlapping weeks

    print(f"   Trips: {len(trips)} · Weekly weeks: {len(merged_weekly)}")

    # ── WeTravel ─────────────────────────────────────────────────
    if args.wetravel_lv:
        print(f"📂 Procesando WeTravel La Ventana...")
        lv_trips = parse_wetravel(args.wetravel_lv, 'La Ventana', existing['la_ventana'].get('trips',[]))
        print(f"   {len(lv_trips)} viajes")
    else:
        lv_trips = existing['la_ventana'].get('trips', [])
        print(f"   La Ventana: conservando {len(lv_trips)} viajes existentes")

    if args.wetravel_yuc:
        yuc_trips = parse_wetravel(args.wetravel_yuc, 'Yucatán', existing['yucatan'].get('trips',[]))
    else:
        yuc_trips = existing['yucatan'].get('trips', [])

    # ── Build final data ──────────────────────────────────────────
    data = {
        'meta': {
            'kpi_anual':    30000000,
            'last_updated': str(ddate.today()),
            'property':     'Akampa · All Destinations'
        },
        'bahia_mag': {
            'trips':   trips,
            'monthly': merged_monthly,
            'weekly':  merged_weekly
        },
        'la_ventana': {'trips': lv_trips},
        'yucatan':    {'trips': yuc_trips}
    }

    # ── Write .js file ────────────────────────────────────────────
    out = Path(args.output).expanduser()
    js  = 'window.AKAMPA_DATA = ' + json.dumps(data, ensure_ascii=False, indent=2) + ';'
    out.write_text(js, encoding='utf-8')
    print(f"\n✅ {out.name} actualizado — {ddate.today()}")

    # ── Deploy to Netlify ─────────────────────────────────────────
    if args.netlify_site and args.netlify_token:
        print("🚀 Subiendo a Netlify...")
        deploy_to_netlify(str(out), args.netlify_site, args.netlify_token)
    else:
        print("ℹ  Sin credenciales Netlify — sube el archivo manualmente")

if __name__ == '__main__':
    main()
