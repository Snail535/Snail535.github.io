// 下载入口配额 + 热度统计：纯逻辑，不 import 任何 Cloudflare 专有 API，
// 因此可以直接用 Node 跑单测（见 test_handler.mjs）。
//
// 设计要点
// - 计数按「上海时间的自然日」重置，键为 c:<YYYYMMDD>:<ip>。
// - 只有真的发出链接才 +1；键不存在、方法不对都不计数。
// - 链接数据放 KV（i:<key>），代码里不出现任何网盘地址。
// - 热度统计放 D1（hits 表按 天 + 刊物期次 累加），一次下载只写 1 行，不占 KV 的 1000 写/天。
//   /hot 是公开只读接口，给站点上的「本周热榜」用；任何异常都降级为空榜单，绝不影响发链接。

const DAY_TTL = 172800; // 计数键存活 2 天，过期自动回收
const HOT_DAYS = 7; // 热榜默认窗口
const HOT_LIMIT = 20;
const HOT_CACHE_TTL = 600; // 边缘缓存 10 分钟，避免每次访问都打 D1
const HOT_SNAPSHOT = 100; // 缓存里固定存的条数（各页面从同一份快照上切）
const PASS_DAYS = 90; // 通行证默认有效天数
const REDEEM_TRIES = 5; // 每个 IP 每天最多尝试兑换次数（防爆破）
// 邀请码字符集：去掉 0/O/1/I，避免看错、抄错
const CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";

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

// 「近 N 天」（含今天）的起始日，返回 YYYYMMDD，可直接和 day 字段做字符串比较
export function windowStart(days, now) {
  const span = Math.max(1, Math.min(365, Number(days) || HOT_DAYS)) - 1;
  return shanghaiDay(now - span * 86400000);
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

// 热榜是公开只读的聚合数据，任何来源都可读（站点可能走 github.io 也可能走自己的域名）
const PUBLIC_CORS = { "Access-Control-Allow-Origin": "*" };

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

/* ---------------- 热度统计 ---------------- */

// 记一次「真的发出了链接」。任何异常都吞掉：统计坏掉不能让下载入口挂掉。
export async function recordHit(env, key, now = Date.now()) {
  if (!env.DB || !key) return false;
  try {
    await env.DB.prepare(
      "INSERT INTO hits (day, k, n) VALUES (?, ?, 1) ON CONFLICT(day, k) DO UPDATE SET n = n + 1"
    )
      .bind(shanghaiDay(now), key)
      .run();
    return true;
  } catch (e) {
    return false;
  }
}

async function queryHot(env, days, limit, now = Date.now()) {
  const empty = { items: [], total: 0 };
  if (!env.DB) return empty;
  const from = windowStart(days, now);
  try {
    const [rows, sum] = await env.DB.batch([
      env.DB.prepare(
        "SELECT k, SUM(n) AS n FROM hits WHERE day >= ? GROUP BY k ORDER BY n DESC, k ASC LIMIT ?"
      ).bind(from, limit),
      env.DB.prepare("SELECT COALESCE(SUM(n), 0) AS n FROM hits WHERE day >= ?").bind(from),
    ]);
    const items = ((rows && rows.results) || []).map((r) => ({ k: r.k, n: Number(r.n) || 0 }));
    const total = Number(((sum && sum.results) || [{}])[0].n) || 0;
    return { items, total };
  } catch (e) {
    return empty;
  }
}

async function hotResponse(request, env, url, ctx, now) {
  const days = Math.max(1, Math.min(90, Number(url.searchParams.get("days")) || HOT_DAYS));
  const limit = Math.max(1, Math.min(100, Number(url.searchParams.get("n")) || HOT_LIMIT));
  // 缓存键只按 days：首页 n=8、榜单页 n=20 共用同一份快照，保证所有页面同一时刻数据一致
  const cacheKey = new URL(url.origin);
  cacheKey.pathname = "/__hot";
  cacheKey.search = `?days=${days}`;

  const cache = typeof caches !== "undefined" && caches.default ? caches.default : null;
  let snapshot = null;
  if (cache) {
    try {
      const hit = await cache.match(cacheKey.toString());
      if (hit) snapshot = await hit.json();
    } catch (e) {
      /* 缓存读失败就当没命中 */
    }
  }
  if (!snapshot || !Array.isArray(snapshot.items)) {
    const { items, total } = await queryHot(env, days, HOT_SNAPSHOT, now);
    snapshot = { ok: true, days, total, updated: new Date(now).toISOString(), items };
    const cached = json(snapshot, 200, {
      ...PUBLIC_CORS,
      "Cache-Control": `public, max-age=${HOT_CACHE_TTL}`,
    });
    if (cache && ctx && typeof ctx.waitUntil === "function") {
      ctx.waitUntil(cache.put(cacheKey.toString(), cached).catch(() => {}));
    }
  }
  // 每个请求从快照上切自己要的条数，重新包一层响应
  return json(
    { ...snapshot, limit, items: snapshot.items.slice(0, limit) },
    200,
    { ...PUBLIC_CORS, "Cache-Control": `public, max-age=${HOT_CACHE_TTL}` }
  );
}

// 站长用的明细：更长窗口 + 按天趋势，需要 ADMIN_KEY
async function statsResponse(env, url, now) {
  const admin = (env.ADMIN_KEY || "").trim();
  if (!admin || url.searchParams.get("t") !== admin) {
    return json({ ok: false, reason: "forbidden" }, 403);
  }
  if (!env.DB) return json({ ok: true, items: [], total: 0, daily: [], note: "db_missing" }, 200);
  const days = Math.max(1, Math.min(365, Number(url.searchParams.get("days")) || 30));
  const limit = Math.max(1, Math.min(500, Number(url.searchParams.get("n")) || 50));
  const from = windowStart(days, now);
  try {
    const [rows, sum, daily] = await env.DB.batch([
      env.DB.prepare(
        "SELECT k, SUM(n) AS n FROM hits WHERE day >= ? GROUP BY k ORDER BY n DESC, k ASC LIMIT ?"
      ).bind(from, limit),
      env.DB.prepare("SELECT COALESCE(SUM(n), 0) AS n FROM hits WHERE day >= ?").bind(from),
      env.DB.prepare("SELECT day, SUM(n) AS n FROM hits WHERE day >= ? GROUP BY day ORDER BY day").bind(from),
    ]);
    return json(
      {
        ok: true,
        days,
        total: Number(((sum && sum.results) || [{}])[0].n) || 0,
        items: ((rows && rows.results) || []).map((r) => ({ k: r.k, n: Number(r.n) || 0 })),
        daily: ((daily && daily.results) || []).map((r) => ({ d: r.day, n: Number(r.n) || 0 })),
      },
      200,
      PUBLIC_CORS
    );
  } catch (e) {
    return json({ ok: false, reason: "db_error", message: String(e && e.message) }, 500, PUBLIC_CORS);
  }
}

/* ---------------- 通行证（邀请码兑换） ---------------- */

function randomToken(len, alphabet) {
  const chars = [];
  try {
    const buf = new Uint8Array(len);
    crypto.getRandomValues(buf);
    for (let i = 0; i < len; i += 1) chars.push(alphabet[buf[i] % alphabet.length]);
  } catch (e) {
    for (let i = 0; i < len; i += 1) chars.push(alphabet[Math.floor(Math.random() * alphabet.length)]);
  }
  return chars.join("");
}

// 校验通行证：D1 里查得到且未过期才算数。返回 { exp } 或 null。
export async function checkPass(env, pid, now = Date.now()) {
  const p = (pid || "").trim();
  if (!env.DB || !p || !/^[a-f0-9]{32}$/i.test(p)) return null;
  try {
    const row = await env.DB.prepare("SELECT exp FROM passes WHERE pid = ?").bind(p.toLowerCase()).first();
    if (row && Number(row.exp) > now) return { exp: Number(row.exp) };
  } catch (e) {
    /* 数据库坏掉就当没有通行证，不能影响发链接 */
  }
  return null;
}

// 兑换邀请码：GET /redeem?code=XXX
// 原子扣减 uses_done，防止一码被并发超用；每个 IP 每天最多试 REDEEM_TRIES 次。
async function redeemResponse(request, env, url, now, ip) {
  const code = (url.searchParams.get("code") || "").trim().toUpperCase();
  if (!code || !/^[A-Z2-9]{8,16}$/.test(code)) {
    return json({ ok: false, reason: "bad_code", message: "邀请码格式不对" }, 400, corsHeaders(request.headers.get("Origin"), env));
  }
  if (!env.DB) return json({ ok: false, reason: "db_missing" }, 503, corsHeaders(request.headers.get("Origin"), env));

  // 尝试次数限制：和下载配额分开计数
  const tryKey = `r:${shanghaiDay(now)}:${ip}`;
  const triedRaw = await env.LINKS.get(tryKey);
  const tried = Number(triedRaw) || 0;
  if (tried >= REDEEM_TRIES) {
    return json({ ok: false, reason: "try_limit", message: "今天尝试次数太多，明天再来" }, 429, corsHeaders(request.headers.get("Origin"), env));
  }
  await env.LINKS.put(tryKey, String(tried + 1), { expirationTtl: DAY_TTL });

  const cors = corsHeaders(request.headers.get("Origin"), env);
  try {
    const row = await env.DB.prepare(
      "SELECT uses_max, uses_done, days FROM codes WHERE code = ?"
    ).bind(code).first();
    if (!row) return json({ ok: false, reason: "bad_code", message: "邀请码不存在或已被删掉" }, 404, cors);

    const upd = await env.DB.prepare(
      "UPDATE codes SET uses_done = uses_done + 1 WHERE code = ? AND uses_done < uses_max"
    ).bind(code).run();
    if (!upd || !upd.meta || upd.meta.changes !== 1) {
      return json({ ok: false, reason: "code_used", message: "这个邀请码的可兑换次数已用完" }, 409, cors);
    }

    const days = Number(row.days) || PASS_DAYS;
    const exp = now + days * 86400000;
    const pid = randomToken(32, "0123456789abcdef");
    await env.DB.prepare(
      "INSERT INTO passes (pid, code, exp, created) VALUES (?, ?, ?, ?)"
    ).bind(pid, code, exp, now).run();

    return json({ ok: true, pid, exp, days }, 200, cors);
  } catch (e) {
    return json({ ok: false, reason: "db_error", message: "系统开小差，请稍后再试" }, 500, cors);
  }
}

// 查通行证状态：GET /pass?p=<pid>
async function passStatusResponse(request, env, url, now) {
  const cors = corsHeaders(request.headers.get("Origin"), env);
  const info = await checkPass(env, url.searchParams.get("p"), now);
  return json(info ? { ok: true, valid: true, exp: info.exp } : { ok: true, valid: false }, 200, cors);
}

// 站长发邀请码：GET /gen?t=<ADMIN_KEY>&n=5&uses=1&days=90&note=
async function genResponse(env, url, now) {
  const admin = (env.ADMIN_KEY || "").trim();
  if (!admin || url.searchParams.get("t") !== admin) {
    return json({ ok: false, reason: "forbidden" }, 403, PUBLIC_CORS);
  }
  if (!env.DB) return json({ ok: false, reason: "db_missing" }, 503, PUBLIC_CORS);
  const n = Math.max(1, Math.min(50, Number(url.searchParams.get("n")) || 5));
  const uses = Math.max(1, Math.min(100, Number(url.searchParams.get("uses")) || 1));
  const days = Math.max(1, Math.min(365, Number(url.searchParams.get("days")) || PASS_DAYS));
  const note = (url.searchParams.get("note") || "").slice(0, 60);
  const codes = [];
  try {
    for (let i = 0; i < n; i += 1) {
      const code = randomToken(12, CODE_ALPHABET);
      await env.DB.prepare(
        "INSERT INTO codes (code, uses_max, uses_done, days, created_at, note) VALUES (?, ?, 0, ?, ?, ?)"
      ).bind(code, uses, days, now, note).run();
      codes.push(code);
    }
  } catch (e) {
    return json({ ok: false, reason: "db_error", message: String(e && e.message) }, 500, PUBLIC_CORS);
  }
  return json({ ok: true, uses, days, note, codes }, 200, PUBLIC_CORS);
}

// 站长看码况：GET /codes?t=<ADMIN_KEY>
async function codesResponse(env, url) {
  const admin = (env.ADMIN_KEY || "").trim();
  if (!admin || url.searchParams.get("t") !== admin) {
    return json({ ok: false, reason: "forbidden" }, 403, PUBLIC_CORS);
  }
  if (!env.DB) return json({ ok: true, codes: [], passes: 0, note: "db_missing" }, 200, PUBLIC_CORS);
  try {
    const [codes, passes] = await env.DB.batch([
      env.DB.prepare(
        "SELECT code, uses_max, uses_done, days, created_at, note FROM codes ORDER BY created_at DESC LIMIT 200"
      ),
      env.DB.prepare("SELECT COUNT(*) AS n FROM passes"),
    ]);
    return json(
      {
        ok: true,
        codes: ((codes && codes.results) || []).map((r) => ({
          code: r.code,
          uses: `${r.uses_done}/${r.uses_max}`,
          days: r.days,
          note: r.note || "",
          created_at: Number(r.created_at),
          dead: r.uses_done >= r.uses_max,
        })),
        passes: Number(((passes && passes.results) || [{}])[0].n) || 0,
      },
      200,
      PUBLIC_CORS
    );
  } catch (e) {
    return json({ ok: false, reason: "db_error", message: String(e && e.message) }, 500, PUBLIC_CORS);
  }
}



/* ---------------- 入口 ---------------- */

export async function handle(request, env, now = Date.now(), ctx = null) {
  const url = new URL(request.url);
  const origin = request.headers.get("Origin");
  const cors = corsHeaders(origin, env);

  if (request.method === "OPTIONS") {
    const allow = url.pathname === "/hot" ? { ...PUBLIC_CORS } : cors;
    return new Response(null, { status: 204, headers: allow });
  }

  // 热榜 / 明细 / 通行证：公开数据与功能，不做来源限制
  if (url.pathname === "/hot") {
    if (request.method !== "GET") return json({ ok: false, reason: "method" }, 405, PUBLIC_CORS);
    return hotResponse(request, env, url, ctx, now);
  }
  if (url.pathname === "/redeem") {
    if (request.method !== "GET") return json({ ok: false, reason: "method" }, 405);
    return redeemResponse(request, env, url, now, clientIp(request));
  }
  if (url.pathname === "/pass") {
    if (request.method !== "GET") return json({ ok: false, reason: "method" }, 405);
    return passStatusResponse(request, env, url, now);
  }
  if (url.pathname === "/gen" || url.pathname === "/codes") {
    if (request.method !== "GET") return json({ ok: false, reason: "method" }, 405, PUBLIC_CORS);
    return url.pathname === "/gen" ? genResponse(env, url, now) : codesResponse(env, url);
  }
  if (url.pathname === "/stats") {
    if (request.method !== "GET") return json({ ok: false, reason: "method" }, 405);
    return statsResponse(env, url, now);
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

  // 持通行证：不限次、不占 5 次配额，但下载热度照记（会员也是真实兴趣）
  const passInfo = await checkPass(env, url.searchParams.get("p"), now);
  if (passInfo) {
    const rec = await env.LINKS.get(`i:${key}`, { type: "json" });
    if (!rec || !rec.url) {
      return json({ ok: false, reason: "not_found" }, 404, cors);
    }
    await recordHit(env, key, now);
    return json(
      {
        ok: true,
        url: rec.url,
        pwd: rec.pwd || "",
        used: 0,
        limit,
        remaining: limit,
        pass: true,
        exp: passInfo.exp,
        resetAt: reset,
      },
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

  // 热度 +1：写 D1，不占 KV 配额；失败也不影响本次发链接
  await recordHit(env, key, now);

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
