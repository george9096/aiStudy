import os                       # 파이썬 기본 모듈. 환경변수를 읽을 때 씀
from dotenv import load_dotenv  # .env 파일을 읽어주는 라이브러리
from google import genai        # Gemini 공식 SDK

load_dotenv()
# ↑ 같은 폴더의 .env 파일을 열어서, 그 안의 내용을 "환경변수"로 등록해줌
#   이걸 안 하면 파이썬은 .env 파일의 존재를 모름

api_key = os.environ["GEMINI_API_KEY"]
# ↑ 방금 등록된 환경변수 중에서 GEMINI_API_KEY 값을 꺼내 변수에 담음

client = genai.Client(api_key=api_key)
# ↑ 키를 들고 있는 "클라이언트" 생성. 이제 이 client로 구글 서버에 요청을 보냄
#   Spring에서 WebClient 만들어두고 재사용하는 것과 같은 개념

response = client.models.generate_content(
    model="gemini-3.5-flash",  # 무료 티어로 쓸 수 있는 flash 계열의 안정 버전
    contents="LLM의 '토큰'이 뭔지 백엔드 개발자에게 세 문장으로 설명해줘",
)
# ↑ 이 한 줄이 실제 API 호출. 내부적으로는 구글 서버에 HTTPS POST 요청을
#   보내고 응답을 기다리는 것 — 외부 REST API 호출과 완전히 같은 일

print(response.text)  # 응답 중에서 텍스트만 출력
print(response)       # 응답 객체 통째로 출력 — 안에 뭐가 더 들었는지 구경용
 