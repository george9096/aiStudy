"""학교 업무 도우미 CLI (1~3단계 누적: 멀티턴 + system 프롬프트 + 도구 호출)

3단계에서 바뀐 것:
- tools.py의 함수 3개를 모델에게 "메뉴판"으로 선언
- 모델이 주문서(function_call)를 내면 → 실행 → 결과를 대화록에 넣고 재호출하는 루프
- 스트리밍은 잠시 뺐다 (도구 루프의 원리가 잘 보이게. 웹 UI 붙일 때 재결합)
"""

import os
from datetime import date

from dotenv import load_dotenv
from google import genai
from google.genai import types

import tools  # 우리가 만든 도구 함수들 (급식조회 / 출결조회 / 성적조회)
import 감사  # 5-3: 도구 호출의 영구 기록 (audit.db)

load_dotenv()
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

SYSTEM_PROMPT = """너는 학교 교직원(교사·행정실)을 위한 업무 도우미다.

원칙:
- 급식·학생 출결·성적 질문에는 반드시 도구를 사용해 실제 데이터로 답한다.
  도구 결과에 없는 내용을 지어내지 않는다.
- 규정·절차 질문에는 search_rules로 기재요령을 검색해서, 근거 쪽 번호와 함께 답한다.
  검색 결과에 없는 내용은 지어내지 말고, 학교별 학칙 확인이 필요한 부분은 그렇다고 말한다.
- 답변은 간결한 존댓말. 인사말과 이모지는 생략한다."""
# 모델은 "오늘"이 며칠인지 모른다 — 날짜는 응답생성()이 "호출 시점"에 붙인다.
# 모듈 상수에 f-string으로 박으면 import 순간 값으로 고정되어, 자정을 넘겨
# 살아있는 서버(Streamlit·배포판)가 어제 날짜로 답하는 조용한 버그가 된다.


# ── 권한표: 역할별 허용 도구 (화이트리스트 — 표에 없으면 거부가 기본) ────────
역할별_허용도구 = {
    "교사": {"get_meal", "get_attendance", "get_grades", "find_student", "search_rules"},
    "행정실": {"get_meal", "search_rules"},  # 학생 개인정보(출결·성적·검색)는 접근 불가
}

# ── 메뉴판: 모델에게 선언하는 도구 목록 ──────────────────────────
# 함수 이름은 영문만 허용(API 제약) → 실제 한글 함수와는 TOOL_FUNCTIONS로 연결.
# description이 핵심이다 — 모델은 이 설명을 읽고 "언제 이 도구를 쓸지" 판단한다.
전체_선언 = [
    {
        "name": "get_meal",
        "description": "지정한 날짜의 학교 급식(조식/중식/석식) 메뉴와 칼로리를 조회한다",
        "parameters": {
            "type": "object",
            "properties": {"날짜": {"type": "string", "description": "YYYY-MM-DD 형식"}},
            "required": ["날짜"],
        },
    },
    {
        "name": "get_attendance",
        "description": "해당 학년/반에서 결석이 일정 횟수 이상인 학생 목록을 조회한다",
        "parameters": {
            "type": "object",
            "properties": {
                "학년": {"type": "integer"},
                "반": {"type": "integer"},
                "최소결석수": {"type": "integer", "description": "이 횟수 이상 결석한 학생만 (기본 1)"},
            },
            "required": ["학년", "반"],
        },
    },
    {
        "name": "get_grades",
        "description": "학생 이름으로 과목별 성적을 조회한다",
        "parameters": {
            "type": "object",
            "properties": {"학생이름": {"type": "string"}},
            "required": ["학생이름"],
        },
    },
    {
        "name": "find_student",
        "description": "학생 이름으로 소속(학년/반/번호)을 찾는다. "
                       "이름만 알고 학년/반이 필요할 때 먼저 이 도구를 사용",
        "parameters": {
            "type": "object",
            "properties": {"이름": {"type": "string"}},
            "required": ["이름"],
        },
    },
    {
        "name": "search_rules",
        "description": "학교생활기록부 기재요령(교육부 규정집)에서 관련 조항을 검색한다. "
                       "생활기록부 기재 방법, 출결 처리, 전출입, 성적 기록 등 규정·절차 질문에 사용",
        "parameters": {
            "type": "object",
            "properties": {"질문": {"type": "string", "description": "찾고 싶은 규정 내용을 문장으로"}},
            "required": ["질문"],
        },
    },
]


def 메뉴판생성(역할: str) -> types.Tool:
    """1차 방어: 역할이 허용된 도구만 담은 메뉴판 — 금지 도구는 존재조차 모르게"""
    허용 = 역할별_허용도구[역할]
    return types.Tool(function_declarations=[선언 for 선언 in 전체_선언 if 선언["name"] in 허용])

TOOL_FUNCTIONS = {  # 주문서의 이름 → 실제 실행할 함수
    "get_meal": tools.급식조회,
    "get_attendance": tools.출결조회,
    "get_grades": tools.성적조회,
    "find_student": tools.학생검색,
    "search_rules": tools.규정검색,
}

def 응답생성(history: list, 역할: str, 사용자: str = "미상"):
    """도구 호출 루프 — 3단계의 심장 + 5-2 권한 검문 + 5-3 감사 기록.

    모델이 주문서를 내는 동안 [권한 검사 → 실행 → 결과 append → 재호출]을 반복하고,
    주문서 없는 응답(=최종 답변)이 나오면 반환한다. 5바퀴 소진 시 None 반환.
    역할은 세션(시스템)이 주입한다 — 모델·사용자 입력을 거치면 안 되는 보안 값.
    """
    config = types.GenerateContentConfig(
        # 프롬프트의 역할 표기는 UX용(거부 사유를 정중히 설명하게) — 방어가 아니다.
        # 방어는 코드가 한다: 메뉴판 필터(1차) + 실행 직전 검문(2차)
        system_instruction=(
            SYSTEM_PROMPT
            + f"\n오늘 날짜: {date.today().isoformat()}"  # 호출 시점 평가 — 항상 진짜 오늘
            + f"\n현재 사용자 역할: {역할}"
        ),
        tools=[메뉴판생성(역할)],  # 1차 방어
    )
    for _ in range(5):  # 안전장치: 최대 5바퀴 — 무한 주문 방지 (하네스의 역할)
        response = client.models.generate_content(
            model="gemini-3.5-flash-lite",  # flash 일일 할당량(20회) 소진 → 별도 주머니인 lite로
            contents=history,
            config=config,
        )

        if not response.function_calls:
            return response  # 주문서가 없다 = 최종 답변이다

        # 주문서도 대화록에 남긴다 (다음 호출 때 모델이 "내가 뭘 시켰는지" 알아야 하므로)
        history.append(response.candidates[0].content)

        # 주문서 실행 — 모델이 한 번에 여러 장 낼 수도 있다
        결과들 = []
        for call in response.function_calls:
            print(f"  [도구 실행] ({역할}) {call.name} {dict(call.args)}")  # 뒷단 동작을 눈에 보이게
            # 2차 방어: 실행 직전 검문. 1차(메뉴판)가 뚫려도 — 프롬프트 인젝션,
            # 모델이 지어낸 도구명, 권한표 갱신 누락 — 어떤 주문이든 여기서 걸린다.
            # 덤: 지어낸 이름은 TOOL_FUNCTIONS 조회 전에 걸리므로 KeyError도 안 난다.
            허용됨 = call.name in 역할별_허용도구.get(역할, set())
            if not 허용됨:
                결과 = {"오류": f"권한 없음 — {역할} 역할은 {call.name} 도구를 사용할 수 없다"}
            else:
                함수 = TOOL_FUNCTIONS[call.name]
                try:
                    결과 = 함수(**call.args)
                    # ↑ ** = 딕셔너리를 키워드 인자로 풀기: {"날짜": "..."} → 함수(날짜="...")
                except Exception as e:
                    결과 = {"오류": f"도구 실행 실패: {e}"}
                    # ↑ 도구가 죽어도(네트워크 장애 등) 프로그램은 안 죽는다.
                    #   에러를 "데이터"로 모델에게 주면 모델이 상황을 말로 설명해준다

            # 5-3 감사 기록 — 허용/거부 불문, 모든 주문이 지나가는 초크 포인트.
            # 결과는 요약()을 거쳐 원문 없이 남는다 (로그 = 제2의 유출 지점 방지)
            감사.기록(사용자, 역할, call.name, dict(call.args), 허용됨, 감사.요약(결과))
            결과들.append(
                types.Part.from_function_response(name=call.name, response={"결과": 결과})
            )

        # 실행 결과를 role="user"로 대화록에 추가 → 다음 바퀴에서 모델이 읽는다
        # ("tool"은 모델(서버)에 따라 거부됨 — user는 어디서나 통하는 공식 문서 방식)
        history.append(types.Content(role="user", parts=결과들))

    return None  # 5바퀴 소진 — 마지막 응답은 진행 멘트+주문서일 수 있어 답변으로 내보내지 않는다


if __name__ == "__main__":
    print("학교 업무 도우미 v0.3 — 권한 장착 (종료: exit)")

    역할 = ""
    while 역할 not in 역할별_허용도구:  # 화이트리스트에 있는 역할만 통과
        역할 = input(f"역할을 선택하세요 {sorted(역할별_허용도구)}: ").strip()
    사용자 = input("이름을 입력하세요: ").strip() or "CLI사용자"

    history = []
    while True:
        user_input = input("\n나: ")
        if user_input == "exit":
            break

        # 트랜잭션 패턴: 사본에서 작업, 성공 시에만 커밋 — history엔 완결된 쌍만 남는다
        작업기록 = history + [{"role": "user", "parts": [{"text": user_input}]}]
        response = 응답생성(작업기록, 역할, 사용자)
        if response and response.text:  # 소진(None)·빈 응답이면 커밋 금지 — 다음 턴이 400으로 죽는다
            print(f"AI: {response.text}")
            작업기록.append({"role": "model", "parts": [{"text": response.text}]})
            history = 작업기록  # ← 커밋
        else:
            print("AI: (답변 생성 실패 — 도구 호출 한도 초과 가능성. 질문을 나눠서 다시 해보세요)")