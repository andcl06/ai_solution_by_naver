# modules/ai_service.py

import requests
import json
import re
import time
import streamlit as st # Streamlit의 st.error, st.warning 등을 사용하기 위해 임시로 import.
                        # 실제 프로덕션에서는 이 로깅 부분을 다른 방식으로 처리하는 것이 좋습니다.

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

def get_article_summary(title: str, link: str, date_str: str, summary_snippet: str, api_key: str, max_attempts: int = 2, delay_seconds: int = 15) -> str:
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

    for attempt in range(max_attempts):
        response_dict = call_potens_api_raw(initial_prompt, api_key=api_key)
        if "text" in response_dict:
            return response_dict["text"]
        else:
            error_msg = response_dict.get("error", "알 수 없는 오류")
            if attempt < max_attempts - 1:
                time.sleep(delay_seconds)
            else:
                return f"Potens.dev AI 호출 최종 실패: {error_msg}"

    return "Potens.dev AI 호출에서 유효한 응답을 받지 못했습니다."

def get_relevant_keywords(trending_keywords_data: list[dict], perspective: str, api_key: str, max_attempts: int = 2, delay_seconds: int = 15) -> list[str]:
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

    for attempt in range(max_attempts):
        response_dict = call_potens_api_raw(prompt, api_key, response_schema=response_schema)
        if "text" in response_dict and isinstance(response_dict["text"], list):
            return response_dict["text"]
        else:
            error_msg = response_dict.get("error", "알 수 없는 오류")
            if attempt < max_attempts - 1:
                time.sleep(delay_seconds)
            else:
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
