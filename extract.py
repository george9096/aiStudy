"""뉴스 텍스트 -> 키-밸류 데이터 (2단계: Structured Output)"""

import os
from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from enum import Enum

load_dotenv()
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])


class 재료상태(str, Enum):
    """Enum = 답을 이 셋 중 하나로 제한. 모델이 '반쯤진행형' 같은 걸 못 만든다"""
    진행형 = "진행형"   # 변동성이 이어질 재료
    소진 = "소진"       # 원샷 이벤트, 내일부턴 조용
    불명 = "불명"


# 원하는 데이터 모양을 클래스로 정의 (Java의 DTO)
class 종목분석(BaseModel):
    종목명: str
    변동률: float | None = Field(description="기사에 %가 명시된 경우만. 없으면 null")
    # float 만 쓰면 기사에 숫자가 없을 때 모델이 0.0을 지어낸다 (0%로 오해됨)
    # float | None = 비워도 된다는 허가. Field 설명으로 언제 비울지 알려준다
    원인: str = Field(description="움직인 이유를 한 문장으로")
    재료: 재료상태 = Field(description="이 재료로 변동성이 더 이어질지 판단")


NEWS = """
엔비디아는 신형 GPU 수요 전망에 4.2% 상승했다.
테슬라는 중국 판매 둔화 우려로 3.1% 하락했다.
애플은 자사주 매입 발표로 1.5% 올랐으나 일회성 이벤트라는 평가가 나온다.
"""


response = client.models.generate_content(
    model="gemini-3.5-flash",
    contents=f"이 기사의 종목들을 뽑아라: {NEWS}",
    config=types.GenerateContentConfig(
        response_mime_type="application/json",  # 줄글 말고 JSON으로
        response_schema=list[종목분석],          # 위 클래스 모양의 배열로
    ),
)


for 종목 in response.parsed:
    print(f"{종목.종목명} {종목.변동률}% [{종목.재료.value}] {종목.원인}")

# 데이터가 됐으니 이런 게 가능해진다 (줄글이면 불가능)
살아있는_상승 = [종목.종목명 for 종목 in response.parsed
              if 종목.재료 == 재료상태.진행형 and 종목.변동률 > 0]
print(f"\n재료가 살아있는 상승 종목: {살아있는_상승}")
