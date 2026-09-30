/* ==========================================================================
   선택 부품 — 히트맵 (라이브러리 불필요)
   로드: {{ kit.scripts("heatmap") }}   (kit.js 다음)

   <div data-kit-heatmap="auto-rate" aria-label="Step별 요일 자동화율"></div>
   {{ kit.data("auto-rate", heat) }}

   heat = { "rows": ["Bump", ...], "cols": ["월", ...], "values": [[92, 88, null, ...], ...],
            "min": 60, "max": 100, "unit": "%", "decimals": 0 }
   색은 kit.css 토큰 --heat-low / --heat-mid / --heat-high 에서 읽는다. null 은 빈 칸.
   ========================================================================== */
(function () {
  "use strict";
  if (!window.Kit) return;
  var K = window.Kit;

  function rgb(hex) {
    var h = String(hex).replace("#", "");
    if (h.length === 3) h = h.replace(/(.)/g, "$1$1");
    return [0, 2, 4].map(function (i) { return parseInt(h.substr(i, 2), 16) || 0; });
  }
  function mix(a, b, t) { return a.map(function (v, i) { return Math.round(v + (b[i] - v) * t); }); }

  function render(box, o) {
    while (box.firstChild) box.removeChild(box.firstChild);
    if (!o || !Array.isArray(o.rows) || !Array.isArray(o.cols) || !Array.isArray(o.values)) {
      var err = K.el("div", { className: "error-state", role: "alert" });
      err.appendChild(K.el("strong", { className: "empty-title" }, "히트맵 데이터를 읽지 못했습니다"));
      box.appendChild(err);
      return;
    }
    var stops = [rgb(K.token("--heat-low")), rgb(K.token("--heat-mid")), rgb(K.token("--heat-high"))];
    var min = typeof o.min === "number" ? o.min : 0;
    var max = typeof o.max === "number" && o.max > min ? o.max : min + 100;
    var unit = o.unit || "";
    var dec = Math.max(0, Math.min(3, parseInt(o.decimals, 10) || 0));
    var fmt = function (v) { return Number(v).toFixed(dec) + unit; };

    var scroll = K.el("div", { className: "heatmap-scroll" });
    var grid = K.el("div", { className: "heatmap", role: "group", "aria-label": box.getAttribute("aria-label") || "히트맵" });
    grid.style.gridTemplateColumns = "max-content repeat(" + o.cols.length + ", minmax(32px, 1fr))";
    grid.appendChild(K.el("div"));
    o.cols.forEach(function (c) { grid.appendChild(K.el("div", { className: "heatmap-head" }, c)); });

    o.rows.forEach(function (r, i) {
      grid.appendChild(K.el("div", { className: "heatmap-row-label" }, r));
      o.cols.forEach(function (c, j) {
        var v = (o.values[i] || [])[j];
        var label = r + " · " + c + ": " + (typeof v === "number" ? fmt(v) : "데이터 없음");
        var cell = K.el("div", { className: "heatmap-cell", title: label, role: "img", "aria-label": label });
        if (typeof v === "number" && isFinite(v)) {
          var t = Math.max(0, Math.min(1, (v - min) / (max - min)));
          var col = t < 0.5 ? mix(stops[0], stops[1], t * 2) : mix(stops[1], stops[2], (t - 0.5) * 2);
          cell.style.backgroundColor = "rgb(" + col.join(",") + ")";
          if (col[0] * 0.299 + col[1] * 0.587 + col[2] * 0.114 < 140) cell.classList.add("is-dark");
          if (o.showValue !== false) cell.textContent = fmt(v);
        }
        grid.appendChild(cell);
      });
    });
    scroll.appendChild(grid);
    box.appendChild(scroll);

    var sc = K.el("div", { className: "heatmap-scale", "aria-hidden": "true" });
    sc.appendChild(K.el("span", null, fmt(min)));
    sc.appendChild(K.el("span", { className: "heatmap-scale-bar" }));
    sc.appendChild(K.el("span", null, fmt(max)));
    box.appendChild(sc);
  }

  K.heatmap = render;
  K.register("heatmap", function (root) {
    root.querySelectorAll("[data-kit-heatmap]").forEach(function (box) {
      render(box, K.readJSON(box.getAttribute("data-kit-heatmap")));
    });
  });
})();
