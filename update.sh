#!/bin/bash
# ──────────────────────────────────────────────────────────────
# Akampa Dashboard — Actualización (manual o automática via Cowork)
# Uso: bash update.sh
#
# Coloca los archivos en reportes/ antes de correr:
#   reportes/Reporte Sales Inteligence*.xlsx   ← export Cloudbeds (obligatorio)
#   reportes/Reporting_Payments_WeTravel.xlsx  ← export WeTravel combinado
# ──────────────────────────────────────────────────────────────

set -e
cd "$(dirname "$0")"

WT_COMBINED="reportes/Reporting_Payments_WeTravel.xlsx"
WT_LV="reportes/wetravel_la_ventana.xlsx"
WT_YUC="reportes/wetravel_yucatan.xlsx"

# Busca el reporte de Cloudbeds con cualquiera de sus nombres conocidos
CLOUDBEDS=$(ls "reportes/Reporte Sales Inteligence"*.xlsx \
               "reportes/Reporte Sales Intelligence"*.xlsx \
               reportes/cloudbeds.xlsx 2>/dev/null | head -1)

# Descarga automática desde Gmail si no hay archivo local
if [ -z "$CLOUDBEDS" ]; then
  if [ -f "gmail_secrets.json" ] || [ -n "$GMAIL_CLIENT_ID" ]; then
    echo "📬 Descargando reporte de Cloudbeds desde Gmail..."
    python3 scripts/akampa_gmail_downloader.py
    CLOUDBEDS=$(ls "reportes/Reporte Sales Inteligence"*.xlsx \
                   "reportes/Reporte Sales Intelligence"*.xlsx \
                   reportes/cloudbeds.xlsx 2>/dev/null | head -1)
  fi
fi

# Verificar que existe el archivo de Cloudbeds
if [ -z "$CLOUDBEDS" ] || [ ! -f "$CLOUDBEDS" ]; then
  echo "❌ No encontré el reporte de Cloudbeds en reportes/"
  echo "   Descárgalo y ponlo en reportes/ (puede tener cualquier nombre)"
  exit 1
fi

echo "✓ Cloudbeds: $CLOUDBEDS"

# Construir argumentos como array (maneja espacios en nombres de archivo)
ARGS=(
  "--reporte"  "$CLOUDBEDS"
  "--existing" "akampa-data-v3.js"
  "--output"   "akampa-data-v3.js"
  "--html"     "index.html"
)

# WeTravel: combinado primero, luego archivos separados como fallback
if [ -f "$WT_COMBINED" ]; then
  echo "✓ WeTravel combinado: $WT_COMBINED"
  ARGS+=(
    "--wetravel_lv"         "$WT_COMBINED"
    "--wetravel_lv_keyword" "La Ventana"
    "--wetravel_yuc"        "$WT_COMBINED"
    "--wetravel_yuc_keyword" "Yucatan"
  )
else
  [ -f "$WT_LV"  ] && echo "✓ WeTravel La Ventana"  && ARGS+=("--wetravel_lv"  "$WT_LV")
  [ -f "$WT_YUC" ] && echo "✓ WeTravel Yucatán"     && ARGS+=("--wetravel_yuc" "$WT_YUC")
fi

# Procesar datos
echo ""
echo "⚙️  Procesando datos..."
python3 scripts/akampa_processor_v3.py "${ARGS[@]}"

# Publicar en GitHub → GitHub Actions despliega → sales.akampa.mx
echo ""
echo "🚀 Publicando en GitHub..."
git add akampa-data-v3.js akampa-data-v3.json index.html
git diff --staged --quiet && echo "ℹ️  Sin cambios nuevos." || \
  (git commit -m "🔄 Auto-update $(date +%Y-%m-%d)" && git push)

echo ""
echo "✅ Listo → https://sales.akampa.mx"
