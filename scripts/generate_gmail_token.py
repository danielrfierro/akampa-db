#!/usr/bin/env python3
"""
generate_gmail_token.py  —  Setup ONE-TIME local
Corre este script UNA VEZ en tu Mac para obtener el refresh_token
que guardarás como GitHub Secret.

Prerequisitos:
  pip install google-auth-oauthlib
  Tener credentials.json descargado de Google Cloud Console

Uso:
  python3 scripts/generate_gmail_token.py
"""

import json
import sys
from pathlib import Path

try:
    from google_auth_oauthlib.flow import InstalledAppFlow
except ImportError:
    sys.exit("❌ Instala: pip install google-auth-oauthlib")

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
CREDENTIALS_FILE = Path("credentials.json")

if not CREDENTIALS_FILE.exists():
    print("❌ No encontré credentials.json en esta carpeta.")
    print()
    print("Pasos para obtenerlo:")
    print("  1. Ve a https://console.cloud.google.com/")
    print("  2. Crea un proyecto (o usa uno existente)")
    print("  3. Habilita la Gmail API")
    print("  4. Ve a 'Credenciales' → 'Crear credenciales' → 'ID de cliente OAuth 2.0'")
    print("  5. Tipo: 'Aplicación de escritorio'")
    print("  6. Descarga el JSON y guárdalo como credentials.json en la raíz del proyecto")
    sys.exit(1)

print("🔑 Iniciando flujo OAuth2...")
print("   (Se abrirá tu navegador para que autorices el acceso a Gmail)")
print()

flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
creds = flow.run_local_server(port=0)

client_id     = creds.client_id
client_secret = creds.client_secret
refresh_token = creds.refresh_token

print()
print("=" * 60)
print("✅  COPIA ESTOS VALORES COMO GITHUB SECRETS")
print("=" * 60)
print()
print(f"GMAIL_CLIENT_ID     →  {client_id}")
print()
print(f"GMAIL_CLIENT_SECRET →  {client_secret}")
print()
print(f"GMAIL_REFRESH_TOKEN →  {refresh_token}")
print()
print("=" * 60)
print("  GitHub → repo akampa-db → Settings → Secrets and variables")
print("  → Actions → New repository secret")
print("=" * 60)

# Guardar también en archivo local (NO hacer commit de esto)
output = {
    "GMAIL_CLIENT_ID":     client_id,
    "GMAIL_CLIENT_SECRET": client_secret,
    "GMAIL_REFRESH_TOKEN": refresh_token,
}
Path("gmail_secrets.json").write_text(json.dumps(output, indent=2))
print()
print("  También guardado en gmail_secrets.json (está en .gitignore)")
