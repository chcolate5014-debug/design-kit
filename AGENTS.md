# 화면 작성 규칙 (Flask 공통 UI 키트)

**기존 공통 클래스와 컴포넌트만 조립한다. 디자인 시스템 확장은 사용자가 명시적으로 요청했을 때만 한다.
필요한 부품이 없으면 가장 가까운 기존 부품으로 만들고, 부족한 부품을 사용자에게 보고한다.**

업무 내용(메뉴 이름, 컬럼, 검색 조건, 상태 문구, 계산, 조회·저장 로직)은 제한하지 않는다. 제한하는 것은 화면을 그리는 방법이다.

## 반드시
1. 새 화면은 `{% extends "kit/base.html" %}` 와 `{% import "kit/macros.html" as kit with context %}` 로 시작하고 `{% block content %}` 안에만 쓴다.
2. 본문 최상위는 `<div class="stack">` 이다. 순서 예: `page-head` → `filterbar` → `kpi-band` → `grid` / `panel`.
3. 부품 사용법은 `templates/kit/samples/` 를 그대로 따른다. 모든 부품은 `catalog.html` 에 있다.
   - 대시보드형: `lot_dashboard.html` · 목록형: `inventory_list.html` · 입력/상세형: `staff_detail.html`
4. 상태 배지·진행률·집계 기준·빈 결과·차트·데이터 전달은 매크로를 쓴다:
   `kit.badge()` `kit.progress()` `kit.basis()` `kit.empty()` `kit.loading()` `kit.error_state()` `kit.options()` `kit.pagination()` `kit.chart()` `kit.data()` `kit.scripts()`
5. 상태는 의미 5종만: `success` `warning` `danger` `info` `neutral`. 업무 문구("지연", "HOLD")를 무엇에 매핑할지는 앱(파이썬)에서 정한다. 배지에는 항상 글자를 넣는다.
6. 메뉴는 `kit_nav`, 현재 메뉴는 `kit_active`, 앱 이름은 `kit_app_name`, 제목은 `kit_title` 로 넘긴다 (예: `app_demo.py` 의 `context_processor`).
7. 조회는 `<form class="filterbar" method="get">`. 조회 후 입력값 유지(`value="{{ f.q }}"`, `kit.options(items, f.x)`), 초기화 링크, 결과 건수(`role="status"`), 빈 결과를 모두 넣는다.
8. 모든 입력에 `<label for>` 를 단다. 필수는 `<span class="req" aria-hidden="true">*</span>` + `aria-required="true"`, 오류는 `aria-invalid="true"` + `.field-error`.
9. 숫자 열은 `class="num"`, 코드값(LOT ID, 품목코드, 사번)은 `class="mono"`.
10. 차트는 `kit.chart(label, spec)` 로만 만든다. spec 형식은 `static/kit/js/kit-chart.js` 맨 위 주석. 색은 `"series-1"`~`"series-6"` 또는 상태 이름으로만 지정한다.

## 금지
- `style="..."` 인라인 스타일, 새 `<style>` 태그, 새 CSS 파일, 다른 CSS 프레임워크(Bootstrap, Tailwind 등)
- hex·rgb 같은 임의 색상. 색은 `kit.css` 토큰에만 있다
- 페이지 안 `<script>` 코드. 데이터는 `kit.data()` / `kit.chart()` 로만 넘기고(`|tojson`), JS는 `kit.scripts("chart", "gantt", "heatmap", "edit", "search")` 로만 로드한다
- `|safe`, `Markup()`, `innerHTML`, `insertAdjacentHTML`, `document.write`
- 연결 안 된 버튼, `href="#"`, 동작하지 않는 요소. 구현하거나 뺀다
- `static/kit/`, `templates/kit/base.html`, `templates/kit/macros.html` 수정 (사용자가 요청한 경우만)

## 부족한 부품을 만났을 때
가장 가까운 부품으로 화면을 완성한 뒤, 답변 끝에 아래 형식으로 보고한다.
```
[키트 부족] 필요한 부품: ○○ / 대신 사용: ○○ / 이유: ○○
```
