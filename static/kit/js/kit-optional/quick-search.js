/* ==========================================================================
   선택 부품 — 브라우저 빠른 검색 (작은 표 전용, 수백 행 이하)
   많은 데이터는 필터바(GET 서버 조회)를 쓴다.
   로드: {{ kit.scripts("search") }}   (kit.js 다음)

   <div class="quick-search">
     <label class="sr-only" for="qs-staff">표 안에서 찾기</label>
     <input class="input" id="qs-staff" type="search" placeholder="표 안에서 찾기" data-kit-quick-search="staff-table">
     <span class="quick-search-count" data-kit-quick-search-count="staff-table" role="status" aria-live="polite"></span>
   </div>
   <table class="table" id="staff-table"> ...
   ========================================================================== */
(function () {
  "use strict";
  if (!window.Kit) return;
  var K = window.Kit;

  function norm(s) { return String(s || "").toLowerCase().replace(/\s+/g, " ").trim(); }

  K.register("quick-search", function (root) {
    root.querySelectorAll("input[data-kit-quick-search]").forEach(function (input) {
      var tableId = input.getAttribute("data-kit-quick-search");
      var table = document.getElementById(tableId);
      if (!table || !table.tBodies[0]) return;
      input.setAttribute("aria-controls", tableId);
      var tb = table.tBodies[0];
      var counter = root.querySelector('[data-kit-quick-search-count="' + tableId + '"]');
      var cols = table.tHead && table.tHead.rows[0] ? table.tHead.rows[0].cells.length : 1;

      var emptyRow = K.el("tr", { hidden: true });
      var emptyTd = K.el("td", { className: "empty-cell", colspan: cols });
      var box = K.el("div", { className: "empty" });
      box.appendChild(K.el("strong", { className: "empty-title" }, "검색 결과가 없습니다"));
      box.appendChild(K.el("span", null, "검색어를 줄이거나 지워 보세요."));
      emptyTd.appendChild(box);
      emptyRow.appendChild(emptyTd);
      tb.appendChild(emptyRow);

      var timer;
      function apply() {
        var q = norm(input.value);
        var rows = Array.prototype.filter.call(tb.rows, function (r) { return r !== emptyRow && !r.querySelector(".empty-cell"); });
        var shown = 0;
        rows.forEach(function (r) {
          var hit = !q || norm(r.textContent).indexOf(q) >= 0;
          r.hidden = !hit;
          if (hit) shown++;
        });
        emptyRow.hidden = !(q && shown === 0);
        if (counter) counter.textContent = q ? rows.length + "건 중 " + shown + "건 표시" : "전체 " + rows.length + "건";
      }
      input.addEventListener("input", function () { clearTimeout(timer); timer = setTimeout(apply, 120); });
      input.addEventListener("keydown", function (e) { if (e.key === "Escape") { input.value = ""; apply(); } });
      apply();
    });
  });
})();
