import streamlit as st
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import time
import csv
import re
import os
import json
import sqlite3 # SQLite 데이터베이스 사용
import pandas as pd # CSV, Excel 생성을 위해 추가
from dotenv import load_dotenv
from collections import Counter
from io import BytesIO # Excel 파일 생성을 위해 추가

# --- Potens.dev AI API 호출 및 응답 처리를 위한 함수들 ---

def call_potens_api_raw(prompt_message: str, api_key: str, response_schema=None) -> dict:
    """
    주어진 프롬프트 메시지로 Potens.dev API를 호출하고 원본 응답을 반환합니다.
    response_schema: JSON 응답을 위한 스키마 (선택 사항)
    """
    if not api_key:
        st.error("🚨 오류: Potens.dev API 키가 누락되었습니다.")
        return {"error": "Potens.dev API 키가 누락되었습니다."}

    potens_api_endpoint = "https://ai.potens.ai/api/chat" 
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "prompt": prompt_message
    }
    if response_schema:
        payload["generationConfig"] = {
            "responseMimeType": "application/json",
            "responseSchema": response_schema
        }

    try:
        response = requests.post(potens_api_endpoint, headers=headers, json=payload, timeout=300)
        response.raise_for_status()
        response_json = response.json()
        
        if "message" in response_json:
            # response_schema가 있을 경우, message 필드의 내용을 JSON으로 파싱 시도
            if response_schema:
                try:
                    parsed_content = json.loads(response_json["message"].strip())
                    return {"text": parsed_content, "raw_response": response_json}
                except json.JSONDecodeError:
                    return {"error": f"Potens.dev API 응답 JSON 디코딩 오류 (message 필드): {response_json['message']}"}
            else:
                return {"text": response_json["message"].strip(), "raw_response": response_json}
        else:
            return {"error": "Potens.dev API 응답 형식이 올바라지 않습니다.", "raw_response": response_json}

    except requests.exceptions.RequestException as e:
        error_message = f"Potens.dev API 호출 오류 발생 ( network/timeout/HTTP): {e}"
        if e.response is not None:
            error_message += f" Response content: {e.response.text}" 
        return {"error": error_message}
    except json.JSONDecodeError:
        return {"error": f"Potens.dev API 응답 JSON 디코딩 오류: {response.text}"}
    except Exception as e:
        return {"error": f"알 수 없는 오류 발생: {e}"}

def call_potens_ai_for_article_summary_with_context_single_call(title: str, link: str, date_str: str, summary_snippet: str, api_key: str, max_attempts: int = 2, delay_seconds: int = 15) -> str:
    """
    Potens.dev AI를 호출하여 제공된 제목, 링크, 날짜, 미리보기 요약을 바탕으로
    뉴스 기사 내용을 요약합니다. (단일 호출)
    링크 접근이 불가능할 경우에도 제공된 정보만으로 요약을 시도합니다.
    """
    initial_prompt = (
        f"다음은 뉴스 기사에 대한 정보입니다. 이 정보를 바탕으로 뉴스 기사 내용을 요약해 주세요.\n"
        f"**제공된 링크에 접근할 수 없거나 기사를 찾을 수 없는 경우, 아래 제공된 제목, 날짜, 미리보기 요약만을 사용하여 기사 내용을 파악하고 요약해 주세요.**\n"
        f"광고나 불필요한 정보 없이 핵심 내용만 간결하게 제공해 주세요.\n\n"
        f"제목: {title}\n"
        f"링크: {link}\n"
        f"날짜: {date_str}\n"
        f"미리보기 요약: {summary_snippet}"
    )
    
    # st.write(f"  - Potens.dev AI 호출 (기사 요약 요청)...") # UI 로그 제거
    for attempt in range(max_attempts):
        response_dict = call_potens_api_raw(initial_prompt, api_key=api_key)
        if "text" in response_dict:
            # st.write(f"    -> 시도 {attempt + 1} 성공.") # UI 로그 제거
            return response_dict["text"]
        else:
            error_msg = response_dict.get("error", "알 수 없는 오류")
            # st.write(f"    -> 시도 {attempt + 1} 실패: {error_msg}. 재시도합니다...") # UI 로그 제거
            if attempt < max_attempts - 1:
                time.sleep(delay_seconds)
            else:
                return f"Potens.dev AI 호출 최종 실패: {error_msg}"
    
    return "Potens.dev AI 호출에서 유효한 응답을 받지 못했습니다."

def get_relevant_keywords_from_ai(trending_keywords_data: list[dict], perspective: str, api_key: str, max_attempts: int = 2, delay_seconds: int = 15) -> list[str]:
    """
    Potens.dev AI를 호출하여 트렌드 키워드 중 특정 관점에서 유의미한 키워드를 선별합니다.
    반환 값: ['keyword1', 'keyword2', ...]
    """
    prompt_keywords = [{"keyword": k['keyword'], "recent_freq": k['recent_freq']} for k in trending_keywords_data]
    
    prompt = (
        f"다음은 뉴스 기사에서 식별된 트렌드 키워드 목록입니다. 이 키워드들을 '{perspective}'의 관점에서 "
        f"가장 유의미하다고 판단되는 순서대로 최대 5개까지 골라 JSON 배열 형태로 반환해 주세요. "
        f"다른 설명 없이 JSON 배열만 반환해야 합니다. 각 키워드는 문자열이어야 합니다.\n\n"
        f"키워드 목록: {json.dumps(prompt_keywords, ensure_ascii=False)}"
    )

    response_schema = {
        "type": "ARRAY",
        "items": {"type": "STRING"}
    }

    # st.info(f"AI가 '{perspective}' 관점에서 유의미한 키워드를 선별 중...") # UI 로그 제거
    for attempt in range(max_attempts):
        response_dict = call_potens_api_raw(prompt, api_key, response_schema=response_schema)
        if "text" in response_dict and isinstance(response_dict["text"], list):
            # st.success(f"AI 키워드 선별 성공 (시도 {attempt + 1}).") # UI 로그 제거
            return response_dict["text"]
        else:
            error_msg = response_dict.get("error", "알 수 없는 오류")
            # st.warning(f"AI 키워드 선별 실패 (시도 {attempt + 1}): {error_msg}. 재시도합니다...") # UI 로그 제거
            if attempt < max_attempts - 1:
                time.sleep(delay_seconds)
            else:
                # st.error(f"AI 키워드 선별 최종 실패: {error_msg}") # UI 로그 제거
                return []
    return []

def clean_ai_response_text(text: str) -> str:
    """
    AI 응답 텍스트에서 불필요한 마크다운 기호, 여러 줄바꿈,
    그리고 AI가 자주 사용하는 서두 문구들을 제거하여 평탄화합니다.
    """
    # 마크다운 코드 블록 제거 (예: ```json ... ```)
    cleaned_text = re.sub(r'```(?:json|text)?\s*([\s\S]*?)\s*```', r'\1', text, flags=re.IGNORECASE)
    
    # 마크다운 헤더, 리스트 기호, 볼드체/이탤릭체 기호 등 제거
    cleaned_text = re.sub(r'#|\*|-|\+', '', cleaned_text)
    
    # 번호가 매겨진 목록 마커 제거 (예: "1.", "2.", "3.")
    cleaned_text = re.sub(r'^\s*\d+\.\s*', '', cleaned_text, flags=re.MULTILINE)

    # AI가 자주 사용하는 서두 문구 제거 (정규표현식으로 유연하게 매칭)
    patterns_to_remove = [
        r'제공해주신\s*URL의\s*뉴스\s*기사\s*내용을\s*요약해드리겠습니다[.:\s]*', 
        r'주요\s*내용[.:\s]*', 
        r'제공해주신\s*텍스트를\s*요약\s*하겠\s*습니다[.:\s]*\s*요약[.:\s]*',
        r'요약해\s*드리겠습니다[.:\s]*\s*주요\s*내용\s*요약[.:\s]*',
        r'다음\s*텍스트의\s*요약입니다[.:\s]*',
        r'주요\s*내용을\s*요약\s*하면\s*다음과\s*같습니다[.:\s]*',
        r'핵심\s*내용은\s*다음과\s*같습니다[.:\s]*',
        r'요약하자면[.:\s]*',
        r'주요\s*요약[.:\s]*',
        r'텍스트를\s*요약하면\s*다음과\s*같습니다[.:\s]*', 
        r'제공된\s*텍스트에\s*대한\s*요약입니다[.:\s]*',
        r'다음은\s*ai가\s*내용을\s*요약한\s*것입니다[.:\s]*',
        r'먼저\s*최신\s*정보가\s*필요합니다[.:\s]*\s*현재\s*자율주행차\s*기술과\s*관련된\s*최신\s*트렌드를\s*확인해보겠습니다[.:\s]*',
        r'ai\s*답변[.:\s]*', 
        r'ai\s*분석[.:\s]*', 
        r'다음은\s*요청하신\s*링크의\s*본문\s*내용입니다[.:\s]*', 
        r'다음은\s*제공된\s*뉴스\s*기사의\s*핵심\s*내용입니다[.:\s]*', 
        r'뉴스\s*기사\s*주요\s*내용\s*요약[.:\s]*', 
        r'검색을\s*진행할\s*URL을\s*찾고\s*있어요[.:\s]*\s*\(1/3\)\s*제공해주신\s*URL에서\s*뉴스\s*기사의\s*주요\s*내용을\s*추출하겠습니다[.:\s]*', 
        r'검색을\s*진행할\s*URL을\s*찾았습니다[.:\s]*\s*\(1/3\)\s*해당\s*링크에서\s*뉴스\s*기사의\s*핵심\s*내용을\s*추출하겠습니다[.:\s]*', 
        r'검색을\s*진행할\s*URL을\s*찾고\s*있어요[.:\s]*\s*\(1/3\)\s*제공해주신\s*링크에서\s*기사\s*내용을\s*추출하겠습니다[.:\s]*', 
        r'검색을\s*진행할\s*URL을\s*찾고\s*있어요[.:\s]*\s*\(1/3\)\s*해당\s*URL에서\s*뉴스\s*기사의\s*주요\s*내용을\s*추출하겠습니다[.:\s]*', 
        r'검색을\s*진행할\s*URL을\s*찾고\s*있어요[.:\s]*\s*\(1/3\)\s*URL을\s*검색하여\s*기사\s*내용을\s*확인하겠습니다[.:\s]*\s*검색\s*결과를\s*바탕으로\s*다음과\s*같이\s*기사의\s*핵심\s*내용만\s*추출했습니다[.:\s]*', 
        r'검색을\s*진행할\s*URL을\s*찾고\s*있어요[.:\s]*\s*\(1/3\)\s*해당\s*URL에서\s*기사\s*내용을\s*확인하겠습니다[.:\s]*\s*기사의\s*주요\s*내용을\s*추출했습니다[.:\s]*', 
        r'검색을\s*진행할\s*URL을\s*찾고\s*있어요[.:\s]*\s*\(1/3\)\s*웹사이트의\s*내용을\s*확인하겠습니다[.:\s]*\s*기사의\s*주요\s*내용을\s*광고나\s*불필요한\s*정보\s*없이\s*추출해\s*드리겠습니다[.:\s]*', 
        r'이상입니다[.:\s]*', 
        r'이상입니다[.:\s]*\s*광고나\s*불필요한\s*정보는\s*제외하고\s*주요\s*내용만\s*추출했습니다[.:\s]*', 
        r'이것이\s*제공해주신\s*YTN\s*뉴스\s*링크에서\s*추출한\s*핵심\s*기사\s*내용입니다[.:\s]*\s*광고나\s*불필요한\s*정보는\s*제외하고\s*기사의\s*주요\s*내용만\s*추출했습니다[.:\s]*', 
        r'위\s*내용은\s*제공해주신\s*URL에서\s*추출한\s*기사의\s*핵심\s*내용입니다[.:\s]*\s*광고나\s*불필요한\s*정보를\s*제거하고\s*주요\s*내용만\s*정리했습니다[.:\s]*', 
        r'제공해주신\s*링크\(https?://[^\s]+\)\s*는\s*연합뉴스의\s*사진\s*기사로,\s*\d{4}년\s*\d{1,2}월\s*\d{1,2}일에\s*게시된\s*내용입니다[.:\s]*\s*기사\s*제목:\s*""[^""]+""\s*핵심\s*내용:[.:\s]*', 
    ]
    for pattern in patterns_to_remove:
        cleaned_text = re.sub(pattern, '', cleaned_text, flags=re.IGNORECASE)

    # 여러 개의 줄바꿈을 하나의 공백으로 대체
    cleaned_text = re.sub(r'\n+', ' ', cleaned_text)
    # 여러 개의 공백을 하나로 대체 (줄바꿈 대체 후에도 중복 공백이 생길 수 있으므로)
    cleaned_text = re.sub(r'\s+', ' ', cleaned_text).strip()
    return cleaned_text

# --- 키워드 추출 및 트렌드 분석 함수들 ---

def get_keywords_from_text(text: str) -> list[str]:
    """
    텍스트에서 키워드를 추출합니다.
    간단한 토큰화, 소문자 변환, 불용어 제거를 수행합니다.
    더 정교한 키워드 추출을 위해서는 형태소 분석기(꼬꼬마, konlpy 등)가 필요할 수 있습니다.
    """
    # 한글, 영어, 숫자만 남기고 특수문자 제거
    text = re.sub(r'[^가-힣a-zA-Z0-9\s]', '', text)
    tokens = text.lower().split()
    
    # 일반적인 불용어 목록 (확장 가능)
    stopwords = ["은", "는", "이", "가", "을", "를", "와", "과", "도", "만", "고", "에", "의", "한", "그", "저", "것", "수", "등", "및", "대한", "통해", "이번", "지난", "다", "있다", "없다", "한다", "된다", "밝혔다", "말했다", "했다", "위해", "으로", "에서", "으로", "로부터", "까지", "부터", "으로", "하여", "에게", "처럼", "만큼", "듯이", "보다", "아니라", "아니면", "그리고", "그러나", "하지만", "따라서", "때문에", "대해", "관련", "지난", "최근", "이번", "이날", "오전", "오후", "오후", "오전", "기자", "뉴스", "연합뉴스", "조선비즈", "한겨레", "YTN", "MBN", "뉴시스", "매일경제", "한국경제"]
    
    # 두 글자 이상인 단어만 포함하고 불용어 제거
    keywords = [word for word in tokens if len(word) > 1 and word not in stopwords]
    return keywords

def analyze_keyword_trends(articles_metadata: list[dict], recent_days_period: int = 2, total_days_period: int = 15, min_surge_ratio: float = 1.5, min_recent_freq: int = 3) -> list[dict]:
    """
    기사 메타데이터를 기반으로 키워드 트렌드를 분석합니다.
    recent_days_period: 트렌드를 감지할 최근 기간 (예: 2일)
    total_days_period: 비교할 전체 기간 (예: 15일)
    min_surge_ratio: 최근 기간 빈도 / 과거 기간 빈도 비율이 이 값 이상일 때 트렌드로 간주
    min_recent_freq: 최근 기간에 최소한 이 횟수 이상 언급되어야 트렌드로 간주
    반환 값: [{keyword: str, recent_freq: int, past_freq: int, surge_ratio: float}]
    """
    if not articles_metadata:
        return []

    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    recent_articles = []
    past_articles = []

    for article in articles_metadata:
        article_date = article.get("날짜")
        if not isinstance(article_date, datetime):
            # 날짜 파싱 실패한 경우, 오늘 날짜로 간주하여 처리 (정확도 낮음)
            st.warning(f"경고: '{article['제목']}' 기사의 날짜 파싱 실패. 오늘 날짜로 간주하여 분석에 포함합니다.")
            article_date = today

        if today - timedelta(days=recent_days_period) <= article_date:
            recent_articles.append(article)
        elif today - timedelta(days=total_days_period) <= article_date < today - timedelta(days=recent_days_period):
            past_articles.append(article)

    # 각 기간의 키워드 빈도 계산
    recent_keywords = Counter()
    for article in recent_articles:
        # 트렌드 분석 시 제목과 미리보기 스니펫 모두 활용
        text_for_keywords = article["제목"] + " " + article.get("내용", "") # '내용'이 이제 미리보기 스니펫
        recent_keywords.update(get_keywords_from_text(text_for_keywords))

    past_keywords = Counter()
    for article in past_articles:
        # 트렌드 분석 시 제목과 미리보기 스니펫 모두 활용
        text_for_keywords = article["제목"] + " " + article.get("내용", "") # '내용'이 이제 미리보기 스니펫
        past_keywords.update(get_keywords_from_text(text_for_keywords))

    trending_keywords_list = [] # 리스트 형태로 변경
    for keyword, recent_freq in recent_keywords.items():
        past_freq = past_keywords.get(keyword, 0) # 과거 기간에 없으면 0
        
        # 최근 기간에 최소 빈도 이상이어야 함
        if recent_freq < min_recent_freq:
            continue

        surge_ratio = None
        if past_freq == 0:
            # 과거에 없었는데 최근에 나타난 키워드는 트렌드로 간주
            if recent_freq >= min_recent_freq: 
                surge_ratio = float('inf') # 무한대로 표현
        else:
            surge_ratio = recent_freq / past_freq
            if surge_ratio < min_surge_ratio: # 최소 증가율 미달 시 트렌드 아님
                continue
        
        trending_keywords_list.append({
            "keyword": keyword,
            "recent_freq": recent_freq,
            "past_freq": past_freq,
            "surge_ratio": surge_ratio
        })
    
    # 빈도 높은 순으로 정렬
    trending_keywords_list = sorted(trending_keywords_list, key=lambda x: x['recent_freq'], reverse=True)
    
    # st.info(f"--- 키워드 트렌드 분석 완료 ---") # UI 로그 제거
    # st.info(f"  - 최근 {recent_days_period}일간 기사 수: {len(recent_articles)}") # UI 로그 제거
    # st.info(f"  - 과거 {total_days_period - recent_days_period}일간 기사 수: {len(past_articles)}") # UI 로그 제거
    # st.info(f"  - 식별된 트렌드 키워드 ({len(trending_keywords_list)}개): {[kw['keyword'] for kw in trending_keywords_list]}") # UI 로그 제거
    
    return trending_keywords_list

# --- SQLite 데이터베이스 함수 ---
DB_FILE = 'news_data.db'

def init_db():
    """데이터베이스를 초기화하고 테이블을 생성합니다."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            link TEXT UNIQUE NOT NULL,
            date TEXT NOT NULL,
            content TEXT,
            crawl_timestamp TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

def insert_article(article: dict):
    """기사 데이터를 데이터베이스에 삽입합니다. 중복 링크는 건너뛰거나 업데이트합니다."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        # 링크가 이미 존재하면 업데이트, 없으면 삽입
        c.execute("INSERT OR REPLACE INTO articles (link, title, date, content, crawl_timestamp) VALUES (?, ?, ?, ?, ?)",
                  (article['링크'], article['제목'], article['날짜'], article['내용'], datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()
    except Exception as e:
        print(f"오류: 데이터베이스 삽입/업데이트 실패 - {e} (링크: {article['링크']})")
    finally:
        conn.close()

def get_all_articles():
    """데이터베이스의 모든 기사 데이터를 가져옵니다."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT title, link, date, content, crawl_timestamp FROM articles ORDER BY date DESC, crawl_timestamp DESC")
    articles = c.fetchall()
    conn.close()
    return articles

def clear_db_content():
    """데이터베이스의 모든 기사 기록을 삭제합니다."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        c.execute("DELETE FROM articles")
        conn.commit()
        # st.success("데이터베이스의 모든 기록이 성공적으로 삭제되었습니다.") # 이 메시지는 세션 상태로 관리
        st.session_state['db_status_message'] = "데이터베이스의 모든 기록이 성공적으로 삭제되었습니다."
        st.session_state['db_status_type'] = "success"
    except Exception as e:
        # st.error(f"데이터베이스 초기화 중 오류 발생: {e}") # 이 메시지도 세션 상태로 관리
        st.session_state['db_status_message'] = f"데이터베이스 초기화 중 오류 발생: {e}"
        st.session_state['db_status_type'] = "error"
    finally:
        conn.close()

# --- Streamlit 앱 시작 ---
st.set_page_config(layout="wide", page_title="뉴스 트렌드 분석기")

st.title("📰 뉴스 트렌드 분석기")
st.markdown("원하는 키워드로 네이버 뉴스 트렌드를 감지하고, AI가 요약한 기사 내용을 확인하세요.")

# --- Potens.dev AI API 키 설정 ---
load_dotenv() # .env 파일 로드
POTENS_API_KEY = os.getenv("POTENS_API_KEY")

if not POTENS_API_KEY:
    st.error("🚨 오류: .env 파일에 'POTENS_API_KEY'가 설정되지 않았습니다. Potens.dev AI 기능을 사용할 수 없습니다.")
    st.stop() # API 키 없으면 앱 실행 중단

# 데이터베이스 초기화
init_db()

# --- Streamlit Session State 초기화 (앱이 처음 로드될 때만 실행) ---
# 세션 상태가 초기화되지 않았다면 기본값 설정
if 'trending_keywords_data' not in st.session_state:
    st.session_state['trending_keywords_data'] = [] # 전체 트렌드 키워드 (내부 분석용)
if 'displayed_trending_keywords' not in st.session_state:
    st.session_state['displayed_trending_keywords'] = [] # UI에 표시될 필터링된 트렌드 키워드
if 'final_collected_articles' not in st.session_state:
    st.session_state['final_collected_articles'] = [] # AI 요약된 최종 기사 목록
# submitted_flag는 폼 제출 시에만 True가 되도록 유지
if 'submitted_flag' not in st.session_state:
    st.session_state['submitted_flag'] = False
# analysis_completed 플래그는 분석 완료 시 True
if 'analysis_completed' not in st.session_state:
    st.session_state['analysis_completed'] = False
# DB 초기화 후 표시될 메시지
if 'db_status_message' not in st.session_state:
    st.session_state['db_status_message'] = ""
if 'db_status_type' not in st.session_state:
    st.session_state['db_status_type'] = ""


# --- UI 레이아웃: 검색 조건 (좌) & 키워드 트렌드 결과 (우) ---
col_search_input, col_trend_results = st.columns([1, 2]) # 1:2 비율로 컬럼 분할

with col_search_input:
    st.header("🔍 검색 조건 설정")
    with st.form("search_form"):
        keyword = st.text_input("검색할 뉴스 키워드 (예: '전기차')", value="전기차", key="keyword_input")
        total_search_days = st.number_input("총 몇 일간의 뉴스를 검색할까요? (예: 15)", min_value=1, value=15, key="total_days_input")
        recent_trend_days = st.number_input("최근 몇 일간의 데이터를 기준으로 트렌드를 분석할까요? (예: 2)", min_value=1, value=2, key="recent_days_input")
        max_naver_search_pages_per_day = st.number_input("각 날짜별로 네이버 뉴스 검색 결과 몇 페이지까지 크롤링할까요? (페이지당 10개 기사, 예: 3)", min_value=1, value=3, key="max_pages_input")
        
        # 폼 제출 버튼
        submitted = st.form_submit_button("뉴스 트렌드 분석 시작")

with col_trend_results:
    st.header("📈 키워드 트렌드 분석 결과")
    st.markdown("다음은 최근 언급량이 급증한 트렌드 키워드입니다.")
    
    # 이 컨테이너는 분석 진행 상황 메시지나 초기 메시지, 최종 결과를 표시합니다.
    # 표와 메시지를 분리하여 관리
    table_placeholder = st.empty() # 표를 표시할 컨테이너
    status_message_placeholder = st.empty() # 상태 메시지를 표시할 컨테이너

    # --- 분석 실행 및 결과 표시 (submitted 버튼 클릭 시) ---
    if submitted:
        # 새로운 검색 요청 시 기존 상태 초기화
        st.session_state['trending_keywords_data'] = []
        st.session_state['displayed_trending_keywords'] = []
        st.session_state['final_collected_articles'] = []
        st.session_state['submitted_flag'] = True # 제출 플래그 설정
        st.session_state['analysis_completed'] = False # 분석 완료 플래그 초기화
        st.session_state['db_status_message'] = "" # DB 초기화 메시지 초기화
        st.session_state['db_status_type'] = "" # DB 초기화 메시지 타입 초기화
        
        # results_display_container를 비우고 새로운 진행 상황 표시
        table_placeholder.empty() # 표 컨테이너 비우기
        my_bar = status_message_placeholder.progress(0, text="데이터 수집 및 분석 진행 중...") # 진행바와 메시지 표시
        status_message_placeholder.info("네이버 뉴스 메타데이터 수집 중...") 

        if recent_trend_days >= total_search_days:
            status_message_placeholder.error("오류: 최근 트렌드 분석 기간은 총 검색 기간보다 짧아야 합니다.")
        else:
            all_collected_news_metadata = []
            
            # --- 1. 네이버 뉴스 메타데이터 수집 ---
            # 오늘 날짜 기준으로 검색 시작 날짜 계산 (submitted 블록 안에서 사용)
            today_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            search_start_date = today_date - timedelta(days=total_search_days - 1)

            total_iterations = total_search_days * max_naver_search_pages_per_day
            current_iteration = 0

            for i in range(total_search_days):
                current_search_date = search_start_date + timedelta(days=i)
                formatted_search_date = current_search_date.strftime('%Y.%m.%d')

                for page in range(max_naver_search_pages_per_day):
                    current_iteration += 1
                    my_bar.progress(current_iteration / total_iterations, text=f"뉴스 메타데이터 수집 중... ({formatted_search_date}, {page+1}페이지)")
                    
                    start_num = page * 10 + 1
                    search_url = (
                        f"https://search.naver.com/search.naver?where=news&query={keyword}"
                        f"&sm=tab_opt&sort=0&photo=0&field=0&pd=3"
                        f"&ds={formatted_search_date}"
                        f"&de={formatted_search_date}"
                        f"&start={start_num}"
                    )
                    
                    try:
                        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36 Edg/138.0.0.0'}
                        response = requests.get(search_url, headers=headers)
                        response.raise_for_status()
                        soup = BeautifulSoup(response.text, "html.parser")

                        title_spans = soup.find_all("span", class_="sds-comps-text-type-headline1")

                        if not title_spans:
                            break
                        else:
                            articles_on_this_page = 0
                            for title_span in title_spans:
                                link_tag = title_span.find_parent('a') 
                                
                                if link_tag and 'href' in link_tag.attrs:
                                    title = title_span.text.strip()
                                    link = link_tag['href']
                                    
                                    summary_snippet_text = ""
                                    next_sibling_a_tag = link_tag.find_next_sibling('a')
                                    if next_sibling_a_tag:
                                        snippet_span = next_sibling_a_tag.find('span', class_='sds-comps-text-type-body1')
                                        if snippet_span:
                                            summary_snippet_text = snippet_span.get_text(strip=True)
                                        else:
                                            summary_snippet_text = next_sibling_a_tag.get_text(strip=True)
                                    
                                    if not (link.startswith('javascript:') or 'ad.naver.com' in link):
                                        pub_date_obj = current_search_date
                                        
                                        article_data_for_db = { # DB 저장을 위한 데이터
                                            "제목": title,
                                            "링크": link,
                                            "날짜": pub_date_obj.strftime('%Y-%m-%d'), # DB 저장을 위해 문자열로 변환
                                            "내용": summary_snippet_text if summary_snippet_text else "" # None 방지
                                        }
                                        all_collected_news_metadata.append({ # 트렌드 분석을 위한 데이터
                                            "제목": title,
                                            "링크": link,
                                            "날짜": pub_date_obj, # datetime 객체 유지
                                            "내용": summary_snippet_text
                                        })
                                        insert_article(article_data_for_db) # DB에 저장
                                        articles_on_this_page += 1
                        
                        if articles_on_this_page == 0:
                            break
                        
                        time.sleep(0.5)

                    except requests.exceptions.RequestException as e:
                        status_message_placeholder.error(f"웹 페이지 요청 중 오류 발생 ({formatted_search_date} 날짜, 페이지 {page + 1}): {e}")
                        break
                    except Exception as e:
                        status_message_placeholder.error(f"스크립트 실행 중 오류 발생 ({formatted_search_date} 날짜, 페이지 {page + 1}): {e}")
                        break
            my_bar.empty() # 프로그레스 바 숨기기
            status_message_placeholder.success(f"총 {len(all_collected_news_metadata)}개의 뉴스 메타데이터를 수집했습니다.")

            # --- 2. 키워드 트렌드 분석 실행 ---
            status_message_placeholder.info("키워드 트렌드 분석 중...")
            with st.spinner("키워드 트렌드 분석 중..."): # 스피너는 유지
                trending_keywords_data = analyze_keyword_trends(
                    all_collected_news_metadata, 
                    recent_days_period=recent_trend_days, 
                    total_days_period=total_search_days
                )
            st.session_state['trending_keywords_data'] = trending_keywords_data # 세션 상태에 전체 트렌드 키워드 저장
            
            if trending_keywords_data:
                # status_message_placeholder.markdown("다음은 최근 언급량이 급증한 트렌드 키워드입니다.") # UI에 이미 설명 있음
                
                # --- AI가 보험 개발자 관점에서 유의미한 키워드 선별 ---
                relevant_keywords_from_ai_raw = []
                with st.spinner("AI가 보험 개발자 관점에서 유의미한 키워드를 선별 중..."):
                    relevant_keywords_from_ai_raw = get_relevant_keywords_from_ai(
                        trending_keywords_data, 
                        "차량보험사의 보험개발자", 
                        POTENS_API_KEY
                    )
                
                # AI가 반환한 키워드 문자열 리스트를 실제 trending_keywords_data와 매칭
                filtered_trending_keywords = []
                if relevant_keywords_from_ai_raw:
                    # AI가 반환한 키워드만 필터링하고, 원래의 빈도 데이터를 유지
                    filtered_trending_keywords = [
                        kw_data for kw_data in trending_keywords_data 
                        if kw_data['keyword'] in relevant_keywords_from_ai_raw
                    ]
                    # 다시 빈도 높은 순으로 정렬 (AI가 순서를 주지 않을 수 있으므로)
                    filtered_trending_keywords = sorted(filtered_trending_keywords, key=lambda x: x['recent_freq'], reverse=True)
                    
                    status_message_placeholder.info(f"AI가 선별한 보험 개발자 관점의 유의미한 키워드 ({len(filtered_trending_keywords)}개): {[kw['keyword'] for kw in filtered_trending_keywords]}")
                else:
                    status_message_placeholder.warning("AI가 보험 개발자 관점에서 유의미한 키워드를 선별하지 못했습니다. 모든 트렌드 키워드를 표시합니다.")
                    filtered_trending_keywords = trending_keywords_data # AI 선별 실패 시 전체 트렌드 키워드 사용

                # 상위 3개 키워드만 최종 트렌드로 인정 (UI에 표시될 키워드)
                top_3_relevant_keywords = filtered_trending_keywords[:3]
                st.session_state['displayed_trending_keywords'] = top_3_relevant_keywords # 세션 상태에 UI 표시용 저장

                if top_3_relevant_keywords:
                    # st.markdown(f"**보험 개발자 관점에서 가장 유의미한 상위 {len(top_3_relevant_keywords)}개 트렌드 키워드:**") # UI에 이미 설명 있음
                    # 결과 테이블은 나중에 results_display_container를 통해 단일 표시
                    pass # 테이블 표시 로직은 최종 표시 부분으로 이동
                else:
                    status_message_placeholder.info("보험 개발자 관점에서 유의미한 트렌드 키워드가 식별되지 않았습니다.")


                # --- 3. 트렌드 기사 본문 요약 (Potens.dev AI 활용) ---
                status_message_placeholder.info("트렌드 기사 본문 요약 중 (Potens.dev AI 호출)...")
                
                recent_trending_articles_candidates = [
                    article for article in all_collected_news_metadata
                    if article.get("날짜") and today_date - timedelta(days=recent_trend_days) <= article["날짜"]
                ]

                processed_links = set()
                
                # AI 요약 대상 기사 필터링 (상위 3개 키워드를 포함하는 기사만)
                articles_for_ai_summary = []
                for article in recent_trending_articles_candidates:
                    text_for_trend_check = article["제목"] + " " + article.get("내용", "")
                    article_keywords_for_trend = get_keywords_from_text(text_for_trend_check)
                    
                    # 상위 3개 트렌드 키워드 중 하나라도 포함하는 기사만 선택
                    if any(trend_kw['keyword'] in article_keywords_for_trend for trend_kw in top_3_relevant_keywords):
                        articles_for_ai_summary.append(article)
                
                total_ai_articles_to_process = len(articles_for_ai_summary)

                if total_ai_articles_to_process == 0:
                    status_message_placeholder.info("선별된 트렌드 키워드를 포함하는 최근 기사가 없거나, AI 요약 대상 기사가 없습니다.")
                else:
                    ai_progress_bar = st.progress(0, text=f"AI가 트렌드 기사를 요약 중... (0/{total_ai_articles_to_process} 완료)")
                    ai_processed_count = 0

                    temp_collected_articles = [] # AI 요약 결과를 임시 저장할 리스트
                    for article in articles_for_ai_summary:
                        if article["링크"] in processed_links:
                            continue # 중복 링크 건너뛰기

                        ai_processed_count += 1
                        ai_progress_bar.progress(ai_processed_count / total_ai_articles_to_process, text=f"AI가 트렌드 기사를 요약 중... ({ai_processed_count}/{total_ai_articles_to_process} 완료)")
                        
                        # st.markdown(f"**[트렌드 기사] {article['제목']}**") # 웹 UI에 기사 제목 표시 (이제 요약은 파일로만)
                        
                        article_date_str = article["날짜"].strftime('%Y-%m-%d') if article["날짜"] else 'N/A'

                        ai_processed_content = call_potens_ai_for_article_summary_with_context_single_call(
                            article["제목"], 
                            article["링크"], 
                            article_date_str, 
                            article["내용"], # 미리보기 스니펫
                            POTENS_API_KEY, 
                            max_attempts=2
                        )
                        
                        final_content = ""
                        if ai_processed_content.startswith("Potens.dev AI 호출 최종 실패") or \
                           ai_processed_content.startswith("Potens.dev AI 호출에서 유효한 응답을 받지 못했습니다."):
                            final_content = f"본문 요약 실패 (AI 오류): {ai_processed_content}"
                            status_message_placeholder.error(f"AI 요약 실패: {final_content}") 
                        else:
                            final_content = clean_ai_response_text(ai_processed_content)
                        
                        temp_collected_articles.append({ # 임시 리스트에 추가
                            "제목": article["제목"],
                            "링크": article["링크"],
                            "날짜": article_date_str,
                            "내용": final_content # AI가 요약한 내용
                        })
                        processed_links.add(article["링크"])
                        time.sleep(0.1) # 각 기사 처리 사이에 짧은 딜레이

                    ai_progress_bar.empty() # AI 요약 프로그레스 바 숨기기
                    st.session_state['final_collected_articles'] = temp_collected_articles # 최종적으로 세션 상태에 저장

                    if st.session_state['final_collected_articles']: # 세션 상태의 데이터를 참조
                        status_message_placeholder.success(f"총 {len(st.session_state['final_collected_articles'])}개의 트렌드 기사 요약을 완료했습니다.")
                    else:
                        status_message_placeholder.info("선별된 트렌드 키워드를 포함하는 기사가 없거나, AI 요약에 실패했습니다.")
                
            else: # trending_keywords_data가 없는 경우
                status_message_placeholder.info("선택된 기간 내에 식별된 트렌드 키워드가 없습니다.")
        
        # submitted 플래그는 제출 후 다시 False로 설정하여 다음 렌더링 시 자동 실행 방지
        st.session_state['submitted_flag'] = False 
        st.session_state['analysis_completed'] = True # 분석 완료 플래그 설정

    # --- 결과가 이미 세션 상태에 있는 경우 표시 ---
    # submitted가 False일 때 (즉, 새로고침되거나 다른 위젯이 변경될 때)
    # 세션 상태에 저장된 데이터가 있고, 분석이 완료된 상태라면 해당 데이터를 results_display_container에 표시
    if not st.session_state.get('submitted_flag', False) and \
       st.session_state.get('analysis_completed', False): # 분석 완료 상태일 때만 표시
        if st.session_state['displayed_trending_keywords']: # 필터링된 키워드 사용
            df_top_keywords = pd.DataFrame(st.session_state['displayed_trending_keywords'])
            df_top_keywords['surge_ratio'] = df_top_keywords['surge_ratio'].apply(
                lambda x: f"{x:.2f}x" if x != float('inf') else "새로운 트렌드"
            )
            table_placeholder.table(df_top_keywords) # 최종 결과를 table_placeholder에 표시

            if st.session_state['final_collected_articles']:
                status_message_placeholder.success(f"총 {len(st.session_state['final_collected_articles'])}개의 트렌드 기사 요약을 완료했습니다.")
        else: # 트렌드 키워드가 없는데 분석은 완료된 경우
            status_message_placeholder.info("선택된 기간 내에 유의미한 트렌드 키워드가 식별되지 않았습니다.")
    # --- 초기 로드 시 메시지 (submitted_flag가 False이고, 아직 분석이 완료되지 않은 경우) ---
    elif not st.session_state.get('submitted_flag', False) and \
         not st.session_state.get('analysis_completed', False):
        # 초기에는 빈 표를 보여주고, 그 아래에 안내 메시지를 표시
        empty_df = pd.DataFrame(columns=['keyword', 'recent_freq', 'past_freq', 'surge_ratio'])
        table_placeholder.table(empty_df) # 빈 표를 미리 렌더링
        status_message_placeholder.info("검색 조건을 입력하고 '뉴스 트렌드 분석 시작' 버튼을 눌러주세요!")


# --- 데이터 다운로드 섹션 ---
st.header("📥 데이터 다운로드")
all_db_articles = get_all_articles()

if all_db_articles:
    # content 필드가 None인 경우 빈 문자열로 대체하여 CSV/Excel 깨짐 방지
    df_all_articles = pd.DataFrame(all_db_articles, columns=['제목', '링크', '날짜', '내용', '수집_시간'])
    df_all_articles['내용'] = df_all_articles['내용'].fillna('') # None 값을 빈 문자열로 채우기
    
    # CSV 데이터 생성
    csv_data = df_all_articles.to_csv(index=False, encoding='utf-8-sig')
    
    # TXT 데이터 생성 (모든 수집 뉴스)
    txt_data_lines = []
    for index, row in df_all_articles.iterrows():
        txt_data_lines.append(f"제목: {row['제목']}")
        txt_data_lines.append(f"링크: {row['링크']}")
        txt_data_lines.append(f"날짜: {row['날짜']}")
        txt_data_lines.append(f"내용: {row['내용']}")
        txt_data_lines.append(f"수집 시간: {row['수집_시간']}")
        txt_data_lines.append("-" * 50) # 구분선
    txt_data_all_crawled = "\n".join(txt_data_lines) # 리스트를 문자열로 변환

    # AI 요약된 기사 데이터 생성 (final_collected_articles)
    # final_collected_articles가 비어있을 경우 빈 DataFrame 생성
    df_ai_summaries = pd.DataFrame(st.session_state['final_collected_articles'], 
                                   columns=['제목', '링크', '날짜', '내용']) # 컬럼 명시
    df_ai_summaries['내용'] = df_ai_summaries['내용'].fillna('') # None 값 처리

    # AI 요약 TXT 데이터 생성 (수정된 부분)
    txt_data_summaries_lines = []
    if not df_ai_summaries.empty:
        for index, row in df_ai_summaries.iterrows():
            txt_data_summaries_lines.append(f"제목: {row['제목']}")
            txt_data_summaries_lines.append(f"링크: {row['링크']}")
            txt_data_summaries_lines.append(f"날짜: {row['날짜']}")
            txt_data_summaries_lines.append(f"요약 내용: {row['내용']}")
            txt_data_summaries_lines.append("-" * 50)
    txt_data_ai_summaries = "\n".join(txt_data_summaries_lines) # 리스트를 문자열로 변환

    # AI 요약 XLSX 데이터 생성
    excel_data_ai_summaries = None
    if not df_ai_summaries.empty:
        # BytesIO 객체를 사용하여 메모리에서 Excel 파일 생성
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df_ai_summaries.to_excel(writer, index=False, sheet_name='AI_Summaries')
        excel_data_ai_summaries = output.getvalue()


    st.markdown("### 📊 수집된 전체 뉴스 데이터")
    col_all_data1, col_all_data2, col_all_data3 = st.columns(3)
    with col_all_data1:
        st.download_button(
            label="📄 TXT 다운로드",
            data=txt_data_all_crawled,
            file_name=f"all_crawled_news_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
            mime="text/plain",
            help="데이터베이스에 저장된 모든 뉴스를 텍스트 파일로 다운로드합니다."
        )
    with col_all_data2:
        st.download_button(
            label="📊 CSV 다운로드",
            data=csv_data,
            file_name=f"all_crawled_news_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
            help="데이터베이스에 저장된 모든 뉴스를 CSV 파일로 다운로드합니다. (엑셀에서 깨질 경우 아래 안내 참조)"
        )
    with col_all_data3:
        # XLSX 다운로드 (모든 수집 뉴스)
        excel_data_all_crawled = None
        output_all_crawled = BytesIO()
        with pd.ExcelWriter(output_all_crawled, engine='xlsxwriter') as writer:
            df_all_articles.to_excel(writer, index=False, sheet_name='All_Crawled_News')
        excel_data_all_crawled = output_all_crawled.getvalue()

        st.download_button(
            label="엑셀 다운로드",
            data=excel_data_all_crawled, # BytesIO.getvalue()로 변환된 데이터 사용
            file_name=f"all_crawled_news_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            help="데이터베이스에 저장된 모든 뉴스를 엑셀 파일(.xlsx)로 다운로드합니다. (한글 깨짐 없음)"
        )
    
    if not df_ai_summaries.empty:
        st.markdown("### 📝 AI 요약 기사")
        col_ai1, col_ai2 = st.columns(2)
        with col_ai1:
            st.download_button(
                label="📄 AI 요약 TXT 다운로드",
                data=txt_data_ai_summaries, # 수정된 부분: 문자열로 변환된 변수를 사용합니다.
                file_name=f"ai_summaries_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                mime="text/plain",
                help="AI가 요약한 트렌드 기사 내용을 텍스트 파일로 다운로드합니다."
            )
        with col_ai2:
            st.download_button(
                label="📊 AI 요약 엑셀 다운로드",
                data=excel_data_ai_summaries,
                file_name=f"ai_summaries_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                help="AI가 요약한 트렌드 기사 내용을 엑셀 파일(.xlsx)로 다운로드합니다."
            )
    else:
        st.info("AI 요약된 트렌드 기사가 없습니다. 먼저 분석을 실행하여 요약된 기사를 생성하세요.")


    st.markdown("---") # 구분선 추가
    col_db_info, col_db_clear = st.columns([2, 1])
    with col_db_info:
        st.info(f"현재 데이터베이스에 총 {len(all_db_articles)}개의 기사가 저장되어 있습니다.")
        # DB 초기화 후 메시지 표시
        if st.session_state['db_status_message']:
            if st.session_state['db_status_type'] == "success":
                st.success(st.session_state['db_status_message'])
            elif st.session_state['db_status_type'] == "error":
                st.error(st.session_state['db_status_message'])
            st.session_state['db_status_message'] = "" # 메시지 표시 후 초기화
            st.session_state['db_status_type'] = ""
        st.markdown("💡 **CSV 파일이 엑셀에서 깨질 경우:** 엑셀에서 '데이터' 탭 -> '텍스트/CSV 가져오기'를 클릭한 후, '원본 파일' 인코딩을 'UTF-8'로 선택하여 가져오세요.")
    with col_db_clear:
        if st.button("데이터베이스 초기화", help="데이터베이스의 모든 저장된 뉴스를 삭제합니다.", type="secondary"):
            clear_db_content()
            # 세션 상태 초기화하여 화면도 비우기
            st.session_state['trending_keywords_data'] = []
            st.session_state['displayed_trending_keywords'] = []
            st.session_state['final_collected_articles'] = []
            st.session_state['submitted_flag'] = False
            st.session_state['analysis_completed'] = False # 분석 완료 플래그도 초기화
            st.rerun() # DB 초기화 후 앱 재실행하여 화면 업데이트

