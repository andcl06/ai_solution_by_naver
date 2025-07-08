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

def retry_ai_call(prompt: str, api_key: str, response_schema=None, max_retries: int = 2, delay_seconds: int = 15) -> dict:
    """
    Potens.dev API 호출에 대한 재시도 로직을 포함한 래퍼 함수.
    call_potens_api_raw를 호출하고 실패 시 재시도합니다.
    """
    for attempt in range(max_retries):
        response_dict = call_potens_api_raw(prompt, api_key=api_key, response_schema=response_schema)

        if "error" not in response_dict:
            return response_dict
        else:
            error_msg = response_dict.get("error", "알 수 없는 오류")
            if attempt < max_retries - 1:
                time.sleep(delay_seconds)
            else:
                return {"error": f"AI 호출 최종 실패: {error_msg}"}
    return {"error": "AI 응답을 가져오는 데 최종 실패했습니다. 나중에 다시 시도해주세요."}


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

    response_dict = retry_ai_call(initial_prompt, api_key=api_key, max_retries=max_attempts, delay_seconds=delay_seconds)
    if "text" in response_dict:
        return response_dict["text"]
    else:
        return response_dict.get("error", "알 수 없는 오류")


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

    response_dict = retry_ai_call(prompt, api_key=api_key, response_schema=response_schema, max_retries=max_attempts, delay_seconds=delay_seconds)
    if "text" in response_dict and isinstance(response_dict["text"], list):
        return response_dict["text"]
    else:
        return [] # 오류 발생 시 빈 리스트 반환

def summarize_long_combined_text(combined_text: str, api_key: str, 
                                 max_length_for_direct_call: int = 1500, # 직접 호출 최대 길이 (조정 가능)
                                 chunk_size: int = 500, # 청크 크기 (조정 가능)
                                 delay_between_chunks: int = 10, # 청크 요약 간 지연 (조정 가능)
                                 max_attempts: int = 2) -> str:
    """
    긴 텍스트를 받아, AI가 처리하기 쉬운 길이로 중간 요약합니다.
    텍스트가 max_length_for_direct_call보다 길면 청크로 나누어 요약하고 합칩니다.
    """
    if not combined_text:
        return ""

    if len(combined_text) <= max_length_for_direct_call:
        # 길이가 충분히 짧으면 직접 요약 요청
        prompt = f"다음 텍스트를 간결하게 요약해 주세요.\n\n텍스트: {combined_text}"
        response_dict = retry_ai_call(prompt, api_key=api_key, max_retries=max_attempts, delay_seconds=delay_between_chunks)
        if "text" in response_dict:
            return clean_ai_response_text(response_dict["text"])
        else:
            return f"긴 텍스트 직접 요약 실패: {response_dict.get('error', '알 수 없는 오류')}"

    # 텍스트가 너무 길면 청크로 나누어 요약
    chunks = [combined_text[i:i + chunk_size] for i in range(0, len(combined_text), chunk_size)]
    
    summarized_chunks = []
    for i, chunk in enumerate(chunks):
        prompt = f"다음 텍스트를 간결하게 요약해 주세요.\n\n텍스트: {chunk}"
        response_dict = retry_ai_call(prompt, api_key=api_key, max_retries=max_attempts, delay_seconds=delay_between_chunks)
        
        if "text" in response_dict:
            summarized_chunks.append(clean_ai_response_text(response_dict["text"]))
        else:
            # 청크 요약 실패 시 해당 청크는 빈 문자열로 처리하거나 오류 메시지를 포함
            summarized_chunks.append(f"[청크 {i+1} 요약 실패: {response_dict.get('error', '알 수 없는 오류')}]")
        
        if i < len(chunks) - 1: # 마지막 청크가 아니면 잠시 대기
            time.sleep(delay_between_chunks)
            
    return " ".join(summarized_chunks)


def get_overall_trend_summary(summarized_articles: list[dict], api_key: str, max_attempts: int = 2, delay_seconds: int = 15) -> str:
    """
    AI가 요약된 기사들을 바탕으로 전반적인 뉴스 트렌드를 요약합니다.
    이때, 입력 텍스트가 길 경우 중간 요약 과정을 거칩니다.
    """
    if not summarized_articles:
        return "요약된 기사가 없어 뉴스 트렌드를 요약할 수 없습니다."

    # 요약된 기사 내용을 하나의 긴 텍스트로 결합
    combined_summaries = "\n\n---\n\n".join([
        f"제목: {art['제목']}\n날짜: {art['날짜']}\n요약: {art['내용']}"
        for art in summarized_articles
    ])

    # 결합된 요약문이 길 경우, 중간 요약 과정을 거침
    processed_content_for_ai = summarize_long_combined_text(
        combined_summaries, 
        api_key,
        max_length_for_direct_call=1500, # 트렌드 요약에 사용할 최대 길이
        chunk_size=500, # 중간 요약 청크 크기
        delay_between_chunks=10 # 중간 요약 청크 간 지연
    )
    
    if "요약 실패" in processed_content_for_ai or not processed_content_for_ai:
        return f"뉴스 트렌드 요약을 위한 사전 처리 실패: {processed_content_for_ai}"


    prompt = (
        f"다음은 최근 뉴스 기사 요약문들을 종합한 내용입니다.\n"
        f"이 내용을 바탕으로 전반적인 뉴스 트렌드를 간결하게 요약해 주세요.\n\n"
        f"종합된 뉴스 요약 내용:\n{processed_content_for_ai}"
    )

    response_dict = retry_ai_call(prompt, api_key=api_key, max_retries=max_attempts, delay_seconds=delay_seconds)
    if "text" in response_dict:
        return response_dict["text"]
    else:
        return response_dict.get("error", "알 수 없는 오류")


def get_insurance_implications_from_ai(trend_summary_text: str, api_key: str, max_attempts: int = 2, delay_seconds: int = 15) -> str:
    """
    AI가 요약된 트렌드 요약문을 바탕으로 자동차 보험 산업에 미칠 영향을 요약합니다.
    """
    if not trend_summary_text:
        return "트렌드 요약문이 없어 자동차 보험 산업 관련 정보를 도출할 수 없습니다."

    # 프롬프트 변경: 트렌드 요약문을 바탕으로 자동차 보험 산업에 미칠 영향 추론
    prompt = (
        f"다음은 최근 뉴스 트렌드를 요약한 내용입니다.\n"
        f"이 트렌드 요약문을 바탕으로 '자동차 보험 산업'에 미칠 수 있는 영향에 대해 간결하게 요약해 주세요.\n" # <-- 추론 요청
        f"한국어로 요약 내용을 제공해 주세요.\n\n"
        f"뉴스 트렌드 요약문:\n{trend_summary_text}"
    )

    response_dict = retry_ai_call(prompt, api_key=api_key, max_retries=max_attempts, delay_seconds=delay_seconds)
    if "text" in response_dict:
        return response_dict["text"]
    else:
        return response_dict.get("error", "알 수 없는 오류")

def get_prettified_report(raw_report_text: str, api_key: str, max_attempts: int = 2, delay_seconds: int = 15) -> str:
    """
    Potens.dev AI를 호출하여 원본 보고서 텍스트를 바탕으로
    더욱 보기 좋고 전문적인 형식의 보고서를 생성합니다.
    """
    if not raw_report_text:
        return "포맷팅할 보고서 내용이 없습니다."

    prompt = (
        f"다음은 뉴스 트렌드 분석 및 보험 상품 개발 인사이트에 대한 보고서 초안입니다.\n"
        f"이 초안의 내용을 유지하면서, 다음 지침에 따라 더욱 전문적이고 가독성 높은 보고서로 재구성해 주세요.\n\n"
        f"[지침]\n"
        f"- 보고서의 각 섹션(뉴스 트렌드 요약, 자동차 보험 산업 관련 주요 사실 및 법적 책임, 부록)을 명확하게 구분하고, 적절한 제목과 부제목을 사용해 주세요.\n"
        f"- 문단 간의 간격을 적절히 조절하여 가독성을 높여 주세요.\n"
        f"- 핵심 내용은 강조(예: 볼드체)하거나 목록 형태로 정리하여 시각적으로 돋보이게 해주세요.\n"
        f"- '키워드 산출 근거'와 '반영된 기사 리스트'는 표(테이블) 형태로 깔끔하게 정리해 주세요.\n"
        f"- 보고서의 전체적인 흐름이 자연스럽고 논리적으로 연결되도록 해주세요.\n"
        f"- 불필요한 반복이나 비문은 수정하고, 전문적인 보고서 톤앤매너를 유지해 주세요.\n"
        f"- 모든 내용은 한국어로 작성해 주세요.\n\n"
        f"[보고서 초안]\n"
        f"{raw_report_text}"
    )

    response_dict = retry_ai_call(prompt, api_key=api_key, max_retries=max_attempts, delay_seconds=delay_seconds)
    if "text" in response_dict:
        return clean_ai_response_text(response_dict["text"]) # AI 응답도 한 번 더 클리닝
    else:
        return response_dict.get("error", "AI를 통한 보고서 포맷팅 실패.")


def clean_ai_response_text(text: str) -> str:
    """
    AI 응답 텍스트에서 불필요한 마크다운 기호, 여러 줄바꿈,
    그리고 AI가 자주 사용하는 서두 문구들을 제거하여 평탄화합니다.
    특히, 텍스트 크기를 키울 수 있는 마크다운 헤더 기호를 적극적으로 제거합니다.
    """
    # 마크다운 코드 블록 제거 (예: ```json ... ```)
    cleaned_text = re.sub(r'```(?:json|text)?\s*([\s\S]*?)\s*```', r'\1', text, flags=re.IGNORECASE)

    # 마크다운 헤더, 리스트 기호, 볼드체/이탤릭체 기호 등 제거
    # 이 부분이 텍스트 크기를 키우는 주요 원인이므로, 적극적으로 제거합니다.
    # 단, 볼드체는 유지하는 것이 좋을 수 있으므로, #, -, + 만 제거하도록 조정
    cleaned_text = re.sub(r'#+\s*|[-+]\s*', '', cleaned_text) # #으로 시작하는 헤더, - 또는 +로 시작하는 리스트 기호 제거
    cleaned_text = re.sub(r'\*\*(.*?)\*\*', r'\1', cleaned_text) # **볼드체** 제거 (텍스트만 남김)
    cleaned_text = re.sub(r'__(.*?)__', r'\1', cleaned_text) # __볼드체__ 제거 (텍스트만 남김)
    cleaned_text = re.sub(r'\*(.*?)\*', r'\1', cleaned_text) # *이탤릭체* 제거 (텍스트만 남김)
    cleaned_text = re.sub(r'_(.*?)_', r'\1', cleaned_text) # _이탤릭체_ 제거 (텍스트만 남김)


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

