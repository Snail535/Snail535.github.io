#!/usr/bin/env bash
# 部署 magazine-links Worker（含热榜统计）
#
# 用法：
#   scripts/worker/deploy.sh            # 用 scripts/.cf_token 里的 token
#   CLOUDFLARE_API_TOKEN=xxx scripts/worker/deploy.sh
#
# 做的事情：
#   1. wrangler.toml 里 database_id 还是 TO_BE_FILLED 时，创建 D1 库 magazine_stats 并写回 id
#   2. 建表（schema.sql）
#   3. 部署 Worker
#   4. 打一下 /hot 看是否通
#
# 需要的 token 权限（2026 年新版 Policies 界面）：
#   Developer Platform 分组下 Workers / Workers KV Storage / D1 都是
#   「Read / Edit」二选一，选 Edit；D1 选了 Edit 才有建库建表权限。
#   另有 Zone 相关编辑权限（DNS / Workers Routes 等）。
# 控制台路径：My Profile → API Tokens → 编辑现有 token → Policies →
#   Search for permission groups 输入 D1 → 在 D1 行点 Edit →
#   Continue to summary → 保存。旧版「Account / D1 / Edit 三下拉」已失效。
# 注意：本站统计明细还需要 secret ADMIN_KEY（见 scripts/.admin_key，不进仓库），
#   用 `wrangler secret put ADMIN_KEY` 写入，否则 /stats 一律 403。

set -euo pipefail
cd "$(dirname "$0")"

if [[ -z "${CLOUDFLARE_API_TOKEN:-}" ]]; then
  if [[ -f ../.cf_token ]]; then
    CLOUDFLARE_API_TOKEN=$(tr -d '\r\n' < ../.cf_token)
    export CLOUDFLARE_API_TOKEN
  else
    echo "缺少 token：写进 scripts/.cf_token，或用 CLOUDFLARE_API_TOKEN 环境变量传入" >&2
    exit 1
  fi
fi

WRANGLER="npx --yes wrangler@4"

if grep -q 'TO_BE_FILLED' wrangler.toml; then
  echo "==> 创建 D1 数据库 magazine_stats"
  out=$($WRANGLER d1 create magazine_stats 2>&1) || { echo "$out" >&2; exit 1; }
  echo "$out"
  dbid=$(printf '%s\n' "$out" | grep -oE '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}' | head -1)
  if [[ -z "$dbid" ]]; then
    echo "没能从 wrangler 输出里解析出 database_id，请手动填进 wrangler.toml" >&2
    exit 1
  fi
  # 已有同名的库时 wrangler 会报错，此时用 d1 list 找回来
  CLOUDFLARE_API_TOKEN=$CLOUDFLARE_API_TOKEN
  sed -i.bak "s/TO_BE_FILLED/$dbid/" wrangler.toml && rm -f wrangler.toml.bak
  echo "==> database_id = $dbid"
else
  echo "==> D1 已配置，跳过创建"
fi

echo "==> 建表"
$WRANGLER d1 execute magazine_stats --remote --file=schema.sql -y

echo "==> 部署 Worker"
$WRANGLER deploy

echo "==> 自检 /hot"
sleep 3
curl -s -m 15 "https://dl.xinyesucai.top/hot?n=5" | head -c 400
echo
