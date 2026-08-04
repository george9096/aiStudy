"""도구 함수 모음 (3단계: Function Calling)

여기 함수들은 LLM과 무관한 평범한 파이썬 함수다.
- 급식조회   → 나이스 공개 API (진짜 데이터)
- 출결조회   → school.db (가짜 데이터)
- 성적조회   → school.db (가짜 데이터)

main.py가 이 함수들을 모델에게 "메뉴판"으로 선언하고,
모델이 주문서를 내면 실행해서 결과를 돌려준다.
설계 원칙: SELECT만, ? 바인딩만 (A안 — 모델에게 자유 SQL을 주지 않는다)
"""

import os
import sqlite3
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

NEIS_KEY = os.environ["NEIS_API_KEY"]
SCHOOL_CODE = os.environ["SCHOOL_CODE"]      # 달성고 7240058
EDU_OFFICE_CODE = "D10"                       # 대구광역시교육청

DB_PATH = Path(__file__).parent / "school.db"
# ↑ "이 파일이 있는 폴더의 school.db" — 어디서 실행해도 같은 DB를 찾게 함


def 급식조회(날짜: str) -> dict:
    """지정한 날짜의 학교 급식 메뉴를 조회한다. 날짜 형식: YYYY-MM-DD"""
    r = requests.get(
        "https://open.neis.go.kr/hub/mealServiceDietInfo",
        params={
            "KEY": NEIS_KEY,
            "Type": "json",
            "ATPT_OFCDC_SC_CODE": EDU_OFFICE_CODE,
            "SD_SCHUL_CODE": SCHOOL_CODE,
            "MLSV_YMD": 날짜.replace("-", ""),  # API는 20260710 형식을 원함
        },
        timeout=10,
    )
    data = r.json()

    # 데이터가 없으면 mealServiceDietInfo 키 없이 RESULT.CODE만 온다
    # INFO-200 = "정상 요청인데 데이터 없음" / ERROR-* = 키 오류 등 진짜 실패
    # 이 둘을 구분하지 않으면 키가 잘못돼도 "급식 없음"으로 조용히 삼켜진다
    if "mealServiceDietInfo" not in data:
        code = data.get("RESULT", {}).get("CODE", "")
        if code.startswith("ERROR"):
            return {"오류": f"나이스 API 오류 ({code}) — API 키/파라미터 확인 필요"}
        return {"안내": f"{날짜} 급식 정보가 없습니다 (주말/방학/미등록)"}

    # 하루에 조식/중식/석식 여러 건이 올 수 있어서 전부 반환
    return {
        "날짜": 날짜,
        "급식": [
            {
                "구분": row["MMEAL_SC_NM"],  # 조식/중식/석식
                "메뉴": row["DDISH_NM"].replace("<br/>", ", "),
                "칼로리": row["CAL_INFO"],
            }
            for row in data["mealServiceDietInfo"][1]["row"]
        ],
    }


def 출결조회(학년: int, 반: int, 최소결석수: int = 1) -> list[dict]:
    """해당 학년/반에서 결석이 최소결석수 이상인 학생 목록을 조회한다."""
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        """
        SELECT 학생.이름, COUNT(*) AS 결석수
        FROM 출결 JOIN 학생 ON 학생.id = 출결.학생_id
        WHERE 출결.구분 = '결석' AND 학생.학년 = ? AND 학생.반 = ?
        GROUP BY 학생.id HAVING 결석수 >= ?
        ORDER BY 결석수 DESC
        """,
        (학년, 반, 최소결석수),  # ? 바인딩 — 값이 SQL 문법으로 해석될 수 없게
    ).fetchall()
    conn.close()
    return [{"이름": 이름, "결석수": 결석수} for 이름, 결석수 in rows]


def 성적조회(학생이름: str) -> list[dict]:
    """학생 이름으로 과목별 성적을 조회한다. 동명이인이 있으면 모두 반환된다."""
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        """
        SELECT 학생.학년, 학생.반, 학생.이름, 성적.과목, 성적.점수
        FROM 성적 JOIN 학생 ON 학생.id = 성적.학생_id
        WHERE 학생.이름 = ?
        ORDER BY 학생.학년, 학생.반, 성적.과목
        """,
        (학생이름,),
    ).fetchall()
    conn.close()
    return [
        {"학년": 학년, "반": 반, "이름": 이름, "과목": 과목, "점수": 점수}
        for 학년, 반, 이름, 과목, 점수 in rows
    ]


# ── 단독 실행 시 자체 테스트 ─────────────────────────────────
# "python tools.py"로 직접 실행하면 아래가 돌고,
# main.py에서 "import tools"로 가져다 쓸 땐 아래는 실행되지 않는다.
# (예전에 예고했던 그 관용구 — __name__은 직접 실행일 때만 "__main__"이 된다)
if __name__ == "__main__":
    print("=== 급식조회 (2026-07-10, 학기 중) ===")
    print(급식조회("2026-07-10"))

    print("\n=== 급식조회 (2026-08-04, 방학) ===")
    print(급식조회("2026-08-04"))

    print("\n=== 출결조회 (2학년 1반, 결석 3회 이상) ===")
    print(출결조회(2, 1, 3))

    print("\n=== 성적조회 (최하은) ===")
    print(성적조회("최하은"))
