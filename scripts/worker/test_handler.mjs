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

console.log(`\n结果：${pass} 通过，${fail} 失败`);
if (fail) process.exit(1);
