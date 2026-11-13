/* ==========================================================
   杂志热榜：从 Worker 的 /hot 拉公开统计数据，再用 /magindex.json
   把「刊物期次键」翻译成标题、链接、缩略图。
   设计原则：任何一步失败都安静收场——隐藏区块或留空，不发报错。
   ========================================================== */
(function () {
  "use strict";

  var MEM_TTL = 5 * 60 * 1000; // 浏览器内缓存 5 分钟，翻页来回不重复请求
  var idxCache = {};           // { url: Promise<map> }

  function cacheGet(key) {
    try {
      var raw = sessionStorage.getItem("hot:" + key);
      if (!raw) return null;
      var box = JSON.parse(raw);
      if (!box || !box.t || Date.now() - box.t > MEM_TTL) return null;
      return box.d;
    } catch (e) { return null; }
  }

  function cacheSet(key, data) {
    try { sessionStorage.setItem("hot:" + key, JSON.stringify({ t: Date.now(), d: data })); } catch (e) {}
  }

  function getJSON(url) {
    return fetch(url, { credentials: "omit", mode: "cors" }).then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    });
  }

  function hotData(api, days, n) {
    var key = api + "|" + days + "|" + n;
    var hit = cacheGet(key);
    if (hit) return Promise.resolve(hit);
    return getJSON(api + "/hot?days=" + days + "&n=" + n).then(function (d) {
      if (d && d.ok) cacheSet(key, d);
      return d || {};
    });
  }

  function issueMap(url) {
    if (!idxCache[url]) {
      idxCache[url] = getJSON(url).then(function (rows) {
        var map = {};
        (rows || []).forEach(function (r) { if (r && r[0]) map[r[0]] = r; });
        return map;
      });
    }
    return idxCache[url];
  }

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }

  function stamp(iso) {
    var t = Date.parse(iso || "");
    if (!t) return "";
    var diff = Date.now() - t;
    if (diff < 60 * 1000) return "刚刚更新";
    if (diff < 60 * 60 * 1000) return Math.round(diff / 60000) + " 分钟前更新";
    var d = new Date(t + 8 * 3600 * 1000);
    return d.getUTCHours() + ":" + String(d.getUTCMinutes()).padStart(2, "0") + " 更新";
  }

  function buildItem(row, n) {
    var k = row[0], title = row[1], url = row[2], cover = row[3], mag = row[4] || "";
    var hits = row[5];
    var a = el("a", "hot-item");
    a.href = url;

    var rank = el("span", "hot-rank", String(n));
    a.appendChild(rank);

    var thumb = el("span", "hot-thumb");
    if (cover) {
      var img = el("img");
      img.src = cover;
      img.alt = title;
      img.loading = "lazy";
      img.decoding = "async";
      thumb.appendChild(img);
    }
    a.appendChild(thumb);

    var info = el("span", "hot-info");
    info.appendChild(el("span", "hot-title", title));
    var meta = el("span", "hot-meta");
    meta.appendChild(el("span", "hot-mag", mag));
    meta.appendChild(el("b", "hot-n", hits + " 次"));
    info.appendChild(meta);
    a.appendChild(info);
    return a;
  }

  function paint(panel, data, map) {
    var n = parseInt(panel.dataset.n, 10) || 10;
    var list = (data.items || []).filter(function (it) { return it && map[it.k]; });
    var box = panel.querySelector("[data-hot-list]");
    var sumEl = panel.querySelector("[data-hot-summary]");
    if (!box) return;

    box.textContent = "";
    if (!list.length) {
      panel.classList.add("is-empty");
      if (panel.dataset.hideOnEmpty === "1") panel.hidden = true;
      if (sumEl) sumEl.textContent = "";
      return;
    }

    var top = list.slice(0, n);
    top.forEach(function (it, i) {
      var row = map[it.k].concat([it.n]);
      box.appendChild(buildItem(row, i + 1));
    });

    if (sumEl) {
      var parts = [];
      if (data.total) parts.push("近 " + (data.days || 7) + " 天共 " + data.total + " 次打开");
      var s = stamp(data.updated);
      if (s) parts.push(s);
      sumEl.textContent = parts.join(" · ");
    }
  }

  function bootPanel(panel) {
    var api = (panel.dataset.api || "").replace(/\/+$/, "");
    var idx = panel.dataset.index || "";
    var days = parseInt(panel.dataset.days, 10) || 7;
    var n = parseInt(panel.dataset.n, 10) || 10;
    if (!api || !idx) { panel.hidden = true; return; }

    Promise.all([hotData(api, days, n), issueMap(idx)])
      .then(function (res) { paint(panel, res[0], res[1]); })
      .catch(function () {
        panel.classList.add("is-empty");
        if (panel.dataset.hideOnEmpty === "1") panel.hidden = true;
        else {
          var sumEl = panel.querySelector("[data-hot-summary]");
          if (sumEl) sumEl.textContent = "热榜暂时拉取不到，稍后再看";
        }
      });
  }

  function bootBadge(badge) {
    var api = (badge.dataset.api || "").replace(/\/+$/, "");
    var key = badge.dataset.hotKey || "";
    if (!api || !key) return;
    hotData(api, 7, 30).then(function (data) {
      var items = data.items || [];
      for (var i = 0; i < items.length; i += 1) {
        if (items[i].k === key) {
          badge.textContent = "本周热榜第 " + (i + 1) + " 位 · " + items[i].n + " 次打开";
          badge.hidden = false;
          badge.classList.add("is-hot");
          if (i < 3) badge.classList.add("is-top" + (i + 1));
          return;
        }
      }
    }).catch(function () {});
  }

  function boot() {
    Array.prototype.forEach.call(document.querySelectorAll("[data-hot-panel]"), bootPanel);
    Array.prototype.forEach.call(document.querySelectorAll("[data-hot-key]"), bootBadge);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
