# Akampa Sales Intelligence Dashboard

**URL:** https://akampa-sales.netlify.app  
**Versión:** v3  
**Última actualización:** 2026-04-14

Dashboard interno de inteligencia comercial para el equipo de ventas y operaciones de Akampa. Consolida datos de tres destinos en tiempo real: Bahía Magdalena (Cloudbeds), La Ventana y Yucatán (WeTravel).

---

## Destinos cubiertos

| Destino | Fuente de datos | Temporada activa |
|---|---|---|
| Bahía Magdalena Ocean Camp | Cloudbeds (4 pestañas) | Ene–Abr 2026 · Oct 2026–Abr 2027 |
| La Ventana | WeTravel (export XLSX) | Activo |
| Yucatán | WeTravel (export XLSX) | Activo |

---

## Arquitectura del sistema

```
Reportes XLSX (Cloudbeds + WeTravel)
        ↓
akampa_processor_v3.py
   → Lee las 4 pestañas de Cloudbeds: ReservationBalanceDue,
     CheckinReview, TotalRevenuePerGuest, OccupancyStatistics
   → Lee exports de WeTravel: La Ventana + Yucatán
   → Acumula histórico (datos anteriores se preservan)
   → Genera akampa-data-v3.js
        ↓
Netlify API (deploy automático)
        ↓
https://akampa-sales.netlify.app ✅
```

---

## Estructura de archivos

```
~/Documents/Cowork/Akampa/
  ├── akampa_config.json          ← Credenciales Netlify, rutas, config Gmail
  ├── akampa_processor_v3.py      ← Procesa XLSXs → genera akampa-data-v3.js
  ├── akampa_run_weekly.py        ← Orquestador principal
  ├── akampa_launch.sh            ← Wrapper para LaunchAgent de macOS
  ├── akampa_gmail_downloader.py  ← Descarga reportes desde Gmail (Cloudbeds)
  ├── akampa-dashboard-v3.html    ← Dashboard (= index.html en Netlify)
  ├── akampa-data-v3.js           ← Datos actuales (se sobreescribe cada ciclo)
  ├── gmail_credentials.json      ← OAuth2 credentials de Google Cloud
  ├── gmail_token.json            ← Token de sesión (se genera automáticamente)
  ├── reportes/                   ← XLSX entrantes (Cowork los deposita aquí)
  │   ├── YYYY-MM-DD/             ← Archivos procesados (archivados por fecha)
  │   ├── wetravel_la_ventana.xlsx
  │   └── wetravel_yucatan.xlsx
  └── logs/
      ├── update.log
      └── launchd_stdout.log
```

---

## Flujo de actualización (estado actual)

### Automático — Cloudbeds (lunes)
```
Cowork (8:00am) → Gmail → descarga XLSX → ~/Downloads/
LaunchAgent (8:30am) → akampa_run_weekly.py → procesa → sube a Netlify
```

> **Nota:** Cowork descarga el archivo pero no puede ejecutar Python directamente.
> El LaunchAgent de macOS toma el relevo 30 minutos después.

### Manual — WeTravel (cada semana)
1. Entra a WeTravel → Reports → Payments → Export XLSX
2. Guarda como `~/Documents/Cowork/Akampa/reportes/wetravel_la_ventana.xlsx`
3. Repite para Yucatán: `wetravel_yucatan.xlsx`
4. El LaunchAgent los detecta automáticamente el lunes

### Manual forzado (cualquier día)
```bash
python3 ~/Documents/Cowork/Akampa/akampa_run_weekly.py
# o con ruta explícita al reporte:
python3 ~/Documents/Cowork/Akampa/akampa_run_weekly.py --reporte ~/Downloads/'Reporte Sales Inteligence.xlsx'
```

---

## Configuración (akampa_config.json)

```json
{
  "netlify": {
    "site_id": "3b2b6c23-26fe-47c6-8b02-ab958afe5c58",
    "token": "nfp_...",
    "data_file": "akampa-data-v3.json"
  },
  "gmail": {
    "cloudbeds_sender": "noreply@cloudbeds.com",
    "report_names": {
      "occupancy": "Occupancy_Statistics",
      "revenue": "Total_Revenue_Per_Guest",
      "balance": "Reservation_Balance_Due_Details",
      "checkin": "Check-in_Review"
    }
  },
  "paths": {
    "download_dir": "~/Documents/Cowork/Akampa/reportes",
    "wetravel_lv": "~/Documents/Cowork/Akampa/reportes/wetravel_la_ventana.xlsx",
    "wetravel_yuc": "~/Documents/Cowork/Akampa/reportes/wetravel_yucatan.xlsx"
  }
}
```

---

## Dependencias Python

```bash
pip install openpyxl requests google-auth google-auth-oauthlib google-api-python-client
```

---

## LaunchAgent macOS (com_akampa_weeklysales.plist)

Ejecuta `akampa_launch.sh` cada lunes a las 8:30am.

**Instalación (una sola vez):**
```bash
cp com_akampa_weeklysales.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com_akampa_weeklysales.plist
```

**Verificar que está activo:**
```bash
launchctl list | grep akampa
```

---

## Autenticación Gmail (una sola vez)

```bash
cd ~/Documents/Cowork/Akampa
python3 akampa_gmail_downloader.py --debug
# Se abre un browser → autoriza con tu cuenta de Google → listo
```

El token se guarda en `gmail_token.json` y se renueva automáticamente.

---

## Troubleshooting

| Error | Solución |
|---|---|
| `No se encontró el reporte de Cloudbeds` | Verifica que el XLSX esté en `~/Downloads/` o en `reportes/` y pásalo con `--reporte` |
| `HTTP 401 Netlify` | Genera nuevo token en Netlify → User Settings → Access tokens → actualiza `akampa_config.json` |
| `No module named openpyxl` | `pip install openpyxl` |
| WeTravel no se actualiza | Descarga el XLSX manualmente y guárdalo como `wetravel_la_ventana.xlsx` / `wetravel_yucatan.xlsx` en `reportes/` |
| `No se encontraron links de descarga` | Ejecuta `akampa_gmail_downloader.py --debug` para ver el body del correo |

---

## Roadmap

- [x] Dashboard Bahía Magdalena con Cloudbeds
- [x] Integración WeTravel La Ventana
- [x] Vista consolidada 3 destinos
- [x] Deploy automático a Netlify
- [x] LaunchAgent macOS (lunes 8:30am)
- [ ] Automatización completa WeTravel (sin descarga manual)
- [ ] Separación cobrado vs pendiente en WeTravel (requiere columna Balance Due)
- [ ] Notificación por correo si el update falla
- [ ] Escalar a otros campamentos Akampa

---

## Netlify

- **Site ID:** `3b2b6c23-26fe-47c6-8b02-ab958afe5c58`
- **Dashboard:** https://akampa-sales.netlify.app
- **Archivos en producción:** `index.html` + `akampa-data-v3.js`
