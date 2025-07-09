# modules/landing_page.py

import streamlit as st

def landing_page():
    """로그인 후 사용자가 기능을 선택하는 랜딩 페이지를 렌더링합니다."""
    # 앱 이름과 환영 메시지
    st.title("✨ 트렌드 기반 특약생성 솔루션") # 앱 이름 명시
    st.subheader(f"👋 {st.session_state.username}님, 환영합니다!")
    st.markdown("---")

    # 앱 사용법 설명
    st.markdown("""
    이 솔루션은 최신 뉴스 트렌드를 분석하고, 이를 기반으로 자동차 보험 특약 개발을 위한 인사이트를 제공합니다.
    
    **주요 기능:**
    * **최신 트렌드 분석**: 특정 키워드로 네이버 뉴스를 수집하고, AI가 트렌드를 요약하여 차량 보험 관련 보고서를 생성합니다.
    * **문서 분석**: 업로드된 문서를 기반으로 질문에 답변하거나, 보험 특약을 생성할 수 있습니다.
    * **보고서 자동화**: 원하는 시간에 뉴스 트렌드 보고서와 생성된 특약을 자동으로 이메일로 전송합니다.
    
    아래 버튼을 클릭하여 원하는 기능으로 이동하세요!
    """)
    st.markdown("---")

    # 버튼을 가로로 배치 (크기 조절을 위해 use_container_width=False)
    col1, col2, col3 = st.columns(3) # 컬럼 3개로 변경

    with col1:
        # use_container_width=False로 설정하여 버튼이 컬럼 너비에 꽉 차지 않도록 함
        if st.button("📈 최신 트렌드 분석 입장", use_container_width=False):
            st.session_state.page = "trend"
            st.rerun()
    with col2:
        if st.button("📄 문서 분석 입장", use_container_width=False):
            st.session_state.page = "document"
            st.rerun()
    with col3: # 새로운 컬럼에 버튼 추가
        if st.button("⏰ 보고서 자동화 입장", use_container_width=False):
            st.session_state.page = "automation"
            st.rerun()

    st.markdown("---") # 구분선 추가

    # 로그아웃 버튼 (로그인 기능 제거로 인해 '메인으로' 버튼으로 변경)
    # 로그인 기능이 없으므로 로그아웃 버튼 대신 앱 초기 상태로 돌아가는 버튼으로 변경
    if st.button("🔄 앱 초기화 (다시 시작)", use_container_width=False):
        # 모든 세션 상태를 초기화하고 앱을 다시 로드
        for key in st.session_state.keys():
            del st.session_state[key]
        st.rerun()

