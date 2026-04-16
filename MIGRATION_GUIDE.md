# Migración Netlify → GitHub Pages
## Akampa Sales Intelligence Dashboard

**Repositorio:** `danielrfierro/akampa-db`  
**URL final:** `https://danielrfierro.github.io/akampa-db`

---

## ESTRUCTURA DEL REPOSITORIO

Antes de empezar, asegúrate de que la carpeta del proyecto tenga esta estructura:

```
akampa-db/
├── index.html                          ← akampa-dashboard-v3.html renombrado
├── akampa-data-v3.js                   ← datos actuales
├── akampa-data-v3.json                 ← datos actuales (JSON)
├── .github/
│   └── workflows/
│       ├── deploy.yml                  ← deploy automático a GH Pages
│       └── daily-update.yml            ← actualización semanal de datos
├── scripts/
│   ├── akampa_processor_v3.py          ← copia desde tu Mac
│   ├── akampa_run_weekly.py            ← copia desde tu Mac
│   ├── akampa_gmail_downloader.py      ← versión nueva (headless)
│   ├── generate_gmail_token.py         ← setup one-time local
│   └── requirements.txt
├── .gitignore
└── MIGRATION_GUIDE.md
```

**Nota:** La carpeta `reportes/` está en .gitignore — los XLSXs nunca se suben al repo.

---

## PASO 1 — Preparar la carpeta local

Abre Terminal. Navega a la carpeta del proyecto:

```bash
# Ajusta la ruta si es diferente
cd ~/Documents/Cowork/Akampa\ Sales\ Intelligence\ Dashboard
```

Renombra el HTML principal a `index.html` (GitHub Pages lo necesita así):

```bash
cp akampa-dashboard-v3.html index.html
```

Copia tus scripts Python a la subcarpeta `scripts/`:

```bash
cp ~/ruta/a/akampa_processor_v3.py scripts/
cp ~/ruta/a/akampa_run_weekly.py   scripts/
```

> Si no sabes la ruta exacta de tus scripts, búscalos con:
> `find ~ -name "akampa_processor_v3.py" 2>/dev/null`

---

## PASO 2 — Inicializar git y conectar a GitHub

```bash
# Inicializar repositorio local
git init

# Agregar todos los archivos (excepto los del .gitignore)
git add .

# Primer commit
git commit -m "🚀 Initial commit — migración desde Netlify"

# Conectar al repositorio GitHub que ya creaste
git remote add origin https://github.com/danielrfierro/akampa-db.git

# Establecer rama principal como 'main'
git branch -M main

# Primer push
git push -u origin main
```

---

## PASO 3 — Activar GitHub Pages en el repositorio

1. Ve a `https://github.com/danielrfierro/akampa-db`
2. Click en **Settings** (pestaña superior)
3. En el menú izquierdo → **Pages**
4. En "Source" selecciona: **GitHub Actions**
5. Guarda

Esto permite que el workflow `deploy.yml` publique el sitio.

---

## PASO 4 — Configurar el Personal Access Token (para que el bot pueda hacer push)

El workflow `daily-update.yml` necesita un token con permisos de escritura para hacer commit y push de los datos actualizados.

1. Ve a `https://github.com/settings/tokens/new`
2. Nombre: `akampa-data-bot`
3. Expiration: 1 year (o "No expiration")
4. Scopes: marca ✅ **repo** (acceso completo a repositorios privados/públicos)
5. Click **Generate token** — **cópialo ahora**, no lo podrás ver de nuevo

Luego agrégalo como Secret en el repo:

1. Ve a `https://github.com/danielrfierro/akampa-db/settings/secrets/actions`
2. Click **New repository secret**
3. Name: `GH_PAT`
4. Secret: pega el token que copiaste
5. Click **Add secret**

---

## PASO 5 — Configurar Gmail OAuth2 (setup one-time)

Este paso se hace UNA SOLA VEZ en tu Mac para obtener el refresh_token permanente.

### 5a. Crear credenciales en Google Cloud Console

1. Ve a `https://console.cloud.google.com/`
2. Crea un proyecto nuevo (o usa uno existente) — ej. "Akampa Gmail Bot"
3. En el menú → **APIs y servicios** → **Biblioteca**
4. Busca "Gmail API" → **Habilitar**
5. Ve a **APIs y servicios** → **Credenciales**
6. Click **Crear credenciales** → **ID de cliente OAuth 2.0**
7. Tipo de aplicación: **Aplicación de escritorio**
8. Nombre: "akampa-gmail-downloader"
9. Click **Crear** → **Descargar JSON**
10. Guarda el archivo como `credentials.json` en la raíz del proyecto

### 5b. Generar el refresh token

```bash
# Instalar dependencia (solo una vez)
pip3 install google-auth-oauthlib

# Correr el script de setup
python3 scripts/generate_gmail_token.py
```

El script abrirá tu navegador para que autorices el acceso. Después de autorizar, verás en Terminal:

```
GMAIL_CLIENT_ID     →  123456789...apps.googleusercontent.com
GMAIL_CLIENT_SECRET →  GOCSPX-...
GMAIL_REFRESH_TOKEN →  1//04...
```

### 5c. Agregar los tres valores como GitHub Secrets

Ve a `https://github.com/danielrfierro/akampa-db/settings/secrets/actions` y crea tres secrets:

| Name | Value |
|------|-------|
| `GMAIL_CLIENT_ID` | el valor que te mostró el script |
| `GMAIL_CLIENT_SECRET` | el valor que te mostró el script |
| `GMAIL_REFRESH_TOKEN` | el valor que te mostró el script |

> **Importante:** `credentials.json` y `gmail_secrets.json` ya están en `.gitignore`. 
> Nunca los subas al repositorio.

---

## PASO 6 — Primer deploy manual para verificar

Una vez que hiciste el push en el Paso 2, el workflow `deploy.yml` debería haberse disparado automáticamente.

Para verificar:
1. Ve a `https://github.com/danielrfierro/akampa-db/actions`
2. Deberías ver el workflow "Deploy to GitHub Pages" corriendo o completado
3. Si está verde ✅ → tu sitio ya está en `https://danielrfierro.github.io/akampa-db`

Para correr el deploy manualmente:
1. Ve a Actions → "Deploy to GitHub Pages" → **Run workflow**

---

## PASO 7 — Verificar el workflow de actualización diaria

Para probar que el workflow de datos funciona (sin esperar al lunes):

1. Ve a `https://github.com/danielrfierro/akampa-db/actions`
2. Click en "Daily Data Update"
3. Click **Run workflow** → **Run workflow** (botón verde)
4. Observa los logs en tiempo real
5. Si todo va bien, verás un nuevo commit en `main` con los datos actualizados

---

## PASO 8 — Actualizar referencias a la URL (opcional)

Si tienes links a `https://akampa-sales.netlify.app` en otros lados:
- La nueva URL es: `https://danielrfierro.github.io/akampa-db`
- Puedes configurar un dominio personalizado en GitHub Pages (Settings → Pages → Custom domain)

---

## RESUMEN DE SECRETS NECESARIOS

| Secret | Para qué sirve |
|--------|----------------|
| `GH_PAT` | Permite al workflow hacer push de datos actualizados |
| `GMAIL_CLIENT_ID` | Autenticación OAuth2 Gmail |
| `GMAIL_CLIENT_SECRET` | Autenticación OAuth2 Gmail |
| `GMAIL_REFRESH_TOKEN` | Autenticación OAuth2 Gmail (token permanente) |

---

## TROUBLESHOOTING

**El workflow de deploy falla con "Permission denied"**
→ Verifica que en Settings → Pages hayas seleccionado "GitHub Actions" como source.

**El workflow de datos falla al hacer push**
→ Verifica que el secret `GH_PAT` tenga scope `repo` completo.

**Gmail dice "invalid_grant" o "invalid_client"**
→ El refresh_token puede haber expirado si no se usa por 6 meses, o si cambiaste la contraseña de Google. Re-corre `generate_gmail_token.py`.

**No encuentra el correo de Cloudbeds**
→ Verifica el asunto exacto en `akampa_gmail_downloader.py` (variable `SUBJECT_FILTER`). El asunto actual configurado es: "Reporte Sales Inteligence".

**El HTML no carga los datos correctamente**
→ Verifica que `akampa-data-v3.js` exista en la raíz del repo y que el HTML lo referencie correctamente.
