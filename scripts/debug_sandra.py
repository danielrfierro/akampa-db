#!/usr/bin/env python3
"""
Diagnóstico: busca la reserva de Sandra Michelsen en Cloudbeds.

Uso:
  python3 scripts/debug_sandra.py --api_key cbat_TU_CLAVE
"""
import argparse, json, sys, urllib.request

BASE_URL = "https://hotels.cloudbeds.com/api/v1.2"

def get_all(endpoint, params, key):
    out, page = [], 1
    while True:
        qs = "&".join(f"{k}={v}" for k, v in {**params, "pageNumber": page, "pageSize": 100}.items())
        req = urllib.request.Request(f"{BASE_URL}/{endpoint}?{qs}")
        req.add_header("Authorization", f"Bearer {key}")
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read())
        chunk = data.get("data", [])
        if isinstance(chunk, dict): chunk = list(chunk.values())
        out.extend(chunk)
        if len(chunk) < 100: break
        page += 1
    return out

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--api_key", required=True)
    a = p.parse_args()

    common = {"includeGuestsDetails": "true"}

    print("\n🔎 1) check-in 2026-11-05 (con includeGuestsDetails)...")
    r1 = get_all("getReservations", {**common, "checkInFrom": "2026-11-05", "checkInTo": "2026-11-05"}, a.api_key)
    print(f"   → {len(r1)} reservas ese día\n")

    print("🔎 2) booking date 2026-05-11 (con includeGuestsDetails)...")
    r2 = get_all("getReservations", {**common, "bookingDateFrom": "2026-05-11", "bookingDateTo": "2026-05-11"}, a.api_key)
    print(f"   → {len(r2)} reservas creadas ese día\n")

    print("🔎 3) Mismos params que producción (status filter)...")
    r3 = get_all("getReservations", {**common,
        "checkInFrom": "2026-11-05", "checkInTo": "2026-11-05",
        "status": "checked_in,checked_out,not_confirmed,confirmed"
    }, a.api_key)
    print(f"   → {len(r3)} reservas\n")

    # Buscar Sandra en todas las listas combinadas
    todas = {r.get("reservationID") or id(r): r for r in r1 + r2 + r3}
    print(f"📋 {len(todas)} reservas únicas combinadas\n")

    print("─── Reservas que mencionan 'Michelsen' o 'Sandra' (JSON completo) ───")
    found = False
    for r in todas.values():
        blob = json.dumps(r, default=str).lower()
        if "michelsen" in blob or "sandra" in blob:
            found = True
            print(f"\n📌 ID: {r.get('reservationID')} · status: {r.get('status')} · dateCreated: {r.get('dateCreated')}")
            print(f"   TODAS las keys: {sorted(r.keys())}")
            print(f"   JSON completo:")
            print(json.dumps(r, indent=2, default=str, ensure_ascii=False))
    if not found:
        print("\n   ❌ NO encontrada en ninguna de las 3 consultas.")
        print("   Posibles causas:")
        print("     • La reserva no existe (¿de verdad se creó?)")
        print("     • Está en otra propiedad de Cloudbeds")
        print("     • Tiene un status raro que ni siquiera responde a queries por fecha")
        print("\n   Verifica directo en la UI de Cloudbeds que la reserva existe y mira su estatus.")

if __name__ == "__main__":
    main()
