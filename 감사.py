"""감사 로그 (5-3): 도구 호출의 영구 기록 — 누가·언제·무엇을·허용/거부·결과요약

설계 원칙:
- 기록 지점은 초크 포인트(main.응답생성 루프) 한 곳 — 모든 도구 호출이 지나간다.
- 결과 "원문"은 기록하지 않는다. 성적·출결이 로그에 쌓이면 로그 파일 자체가
  제2의 유출 지점이 된다 → 요약(성공/오류, 건수)만 남긴다.
- 인자는 기록한다 — "누가 누구의 성적을 조회했나"가 감사의 목적이므로.
- school.db(업무 데이터)와 분리된 별도 파일. audit.db는 커밋하지 않는다(.gitignore).
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "audit.db"


def _연결():
    # 호출할 때마다 새로 연결 — Streamlit은 세션마다 다른 스레드에서 돌 수 있는데,
    # sqlite 연결 객체는 스레드 간 공유가 안 되므로 "그때그때 열고 닫기"가 안전하다
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS 감사로그 (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            시각     TEXT NOT NULL,
            사용자   TEXT NOT NULL,
            역할     TEXT NOT NULL,
            도구     TEXT NOT NULL,
            인자     TEXT NOT NULL,   -- json 문자열
            허용     INTEGER NOT NULL, -- 1 허용 / 0 거부
            결과요약 TEXT NOT NULL
        )
    """)
    return conn


def 기록(사용자: str, 역할: str, 도구: str, 인자: dict, 허용: bool, 결과요약: str):
    conn = _연결()
    conn.execute(
        "INSERT INTO 감사로그 (시각, 사용자, 역할, 도구, 인자, 허용, 결과요약) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (datetime.now().isoformat(timespec="seconds"), 사용자, 역할, 도구,
         json.dumps(인자, ensure_ascii=False), int(허용), 결과요약),
    )
    conn.commit()
    conn.close()


def 요약(결과) -> str:
    """도구 결과를 원문 없이 요약 — 개인정보가 로그로 새지 않게 하는 관문"""
    if isinstance(결과, dict):
        if "오류" in 결과:
            return f"오류: {결과['오류']}"
        if "안내" in 결과:
            return f"안내: {결과['안내']}"
        return f"성공 (키: {', '.join(결과)})"
    if isinstance(결과, list):
        return f"성공 (목록 {len(결과)}건)"
    return "성공"


# ── 단독 실행 시 간이 열람기: python 감사.py ─────────────────────────
if __name__ == "__main__":
    conn = _연결()
    rows = conn.execute(
        "SELECT 시각, 사용자, 역할, 도구, 인자, 허용, 결과요약 FROM 감사로그 ORDER BY id DESC LIMIT 20"
    ).fetchall()
    conn.close()

    if not rows:
        print("감사 로그가 비어 있습니다")
    for 시각, 사용자, 역할, 도구, 인자, 허용, 요약문 in rows:
        상태 = "허용" if 허용 else "거부⛔"
        print(f"{시각} | {사용자}({역할}) | {상태} | {도구} {인자} | {요약문}")
