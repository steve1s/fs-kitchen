/**
 * FareShare Kitchen — Cloudflare Worker
 * ───────────────────────────────────────
 * Secure proxy between the public app and Anthropic API.
 * Your API key lives here as a secret — never exposed to browsers.
 *
 * Free tier: 100,000 requests/day  →  workers.cloudflare.com
 *
 * DEPLOY STEPS:
 *   1. Go to workers.cloudflare.com → Create Worker
 *   2. Paste this entire file, click Deploy
 *   3. Go to Settings → Variables → Add:
 *        ANTHROPIC_API_KEY = sk-ant-...   (tick Encrypt)
 *   4. (Recommended) Set ALLOWED_ORIGIN below to your GitHub Pages URL
 *   5. Redeploy
 */

// ── CONFIG ────────────────────────────────────────────────────────────────
// Lock this down to your GitHub Pages URL after testing, e.g.:
//   "https://your-username.github.io"
// Leave as "*" during development.
const ALLOWED_ORIGIN = "*";

// Max recipe generations per IP per minute (burst guard)
const RATE_LIMIT = 5;
const ipLog = new Map();


// ── HANDLER ───────────────────────────────────────────────────────────────
export default {
  async fetch(request, env) {

    // CORS preflight
    if (request.method === "OPTIONS") {
      return respond(null, 204);
    }

    // Only POST allowed
    if (request.method !== "POST") {
      return respond({ error: "Method not allowed" }, 405);
    }

    // Rate limiting by IP
    const ip  = request.headers.get("CF-Connecting-IP") || "unknown";
    const now = Date.now();
    const hits = (ipLog.get(ip) || []).filter(t => now - t < 60_000);
    if (hits.length >= RATE_LIMIT) {
      return respond(
        { error: "Too many requests — please wait a moment and try again." },
        429
      );
    }
    hits.push(now);
    ipLog.set(ip, hits);

    // Parse body
    let body;
    try {
      body = await request.json();
    } catch {
      return respond({ error: "Invalid JSON" }, 400);
    }

    if (!body.messages || !Array.isArray(body.messages)) {
      return respond({ error: "Missing messages array" }, 400);
    }

    // Check secret is set
    if (!env.ANTHROPIC_API_KEY) {
      return respond(
        { error: "ANTHROPIC_API_KEY secret not set in Worker settings." },
        500
      );
    }

    // Forward to Anthropic — key injected server-side
    let anthropicResp;
    try {
      anthropicResp = await fetch("https://api.anthropic.com/v1/messages", {
        method: "POST",
        headers: {
          "Content-Type":      "application/json",
          "x-api-key":         env.ANTHROPIC_API_KEY,
          "anthropic-version": "2023-06-01",
        },
        body: JSON.stringify({
          model:      body.model      || "claude-sonnet-4-6",
          max_tokens: body.max_tokens || 1500,
          system:     body.system     || "",
          messages:   body.messages,
        }),
      });
    } catch (e) {
      return respond({ error: "Failed to reach Anthropic API: " + e.message }, 502);
    }

    const data = await anthropicResp.json();

    if (!anthropicResp.ok) {
      return respond(
        { error: data?.error?.message || `Anthropic error ${anthropicResp.status}` },
        anthropicResp.status
      );
    }

    return respond(data, 200);
  },
};


// ── HELPERS ───────────────────────────────────────────────────────────────
function respond(body, status) {
  return new Response(
    body === null ? null : JSON.stringify(body),
    {
      status,
      headers: {
        "Content-Type":                 "application/json",
        "Access-Control-Allow-Origin":  ALLOWED_ORIGIN,
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
      },
    }
  );
}
