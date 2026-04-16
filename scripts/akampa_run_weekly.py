#!/usr/bin/env python3
"""
akampa_run_weekly.py
──────────────────────────────────────────────────────────────────────
Orquestador principal. Se ejecuta cada lunes a las 8:30am via LaunchAgent.

La descarga del XLSX la hace Cowork (vía Gmail MCP + Chrome) a las 8:00am,
guardando el archivo en ~/Documents/Cowork/Akampa/reportes/.

Flujo:
  1. Localiza el XLSX más reciente en reportes/
  2. Procesa con akampa_processor_v3.py y sube a Netlify
  3. Archiva el reporte procesado

Uso:
  python3 ~/Documents/Cowork/Akampa/akampa_run_weekly.py
  python3 ~/Documents/Cowork/Akampa/akampa_run_weekly.py --reporte /ruta/al/archivo.xlsx
"""

import argparse, json, subprocess, sys, shutil, glob
from pathlib import Path
from datetime import datetime

BASE     = Path.home() / 'Documents' / 'Cowork' / 'Akampa'
LOG_FILE = BASE / 'logs' / 'update.log'

def log(msg):
    ts   = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    line = f"[{ts}] {msg}"
    print(line)
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, 'a') as f:
        f.write(line + '\n')

def load_config():
    return json.loads((BASE / 'akampa_config.json').read_text())

def find_latest_report(download_dir):
    """Busca el XLSX más reciente en reportes/ (depositado por Cowork)."""
    patterns = [
        str(download_dir / 'Reporte_Sales_Inteligence*.xlsx'),
        str(download_dir / 'Reporte_Sales_Intelligence*.xlsx'),
        str(download_dir / 'Reporte*.xlsx'),
        str(download_dir / 'Sales_Intelligence*.xlsx'),
    ]
    found = []
    for pat in patterns:
        found.extend(glob.glob(pat))
    if not found:
        return None
    return max(found, key=lambda f: Path(f).stat().st_mtime)

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--reporte',      default=None,
                   help='Ruta directa al XLSX (opcional; si no se pasa, busca en reportes/)')
    p.add_argument('--wetravel_lv',  default=None)
    p.add_argument('--wetravel_yuc', default=None)
    args = p.parse_args()

    log("=" * 60)
    log("🚀 Akampa Dashboard — Actualización semanal")
    log("=" * 60)

    config = load_config()
    paths  = config['paths']
    nl_cfg = config['netlify']
    dl_dir = Path(paths['download_dir']).expanduser()
    data_js = BASE / 'akampa-data-v3.js'

    # ── PASO 1: Localizar reporte (depositado por Cowork a las 8am) ───
    log("\n📋 PASO 1 — Localizando reporte de Cloudbeds...")
    reporte = args.reporte or find_latest_report(dl_dir)

    if not reporte or not Path(reporte).exists():
        log("❌ No se encontró el reporte de Cloudbeds.")
        log(f"   Carpeta esperada: {dl_dir}")
        log("   Verifica que Cowork descargó el XLSX esta semana,")
        log("   o pasa la ruta manualmente con --reporte /ruta/archivo.xlsx")
        sys.exit(1)

    log(f"   ✓ Reporte: {Path(reporte).name}")
    log(f"   ✓ Tamaño:  {Path(reporte).stat().st_size // 1024} KB")

    # ── PASO 2: WeTravel (opcional) ───────────────────────────────────
    wt_lv = args.wetravel_lv
    if not wt_lv:
        wt_path = Path(paths['wetravel_lv']).expanduser()
        wt_lv = str(wt_path) if wt_path.exists() else None

    log(f"\n   WeTravel La Ventana: {'✓ ' + Path(wt_lv).name if wt_lv else 'no encontrado — se conservan datos anteriores'}")

    # ── PASO 3: Procesar y subir a Netlify ────────────────────────────
    log("\n⚙  PASO 2 — Procesando datos y desplegando en Netlify...")
    cmd = [
        sys.executable, str(BASE / 'akampa_processor_v3.py'),
        '--reporte',       reporte,
        '--existing',      str(data_js),
        '--output',        str(data_js),
        '--netlify_site',  nl_cfg['site_id'],
        '--netlify_token', nl_cfg['token'],
    ]
    if wt_lv:             cmd += ['--wetravel_lv',  wt_lv]
    if args.wetravel_yuc: cmd += ['--wetravel_yuc', args.wetravel_yuc]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if result.stdout:
        log(result.stdout.strip())
    if result.returncode != 0:
        log(f"❌ Error en el procesador:\n{result.stderr[:600]}")
        sys.exit(1)

    # ── PASO 4: Archivar reporte procesado ────────────────────────────
    log("\n📦 PASO 3 — Archivando reporte...")
    archive = dl_dir / datetime.now().strftime('%Y-%m-%d')
    archive.mkdir(parents=True, exist_ok=True)
    shutil.move(reporte, str(archive / Path(reporte).name))
    log(f"   → reportes/{archive.name}/{Path(reporte).name}")

    log("\n✅ Netlify actualizado")
    log(f"   Dashboard: https://akampa-sales.netlify.app")
    log("=" * 60)

if __name__ == '__main__':
    main()
