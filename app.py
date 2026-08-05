"""학교 업무 도우미 웹 UI (5-1 채팅 + 5-2 역할별 권한)

설계 핵심: main.py의 응답생성(도구 호출 루프)을 복사하지 않고 import로 재사용.
- main.py 맨 아래 if __name__ == "__main__" 가드 덕분에 CLI 루프는 실행되지 않고
  함수·메뉴판·system 프롬프트만 가져와진다.
- 기록은 두 벌: 메시지들(화면용 — 사람이 읽는 말풍선)과 history(모델용 —
  주문서·도구 결과까지 포함, main.py와 같은 형식). 내용·형식이 달라서 분리.
- 5-2: 역할은 반드시 session_state(세션별 저장소)에 산다. 모듈 전역에 두면
  서버 프로세스가 하나라서 모든 접속자가 공유 — 마지막 로그인이 전원의 권한을
  덮어쓰는 사고가 난다.
"""

import streamlit as st

import main  # 응답생성 + 권한표 + SYSTEM_PROMPT 재사용

# ── 로그인 게이트: 역할이 정해지기 전엔 채팅 화면을 그리지 않는다 ─────────────
if "역할" not in st.session_state:
    st.title("학교 업무 도우미 — 로그인")
    이름 = st.text_input("이름")
    역할선택 = st.selectbox("역할", sorted(main.역할별_허용도구))  # 권한표가 곧 선택지
    if st.button("로그인") and 이름.strip():
        st.session_state.역할 = 역할선택      # 보안 값은 세션에 — 이후 코드가 직접 주입
        st.session_state.사용자명 = 이름.strip()
        st.session_state.메시지들 = []
        st.session_state.history = []
        st.rerun()   # 즉시 재실행 → 이번엔 게이트를 통과해 채팅 화면이 그려진다
    st.stop()        # 로그인 전이면 이 재실행은 여기서 끝 — 아래 코드는 안 돈다

# ── 여기부터는 로그인된 세션만 도달 ──────────────────────────────────────
with st.sidebar:
    st.write(f"👤 {st.session_state.사용자명} · **{st.session_state.역할}**")
    if st.button("로그아웃"):
        st.session_state.clear()  # 세션 저장소 전체 비움 → 다음 재실행에서 로그인 화면
        st.rerun()

st.title("학교 업무 도우미")
st.caption("급식(나이스) · 출결/성적(교내 DB) · 생활기록부 규정(RAG)")

for msg in st.session_state.메시지들:
    with st.chat_message(msg["role"]):
        st.write(msg["text"])

user_input = st.chat_input("예: 2026-07-10 급식 / 2학년 1반 결석 / 봉사활동 기재 방법")
if user_input:  # LLM 호출은 반드시 이 블록 안 — 입력 없는 재실행마다 과금되지 않게
    with st.chat_message("user"):
        st.write(user_input)  # 이번 화면에는 즉시 그리되, 기록(메시지들)은 커밋 시점에

    # 트랜잭션 패턴: 원본(history)은 두고 "사본"에서 작업 → 성공해야만 커밋.
    # 원리는 롤백과 같은 목표(완결된 질문-답변 쌍만 유지)인데 더 강하다 —
    # 예외가 나든, 생성 도중 사용자가 재실행을 유발해 이 코드가 끊기든,
    # 커밋 줄에 도달하지 못하면 원본은 아예 건드려지지 않았으므로 항상 무결.
    작업기록 = list(st.session_state.history)  # 얕은 복사면 충분 — 응답생성은 append만 한다
    작업기록.append({"role": "user", "parts": [{"text": user_input}]})

    with st.chat_message("assistant"):
        with st.spinner("생각 중..."):  # 도구 루프가 도는 동안 스피너 (스트리밍은 추후)
            try:
                response = main.응답생성(
                    작업기록, st.session_state.역할, st.session_state.사용자명
                )
                답변 = response.text if response else None  # None = 5바퀴 소진(미완성)
            except Exception as e:
                답변 = None
                st.error(f"응답 생성에 실패했습니다. 잠시 후 다시 시도해주세요.\n\n상세: {e}")
        if 답변:
            st.write(답변)
        else:  # 예외 없이 답변만 없는 경우(소진 등)도 이번 화면에 바로 안내
            st.write("⚠️ 답변을 만들지 못했습니다. 질문을 나눠서 다시 시도해주세요.")

    # 화면 기록도 여기(호출 이후)서만 추가 — 생성 도중 실행이 끊기면 화면·모델 기록
    # 둘 다 이 질문을 모르는 상태로 남아 서로 어긋나지 않는다 (다시 물으면 그만)
    if 답변:
        작업기록.append({"role": "model", "parts": [{"text": 답변}]})
        st.session_state.history = 작업기록  # ← 커밋 (성공 시에만 원본 교체)
        st.session_state.메시지들.append({"role": "user", "text": user_input})
        st.session_state.메시지들.append({"role": "assistant", "text": 답변})
    else:
        # history는 커밋 안 함 = 롤백. 화면 기록에는 질문+실패 사실을 남긴다
        st.session_state.메시지들.append({"role": "user", "text": user_input})
        st.session_state.메시지들.append(
            {"role": "assistant", "text": "⚠️ 답변을 만들지 못했습니다. 질문을 나눠서 다시 시도해주세요."}
        )
