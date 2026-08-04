import os                       # 파이썬 기본 모듈. 환경변수를 읽을 때 씀
from dotenv import load_dotenv  # .env 파일을 읽어주는 라이브러리
from google import genai        # Gemini 공식 SDK
from google.genai import types  # 호출 옵션(config)을 만들 때 쓰는 타입들

SYSTEM_PROMPT = """너는 학교 교직원(교사·행정실)을 위한 업무 도우미다.

원칙:
- 학교 규정·학사 업무 질문에 답한다. 규정 답변은 일반론과 "학교별 학칙 확인이
  필요한 부분"을 구분해서 말하고, 근거 없이 단정하지 않는다.
- 너는 실시간 데이터(급식, 학사일정, 학생 정보)에 접근할 수 없다.
  관련 질문에는 지어내지 말고 접근 불가라고 밝힌다.
- 학생 개인정보 질문에는 답하지 않고, 권한 확인이 필요한 정보라고 안내한다.
- 사용자가 문서(공문·규정·가정통신문)를 주면: 요약 → 해야 할 일 → 기한 순으로 정리한다.
- 답변은 간결한 존댓말. 인사말과 이모지는 생략한다."""
# ↑ system 프롬프트는 매 요청마다 전송된다 = 길수록 매번 비싸진다. 그래서 압축 유지.
#   3단계에서 급식·학사일정(나이스 API)·학생 DB 조회가 "도구"로 붙으면
#   위의 "접근 불가" 항목들이 실제 조회로 바뀐다.

load_dotenv()
# ↑ 같은 폴더의 .env 파일을 열어서, 그 안의 내용을 "환경변수"로 등록해줌
#   이걸 안 하면 파이썬은 .env 파일의 존재를 모름

api_key = os.environ["GEMINI_API_KEY"]
# ↑ 방금 등록된 환경변수 중에서 GEMINI_API_KEY 값을 꺼내 변수에 담음

client = genai.Client(api_key=api_key)
# ↑ 키를 들고 있는 "클라이언트" 생성. 이제 이 client로 구글 서버에 요청을 보냄
#   Spring에서 WebClient 만들어두고 재사용하는 것과 같은 개념

print("학교 업무 도우미 v0.1 (종료하려면 exit 입력)")

history = []
# ↑ 대화록. API 서버는 아무것도 기억하지 않으므로(stateless),
#   기억이 필요하면 클라이언트인 우리가 이렇게 직접 들고 다녀야 한다

while True:  # 무한 루프 — break를 만날 때까지 계속 돈다
    user_input = input("\n나: ")

    if user_input == "exit":
        break

    # 1) 내 말을 대화록에 추가. role="user"가 "이건 사용자가 한 말"이라는 표시
    history.append({"role": "user", "parts": [{"text": user_input}]})

    # 2) 방금 말 한 줄이 아니라 "대화록 전체"를 보낸다
    #    모델은 매 요청마다 이 대화록을 처음부터 끝까지 다시 읽고 다음 답을 만든다
    # generate_content → generate_content_stream
    # 완성된 응답 하나가 아니라, 생성되는 족족 날아오는 "조각(chunk)들의 흐름"이 반환된다
    stream = client.models.generate_content_stream(
        model="gemini-3.5-flash",
        contents=history,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,  # 매 요청에 깔리는 상위 지시문
        ),
    )

    # 3) 조각을 받는 즉시 화면에 뿌리면서, 동시에 변수에 이어붙인다
    print("AI: ", end="", flush=True)
    full_text = ""  # history에 넣으려면 결국 "전체 텍스트"가 필요하므로 누적해둔다
    for chunk in stream:
        if chunk.text:  # 텍스트가 없는 조각(마지막 메타데이터 등)도 섞여 오므로 걸러준다
            print(chunk.text, end="", flush=True)
            # end=""  → 조각마다 줄바꿈하지 않기
            # flush=True → 버퍼에 쌓아두지 말고 즉시 화면에 내보내기 (이게 없으면 뚝뚝 끊겨 보임)
            full_text += chunk.text
    print()  # 답변이 끝났으니 줄바꿈 한 번

    # 4) 누적해둔 전체 답변을 대화록에 추가 (여기는 스트리밍이든 아니든 동일)
    history.append({"role": "model", "parts": [{"text": full_text}]})