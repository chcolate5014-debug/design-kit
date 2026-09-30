/* ==========================================================================
   Flask 공통 UI 키트 — kit-chart.js  (Chart.js v4 공통 테마 + 자동 초기화)
   로드 순서: kit.js → chart.umd.min.js → kit-chart.js   ({{ kit.scripts("chart") }} 가 처리)

   - 색은 kit.css 토큰(getComputedStyle)에서만 읽는다. 이 파일에 색 값을 쓰지 않는다.
   - 페이지는 차트 옵션을 직접 쓰지 않고, 아래 "차트 명세(JSON)"만 넘긴다.
       {{ kit.chart("상태 분포", spec) }}                 → 명세를 페이지에 포함
       {{ kit.chart("추이", src=url_for("api_trend")) }}   → 명세를 URL에서 받아옴 (로딩·실패 안내 포함)

   차트 명세
   {
     "type": "bar" | "line" | "doughnut",
     "labels": ["1주", "2주", ...],
     "series": [
       { "label": "정상", "data": [3, 5, ...],
         "color": "series-1".."series-6" | "success"|"warning"|"danger"|"info"|"neutral" | "accent",
         "colors": ["success", "warning", ...],   // doughnut: 조각별 색
         "dashed": true,                          // line: 목표선 등 점선
         "fill": true }                           // line: 아래 면 채움
     ],
     "horizontal": false, "stacked": false,       // bar
     "unit": "%", "min": 0, "max": 100,           // 값 축
     "legend": "bottom" | "right" | false
   }
   "데이터 없음" 안내: series 가 비었거나 값이 모두 null 일 때 (doughnut 은 모두 0 일 때도)
   ========================================================================== */
(function () {
  "use strict";
  if (!window.Kit) return;

  var NAMED = ["success", "warning", "danger", "info", "neutral"];

  function tok(name) { return window.Kit.token(name); }
  function color(key, i) {
    if (!key) return tok("--series-" + ((i % 6) + 1));
    if (NAMED.indexOf(key) >= 0) return tok("--st-" + key);
    if (key === "accent") return tok("--accent");
    if (/^series-[1-6]$/.test(key)) return tok("--" + key);
    return tok("--st-neutral");                       // 알 수 없는 값은 중립색
  }
  function withAlpha(c, a) {                          // 토큰 hex → rgba
    var h = String(c).replace("#", "");
    if (h.length === 3) h = h.replace(/(.)/g, "$1$1");
    if (!/^[0-9a-fA-F]{6}$/.test(h)) return c;
    return "rgba(" + parseInt(h.slice(0, 2), 16) + "," + parseInt(h.slice(2, 4), 16) + "," + parseInt(h.slice(4, 6), 16) + "," + a + ")";
  }

  function message(box, state, title, desc) {
    var old = box.querySelector(".chart-msg");
    if (old) old.parentNode.removeChild(old);
    box.setAttribute("data-kit-chart-state", state);
    if (!title) return;
    var m = window.Kit.el("div", { className: "chart-msg" + (state === "error" ? " is-error" : ""), role: state === "error" ? "alert" : "status" });
    if (state === "loading") m.appendChild(window.Kit.el("span", { className: "spinner", "aria-hidden": "true" }));
    m.appendChild(window.Kit.el("strong", null, title));
    if (desc) m.appendChild(window.Kit.el("span", null, desc));
    box.appendChild(m);
  }

  function isEmpty(spec) {
    if (!spec || !Array.isArray(spec.series) || !spec.series.length) return true;
    var zeroIsEmpty = spec.type === "doughnut";           // 도넛은 모두 0이면 그릴 것이 없음
    return !spec.series.some(function (s) {
      return Array.isArray(s.data) && s.data.some(function (v) {
        return v !== null && v !== undefined && v !== "" && !(zeroIsEmpty && Number(v) === 0);
      });
    });
  }

  function fmt(v, unit) {
    if (v === null || v === undefined) return "-";
    var n = typeof v === "number" ? v.toLocaleString("ko-KR", { maximumFractionDigits: 2 }) : String(v);
    return unit ? n + unit : n;
  }

  function build(spec) {
    var type = spec.type === "line" || spec.type === "doughnut" ? spec.type : "bar";
    var ink2 = tok("--ink-2"), ink3 = tok("--ink-3"), line = tok("--line"), surface = tok("--surface");
    var unit = spec.unit || "";

    var datasets = spec.series.map(function (s, i) {
      var c = color(s.color, i);
      var d = { label: s.label || "", data: s.data || [] };
      if (type === "doughnut") {
        var cs = (s.colors || []).map(function (k, j) { return color(k, j); });
        d.backgroundColor = cs.length ? cs : d.data.map(function (_, j) { return color(null, j); });
        d.borderColor = surface; d.borderWidth = 2;
      } else if (type === "line") {
        d.borderColor = c; d.backgroundColor = s.fill ? withAlpha(c, 0.1) : c;
        d.fill = !!s.fill; d.borderWidth = s.dashed ? 1.5 : 2; d.tension = 0.25;
        d.pointRadius = s.dashed ? 0 : 2.5; d.pointHoverRadius = 4; d.pointBackgroundColor = c;
        if (s.dashed) d.borderDash = [4, 4];
      } else {
        d.backgroundColor = c; d.borderRadius = 2; d.maxBarThickness = 28;
      }
      return d;
    });

    var legendPos = spec.legend === false ? false : (spec.legend === "right" ? "right" : "bottom");
    var showLegend = legendPos !== false && (type === "doughnut" || datasets.length > 1);

    var options = {
      responsive: true, maintainAspectRatio: false,
      animation: window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches ? false : { duration: 250 },
      plugins: {
        legend: {
          display: showLegend, position: legendPos || "bottom", align: "start",
          labels: { color: ink2, boxWidth: 10, boxHeight: 10, padding: 12 }
        },
        tooltip: {
          backgroundColor: tok("--topbar-bg"), titleColor: tok("--ink-inverse"), bodyColor: tok("--topbar-ink"),
          padding: 8, cornerRadius: 3, boxPadding: 4, mode: type === "doughnut" ? "nearest" : "index", intersect: type === "doughnut",
          callbacks: {
            label: function (ctx) {
              var v = type === "doughnut" ? ctx.parsed : (spec.horizontal ? ctx.parsed.x : ctx.parsed.y);
              var name = type === "doughnut" ? ctx.label : ctx.dataset.label;
              return (name ? name + ": " : "") + fmt(v, unit);
            }
          }
        }
      }
    };
    if (type === "doughnut") {
      options.cutout = "64%";
    } else {
      var valueAxis = {
        stacked: !!spec.stacked, beginAtZero: spec.min == null,
        grid: { color: line }, border: { display: false },
        ticks: { color: ink3, callback: function (v) { return fmt(v, unit); } }
      };
      if (spec.min != null) valueAxis.min = spec.min;
      if (spec.max != null) valueAxis.max = spec.max;
      var catAxis = { stacked: !!spec.stacked, grid: { display: false }, border: { color: line }, ticks: { color: ink3 } };
      options.scales = spec.horizontal ? { x: valueAxis, y: catAxis } : { x: catAxis, y: valueAxis };
      if (spec.horizontal) options.indexAxis = "y";
    }
    return { type: type, data: { labels: spec.labels || [], datasets: datasets }, options: options };
  }

  function render(box, spec) {
    if (typeof window.Chart === "undefined") {
      message(box, "error", "차트를 불러오지 못했습니다", "차트 파일(static/kit/vendor/chart.umd.min.js)이 없거나 로드되지 않았습니다.");
      return;
    }
    if (isEmpty(spec)) { message(box, "empty", "표시할 데이터가 없습니다", "조회 조건을 바꿔 보세요."); return; }
    message(box, "ready");
    var canvas = box.querySelector("canvas") || box.appendChild(window.Kit.el("canvas"));
    try {
      if (box._kitChart) box._kitChart.destroy();
      box._kitChart = new window.Chart(canvas, build(spec));
    } catch (err) {
      if (window.console) console.error("[kit-chart]", err);
      message(box, "error", "차트를 그리지 못했습니다", "차트 명세를 확인하세요.");
    }
  }

  function init(box) {
    var src = box.getAttribute("data-kit-chart-src");
    if (src) {
      message(box, "loading", "불러오는 중입니다");
      fetch(src, { headers: { "Accept": "application/json" }, credentials: "same-origin" })
        .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
        .then(function (spec) { render(box, spec); })
        .catch(function (err) {
          if (window.console) console.error("[kit-chart]", err);
          message(box, "error", "데이터를 불러오지 못했습니다", "잠시 후 새로고침해 보세요.");
        });
      return;
    }
    render(box, window.Kit.readJSON(box.querySelector('script[type="application/json"]')));
  }

  if (typeof window.Chart !== "undefined" && window.Chart.defaults) {
    window.Chart.defaults.font.family = tok("--font");
    window.Chart.defaults.font.size = 12;
    window.Chart.defaults.color = tok("--ink-2");
    window.Chart.defaults.borderColor = tok("--line");
  }

  window.Kit.chart = { build: build, render: render, color: color };
  window.Kit.register("chart", function (root) {
    root.querySelectorAll("[data-kit-chart]").forEach(function (box) {
      try { init(box); }
      catch (err) { message(box, "error", "차트를 불러오지 못했습니다", ""); }
    });
  });
})();
