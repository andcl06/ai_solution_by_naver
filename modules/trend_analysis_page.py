# modules/trend_analysis_page.py

import streamlit as st
from datetime import datetime, timedelta
import time
import re
import os
import json
import pandas as pd
from dotenv import load_dotenv
from io import BytesIO
import streamlit.components.v1 as components

# --- 모듈 임포트 (경로 조정) ---
from modules import ai_service
from modules import database_manager
from modules import news_crawler
from modules import trend_analyzer
from modules import data_exporter
from modules import email_sender
# from modules import report_automation_page # 이 페이지에서는 직접 임포트하지 않습니다. main_app에서 라우팅합니다.

# --- 페이지 함수 정의 ---
def trend_analysis_page():
    """
    최신 뉴스 기반 트렌드 분석 및 보고서 생성을 수행하는 페이지입니다.
    """
    st.title("📰 뉴스 트렌드 분석기")
    st.markdown("원하는 키워드로 네이버 뉴스 트렌드를 감지하고, AI가 요약한 기사 내용을 확인하세요.")

    # --- 메인으로 돌아가기 버튼 ---
    if st.button("⬅️ 메인으로"):
        st.session_state.page = "landing"
        st.rerun()
    st.markdown("---") # 버튼 아래 구분선 추가

    # --- Potens.dev AI API 키 설정 ---
    POTENS_API_KEY = os.getenv("POTENS_API_KEY")

    if not POTENS_API_KEY:
        st.error("🚨 오류: .env 파일에 'POTENS_API_KEY'가 설정되지 않았습니다. Potens.dev AI 기능을 사용할 수 없습니다.")
        return

    # --- 이메일 설정 정보 로드 (수동 전송 기능에만 필요) ---
    SENDER_EMAIL = os.getenv("SENDER_EMAIL")
    SENDER_PASSWORD = os.getenv("SENDER_PASSWORD")
    SMTP_SERVER = os.getenv("SMTP_SERVER")
    SMTP_PORT = os.getenv("SMTP_PORT")

    email_config_ok = True
    if not all([SENDER_EMAIL, SENDER_PASSWORD, SMTP_SERVER, SMTP_PORT]):
        st.warning("⚠️ 이메일 전송 기능 활성화를 위해 .env 파일에 SENDER_EMAIL, SENDER_PASSWORD, SMTP_SERVER, SMTP_PORT를 설정해주세요.")
        email_config_ok = False
    else:
        try:
            SMTP_PORT = int(SMTP_PORT)
        except ValueError:
            st.error("🚨 오류: SMTP_PORT는 유효한 숫자여야 합니다.")
            email_config_ok = False


    # 데이터베이스 초기화
    database_manager.init_db()
    all_db_articles = database_manager.get_all_articles()


    # --- Streamlit Session State 초기화 ---
    if 'trending_keywords_data' not in st.session_state:
        st.session_state['trending_keywords_data'] = []
    if 'displayed_keywords' not in st.session_state:
        st.session_state['displayed_keywords'] = []
    if 'final_collected_articles' not in st.session_state:
        st.session_state['final_collected_articles'] = []
    if 'ai_insights_summary' not in st.session_state:
        st.session_state['ai_insights_summary'] = ""
    if 'ai_trend_summary' not in st.session_state:
        st.session_state['ai_trend_summary'] = ""
    if 'ai_insurance_info' not in st.session_state:
        st.session_state['ai_insurance_info'] = ""
    if 'db_status_message' not in st.session_state:
        st.session_state['db_status_message'] = ""
    if 'db_status_type' not in st.session_state:
        st.session_state['db_status_type'] = ""
    if 'prettified_report_for_download' not in st.session_state:
        st.session_state['prettified_report_for_download'] = ""
    if 'formatted_trend_summary' not in st.session_state:
        st.session_state['formatted_trend_summary'] = ""
    if 'formatted_insurance_info' not in st.session_state:
        st.session_state['formatted_insurance_info'] = ""
    if 'email_status_message' not in st.session_state:
        st.session_state['email_status_message'] = ""
    if 'email_status_type' not in st.session_state:
        st.session_state['email_status_type'] = ""
    # 검색 프로필 관련 세션 상태
    if 'search_profiles' not in st.session_state:
        st.session_state['search_profiles'] = database_manager.get_search_profiles()
    if 'selected_profile_id' not in st.session_state:
        st.session_state['selected_profile_id'] = None
    # 예약 작업 관련 세션 상태는 이제 report_automation_page에서 관리
    # if 'scheduled_task' not in st.session_state: ...
    # if 'auto_refresh_on' not in st.session_state: ...
    # if 'scheduled_task_running' not in st.session_state: ...
    if 'recipient_emails_input' not in st.session_state: # 이메일 입력 필드 상태
        st.session_state['recipient_emails_input'] = ""


    # --- 자동 보고서 전송 스케줄러 로직은 report_automation_page.py로 이동됨 ---
    # 이 페이지에서는 스케줄러 관련 로직을 제거합니다.
    # st.sidebar.write(...) 등도 제거.


    # --- UI 레이아웃: 검색 조건 (좌) & 키워드 트렌드 결과 (우) ---
    col_search_input, col_trend_results = st.columns([1, 2])

    with col_search_input:
        st.header("🔍 검색 조건 설정")

        # --- 검색 프로필 관리 ---
        st.subheader("저장된 검색 프로필")
        profiles = st.session_state['search_profiles'] # 최신 프로필 목록 가져오기
        profile_names = ["-- 프로필 선택 --"] + [p['profile_name'] for p in profiles]
        
        # 현재 선택된 프로필 ID가 있다면 해당 프로필의 이름을 기본값으로 설정
        current_profile_name = "-- 프로필 선택 --"
        if st.session_state['selected_profile_id']:
            selected_profile_obj = next((p for p in profiles if p['id'] == st.session_state['selected_profile_id']), None)
            if selected_profile_obj:
                current_profile_name = selected_profile_obj['profile_name']

        selected_profile_name = st.selectbox(
            "불러올 프로필을 선택하세요:", 
            profile_names, 
            index=profile_names.index(current_profile_name) if current_profile_name in profile_names else 0,
            key="profile_selector"
        )
        
        # 프로필 불러오기/삭제 버튼
        col_load_profile, col_delete_profile = st.columns(2)
        with col_load_profile:
            if st.button("프로필 불러오기", help="선택된 프로필의 검색 조건을 적용합니다."):
                if selected_profile_name != "-- 프로필 선택 --":
                    selected_profile = next((p for p in profiles if p['profile_name'] == selected_profile_name), None)
                    if selected_profile:
                        st.session_state['keyword_input'] = selected_profile['keyword']
                        st.session_state['total_days_input'] = selected_profile['total_search_days']
                        st.session_state['recent_days_input'] = selected_profile['recent_trend_days']
                        st.session_state['max_pages_input'] = selected_profile['max_naver_search_pages_per_day']
                        st.session_state['selected_profile_id'] = selected_profile['id'] # 선택된 프로필 ID 저장
                        st.info(f"✅ 프로필 '{selected_profile_name}'이(가) 불러와졌습니다.")
                        st.rerun()
                else:
                    st.warning("불러올 프로필을 선택해주세요.")
        with col_delete_profile:
            if st.button("프로필 삭제", help="선택된 프로필을 데이터베이스에서 삭제합니다."):
                if selected_profile_name != "-- 프로필 선택 --":
                    selected_profile = next((p for p in profiles if p['profile_name'] == selected_profile_name), None)
                    if selected_profile:
                        if database_manager.delete_search_profile(selected_profile['id']):
                            st.success(f"✅ 프로필 '{selected_profile_name}'이(가) 삭제되었습니다.")
                            st.session_state['search_profiles'] = database_manager.get_search_profiles() # 프로필 목록 새로고침
                            if st.session_state['selected_profile_id'] == selected_profile['id']:
                                st.session_state['selected_profile_id'] = None # 삭제된 프로필이 선택되어 있었다면 초기화
                            st.rerun()
                        else:
                            st.error(f"🚨 프로필 '{selected_profile_name}' 삭제에 실패했습니다.")
                else:
                    st.warning("삭제할 프로필을 선택해주세요.")

        with st.form("search_form"):
            keyword = st.text_input("검색할 뉴스 키워드 (예: '전기차')", value=st.session_state.get('keyword_input', "전기차"), key="keyword_input")
            total_search_days = st.number_input("총 몇 일간의 뉴스를 검색할까요? (예: 15)", min_value=1, value=st.session_state.get('total_days_input', 15), key="total_days_input")
            recent_trend_days = st.number_input("최근 몇 일간의 데이터를 기준으로 트렌드를 분석할까요? (예: 2)", min_value=1, value=st.session_state.get('recent_days_input', 2), key="recent_days_input")
            max_naver_search_pages_per_day = st.number_input("각 날짜별로 네이버 뉴스 검색 결과 몇 페이지까지 크롤링할까요? (페이지당 10개 기사, 예: 3)", min_value=1, value=st.session_state.get('max_pages_input', 3), key="max_pages_input")

            col_submit, col_save_profile = st.columns([0.7, 0.3])
            with col_submit:
                submitted = st.form_submit_button("뉴스 트렌드 분석 시작")
            with col_save_profile:
                profile_name_to_save = st.text_input("프로필 이름 (저장)", value="", help="현재 검색 설정을 저장할 이름을 입력하세요.")
                if st.form_submit_button("프로필 저장"):
                    if profile_name_to_save:
                        if database_manager.save_search_profile(profile_name_to_save, keyword, total_search_days, recent_trend_days, max_naver_search_pages_per_day):
                            st.success(f"✅ 검색 프로필 '{profile_name_to_save}'이(가) 성공적으로 저장되었습니다.")
                            st.session_state['search_profiles'] = database_manager.get_search_profiles() # 프로필 목록 새로고침
                            st.rerun()
                        else:
                            st.error(f"🚨 검색 프로필 '{profile_name_to_save}' 저장에 실패했습니다. 이미 존재하는 이름일 수 있습니다.")
                    else:
                        st.warning("저장할 프로필 이름을 입력해주세요.")

    with col_trend_results:
        st.header("📈 키워드 트렌드 분석 결과")
        st.markdown("다음은 최근 언급량이 급증한 트렌드 키워드입니다.")

        table_placeholder = st.empty()
        status_message_placeholder = st.empty()

        if submitted:
            # 새로운 검색 요청 시 기존 상태 초기화
            st.session_state['trending_keywords_data'] = []
            st.session_state['displayed_keywords'] = []
            st.session_state['final_collected_articles'] = []
            st.session_state['ai_insights_summary'] = ""
            st.session_state['ai_trend_summary'] = ""
            st.session_state['ai_insurance_info'] = ""
            st.session_state['prettified_report_for_download'] = ""
            st.session_state['formatted_trend_summary'] = ""
            st.session_state['formatted_insurance_info'] = ""
            st.session_state['email_status_message'] = ""
            st.session_state['email_status_type'] = ""

            st.session_state['submitted_flag'] = True
            st.session_state['analysis_completed'] = False
            st.session_state['db_status_message'] = ""
            st.session_state['db_status_type'] = ""

            table_placeholder.empty()
            my_bar = status_message_placeholder.progress(0, text="데이터 수집 및 분석 진행 중...")
            status_message_placeholder.info("네이버 뉴스 메타데이터 수집 중...")

            if recent_trend_days >= total_search_days:
                status_message_placeholder.error("오류: 최근 트렌드 분석 기간은 총 검색 기간보다 짧아야 합니다.")
            else:
                all_collected_news_metadata = []

                today_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
                search_start_date = today_date - timedelta(days=total_search_days - 1)

                total_expected_articles = total_search_days * max_naver_search_pages_per_day * 10
                processed_article_count = 0


                for i in range(total_search_days):
                    current_search_date = search_start_date + timedelta(days=i)
                    formatted_search_date = current_search_date.strftime('%Y.%m.%d')

                    daily_articles = news_crawler.crawl_naver_news_metadata(
                        keyword,
                        current_search_date,
                        max_naver_search_pages_per_day
                    )

                    for article in daily_articles:
                        processed_article_count += 1
                        progress_percentage = processed_article_count / total_expected_articles
                        my_bar.progress(min(progress_percentage, 1.0), text=f"뉴스 메타데이터 수집 중... ({formatted_search_date}, {processed_article_count}개 기사 처리 완료)")


                        article_data_for_db = {
                            "제목": article["제목"],
                            "링크": article["링크"],
                            "날짜": article["날짜"].strftime('%Y-%m-%d'),
                            "내용": article["내용"]
                        }
                        database_manager.insert_article(article_data_for_db)

                        all_collected_news_metadata.append(article)

                my_bar.empty()
                status_message_placeholder.success(f"총 {len(all_collected_news_metadata)}개의 뉴스 메타데이터를 수집했습니다.")

                # --- 2. 키워드 트렌드 분석 실행 ---
                status_message_placeholder.info("키워드 트렌드 분석 중...")
                with st.spinner("키워드 트렌드 분석 중..."):
                    trending_keywords_data = trend_analyzer.analyze_keyword_trends(
                        all_collected_news_metadata,
                        recent_days_period=recent_trend_days,
                        total_days_period=total_search_days
                    )
                st.session_state['trending_keywords_data'] = trending_keywords_data

                if trending_keywords_data:
                    # --- AI가 보험 개발자 관점에서 유의미한 키워드 선별 ---
                    relevant_keywords_from_ai_raw = []
                    with st.spinner("AI가 보험 개발자 관점에서 유의미한 키워드를 선별 중..."):
                        relevant_keywords_from_ai_raw = ai_service.get_relevant_keywords(
                            trending_keywords_data,
                            "차량보험사의 보험개발자",
                            POTENS_API_KEY
                        )

                    filtered_trending_keywords = []
                    if relevant_keywords_from_ai_raw:
                        filtered_trending_keywords = [
                            kw_data for kw_data in trending_keywords_data
                            if kw_data['keyword'] in relevant_keywords_from_ai_raw
                        ]
                        filtered_trending_keywords = sorted(filtered_trending_keywords, key=lambda x: x['recent_freq'], reverse=True)

                        status_message_placeholder.info(f"AI가 선별한 보험 개발자 관점의 유의미한 키워드 ({len(filtered_trending_keywords)}개): {[kw['keyword'] for kw in filtered_trending_keywords]}")
                    else:
                        status_message_placeholder.warning("AI가 보험 개발자 관점에서 유의미한 키워드를 선별하지 못했습니다. 모든 트렌드 키워드를 표시합니다.")
                        filtered_trending_keywords = trending_keywords_data

                    top_3_relevant_keywords = filtered_trending_keywords[:3]
                    st.session_state['displayed_keywords'] = top_3_relevant_keywords

                    if top_3_relevant_keywords:
                        pass
                    else:
                        status_message_placeholder.info("보험 개발자 관점에서 유의미한 트렌드 키워드가 식별되지 않습니다.")


                    # --- 3. 트렌드 기사 본문 요약 (Potens.dev AI 활용) ---
                    status_message_placeholder.info("트렌드 기사 본문 요약 중 (Potens.dev AI 호출)...")

                    recent_trending_articles_candidates = [
                        article for article in all_collected_news_metadata
                        if article.get("날짜") and today_date - timedelta(days=recent_trend_days) <= article["날짜"]
                    ]

                    processed_links = set()

                    articles_for_ai_summary = []
                    for article in recent_trending_articles_candidates:
                        text_for_trend_check = article["제목"] + " " + article.get("내용", "")
                        article_keywords_for_trend = trend_analyzer.extract_keywords_from_text(text_for_trend_check)

                        if any(trend_kw['keyword'] in article_keywords_for_trend for trend_kw in top_3_relevant_keywords):
                            articles_for_ai_summary.append(article)

                    total_ai_articles_to_process = len(articles_for_ai_summary)

                    if total_ai_articles_to_process == 0:
                        status_message_placeholder.info("선별된 트렌드 키워드를 포함하는 최근 기사가 없거나, AI 요약 대상 기사가 없습니다.")
                    else:
                        ai_progress_bar = st.progress(0, text=f"AI가 트렌드 기사를 요약 중... (0/{total_ai_articles_to_process} 완료)")
                        ai_processed_count = 0

                        temp_collected_articles = []
                        for article in articles_for_ai_summary:
                            if article["링크"] in processed_links:
                                continue

                            article_date_str = article["날짜"].strftime('%Y-%m-%d')

                            ai_processed_content = ai_service.get_article_summary(
                                article["제목"],
                                article["링크"],
                                article_date_str,
                                article["내용"],
                                POTENS_API_KEY,
                                max_attempts=2
                            )

                            final_content = ""
                            if ai_processed_content.startswith("Potens.dev AI 호출 최종 실패") or \
                               ai_processed_content.startswith("Potens.dev AI 호출에서 유효한 응답을 받지 못했습니다."):
                                final_content = f"본문 요약 실패 (AI 오류): {ai_processed_content}"
                                status_message_placeholder.error(f"AI 요약 실패: {final_content}")
                            else:
                                final_content = ai_service.clean_ai_response_text(ai_processed_content)

                            temp_collected_articles.append({
                                "제목": article["제목"],
                                "링크": article["링크"],
                                "날짜": article_date_str,
                                "내용": final_content
                            })
                            processed_links.add(article["링크"])
                            time.sleep(0.1)

                        ai_progress_bar.empty()
                        st.session_state['final_collected_articles'] = temp_collected_articles

                        if st.session_state['final_collected_articles']:
                            status_message_placeholder.success(f"총 {len(st.session_state['final_collected_articles'])}개의 트렌드 기사 요약을 완료했습니다.")

                            # --- 4. AI가 트렌드 요약 및 보험 상품 개발 인사이트 도출 (분리된 호출) ---
                            status_message_placeholder.info("AI가 트렌드 요약 및 보험 상품 개발 인사이트를 도출 중 (분리된 호출)...")

                            articles_for_ai_insight_generation = st.session_state['final_collected_articles']

                            with st.spinner("AI가 뉴스 트렌드를 요약 중..."):
                                trend_summary = ai_service.get_overall_trend_summary(
                                    articles_for_ai_insight_generation,
                                    POTENS_API_KEY
                                )
                                st.session_state['ai_trend_summary'] = ai_service.clean_ai_response_text(trend_summary)
                                if st.session_state['ai_trend_summary'].startswith("요약된 기사가 없어") or \
                                   st.session_state['ai_trend_summary'].startswith("Potens.dev AI 호출 최종 실패") or \
                                   st.session_state['ai_trend_summary'].startswith("Potens.dev AI 호출에서 유효한 응답을 받지 못했습니다."):
                                    status_message_placeholder.error(f"AI 트렌드 요약 실패: {st.session_state['ai_trend_summary']}")
                                else:
                                    st.session_state['ai_trend_summary_ok'] = True # 성공 플래그
                                    status_message_placeholder.success("AI 뉴스 트렌드 요약 완료!")
                                time.sleep(1)

                            with st.spinner("AI가 자동차 보험 산업 관련 정보를 분석 중..."):
                                insurance_info = ai_service.get_insurance_implications_from_ai(
                                    st.session_state['ai_trend_summary'],
                                    POTENS_API_KEY
                                )
                                st.session_state['ai_insurance_info'] = ai_service.clean_ai_response_text(insurance_info)
                                if st.session_state['ai_insurance_info'].startswith("요약된 기사가 없어") or \
                                   st.session_state['ai_insurance_info'].startswith("Potens.dev AI 호출 최종 실패") or \
                                   st.session_state['ai_insurance_info'].startswith("Potens.dev AI 호출에서 유효한 응답을 받지 못했습니다.") or \
                                   st.session_state['ai_insurance_info'].startswith("트렌드 요약문이 없어"):
                                    status_message_placeholder.error(f"AI 자동차 보험 산업 관련 정보 분석 실패: {st.session_state['ai_insurance_info']}")
                                else:
                                    st.session_state['ai_insurance_info_ok'] = True # 성공 플래그
                                    status_message_placeholder.success("AI 자동차 보험 산업 관련 정보 분석 완료!")
                                time.sleep(1)

                            # --- 5. AI가 각 섹션별로 포맷팅 (부하 분산) ---
                            with st.spinner("AI가 뉴스 트렌드 요약 보고서를 포맷팅 중..."):
                                formatted_trend_summary = ai_service.format_text_with_markdown(
                                    st.session_state['ai_trend_summary'],
                                    POTENS_API_KEY
                                )
                                st.session_state['formatted_trend_summary'] = formatted_trend_summary
                                if formatted_trend_summary.startswith("AI를 통한 보고서 포맷팅 실패"):
                                    status_message_placeholder.warning("AI 뉴스 트렌드 요약 포맷팅에 실패했습니다. 원본 텍스트가 사용됩니다.")
                                    st.session_state['formatted_trend_summary'] = st.session_state['ai_trend_summary']
                                else:
                                    status_message_placeholder.success("AI 뉴스 트렌드 요약 보고서 포맷팅 완료!")
                                time.sleep(1)

                            with st.spinner("AI가 자동차 보험 산업 관련 정보 보고서를 포맷팅 중..."):
                                formatted_insurance_info = ai_service.format_text_with_markdown(
                                    st.session_state['ai_insurance_info'],
                                    POTENS_API_KEY
                                )
                                st.session_state['formatted_insurance_info'] = formatted_insurance_info
                                if formatted_insurance_info.startswith("AI를 통한 보고서 포맷팅 실패"):
                                    status_message_placeholder.warning("AI 자동차 보험 산업 관련 정보 포맷팅에 실패했습니다. 원본 텍스트가 사용됩니다.")
                                    st.session_state['formatted_insurance_info'] = st.session_state['ai_insurance_info']
                                else:
                                    st.session_state['formatted_insurance_info_ok'] = True # 성공 플래그
                                    status_message_placeholder.success("AI 자동차 보험 산업 관련 정보 포맷팅 완료!")
                                time.sleep(1)

                            # --- 6. 최종 보고서 결합 (AI 포맷팅 + 직접 구성 부록) ---
                            final_prettified_report = ""
                            final_prettified_report += "# 뉴스 트렌드 분석 및 보험 상품 개발 인사이트\n\n"
                            final_prettified_report += "## 개요\n\n"
                            final_prettified_report += "이 보고서는 최근 뉴스 트렌드를 분석하고, 이를 바탕으로 자동차 보험 상품 개발에 필요한 주요 인사이트를 제공합니다.\n\n"

                            if st.session_state['formatted_trend_summary']:
                                final_prettified_report += "## 뉴스 트렌드 요약\n"
                                final_prettified_report += st.session_state['formatted_trend_summary'] + "\n\n"
                            else:
                                final_prettified_report += "## 뉴스 트렌드 요약 (생성 실패)\n"
                                final_prettified_report += st.session_state['ai_trend_summary'] + "\n\n"

                            if st.session_state['formatted_insurance_info']:
                                final_prettified_report += "## 자동차 보험 산업 관련 주요 사실 및 법적 책임\n"
                                final_prettified_report += st.session_state['formatted_insurance_info'] + "\n\n"
                            else:
                                final_prettified_report += "## 자동차 보험 산업 관련 주요 사실 및 법적 책임 (생성 실패)\n"
                                final_prettified_report += st.session_state['ai_insurance_info'] + "\n\n"

                            # --- 부록 섹션 추가 (AI 포맷팅 없이 직접 구성) ---
                            final_prettified_report += "---\n\n"
                            final_prettified_report += "## 부록\n\n"

                            final_prettified_report += "### 키워드 산출 근거\n"
                            if st.session_state['displayed_keywords']:
                                for kw_data in st.session_state['displayed_keywords']:
                                    surge_ratio_display = (f'''{kw_data.get('surge_ratio'):.2f}x''' if kw_data.get('surge_ratio') != float('inf') else '새로운 트렌드')
                                    final_prettified_report += (
                                        f"- **키워드**: {kw_data['keyword']}\n"
                                        f"  - 최근 언급량: {kw_data['recent_freq']}회\n"
                                        f"  - 이전 언급량: {kw_data['past_freq']}회\n"
                                        f"  - 증가율: {surge_ratio_display}\n\n"
                                    )
                            else:
                                final_prettified_report += "키워드 산출 근거 데이터가 없습니다.\n\n"

                            final_prettified_report += "### 반영된 기사 리스트\n"
                            if temp_collected_articles:
                                for i, article in enumerate(temp_collected_articles):
                                    final_prettified_report += (
                                        f"{i+1}. **제목**: {article['제목']}\n"
                                        f"   **날짜**: {article['날짜']}\n"
                                        f"   **링크**: {article['링크']}\n"
                                        f"   **요약 내용**: {article['내용'][:150]}...\n\n"
                                    )
                            else:
                                final_prettified_report += "반영된 기사 리스트가 없습니다.\n\n"

                            st.session_state['prettified_report_for_download'] = final_prettified_report


                        else:
                            status_message_placeholder.info("선별된 트렌드 키워드를 포함하는 기사가 없거나, AI 요약에 실패했습니다.")

                else:
                    status_message_placeholder.info("선택된 기간 내에 유의미한 트렌드 키워드가 없습니다.")

            st.session_state['submitted_flag'] = False
            st.session_state['analysis_completed'] = True
            st.rerun()

        # --- 결과가 이미 세션 상태에 있는 경우 표시 ---
        if not st.session_state.get('submitted_flag', False) and \
           st.session_state.get('analysis_completed', False):
            if st.session_state['displayed_keywords']:
                df_top_keywords = pd.DataFrame(st.session_state['displayed_keywords'])
                df_top_keywords['surge_ratio'] = df_top_keywords['surge_ratio'].apply(
                    lambda x: f"{x:.2f}x" if x != float('inf') else "새로운 트렌드"
                )
                table_placeholder.table(df_top_keywords)

                if st.session_state['final_collected_articles']:
                    status_message_placeholder.success(
                        f"총 {len(st.session_state['final_collected_articles'])}개의 트렌드 기사 요약을 완료했습니다. "
                        "AI 트렌드 요약 및 보험 상품 개발 인사이트 보고서는 아래 '데이터 다운로드' 섹션에서 다운로드할 수 있습니다."
                    )
            else:
                st.info("선택된 기간 내에 유의미한 트렌드 키워드가 식별되지 않았습니다.")
        elif not st.session_state.get('submitted_flag', False) and \
             not st.session_state.get('analysis_completed', False):
            empty_df = pd.DataFrame(columns=['keyword', 'recent_freq', 'past_freq', 'surge_ratio'])
            table_placeholder.table(empty_df)
            status_message_placeholder.info("검색 조건을 입력하고 '뉴스 트렌드 분석 시작' 버튼을 눌러주세요!")


    # --- 데이터 다운로드 섹션 ---
    st.header("📥 데이터 다운로드")
    # all_db_articles는 함수 시작 부분에서 이미 정의되었습니다.
    # if all_db_articles: # 이 조건문은 이제 필요 없습니다.


    txt_data_all_crawled = ""
    excel_data_all_crawled = None
    txt_data_ai_summaries = ""
    excel_data_ai_summaries = None
    txt_data_ai_insights = ""
    excel_data_ai_insights = None

    # all_db_articles가 비어있을 수도 있으므로, DataFrame 생성 전에 확인
    if all_db_articles:
        df_all_articles = pd.DataFrame(all_db_articles, columns=['제목', '링크', '날짜', '내용', '수집_시간'])
        df_all_articles['내용'] = df_all_articles['내용'].fillna('')

        txt_data_all_crawled = data_exporter.export_articles_to_txt(
            [dict(zip(df_all_articles.columns, row)) for row in df_all_articles.values],
            file_prefix="all_crawled_news"
        )

        excel_data_all_crawled = data_exporter.export_articles_to_excel(df_all_articles, sheet_name='All_Crawled_News')


    df_ai_summaries = pd.DataFrame(st.session_state['final_collected_articles'],
                                   columns=['제목', '링크', '날짜', '내용'])
    df_ai_summaries['내용'] = df_ai_summaries['내용'].fillna('')

    txt_data_ai_summaries = data_exporter.export_articles_to_txt(
        [dict(zip(df_ai_summaries.columns, row)) for row in df_ai_summaries.values],
        file_prefix="ai_summaries"
    )

    if not df_ai_summaries.empty:
        excel_data_ai_summaries = data_exporter.export_articles_to_excel(df_ai_summaries, sheet_name='AI_Summaries')

    if st.session_state['prettified_report_for_download']:
        txt_data_ai_insights = st.session_state['prettified_report_for_download']
    else:
        txt_data_ai_insights = "AI 트렌드 요약 및 보험 상품 개발 인사이트가 없습니다."


    if st.session_state['prettified_report_for_download']:
        excel_data_ai_insights = data_exporter.export_ai_report_to_excel(
            st.session_state['prettified_report_for_download'],
            sheet_name='AI_Insights_Report'
        )
    else:
        excel_data_ai_insights = None


    st.markdown("### 📊 수집된 전체 뉴스 데이터")
    col_all_data_txt, col_all_data_excel = st.columns([0.1, 0.9])
    with col_all_data_txt:
        st.download_button(
            label="📄 TXT 다운로드",
            data=txt_data_all_crawled,
            file_name=data_exporter.generate_filename("all_crawled_news", "txt"),
            mime="text/plain",
            help="데이터베이스에 저장된 모든 뉴스를 텍스트 파일로 다운로드합니다."
        )
    with col_all_data_excel:
        if excel_data_all_crawled:
            st.download_button(
                label="엑셀 다운로드",
                data=excel_data_all_crawled.getvalue(),
                file_name=data_exporter.generate_filename("all_crawled_news", "xlsx"),
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                help="데이터베이스에 저장된 모든 뉴스를 엑셀 파일(.xlsx)로 다운로드합니다. (한글 깨짐 없음)"
            )
        else:
            st.info("엑셀 다운로드 데이터가 없습니다.")


    if not df_ai_summaries.empty:
        st.markdown("### 📝 AI 요약 기사")
        col_ai_txt, col_ai_excel = st.columns([0.1, 0.9])
        with col_ai_txt:
            st.download_button(
                label="📄 AI 요약 TXT 다운로드",
                data=txt_data_ai_summaries,
                file_name=data_exporter.generate_filename("ai_summaries", "txt"),
                mime="text/plain",
                help="AI가 요약한 트렌드 기사 내용을 텍스트 파일로 다운로드합니다."
            )
        with col_ai_excel:
            if excel_data_ai_summaries:
                st.download_button(
                    label="📊 AI 요약 엑셀 다운로드",
                    data=excel_data_ai_summaries.getvalue(),
                    file_name=data_exporter.generate_filename("ai_summaries", "xlsx"),
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    help="AI가 요약한 트렌드 기사 내용을 엑셀 파일(.xlsx)로 다운로드합니다."
                )
            else:
                st.info("AI 요약 엑셀 다운로드 데이터가 없습니다.")
    else:
        st.info("AI 요약된 트렌드 기사가 없습니다. 먼저 분석을 실행하여 요약된 기사를 생성하세요.")

    if st.session_state['prettified_report_for_download']:
        st.markdown("### 💡 AI 트렌드 요약 및 보험 상품 개발 인사이트")
        col_ai_insights_txt, col_ai_insights_excel, col_ai_insights_email = st.columns([0.1, 0.4, 0.5])
        with col_ai_insights_txt:
            st.download_button(
                label="📄 TXT 다운로드",
                data=txt_data_ai_insights,
                file_name=data_exporter.generate_filename("ai_insights_report", "txt"),
                mime="text/plain",
                help="AI가 도출한 트렌드 요약 및 보험 상품 개발 인사이트 보고서를 텍스트 파일로 다운로드합니다."
            )
        with col_ai_insights_excel:
            if excel_data_ai_insights:
                st.download_button(
                    label="📊 엑셀 다운로드",
                    data=excel_data_ai_insights.getvalue(),
                    file_name=data_exporter.generate_filename("ai_insights_report", "xlsx"),
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    help="AI가 도출한 트렌드 요약 및 보험 상품 개발 인사이트 보고서를 엑셀 파일로 다운로드합니다."
                )
            else:
                st.info("AI 인사이트 엑셀 다운로드 데이터가 없습니다.")
        with col_ai_insights_email:
            st.text_input(
                "수신자 이메일 (콤마로 구분)",
                value=st.session_state['recipient_emails_input'],
                key="email_recipients_input",
                help="보고서를 받을 이메일 주소를 콤마(,)로 구분하여 입력하세요."
            )
            # 이메일 전송 버튼 (보고서만) - 특약 포함 전송은 자동화 페이지에서
            if st.button("📧 보고서 이메일 전송", help="생성된 보고서를 이메일로 전송합니다."):
                recipient_emails_str = st.session_state['email_recipients_input']
                recipient_emails_list = [e.strip() for e in recipient_emails_str.split(',') if e.strip()]

                if not recipient_emails_list:
                    st.session_state['email_status_message'] = "🚨 수신자 이메일 주소를 입력해주세요."
                    st.session_state['email_status_type'] = "error"
                    st.rerun()
                elif not email_config_ok:
                    st.session_state['email_status_message'] = "🚨 이메일 설정 정보가 올바르지 않아 이메일을 전송할 수 없습니다."
                    st.session_state['email_status_type'] = "error"
                    st.rerun()
                else:
                    with st.spinner("이메일 전송 중..."):
                        email_subject = f"뉴스 트렌드 분석 보고서 - {datetime.now().strftime('%Y%m%d')}"
                        email_body = st.session_state['prettified_report_for_download']

                        attachments = []
                        if excel_data_ai_insights:
                            attachments.append({
                                "data": excel_data_ai_insights.getvalue(),
                                "filename": data_exporter.generate_filename("ai_insights_report", "xlsx"),
                                "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                            })
                        
                        # 이 페이지에서는 특약 첨부는 하지 않습니다.
                        # 특약 첨부는 report_automation_page에서 담당합니다.

                        success = email_sender.send_email_with_multiple_attachments( # 함수명 변경
                            sender_email=SENDER_EMAIL,
                            sender_password=SENDER_PASSWORD,
                            receiver_emails=recipient_emails_list, # 리스트 형태로 전달
                            smtp_server=SMTP_SERVER,
                            smtp_port=SMTP_PORT,
                            subject=email_subject,
                            body=email_body,
                            attachments=attachments, # 여러 첨부파일 전달
                            report_format="markdown"
                        )
                        if success:
                            st.session_state['email_status_message'] = "이메일이 성공적으로 전송되었습니다!"
                            st.session_state['email_status_type'] = "success"
                        else:
                            st.session_state['email_status_message'] = "이메일 전송에 실패했습니다. 설정 및 로그를 확인해주세요."
                            st.session_state['email_status_type'] = "error"
                        st.rerun()

            # 이메일 전송 상태 메시지 표시
            if st.session_state['email_status_message']:
                if st.session_state['email_status_type'] == "success":
                    st.success(st.session_state['email_status_message'])
                elif st.session_state['email_status_type'] == "error":
                    st.error(st.session_state['email_status_message']) # 메시지 출력으로 변경
                st.session_state['email_status_message'] = ""
                st.session_state['email_status_type'] = ""


    else:
        st.info("AI 트렌드 요약 및 보험 상품 개발 인사이트가 없습니다. 분석을 실행하여 생성하세요.")

    st.markdown("---")
    col_db_info, col_db_clear = st.columns([2, 1])
    with col_db_info:
        st.info(f"현재 데이터베이스에 총 {len(all_db_articles)}개의 기사가 저장되어 있습니다.")
        if st.session_state['db_status_message']:
            if st.session_state['db_status_type'] == "success":
                st.success(st.session_state['db_status_message'])
            elif st.session_state['db_status_type'] == "error":
                st.error(st.session_state['db_status_message']) # 메시지 출력으로 변경
            st.session_state['db_status_message'] = ""
            st.session_state['db_status_type'] = ""
        st.markdown("💡 **CSV 파일이 엑셀에서 깨질 경우:** 엑셀에서 '데이터' 탭 -> '텍스트/CSV 가져오기'를 클릭한 후, '원본 파일' 인코딩을 'UTF-8'로 선택하여 가져오세요.")
    with col_db_clear:
        if st.button("데이터베이스 초기화", help="데이터베이스의 모든 저장된 뉴스를 삭제합니다.", type="secondary"):
            database_manager.clear_db_content()
            st.session_state['trending_keywords_data'] = []
            st.session_state['displayed_keywords'] = []
            st.session_state['final_collected_articles'] = []
            st.session_state['ai_insights_summary'] = ""
            st.session_state['ai_trend_summary'] = ""
            st.session_state['ai_insurance_info'] = ""
            st.session_state['submitted_flag'] = False
            st.session_state['analysis_completed'] = False
            st.session_state['prettified_report_for_download'] = ""
            st.session_state['formatted_trend_summary'] = ""
            st.session_state['formatted_insurance_info'] = ""
            st.session_state['email_status_message'] = ""
            st.session_state['email_status_type'] = ""
            st.session_state['search_profiles'] = database_manager.get_search_profiles() # 프로필 목록 새로고침
            st.session_state['scheduled_task'] = database_manager.get_scheduled_task() # 예약 정보 새로고침
            database_manager.save_generated_endorsement("") # 데이터베이스 특약도 초기화 (새로 추가)
            st.rerun()
