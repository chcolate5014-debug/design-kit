/* ==========================================================================
   Flask 공통 UI 키트 — kit.js (의존성 없음)
   - 모든 부품은 data-kit-* 속성으로 자동 초기화된다. 해당 요소가 없으면 조용히 건너뛴다.
   - 부품마다 따로 초기화(try/catch)하므로 한 부품의 오류가 다른 부품을 멈추지 않는다.
   - 데이터 문자열은 innerHTML 에 넣지 않는다. Kit.el() / textContent 만 사용한다.

   공개 API
     Kit.toast(message, status?, ms?)   status: success|warning|danger|info|neutral
     Kit.el(tag, attrs?, text?)          안전한 요소 생성 (text 는 textContent 로 들어감)
     Kit.readJSON(elOrId)                <script type="application/json"> 읽기
     Kit.token("--accent")               CSS 토큰 값 읽기
     Kit.postJSON(url, body)             JSON POST (meta[name=csrf-token] 이 있으면 X-CSRFToken 헤더 추가)
     Kit.register(name, initFn)          선택 부품 등록 (DOM 준비 후 1회 실행)
   ========================================================================== */
(function () {
  "use strict";
  document.documentElement.classList.add("kit-js");

  var STATUSES = ["success", "warning", "danger", "info", "neutral"];
  var inits = [];
  var ready = false;

  function register(name, fn) {
    if (ready) run(name, fn); else inits.push([name, fn]);
  }
  function run(name, fn) {
    try { fn(document); }
    catch (err) { if (window.console) console.error("[kit] " + name + " 초기화 실패:", err); }
  }
  function boot() {
    ready = true;
    inits.forEach(function (it) { run(it[0], it[1]); });
    inits = [];
  }

  /* ---------- 도우미 ---------- */
  function el(tag, attrs, text) {
    var node = document.createElement(tag);
    if (attrs) Object.keys(attrs).forEach(function (k) {
      var v = attrs[k];
      if (v == null || v === false) return;
      if (k === "className") node.className = v;
      else node.setAttribute(k, v === true ? "" : String(v));
    });
    if (text != null) node.textContent = String(text);
    return node;
  }
  function readJSON(ref) {
    var node = typeof ref === "string" ? document.getElementById(ref) : ref;
    if (!node) return null;
    try { return JSON.parse(node.textContent || "null"); }
    catch (err) { if (window.console) console.error("[kit] JSON 파싱 실패:", err); return null; }
  }
  function token(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }
  function status(s) { return STATUSES.indexOf(s) >= 0 ? s : "neutral"; }
  function postJSON(url, body) {
    var headers = { "Content-Type": "application/json", "Accept": "application/json" };
    var csrf = document.querySelector('meta[name="csrf-token"]');
    if (csrf && csrf.content) headers["X-CSRFToken"] = csrf.content;
    return fetch(url, { method: "POST", headers: headers, body: JSON.stringify(body), credentials: "same-origin" });
  }

  /* ---------- 토스트 (aria-live) ---------- */
  function toast(message, st, ms) {
    var region = document.getElementById("kit-toasts");
    if (!region) {
      region = el("div", { id: "kit-toasts", className: "toast-region", "aria-live": "polite" });
      document.body.appendChild(region);
    }
    var t = el("div", { className: "toast " + status(st || "neutral") }, message);
    if (st === "danger") t.setAttribute("role", "alert");
    region.appendChild(t);
    requestAnimationFrame(function () { t.classList.add("is-show"); });
    setTimeout(function () {
      t.classList.remove("is-show");
      setTimeout(function () { if (t.parentNode) t.parentNode.removeChild(t); }, 250);
    }, ms || (st === "danger" ? 5000 : 2600));
    return t;
  }

  /* ---------- 좁은 화면 메뉴 접기 ---------- */
  register("nav", function (root) {
    var btn = root.querySelector("[data-kit-nav-toggle]");
    if (!btn) return;
    var nav = document.getElementById(btn.getAttribute("aria-controls"));
    if (!nav) return;
    btn.addEventListener("click", function () {
      var open = !nav.classList.contains("is-open");
      nav.classList.toggle("is-open", open);
      btn.setAttribute("aria-expanded", open ? "true" : "false");
    });
  });

  /* ---------- 알림 배너 닫기: <div class="alert" data-kit-dismissible> ---------- */
  register("alert", function (root) {
    root.querySelectorAll(".alert[data-kit-dismissible]").forEach(function (box) {
      var b = el("button", { type: "button", className: "alert-close", "aria-label": "알림 닫기" }, "×");
      b.addEventListener("click", function () { box.parentNode.removeChild(box); });
      box.appendChild(b);
    });
  });

  /* ---------- 테이블 정렬 ----------
     <table class="table" data-kit-sort>
       <th data-sort="id|text|number|date">LOT ID</th>
     셀에 data-sort-value 가 있으면 그 값을 기준으로 정렬한다. */
  var collatorId = new Intl.Collator("ko", { numeric: true, sensitivity: "base" });
  var collatorText = new Intl.Collator("ko", { sensitivity: "base" });

  function cellValue(row, idx) {
    var c = row.cells[idx];
    if (!c) return "";
    return (c.hasAttribute("data-sort-value") ? c.getAttribute("data-sort-value") : c.textContent).trim();
  }
  function toNumber(s) {
    var n = parseFloat(String(s).replace(/[,\s%]/g, ""));
    return isNaN(n) ? null : n;
  }
  function toDate(s) {
    if (!s) return null;
    var t = Date.parse(String(s).replace(" ", "T").replace(/\./g, "-"));
    return isNaN(t) ? null : t;
  }
  function key(type, s) {             // 비교용 값. 빈 값(또는 해석 불가)은 null
    if (type === "number") return toNumber(s);
    if (type === "date") return toDate(s);
    return s === "" || s === "-" ? null : s;
  }
  function compare(type, x, y) {
    if (type === "number" || type === "date") return x - y;
    return (type === "id" ? collatorId : collatorText).compare(x, y);
  }

  register("sort", function (root) {
    root.querySelectorAll("table[data-kit-sort]").forEach(function (table) {
      var ths = table.querySelectorAll("thead th[data-sort]");
      ths.forEach(function (th) {
        var type = th.getAttribute("data-sort") || "text";
        var btn = el("button", { type: "button", className: "sort-btn" });
        while (th.firstChild) btn.appendChild(th.firstChild);
        btn.appendChild(el("span", { className: "sort-icon", "aria-hidden": "true" }));
        th.appendChild(btn);

        btn.addEventListener("click", function () {
          var dir = th.getAttribute("aria-sort") === "ascending" ? "descending" : "ascending";
          ths.forEach(function (o) { o.removeAttribute("aria-sort"); });
          th.setAttribute("aria-sort", dir);
          var idx = th.cellIndex;
          var tb = table.tBodies[0];
          if (!tb) return;
          var rows = Array.prototype.slice.call(tb.rows);
          var fixed = rows.filter(function (r) { return r.querySelector(".empty-cell"); });
          var data = rows.filter(function (r) { return !r.querySelector(".empty-cell"); })
            .map(function (r, i) { return { r: r, i: i, k: key(type, cellValue(r, idx)) }; });
          data.sort(function (a, b) {
            if (a.k === null || b.k === null) {            // 빈 값은 정렬 방향과 관계없이 맨 뒤
              return (a.k === null) - (b.k === null) || a.i - b.i;
            }
            var res = compare(type, a.k, b.k);
            if (dir === "descending") res = -res;
            return res || a.i - b.i;
          });
          var frag = document.createDocumentFragment();
          data.forEach(function (d) { frag.appendChild(d.r); });
          fixed.forEach(function (r) { frag.appendChild(r); });
          tb.appendChild(frag);
        });
      });
    });
  });

  /* ---------- 탭 ----------
     <div data-kit-tabs>
       <div class="tabs"><button class="tab" type="button" aria-controls="p1">기본</button>...</div>
       <section class="tab-panel" id="p1">...</section>
     처음 선택할 탭은 aria-selected="true" 로 표시 (없으면 첫 탭) */
  var tabSeq = 0;
  register("tabs", function (root) {
    root.querySelectorAll("[data-kit-tabs]").forEach(function (box) {
      var list = box.querySelector(".tabs");
      if (!list) return;
      var tabs = Array.prototype.slice.call(list.querySelectorAll(".tab[aria-controls]"));
      if (!tabs.length) return;
      list.setAttribute("role", "tablist");
      tabs.forEach(function (t) {
        if (!t.id) t.id = "kit-tab-" + (++tabSeq);
        t.setAttribute("role", "tab");
        var p = document.getElementById(t.getAttribute("aria-controls"));
        if (p) { p.setAttribute("role", "tabpanel"); p.setAttribute("aria-labelledby", t.id); p.setAttribute("tabindex", "0"); }
      });
      function select(tab, focus) {
        tabs.forEach(function (t) {
          var on = t === tab;
          t.setAttribute("aria-selected", on ? "true" : "false");
          t.setAttribute("tabindex", on ? "0" : "-1");
          var p = document.getElementById(t.getAttribute("aria-controls"));
          if (p) p.hidden = !on;
        });
        if (focus) tab.focus();
      }
      var initial = tabs.filter(function (t) { return t.getAttribute("aria-selected") === "true"; })[0] || tabs[0];
      select(initial, false);
      tabs.forEach(function (t, i) {
        t.addEventListener("click", function () { select(t, false); });
        t.addEventListener("keydown", function (e) {
          var n = null;
          if (e.key === "ArrowRight") n = tabs[(i + 1) % tabs.length];
          else if (e.key === "ArrowLeft") n = tabs[(i - 1 + tabs.length) % tabs.length];
          else if (e.key === "Home") n = tabs[0];
          else if (e.key === "End") n = tabs[tabs.length - 1];
          if (n) { e.preventDefault(); select(n, true); }
        });
      });
    });
  });

  /* ---------- 모달 ----------
     <button type="button" data-kit-modal-open="m1">열기</button>
     <dialog class="modal" id="m1" aria-labelledby="m1-title"> ... <button data-kit-modal-close>닫기</button></dialog>
     Esc 로 닫힘, 열려 있는 동안 Tab 포커스가 모달 안에서만 돈다, 닫으면 연 버튼으로 포커스 복귀. */
  var FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';
  register("modal", function (root) {
    root.querySelectorAll("[data-kit-modal-open]").forEach(function (opener) {
      var dlg = document.getElementById(opener.getAttribute("data-kit-modal-open"));
      if (!dlg || typeof dlg.showModal !== "function") return;
      opener.setAttribute("aria-haspopup", "dialog");
      opener.addEventListener("click", function () {
        dlg._kitOpener = opener;
        dlg.showModal();
        var first = dlg.querySelector("[autofocus]") || dlg.querySelector(FOCUSABLE);
        if (first) first.focus();
      });
    });
    root.querySelectorAll("dialog.modal").forEach(function (dlg) {
      if (dlg._kitBound) return;
      dlg._kitBound = true;
      dlg.addEventListener("click", function (e) {
        if (e.target.closest("[data-kit-modal-close]")) { dlg.close(); return; }
        if (e.target === dlg) {            // 배경(backdrop) 클릭
          var r = dlg.getBoundingClientRect();
          if (e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom) dlg.close();
        }
      });
      dlg.addEventListener("keydown", function (e) {
        if (e.key !== "Tab") return;
        var f = Array.prototype.filter.call(dlg.querySelectorAll(FOCUSABLE), function (n) { return n.offsetParent !== null; });
        if (!f.length) { e.preventDefault(); return; }
        var first = f[0], last = f[f.length - 1];
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
      });
      dlg.addEventListener("close", function () {
        if (dlg._kitOpener) dlg._kitOpener.focus();
      });
    });
  });

  /* ---------- 서버가 넘긴 토스트: <div data-kit-toast="저장했습니다" data-kit-toast-status="success" hidden> ---------- */
  register("flash", function (root) {
    root.querySelectorAll("[data-kit-toast]").forEach(function (n) {
      toast(n.getAttribute("data-kit-toast"), n.getAttribute("data-kit-toast-status") || "info");
    });
  });

  /* ---------- 차트 안전망: kit-chart.js 자체가 로드되지 않아도 빈 상자로 남지 않게 ---------- */
  window.addEventListener("load", function () {
    document.querySelectorAll("[data-kit-chart]:not([data-kit-chart-state])").forEach(function (box) {
      box.setAttribute("data-kit-chart-state", "error");
      var m = el("div", { className: "chart-msg is-error", role: "alert" });
      m.appendChild(el("strong", null, "차트를 불러오지 못했습니다"));
      m.appendChild(el("span", null, "차트 스크립트가 로드되지 않았습니다. 다른 기능은 그대로 사용할 수 있습니다."));
      box.appendChild(m);
    });
  });

  window.Kit = {
    toast: toast, el: el, readJSON: readJSON, token: token,
    status: status, postJSON: postJSON, register: register
  };

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
