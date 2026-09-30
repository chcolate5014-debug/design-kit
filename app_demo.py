"""
Flask 공통 UI 키트 — 데모 앱 (모든 데이터는 더미)

실행 (로컬 확인용):
    pip install flask
    python app_demo.py        →  http://127.0.0.1:8050

debug=True 는 내 PC에서 화면을 확인할 때만 쓴다. 사내 서버 배포 설정으로 쓰지 않는다.

이 파일이 보여주는 것
  - 메뉴·앱 이름을 context_processor 로 한 곳에서 넘기는 방법 (kit_nav, kit_active)
  - GET 필터(서버 조회) + 입력값 유지 + 초기화 + 빈 결과
  - 집계 기준(전체 / 조회 결과) 계산은 앱이 한다
  - 인라인 편집 저장 API: {"ok": true} 성공 / {"ok": false, "error": "..."} 실패
"""
import csv
import io
import random
import time
from datetime import date, datetime, timedelta

from flask import Flask, Response, abort, jsonify, redirect, render_template, request, url_for

app = Flask(__name__)
TODAY = date(2026, 9, 30)


# ---------------------------------------------------------------------------
# 공통: 앱 이름, 메뉴 (kit/base.html 이 사용)
# ---------------------------------------------------------------------------
@app.context_processor
def inject_kit():
    return {
        "kit_app_name": "UI 키트 데모",
        "kit_home": url_for("index"),
        "kit_updated_at": "2026-09-30 14:00",
        "kit_user": "홍길동",
        "kit_nav": [
            {"title": "Samples", "links": [
                {"id": "lot", "label": "LOT 현황", "href": url_for("lot_dashboard")},
                {"id": "inventory", "label": "원부자재 재고", "href": url_for("inventory")},
                {"id": "staff", "label": "인력 현황", "href": url_for("staff")},
            ]},
            {"title": "Kit", "links": [
                {"id": "catalog", "label": "부품 카탈로그", "href": url_for("catalog")},
            ]},
        ],
    }


@app.route("/")
def index():
    return redirect(url_for("lot_dashboard"))


# ---------------------------------------------------------------------------
# 1) 대시보드형: LOT 현황
# ---------------------------------------------------------------------------
STEPS = ["입고", "Bump", "Die Attach", "Underfill", "Mold", "Grind", "Test"]
PRODUCTS = ["PKG-A12", "PKG-B08", "PKG-C16", "R&D <시험>"]
# 업무 상태 문구 → 키트 상태(의미 5종) 매핑은 앱이 정한다
LOT_STATUS = {"진행": "info", "지연": "warning", "HOLD": "danger", "완료": "success", "대기": "neutral"}
MEMOS = ["", "", "", "장비 PM 대기", "재작업 검토", "", "고객 \"A&B\" 확인 <긴급>", "", "Q'26 샘플", "", "", ""]


def build_lots(n=180, seed=7):
    rnd = random.Random(seed)
    lots = []
    for i in range(n):
        st = rnd.choices(list(LOT_STATUS), weights=[12, 4, 2, 5, 3])[0]
        step_i = len(STEPS) - 1 if st == "완료" else (0 if st == "대기" else rnd.randint(0, len(STEPS) - 2))
        prog = 100 if st == "완료" else (0 if st == "대기" else round((step_i + rnd.random()) / len(STEPS) * 100))
        due = TODAY + timedelta(days=(-rnd.randint(1, 4) if st == "지연" else rnd.randint(-2, 10)))
        lots.append({
            "lot_id": f"ER26A{i + 1:04d}",           # ER26A0009 < ER26A0010 (자연 정렬 확인용)
            "product": rnd.choice(PRODUCTS),
            "step": STEPS[step_i],
            "status": st,
            "progress": prog,
            "days": rnd.randint(0, 21),
            "due": due.isoformat(),
            "memo": rnd.choice(MEMOS),
        })
    return lots


LOTS = build_lots()


def lot_filters():
    return {k: request.args.get(k, "").strip() for k in ("product", "step", "status", "q")}


def filter_lots(f):
    rows = LOTS
    if f["product"]:
        rows = [r for r in rows if r["product"] == f["product"]]
    if f["step"]:
        rows = [r for r in rows if r["step"] == f["step"]]
    if f["status"]:
        rows = [r for r in rows if r["status"] == f["status"]]
    if f["q"]:
        q = f["q"].upper()
        rows = [r for r in rows if q in r["lot_id"].upper()]
    return rows


@app.route("/lot")
def lot_dashboard():
    f = lot_filters()
    rows = filter_lots(f)
    filtered = any(f.values())
    count = {s: sum(1 for r in rows if r["status"] == s) for s in LOT_STATUS}

    status_chart = {
        "type": "doughnut",
        "labels": list(LOT_STATUS),
        "series": [{"label": "LOT 수", "data": [count[s] for s in LOT_STATUS],
                    "colors": list(LOT_STATUS.values())}],
        "legend": "right",
    }
    wip_chart = {
        "type": "bar", "horizontal": True, "stacked": True, "unit": "",
        "labels": STEPS[:-1],
        "series": [
            {"label": s, "color": LOT_STATUS[s],
             "data": [sum(1 for r in rows if r["step"] == st and r["status"] == s) for st in STEPS[:-1]]}
            for s in ("진행", "지연", "HOLD")
        ] if rows else [],                      # 조회 결과가 없으면 차트는 '데이터 없음' 안내
    }

    start = TODAY - timedelta(days=3)
    gantt = {"start": start.isoformat(), "days": 8, "now": f"{TODAY.isoformat()}T14:00", "mono": True, "rows": []}
    rnd = random.Random(3)
    for r in rows[:8]:
        t = datetime.combine(start, datetime.min.time()) + timedelta(hours=rnd.randint(0, 20))
        segs = []
        for s in STEPS[: STEPS.index(r["step"]) + 1]:
            dur = timedelta(hours=rnd.randint(10, 30))
            is_current = s == r["step"] and r["status"] != "완료"
            segs.append({"from": t.isoformat(timespec="minutes"), "to": (t + dur).isoformat(timespec="minutes"),
                         "label": s, "status": LOT_STATUS[r["status"]] if is_current else "success"})
            t += dur
        segs.append({"from": t.isoformat(timespec="minutes"), "to": (t + timedelta(hours=30)).isoformat(timespec="minutes"),
                     "label": "계획", "status": "plan"})
        gantt["rows"].append({"label": r["lot_id"], "segs": segs})

    rnd = random.Random(11)
    heat = {"rows": STEPS[1:], "cols": ["월", "화", "수", "목", "금", "토", "일"],
            "values": [[None if (j == 6 and i % 3 == 0) else rnd.randint(62, 99) for j in range(7)] for i in range(len(STEPS) - 1)],
            "min": 60, "max": 100, "unit": "%"}

    return render_template(
        "kit/samples/lot_dashboard.html", kit_active="lot", kit_title="LOT 현황",
        f=f, filtered=filtered, rows=rows, total=len(LOTS), count=count,
        steps=STEPS, products=PRODUCTS, statuses=list(LOT_STATUS), lot_status=LOT_STATUS,
        status_chart=status_chart, wip_chart=wip_chart, gantt=gantt, heat=heat,
    )


@app.route("/api/lot/trend")
def api_lot_trend():
    """차트 명세를 URL로 받아오는 예시 (전체 기준). ?delay=초 로 로딩 상태를 볼 수 있다."""
    time.sleep(min(float(request.args.get("delay", 0) or 0), 5))
    weeks = [f"W{w}" for w in range(31, 40)]
    rate = [81.2, 83.0, 82.4, 85.1, 86.9, 86.2, 88.4, 89.0, 90.3]
    return jsonify({
        "type": "line", "labels": weeks, "unit": "%", "min": 70, "max": 100,
        "series": [
            {"label": "자동화율", "data": rate, "color": "series-1", "fill": True},
            {"label": "목표", "data": [90] * len(weeks), "color": "neutral", "dashed": True},
        ],
    })


@app.route("/api/demo/broken")
def api_demo_broken():
    """차트 로딩 실패 안내를 보여주기 위한 데모 엔드포인트"""
    return jsonify({"error": "demo"}), 500


# ---------------------------------------------------------------------------
# 2) 목록형: 원부자재 재고
# ---------------------------------------------------------------------------
CATEGORIES = ["기판", "솔더볼", "언더필", "몰드 컴파운드", "테이프"]
WAREHOUSES = ["A동 1층", "A동 2층", "B동 자동창고"]
STOCK_STATUS = {"정상": "success", "부족": "danger", "과다": "info", "유효기간 임박": "warning"}
PAGE_SIZE = 20


def build_materials(n=137, seed=21):
    rnd = random.Random(seed)
    names = {"기판": ["Substrate 2L", "Substrate 4L", "Core 기판"], "솔더볼": ["SAC305 Ø0.25", "SAC305 Ø0.30"],
             "언더필": ["CUF-A", "MUF \"Low-α\""], "몰드 컴파운드": ["EMC G-700", "EMC <Green>"], "테이프": ["BG Tape", "Dicing Tape & Reel"]}
    items = []
    for i in range(n):
        cat = rnd.choice(CATEGORIES)
        safety = rnd.choice([200, 500, 1000, 2000])
        qty = int(safety * rnd.uniform(0.2, 2.6))
        exp_days = rnd.randint(3, 200)
        if exp_days < 20:
            st = "유효기간 임박"
        elif qty < safety:
            st = "부족"
        elif qty > safety * 2.2:
            st = "과다"
        else:
            st = "정상"
        items.append({
            "code": f"RM-{i + 1:04d}",
            "name": rnd.choice(names[cat]),
            "category": cat,
            "warehouse": rnd.choice(WAREHOUSES),
            "qty": qty,
            "safety": safety,
            "fill": min(100, round(qty / safety * 100)),
            "received": (TODAY - timedelta(days=rnd.randint(0, 60))).isoformat(),
            "expires": (TODAY + timedelta(days=exp_days)).isoformat(),
            "status": st,
        })
    return items


MATERIALS = build_materials()


def inventory_rows():
    f = {k: request.args.get(k, "").strip() for k in ("category", "warehouse", "status", "q")}
    rows = MATERIALS
    if f["category"]:
        rows = [r for r in rows if r["category"] == f["category"]]
    if f["warehouse"]:
        rows = [r for r in rows if r["warehouse"] == f["warehouse"]]
    if f["status"]:
        rows = [r for r in rows if r["status"] == f["status"]]
    if f["q"]:
        q = f["q"].lower()
        rows = [r for r in rows if q in r["code"].lower() or q in r["name"].lower()]
    return f, rows


@app.route("/inventory")
def inventory():
    f, rows = inventory_rows()
    pages = max(1, -(-len(rows) // PAGE_SIZE))
    try:
        page = min(max(1, int(request.args.get("page", 1))), pages)
    except ValueError:
        page = 1
    page_rows = rows[(page - 1) * PAGE_SIZE: page * PAGE_SIZE]
    summary = {
        "all_total": len(MATERIALS),
        "total": len(rows),
        "short": sum(1 for r in rows if r["status"] == "부족"),
        "expiring": sum(1 for r in rows if r["status"] == "유효기간 임박"),
        "qty": sum(r["qty"] for r in rows),
    }
    return render_template(
        "kit/samples/inventory_list.html", kit_active="inventory", kit_title="원부자재 재고",
        f=f, filtered=any(f.values()), rows=page_rows, page=page, pages=pages, page_size=PAGE_SIZE,
        summary=summary, categories=CATEGORIES, warehouses=WAREHOUSES, stock_status=STOCK_STATUS,
    )


@app.route("/inventory.csv")
def inventory_csv():
    _, rows = inventory_rows()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["품목코드", "품목명", "분류", "창고", "현재고", "안전재고", "최근 입고일", "유효기한", "상태"])
    for r in rows:
        w.writerow([r["code"], r["name"], r["category"], r["warehouse"], r["qty"], r["safety"], r["received"], r["expires"], r["status"]])
    return Response("﻿" + buf.getvalue(), mimetype="text/csv; charset=utf-8",
                    headers={"Content-Disposition": "attachment; filename=inventory.csv"})


# ---------------------------------------------------------------------------
# 3) 입력/상세형: 인력 현황
# ---------------------------------------------------------------------------
TEAMS = ["공정기술", "설비기술", "품질", "생산관리"]
SHIFTS = ["주간", "A조", "B조", "C조"]
STAFF_STATUS = {"근무": "success", "교육": "info", "휴가": "neutral", "지원 필요": "warning"}
STAFF = [
    {"id": f"E{1000 + i}", "name": n, "team": TEAMS[i % 4], "shift": SHIFTS[i % 4], "status": list(STAFF_STATUS)[i % 4 if i % 5 else 0],
     "phone": f"010-{2000 + i * 37:04d}-{5000 + i * 91:04d}", "joined": (date(2015, 3, 2) + timedelta(days=i * 211)).isoformat(),
     "certs": (i * 3) % 7, "note": ["", "야간 교대 선호", "", "<장비> 자격 갱신 예정", "", "R&D \"TF\" 겸직", ""][i % 7],
     "trainings": [{"date": "2026-08-12", "title": "안전 교육", "hours": 4}] if i % 2 else []}
    for i, n in enumerate(["김민준", "이서연", "박도윤", "최지우", "정하준", "강서윤", "조은우", "윤지아",
                           "장시우", "임하은", "한유준", "오수아", "서지호", "신예린"])
]


def staff_by_id(sid):
    for s in STAFF:
        if s["id"] == sid:
            return s
    return None


def validate_staff(form):
    errors = {}
    name = form.get("name", "").strip()
    if not name:
        errors["name"] = "이름을 입력하세요."
    elif len(name) > 20:
        errors["name"] = "이름은 20자 이하로 입력하세요."
    if form.get("team") not in TEAMS:
        errors["team"] = "소속을 목록에서 고르세요."
    phone = form.get("phone", "").strip()
    digits = phone.replace("-", "")
    if not (digits.isdigit() and 10 <= len(digits) <= 11):
        errors["phone"] = "연락처는 010-1234-5678 형식으로 입력하세요."
    try:
        datetime.strptime(form.get("joined", ""), "%Y-%m-%d")
    except ValueError:
        errors["joined"] = "입사일을 날짜로 입력하세요."
    return errors


@app.route("/staff", methods=["GET", "POST"])
def staff():
    sid = request.args.get("id") or STAFF[0]["id"]
    person = staff_by_id(sid)
    if person is None:
        abort(404)
    errors, form = {}, dict(person)
    tab = request.args.get("tab", "info")
    if request.method == "POST":
        form = {k: request.form.get(k, "") for k in ("name", "team", "shift", "phone", "joined", "note")}
        errors = validate_staff(form)
        tab = "edit"
        if not errors:
            person.update({k: form[k].strip() for k in form})
            return redirect(url_for("staff", id=sid, saved=1))
    return render_template(
        "kit/samples/staff_detail.html", kit_active="staff", kit_title="인력 현황",
        staff=STAFF, person=person, form=form, errors=errors, tab=tab,
        teams=TEAMS, shifts=SHIFTS, staff_status=STAFF_STATUS, saved=request.args.get("saved"),
    )


@app.route("/staff/<sid>/training", methods=["POST"])
def staff_training(sid):
    person = staff_by_id(sid) or abort(404)
    title = request.form.get("title", "").strip()[:40]
    try:
        hours = max(1, min(40, int(request.form.get("hours", "0"))))
    except ValueError:
        hours = 0
    day = request.form.get("date", "")
    if title and hours and day:
        person["trainings"].append({"date": day, "title": title, "hours": hours})
        return redirect(url_for("staff", id=sid, tab="training", saved=1))
    return redirect(url_for("staff", id=sid, tab="training", saved="error"))


@app.route("/api/staff/save", methods=["POST"])
def api_staff_save():
    """인라인 편집 저장 API. 값에 '실패'가 들어 있으면 실패를 돌려준다 (실패 시연용)."""
    time.sleep(0.4)
    body = request.get_json(silent=True) or {}
    person = staff_by_id(str(body.get("id", "")))
    field, value = body.get("field"), str(body.get("value", ""))
    if person is None or field not in ("note",):
        return jsonify({"ok": False, "error": "저장할 수 없는 항목입니다."}), 400
    if "실패" in value:
        return jsonify({"ok": False, "error": "데모: '실패'가 포함된 값은 거부합니다."}), 422
    if len(value) > 100:
        return jsonify({"ok": False, "error": "100자 이하로 입력하세요."}), 422
    person[field] = value
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# 4) 부품 카탈로그
# ---------------------------------------------------------------------------
@app.route("/catalog")
def catalog():
    try:
        page = max(1, min(12, int(request.args.get("page", 3))))
    except ValueError:
        page = 3
    sample_rows = [
        {"id": "ER26A0010", "name": "Bump", "qty": 1200, "rate": 91.5, "date": "2026-09-28", "status": "success", "label": "완료"},
        {"id": "ER26A0009", "name": "Mold <2차>", "qty": 85, "rate": 64.0, "date": "2026-10-02", "status": "warning", "label": "지연"},
        {"id": "ER26A0100", "name": "A&B \"Test\"", "qty": 9, "rate": 12.3, "date": "2026-09-30", "status": "danger", "label": "HOLD"},
        {"id": "ER26A0001", "name": "Die Attach", "qty": 30500, "rate": 100, "date": "2026-09-15", "status": "info", "label": "진행"},
        {"id": "ER26A0002", "name": "Grind", "qty": 0, "rate": 0, "date": "", "status": "neutral", "label": "대기"},
    ]
    chart_bar = {"type": "bar", "labels": ["월", "화", "수", "목", "금"],
                 "series": [{"label": "투입", "data": [12, 19, 15, 22, 18]}, {"label": "완료", "data": [10, 17, 16, 18, 20]}]}
    chart_empty = {"type": "bar", "labels": [], "series": [{"label": "없음", "data": []}]}
    gantt = {"start": "2026-09-28", "days": 5, "now": "2026-09-30T14:00", "mono": True, "rows": [
        {"label": "ER26A0001", "segs": [{"from": "2026-09-28T06:00", "to": "2026-09-29T12:00", "label": "Bump", "status": "success"},
                                        {"from": "2026-09-29T12:00", "to": "2026-10-01T02:00", "label": "Mold", "status": "info"},
                                        {"from": "2026-10-01T02:00", "to": "2026-10-02T12:00", "label": "Test", "status": "plan"}]},
        {"label": "ER26A0002", "segs": [{"from": "2026-09-28T10:00", "to": "2026-09-30T20:00", "label": "Underfill 지연", "status": "warning"}]},
        {"label": "ER26A0003", "segs": [{"from": "2026-09-29T00:00", "to": "2026-09-30T08:00", "label": "HOLD <검토>", "status": "danger"}]},
    ]}
    heat = {"rows": ["Bump", "Mold", "Test"], "cols": ["월", "화", "수", "목", "금"],
            "values": [[95, 88, 72, 91, None], [64, 70, 81, 85, 90], [99, 97, 93, 60, 78]], "min": 60, "max": 100, "unit": "%"}
    toast = request.args.get("toast")
    return render_template(
        "kit/samples/catalog.html", kit_active="catalog", kit_title="부품 카탈로그",
        page=page, pages=12, sample_rows=sample_rows, chart_bar=chart_bar, chart_empty=chart_empty,
        gantt=gantt, heat=heat, toast=toast if toast in ("success", "warning", "danger", "info", "neutral") else None,
    )


if __name__ == "__main__":
    # 로컬 확인용 설정. 사내 서버 배포에는 debug=True 를 쓰지 않는다.
    app.run(host="127.0.0.1", port=8050, debug=True)
