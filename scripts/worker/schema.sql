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
