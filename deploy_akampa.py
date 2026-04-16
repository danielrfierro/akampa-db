#!/usr/bin/env python3
"""
deploy_akampa.py  —  Deploy ZIP a Netlify
  python3 deploy_akampa.py
"""
import urllib.request, urllib.error, json, sys, io, zipfile
from pathlib import Path

SITE_ID = "3b2b6c23-26fe-47c6-8b02-ab958afe5c58"
TOKEN   = "nfp_BL4G5bc5HFzLj3vBHCFTwH3xHUvCvSGA892c"
BASE    = "https://api.netlify.com/api/v1"

NETLIFY_TOML = b"""
[[headers]]
  for = "/*"
  [headers.values]
    Content-Type = "text/html; charset=UTF-8"
"""

def find_file(name):
    candidates = [
        Path.cwd() / name,
        Path(__file__).parent / name,
        Path.home() / "Documents" / "Cowork" / "Akampa" / name,
        Path.home() / "Documents" / "Cowork" / "Akampa Sales Intelligence Dashboard" / name,
        Path.home() / "Documents" / "Cowork" / "akampa" / name,
    ]
    for p in candidates:
        if p.exists():
            size = p.stat().st_size
            print(f"   {p}  ({size:,} bytes)")
            return p, size
    return None, 0

print("🔍 Buscando akampa-dashboard-v3.html...")
html_path, html_size = find_file("akampa-dashboard-v3.html")

if not html_path:
    sys.exit("❌ No encontré el HTML.\nCopia akampa-dashboard-v3.html a esta misma carpeta.")

# Advertir si es la versión vieja (tiene la línea del data JS externo)
html_bytes = html_path.read_bytes()
if b'akampa-data-v3.js' in html_bytes:
    print("⚠️  ADVERTENCIA: Este HTML depende de akampa-data-v3.js (versión vieja).")
    print("   Busca la versión nueva (74,000-75,000 bytes sin esa línea) y cópiala aquí.")
    resp = input("   ¿Continuar de todas formas? (s/N): ").strip().lower()
    if resp != 's':
        sys.exit("Deploy cancelado.")

# Construir ZIP con index.html + netlify.toml
buf = io.BytesIO()
with zipfile.ZipFile(buf, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
    zf.writestr("index.html",    html_bytes)
    zf.writestr("netlify.toml",  NETLIFY_TOML)
zip_bytes = buf.getvalue()
print(f"\n📦 ZIP: {len(zip_bytes):,} bytes  (index.html + netlify.toml)")

# POST ZIP a Netlify
print("🚀 Subiendo a Netlify...")
url = f"{BASE}/sites/{SITE_ID}/deploys"
r   = urllib.request.Request(url, data=zip_bytes, method="POST")
r.add_header("Authorization", f"Bearer {TOKEN}")
r.add_header("Content-Type",  "application/zip")

try:
    with urllib.request.urlopen(r, timeout=120) as resp:
        result = json.loads(resp.read())
        deploy_id = result.get("id", "?")[:12]
        state     = result.get("state", "?")
        ssl_url   = result.get("ssl_url") or result.get("url", "")
        print(f"   ✓ Deploy ID: {deploy_id}...  estado: {state}")
        print(f"\n✅ Listo!  https://akampa-sales.netlify.app")
except urllib.error.HTTPError as e:
    body = e.read().decode()
    sys.exit(f"❌ Error {e.code}: {body}")
