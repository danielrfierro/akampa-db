#!/usr/bin/env python3
from __future__ import annotations
"""
cloudbeds_api.py
──────────────────────────────────────────────────────────────────────────────
Reemplaza parse_cloudbeds() usando la API v1.2 de Cloudbeds directamente.
Produce exactamente los mismos datos que el parser de XLSX para que
akampa_processor_v3.py funcione sin cambios.

Salidas (mismas que parse_cloudbeds()):
  bal             → {date: {cobrado, pend, total}}  por check-in date
  ci_data         → {date: {guests, rooms}}          por check-in date
  monthly_new     → {season: {mes_abr: {m,g,occ,rpg,rev}}}
  booking_weekly  → {YYYY-Www: monto_pagado}
  booking_weekly_pend → {YYYY-Www: monto_pendiente}
  booking_daily   → {YYYY-MM-DD: monto_pagado}

Uso directo:
  python3 scripts/cloudbeds_api.py --api_key cbat_TU_CLAVE [--desde 2026-01-01] [--hasta 2027-12-31]

Uso como módulo (desde akampa_processor_v3.py):
  from cloudbeds_api import fetch_cloudbeds_api
  bal, ci_data, monthly_new, bk_wk, bk_pend, bk_daily = fetch_cloudbeds_api(api_key)
"""

import argparse
import json
import sys
import time
from collections import defaultdict
from datetime import datetime, date as ddate
from zoneinfo import ZoneInfo

try:
    import urllib.request
    import urllib.error
except ImportError:
    sys.exit("ERROR: urllib no disponible")

# ── Constantes ────────────────────────────────────────────────────────────────
BASE_URL   = "https://hotels.cloudbeds.com/api/v1.2"
PAGE_SIZE  = 100       # máximo permitido por Cloudbeds
RATE_LIMIT = 0.25      # segundos entre requests (evita 429)
MX_TZ      = ZoneInfo("America/Mexico_City")
MES_ABREV  = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"]


# ── HTTP helper ───────────────────────────────────────────────────────────────
def _get(endpoint: str, params: dict, api_key: str) -> dict:
    """GET a Cloudbeds API endpoint, retorna JSON parseado."""
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"{BASE_URL}/{endpoint}?{qs}"
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {api_key}")
    req.add_header("Accept", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code} en {endpoint}: {body[:300]}")


def _get_all_pages(endpoint: str, base_params: dict, api_key: str,
                   data_key: str = "data") -> list:
    """Pagina automáticamente hasta obtener todos los resultados."""
    results = []
    page = 1
    while True:
        params = {**base_params, "pageNumber": page, "pageSize": PAGE_SIZE}
        resp = _get(endpoint, params, api_key)
        if not resp.get("success"):
            print(f"   ⚠ API warning en {endpoint} p.{page}: {resp.get('message','')}")
            break
        chunk = resp.get(data_key, [])
        if isinstance(chunk, dict):
            # Algunos endpoints devuelven dict en lugar de list
            chunk = list(chunk.values())
        results.extend(chunk)
        total   = int(resp.get("total", resp.get("count", len(chunk))))
        fetched = page * PAGE_SIZE
        print(f"   → {endpoint} p.{page}: {len(chunk)} items (total {total})")
        if fetched >= total or len(chunk) < PAGE_SIZE:
            break
        page += 1
        time.sleep(RATE_LIMIT)
    return results


# ── Helpers de fecha ──────────────────────────────────────────────────────────
def _parse_date(v) -> ddate | None:
    if not v:
        return None
    try:
        return datetime.strptime(str(v)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _iso_week(d: ddate) -> str:
    iso = d.isocalendar()
    return f"{iso[0]}-W{str(iso[1]).zfill(2)}"


def _season(yr: int, mo: int) -> str:
    """Infiere la temporada Akampa a partir de año/mes."""
    # Oct-Dic → primer año de temporada; Ene-Sep → segundo año
    if mo >= 10:
        return f"{yr}-{yr+1}"
    else:
        return f"{yr-1}-{yr}"


# ── Fetch reservations ────────────────────────────────────────────────────────
def _fetch_reservations(api_key: str, desde: str, hasta: str) -> list:
    """
    Trae todas las reservaciones cuyo check-in esté entre desde y hasta.
    Excluye canceladas en el filtro para reducir volumen.
    """
    print(f"📡 Fetching reservations {desde} → {hasta}...")
    # Cloudbeds acepta status como parámetro para pre-filtrar
    params = {
        "checkInFrom":  desde,
        "checkInTo":    hasta,
        "includeGuestsDetails": "true",   # trae adultos/niños por habitación
        "status":       "checked_in,checked_out,not_confirmed,confirmed",
    }
    reservations = _get_all_pages("getReservations", params, api_key)
    print(f"   Total reservaciones: {len(reservations)}")
    return reservations


def _fetch_reservations_by_booking(api_key: str, desde: str, hasta: str) -> list:
    """
    Trae reservaciones por fecha de BOOKING (no check-in).
    Necesario para construir el historial semanal/diario de ventas.
    """
    print(f"📡 Fetching reservations by booking date {desde} → {hasta}...")
    params = {
        "bookingDateFrom": desde,
        "bookingDateTo":   hasta,
        "status":          "checked_in,checked_out,not_confirmed,confirmed",
    }
    return _get_all_pages("getReservations", params, api_key)


# ── Parsers ───────────────────────────────────────────────────────────────────
def _build_bal_and_ci(reservations: list) -> tuple[dict, dict]:
    """
    Construye bal y ci_data agrupados por check-in date.

    bal     = {date: {cobrado, pend, total}}
    ci_data = {date: {guests, rooms}}
    """
    bal     = defaultdict(lambda: {"cobrado": 0.0, "pend": 0.0, "total": 0.0})
    ci_data = defaultdict(lambda: {"guests": 0, "rooms": 0})

    for r in reservations:
        status = str(r.get("status", "")).strip().lower()
        # Excluir canceladas (por si el filtro de API no las eliminó todas)
        if "cancel" in status:
            continue

        ci = _parse_date(r.get("checkIn"))
        if not ci:
            continue

        # Financiero
        try:
            grand  = float(r.get("grandTotal", 0) or 0)
            paid   = float(r.get("paid", 0) or 0)
            balance= float(r.get("balance", r.get("balanceDue", 0)) or 0)
        except (TypeError, ValueError):
            continue

        bal[ci]["total"]   += grand
        bal[ci]["cobrado"] += paid
        bal[ci]["pend"]    += balance

        # Huéspedes y habitaciones
        # Cloudbeds puede devolver adults/children a nivel reserva o por room
        adults   = int(r.get("adults",   0) or 0)
        children = int(r.get("children", 0) or 0)
        guests   = adults + children
        if guests == 0:
            # Intentar sumar desde rooms_details si está disponible
            for room in r.get("rooms", []):
                guests += int(room.get("adults", 0) or 0)
                guests += int(room.get("children", 0) or 0)

        rooms_count = len(r.get("rooms", [])) or int(r.get("roomsBooked", 1) or 1)

        ci_data[ci]["guests"] += guests
        ci_data[ci]["rooms"]  += rooms_count

    # Redondear financiero
    for d in bal:
        bal[d] = {k: round(v, 2) for k, v in bal[d].items()}

    return dict(bal), dict(ci_data)


def _build_booking_weekly(reservations: list) -> tuple[dict, dict, dict]:
    """
    Construye weekly/daily de ventas agrupado por BOOKING DATE.
    Equivalente al tab ReservationsByBookingDate del XLSX.

    Retorna: (weekly_paid, weekly_pend, daily_paid)
    """
    weekly      = defaultdict(float)
    weekly_pend = defaultdict(float)
    daily       = defaultdict(float)

    for r in reservations:
        status = str(r.get("status", "")).strip().lower()
        if "cancel" in status:
            continue

        booking_date = _parse_date(
            r.get("dateCreated") or r.get("bookingDate") or r.get("reservationCreated")
        )
        if not booking_date:
            continue

        try:
            paid    = float(r.get("paid", 0) or 0)
            balance = float(r.get("balance", r.get("balanceDue", 0)) or 0)
            grand   = float(r.get("grandTotal", 0) or 0)
        except (TypeError, ValueError):
            continue

        if grand <= 0 and paid <= 0 and balance <= 0:
            continue

        wk = _iso_week(booking_date)
        ds = str(booking_date)

        if paid > 0:
            weekly[wk] += paid
            daily[ds]  += paid
        if balance > 0:
            weekly_pend[wk] += balance

    return (
        {k: round(v) for k, v in weekly.items()},
        {k: round(v) for k, v in weekly_pend.items()},
        {k: round(v) for k, v in daily.items()},
    )


def _build_monthly(reservations: list) -> dict:
    """
    Construye monthly_new agrupado por mes de check-in.
    Equivalente al tab TotalRevenuePerGuest del XLSX.

    Retorna: {season: {mes_abr: {m, g, occ, rpg, rev}}}
    """
    # Agrupamos por YYYY-MM
    by_month = defaultdict(lambda: {"guests": 0, "revenue": 0.0, "reservations": 0})

    for r in reservations:
        status = str(r.get("status", "")).strip().lower()
        if "cancel" in status:
            continue
        ci = _parse_date(r.get("checkIn"))
        if not ci:
            continue
        ym = f"{ci.year}-{str(ci.month).zfill(2)}"
        try:
            paid = float(r.get("paid", 0) or 0)
        except (TypeError, ValueError):
            paid = 0.0

        adults   = int(r.get("adults", 0) or 0)
        children = int(r.get("children", 0) or 0)
        guests   = adults + children or 1

        by_month[ym]["guests"]       += guests
        by_month[ym]["revenue"]      += paid
        by_month[ym]["reservations"] += 1

    monthly_new = {}
    for ym, data in by_month.items():
        if not data["revenue"] and not data["guests"]:
            continue
        yr, mo = int(ym[:4]), int(ym[5:7])
        season  = _season(yr, mo)
        m_abr   = MES_ABREV[mo - 1]
        rpg     = round(data["revenue"] / data["guests"]) if data["guests"] else 0
        monthly_new.setdefault(season, {})[m_abr] = {
            "m":   m_abr,
            "g":   data["guests"],
            "occ": 0,    # ocupación requiere endpoint separado (ver nota abajo)
            "rpg": rpg,
            "rev": round(data["revenue"]),
        }

    return monthly_new


# ── Entry point principal ─────────────────────────────────────────────────────
def fetch_cloudbeds_api(
    api_key: str,
    desde:   str = "2026-01-01",
    hasta:   str = "2027-12-31",
    desde_booking: str = "2025-01-01",
) -> tuple[dict, dict, dict, dict, dict, dict]:
    """
    Función principal. Retorna (bal, ci_data, monthly_new,
    booking_weekly, booking_weekly_pend, booking_daily)
    en exactamente el mismo formato que parse_cloudbeds().

    Args:
        api_key:        Bearer token de Cloudbeds (cbat_...)
        desde:          Fecha inicio para check-in (YYYY-MM-DD)
        hasta:          Fecha fin para check-in (YYYY-MM-DD)
        desde_booking:  Fecha inicio para booking date (más atrás, captura historial de ventas)
    """
    # 1. Reservaciones por check-in (para bal + ci_data + monthly)
    res_checkin = _fetch_reservations(api_key, desde, hasta)
    bal, ci_data = _build_bal_and_ci(res_checkin)
    monthly_new  = _build_monthly(res_checkin)

    print(f"   Balance Due: {len(bal)} fechas · Check-in: {len(ci_data)} fechas "
          f"· Monthly: {sum(len(v) for v in monthly_new.values())} meses")

    # 2. Reservaciones por booking date (para weekly/daily historial de ventas)
    # Usamos un rango más amplio para capturar todo el historial de bookings
    res_booking = _fetch_reservations_by_booking(api_key, desde_booking, hasta)
    bk_wk, bk_pend, bk_daily = _build_booking_weekly(res_booking)

    print(f"   Booking weekly: {len(bk_wk)} semanas · "
          f"Pend: {len(bk_pend)} · Daily: {len(bk_daily)} días")

    return bal, ci_data, monthly_new, bk_wk, bk_pend, bk_daily


# ── CLI standalone ────────────────────────────────────────────────────────────
def main():
    p = argparse.ArgumentParser(description="Cloudbeds API → datos para Akampa Dashboard")
    p.add_argument("--api_key",       required=True,  help="Bearer token cbat_...")
    p.add_argument("--desde",         default="2026-01-01")
    p.add_argument("--hasta",         default="2027-12-31")
    p.add_argument("--desde_booking", default="2025-01-01")
    p.add_argument("--output",        default=None,   help="Guardar JSON de salida (opcional)")
    args = p.parse_args()

    bal, ci_data, monthly_new, bk_wk, bk_pend, bk_daily = fetch_cloudbeds_api(
        api_key       = args.api_key,
        desde         = args.desde,
        hasta         = args.hasta,
        desde_booking = args.desde_booking,
    )

    result = {
        "bal":             {str(k): v for k, v in bal.items()},
        "ci_data":         {str(k): v for k, v in ci_data.items()},
        "monthly_new":     monthly_new,
        "booking_weekly":  bk_wk,
        "booking_weekly_pend": bk_pend,
        "booking_daily":   bk_daily,
    }

    if args.output:
        from pathlib import Path
        Path(args.output).write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\n✅ Datos guardados en {args.output}")
    else:
        print(f"\n✅ Resumen:")
        print(f"   bal:            {len(bal)} fechas de check-in")
        print(f"   ci_data:        {len(ci_data)} fechas con huéspedes")
        print(f"   monthly_new:    {sum(len(v) for v in monthly_new.values())} meses")
        print(f"   booking_weekly: {len(bk_wk)} semanas")
        print(f"   booking_daily:  {len(bk_daily)} días")


if __name__ == "__main__":
    main()
