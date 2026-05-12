#!/usr/bin/env python3
"""
weekly_digest.py — Reporte semanal de Akampa Sales Intelligence.

Calcula métricas de la semana actual (lun-vie), compara con la semana anterior,
detecta refunds y trips en riesgo, y envía el email vía Resend API.

Uso:
  python3 scripts/weekly_digest.py                   # envía email real
  python3 scripts/weekly_digest.py --dry-run          # imprime HTML sin enviar

Env vars:
  RESEND_API_KEY  (requerido para envío)
  DIGEST_FROM     (default: "onboarding@resend.dev" — sandbox)
  DIGEST_TO       (default: "daniel@akampa.mx", separar múltiples con coma)
"""
import argparse, json, os, re, subprocess, sys, urllib.request, urllib.error
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

MX_TZ = ZoneInfo("America/Mexico_City")
TEMPLATE_PATH = Path(__file__).parent / "digest_template.html"
DATA_PATH     = Path(__file__).parent.parent / "akampa-data-v3.js"


# ── Helpers ───────────────────────────────────────────────────────────
def load_data(path):
    txt = Path(path).read_text()
    m = re.search(r"window\.AKAMPA_DATA\s*=\s*({.*})\s*;?\s*$", txt, re.DOTALL)
    if not m:
        raise SystemExit(f"❌ No se pudo parsear {path}")
    return json.loads(m.group(1))


def load_data_at_commit(commit_hash):
    """Carga akampa-data-v3.js desde un commit específico."""
    try:
        result = subprocess.run(
            ["git", "show", f"{commit_hash}:akampa-data-v3.js"],
            capture_output=True, text=True, check=True,
        )
        m = re.search(r"window\.AKAMPA_DATA\s*=\s*({.*})\s*;?\s*$", result.stdout, re.DOTALL)
        return json.loads(m.group(1)) if m else None
    except (subprocess.CalledProcessError, json.JSONDecodeError):
        return None


def find_commit_before(target_date):
    """Encuentra el último commit que tocó akampa-data-v3.js antes de target_date."""
    try:
        result = subprocess.run(
            ["git", "log",
             f"--before={target_date.isoformat()}",
             "--format=%H", "-1", "--", "akampa-data-v3.js"],
            capture_output=True, text=True, check=True,
        )
        return result.stdout.strip() or None
    except subprocess.CalledProcessError:
        return None


def iso_week_num(d):
    return d.isocalendar()[1]


def n0(v):
    """Formato MXN con separadores."""
    return f"{round(v):,}".replace(",", ",")


def fmt_money(v):
    if abs(v) >= 1_000_000:
        return f"{v/1_000_000:.2f}M"
    if abs(v) >= 1_000:
        return f"{v/1_000:.0f}k"
    return f"{round(v):,}"


def parse_date(s):
    return datetime.strptime(s, "%Y-%m-%d").date()


# ── Métricas ──────────────────────────────────────────────────────────
def sales_in_range(data, start, end):
    """Suma ventas (cobrado) por booking date en el rango [start, end] inclusivo."""
    bm = sum(v for k, v in data["bahia_mag"].get("daily", {}).items()
             if start <= parse_date(k) <= end)
    lv = 0
    for t in data.get("la_ventana", {}).get("trips", []):
        for p in t.get("payments", []):
            if start <= parse_date(p["date"]) <= end:
                lv += p.get("amount", 0)
    yuc = 0
    for t in data.get("yucatan", {}).get("trips", []):
        for p in t.get("payments", []):
            if start <= parse_date(p["date"]) <= end:
                yuc += p.get("amount", 0)
    return bm, lv, yuc


def pipeline_pendiente(data):
    """Suma pend de trips futuros/próximos, no buyout."""
    total = 0
    count = 0
    today = date.today()
    for t in data["bahia_mag"].get("trips", []):
        if t.get("buyout"):
            continue
        try:
            end = parse_date(t["end"])
        except (KeyError, ValueError):
            continue
        if end < today:
            continue
        pend = t.get("pend", 0) or 0
        if pend > 0:
            total += pend
            count += 1
    return total, count


def meta_progress(data):
    """% completado vs meta total. Usa cobrado + pendiente (matchea total del dashboard)."""
    target = data.get("meta", {}).get("kpi_anual") or data.get("meta", {}).get("kpi") or 30_000_000
    revenue = 0
    for t in data["bahia_mag"].get("trips", []):
        revenue += (t.get("cobrado", 0) or 0) + (t.get("pend", 0) or 0)
    for t in data.get("la_ventana", {}).get("trips", []):
        for p in t.get("payments", []):
            revenue += p.get("amount", 0) or 0
    for t in data.get("yucatan", {}).get("trips", []):
        for p in t.get("payments", []):
            revenue += p.get("amount", 0) or 0
    pct = (revenue / target * 100) if target else 0
    return revenue, target, pct


def detect_refunds(current, previous):
    """Compara trips BM entre snapshots: detecta cobrado o total decreases."""
    if not previous:
        return []
    prev_map = {t["id"]: t for t in previous["bahia_mag"].get("trips", [])}
    refunds = []
    for t in current["bahia_mag"].get("trips", []):
        p = prev_map.get(t["id"])
        if not p:
            continue
        delta = (t.get("cobrado", 0) or 0) - (p.get("cobrado", 0) or 0)
        if delta < -500:  # umbral mínimo $500 para evitar ruido
            refunds.append({
                "name": t["name"],
                "start": t["start"],
                "delta": delta,
            })
    return sorted(refunds, key=lambda r: r["delta"])


def trips_at_risk(data, days_ahead=60):
    """Trips BM próximos en días_ahead que NO están en banda 'viable' o 'sold out'."""
    today = date.today()
    cutoff = today + timedelta(days=days_ahead)
    risky = []
    for t in data["bahia_mag"].get("trips", []):
        if t.get("buyout"):
            continue
        try:
            start = parse_date(t["start"])
        except (KeyError, ValueError):
            continue
        if not (today <= start <= cutoff):
            continue
        g = t.get("guests", 0) or 0
        if g == 28 or (g and (g % 8 == 0 or g % 9 == 0)):
            continue  # sold out o viable
        risky.append({
            "name": t["name"],
            "start": t["start"],
            "end":   t["end"],
            "guests": g,
            "days_to": (start - today).days,
        })
    return sorted(risky, key=lambda x: x["days_to"])


def fetch_new_bookings_this_week(monday, friday):
    """Lista reservas creadas en el rango [monday, friday] de la semana actual.
    Cloudbeds API ignora bookingDateFrom/To en algunos casos, así que filtramos
    client-side por r['dateCreated']."""
    api_key = os.environ.get("CLOUDBEDS_API_KEY")
    if not api_key:
        return None
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from cloudbeds_api import _get_all_pages, _fetch_reservation_full
        import time as _time
        # Fetch amplio y filtramos en Python
        params = {
            "bookingDateFrom": monday.isoformat(),
            "bookingDateTo":   friday.isoformat(),
            "status":          "checked_in,checked_out,not_confirmed,confirmed",
            "includeGuestsDetails": "true",
        }
        all_res = _get_all_pages("getReservations", params, api_key)
        filtered = []
        for r in all_res:
            dc = r.get("dateCreated") or r.get("bookingDate")
            if not dc:
                continue
            try:
                d = datetime.strptime(str(dc)[:10], "%Y-%m-%d").date()
            except ValueError:
                continue
            if monday <= d <= friday:
                filtered.append(r)
        # Enriquecer cada uno con `total` (grandTotal) via singular endpoint
        # para mostrar el monto FULL de la reserva, no solo balance.
        for r in filtered:
            rid = r.get("reservationID")
            if not rid:
                continue
            full = _fetch_reservation_full(api_key, rid)
            if full and full.get("total") is not None:
                r["grandTotal"] = full["total"]
            _time.sleep(0.25)
        return filtered
    except Exception as e:
        print(f"   ⚠ no se pudo fetchear nuevos bookings: {e}", file=sys.stderr)
        return None


# ── Render HTML ───────────────────────────────────────────────────────
def render_section_new_bookings(reservations):
    if not reservations:
        return ""
    # Ordenar por grandTotal (monto completo de la reserva) descendente
    def total(r):
        try:
            return float(r.get("grandTotal") or r.get("balance") or 0)
        except (TypeError, ValueError):
            return 0
    top = sorted(reservations, key=total, reverse=True)[:3]
    grand = sum(total(r) for r in reservations)
    rows = ""
    for r in top:
        name = r.get("guestName") or "—"
        start = r.get("startDate") or ""
        amount = total(r)
        rows += f'''
              <tr>
                <td style="padding:8px 0;font-size:12px;color:#5a5040">{name} · {start}</td>
                <td style="padding:8px 0;font-size:12px;color:#1e2820;text-align:right;font-weight:600">${fmt_money(amount)}</td>
              </tr>'''
    extra = ""
    if len(reservations) > 3:
        extra = f'''
              <tr>
                <td style="padding:8px 0;font-size:12px;color:#888;font-style:italic" colspan="2">+ {len(reservations) - 3} más</td>
              </tr>'''
    return f'''
        <tr>
          <td style="padding:24px 32px 8px">
            <h2 style="font-size:11px;color:#9a6e28;letter-spacing:.14em;text-transform:uppercase;margin:0 0 12px;font-weight:600">Nuevos bookings · {len(reservations)} reservas / ${fmt_money(grand)}</h2>
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="border-collapse:collapse">{rows}{extra}
            </table>
          </td>
        </tr>'''


def render_section_refunds(refunds):
    if not refunds:
        return ""
    rows = ""
    total = 0
    for r in refunds:
        total += r["delta"]
        rows += f'''
              <div style="font-size:12px;color:#5a5040;margin-top:4px">Trip {r["start"]} · {r["name"]} · <span style="color:#8a3020;font-weight:600">${fmt_money(r["delta"])}</span></div>'''
    return f'''
        <tr>
          <td style="padding:8px 32px">
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:rgba(138,48,32,.05);border-left:3px solid #8a3020;border-radius:4px">
              <tr>
                <td style="padding:14px 16px">
                  <h2 style="font-size:11px;color:#8a3020;letter-spacing:.14em;text-transform:uppercase;margin:0 0 4px;font-weight:600">⚠ Refunds detectados · ${fmt_money(total)}</h2>{rows}
                </td>
              </tr>
            </table>
          </td>
        </tr>'''


def render_section_risk(risky):
    if not risky:
        return ""
    rows = ""
    for r in risky[:5]:  # máximo 5 para no saturar
        rows += f'''
              <tr>
                <td style="padding:10px 12px;font-size:12px;color:#1e2820;border-bottom:1px solid #f0ede6">{r["name"]} {r["start"][5:]}–{r["end"][5:]}</td>
                <td style="padding:10px 12px;font-size:12px;color:#8a3020;font-weight:600;text-align:center;border-bottom:1px solid #f0ede6">{r["guests"]}</td>
                <td style="padding:10px 12px;font-size:11px;color:#7a6e58;text-align:right;border-bottom:1px solid #f0ede6">en {r["days_to"]} días</td>
              </tr>'''
    extra = ""
    if len(risky) > 5:
        extra = f'<div style="font-size:11px;color:#7a6e58;margin-top:8px;text-align:right">+ {len(risky)-5} viajes más en riesgo</div>'
    return f'''
        <tr>
          <td style="padding:24px 32px 8px">
            <h2 style="font-size:11px;color:#8a6020;letter-spacing:.14em;text-transform:uppercase;margin:0 0 12px;font-weight:600">⚠ Trips en riesgo · Próximos 60 días</h2>
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="border-collapse:collapse;background:#fefdf8;border-radius:4px">
              <tr style="background:#f0ede6">
                <td style="padding:8px 12px;font-size:10px;color:#7a6e58;text-transform:uppercase;letter-spacing:.08em;font-weight:600">Viaje</td>
                <td style="padding:8px 12px;font-size:10px;color:#7a6e58;text-transform:uppercase;letter-spacing:.08em;font-weight:600;text-align:center">Huéspedes</td>
                <td style="padding:8px 12px;font-size:10px;color:#7a6e58;text-transform:uppercase;letter-spacing:.08em;font-weight:600;text-align:right">Check-in</td>
              </tr>{rows}
            </table>{extra}
          </td>
        </tr>'''


# ── Main ──────────────────────────────────────────────────────────────
def build_report(data, prev_data, today=None):
    today = today or datetime.now(MX_TZ).date()
    monday = today - timedelta(days=today.weekday())
    friday = monday + timedelta(days=4)
    prev_monday = monday - timedelta(days=7)
    prev_friday = friday - timedelta(days=7)

    # Ventas actuales y previas — ambas calculadas desde el data file ACTUAL
    # (el snapshot de hace 7 días tiene data incompleta del periodo anterior).
    # El snapshot prev_data solo se usa para detectar refunds.
    bm, lv, yuc = sales_in_range(data, monday, friday)
    sales_now = bm + lv + yuc
    p_bm, p_lv, p_yuc = sales_in_range(data, prev_monday, prev_friday)
    sales_prev = p_bm + p_lv + p_yuc

    delta_pct = ((sales_now - sales_prev) / sales_prev * 100) if sales_prev > 0 else 0
    delta_arrow = "▲" if delta_pct >= 0 else "▼"
    delta_color = "#2a7a48" if delta_pct >= 0 else "#8a3020"

    pend_total, pend_count = pipeline_pendiente(data)
    revenue, target, meta_pct = meta_progress(data)

    refunds  = detect_refunds(data, prev_data)
    risky    = trips_at_risk(data, days_ahead=60)
    new_bks  = fetch_new_bookings_this_week(monday, friday)

    # Forecast anual: revenue actual contratado + extrapolación del ritmo
    # de nuevas ventas YTD. Es directional (la estacionalidad lo afecta).
    year_start = date(today.year, 1, 1)
    year_end   = date(today.year, 12, 31)
    days_elapsed = max(1, (today - year_start).days + 1)
    days_remaining_year = (year_end - today).days

    # Pace YTD: sumar todo lo que cayó como pago en este año calendario
    ytd_paid = 0
    for k, v in data["bahia_mag"].get("daily", {}).items():
        try:
            d = parse_date(k)
            if d.year == today.year and d <= today:
                ytd_paid += v
        except (KeyError, ValueError):
            continue
    for t in data.get("la_ventana", {}).get("trips", []):
        for p in t.get("payments", []):
            try:
                d = parse_date(p.get("date", ""))
                if d.year == today.year and d <= today:
                    ytd_paid += p.get("amount", 0) or 0
            except (KeyError, ValueError):
                continue
    for t in data.get("yucatan", {}).get("trips", []):
        for p in t.get("payments", []):
            try:
                d = parse_date(p.get("date", ""))
                if d.year == today.year and d <= today:
                    ytd_paid += p.get("amount", 0) or 0
            except (KeyError, ValueError):
                continue

    pace_per_day = ytd_paid / days_elapsed
    forecast = revenue + pace_per_day * days_remaining_year
    proj_pct = (forecast / target * 100) if target else 0
    proj_gap = max(0, target - forecast)
    proj_label = f"A este ritmo: <strong style=\"color:#c8a05a\">${fmt_money(forecast)}</strong> estimado al cierre del año"
    proj_sub   = f"{proj_pct:.1f}% de meta anual · ${fmt_money(revenue)} ya contratado · faltan ${fmt_money(proj_gap)} para ${fmt_money(target)}"

    return {
        "WEEK_NUM": iso_week_num(today),
        "WEEK_RANGE": f"{monday.day} al {friday.day} de {monday.strftime('%B').lower()}, {monday.year}".replace(
            "january","enero").replace("february","febrero").replace("march","marzo").replace(
            "april","abril").replace("may","mayo").replace("june","junio").replace(
            "july","julio").replace("august","agosto").replace("september","septiembre").replace(
            "october","octubre").replace("november","noviembre").replace("december","diciembre"),
        "PREV_WEEK_NUM": iso_week_num(prev_monday),
        "SALES_NET": fmt_money(sales_now),
        "DELTA_PCT": f"{abs(delta_pct):.1f}%",
        "DELTA_ARROW": delta_arrow,
        "DELTA_COLOR": delta_color,
        "PIPELINE_PEND": fmt_money(pend_total),
        "PIPELINE_COUNT": pend_count,
        "META_PCT": f"{meta_pct:.1f}",
        "META_REVENUE": fmt_money(revenue),
        "META_TARGET": fmt_money(target),
        "BM_SALES": fmt_money(bm),
        "LV_SALES": fmt_money(lv),
        "YUC_SALES": fmt_money(yuc),
        "PROJECTION_LABEL": proj_label,
        "PROJECTION_SUB":   proj_sub,
        "NEW_BOOKINGS_SECTION": render_section_new_bookings(new_bks or []),
        "REFUNDS_SECTION": render_section_refunds(refunds),
        "RISK_SECTION": render_section_risk(risky),
        "_subject": f"📊 Reporte semanal Akampa · Semana {iso_week_num(today)} ({monday.day}-{friday.day} {monday.strftime('%b').lower()})",
    }


def render_html(report):
    template = TEMPLATE_PATH.read_text()
    # Reemplazo manual de placeholders (no usar .format porque hay {} en el HTML CSS)
    html = template
    for k, v in report.items():
        if k.startswith("_"):
            continue
        html = html.replace("{" + k + "}", str(v))
    return html


def send_email(subject, html, dry_run=False):
    api_key = os.environ.get("RESEND_API_KEY")
    sender  = os.environ.get("DIGEST_FROM", "onboarding@resend.dev")
    to_raw  = os.environ.get("DIGEST_TO", "daniel@akampa.mx")
    recipients = [e.strip() for e in to_raw.split(",") if e.strip()]
    # Debug: confirma qué valores leyó el workflow
    print(f"   📨 from: {sender}")
    print(f"   📨 to:   {recipients}")
    print(f"   🔑 api_key: {'set ('+api_key[:6]+'...)' if api_key else 'MISSING'}")

    if dry_run:
        print(f"--- DRY RUN ---")
        print(f"From: {sender}")
        print(f"To: {recipients}")
        print(f"Subject: {subject}")
        out = Path("/tmp/digest-rendered.html")
        out.write_text(html)
        print(f"HTML guardado: {out}")
        return

    if not api_key:
        raise SystemExit("❌ RESEND_API_KEY no configurada — no se puede enviar.")

    payload = json.dumps({
        "from": sender,
        "to": recipients,
        "subject": subject,
        "html": html,
    }).encode()

    req = urllib.request.Request(
        "https://api.resend.com/emails",
        method="POST",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type":  "application/json",
            # Cloudflare (delante de Resend) bloquea User-Agent "Python-urllib"
            "User-Agent":    "akampa-weekly-digest/1.0",
            "Accept":        "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
            print(f"✅ Email enviado · id: {result.get('id')}")
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        print(f"❌ Resend HTTP {e.code}")
        print(f"   Response headers: {dict(e.headers)}")
        print(f"   Response body (raw): {body!r}")
        raise SystemExit(1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="Imprime HTML y guarda en /tmp/digest-rendered.html sin enviar")
    ap.add_argument("--data", default=str(DATA_PATH))
    args = ap.parse_args()

    print(f"📊 Generando digest semanal...")
    data = load_data(args.data)

    # Snapshot de hace ~7 días para deltas / refunds
    week_ago = date.today() - timedelta(days=7)
    commit = find_commit_before(week_ago)
    prev_data = load_data_at_commit(commit) if commit else None
    if prev_data:
        print(f"   ✓ Snapshot de {week_ago.isoformat()}: commit {commit[:8]}")
    else:
        print(f"   ⚠ No se encontró snapshot anterior — deltas y refunds vacíos")

    report = build_report(data, prev_data)
    html   = render_html(report)
    send_email(report["_subject"], html, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
