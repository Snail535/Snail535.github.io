// 本地单测：node scripts/worker/test_handler.mjs
// 用内存 KV 模拟 Cloudflare KV，验证配额、跨域、日期重置等行为。
import { handle, shanghaiDay, resetAt } from "./handler.js";

class MemoryKV {
  constructor() {
    this.map = new Map();
    this.writes = 0;
  }
  async get(key, opts) {
    const v = this.map.get(key);
    if (v === undefined) return null;
    if (opts && opts.type === "json") return JSON.parse(v);
    return v;
  }
  async put(key, value, opts) {
    this.map.set(key, value);
    this.writes += 1;
  }
}

const env = { LINKS: new MemoryKV(), DAILY_LIMIT: "5", ALLOWED_ORIGINS: "https://snail535.github.io" };
const ORIGIN = "https://snail535.github.io";
const T0 = Date.UTC(2026, 10, 10, 4, 0, 0); // 2026-11-10 12:00 +08:00

function req(path, { ip = "1.2.3.4", method = "GET", origin = ORIGIN } = {}) {
  const headers = new Headers();
  if (ip) headers.set("CF-Connecting-IP", ip);
  if (origin) headers.set("Origin", origin);
  return new Request(`https://dl.example.com${path}`, { method, headers });
}

let pass = 0;
let fail = 0;
function check(name, cond, detail = "") {
  if (cond) {
    pass += 1;
    console.log(`  ok   ${name}`);
  } else {
    fail += 1;
    console.log(`  FAIL ${name} ${detail}`);
  }
}

// 准备两条链接
await env.LINKS.put("i:magazines/economist/2025-01-04-usa", JSON.stringify({ url: "https://pan.quark.cn/s/aaa", pwd: "" }));
await env.LINKS.put("i:magazines/fhm/2025-02-canada", JSON.stringify({ url: "https://pan.quark.cn/s/bbb", pwd: "k3x9" }));

console.log("日期工具");
check("上海日期", shanghaiDay(T0) === "20261110", shanghaiDay(T0));
check("重置时间 = 次日 0 点", new Date(resetAt(T0)).toISOString() === "2026-11-10T16:00:00.000Z", new Date(resetAt(T0)).toISOString());

console.log("\n配额（5 次/天）");
const K = "/link?k=magazines/economist/2025-01-04-usa";
for (let i = 1; i <= 5; i += 1) {
  const r = await handle(req(K), env, T0);
  const b = await r.json();
  check(`第 ${i} 次放行，剩余 ${5 - i}`, r.status === 200 && b.ok && b.remaining === 5 - i, `status=${r.status} ${JSON.stringify(b)}`);
}

const sixth = await handle(req(K), env, T0);
const sixthBody = await sixth.json();
check("第 6 次被拒 429", sixth.status === 429 && sixthBody.reason === "limit", `status=${sixth.status}`);
check("被拒后不再写 KV", env.LINKS.writes === 5 + 2, `writes=${env.LINKS.writes}`);

console.log("\n换 IP 不受影响");
const other = await handle(req(K, { ip: "5.6.7.8" }), env, T0);
const otherBody = await other.json();
check("不同 IP 仍有完整 5 次", other.status === 200 && otherBody.remaining === 4, `status=${other.status}`);

console.log("\n跨天重置");
const tomorrow = T0 + 86400000;
const reset = await handle(req(K), env, tomorrow);
const resetBody = await reset.json();
check("次日 0 点后恢复", reset.status === 200 && resetBody.used === 1, `status=${reset.status}`);

console.log("\n不存在 / 参数错误不计数");
const before = env.LINKS.writes;
const missing = await handle(req("/link?k=magazines/nope/nope", { ip: "9.9.9.9" }), env, T0);
check("未知 key 返回 404", missing.status === 404);
check("未知 key 不写计数", env.LINKS.writes === before, `writes=${env.LINKS.writes}`);
const noKey = await handle(req("/link", { ip: "9.9.9.9" }), env, T0);
check("缺 key 返回 400", noKey.status === 400);

console.log("\n跨域");
const pre = await handle(req(K, { method: "OPTIONS" }), env, T0);
check("预检 204 且带允许来源", pre.status === 204 && pre.headers.get("Access-Control-Allow-Origin") === ORIGIN);
const evil = await handle(req(K, { origin: "https://evil.example.com" }), env, T0);
check("陌生站点不给 CORS 头", evil.headers.get("Access-Control-Allow-Origin") === null);
check("陌生站点直接 403", evil.status === 403);
const noOrigin = await handle(req(K, { ip: "4.4.4.4", origin: null }), env, T0);
check("无 Origin 的直接请求放行（curl 调试用）", noOrigin.status === 200, `status=${noOrigin.status}`);

const health = await handle(req("/"), env, T0);
check("根路径自检可用", health.status === 200);

console.log("\n站长白名单");
const KEY = "k3J9xQ2mT7pR5vW8";
const envAdmin = { ...env, ADMIN_KEY: KEY, BYPASS_IPS: "8.8.8.8" }; // 复用同一份 KV
const w0 = env.LINKS.writes;
const withT = await handle(req(K + "&t=" + KEY, { ip: "5.5.5.5" }), envAdmin, T0);
check("带密钥取链成功", withT.status === 200 && (await withT.json()).bypass === true);
check("密钥调用不写计数", env.LINKS.writes === w0, `writes=${env.LINKS.writes}`);

const withCookie = await handle(
  new Request(`https://dl.example.com${K}`, {
    headers: { "CF-Connecting-IP": "5.5.5.5", Origin: ORIGIN, Cookie: `mg_admin=${KEY}` },
  }),
  envAdmin,
  T0
);
check("cookie 方式同样豁免", withCookie.status === 200);

const wrongT = await handle(req(K + "&t=nope", { ip: "6.6.6.6" }), envAdmin, T0);
check("错误密钥按普通访客计数", wrongT.status === 200 && env.LINKS.writes === w0 + 1, `writes=${env.LINKS.writes}`);

const byIp = await handle(req(K, { ip: "8.8.8.8" }), envAdmin, T0);
check("白名单 IP 豁免", byIp.status === 200 && (await byIp.json()).bypass === true);

const noSecret = await handle(req(K + "&t=", { ip: "7.7.7.7" }), env, T0);
check("未配置密钥时不影响普通计数", noSecret.status === 200);

/* ---------------- 热度统计（D1 内存模拟） ---------------- */
class StubDB {
  constructor() {
    this.rows = new Map(); // "day|k" -> n
    this.boom = false;
    this.writes = 0;
  }
  prepare(sql) {
    const self = this;
    const stmt = (args) => ({
      all: async () => self._all(sql, args),
      run: async () => self._run(sql, args),
    });
    return {
      bind: (...args) => stmt(args),
      ...stmt([]),
    };
  }
  async batch(list) {
    const out = [];
    for (const s of list) out.push(await s.all());
    return out;
  }
  async _run(sql, args) {
    if (this.boom) throw new Error("d1 down");
    if (sql.includes("INSERT INTO hits")) {
      const id = `${args[0]}|${args[1]}`;
      this.rows.set(id, (this.rows.get(id) || 0) + 1);
      this.writes += 1;
      return { success: true };
    }
    throw new Error("unsupported sql " + sql);
  }
  async _all(sql, args) {
    if (this.boom) throw new Error("d1 down");
    const all = [...this.rows.entries()].map(([id, n]) => {
      const [day, k] = id.split("|");
      return { day, k, n };
    });
    const from = args[0];
    if (sql.includes("GROUP BY k")) {
      const agg = new Map();
      all.filter((r) => r.day >= from).forEach((r) => agg.set(r.k, (agg.get(r.k) || 0) + r.n));
      const items = [...agg.entries()]
        .map(([k, n]) => ({ k, n }))
        .sort((a, b) => b.n - a.n || (a.k < b.k ? -1 : 1))
        .slice(0, args[1]);
      return { success: true, results: items };
    }
    if (sql.includes("GROUP BY day")) {
      const agg = new Map();
      all.filter((r) => r.day >= from).forEach((r) => agg.set(r.day, (agg.get(r.day) || 0) + r.n));
      const results = [...agg.entries()].sort((a, b) => (a[0] < b[0] ? -1 : 1)).map(([day, n]) => ({ day, n }));
      return { success: true, results };
    }
    if (sql.includes("COALESCE(SUM(n), 0)")) {
      const total = all.filter((r) => r.day >= from).reduce((s, r) => s + r.n, 0);
      return { success: true, results: [{ n: total }] };
    }
    throw new Error("unsupported sql " + sql);
  }
}

console.log("\n热度统计");
const db = new StubDB();
const envDb = { ...env, DB: db };
const before2 = env.LINKS.writes;

const h1 = await handle(req("/link?k=magazines/economist/2025-01-04-usa", { ip: "10.0.0.1" }), envDb, T0);
check("带 D1 时仍正常发链", h1.status === 200 && (await h1.json()).ok === true);
check("一次发链记 1 行统计", db.writes === 1, `writes=${db.writes}`);
check("统计不动 KV 计数之外的东西", env.LINKS.writes === before2 + 1, `writes=${env.LINKS.writes}`);

await handle(req("/link?k=magazines/economist/2025-01-04-usa", { ip: "10.0.0.2" }), envDb, T0);
await handle(req("/link?k=magazines/fhm/2025-02-canada", { ip: "10.0.0.3" }), envDb, T0);

const hot = await handle(req("/hot"), envDb, T0);
const hotBody = await hot.json();
check("热榜 200 且公开可读", hot.status === 200 && hot.headers.get("Access-Control-Allow-Origin") === "*");
check("热榜按次数排序", hotBody.items[0].k === "magazines/economist/2025-01-04-usa" && hotBody.items[0].n === 2, JSON.stringify(hotBody.items));
check("热榜带总数", hotBody.total === 3, `total=${hotBody.total}`);

const hotEmpty = await (await handle(req("/hot"), env, T0)).json();
check("没有 D1 时热榜降级为空", hotEmpty.ok === true && hotEmpty.items.length === 0);

const dbBoom = new StubDB();
dbBoom.boom = true;
const boomLink = await handle(req("/link?k=magazines/fhm/2025-02-canada", { ip: "10.0.0.9" }), { ...env, DB: dbBoom }, T0);
check("D1 挂了也不影响发链", boomLink.status === 200 && (await boomLink.json()).ok === true);
const boomHot = await (await handle(req("/hot"), { ...env, DB: dbBoom }, T0)).json();
check("D1 挂了热榜返回空而不是 500", boomHot.ok === true && boomHot.items.length === 0);

const bypassStat = await handle(req("/link?k=magazines/fhm/2025-02-canada&t=" + KEY, { ip: "10.0.0.4" }), { ...envDb, ADMIN_KEY: KEY }, T0);
check("站长豁免不记热度", bypassStat.status === 200 && db.writes === 3, `writes=${db.writes}`);

const statsNoKey = await handle(req("/stats"), envDb, T0);
check("明细接口无密钥 403", statsNoKey.status === 403);
const stats = await handle(req("/stats?t=" + KEY), { ...envDb, ADMIN_KEY: KEY }, T0);
const statsBody = await stats.json();
check("明细带按天趋势", stats.status === 200 && statsBody.daily.length === 1 && statsBody.daily[0].n === 3, JSON.stringify(statsBody.daily));

console.log(`\n结果：${pass} 通过，${fail} 失败`);
if (fail) process.exit(1);
