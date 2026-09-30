"""
kit_installer.txt 생성기.  실행: python tools/build_installer.py

- 코드 파일(텍스트)만 담는다. 폰트·Chart.js 는 담지 않고, 설치 시 어디서 받는지 안내한다.
- 메일 전달을 고려해 모든 줄을 900자 이하로 유지한다 (파일 내용은 base64 76자 줄로 저장).
"""
import base64
import hashlib
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

INCLUDE = [
    "AGENTS.md",
    "app_demo.py",
    "templates/kit/base.html",
    "templates/kit/macros.html",
    *sorted(str(p.relative_to(ROOT)).replace("\\", "/") for p in (ROOT / "templates/kit/samples").glob("*.html")),
    "static/kit/css/kit.css",
    "static/kit/js/kit.js",
    "static/kit/js/kit-chart.js",
    *sorted(str(p.relative_to(ROOT)).replace("\\", "/") for p in (ROOT / "static/kit/js/kit-optional").glob("*.js")),
    "tools/verify_kit.py",
]
RENAME = {"README.md": "KIT_README.md"}      # 기존 프로젝트의 README.md 와 겹치지 않게

HEADER = r'''# -*- coding: utf-8 -*-
# =====================================================================
#  Flask 공통 UI 키트 — 설치 스크립트 ({today}, 파일 {count}개)
#
#  사용법
#   1) 이 파일 이름을 kit_installer.py 로 바꾼다
#   2) Flask 프로젝트 폴더(app.py, templates/, static/ 가 있는 곳)에서:
#        python kit_installer.py            기존 파일은 건너뜀
#        python kit_installer.py --force    기존 파일도 덮어씀
#        python kit_installer.py --dry-run  무엇을 쓸지만 출력
#   3) 폰트·Chart.js 는 이 스크립트에 들어 있지 않다. 실행 후 안내를 따라 넣는다.
#      (차트를 쓰지 않는 화면, 폰트가 없는 환경에서도 키트는 동작한다)
#   4) 적용 방법: KIT_README.md
# =====================================================================
import base64, hashlib, os, sys

FORCE = "--force" in sys.argv
DRY = "--dry-run" in sys.argv
FILES = {{}}   # 경로 -> (sha256, base64 줄 목록)
'''

FOOTER = r'''

def main():
    written, skipped = [], []
    for path, (digest, lines) in FILES.items():
        data = base64.b64decode("".join(lines))
        if hashlib.sha256(data).hexdigest() != digest:
            print("손상됨 (메일 전달 중 내용이 바뀐 것 같습니다):", path)
            sys.exit(1)
        if os.path.exists(path) and not FORCE:
            skipped.append(path)
            continue
        written.append(path)
        if DRY:
            continue
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(path, "wb") as fp:
            fp.write(data)
    if not DRY:
        for d in ("static/kit/vendor", "static/kit/fonts"):
            os.makedirs(d, exist_ok=True)

    print("%s %d개" % ("쓸 파일" if DRY else "설치", len(written)))
    for p in written:
        print("  +", p)
    if skipped:
        print("이미 있어서 건너뜀 %d개 (덮어쓰려면 --force)" % len(skipped))
        for p in skipped:
            print("  =", p)
        if "AGENTS.md" in skipped:
            print("  ※ 기존 AGENTS.md 가 있습니다. 키트 규칙을 기존 파일 맨 위에 직접 합쳐 주세요.")

    print("""
직접 넣어야 하는 파일 (없어도 동작하지만, 있으면 적용됨)
  static/kit/vendor/chart.umd.min.js   Chart.js v4 — https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js
                                        (없으면 차트 자리에 '차트를 불러오지 못했습니다' 안내, 나머지 기능은 정상)
  static/kit/fonts/PretendardVariable.woff2
                                        https://github.com/orioncactus/pretendard/releases (web/variable/woff2)
                                        (없으면 맑은 고딕)
  static/kit/fonts/D2Coding.woff2      https://github.com/naver/d2codingfont/releases 또는 npm 'd2coding' 의 d2coding-subset.woff2
                                        (없으면 Consolas)
  각 LICENSE 파일도 같은 폴더에 함께 두세요. GitHub 저장소 형태에는 모두 포함되어 있습니다.

확인: pip install flask 후  python app_demo.py  →  http://127.0.0.1:8050  (로컬 확인용)
""")


if __name__ == "__main__":
    main()
'''


def main():
    out = [HEADER.format(today=date.today().isoformat(), count=len(INCLUDE) + len(RENAME))]
    items = [(p, p) for p in INCLUDE] + list(RENAME.items())
    for src, dst in items:
        data = (ROOT / src).read_bytes()
        b64 = base64.b64encode(data).decode("ascii")
        lines = [b64[i:i + 76] for i in range(0, len(b64), 76)]
        out.append(f"\nFILES[{dst!r}] = ({hashlib.sha256(data).hexdigest()!r}, [\n")
        out.extend(f'    "{ln}",\n' for ln in lines)
        out.append("])\n")
    out.append(FOOTER)
    text = "".join(out)
    assert max(len(ln) for ln in text.splitlines()) < 900
    (ROOT / "kit_installer.txt").write_text(text, encoding="utf-8", newline="\n")
    print(f"kit_installer.txt: 파일 {len(items)}개, {len(text) // 1024} KB")


if __name__ == "__main__":
    main()
