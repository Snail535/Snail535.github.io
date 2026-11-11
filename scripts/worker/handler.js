// 下载入口配额：纯逻辑，不 import 任何 Cloudflare 专有 API，
// 因此可以直接用 Node 跑单测（见 test_handler.mjs）。
//
// 设计要点
// - 计数按「上海时间的自然日」重置，键为 c:<YYYYMMDD>:<ip>。
// - 只有真的发出链接才 +1；键不存在、方法不对都不计数。
// - 链接数据放 KV（i:<key>），代码里不出现任何网盘地址。

const DAY_TTL = 172800; // 计数键存活 2 天，过期自动回收

export function shanghaiDay(now) {
  const t = new Date(now + 8 * 3600 * 1000);
  return (
    t.getUTCFullYear() +
    String(t.getUTCMonth() + 1).padStart(2, "0") +
    String(t.getUTCDate()).padStart(2, "0")
  );
}

// 下一个「上海时间 0 点」的毫秒时间戳
export function resetAt(now) {
  const t = new Date(now + 8 * 3600 * 1000);
  return Date.UTC(t.getUTCFullYear(), t.getUTCMonth(), t.getUTCDate() + 1) - 8 * 3600 * 1000;
}

function allowedOrigins(env) {
  const raw = env.ALLOWED_ORIGINS || "https://snail535.github.io,https://www.snail535.github.io";
  return raw.split(",").map((s) => s.trim()).filter(Boolean);
}

function corsHeaders(origin, env) {
  const h = { Vary: "Origin" };
  if (origin && allowedOrigins(env).includes(origin)) {
    h["Access-Control-Allow-Origin"] = origin;
    h["Access-Control-Allow-Methods"] = "GET, OPTIONS";
    h["Access-Control-Allow-Headers"] = "Content-Type";
    h["Access-Control-Max-Age"] = "86400";
  }
  return h;
}

function json(body, status, extra = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store",
      ...extra,
    },
  });
}

function clientIp(request) {
  const ip = request.headers.get("CF-Connecting-IP");
  if (ip) return ip.trim();
  const xff = request.headers.get("X-Forwarded-For");
  if (xff) return xff.split(",")[0].trim();
  return "0.0.0.0";
}

// 站长白名单：密钥（?t= 或 cookie mg_admin）或固定 IP，都不计数、不受 5 次限制。
export function isExempt(request, env, url) {
  const ips = (env.BYPASS_IPS || "")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
  if (ips.includes(clientIp(request))) return true;

  const admin = (env.ADMIN_KEY || "").trim();
  if (!admin) return false;
  if (url.searchParams.get("t") === admin) return true;
  const cookie = request.headers.get("Cookie") || "";
  return cookie.split(";").some((c) => c.trim() === `mg_admin=${admin}`);
}

export async function handle(request, env, now = Date.now()) {
  const url = new URL(request.url);
  const origin = request.headers.get("Origin");
  const cors = corsHeaders(origin, env);

  if (request.method === "OPTIONS") {
    return new Response(null, { status: 204, headers: cors });
  }
  // 浏览器里从别的站点发起的调用一律拒掉；不带 Origin 的直接请求（curl、本机调试）才放行
  if (origin && !cors["Access-Control-Allow-Origin"]) {
    return json({ ok: false, reason: "origin" }, 403, { Vary: "Origin" });
  }
  if (request.method !== "GET") {
    return json({ ok: false, reason: "method" }, 405, cors);
  }
  if (url.pathname !== "/link") {
    return json({ ok: true, service: "magazine-links", limit: Number(env.DAILY_LIMIT) || 5 }, 200, cors);
  }

  const key = url.searchParams.get("k");
  if (!key) return json({ ok: false, reason: "missing_key" }, 400, cors);

  const limit = Number(env.DAILY_LIMIT) || 5;
  const ip = clientIp(request);
  const counterKey = `c:${shanghaiDay(now)}:${ip}`;
  const reset = resetAt(now);

  // 站长自己：不计数、直接发链接，方便随时验证网盘是否有效
  if (isExempt(request, env, url)) {
    const rec = await env.LINKS.get(`i:${key}`, { type: "json" });
    if (!rec || !rec.url) {
      return json({ ok: false, reason: "not_found" }, 404, cors);
    }
    return json(
      { ok: true, url: rec.url, pwd: rec.pwd || "", used: 0, limit, remaining: limit, bypass: true, resetAt: reset },
      200,
      cors
    );
  }

  const usedRaw = await env.LINKS.get(counterKey);
  const used = Number(usedRaw) || 0;

  if (used >= limit) {
    return json({ ok: false, reason: "limit", used, limit, resetAt: reset }, 429, cors);
  }

  const rec = await env.LINKS.get(`i:${key}`, { type: "json" });
  if (!rec || !rec.url) {
    return json({ ok: false, reason: "not_found" }, 404, cors);
  }

  const next = used + 1;
  await env.LINKS.put(counterKey, String(next), { expirationTtl: DAY_TTL });

  return json(
    {
      ok: true,
      url: rec.url,
      pwd: rec.pwd || "",
      used: next,
      limit,
      remaining: Math.max(0, limit - next),
      resetAt: reset,
    },
    200,
    cors
  );
}
