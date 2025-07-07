# experiment_potens_api.py

import streamlit as st
import os
from dotenv import load_dotenv
from io import BytesIO

# modules 폴더에서 ai_service 모듈 임포트
# 프로젝트 루트에서 실행할 경우 sys.path에 modules가 추가되어야 하지만,
# Streamlit 실행 시에는 일반적으로 자동으로 인식됩니다.
from modules import ai_service

# --- Streamlit 앱 시작 ---
st.set_page_config(layout="wide", page_title="Potens.dev API 파일 전송 실험")

st.title("🧪 Potens.dev API 파일 전송 실험")
st.info("이 섹션은 Potens.dev AI API가 긴 텍스트 파일 내용을 직접 프롬프트로 처리할 수 있는지 실험하기 위한 것입니다.")

# --- Potens.dev AI API 키 설정 ---
load_dotenv() # .env 파일 로드
POTENS_API_KEY = os.getenv("POTENS_API_KEY")

if not POTENS_API_KEY:
    st.error("🚨 오류: .env 파일에 'POTENS_API_KEY'가 설정되지 않았습니다. Potens.dev AI 기능을 사용할 수 없습니다.")
    st.stop() # API 키 없으면 앱 실행 중단

with st.expander("파일 전송 실험 시작"):
    uploaded_file = st.file_uploader("텍스트 파일 (.txt)을 업로드하세요.", type=["txt"])
    
    if uploaded_file is not None:
        file_content = uploaded_file.read().decode("utf-8")
        st.write(f"업로드된 파일 내용 (처음 500자):")
        st.code(file_content[:500] + "..." if len(file_content) > 500 else file_content)
        st.write(f"총 파일 크기: {len(file_content)} 자")

        # AI에게 파일 내용을 요약해달라는 프롬프트
        prompt_for_file = f"다음은 업로드된 텍스트 파일의 내용입니다. 이 내용을 간결하게 요약해 주세요.\n\n{file_content}"

        if st.button("파일 내용으로 AI 호출 실험"):
            with st.spinner("AI 호출 중... (파일 내용 전송)"):
                # ai_service.call_potens_api_raw 함수를 직접 사용하여 원본 응답 확인
                # retry_ai_call을 사용하지 않고 raw 호출을 통해 오류를 더 명확히 파악
                response_from_file_api = ai_service.call_potens_api_raw(prompt_for_file, POTENS_API_KEY)
                
                if "error" in response_from_file_api:
                    st.error(f"AI 호출 실패: {response_from_file_api['error']}")
                    if "raw_response" in response_from_file_api:
                        st.json(response_from_file_api["raw_response"])
                else:
                    st.success("AI 호출 성공!")
                    st.subheader("AI 응답:")
                    st.write(response_from_file_api["text"])
                    st.subheader("AI 원본 응답 (JSON):")
                    st.json(response_from_file_api["raw_response"])
                    
                    # 응답이 너무 길면 잘라서 보여주기
                    if len(response_from_file_api["text"]) > 1000:
                        st.info("AI 응답이 길어 일부만 표시합니다.")
                        st.write(response_from_file_api["text"][:1000] + "...")

