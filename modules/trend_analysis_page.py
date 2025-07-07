# modules/trend_analysis_page.py

import streamlit as st
from datetime import datetime, timedelta
import time
import re
import os
import json
import pandas as pd
from dotenv import load_dotenv # 이 페이지에서는 os.getenv로 바로 접근하므로 load_dotenv는 필요 없음
from io import BytesIO

# --- 모듈 임포트 (경로 조정) ---
# pages 디렉토리에서 modules 디렉토리로 접근하기 위해 'modules.' 접두사 사용
from modules import ai_service
from modules import database_manager
from modules import news_crawler
from modules import trend_analyzer
from modules import data_exporter


# --- 페이지 함수 정의 ---
def trend_analysis_page():
    """
    최신 뉴스 기반 트렌드 분석 및 보고서 생성을 수행하는 페이지입니다.
    """
    # st.set_page_config는 main_app.py에서 설정하므로 여기서는 제거
    st.title("📰 뉴스 트렌드 분석기")
    st.markdown("원하는 키워드로 네이버 뉴스 트렌드를 감지하고, AI가 요약한 기사 내용을 확인하세요.")

    # --- 메인으로 돌아가기 버튼 ---
    if st.button("⬅️ 메인으로"):
        st.session_state.page = "landing"
        st.rerun()
    st.markdown("---") # 버튼 아래 구분선 추가

    # --- Potens.dev AI API 키 설정 ---
    # main_app.py에서 이미 load_dotenv()를 호출했으므로, 여기서는 os.getenv로 바로 접근
    POTENS_API_KEY = os.getenv("POTENS_API_KEY")

    if not POTENS_API_KEY:
        st.error("🚨 오류: .env 파일에 'POTENS_API_KEY'가 설정되지 않았습니다. Potens.dev AI 기능을 사용할 수 없습니다.")
        # API 키가 없으면 더 이상 진행하지 않도록 return
        return

    # 데이터베이스 초기화 (앱 시작 시 main_app에서 이미 호출될 수 있으나, 페이지 진입 시 재확인)
    database_manager.init_db()

    # --- Streamlit Session State 초기화 (페이지 진입 시 필요한 경우) ---
    # 각 페이지는 자신의 세션 상태 변수를 명확히 관리하는 것이 좋습니다.
    # main_app.py에서 공통 변수는 초기화했지만, 페이지별 변수는 여기서 초기화합니다.
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


    # --- UI 레이아웃: 검색 조건 (좌) & 키워드 트렌드 결과 (우) ---
    col_search_input, col_trend_results = st.columns([1, 2])

    with col_search_input:
        st.header("🔍 검색 조건 설정")
        with st.form("search_form"):
            keyword = st.text_input("검색할 뉴스 키워드 (예: '전기차')", value="전기차", key="keyword_input")
            total_search_days = st.number_input("총 몇 일간의 뉴스를 검색할까요? (예: 15)", min_value=1, value=15, key="total_days_input")
            recent_trend_days = st.number_input("최근 몇 일간의 데이터를 기준으로 트렌드를 분석할까요? (예: 2)", min_value=1, value=2, key="recent_days_input")
            max_naver_search_pages_per_day = st.number_input("각 날짜별로 네이버 뉴스 검색 결과 몇 페이지까지 크롤링할까요? (페이지당 10개 기사, 예: 3)", min_value=1, value=3, key="max_pages_input")

            submitted = st.form_submit_button("뉴스 트렌드 분석 시작")

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

            st.session_state['submitted_flag'] = True
            st.session_state['analysis_completed'] = False
            st.session_state['db_status_message'] = "" # 제출 시에도 초기화
            st.session_state['db_status_type'] = ""     # 제출 시에도 초기화

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

                            # AI에게 전달할 요약된 기사 목록 (전체 기사 요약본을 전달)
                            articles_for_ai_insight_generation = st.session_state['final_collected_articles'] # 모든 요약 기사 전달

                            # 트렌드 요약 호출
                            with st.spinner("AI가 뉴스 트렌드를 요약 중..."):
                                trend_summary = ai_service.get_overall_trend_summary(
                                    articles_for_ai_insight_generation, # 전체 요약 기사 목록 전달
                                    POTENS_API_KEY
                                )
                                st.session_state['ai_trend_summary'] = ai_service.clean_ai_response_text(trend_summary)
                                if st.session_state['ai_trend_summary'].startswith("요약된 기사가 없어") or \
                                   st.session_state['ai_trend_summary'].startswith("Potens.dev AI 호출 최종 실패") or \
                                   st.session_state['ai_trend_summary'].startswith("Potens.dev AI 호출에서 유효한 응답을 받지 못했습니다."):
                                    status_message_placeholder.error(f"AI 트렌드 요약 실패: {st.session_state['ai_trend_summary']}")
                                else:
                                    status_message_placeholder.success("AI 뉴스 트렌드 요약 완료!")
                                time.sleep(1) # 다음 UI 업데이트 전 잠시 대기

                            # 보험 관련 정보 호출
                            with st.spinner("AI가 자동차 보험 산업 관련 정보를 분석 중..."):
                                insurance_info = ai_service.get_insurance_implications_from_ai(
                                    st.session_state['ai_trend_summary'], # 변경된 부분: 트렌드 요약문 전달
                                    POTENS_API_KEY
                                )
                                st.session_state['ai_insurance_info'] = ai_service.clean_ai_response_text(insurance_info)
                                if st.session_state['ai_insurance_info'].startswith("요약된 기사가 없어") or \
                                   st.session_state['ai_insurance_info'].startswith("Potens.dev AI 호출 최종 실패") or \
                                   st.session_state['ai_insurance_info'].startswith("Potens.dev AI 호출에서 유효한 응답을 받지 못했습니다.") or \
                                   st.session_state['ai_insurance_info'].startswith("트렌드 요약문이 없어"): # 트렌드 요약문이 없는 경우도 실패
                                    status_message_placeholder.error(f"AI 자동차 보험 산업 관련 정보 분석 실패: {st.session_state['ai_insurance_info']}")
                                else:
                                    status_message_placeholder.success("AI 자동차 보험 산업 관련 정보 분석 완료!")
                                time.sleep(1) # 다음 UI 업데이트 전 잠시 대기

                            # 두 결과를 합쳐서 최종 인사이트 요약 생성
                            final_insights_text = ""
                            if st.session_state['ai_trend_summary'] and \
                               not st.session_state['ai_trend_summary'].startswith("AI 호출 최종 실패"):
                                final_insights_text += "### 뉴스 트렌드 요약\n"
                                final_insights_text += st.session_state['ai_trend_summary'] + "\n\n"
                            else:
                                final_insights_text += "### 뉴스 트렌드 요약 (생성 실패)\n"
                                final_insights_text += st.session_state['ai_trend_summary'] + "\n\n"

                            if st.session_state['ai_insurance_info'] and \
                               not st.session_state['ai_insurance_info'].startswith("AI 호출 최종 실패") and \
                               not st.session_state['ai_insurance_info'].startswith("트렌드 요약문이 없어"): # 트렌드 요약문이 없는 경우도 실패
                                final_insights_text += "### 자동차 보험 산업 관련 주요 사실 및 법적 책임\n"
                                final_insights_text += st.session_state['ai_insurance_info'] + "\n"
                            else:
                                final_insights_text += "### 자동차 보험 산업 관련 주요 사실 및 법적 책임 (생성 실패)\n"
                                final_insights_text += st.session_state['ai_insurance_info'] + "\n"

                            # --- 부록 섹션 추가 ---
                            final_insights_text += "\n---\n\n"
                            final_insights_text += "## 부록\n\n"

                            # 키워드 산출 근거 추가
                            final_insights_text += "### 키워드 산출 근거\n"
                            if st.session_state['displayed_keywords']:
                                for kw_data in st.session_state['displayed_keywords']:
                                    # f-string 문법 오류 수정
                                    surge_ratio_display = (f'''{kw_data.get('surge_ratio'):.2f}x''' if kw_data.get('surge_ratio') != float('inf') else '새로운 트렌드')
                                    final_insights_text += (
                                        f"- **키워드**: {kw_data['keyword']}\n"
                                        f"  - 최근 언급량: {kw_data['recent_freq']}회\n"
                                        f"  - 이전 언급량: {kw_data['past_freq']}회\n"
                                        f"  - 증가율: {surge_ratio_display}\n"
                                    )
                            else:
                                final_insights_text += "키워드 산출 근거 데이터가 없습니다.\n"
                            final_insights_text += "\n"

                            # 반영된 기사 리스트 추가 (배치 요약 대신 원본 기사 정보 나열)
                            final_insights_text += "### 반영된 기사 리스트\n"
                            if st.session_state['final_collected_articles']:
                                for i, article in enumerate(st.session_state['final_collected_articles']):
                                    final_insights_text += (
                                        f"{i+1}. **제목**: {article['제목']}\n"
                                        f"   **날짜**: {article['날짜']}\n" # 오타 수정
                                        f"   **링크**: {article['링크']}\n"
                                        f"   **요약 내용**: {article['내용'][:100]}...\n" # 요약 내용의 일부만 표시
                                    )
                                final_insights_text += "\n"
                            else:
                                final_insights_text += "반영된 기사 리스트가 없습니다.\n"

                            st.session_state['ai_insights_summary'] = final_insights_text

                        else:
                            status_message_placeholder.info("선별된 트렌드 키워드를 포함하는 기사가 없거나, AI 요약에 실패했습니다.")

                else:
                    status_message_placeholder.info("선택된 기간 내에 유의미한 트렌드 키워드가 없습니다.")

            st.session_state['submitted_flag'] = False
            st.session_state['analysis_completed'] = True

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
                    status_message_placeholder.success(f"총 {len(st.session_state['final_collected_articles'])}개의 트렌드 기사 요약을 완료했습니다.")

                    # AI 인사이트 요약 표시 (트렌드 보고서)
                    # 이 부분을 주석 처리하여 화면에 표시되지 않도록 함
                    # if st.session_state['ai_insights_summary']:
                    #     st.markdown("---")
                    #     st.subheader("💡 AI 트렌드 요약 및 보험 상품 개발 인사이트")
                    #     st.markdown(st.session_state['ai_insights_summary'])
                    # else:
                    #     st.info("AI 트렌드 요약 및 보험 상품 개발 인사이트가 아직 없습니다. 분석을 실행해주세요.")
                    
                    # 대신, 분석 완료 메시지에 다운로드 안내 추가
                    status_message_placeholder.success(
                        f"총 {len(st.session_state['final_collected_articles'])}개의 트렌드 기사 요약을 완료했습니다. "
                        "AI 트렌드 요약 및 보험 상품 개발 인사이트 보고서는 아래 '데이터 다운로드' 섹션에서 다운로드할 수 있습니다."
                    )


            else:
                st.info("선택된 기간 내에 유의미한 트렌드 키워드가 식별되지 않았습니다.")
        # --- 초기 로드 시 메시지 ---
        elif not st.session_state.get('submitted_flag', False) and \
             not st.session_state.get('analysis_completed', False):
            empty_df = pd.DataFrame(columns=['keyword', 'recent_freq', 'past_freq', 'surge_ratio'])
            table_placeholder.table(empty_df)
            status_message_placeholder.info("검색 조건을 입력하고 '뉴스 트렌드 분석 시작' 버튼을 눌러주세요!")


    # --- 데이터 다운로드 섹션 ---
    st.header("📥 데이터 다운로드")
    all_db_articles = database_manager.get_all_articles()

    if all_db_articles:
        # 변수 초기화
        txt_data_all_crawled = ""
        excel_data_all_crawled = None
        txt_data_ai_summaries = ""
        excel_data_ai_summaries = None
        txt_data_ai_insights = ""
        excel_data_ai_insights = None

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

        txt_data_ai_insights = st.session_state['ai_insights_summary']

        if st.session_state['ai_insights_summary']:
            ai_insights_df = pd.DataFrame({
                '보고서 섹션': ['뉴스 트렌드 요약', '자동차 보험 산업 관련 주요 사실 및 법적 책임', '키워드 산출 근거', '반영된 기사 리스트'],
                '내용': [
                    st.session_state['ai_trend_summary'],
                    st.session_state['ai_insurance_info'],
                    "\n".join([f"- {kw_data['keyword']}: 최근 {kw_data['recent_freq']}회, 이전 {kw_data['past_freq']}회, 증가율 {f'''{kw_data.get('surge_ratio'):.2f}x''' if kw_data.get('surge_ratio') != float('inf') else '새로운 트렌드'}" for kw_data in st.session_state['displayed_keywords']]),
                    "\n".join([f"{i+1}. 제목: {art['제목']}\n날짜: {art['날짜']}\n링크: {art['링크']}\n요약 내용: {art['내용'][:100]}..." for i, art in enumerate(st.session_state['final_collected_articles'])])
                ]
            })
            excel_data_ai_insights = data_exporter.export_articles_to_excel(ai_insights_df, sheet_name='AI_Insights_Report')


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

        if st.session_state['ai_insights_summary']:
            st.markdown("### 💡 AI 트렌드 요약 및 보험 상품 개발 인사이트")
            col_ai_insights_txt, col_ai_insights_excel = st.columns([0.1, 0.9])
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
                    st.error(st.session_state['db_status_message'])
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
                st.rerun()
