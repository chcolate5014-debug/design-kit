"""
키트 검증 스크립트 — 헤드리스 브라우저로 실제 동작을 확인하고 VERIFY.md 와 previews/*.png 를 만든다.

준비:  pip install flask playwright
       (브라우저는 PC에 설치된 Edge 를 쓴다. Edge 가 없으면: python -m playwright install chromium 후 BROWSER_CHANNEL= 로 실행)
실행:  python tools/verify_kit.py
"""
import os
import re
import sys
import threading
import traceback
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from playwright.sync_api import sync_playwright  # noqa: E402
from werkzeug.serving import make_server  # noqa: E402

import app_demo  # noqa: E402

PORT = 8051
BASE = f"http://127.0.0.1:{PORT}"
CHANNEL = os.environ.get("BROWSER_CHANNEL", "msedge") or None
PREVIEWS = ROOT / "previews"
RESULTS = []          # (분류, 항목, 통과 여부, 비고)


def check(group, name, ok, note=""):
    RESULTS.append((group, name, bool(ok), note))
    print(("  PASS " if ok else "  FAIL ") + f"[{group}] {name}" + (f" — {note}" if note else ""))


def run_case(group, name, fn):
    try:
        fn()
    except Exception as e:  # 한 항목이 실패해도 나머지는 계속
        traceback.print_exc()
        check(group, name, False, f"예외: {type(e).__name__}: {e}"[:200])


# ---------------------------------------------------------------------------
# 1. 정적 규칙 검사 (샘플이 AGENTS.md 규칙을 지키는지)
# ---------------------------------------------------------------------------
def static_rules():
    g = "규칙"
    samples = list((ROOT / "templates/kit/samples").glob("*.html"))
    templates = samples + [ROOT / "templates/kit/base.html", ROOT / "templates/kit/macros.html"]
    bad = {}
    for p in samples:
        t = p.read_text(encoding="utf-8")
        for label, pat in [("인라인 style", r'\sstyle\s*='), ("<style>", r"<style"), ("|safe", r"\|\s*safe"),
                           ('href="#"', r'href="#"'), ("<script> 코드", r"<script(?![^>]*application/json)"),
                           ("hex 색", r"#[0-9a-fA-F]{6}\b"), ("innerHTML", r"innerHTML")]:
            if re.search(pat, t):
                bad.setdefault(p.name, []).append(label)
    check(g, "샘플 템플릿: 인라인 style·<style>·|safe·href=\"#\"·<script> 코드·hex 색·innerHTML 없음",
          not bad, str(bad) if bad else f"{len(samples)}개 파일")
    base_bad = [p.name for p in templates if re.search(r'\sstyle\s*=|\|\s*safe|<style', p.read_text(encoding="utf-8"))]
    check(g, "base.html·macros.html: 인라인 style·|safe·<style> 없음", not base_bad, str(base_bad))

    js_files = list((ROOT / "static/kit/js").rglob("*.js"))
    js_bad = {}
    for p in js_files:
        t = p.read_text(encoding="utf-8")
        code = re.sub(r"/\*.*?\*/", "", t, flags=re.S)
        code = re.sub(r"(?m)^\s*//.*$", "", code)
        for label, pat in [("innerHTML", r"\.innerHTML\s*="), ("insertAdjacentHTML", r"insertAdjacentHTML"),
                           ("document.write", r"document\.write"), ("hex 색", r"['\"]#[0-9a-fA-F]{3,6}['\"]")]:
            if re.search(pat, code):
                js_bad.setdefault(p.name, []).append(label)
    check(g, "키트 JS: innerHTML·insertAdjacentHTML·document.write·hex 색 없음", not js_bad,
          str(js_bad) if js_bad else f"{len(js_files)}개 파일")

    css = (ROOT / "static/kit/css/kit.css").read_text(encoding="utf-8")
    root_end = css.index("}", css.index(":root {"))
    outside = re.findall(r"#[0-9a-fA-F]{3,6}\b", css[root_end:])
    check(g, "kit.css: 색 값은 :root 토큰에만 정의", not outside, str(outside[:5]))

    ext = []
    for p in templates + js_files + [ROOT / "static/kit/css/kit.css"]:
        ext += [f"{p.name}: {u}" for u in re.findall(r"https?://[^\s\"')]+", p.read_text(encoding="utf-8"))]
    check(g, "템플릿·CSS·JS에 외부 URL(CDN) 참조 없음", not ext, str(ext[:3]))


# ---------------------------------------------------------------------------
# 2. 브라우저 검증
# ---------------------------------------------------------------------------
def new_page(browser, width=1920, height=1080, block=None, errors=None, requests=None, reduced=False):
    ctx = browser.new_context(viewport={"width": width, "height": height},
                              reduced_motion="reduce" if reduced else "no-preference")
    page = ctx.new_page()
    if errors is not None:
        page.on("pageerror", lambda e: errors.append(str(e)))

    def route(r):
        url = r.request.url
        if requests is not None:
            requests.append(url)
        if not url.startswith(BASE):
            return r.abort()            # 외부 네트워크 차단
        if block and re.search(block, url):
            return r.abort()
        return r.continue_()
    page.route("**/*", route)
    return ctx, page


def rows_text(page, sel="table[data-kit-sort] tbody tr:not([hidden])", col=1):
    return page.eval_on_selector_all(sel, f"rs => rs.map(r => r.cells[{col - 1}] ? r.cells[{col - 1}].textContent.trim() : '')")


def browser_checks(browser):
    # ---------- 필터: 드롭다운, 조합, 유지, 초기화, 빈 결과 ----------
    def filters():
        g = "필터"
        ctx, p = new_page(browser)
        p.goto(BASE + "/lot")
        opts = {s: p.eval_on_selector_all(f"#{s} option", "os => os.map(o => o.textContent)")
                for s in ("f-product", "f-step", "f-status")}
        exp = {"f-product": ["전체"] + app_demo.PRODUCTS, "f-step": ["전체"] + app_demo.STEPS,
               "f-status": ["전체"] + list(app_demo.LOT_STATUS)}
        check(g, "LOT 드롭다운 옵션이 모두 표시됨 (특수문자 옵션 'R&D <시험>' 포함)", opts == exp,
              ", ".join(f"{k}:{len(v)}개" for k, v in opts.items()))

        p.select_option("#f-product", "PKG-A12")
        p.select_option("#f-status", "지연")
        p.fill("#f-q", "ER26A00")
        p.click(".filterbar button[type=submit]")
        p.wait_for_load_state()
        expected = [r for r in app_demo.LOTS if r["product"] == "PKG-A12" and r["status"] == "지연" and "ER26A00" in r["lot_id"]]
        prods = set(rows_text(p, col=2))
        stats = set(p.eval_on_selector_all("table[data-kit-sort] tbody tr td:nth-child(4)", "t => t.map(x => x.textContent.trim())"))
        n = len(rows_text(p))
        check(g, "필터 조합(제품+상태+LOT ID) 결과가 조건과 일치", n == len(expected) and prods <= {"PKG-A12"} and stats <= {"지연"},
              f"{n}건 (기대 {len(expected)}건)")
        kept = (p.input_value("#f-product"), p.input_value("#f-status"), p.input_value("#f-q"))
        check(g, "조회 후 입력값 유지", kept == ("PKG-A12", "지연", "ER26A00"), str(kept))
        res = p.text_content(".filterbar-result")
        check(g, "결과 건수 안내(role=status)에 건수 표시", f"{n}" in res and p.get_attribute(".filterbar-result", "role") == "status", res.strip())
        check(g, "조회 결과 기준 표시(basis)가 '조회 결과 기준'으로 바뀜", "조회 결과 기준" in p.text_content(".kpi-band-head"))

        p.click(".filterbar-actions a")
        p.wait_for_load_state()
        check(g, "초기화 링크 → 조건 비움, 전체 180건", len(rows_text(p)) == 180 and p.input_value("#f-q") == "" and p.url.endswith("/lot"),
              p.url)

        p.goto(BASE + "/lot?q=ZZZ999")
        empty = p.locator("td.empty-cell .empty")
        check(g, "빈 결과: 안내 문구 + 초기화 버튼 표시", empty.count() == 1 and "없습니다" in empty.text_content()
              and p.locator("td.empty-cell a.btn").get_attribute("href") == "/lot")
        check(g, "빈 결과일 때 차트는 '표시할 데이터가 없습니다' 안내",
              p.locator("[data-kit-chart][data-kit-chart-state=empty]").count() == 2)

        p.goto(BASE + "/inventory?status=부족&q=RM")
        hrefs = p.eval_on_selector_all(".pager a", "as => as.map(a => a.getAttribute('href'))")
        ok = all("status=" in h and "q=RM" in h for h in hrefs)
        check(g, "재고 페이지 번호 링크가 조회 조건을 유지", ok and len(hrefs) > 0,
              f"링크 {len(hrefs)}개" + (f", 예: {hrefs[0]}" if hrefs else " (1쪽뿐)"))
        p.goto(BASE + "/inventory?status=부족")
        p.click(".pager a:has-text('2')")
        p.wait_for_load_state()
        st = set(p.eval_on_selector_all("table tbody td:last-child", "t => t.map(x => x.textContent.trim())"))
        check(g, "2쪽으로 이동해도 필터(부족) 유지", st == {"부족"} and "page=2" in p.url, p.url)
        p.goto(BASE + "/inventory?q=없는품목")
        check(g, "재고 빈 결과 표시", p.locator("td.empty-cell").count() == 1)
        ctx.close()

    # ---------- 정렬 ----------
    def sorting():
        g = "정렬"
        ctx, p = new_page(browser)
        p.goto(BASE + "/catalog")
        tb = "#cat-table tbody tr:not([hidden])"
        th = lambda i: p.locator(f"#cat-table thead th:nth-child({i}) .sort-btn")  # noqa: E731
        th(1).click()
        ids = rows_text(p, tb, 1)
        check(g, "ID 자연 정렬 (ER26A0009 < ER26A0010 < ER26A0100)", ids == ["ER26A0001", "ER26A0002", "ER26A0009", "ER26A0010", "ER26A0100"], str(ids))
        th(1).click()
        ids2 = rows_text(p, tb, 1)
        aria = p.get_attribute("#cat-table thead th:nth-child(1)", "aria-sort")
        check(g, "다시 누르면 내림차순 + aria-sort=descending", ids2 == ids[::-1] and aria == "descending", aria or "")
        th(3).click()
        q = rows_text(p, tb, 3)
        check(g, "숫자 정렬 (천 단위 쉼표 포함)", q == ["0", "9", "85", "1,200", "30,500"], str(q))
        th(5).click()
        d = rows_text(p, tb, 5)
        check(g, "날짜 정렬, 빈 값('-')은 맨 뒤", d == ["2026-09-15", "2026-09-28", "2026-09-30", "2026-10-02", "-"], str(d))
        th(5).click()
        d2 = rows_text(p, tb, 5)
        check(g, "날짜 내림차순에서도 빈 값은 맨 뒤", d2[-1] == "-" and d2[0] == "2026-10-02", str(d2))
        th(4).click()
        r = rows_text(p, tb, 4)
        check(g, "진행률 열은 data-sort-value 로 숫자 정렬", r == ["0%", "12%", "64%", "92%", "100%"], str(r))
        others = p.eval_on_selector_all("#cat-table thead th[aria-sort]", "t => t.length")
        check(g, "정렬 중인 열 하나에만 aria-sort", others == 1)

        # 키보드
        p.goto(BASE + "/lot")
        p.focus("table[data-kit-sort] thead th:nth-child(6) .sort-btn")
        p.keyboard.press("Enter")
        days = [int(x) for x in rows_text(p, col=6)]
        a1 = p.get_attribute("table[data-kit-sort] thead th:nth-child(6)", "aria-sort")
        p.keyboard.press("Space")
        days2 = [int(x) for x in rows_text(p, col=6)]
        check(g, "키보드(Enter/Space)로 정렬, 180행 숫자 정렬 정확",
              days == sorted(days) and days2 == sorted(days, reverse=True) and a1 == "ascending", f"aria-sort={a1}")
        p.keyboard.press("Tab")
        focused = p.evaluate("document.activeElement.className")
        check(g, "정렬 버튼은 Tab 으로 이동 가능", focused == "sort-btn", focused)
        ctx.close()

    # ---------- 인라인 편집 ----------
    def inline_edit():
        g = "인라인 편집"
        ctx, p = new_page(browser)
        posts = []
        p.on("request", lambda r: posts.append(r.url) if r.method == "POST" else None)
        p.goto(BASE + "/staff")
        cell = lambda i: p.locator("#staff-table tbody tr").nth(i)  # noqa: E731

        # 성공
        cell(0).locator(".edit-cell").click()
        p.keyboard.type("야간 선호 <테스트> & \"따옴표\"")
        p.keyboard.press("Enter")
        cell(0).locator(".edit-state:has-text('저장 중')").wait_for(timeout=2000)
        cell(0).locator(".edit-state:has-text('저장됨')").wait_for(timeout=4000)
        saved = app_demo.staff_by_id("E1000")["note"]
        check(g, "저장 성공: '저장 중' → 서버 {ok:true} 후 '저장됨', 서버 값 반영", saved == "야간 선호 <테스트> & \"따옴표\"", saved)
        check(g, "저장된 특수문자가 태그로 해석되지 않고 글자로 표시",
              cell(0).locator(".edit-cell-text").text_content() == saved and cell(0).locator(".edit-cell-text *").count() == 0)

        # 실패 → 원래 값 복원
        before = cell(1).locator(".edit-cell-text").text_content()
        cell(1).locator(".edit-cell").click()
        p.keyboard.press("Control+A")
        p.keyboard.type("실패 시연")
        p.keyboard.press("Enter")
        cell(1).locator(".edit-state:has-text('저장 실패')").wait_for(timeout=4000)
        after = cell(1).locator(".edit-cell-text").text_content()
        toast = p.locator(".toast.danger").first.text_content()
        check(g, "저장 실패: 원래 값 복원 + 오류 표시(토스트 role=alert, 서버 사유 포함)",
              after == before and "거부" in toast and app_demo.staff_by_id("E1001")["note"] == before, f"복원값='{after}'")

        # 서버 연결 실패
        p.route("**/api/staff/save", lambda r: r.abort())
        cell(2).locator(".edit-cell").click()
        p.keyboard.type("네트워크 실패")
        p.keyboard.press("Enter")
        cell(2).locator(".edit-state:has-text('저장 실패')").wait_for(timeout=4000)
        check(g, "네트워크 오류도 실패 처리 + 원래 값 복원", cell(2).locator(".edit-cell-text").text_content() == "")
        p.unroute("**/api/staff/save")

        # 한글 조합 중 Enter
        n_before = len(posts)
        cell(3).locator(".edit-cell").click()
        p.keyboard.type("한글")
        p.evaluate("""() => {
            const i = document.querySelector('.edit-input');
            i.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', isComposing: true, keyCode: 229, bubbles: true, cancelable: true}));
        }""")
        p.wait_for_timeout(300)
        still = p.locator(".edit-input").count() == 1
        check(g, "한글 조합 중 Enter(isComposing)는 저장하지 않음", still and len(posts) == n_before, f"입력창 유지={still}, POST {len(posts) - n_before}건")
        p.keyboard.press("Escape")
        check(g, "Esc 는 취소(원래 값 유지)", p.locator(".edit-input").count() == 0
              and cell(3).locator(".edit-cell-text").text_content() == app_demo.staff_by_id("E1003")["note"])

        # 저장 URL 없음 = 데모
        p.goto(BASE + "/catalog")
        p.locator("[aria-labelledby=c-edit] .edit-cell").first.click()
        p.keyboard.type(" 수정")
        p.keyboard.press("Enter")
        demo = p.locator("[aria-labelledby=c-edit] .edit-state").first.text_content()
        check(g, "저장 URL이 없으면 '데모: 저장되지 않음' 표시", "데모: 저장되지 않음" in demo, demo)
        ctx.close()

    # ---------- 차트/폰트/외부 네트워크 ----------
    def resilience():
        g = "장애 상황"
        errs, reqs = [], []
        ctx, p = new_page(browser, block=r"chart\.umd\.min\.js", errors=errs, requests=reqs)
        p.goto(BASE + "/lot", wait_until="load")
        p.wait_for_timeout(500)
        msgs = p.eval_on_selector_all(".chart-msg strong", "s => s.map(x => x.textContent)")
        check(g, "Chart.js 파일 없음 → 차트 3곳 모두 '차트를 불러오지 못했습니다'",
              len(msgs) == 3 and all("불러오지 못했습니다" in m for m in msgs), str(msgs))
        p.locator("table[data-kit-sort] thead th:nth-child(1) .sort-btn").click()
        p.locator("table[data-kit-sort] thead th:nth-child(1) .sort-btn").click()
        first = rows_text(p)[0]
        gantt = p.locator(".gantt-seg").count()
        heat = p.locator(".heatmap-cell").count()
        check(g, "Chart.js 없음에도 정렬·간트·히트맵 정상", first == "ER26A0180" and gantt > 0 and heat > 0,
              f"정렬 첫 행 {first}, 간트 막대 {gantt}, 히트맵 칸 {heat}")
        check(g, "Chart.js 없음에도 스크립트 오류(pageerror) 없음", not errs, str(errs[:2]))
        PREVIEWS.mkdir(exist_ok=True)
        p.screenshot(path=str(PREVIEWS / "lot_no_chartjs_1920.png"))
        ctx.close()

        errs2 = []
        ctx, p = new_page(browser, block=r"kit-chart\.js", errors=errs2)
        p.goto(BASE + "/lot", wait_until="load")
        p.wait_for_timeout(300)
        n = p.locator(".chart-msg.is-error").count()
        check(g, "kit-chart.js 자체가 없어도 차트 자리에 오류 안내 (kit.js 안전망)", n == 3, f"{n}곳")
        ctx.close()

        ctx, p = new_page(browser)
        p.goto(BASE + "/staff")
        p.route("**/static/kit/vendor/**", lambda r: r.abort())
        p.goto(BASE + "/staff")
        p.locator("#qs-staff").fill("품질")
        p.wait_for_timeout(300)
        p.click("[data-kit-modal-open]")
        opened = p.evaluate("document.getElementById('m-training').open")
        check(g, "차트를 쓰지 않는 화면은 차트 파일 없이 독립 동작(검색·모달)", opened and p.locator("#staff-table tbody tr:not([hidden])").count() > 0)
        ctx.close()

        errs3 = []
        ctx, p = new_page(browser, block=r"\.woff2", errors=errs3)
        p.goto(BASE + "/lot")
        p.wait_for_timeout(300)
        fam = p.evaluate("getComputedStyle(document.body).fontFamily")
        loaded = p.evaluate("[...document.fonts].filter(f => f.status === 'loaded').map(f => f.family)")
        over = p.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
        bh = p.eval_on_selector_all(".badge", "bs => [...new Set(bs.map(b => Math.round(b.getBoundingClientRect().height)))]")
        check(g, "폰트 파일 없음 → 시스템 글꼴(맑은 고딕)로 표시, 가로 넘침 없음, 배지 높이 유지",
              over <= 0 and bh == [20] and not loaded, f"font-family={fam[:40]}…, 로드된 웹폰트={loaded}, 넘침={over}px, 배지 높이={bh}")
        p.screenshot(path=str(PREVIEWS / "lot_no_fonts_1920.png"))
        ctx.close()

        ctx, p = new_page(browser)
        p.goto(BASE + "/lot")
        p.wait_for_timeout(300)
        loaded = p.evaluate("[...document.fonts].filter(f => f.status === 'loaded').map(f => f.family)")
        check(g, "폰트 파일 있음 → Pretendard·D2Coding 자동 적용", "Kit Pretendard" in " ".join(loaded) and "Kit D2Coding" in " ".join(loaded), str(loaded))
        ctx.close()

        ext = [u for u in reqs if not u.startswith(BASE)]
        all_reqs = []
        for path in ("/lot", "/inventory", "/staff", "/catalog"):
            c, pg = new_page(browser, requests=all_reqs)
            pg.goto(BASE + path, wait_until="networkidle")
            c.close()
        ext += [u for u in all_reqs if not u.startswith(BASE)]
        check(g, "외부 네트워크 요청 0건 (4개 화면, 외부 차단 상태에서 정상 동작)", not ext, f"총 요청 {len(all_reqs)}건, 외부 {len(ext)}건")

    # ---------- 특수문자 ----------
    def escaping():
        g = "특수문자"
        ctx, p = new_page(browser)
        dialogs = []
        p.on("dialog", lambda d: (dialogs.append(d.message), d.dismiss()))
        p.goto(BASE + "/lot?product=R%26D+%3C%EC%8B%9C%ED%97%98%3E")
        prods = set(rows_text(p, col=2))
        check(g, "'R&D <시험>' 필터 조회·표시·선택 유지", prods == {"R&D <시험>"} and p.input_value("#f-product") == "R&D <시험>", str(prods))
        p.goto(BASE + "/lot")
        memo = p.eval_on_selector_all("table[data-kit-sort] tbody td:nth-child(8)", "t => t.map(x => [x.textContent, x.children.length])")
        hit = [m for m in memo if "<긴급>" in m[0]]
        check(g, "메모의 < > & \" 가 글자로 표시되고 요소로 해석되지 않음", hit and all(m[1] == 0 for m in hit), hit[0][0] if hit else "")
        p.goto(BASE + "/lot?q=%3Cscript%3Ealert(1)%3C%2Fscript%3E%22%27")
        check(g, "검색어에 <script>·따옴표를 넣어도 실행되지 않고 값으로 유지",
              not dialogs and p.input_value("#f-q") == "<script>alert(1)</script>\"'")
        p.goto(BASE + "/catalog")
        seg = p.locator(".gantt-seg:has-text('HOLD <검토>')")
        check(g, "간트 막대 라벨의 특수문자도 글자로 표시 (JSON은 |tojson, DOM은 textContent)",
              seg.count() == 1 and seg.evaluate("e => e.children.length") == 0)
        raw = p.request.get(BASE + "/catalog").text()
        block = raw.split('id="c-gantt"')[1].split("</script>")[0]
        check(g, "JSON 데이터 블록에서 < > 가 \\u003c \\u003e 로 이스케이프 (|tojson)", "HOLD \\u003c" in block and "<" not in block[1:])
        ctx.close()

    # ---------- 대량 행 + 고정 헤더 ----------
    def big_table():
        g = "대량 데이터"
        ctx, p = new_page(browser)
        p.goto(BASE + "/lot")
        n = len(rows_text(p))
        info = p.evaluate("""() => {
            const w = document.querySelector('.table-wrap');
            w.scrollTop = w.scrollHeight;
            const th = w.querySelector('thead th');
            return {scroll: w.scrollHeight > w.clientHeight, wrapTop: Math.round(w.getBoundingClientRect().top),
                    thTop: Math.round(th.getBoundingClientRect().top), page: document.documentElement.scrollHeight};
        }""")
        check(g, f"LOT {n}행: 표 안에서 스크롤, 헤더 고정", n == 180 and info["scroll"] and abs(info["wrapTop"] - info["thTop"]) <= 1, str(info))
        p.screenshot(path=str(PREVIEWS / "lot_table_scrolled_1920.png"))
        ctx.close()

    # ---------- 화면 폭 ----------
    def widths():
        g = "화면 폭"
        for w, h in ((1920, 1080), (1280, 800), (390, 844)):
            for path in ("/lot", "/inventory", "/staff", "/catalog"):
                ctx, p = new_page(browser, w, h)
                p.goto(BASE + path, wait_until="networkidle")
                over = p.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
                bad_badges = p.eval_on_selector_all(".badge", "bs => bs.filter(b => Math.round(b.getBoundingClientRect().height) !== 20).length")
                cur = p.eval_on_selector_all(".sidenav a[aria-current=page]", "a => a.map(x => x.textContent.trim())")
                ok = over <= 0 and bad_badges == 0 and len(cur) == 1
                note = f"가로 넘침 {over}px, 높이 어긋난 배지 {bad_badges}개, 선택 메뉴 {cur}"
                if w == 390:
                    toggle = p.locator(".nav-toggle")
                    hidden_before = not p.locator("#kit-nav").is_visible()
                    toggle.click()
                    vis = p.locator("#kit-nav").is_visible() and p.get_attribute(".nav-toggle", "aria-expanded") == "true"
                    wraps = p.eval_on_selector_all(".table-wrap", "ws => ws.filter(w => w.scrollWidth > w.clientWidth).length")
                    ok = ok and hidden_before and vis
                    note += f", 메뉴 버튼으로 열림={vis}, 가로 스크롤 표 {wraps}개"
                    if path == "/lot":
                        p.screenshot(path=str(PREVIEWS / "lot_mobile_menu_open_390.png"), full_page=False)
                if w == 1280 and path in ("/lot", "/staff"):
                    p.screenshot(path=str(PREVIEWS / f"{path.strip('/')}_1280.png"), full_page=True)
                check(g, f"{w}px {path}: 가로 넘침 없음, 배지 20px, 메뉴 선택 표시(aria-current)", ok, note)
                ctx.close()

    # ---------- 탭·모달·토스트·빠른 검색·접근성 ----------
    def interactions():
        g = "상호작용·접근성"
        ctx, p = new_page(browser)
        p.goto(BASE + "/staff")
        p.focus(".tab[aria-controls=tab-info]")
        p.keyboard.press("ArrowRight")
        sel = p.get_attribute(".tab[aria-controls=tab-edit]", "aria-selected")
        vis = p.locator("#tab-edit").is_visible() and not p.locator("#tab-info").is_visible()
        check(g, "탭: 화살표 키 이동, aria-selected, 패널 전환", sel == "true" and vis)

        opener = p.locator("[data-kit-modal-open=m-training]")
        opener.click()
        is_open = p.evaluate("document.getElementById('m-training').open")
        first = p.evaluate("document.activeElement.id")
        for _ in range(8):
            p.keyboard.press("Tab")
        inside = p.evaluate("document.getElementById('m-training').contains(document.activeElement)")
        p.keyboard.press("Escape")
        closed = not p.evaluate("document.getElementById('m-training').open")
        back = p.evaluate("document.activeElement.getAttribute('data-kit-modal-open')")
        check(g, "모달: 열기, 첫 입력에 포커스, Tab 가두기, Esc 닫기, 연 버튼으로 포커스 복귀",
              is_open and first == "t-title" and inside and closed and back == "m-training", f"첫 포커스={first}, 복귀={back}")

        p.fill("#qs-staff", "품질")
        p.wait_for_timeout(250)
        cnt = p.text_content("[data-kit-quick-search-count=staff-table]")
        shown = p.locator("#staff-table tbody tr:not([hidden])").count()
        p.fill("#qs-staff", "없는사람")
        p.wait_for_timeout(250)
        empty_vis = p.locator("#staff-table td.empty-cell").is_visible()
        check(g, "빠른 검색: 건수 안내(aria-live) + 결과 없음 표시", "건 표시" in cnt and shown == 3 and empty_vis, cnt)

        p.goto(BASE + "/staff?id=E1002")
        p.click(".tab[aria-controls=tab-edit]")
        p.fill("#e-name", "")
        p.fill("#e-phone", "12")
        p.click("#tab-edit button[type=submit]")
        p.wait_for_load_state()
        inv = p.eval_on_selector_all("[aria-invalid=true]", "e => e.map(x => x.id)")
        err = p.locator(".field-error").count()
        tab_ok = p.locator("#tab-edit").is_visible()
        check(g, "입력 폼: 서버 검증 오류 → 오류 탭 유지, aria-invalid + 오류 문구 + 오류 배너", set(inv) >= {"e-name", "e-phone"} and err >= 2 and tab_ok, str(inv))
        p.fill("#e-name", "박도윤")
        p.fill("#e-phone", "010-1111-2222")
        p.click("#tab-edit button[type=submit]")
        p.wait_for_load_state()
        t = p.locator(".toast.success").first
        t.wait_for(timeout=2000)
        check(g, "입력 폼 저장 성공 → 리다이렉트 후 토스트(aria-live 영역)",
              "저장했습니다" in t.text_content() and p.get_attribute("#kit-toasts", "aria-live") == "polite")

        p.click("[data-kit-modal-open=m-training]")
        p.fill("#t-title", "화학물질 <MSDS> 교육")
        p.click("#m-training button[type=submit]")
        p.wait_for_load_state()
        rows = p.locator("#tab-training tbody tr").count()
        check(g, "모달 입력 저장 → 교육 이력 탭에 반영", p.locator("#tab-training").is_visible() and rows >= 1, f"{rows}행")

        p.goto(BASE + "/lot")
        p.keyboard.press("Tab")
        skip = p.evaluate("document.activeElement.className")
        p.keyboard.press("Enter")
        main = p.evaluate("document.activeElement.id")
        check(g, "본문 바로가기: 첫 Tab 에 표시, Enter 로 본문 이동", skip == "skip-link" and main == "kit-main", f"{skip} → {main}")
        outline = p.evaluate("""() => { const b = document.querySelector('.filterbar .btn-primary'); b.focus();
            return getComputedStyle(b).outlineStyle; }""")
        unl = p.evaluate("[...document.querySelectorAll('input, select, textarea')].filter(i => i.type !== 'hidden' && !i.labels?.length && !i.getAttribute('aria-label')).length")
        check(g, "키보드 포커스 표시(outline) + 모든 입력에 label", outline != "none" and unl == 0, f"outline={outline}, label 없는 입력 {unl}개")
        ctx.close()

        ctx, p = new_page(browser, reduced=True)
        p.goto(BASE + "/catalog?toast=info")
        tr = p.evaluate("getComputedStyle(document.querySelector('.toast')).transitionDuration")
        anim = p.evaluate("getComputedStyle(document.querySelector('.spinner')).animationDuration")
        check(g, "모션 줄이기 설정 → 전환·애니메이션 제거", tr in ("0s",) and anim in ("1e-05s", "0.00001s", "0s"), f"transition={tr}, animation={anim}")
        ctx.close()

    # ---------- 미리보기 스크린샷 ----------
    def previews():
        PREVIEWS.mkdir(exist_ok=True)
        for path, name in (("/lot", "lot_dashboard"), ("/inventory", "inventory_list"), ("/staff", "staff_detail"), ("/catalog", "catalog")):
            ctx, p = new_page(browser, 1920, 1080)
            p.goto(BASE + path, wait_until="networkidle")
            p.wait_for_timeout(400)
            p.screenshot(path=str(PREVIEWS / f"{name}_1920.png"), full_page=True)
            ctx.close()
        ctx, p = new_page(browser, 1920, 1080)
        p.goto(BASE + "/staff?id=E1004")
        p.click("[data-kit-modal-open=m-training]")
        p.wait_for_timeout(200)
        p.screenshot(path=str(PREVIEWS / "staff_modal_1920.png"))
        ctx.close()
        check("미리보기", "previews/*.png 생성", True, ", ".join(sorted(x.name for x in PREVIEWS.glob("*.png"))))

    for grp, name, fn in (("필터", "필터 전체", filters), ("정렬", "정렬 전체", sorting), ("인라인 편집", "인라인 편집 전체", inline_edit),
                          ("장애 상황", "장애 상황 전체", resilience), ("특수문자", "특수문자 전체", escaping),
                          ("대량 데이터", "대량 데이터 전체", big_table), ("화면 폭", "화면 폭 전체", widths),
                          ("상호작용·접근성", "상호작용 전체", interactions), ("미리보기", "미리보기", previews)):
        print(f"\n== {grp}")
        run_case(grp, name, fn)


# ---------------------------------------------------------------------------
# 3. VERIFY.md 작성
# ---------------------------------------------------------------------------
NOT_VERIFIED = [
    ("사내 Edge 버전·그룹 정책", "사내 PC의 Edge 버전, 보안 정책(스크립트 차단, 확장 프로그램)에서의 동작"),
    ("사내 모니터·배율", "사내 모니터의 Windows 배율(125%·150%)에서 글자 크기와 표 밀도 — 여기서는 100% 배율만 확인"),
    ("맑은 고딕 실제 렌더링", "폰트 파일 없는 상태는 이 PC(Windows 11, 맑은 고딕 설치)에서 확인. 사내 PC 글꼴 구성이 다르면 재확인 필요"),
    ("사내 Flask 앱 연결", "기존 앱의 static 경로·블루프린트·url_prefix·CSRF 설정과의 결합 (README의 연결 절차대로 적용 후 확인 필요)"),
    ("실제 저장 API", "사내 저장 API가 {\"ok\": true} 형식으로 응답하는지, 인증 만료 시 응답(302 로그인 페이지 등)이 실패로 처리되는지"),
    ("실제 한글 IME", "isComposing 이벤트를 합성해 확인함. 실제 사내 PC의 MS 한글 입력기로 조합 중 Enter 는 사람이 한 번 확인 권장"),
    ("사내망 CDN 차단", "외부 요청 0건은 확인했으나, 사내 프록시 환경 자체에서는 실행하지 못함"),
    ("OpenCode(사내 LLM)의 규칙 준수", "AGENTS.md 를 사내 LLM이 실제로 따르는지는 사내에서 화면 1~2개를 만들어 보고 확인 필요"),
]


def write_report():
    passed = sum(1 for r in RESULTS if r[2])
    lines = [
        "# VERIFY — 키트 검증 결과",
        "",
        f"- 실행: `python tools/verify_kit.py` · {datetime.now():%Y-%m-%d %H:%M}",
        f"- 브라우저: 헤드리스 {'Microsoft Edge' if CHANNEL == 'msedge' else 'Chromium'} (Playwright) · 데모 앱 `app_demo.py`",
        f"- 결과: **{passed} / {len(RESULTS)} 통과**",
        "",
        "## 검증함 (자동 실행)",
        "",
        "| 분류 | 항목 | 결과 | 비고 |",
        "|---|---|---|---|",
    ]
    for g, name, ok, note in RESULTS:
        note = note.replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {g} | {name} | {'통과' if ok else '**실패**'} | {note} |")
    lines += ["", "## 사내 환경에서만 확인 가능 (검증 못 함)", "", "| 항목 | 내용 |", "|---|---|"]
    lines += [f"| {a} | {b} |" for a, b in NOT_VERIFIED]
    lines += ["", "## 미리보기", "", "`previews/` 폴더의 스크린샷은 이 검증 실행 중에 찍은 것이다.", ""]
    (ROOT / "VERIFY.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"\nVERIFY.md 작성: {passed}/{len(RESULTS)} 통과")
    return passed == len(RESULTS)


def main():
    server = make_server("127.0.0.1", PORT, app_demo.app, threaded=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print("== 규칙")
    run_case("규칙", "정적 규칙", static_rules)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel=CHANNEL, headless=True)
        browser_checks(browser)
        browser.close()
    server.shutdown()
    sys.exit(0 if write_report() else 1)


if __name__ == "__main__":
    main()
