/* ==========================================================================
   선택 부품 — 인라인 편집
   로드: {{ kit.scripts("edit") }}   (kit.js 다음)

   <table class="table" data-kit-edit-url="{{ url_for('api_save') }}">   ← 저장 URL (가까운 조상 또는 요소 자신)
     <td><span data-kit-edit data-id="{{ row.id }}" data-field="memo" data-placeholder="메모 추가">{{ row.memo }}</span></td>

   동작
   - 클릭 또는 Enter/Space 로 편집, Enter 저장, Esc 취소, 다른 곳을 누르면 저장
   - 한글 조합 중 Enter(isComposing)는 저장하지 않는다
   - POST {id, field, value} → 서버가 {"ok": true} 를 돌려줄 때만 "저장됨"
     그 외(ok 아님, HTTP 오류, 네트워크 오류)는 원래 값으로 되돌리고 오류를 표시한다.
     서버가 {"ok": false, "error": "사유"} 를 주면 사유를 보여준다.
   - 저장 URL이 없으면 "데모: 저장되지 않음"을 표시한다 (값은 화면에만 반영)
   ========================================================================== */
(function () {
  "use strict";
  if (!window.Kit) return;
  var K = window.Kit;

  function setState(cell, kind, text) {
    var s = cell.querySelector(".edit-state");
    if (!s) { s = K.el("span", { className: "edit-state" }); cell.appendChild(s); }
    s.className = "edit-state " + kind;
    s.textContent = text || "";
    clearTimeout(cell._kitT);
    if (kind === "success") cell._kitT = setTimeout(function () { s.textContent = ""; }, 2500);
  }

  function enhance(src) {
    var value = src.textContent.trim();
    var id = src.getAttribute("data-id") || "";
    var field = src.getAttribute("data-field") || "";
    var host = src.closest("[data-kit-edit-url]");
    var url = host ? host.getAttribute("data-kit-edit-url") : "";
    var ph = src.getAttribute("data-placeholder") || "입력";
    var fieldLabel = src.getAttribute("data-label") || field;

    var cell = K.el("span", { className: "edit-wrap" });
    var btn = K.el("button", { type: "button", className: "edit-cell", "aria-label": fieldLabel + " 편집: " + (value || "비어 있음") });
    var text = K.el("span", { className: "edit-cell-text", "data-placeholder": ph }, value);
    btn.appendChild(text);
    cell.appendChild(btn);
    src.parentNode.replaceChild(cell, src);

    var saved = value;          // 서버에 저장된 값
    var input = null;

    function show(v) {
      text.textContent = v;
      btn.setAttribute("aria-label", fieldLabel + " 편집: " + (v || "비어 있음"));
    }

    function open() {
      input = K.el("input", { type: "text", className: "edit-input", "aria-label": fieldLabel, maxlength: src.getAttribute("data-maxlength") || 200 });
      input.value = saved;
      btn.hidden = true;
      cell.insertBefore(input, btn);
      input.focus();
      input.select();
      var done = false;
      function finish(save, refocus) {
        if (done) return;
        done = true;
        var v = input.value.trim();
        cell.removeChild(input);
        input = null;
        btn.hidden = false;
        if (refocus) btn.focus();
        if (save && v !== saved) commit(v);
      }
      input.addEventListener("keydown", function (e) {
        if (e.key === "Enter") {
          if (e.isComposing || e.keyCode === 229) return;      // 한글 조합 중 Enter 는 무시
          e.preventDefault(); finish(true, true);
        } else if (e.key === "Escape") {
          e.preventDefault(); finish(false, true);
        }
      });
      input.addEventListener("blur", function () { finish(true, false); });
    }

    function commit(v) {
      show(v);
      if (!url) {
        saved = v;
        setState(cell, "warning", "데모: 저장되지 않음");
        K.toast("데모 화면입니다. 저장되지 않았습니다.", "warning");
        return;
      }
      btn.disabled = true;
      cell.setAttribute("aria-busy", "true");
      setState(cell, "saving", "저장 중…");
      K.postJSON(url, { id: id, field: field, value: v })
        .then(function (r) {
          return r.json().catch(function () { return null; }).then(function (j) { return { http: r.ok, body: j }; });
        })
        .then(function (res) {
          if (res.http && res.body && res.body.ok === true) {
            saved = v;
            setState(cell, "success", "저장됨");
            K.toast("저장했습니다: " + (id || fieldLabel), "success");
          } else {
            fail(res.body && res.body.error ? String(res.body.error) : "서버가 저장을 확인하지 않았습니다.");
          }
        })
        .catch(function () { fail("서버에 연결하지 못했습니다."); })
        .then(function () { btn.disabled = false; cell.removeAttribute("aria-busy"); });
    }

    function fail(reason) {
      show(saved);                                   // 원래 값 복원
      setState(cell, "danger", "저장 실패");
      K.toast("저장하지 못했습니다. " + reason + " 원래 값으로 되돌렸습니다.", "danger");
    }

    btn.addEventListener("click", open);
  }

  K.register("inline-edit", function (root) {
    root.querySelectorAll("[data-kit-edit]").forEach(enhance);
  });
})();
