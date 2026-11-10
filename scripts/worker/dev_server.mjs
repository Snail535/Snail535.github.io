// 本地模拟 Worker：node scripts/worker/dev_server.mjs [port]
// 用内存 KV 加载 scripts/.links_kv.json，验证前端与接口的联调行为。
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { handle } from "./handler.js";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "../..");
const port = Number(process.argv[2] || 8787);

class MemoryKV {
  constructor() {
    this.map = new Map();
  }
  async get(key, opts) {
    const v = this.map.get(key);
    if (v === undefined) return null;
    if (opts && opts.type === "json") return JSON.parse(v);
    return v;
  }
  async put(key, value) {
    this.map.set(key, value);
  }
}

const env = {
  LINKS: new MemoryKV(),
  DAILY_LIMIT: "5",
  ALLOWED_ORIGINS: "http://127.0.0.1:8099,http://localhost:8099,http://127.0.0.1:8787",
};

const linksFile = path.join(root, "scripts/.links_kv.json");
const links = JSON.parse(fs.readFileSync(linksFile, "utf-8"));
for (const [k, v] of Object.entries(links)) {
  await env.LINKS.put(`i:${k}`, JSON.stringify(v));
}
console.log(`已加载 ${Object.keys(links).length} 条链接`);

http
  .createServer(async (req, res) => {
    const url = `http://127.0.0.1:${port}${req.url}`;
    const headers = new Headers();
    for (const [k, v] of Object.entries(req.headers)) {
      if (typeof v === "string") headers.set(k, v);
    }
    const request = new Request(url, { method: req.method, headers });
    const response = await handle(request, env);
    res.writeHead(response.status, Object.fromEntries(response.headers));
    res.end(Buffer.from(await response.arrayBuffer()));
  })
  .listen(port, "127.0.0.1", () => {
    console.log(`dev worker: http://127.0.0.1:${port}`);
  });
