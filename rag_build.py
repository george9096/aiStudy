"""RAG 1막: 색인 구축 (PDF → 텍스트 → 청크 → 임베딩 → 저장)

한 번만 실행하는 사전 준비 스크립트.
청킹 전략: 쪽(페이지) 단위 기반 — 조각마다 쪽 번호가 남아서 답변에 출처를 달 수 있다.
긴 쪽은 겹침(overlap)을 두고 분할, 내용이 거의 없는 쪽(표지·간지)은 버린다.
"""

import json
import os
import time

import numpy as np
from dotenv import load_dotenv
from google import genai
from google.genai import errors
from pypdf import PdfReader

load_dotenv()

PDF_PATH = r"docs\학교생활기록부_기재요령(고등학교).pdf"
INDEX_경로 = "docs\\index_chunks.json"   # 조각 원문 + 쪽 번호
VECTOR_경로 = "docs\\index_vectors.npy"  # 조각별 벡터 (403 × 3072 행렬)

최대길이 = 900   # 조각 하나의 최대 글자 수 (너무 크면: 검색이 뭉툭해지고 프롬프트가 비싸짐)
겹침 = 100       # 분할 경계에 걸친 문장이 잘리지 않게 앞 조각 꼬리를 다음 조각 머리에 중복
최소길이 = 50    # 이보다 짧은 쪽은 표지/간지로 보고 버림


def 긴쪽_분할(text: str) -> list[str]:
    """최대길이를 넘는 텍스트를 줄바꿈 근처에서 잘라 겹침을 두고 나눈다"""
    조각들 = []
    while len(text) > 최대길이:
        절단 = text.rfind("\n", 최대길이 - 300, 최대길이)  # 뒤쪽 300자 안의 줄바꿈에서 자르기
        if 절단 == -1:
            절단 = 최대길이  # 줄바꿈이 없으면 그냥 최대길이에서
        조각들.append(text[:절단])
        text = text[절단 - 겹침:]  # 겹침만큼 물고 다음 조각 시작
    조각들.append(text)
    return 조각들


def 청크만들기() -> list[dict]:
    reader = PdfReader(PDF_PATH)
    청크들 = []
    for 쪽번호, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        if len(text) < 최소길이:
            continue  # 표지, 간지, 빈 쪽 버림
        for 조각 in 긴쪽_분할(text):
            청크들.append({"쪽": 쪽번호, "내용": 조각.strip()})
    return 청크들


def 색인구축(청크들: list[dict]):
    """조각 전부를 임베딩해서 파일 2개로 저장 (조각 원문 json + 벡터 npy)"""
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    벡터들 = []
    for i in range(0, len(청크들), 50):  # API가 한 번에 받는 개수 제한이 있어 50개씩 묶어서
        묶음 = [c["내용"] for c in 청크들[i : i + 50]]

        for 시도 in range(1, 6):  # 429(요청 한도)를 만나면 기다렸다 같은 묶음 재시도
            try:
                result = client.models.embed_content(model="gemini-embedding-001", contents=묶음)
                break
            except errors.ClientError as e:
                if e.code == 429 and 시도 < 5:
                    print(f"  (429 한도 — 40초 대기 후 재시도 {시도}/5)")
                    time.sleep(40)
                else:
                    raise

        벡터들 += [e.values for e in result.embeddings]
        print(f"  임베딩 진행: {len(벡터들)}/{len(청크들)}")
        time.sleep(15)  # 무료 티어 분당 한도를 넘지 않게 묶음 사이 대기 (한 번만 도는 스크립트라 느긋하게)

    with open(INDEX_경로, "w", encoding="utf-8") as f:
        json.dump(청크들, f, ensure_ascii=False)
    np.save(VECTOR_경로, np.array(벡터들, dtype=np.float32))
    # ↑ 조각 i의 원문은 json의 i번째, 벡터는 행렬의 i번째 행 — 같은 순서로 저장이 약속


if __name__ == "__main__":
    청크들 = 청크만들기()
    길이들 = [len(c["내용"]) for c in 청크들]
    print(f"청크 수: {len(청크들)}개 / 길이: 평균 {sum(길이들)//len(길이들)}자, 최대 {max(길이들)}자")

    색인구축(청크들)
    print(f"\n저장 완료: {INDEX_경로}, {VECTOR_경로}")
    print(f"벡터 행렬 크기: {np.load(VECTOR_경로).shape}")
