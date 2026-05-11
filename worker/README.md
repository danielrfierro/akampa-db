# Akampa AI Bot — Cloudflare Worker

Proxy entre el dashboard y la API de Google Gemini. Mantiene la API key fuera del browser.

## Setup (una sola vez)

### 1. API key de Gemini

Ya la tienes (de https://aistudio.google.com).

### 2. Crear cuenta de Cloudflare (si no tienes)

https://dash.cloudflare.com/sign-up — gratis.

### 3. Instalar wrangler

```bash
npm install -g wrangler
wrangler login          # abre browser → autoriza
```

### 4. Deploy

Desde este directorio (`worker/`):

```bash
wrangler secret put GEMINI_API_KEY
# pega tu key cuando lo pida

wrangler deploy
```

Wrangler te imprime la URL final, algo como:
`https://akampa-ai.<TU-SUBDOMINIO>.workers.dev`

### 5. Conectar el dashboard

Copia esa URL y pégala en `index.html` (al inicio del bloque AI bot):

```js
const AI_WORKER_URL = 'https://akampa-ai.tu-subdominio.workers.dev';
```

Push a `main` → GitHub Pages despliega → el bot está vivo.

## Cómo actualizar el system prompt

Edita `SYSTEM_PROMPT` en `worker.js` y vuelve a correr `wrangler deploy`.

## Cómo restringir el origin (opcional)

Una vez confirmado el dominio del dashboard (`https://sales.akampa.mx`), descomenta en `wrangler.toml`:

```toml
[vars]
ALLOWED_ORIGIN = "https://sales.akampa.mx"
```

Y re-deploy.

## Costos

- Cloudflare Workers: gratis hasta 100k requests/día
- Gemini 2.5 Flash: gratis hasta 1,500 requests/día (Google AI Studio free tier)

Para uso interno de Akampa, todo cabe sobrado en free tier.

## Cambiar de modelo

En `worker.js`, busca `gemini-2.5-flash` y cambia a:
- `gemini-2.5-flash` (default, balance velocidad/calidad)
- `gemini-2.5-pro` (más capaz, más lento, más caro si te sales del free tier)
- `gemini-2.0-flash` (alternativa más rápida)
