# test_potens_api.py

import os
from dotenv import load_dotenv
from modules import ai_service # ai_service 모듈 임포트

def test_potens_api_call():
    """
    Potens.dev API 호출을 테스트하는 함수입니다.
    .env 파일에서 API 키를 로드하여 사용합니다.
    """
    # .env 파일 로드
    # verbose=True를 추가하여 로드 과정에 대한 자세한 정보를 출력합니다.
    # override=True를 추가하여 이미 설정된 환경 변수도 .env 파일의 값으로 덮어씁니다.
    dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
    load_success = load_dotenv(dotenv_path=dotenv_path, verbose=True, override=True)

    print(f"'.env' 파일 로드 성공 여부: {load_success}")
    if not load_success:
        print(f"경고: '.env' 파일을 로드하지 못했습니다. 파일 경로를 확인해주세요: {dotenv_path}")
        print("python-dotenv 라이브러리가 설치되어 있는지 확인해주세요 (pip install python-dotenv).")


    POTENS_API_KEY = os.getenv("POTENS_API_KEY")

    if not POTENS_API_KEY:
        print("오류: 'POTENS_API_KEY' 환경 변수가 설정되지 않았습니다.")
        print("'.env' 파일에 'POTENS_API_KEY=\"YOUR_API_KEY\"' 형식으로 올바르게 설정되어 있는지 확인해주세요.")
        return

    # 테스트를 위한 프롬프트
    test_prompt = "안녕하세요! 당신은 누구인가요? 50자 이내로 답변해주세요."

    print(f"\nPotens.dev API 호출 테스트 시작...")
    print(f"사용할 API 키 (일부): {POTENS_API_KEY[:5]}*****{POTENS_API_KEY[-5:]}") # 보안을 위해 일부만 출력
    print(f"프롬프트: '{test_prompt}'")

    # ai_service 모듈의 retry_ai_call 함수 호출
    response = ai_service.retry_ai_call(test_prompt, POTENS_API_KEY, max_retries=1, delay_seconds=5)

    if "text" in response:
        print("\n--- API 호출 성공 ---")
        print("응답 내용:")
        print(response["text"])
        if "raw_response" in response:
            print("\n--- 원본 응답 (디버깅용) ---")
            print(response["raw_response"])
    else:
        print("\n--- API 호출 실패 ---")
        print("오류:", response.get("error", "알 수 없는 오류"))
        if "raw_response" in response:
            print("\n--- 원본 응답 (디버깅용) ---")
            print(response["raw_response"])

if __name__ == "__main__":
    test_potens_api_call()
