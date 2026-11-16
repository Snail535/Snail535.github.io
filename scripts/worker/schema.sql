-- 下载热度统计（D1）
-- 一次成功发出网盘链接记 1 行；同一天同一期只累加，不新增行。
-- 应用：wrangler d1 execute magazine_stats --remote --file=schema.sql

CREATE TABLE IF NOT EXISTS hits (
  day TEXT NOT NULL,                 -- 上海时间日期 YYYYMMDD
  k   TEXT NOT NULL,                 -- 站点里的键：<magazine_slug>-<期次文件名去后缀>
  n   INTEGER NOT NULL DEFAULT 0,    -- 当天被打开的次数
  PRIMARY KEY (day, k)
);

CREATE INDEX IF NOT EXISTS idx_hits_day ON hits (day);
CREATE INDEX IF NOT EXISTS idx_hits_k ON hits (k);

-- 邀请码（站长生成，一码可限次）与通行证（兑换后 90 天内下载不限次）
CREATE TABLE IF NOT EXISTS codes (
  code       TEXT PRIMARY KEY,          -- 邀请码（12 位，去掉易混字符的字母数字）
  uses_max   INTEGER NOT NULL DEFAULT 1, -- 最多可兑换次数（1 = 一次性）
  uses_done  INTEGER NOT NULL DEFAULT 0, -- 已兑换次数
  days       INTEGER NOT NULL DEFAULT 90, -- 兑换后通行证有效天数
  created_at INTEGER NOT NULL,          -- 生成时间（毫秒）
  note       TEXT NOT NULL DEFAULT ''   -- 备注：发给谁
);

CREATE INDEX IF NOT EXISTS idx_codes_created ON codes (created_at);

CREATE TABLE IF NOT EXISTS passes (
  pid     TEXT PRIMARY KEY,            -- 通行证 id（32 位 hex，浏览器存 localStorage）
  code    TEXT NOT NULL,               -- 由哪个邀请码兑换的
  exp     INTEGER NOT NULL,            -- 到期时间（毫秒）
  created INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_passes_exp ON passes (exp);
