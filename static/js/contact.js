/* 联系邮箱渲染：页面上显示的是由片段拼出的地址，源码里没有完整邮箱。
   同时提供 mailto 链接与「复制地址」，方便没有邮件客户端的访客。 */
(function () {
  "use strict";

  function rev(s) { return String(s || "").split("").reverse().join(""); }

  function legacyCopy(t, done) {
    var ta = document.createElement("textarea");
    ta.value = t;
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand("copy"); done(); } catch (e) {}
    document.body.removeChild(ta);
  }

  function copyText(t, btn) {
    var done = function () {
      var old = btn.textContent;
      btn.textContent = "已复制";
      setTimeout(function () { btn.textContent = old; }, 1500);
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(t).then(done, function () { legacyCopy(t, done); });
    } else {
      legacyCopy(t, done);
    }
  }

  document.querySelectorAll(".mg-mail[data-mu]").forEach(function (box) {
    var addr = rev(box.dataset.mu) + String.fromCharCode(64) + rev(box.dataset.md);
    if (addr.indexOf("@") < 1) return;

    var mode = box.classList.contains("mg-mail-button") ? "button"
      : box.classList.contains("mg-mail-text") ? "text" : "inline";
    var subj = box.dataset.subject || "杂志库反馈";

    var a = document.createElement("a");
    a.className = "mg-mail-link" + (mode === "button" ? " about-btn" : "");
    a.href = "mailto:" + addr + "?subject=" + encodeURIComponent(subj);
    a.textContent = mode === "button" ? (box.dataset.label || "写邮件") + " ↗" : addr;
    box.appendChild(a);

    if ((box.dataset.copy || "1") === "1") {
      var b = document.createElement("button");
      b.type = "button";
      b.className = "mg-mail-copy mg-copy";
      b.textContent = mode === "button" ? "复制地址" : "复制";
      b.addEventListener("click", function () { copyText(addr, b); });
      box.appendChild(b);
    }

    box.style.display = "inline-flex";
  });
})();
