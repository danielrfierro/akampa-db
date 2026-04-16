#!/usr/bin/env python3
"""
akampa_gmail_downloader.py  —  Descarga el Excel más reciente de Cloudbeds desde Gmail
Diseñado para correr en GitHub Actions (headless, sin interacción).

Requiere variables de entorno:
  GMAIL_CLIENT_ID
  GMAIL_CLIENT_SECRET
  GMAIL_REFRESH_TOKEN

Guarda el archivo descargado como: reportes/cloudbeds_latest.xlsx
"""

import os
import base64
import json
import urllib.request
import urllib.parse
import sys
from pathlib import Path

# ── Configuración ─────────────────────────────────────────────────────────────
SENDER_FILTER   = "noreply@cloudbeds.com"
SUBJECT_FILTER  = "Reporte Sales Inteligence"   # tal como llega en el correo
DOWNLOAD_PATH   = Path("reportes/cloudbeds_latest.xlsx")
TOKEN_URL       = "https://oauth2.googleapis.com/token"
GMAIL_API_BASE  = "https://gmail.googleapis.com/gmail/v1/users/me"

# ── Helpers ───────────────────────────────────────────────────────────────────

def get_access_token(client_id: str, client_secret: str, refresh_token: str) -> str:
    """Obtiene un access token nuevo usando el refresh token."""
    data = urllib.parse.urlencode({
        "client_id":     client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type":    "refresh_token",
    }).encode()

    req = urllib.request.Request(TOKEN_URL, data=data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")

    with urllib.request.urlopen(req) as resp:
        token_data = json.loads(resp.read())

    if "access_token" not in token_data:
        raise RuntimeError(f"No se pudo obtener access token: {token_data}")

    print("✓ Access token obtenido")
    return token_data["access_token"]


def gmail_get(access_token: str, endpoint: str, params: dict = None) -> dict:
    """GET a la API de Gmail."""
    url = f"{GMAIL_API_BASE}/{endpoint}"
    if params:
        url += "?" + urllib.parse.urlencode(params)

    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {access_token}")

    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def find_latest_message(access_token: str) -> str | None:
    """Busca el mensaje más reciente que coincida con sender + subject."""
    query = f"from:{SENDER_FILTER} subject:{SUBJECT_FILTER}"
    result = gmail_get(access_token, "messages", {
        "q":          query,
        "maxResults": 5,
    })

    messages = result.get("messages", [])
    if not messages:
        print(f"⚠️  No se encontraron correos de '{SENDER_FILTER}' con asunto '{SUBJECT_FILTER}'")
        return None

    # El primero es el más reciente (Gmail retorna en orden inverso)
    msg_id = messages[0]["id"]
    print(f"✓ Correo encontrado: {msg_id}")
    return msg_id


def extract_xlsx_attachment(access_token: str, msg_id: str) -> bytes | None:
    """Extrae el primer attachment .xlsx del mensaje."""
    msg = gmail_get(access_token, f"messages/{msg_id}", {"format": "full"})
    parts = msg.get("payload", {}).get("parts", [])

    for part in parts:
        filename = part.get("filename", "")
        mime     = part.get("mimeType", "")
        body     = part.get("body", {})

        if filename.endswith(".xlsx") or "spreadsheet" in mime or "excel" in mime:
            attachment_id = body.get("attachmentId")

            if attachment_id:
                # Adjunto grande → llamada separada
                att = gmail_get(access_token, f"messages/{msg_id}/attachments/{attachment_id}")
                data = att["data"]
            elif "data" in body:
                data = body["data"]
            else:
                continue

            # Gmail usa base64url
            xlsx_bytes = base64.urlsafe_b64decode(data + "==")
            print(f"✓ Attachment extraído: {filename} ({len(xlsx_bytes):,} bytes)")
            return xlsx_bytes

    print("⚠️  No se encontró attachment .xlsx en el correo")
    return None


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    client_id     = os.environ.get("GMAIL_CLIENT_ID")
    client_secret = os.environ.get("GMAIL_CLIENT_SECRET")
    refresh_token = os.environ.get("GMAIL_REFRESH_TOKEN")

    if not all([client_id, client_secret, refresh_token]):
        sys.exit("❌ Faltan variables de entorno: GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET, GMAIL_REFRESH_TOKEN")

    print("🔑 Autenticando con Gmail...")
    access_token = get_access_token(client_id, client_secret, refresh_token)

    print("📬 Buscando correo de Cloudbeds...")
    msg_id = find_latest_message(access_token)
    if not msg_id:
        sys.exit(1)

    print("📎 Extrayendo archivo Excel...")
    xlsx_bytes = extract_xlsx_attachment(access_token, msg_id)
    if not xlsx_bytes:
        sys.exit(1)

    # Guardar
    DOWNLOAD_PATH.parent.mkdir(parents=True, exist_ok=True)
    DOWNLOAD_PATH.write_bytes(xlsx_bytes)
    print(f"\n✅ Guardado en: {DOWNLOAD_PATH}  ({len(xlsx_bytes):,} bytes)")


if __name__ == "__main__":
    main()
