/* 通行证页：读 localStorage 里的通行证（详情页脚本也用同一份），
   兑换邀请码走 Worker 的 /redeem，状态查询走 /pass。 */
(function () {
  "use strict";

  var KEY = "mgPass";

  var card = document.querySelector("[data-pass]");
  if (!card) return;
  var api = (card.dataset.api || "").replace(/\/+$/, "");
  var total = parseInt(card.dataset.limit, 10) || 3;
  var statusEl = card.querySelector('[data-role="status"]');
  var formEl = card.querySelector('[data-role="form"]');
  var inputEl = card.querySelector('[data-role="input"]');
  var redeemBtn = card.querySelector('[data-role="redeem"]');
  var okEl = card.querySelector('[data-role="ok"]');

  function readPass() {
    try {
      var p = JSON.parse(localStorage.getItem(KEY) || "null");
      if (p && p.pid && p.exp > Date.now()) return p;
    } catch (e) {}
    return null;
  }

  function savePass(pid, exp) {
    try { localStorage.setItem(KEY, JSON.stringify({ pid: pid, exp: exp })); } catch (e) {}
  }

  function clearPass() {
    try { localStorage.removeItem(KEY); } catch (e) {}
  }

  function fmtDate(ms) {
    var d = new Date(ms + 8 * 3600 * 1000);
    return d.getUTCFullYear() + " 年 " + (d.getUTCMonth() + 1) + " 月 " + d.getUTCDate() + " 日";
  }

  function getJSON(url) {
    return fetch(url, { credentials: "omit" }).then(function (r) {
      return r.json().then(function (b) { return { status: r.status, body: b }; });
    });
  }

  function showGuest(msg) {
    statusEl.textContent = msg || ("当前身份：游客 · 每天最多 " + total + " 次下载入口");
    statusEl.classList.remove("is-ok");
    formEl.hidden = false;
    okEl.hidden = true;
  }

  function showOk(exp) {
    statusEl.textContent = "通行证有效";
    statusEl.classList.add("is-ok");
    formEl.hidden = true;
    okEl.hidden = false;
    card.querySelector('[data-role="exp"]').textContent = fmtDate(exp);
  }

  function check(pass) {
    if (!api) { showGuest("接口未配置，兑换暂不可用"); return; }
    getJSON(api + "/pass?p=" + encodeURIComponent(pass.pid)).then(function (res) {
      var b = res.body || {};
      if (b.valid) showOk(pass.exp);
      else { clearPass(); showGuest("通行证已过期或被撤销，可以重新兑换"); }
    }).catch(function () {
      // 接口查不到状态时按本地记录显示，别把人拦在外面
      showOk(pass.exp);
    });
  }

  function onRedeem() {
    var code = (inputEl.value || "").trim().toUpperCase();
    if (!code) { inputEl.focus(); return; }
    redeemBtn.disabled = true;
    redeemBtn.textContent = "兑换中…";
    getJSON(api + "/redeem?code=" + encodeURIComponent(code)).then(function (res) {
      var b = res.body || {};
      if (b.ok && b.pid) {
        savePass(b.pid, b.exp);
        showOk(b.exp);
        return;
      }
      var msg = b.message || "兑换失败，请检查邀请码";
      statusEl.textContent = msg;
      statusEl.classList.remove("is-ok");
      redeemBtn.disabled = false;
      redeemBtn.textContent = "兑换";
      inputEl.select();
    }).catch(function () {
      statusEl.textContent = "网络异常，请稍后再试";
      redeemBtn.disabled = false;
      redeemBtn.textContent = "兑换";
    });
  }

  redeemBtn.addEventListener("click", onRedeem);
  inputEl.addEventListener("keydown", function (e) {
    if (e.key === "Enter") onRedeem();
  });

  var mine = readPass();
  if (mine) check(mine);
  else showGuest();
})();
