/* ==========================================================================
   선택 부품 — 간트 타임라인 (라이브러리 불필요)
   로드: {{ kit.scripts("gantt") }}   (kit.js 다음)

   <div data-kit-gantt="lot-gantt" aria-label="LOT 타임라인"></div>
   {{ kit.data("lot-gantt", gantt) }}

   gantt = {
     "start": "2026-09-24", "days": 7, "now": "2026-09-28T14:00",   // now 는 선택
     "mono": true,                                                   // 행 이름을 고정폭(코드값)으로
     "rows": [ { "label": "ER26A0001",
                 "segs": [ { "from": "2026-09-24T08:00", "to": "2026-09-25T20:00",
                             "label": "Bump", "status": "success|warning|danger|info|neutral|plan" } ] } ]
   }
   막대 좌표(left/width)는 이 파일 안에서만 계산하고 0~100% 로 자른다.
   ========================================================================== */
(function () {
  "use strict";
  if (!window.Kit) return;
  var K = window.Kit;
  var DAY = 864e5;

  function parse(s) {
    if (!s) return NaN;
    s = String(s).trim().replace(" ", "T");
    if (/^\d{4}-\d{2}-\d{2}$/.test(s)) s += "T00:00";   // 날짜만 있으면 현지 자정 기준
    return new Date(s).getTime();
  }
  function clamp(v) { return Math.max(0, Math.min(100, v)); }
  function md(t) { var d = new Date(t); return (d.getMonth() + 1) + "/" + d.getDate(); }
  function hm(t) { var d = new Date(t); return md(t) + " " + ("0" + d.getHours()).slice(-2) + ":" + ("0" + d.getMinutes()).slice(-2); }

  function render(box, o) {
    while (box.firstChild) box.removeChild(box.firstChild);
    var start = parse(o && o.start);
    var days = Math.max(1, Math.min(62, parseInt(o && o.days, 10) || 7));
    if (!o || isNaN(start) || !Array.isArray(o.rows)) {
      var err = K.el("div", { className: "error-state", role: "alert" });
      err.appendChild(K.el("strong", { className: "empty-title" }, "타임라인 데이터를 읽지 못했습니다"));
      box.appendChild(err);
      return;
    }
    if (!o.rows.length) {
      var em = K.el("div", { className: "empty", role: "status" });
      em.appendChild(K.el("strong", { className: "empty-title" }, "표시할 일정이 없습니다"));
      box.appendChild(em);
      return;
    }
    var span = days * DAY;
    var pct = function (t) { return ((t - start) / span) * 100; };
    var now = parse(o.now);

    var scroll = K.el("div", { className: "gantt-scroll" });
    var grid = K.el("div", { className: "gantt", role: "group", "aria-label": box.getAttribute("aria-label") || "타임라인" });
    grid.appendChild(K.el("div", { className: "gantt-corner" }));
    var scale = K.el("div", { className: "gantt-scale", "aria-hidden": "true" });
    scale.style.gridTemplateColumns = "repeat(" + days + ", minmax(0, 1fr))";
    for (var i = 0; i < days; i++) scale.appendChild(K.el("span", null, md(start + i * DAY)));
    grid.appendChild(scale);

    o.rows.forEach(function (row, ri) {
      var label = K.el("div", { className: "gantt-label" });
      label.appendChild(K.el("span", { className: o.mono ? "mono" : null, title: row.label }, row.label));
      grid.appendChild(label);

      var track = K.el("div", { className: "gantt-track" });
      for (var d = 1; d < days; d++) {
        var g = K.el("div", { className: "gantt-grid", "aria-hidden": "true" });
        g.style.left = clamp((d / days) * 100) + "%";
        track.appendChild(g);
      }
      (row.segs || []).forEach(function (s) {
        var a = parse(s.from), b = parse(s.to);
        if (isNaN(a) || isNaN(b) || b <= a) return;
        var l = clamp(pct(a)), r = clamp(pct(b));
        if (r <= l) return;                              // 표시 구간 밖
        var st = s.status === "plan" ? "plan" : K.status(s.status);
        var text = row.label + " · " + (s.label || "") + " · " + hm(a) + " ~ " + hm(b);
        var seg = K.el("div", { className: "gantt-seg " + st, title: text, role: "img", "aria-label": text }, s.label || "");
        seg.style.left = l + "%";
        seg.style.width = (r - l) + "%";
        track.appendChild(seg);
      });
      if (!isNaN(now)) {
        var p = pct(now);
        if (p >= 0 && p <= 100) {
          var line = K.el("div", { className: "gantt-now", "aria-hidden": "true" });
          line.style.left = p + "%";
          track.appendChild(line);
          if (ri === 0) {
            var tag = K.el("div", { className: "gantt-now-label", "aria-hidden": "true" }, "NOW");
            tag.style.left = p + "%";
            track.appendChild(tag);
          }
        }
      }
      grid.appendChild(track);
    });
    scroll.appendChild(grid);
    box.appendChild(scroll);
  }

  K.gantt = render;
  K.register("gantt", function (root) {
    root.querySelectorAll("[data-kit-gantt]").forEach(function (box) {
      render(box, K.readJSON(box.getAttribute("data-kit-gantt")));
    });
  });
})();
