import requests
from bs4 import BeautifulSoup
from datetime import datetime
import time # 요청 사이에 딜레이를 주기 위해 추가 (서버 부하 방지)
import csv # CSV 파일 저장을 위해 추가
import json # Potens.dev API 응답이 JSON일 경우를 대비
import re # AI 응답 정제를 위해 추가
import os # For loading environment variables
from dotenv import load_dotenv # For loading .env file

# --- Potens.dev AI API 호출 및 응답 처리를 위한 함수들 ---

def call_potens_api_raw(prompt_message: str, api_key: str) -> dict:
    """
    주어진 프롬프트 메시지로 Potens.dev API를 호출하고 원본 응답을 반환합니다.
    이 함수는 Potens.dev API의 기본 응답 형태를 직접 반환합니다 (message 키 등).
    """
    if not api_key:
        return {"error": "API 키가 누락되었습니다."}

    # Potens.dev API 엔드포인트는 일반적으로 https://ai.potens.ai/api/chat 입니다.
    # 만약 다른 엔드포인트를 사용하신다면 아래 URL을 수정해주세요.
    potens_api_endpoint = "https://ai.potens.ai/api/chat" 

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "prompt": prompt_message # AI에게 전달할 메시지
    }

    try:
        response = requests.post(potens_api_endpoint, headers=headers, json=payload, timeout=300) # 타임아웃 5분 (300초)
        response.raise_for_status() # HTTP 에러 발생 시 예외 발생
        
        response_json = response.json()
        
        if "message" in response_json:
            return {"text": response_json["message"].strip(), "raw_response": response_json}
        else:
            return {"error": "API 응답 형식이 올바르지 않습니다.", "raw_response": response_json}

    except requests.exceptions.RequestException as e:
        error_message = f"API 호출 오류 발생 (네트워크/타임아웃/HTTP): {e}"
        if e.response is not None:
            error_message += f" Response content: {e.response.text}" 
        return {"error": error_message}
    except json.JSONDecodeError:
        return {"error": f"API 응답 JSON 디코딩 오류: {response.text}"}
    except Exception as e:
        return {"error": f"알 수 없는 오류 발생: {e}"}

def call_potens_api_with_confirmation(link: str, api_key: str, max_attempts: int = 2, delay_seconds: int = 15) -> str:
    """
    Potens.dev API를 호출하여 뉴스 기사 내용을 가져오고,
    추가적인 프롬프트로 AI에게 답변을 확인/재평가하도록 요청합니다.
    """
    initial_prompt = f"이거 뉴스 기사 검색하고 그 내용 반환해줘\n\n링크: {link}"
    first_response = None
    
    print(f"  - 1단계 AI 호출 (초기 내용 추출)...")
    for attempt in range(max_attempts):
        response_dict = call_potens_api_raw(initial_prompt, api_key=api_key)
        if "text" in response_dict:
            first_response = response_dict["text"]
            print(f"    -> 1단계 시도 {attempt + 1} 성공.")
            break
        else:
            error_msg = response_dict.get("error", "알 수 없는 오류")
            print(f"    -> 1단계 시도 {attempt + 1} 실패: {error_msg}. 재시도합니다...")
            if attempt < max_attempts - 1:
                time.sleep(delay_seconds)
            else:
                return f"1단계 AI 호출 최종 실패: {error_msg}"
    
    if first_response is None:
        return "1단계 AI 호출에서 유효한 응답을 받지 못했습니다."

    # 2단계: AI에게 1차 응답을 바탕으로 확인/재평가 요청
    confirmation_prompt = (
        f"당신이 이전에 제공한 요약이 다음 링크의 뉴스 기사 내용과 정확히 일치하는지 다시 확인해줘. "
        f"불필요한 내용(광고, 기자 정보, 일반적인 서두/결론 문구 등) 없이 핵심 내용만 간결하게 요약해줘.\n\n"
        f"원본 링크: {link}\n"
        f"이전 요약: {first_response[:2000]}" # 이전 요약이 너무 길면 잘라서 전달
    )
    
    print(f"  - 2단계 AI 호출 (확인/재평가 요청)...")
    final_response = None
    for attempt in range(max_attempts):
        response_dict = call_potens_api_raw(confirmation_prompt, api_key=api_key)
        if "text" in response_dict:
            final_response = response_dict["text"]
            print(f"    -> 2단계 시도 {attempt + 1} 성공.")
            break
        else:
            error_msg = response_dict.get("error", "알 수 없는 오류")
            print(f"    -> 2단계 시도 {attempt + 1} 실패: {error_msg}. 재시도합니다...")
            if attempt < max_attempts - 1:
                time.sleep(delay_seconds)
            else:
                return f"2단계 AI 호출 최종 실패: {error_msg}"

    return final_response if final_response is not None else "최종 AI 응답을 받지 못했습니다."


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
    # 줄의 시작에 있는 숫자. 공백. 점. 공백을 제거
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
        cleaned_text = re.sub(pattern, '', cleaned_text, flags=re.IGNORECASE) # 대소문자 무시 플래그 추가

    # 여러 개의 줄바꿈을 하나의 공백으로 대체
    cleaned_text = re.sub(r'\n+', ' ', cleaned_text)
    # 여러 개의 공백을 하나로 대체 (줄바꿈 대체 후에도 중복 공백이 생길 수 있으므로)
    cleaned_text = re.sub(r'\s+', ' ', cleaned_text).strip()
    return cleaned_text

# -----------------------------------------------------------------------------

# --- Potens.dev AI API 키 설정 ---
load_dotenv() # .env 파일 로드
POTENS_API_KEY = os.getenv("POTENS_API_KEY")

# API 키가 설정되지 않았을 경우 경고 메시지 출력
if not POTENS_API_KEY:
    print("\n[경고] POTENS_API_KEY가 .env 파일에 설정되지 않았습니다.")
    print("Potens.dev AI API를 사용할 수 없습니다. 본문 내용은 'API 키 없음'으로 표시됩니다.\n")
    POTENS_API_KEY = None 

# 사용자로부터 검색할 뉴스 키워드 입력받기
keyword = input("검색할 뉴스 키워드를 입력하세요: ")

# 사용자로부터 검색 시작 날짜 입력받기
while True:
    start_date_str = input("검색 시작 날짜를 입력하세요 (예: 2025.06.01): ")
    try:
        start_date = datetime.strptime(start_date_str, "%Y.%m.%d")
        break
    except ValueError:
        print("날짜 형식이 올바르지 않습니다. %Y.%m.%d 형식으로 다시 입력해주세요.")

# 사용자로부터 검색 종료 날짜 입력받기
while True:
    end_date_str = input("검색 종료 날짜를 입력하세요 (예: 2025.06.30): ")
    try:
        end_date = datetime.strptime(end_date_str, "%Y.%m.%d")
        if end_date < start_date:
            print("종료 날짜는 시작 날짜보다 빠를 수 없습니다. 다시 입력해주세요.")
        else:
            break
    except ValueError:
        print("날짜 형식이 올바르지 않습니다. %Y.%m.%d 형식으로 다시 입력해주세요.")

# 몇 페이지까지 크롤링할 것인지 입력받기 (테스트를 위해 1페이지로 고정)
# max_pages_to_crawl = int(input("몇 페이지까지 크롤링할까요? (예: 1, 5, 10 등): ")) # 원래 코드
max_pages_to_crawl = 1 # 테스트를 위해 1페이지로 고정

all_collected_news = [] # 모든 페이지에서 수집한 기사를 저장할 리스트
article_processed_count = 0 # 처리된 기사 수를 세는 카운터

print(f"\n네이버 뉴스에서 '{keyword}' 키워드로 '{start_date_str}'부터 '{end_date_str}'까지 검색 중...")

# 페이지네이션 처리 루프
for page in range(max_pages_to_crawl):
    start_num = page * 10 + 1 # 각 페이지의 시작 번호 (1, 11, 21, ...)
    
    # 네이버 뉴스 검색 결과 페이지 URL (키워드, 날짜, 페이지 번호 포함)
    search_url = (
        f"https://search.naver.com/search.naver?where=news&query={keyword}"
        f"&sm=tab_opt&sort=0&photo=0&field=0&pd=3" # pd=3은 기간 직접 입력을 의미
        f"&ds={start_date.strftime('%Y.%m.%d')}" # 시작 날짜 포맷팅
        f"&de={end_date.strftime('%Y.%m.%d')}"   # 종료 날짜 포맷팅
        f"&start={start_num}" # 페이지네이션 파라미터 추가
    )

    print(f"\n--- {page + 1} 페이지 크롤링 중 (URL: {search_url}) ---")
    
    try:
        # 웹 페이지 요청 시 User-Agent 헤더 추가 (봇 감지 회피에 도움)
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36 Edg/138.0.0.0'}
        response = requests.get(search_url, headers=headers)
        response.raise_for_status() # HTTP 에러 발생 시 예외 발생
        soup = BeautifulSoup(response.text, "html.parser")

        # CSS 선택자: 'sds-comps-text-type-headline1' 사용 (기사 메인 제목에 특화)
        title_spans = soup.find_all("span", class_="sds-comps-text-type-headline1")

        if not title_spans:
            print(f"'{page + 1}' 페이지에서 기사를 찾을 수 없습니다. 더 이상 결과가 없거나 HTML 구조가 변경되었을 수 있습니다.")
            if page == 0: # 첫 페이지에서 아무것도 못 찾았을 때만 URL 출력
                print("현재 페이지 URL:", search_url)
            break # 더 이상 기사가 없으므로 반복 중단
        else:
            for title_span in title_spans:
                link_tag = title_span.find_parent('a') 
                
                if link_tag and 'href' in link_tag.attrs:
                    title = title_span.text.strip()
                    link = link_tag['href']
                    
                    if not (link.startswith('javascript:') or 'ad.naver.com' in link):
                        # --- Potens.dev AI API를 사용하여 뉴스 링크 직접 처리 ---
                        article_content = "API 키 없음 또는 본문 추출 실패" # 기본값 설정
                        if POTENS_API_KEY:
                            print(f"  - Potens.dev AI로 기사 내용 추출/요약 중 (2단계 확인 프롬프트 사용): {title[:30]}...")
                            # 2단계 확인 프롬프트 로직을 포함한 함수 호출
                            ai_final_response = call_potens_api_with_confirmation(link, POTENS_API_KEY, max_attempts=2) # 각 단계별 재시도 횟수
                            
                            if ai_final_response.startswith("1단계 AI 호출 최종 실패") or \
                               ai_final_response.startswith("2단계 AI 호출 최종 실패") or \
                               ai_final_response.startswith("1단계 AI 호출에서 유효한 응답을 받지 못했습니다.") or \
                               ai_final_response.startswith("최종 AI 응답을 받지 못했습니다."):
                                article_content = f"본문 추출 실패 (AI 오류): {ai_final_response}"
                                print(f"    -> AI 본문 추출 실패: {ai_final_response}") 
                            else:
                                article_content = clean_ai_response_text(ai_final_response)
                                print("    -> AI 본문 추출 성공")
                        else:
                            print("    -> Potens.dev AI API 키가 없어 본문 추출 건너뜀.")
                        
                        all_collected_news.append({"제목": title, "링크": link, "내용": article_content})
                        article_processed_count += 1
                        
                        # --- 테스트를 위한 강제 1분 대기 ---
                        print("\n--- Potens.dev AI 호출 후 1분(60초) 강제 대기 시작 ---")
                        time.sleep(60) # 1분(60초) 대기
                        print("--- 1분 대기 완료 ---")
                        
                        break # 첫 번째 기사 처리 후 루프 종료
            
            if article_processed_count > 0: # 첫 번째 기사를 처리했으면 페이지 루프도 종료
                break 
            elif page_news_count == 0 and page > 0:
                print(f"페이지 {page + 1}에서 필터링 후 표시할 기사가 없습니다. 반복을 중단합니다.")
                break

    except requests.exceptions.RequestException as e:
        print(f"웹 페이지 요청 중 오류 발생 (페이지 {page + 1}): {e}")
        break
    except Exception as e:
        print(f"스크립트 실행 중 오류 발생 (페이지 {page + 1}): {e}")
        break

print("\n----------------------------------------")
if all_collected_news:
    print(f"총 {len(all_collected_news)}개의 기사를 수집했습니다.")
    
    # CSV 파일로 저장
    file_name = f"{keyword}_{start_date.strftime('%Y%m%d')}_{end_date.strftime('%Y%m%d')}_news_test.csv" # 테스트용 파일명
    
    try:
        # 'utf-8-sig' 인코딩은 엑셀에서 한글 깨짐 방지를 위해 BOM을 포함합니다.
        with open(file_name, mode='w', newline='', encoding='utf-8-sig') as file:
            writer = csv.writer(file)
            # CSV 헤더 작성 (내용 필드 포함)
            writer.writerow(['제목', '링크', '내용'])
            
            # 각 기사 데이터 작성
            for news_item in all_collected_news:
                writer.writerow([news_item['제목'], news_item['링크'], news_item['내용']])
        print(f"\n수집된 기사가 '{file_name}' 파일로 성공적으로 저장되었습니다.")
        
    except Exception as e:
        print(f"\nCSV 파일 저장 중 오류 발생: {e}")

    # 터미널에 결과 출력
    print("\n수집된 기사 목록 (터미널 출력):")
    for news_item in all_collected_news:
        print(f"제목: {news_item['제목']}")
        print(f"링크: {news_item['링크']}")
        print(f"내용:\n{news_item['내용']}\n") # 내용 전체 출력
else:
    print("수집된 기사가 없습니다.")
