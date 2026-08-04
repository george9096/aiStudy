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

load_dotenv()
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

SYSTEM_PROMPT = f"""너는 학교 교직원(교사·행정실)을 위한 업무 도우미다.
오늘 날짜: {date.today().isoformat()}

원칙:
- 급식·학생 출결·성적 질문에는 반드시 도구를 사용해 실제 데이터로 답한다.
  도구 결과에 없는 내용을 지어내지 않는다.
- 규정 질문에는 일반론과 "학교별 학칙 확인이 필요한 부분"을 구분해서 답한다.
- 답변은 간결한 존댓말. 인사말과 이모지는 생략한다."""
# ↑ 모델은 "오늘"이 며칠인지 모른다 — 그래서 날짜를 프롬프트에 넣어준다
#   (학생 개인정보 권한 제어는 5단계에서 "코드로" 추가할 예정)


# ── 메뉴판: 모델에게 선언하는 도구 목록 ──────────────────────────
# 함수 이름은 영문만 허용(API 제약) → 실제 한글 함수와는 TOOL_FUNCTIONS로 연결.
# description이 핵심이다 — 모델은 이 설명을 읽고 "언제 이 도구를 쓸지" 판단한다.
메뉴판 = types.Tool(function_declarations=[
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
])

TOOL_FUNCTIONS = {  # 주문서의 이름 → 실제 실행할 함수
    "get_meal": tools.급식조회,
    "get_attendance": tools.출결조회,
    "get_grades": tools.성적조회,
}

CONFIG = types.GenerateContentConfig(
    system_instruction=SYSTEM_PROMPT,
    tools=[메뉴판],
)


def 응답생성(history: list):
    """도구 호출 루프 — 3단계의 심장.

    모델이 주문서를 내는 동안 [실행 → 결과 append → 재호출]을 반복하고,
    주문서 없는 응답(=최종 답변)이 나오면 반환한다.
    """
    for _ in range(5):  # 안전장치: 최대 5바퀴 — 무한 주문 방지 (하네스의 역할)
        response = client.models.generate_content(
            model="gemini-3.5-flash",
            contents=history,
            config=CONFIG,
        )

        if not response.function_calls:
            return response  # 주문서가 없다 = 최종 답변이다

        # 주문서도 대화록에 남긴다 (다음 호출 때 모델이 "내가 뭘 시켰는지" 알아야 하므로)
        history.append(response.candidates[0].content)

        # 주문서 실행 — 모델이 한 번에 여러 장 낼 수도 있다
        결과들 = []
        for call in response.function_calls:
            print(f"  [도구 실행] {call.name} {dict(call.args)}")  # 뒷단 동작을 눈에 보이게
            함수 = TOOL_FUNCTIONS[call.name]
            try:
                결과 = 함수(**call.args)
                # ↑ ** = 딕셔너리를 키워드 인자로 풀기: {"날짜": "..."} → 함수(날짜="...")
            except Exception as e:
                결과 = {"오류": f"도구 실행 실패: {e}"}
                # ↑ 도구가 죽어도(네트워크 장애 등) 프로그램은 안 죽는다.
                #   에러를 "데이터"로 모델에게 주면 모델이 상황을 말로 설명해준다
            결과들.append(
                types.Part.from_function_response(name=call.name, response={"결과": 결과})
            )

        # 실행 결과를 role="tool"로 대화록에 추가 → 다음 바퀴에서 모델이 읽는다
        history.append(types.Content(role="tool", parts=결과들))

    return response  # 5바퀴를 다 써도 주문이 이어지면 마지막 응답이라도 반환


if __name__ == "__main__":
    print("학교 업무 도우미 v0.2 — 도구 장착 (종료: exit)")

    history = []
    while True:
        user_input = input("\n나: ")
        if user_input == "exit":
            break

        history.append({"role": "user", "parts": [{"text": user_input}]})
        response = 응답생성(history)
        print(f"AI: {response.text}")
        history.append({"role": "model", "parts": [{"text": response.text}]})
