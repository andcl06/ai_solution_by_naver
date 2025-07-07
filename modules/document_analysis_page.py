# modules/document_analysis_page.py

import streamlit as st
import os # 환경 변수 접근을 위해 필요
from loguru import logger # 로깅을 위해 필요

# --- 모듈 임포트 ---
from modules import ai_service # AI 서비스 모듈
from modules import document_processor # 새로 만든 문서 처리 모듈

from langchain.memory import StreamlitChatMessageHistory # Langchain Streamlit 통합


def document_analysis_page():
    """
    문서 기반 QA 챗봇 및 특약 생성 기능을 제공하는 페이지입니다.
    """
    st.title("📄 _Private Data :red[QA Chat]_")

    # 메인으로 돌아가기 버튼
    if st.button("⬅️ 메인으로"):
        st.session_state.page = "landing"
        st.rerun()
    st.markdown("---") # 버튼 아래 구분선 추가

    # Potens API 키 로드 (main_app.py에서 로드된 것을 사용)
    POTENS_API_KEY = os.getenv("POTENS_API_KEY")
    if not POTENS_API_KEY:
        st.error("🚨 오류: Potens.dev API 키가 설정되지 않았습니다. .env 파일을 확인해주세요.")
        return # API 키 없으면 페이지 기능 비활성화

    # 세션 상태 초기화
    if "vectordb" not in st.session_state:
        st.session_state.vectordb = None
    if 'messages' not in st.session_state:
        st.session_state.messages = [{
            "role": "assistant",
            "content": "안녕하세요! 문서 기반 질문을 해보세요."
        }]
    if "docs" not in st.session_state: # 특약 생성 기능에서 필요
        st.session_state.docs = []


    with st.sidebar:
        selected_menu = st.selectbox("📌 메뉴 선택", ["최신 QA", "특약 생성"])
        uploaded_files = st.file_uploader("📎 문서 업로드", type=['pdf', 'docx', 'pptx', 'txt'], accept_multiple_files=True)
        process = st.button("📚 문서 처리")

    if process:
        if not uploaded_files:
            st.warning("문서를 업로드해주세요.")
            st.stop()

        with st.spinner("문서를 처리 중입니다..."):
            docs = document_processor.get_text(uploaded_files)
            chunks = document_processor.get_text_chunks(docs)
            vectordb = document_processor.get_vectorstore(chunks)
            st.session_state.vectordb = vectordb
            st.session_state.docs = docs # 'docs' 세션 상태에 저장 (특약 생성에서 사용)
            st.success("✅ 문서 분석 완료! 메뉴를 선택해 진행하세요.")
            st.session_state.messages = [{ # 문서 처리 후 메시지 초기화
                "role": "assistant",
                "content": "문서 분석이 완료되었습니다. 이제 질문하거나 특약을 생성할 수 있습니다."
            }]
            st.rerun()


    if selected_menu == "최신 QA":
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        history = StreamlitChatMessageHistory(key="chat_messages") # StreamlitChatMessageHistory 초기화

        if query := st.chat_input("질문을 입력해주세요."):
            st.session_state.messages.append({"role": "user", "content": query})

            with st.chat_message("user"):
                st.markdown(query)

            with st.chat_message("assistant"):
                if not st.session_state.vectordb:
                    st.warning("먼저 문서를 업로드하고 처리해야 합니다.")
                    st.stop()

                with st.spinner("답변 생성 중..."):
                    retriever = st.session_state.vectordb.as_retriever(search_type="similarity", k=3)
                    docs = retriever.get_relevant_documents(query)

                    context = "\n\n".join([doc.page_content for doc in docs])
                    final_prompt = f"""다음 문서를 참고하여 질문에 답하세요.

[문서 내용]:
{context}

[질문]:
{query}

[답변]:
"""
                    # ai_service 모듈의 retry_ai_call 함수 사용
                    response_dict = ai_service.retry_ai_call(final_prompt, POTENS_API_KEY)
                    answer = ai_service.clean_ai_response_text(response_dict.get("text", response_dict.get("error", "AI 응답 실패.")))

                    st.markdown(answer)
                    with st.expander("📄 참고 문서"):
                        for doc_ref in docs:
                            st.markdown(f"**출처**: {doc_ref.metadata.get('source', '알 수 없음')}")
                            st.markdown(doc_ref.page_content)

                    st.session_state.messages.append({"role": "assistant", "content": answer})

    elif selected_menu == "특약 생성":
        st.subheader("📑 보험 특약 생성기")

        if "docs" not in st.session_state or not st.session_state.docs:
            st.warning("문서를 먼저 업로드하고 처리해주세요.")
            st.stop()

        all_text = "\n\n".join([doc.page_content for doc in st.session_state.docs])
        prompt = f"""
너는 자동차 보험을 설계하고 있는 보험사 직원이야.  
다음 조건에 따라 자동차 보험 **특약**을 생성해줘.

[기본 조건]
- 자동차 보험 표준약관을 참고해줘.
- 아래의 구성 항목을 반드시 포함해줘:
  1. 특약의 명칭
  2. 특약의 목적
  3. 보장 범위
  4. 보험금 지급 조건
  5. 보험료 산정 방식
  6. 면책 사항
  7. 특약의 적용 기간
  8. 기타 특별 조건

[기획 목적]
- 이 특약은 **보험 상품 기획 초기 단계**에서 **트렌드 조사 및 방향성 도출에 도움**이 되는 목적으로 작성돼야 해.
- 창의적인 요소를 포함해도 좋지만, **실제 상품화 가능성**을 고려해서 구성해줘.
- 새로운 기술(예: 블랙박스, 자율주행, 스마트폰 앱 등)이나 최근 사회적 이슈(예: 고령 운전자 증가, 이륜차 배달 사고 등)를 반영해도 좋아.

[참고자료]
- 첨부된 자동차 보험 표준약관 문서를 분석하고, 그 구조 및 표현방식을 따라줘.

[표준약관 내용]
{all_text}

[결과]:
"""

        if st.button("🚀 특약 생성 시작"):
            with st.spinner("Potens API에 요청 중입니다..."):
                # ai_service 모듈의 retry_ai_call 함수 사용
                response_dict = ai_service.retry_ai_call(prompt, POTENS_API_KEY)
                answer = ai_service.clean_ai_response_text(response_dict.get("text", response_dict.get("error", "AI 응답 실패.")))

            st.markdown("### ✅ 생성된 특약")
            st.markdown(answer)
