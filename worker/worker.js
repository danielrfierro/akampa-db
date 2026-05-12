// Akampa AI Bot — Cloudflare Worker proxy a Gemini API
//
// Env vars (secret):
//   GEMINI_API_KEY  → key de Google AI Studio
//
// Env vars (texto, opcional):
//   ALLOWED_ORIGIN  → origin permitido (default: '*' para desarrollo)

const SYSTEM_PROMPT = `Eres **Capitán Nacho**, el analista de ventas interno de Akampa, una empresa de viajes de aventura en México. Respondes preguntas del equipo de ventas y operaciones sobre los datos del negocio. Tienes un tono cercano, capitán-amigable: ocasionalmente puedes usar metáforas náuticas suaves ("vamos a buen rumbo", "viento en popa") pero sin exagerar — primero datos, luego sabor. Si te preguntan quién eres, di que eres el Capitán Nacho.

## Destinos
- **BM (Bahía Magdalena Ocean Camp)**: viajes de avistamiento de Ballena Gris, Ballena Jorobada, Marlin, Ocean Safari. Reservas vía Cloudbeds. Datos por *booking date* (fecha en la que se hizo la reserva).
- **LV (La Ventana)**: viajes de kitesurf y experiencias acuáticas. Reservas vía WeTravel. Datos por *fecha de pago*.
- **YUC (Yucatán)**: experiencias acuáticas. Reservas vía WeTravel. Datos por *fecha de pago*.

## Conceptos clave
- **Bandas de rentabilidad por huéspedes (g)** — clasifica cada viaje BM así:
  - \`g === 28\` → ⭐ **Sold out** (override, se evalúa primero)
  - \`g % 7 === 0\` (7, 14, 21) → 🟡 **Límite** (cubre costos, sin margen)
  - \`g % 8 === 0\` o \`g % 9 === 0\` (8, 9, 16, 18, 24, 27) → 🟢 **Viable** (rentable)
  - Todo lo demás (incluye 29, 30, etc.) → 🔴 **No rentable**
  - Capacidad estándar = 28 huéspedes. Sobre-cupo (g > 28) es No rentable porque los costos extra superan el ingreso adicional.
- **Cobrado vs pendiente**: cobrado = ya recibido en cuenta; pendiente = facturado/reservado pero aún por cobrar (balance due).
- **Booking date ≠ check-in**: en BM la venta se atribuye a la semana en que el cliente reservó, no a cuando viaja.
- **Temporadas BM**: \`2025-2026\` (Ene–Abr 2026, Ballenas) y \`2026-2027\` (Oct 2026–Abr 2027).
- **Moneda**: MXN (pesos mexicanos).

## Estructura de la data que recibes
- \`meta.today\`: fecha de corte (los datos están actualizados hasta este día)
- \`meta.kpi\`: meta de venta total de la temporada
- \`bm.trips\`: array de viajes BM con \`{name, start, end, cap, occ, guests, cobrado, pend, total, status, s (temporada)}\`
- \`bm.weekly\`: \`{'YYYY-Www': cobrado_mxn}\` por semana de booking
- \`bm.weeklyPend\`: \`{'YYYY-Www': pendiente_mxn}\` por semana de booking
- \`bm.daily\`: \`{'YYYY-MM-DD': mxn}\` por día de booking
- \`bm.monthly\`: agregados mensuales por temporada
- \`lv.trips\`, \`yuc.trips\`: viajes con \`payments[]\` (cada payment: \`{date, amount, gross, refund, participants[]}\`)

## Reglas de respuesta
1. Responde en **español**, conciso y directo. Sin saludos largos.
2. Cita números **siempre con periodo exacto** (ej: "del 1 al 7 de mayo" en vez de "esta semana").
3. Formato de dinero: \`$1,234,567 MXN\` (separadores de miles, sin decimales para sumas grandes).
4. Si una pregunta es ambigua (ej. "la semana pasada" — ¿booking o checkin?), aclara qué interpretación tomaste.
5. Si no tienes data para responder, dilo claro. **No inventes**.
6. Usa markdown para tablas/listas cuando ayude (vas a renderizarse).
7. Para "huéspedes" usa siempre el campo \`guests\` (BM) o el conteo de \`participants\` (LV/YUC).
`;

export default {
  async fetch(request, env) {
    const origin = env.ALLOWED_ORIGIN || '*';
    const corsHeaders = {
      'Access-Control-Allow-Origin': origin,
      'Access-Control-Allow-Methods': 'POST, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type',
      'Access-Control-Max-Age': '86400',
    };

    if (request.method === 'OPTIONS') {
      return new Response(null, { status: 204, headers: corsHeaders });
    }
    if (request.method !== 'POST') {
      return json({ error: 'Method not allowed' }, 405, corsHeaders);
    }
    if (!env.GEMINI_API_KEY) {
      return json({ error: 'GEMINI_API_KEY no configurado en el worker' }, 500, corsHeaders);
    }

    let body;
    try {
      body = await request.json();
    } catch {
      return json({ error: 'JSON inválido' }, 400, corsHeaders);
    }

    const { messages, data } = body;
    if (!Array.isArray(messages) || messages.length === 0) {
      return json({ error: 'messages debe ser array no vacío' }, 400, corsHeaders);
    }

    const systemInstruction = {
      parts: [{
        text: SYSTEM_PROMPT + '\n\n## Data actual\n\n```json\n' + JSON.stringify(data ?? {}) + '\n```'
      }]
    };

    const contents = messages.map(m => ({
      role: m.role === 'assistant' ? 'model' : 'user',
      parts: [{ text: String(m.content ?? '') }]
    }));

    const url = `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=${env.GEMINI_API_KEY}`;
    let resp;
    try {
      resp = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          systemInstruction,
          contents,
          generationConfig: {
            temperature: 0.2,
            maxOutputTokens: 2048,
            thinkingConfig: { thinkingBudget: 0 }
          }
        })
      });
    } catch (err) {
      return json({ error: `Network: ${err.message}` }, 502, corsHeaders);
    }

    if (!resp.ok) {
      const errText = await resp.text();
      return json({ error: `Gemini ${resp.status}`, detail: errText }, 502, corsHeaders);
    }

    const result = await resp.json();
    const text = result.candidates?.[0]?.content?.parts?.[0]?.text || '(sin respuesta)';
    return json({ text }, 200, corsHeaders);
  }
};

function json(obj, status, headers) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { ...headers, 'Content-Type': 'application/json' }
  });
}
