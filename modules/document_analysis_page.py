# modules/document_analysis_page.py

import streamlit as st
import os # 환경 변수 접근을 위해 필요
from loguru import logger # 로깅을 위해 필요
from datetime import datetime # 파일명에 타임스탬프를 위해 추가

# --- 모듈 임포트 ---
from modules import ai_service # AI 서비스 모듈
from modules import document_processor # 새로 만든 문서 처리 모듈
from modules import database_manager # 데이터베이스 관리 모듈 임포트 (새로 추가)

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
    # 'generated_endorsement_text' 대신 'generated_endorsement_sections'로 변경하여 각 섹션별로 저장
    if 'generated_endorsement_sections' not in st.session_state:
        st.session_state.generated_endorsement_sections = {}
    # 새로 추가: 생성된 특약의 전체 텍스트를 저장할 세션 상태 (이제 데이터베이스와 동기화)
    if 'generated_endorsement_full_text' not in st.session_state:
        st.session_state['generated_endorsement_full_text'] = database_manager.get_latest_generated_endorsement() or "" # DB에서 불러오기


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
            st.session_state.generated_endorsement_sections = {} # 문서 처리 시 특약 초기화
            st.session_state['generated_endorsement_full_text'] = "" # 특약 전체 텍스트 초기화 (DB에도 반영 필요)
            database_manager.save_generated_endorsement("") # DB에서도 특약 초기화
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
        
        # 특약 구성 항목 정의 (협업자 파일에서 가져옴)
        sections = {
            "1. 특약의 명칭": "자동차 보험 표준약관을 참고하여 특약의 **명칭**을 작성해줘.",
            "2. 특약의 목적": "이 특약의 **목적**을 설명해줘.",
            "3. 보장 범위": "**보장 범위**에 대해 상세히 작성해줘.",
            "4. 보험금 지급 조건": "**보험금 지급 조건**을 구체적으로 작성해줘.",
            "5. 보험료 산정 방식": "**보험료 산정 방식**을 설명해줘.",
            "6. 면책 사항": "**면책 사항**에 해당하는 내용을 작성해줘.",
            "7. 특약의 적용 기간": "**적용 기간**을 명시해줘.",
            "8. 기타 특별 조건": "**기타 특별 조건**이 있다면 제안해줘."
        }

        if st.button("🚀 특약 생성 시작"):
            all_generated_sections = {} # 각 섹션별 답변을 저장할 딕셔너리
            full_text_for_download = "" # 다운로드용 전체 텍스트 (이제 세션 상태에도 저장)

            with st.spinner("Potens API에 순차적으로 요청 중입니다..."):
                for title, question in sections.items():
                    st.info(f"⏳ {title} 생성 중...")
                    prompt = f"""
너는 자동차 보험을 설계하고 있는 보험사 직원이야.
다음 조건에 따라 자동차 보험 특약의 '{title}'을 3~5줄 정도로 작성해줘.

[기획 목적]
- 이 특약은 보험 상품 기획 초기 단계에서 트렌드 조사 및 방향성 도출에 도움 되는 목적으로 작성돼야 해.
- 새로운 기술(예: 블랙박스, 자율주행 등)이나 최근 사회적 이슈(예: 고령 운전자 증가 등)를 반영해도 좋아.
- 표준약관 표현 방식을 따라줘.

[표준약관 내용]
{all_text}

[질문]
{question}

[답변]
"""
                    # ai_service 모듈의 retry_ai_call 함수 사용
                    response_dict = ai_service.retry_ai_call(prompt, POTENS_API_KEY)
                    answer = ai_service.clean_ai_response_text(response_dict.get("text", response_dict.get("error", "AI 응답 실패.")))
                    
                    all_generated_sections[title] = answer # 각 섹션별로 저장
                    full_text_for_download += f"#### {title}\n{answer.strip()}\n\n" # 다운로드용 텍스트에 추가

            st.session_state.generated_endorsement_sections = all_generated_sections # 세션 상태에 딕셔너리로 저장
            st.session_state['generated_endorsement_full_text'] = full_text_for_download # 새로 추가: 전체 특약 텍스트 세션 상태에 저장
            database_manager.save_generated_endorsement(full_text_for_download) # 데이터베이스에 특약 저장 (새로 추가)
            st.success("✅ 특약 생성 완료!")
            st.rerun() # 생성 완료 후 UI 업데이트를 위해 rerun

        # 생성된 특약이 세션 상태에 있으면 표시
        if st.session_state.generated_endorsement_sections:
            st.markdown("### 📄 최종 생성된 특약")
            # 세션 상태에 저장된 각 섹션을 반복하여 마크다운으로 표시
            full_text_for_download_display = "" # 화면 표시와 다운로드용 텍스트를 분리
            for title, content in st.session_state.generated_endorsement_sections.items():
                st.markdown(f"#### {title}") # 협업자 코드처럼 각 섹션 제목을 마크다운 헤더로
                st.write(content) # 각 섹션의 내용을 일반 텍스트로 표시하여 글자 크기 제어
                full_text_for_download_display += f"#### {title}\n{content.strip()}\n\n" # 다운로드용 텍스트 다시 구성

            # 다운로드 버튼 추가
            st.download_button(
                label="📥 특약 전체 다운로드 (.txt)",
                data=full_text_for_download_display, # 화면에 표시된 내용과 동일하게 다운로드
                file_name=f"생성된_보험_특약_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt", # 파일명에 타임스탬프 추가
                mime="text/plain"
            )
