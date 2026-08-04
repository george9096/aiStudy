"""가짜 학생 DB 생성 스크립트 (3단계 준비물)

실행하면 school.db (SQLite 파일)가 만들어진다. 전부 합성 데이터 — 실데이터 아님.
sqlite3는 파이썬에 내장돼 있어서 pip install 불필요 (서버 없이 파일 하나로 도는 DB).

설계 원칙: 공공 정보(학교·급식·일정)는 나이스 API가 담당하므로 DB에 두지 않는다.
DB에는 나이스가 공개하지 않는 것 = 학생 개인정보(합성)만 둔다.
"""

import random
import sqlite3

random.seed(42)  # 시드 고정 = 누가 언제 돌려도 같은 데이터 (재현 가능)

conn = sqlite3.connect("school.db")
cur = conn.cursor()

# ── 테이블 생성 ──────────────────────────────────────────────
cur.executescript("""
DROP TABLE IF EXISTS 출결;
DROP TABLE IF EXISTS 성적;
DROP TABLE IF EXISTS 학생;

CREATE TABLE 학생 (
    id     INTEGER PRIMARY KEY,
    이름   TEXT NOT NULL,
    학년   INTEGER NOT NULL,
    반     INTEGER NOT NULL,
    번호   INTEGER NOT NULL
);

CREATE TABLE 성적 (
    id       INTEGER PRIMARY KEY,
    학생_id  INTEGER NOT NULL REFERENCES 학생(id),
    학기     TEXT NOT NULL,      -- 예: '2026-1'
    과목     TEXT NOT NULL,
    점수     INTEGER NOT NULL
);

CREATE TABLE 출결 (
    id       INTEGER PRIMARY KEY,
    학생_id  INTEGER NOT NULL REFERENCES 학생(id),
    날짜     TEXT NOT NULL,      -- 'YYYY-MM-DD'
    구분     TEXT NOT NULL,      -- 결석 / 지각 / 조퇴
    사유     TEXT NOT NULL       -- 질병 / 무단 / 기타
);
""")

# ── 가짜 학생 50여 명 생성 ────────────────────────────────────
성_목록 = ["김", "이", "박", "최", "정", "강", "조", "윤", "장", "임"]
이름_목록 = ["민준", "서연", "도윤", "지우", "하준", "서준", "지민", "수아",
           "예준", "하은", "시우", "채원", "유준", "지아", "은우", "다은"]

학생들 = []
for 학년 in (1, 2, 3):
    for 반 in (1, 2):
        인원 = random.randint(8, 10)
        for 번호 in range(1, 인원 + 1):
            이름 = random.choice(성_목록) + random.choice(이름_목록)
            학생들.append((이름, 학년, 반, 번호))

cur.executemany("INSERT INTO 학생 (이름, 학년, 반, 번호) VALUES (?, ?, ?, ?)", 학생들)

# ── 성적: 학생마다 5과목 × 1학기 ─────────────────────────────
과목들 = ["국어", "영어", "수학", "과학", "사회"]
for 학생_id in range(1, len(학생들) + 1):
    기본기 = random.randint(50, 90)  # 학생마다 실력대를 두고 과목별로 흔들기
    for 과목 in 과목들:
        점수 = max(0, min(100, 기본기 + random.randint(-15, 15)))
        cur.execute(
            "INSERT INTO 성적 (학생_id, 학기, 과목, 점수) VALUES (?, '2026-1', ?, ?)",
            (학생_id, 과목, 점수),
        )

# ── 출결: 1학기(3/2~7/17) 중 무작위. 일부 학생은 결석이 잦도록 ──
def 랜덤_날짜():
    월 = random.randint(3, 7)
    일 = random.randint(1, 28)
    return f"2026-{월:02d}-{일:02d}"

for 학생_id in range(1, len(학생들) + 1):
    성실도 = random.random()
    건수 = random.randint(4, 8) if 성실도 < 0.15 else random.randint(0, 3)
    for _ in range(건수):
        구분 = random.choices(["결석", "지각", "조퇴"], weights=[5, 3, 2])[0]
        사유 = random.choices(["질병", "무단", "기타"], weights=[6, 2, 2])[0]
        cur.execute(
            "INSERT INTO 출결 (학생_id, 날짜, 구분, 사유) VALUES (?, ?, ?, ?)",
            (학생_id, 랜덤_날짜(), 구분, 사유),
        )

conn.commit()

# ── 생성 결과 확인 ───────────────────────────────────────────
print("생성 완료: school.db")
for 테이블 in ("학생", "성적", "출결"):
    건수 = cur.execute(f"SELECT COUNT(*) FROM {테이블}").fetchone()[0]
    print(f"  {테이블}: {건수}건")

print("\n[검증] 결석 3회 이상 학생 (도우미 대표 질문이 답 가능한지):")
rows = cur.execute("""
    SELECT 학생.학년, 학생.반, 학생.이름, COUNT(*) AS 결석수
    FROM 출결 JOIN 학생 ON 학생.id = 출결.학생_id
    WHERE 출결.구분 = '결석'
    GROUP BY 학생.id HAVING 결석수 >= 3
    ORDER BY 결석수 DESC
""").fetchall()
for 학년, 반, 이름, 결석수 in rows:
    print(f"  {학년}학년 {반}반 {이름} — 결석 {결석수}회")

conn.close()
