import base64
import json
import requests
from google.oauth2 import service_account
import google.auth.transport.requests
from pathlib import Path

from whisper.constants import DATA_PATH, PROJECT_ROOT_PATH


def transcribe_audio(audio_file_path:Path, language_code='ko-KR'):
    """
    Google Cloud Speech-to-Text API를 사용하여 오디오 파일을 텍스트로 변환합니다.

    Args:
        audio_file_path (Path): 변환할 오디오 파일 경로
        language_code (str): 인식할 언어 코드 (기본값: 한국어)

    Returns:
        str: 변환된 텍스트
    """
    # 1. 서비스 계정 키 파일에서 인증 정보 로드 (JSON 키 파일 필요)
    credentials = service_account.Credentials.from_service_account_file(
        PROJECT_ROOT_PATH/'lecture2quiz-3c060176783f.json',
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )

    # 2. 액세스 토큰 얻기
    auth_req = google.auth.transport.requests.Request()
    credentials.refresh(auth_req)
    access_token = credentials.token

    # 3. 오디오 파일 읽기 및 base64 인코딩
    with open(audio_file_path, 'rb') as audio_file:
        audio_content = base64.b64encode(audio_file.read()).decode('utf-8')

    # 4. API 요청 데이터 구성
    request_data = {
        "config": {
            "languageCode": language_code,
            "enableAutomaticPunctuation": True,
            "model": "default"  # 또는 "phone_call", "video", "command_and_search" 등
        },
        "audio": {
            "content": audio_content
        }
    }

    # 5. API 엔드포인트 URL (동기식 인식 사용)
    url = "https://speech.googleapis.com/v1/speech:recognize"

    # 6. HTTP 요청 헤더
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    # 7. API 요청 보내기
    response = requests.post(url, headers=headers, data=json.dumps(request_data))

    # 8. 결과 처리
    if response.status_code == 200:
        results = response.json().get('results', [])
        transcripts = []
        for result in results:
            alternatives = result.get('alternatives', [])
            if alternatives:
                transcripts.append(alternatives[0].get('transcript', ''))
        return ' '.join(transcripts)
    else:
        print(f"에러 발생: {response.status_code}")
        print(response.text)
        return None


# 사용 예시
if __name__ == "__main__":
    result = transcribe_audio(DATA_PATH/'audio.m4a')
    print("인식 결과:", result)


# 긴 오디오 파일(1분 이상)을 처리하기 위한 비동기식 인식 함수
def transcribe_long_audio(audio_file_path, language_code='ko-KR'):
    """
    Google Cloud Speech-to-Text API를 사용하여 긴 오디오 파일을 비동기적으로 텍스트로 변환합니다.

    Args:
        audio_file_path (str): 변환할 오디오 파일 경로
        language_code (str): 인식할 언어 코드 (기본값: 한국어)

    Returns:
        str: 작업 ID (operation name)
    """
    # 1. 서비스 계정 키 파일에서 인증 정보 로드
    credentials = service_account.Credentials.from_service_account_file(
        'your-service-account-key.json',
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )

    # 2. 액세스 토큰 얻기
    auth_req = google.auth.transport.requests.Request()
    credentials.refresh(auth_req)
    access_token = credentials.token

    # 3. 오디오 파일 읽기 및 base64 인코딩
    with open(audio_file_path, 'rb') as audio_file:
        audio_content = base64.b64encode(audio_file.read()).decode('utf-8')

    # 4. API 요청 데이터 구성
    request_data = {
        "config": {
            "languageCode": language_code,
            "enableAutomaticPunctuation": True,
            "model": "default"
        },
        "audio": {
            "content": audio_content
        }
    }

    # 5. API 엔드포인트 URL (비동기식 인식 사용)
    url = "https://speech.googleapis.com/v1/speech:longrunningrecognize"

    # 6. HTTP 요청 헤더
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    # 7. API 요청 보내기
    response = requests.post(url, headers=headers, data=json.dumps(request_data))

    # 8. 결과 처리
    if response.status_code == 200:
        operation_name = response.json().get('name')
        print(f"비동기 작업 시작됨: {operation_name}")
        return operation_name
    else:
        print(f"에러 발생: {response.status_code}")
        print(response.text)
        return None


# 비동기 작업 상태 확인 함수
def check_operation_status(operation_name):
    """
    비동기 음성 인식 작업의 상태를 확인합니다.

    Args:
        operation_name (str): 작업 ID

    Returns:
        dict: 작업 상태 정보 또는 결과
    """
    # 1. 서비스 계정 키 파일에서 인증 정보 로드
    credentials = service_account.Credentials.from_service_account_file(
        'your-service-account-key.json',
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )

    # 2. 액세스 토큰 얻기
    auth_req = google.auth.transport.requests.Request()
    credentials.refresh(auth_req)
    access_token = credentials.token

    # 3. API 엔드포인트 URL
    url = f"https://speech.googleapis.com/v1/operations/{operation_name}"

    # 4. HTTP 요청 헤더
    headers = {
        "Authorization": f"Bearer {access_token}"
    }

    # 5. API 요청 보내기
    response = requests.get(url, headers=headers)

    # 6. 결과 처리
    if response.status_code == 200:
        result = response.json()
        if "done" in result and result["done"]:
            if "response" in result:
                # 완료된 결과 출력
                transcripts = []
                for result_item in result["response"].get("results", []):
                    alternatives = result_item.get("alternatives", [])
                    if alternatives:
                        transcripts.append(alternatives[0].get("transcript", ""))
                return {"status": "complete", "transcript": " ".join(transcripts)}
            else:
                return {"status": "complete", "transcript": ""}
        else:
            return {"status": "in_progress"}
    else:
        print(f"에러 발생: {response.status_code}")
        print(response.text)
        return {"status": "error", "details": response.text}