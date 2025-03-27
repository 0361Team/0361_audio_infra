import os
import json
import time
import tempfile
import logging
from pathlib import Path
import traceback
from typing import Dict, Any, Optional, Union
import asyncio
from faster_whisper import WhisperModel
from google.cloud import storage
from google.oauth2 import service_account

# 로깅 설정
logger = logging.getLogger("faster-whisper.processor")

# 환경 변수
TRANSCRIPT_BUCKET = os.environ.get('TRANSCRIPT_BUCKET')
MODEL_SIZE = os.environ.get('MODEL_SIZE', 'medium')
COMPUTE_TYPE = os.environ.get('COMPUTE_TYPE', 'float16')

# GCP 클라이언트 초기화
credentials = service_account.Credentials.from_service_account_file(Path().parent/Path('lecture2quiz-3c060176783f.json'))
storage_client = storage.Client(project='lecture2quiz', credentials=credentials)

# 모델 인스턴스
model = None

# 트랜스크립션 결과 저장을 위한 인메모리 저장소
transcription_results = {}



def load_model():
    """Faster Whisper 모델 로드 (지연 초기화)"""
    global model
    if model is None:
        device = "cuda" if os.environ.get("CUDA_VISIBLE_DEVICES") else "cpu"
        logger.info(f"Faster-Whisper 모델 로드 중 (장치: {device}, 모델 크기: {MODEL_SIZE})")
        compute_type = COMPUTE_TYPE
        # 모델 초기화
        model = WhisperModel(MODEL_SIZE, device=device, compute_type=compute_type)
        logger.info("Faster-Whisper 모델 로드 완료")
    return model


# 모델 미리 로드 (선택적)
try:
    load_model()
except Exception as e:
    logger.warning(f"모델 사전 로드 실패: {e}. 첫 요청 시 로드됩니다.")


async def download_audio(bucket_name: str, object_name: str) -> str:
    """Cloud Storage에서 오디오 파일 다운로드 (비동기)"""
    try:
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(object_name)

        # 임시 파일 생성
        _, temp_local_filename = tempfile.mkstemp(suffix=Path(object_name).suffix)

        # 비동기 방식으로 다운로드 (이벤트 루프 차단 방지)
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: blob.download_to_filename(temp_local_filename)
        )

        logger.info(f"오디오 파일 다운로드 완료: {object_name}")
        return temp_local_filename
    except Exception as e:
        logger.error(f"오디오 파일 다운로드 오류: {e}")
        raise


async def upload_transcript(
        transcript_data: Dict[str, Any],
        object_name: str,
        session_id: Optional[str] = None,
        request_id: Optional[str] = None
) -> str:
    """트랜스크립션 결과를 Cloud Storage에 업로드 (비동기)"""
    try:
        # 원본 파일명에서 확장자 제거 후 .json 추가
        base_name = Path(object_name).stem

        # 결과 파일명 구성
        if session_id:
            # 세션 ID가 있으면 폴더 구조에 포함
            transcript_name = f"{session_id}/{base_name}.json"
        else:
            transcript_name = f"{base_name}.json"

        # 요청 ID가 있으면 메타데이터에 추가
        metadata = {}
        if request_id:
            metadata["request_id"] = request_id

        # 결과 버킷에 업로드
        bucket = storage_client.bucket(TRANSCRIPT_BUCKET)
        blob = bucket.blob(transcript_name)

        # 메타데이터 설정
        if metadata:
            blob.metadata = metadata

        # JSON 문자열로 변환
        transcript_json = json.dumps(transcript_data, ensure_ascii=False, indent=2)

        # 비동기 방식으로 업로드
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: blob.upload_from_string(transcript_json, content_type="application/json")
        )

        logger.info(f"트랜스크립션 결과 업로드 완료: {TRANSCRIPT_BUCKET}/{transcript_name}")
        return transcript_name
    except Exception as e:
        logger.error(f"트랜스크립션 결과 업로드 오류: {e}")
        raise


async def process_audio(audio_file_path: str) -> Dict[str, Any]:
    """Faster-Whisper를 사용하여 오디오 파일 처리 (비동기 래퍼)"""
    try:
        logger.info(f"오디오 파일 처리 중: {audio_file_path}")

        # 모델 로드
        whisper_model = load_model()

        # 처리 로직을 스레드 풀에서 실행 (CPU/GPU 바운드 작업)
        loop = asyncio.get_event_loop()

        # Faster-Whisper는 segments와 info를 반환합니다.
        segments_generator, info = await loop.run_in_executor(
            None,
            lambda: whisper_model.transcribe(
                audio_file_path,
                language="ko",  # 한국어 처리 (자동 감지도 가능)
                beam_size=5,
                vad_filter=True,
                vad_parameters=dict(min_silence_duration_ms=500)
            )
        )

        # 세그먼트 처리
        segments_list = []
        full_text = ""

        # 세그먼트 목록을 생성하고 전체 텍스트 구성
        for segment in segments_generator:
            segment_dict = {
                "id": len(segments_list),
                "start": segment.start,
                "end": segment.end,
                "text": segment.text.strip(),
                # word-level 타임스탬프가 있는 경우
                "words": [
                    {"word": word.word, "start": word.start, "end": word.end, "probability": word.probability}
                    for word in (segment.words or [])
                ]
            }

            segments_list.append(segment_dict)
            full_text += segment.text + " "

        # WhisperX 포맷 유지를 위한 결과 구성
        result = {
            "segments": segments_list,
            "language": info.language,
            "text": full_text.strip(),
            "language_probability": info.language_probability
        }

        logger.info(f"트랜스크립션 완료! 감지된 언어: {info.language}")
        return result
    except Exception as e:
        logger.error(f"오디오 처리 오류: {e}")
        logger.error(traceback.format_exc())
        raise


async def process_audio_file(
        bucket_name: str,
        object_name: str,
        session_id: Optional[str] = None,
        request_id: Optional[str] = None
) -> Dict[str, Any]:
    """오디오 파일 처리 워크플로우 (백그라운드 태스크용)"""
    if not TRANSCRIPT_BUCKET:
        raise ValueError("환경 변수 TRANSCRIPT_BUCKET이 설정되지 않았습니다")

    start_time = time.time()
    local_file_path = None

    try:
        logger.info(f"처리 시작: {bucket_name}/{object_name} (요청 ID: {request_id})")

        # 오디오 파일 다운로드
        local_file_path = await download_audio(bucket_name, object_name)

        # 오디오 처리
        transcript_result = await process_audio(local_file_path)

        # 결과 업로드
        transcript_name = await upload_transcript(
            transcript_result,
            object_name,
            session_id,
            request_id
        )

        # 처리 시간 계산
        processing_time = time.time() - start_time

        # 결과 반환
        result = {
            "status": "success",
            "message": "오디오 처리 완료",
            "request_id": request_id,
            "transcript_location": f"gs://{TRANSCRIPT_BUCKET}/{transcript_name}",
            "processing_time_seconds": processing_time
        }

        logger.info(f"처리 완료: {object_name} ({processing_time:.2f}초)")
        return result

    except Exception as e:
        logger.error(f"오디오 파일 처리 오류: {e}")
        logger.error(traceback.format_exc())

        # 오류 정보 반환
        return {
            "status": "error",
            "message": "오디오 처리 중 오류 발생",
            "request_id": request_id,
            "error_details": str(e),
            "processing_time_seconds": time.time() - start_time
        }
    finally:
        # 임시 파일 정리
        if local_file_path and os.path.exists(local_file_path):
            os.remove(local_file_path)
            logger.info(f"임시 파일 제거: {local_file_path}")

async def process_uploaded_file(
        file_path: str,
        request_id: str,
        language: Optional[str] = None,
        beam_size: int = 5
) -> Dict[str, Any]:
    """사용자가 업로드한 오디오 파일 처리 함수"""
    start_time = time.time()

    try:
        logger.info(f"업로드된 오디오 처리 중: {file_path} (요청 ID: {request_id})")

        # 모델 로드
        whisper_model = load_model()

        # 처리 로직을 스레드 풀에서 실행
        loop = asyncio.get_event_loop()

        # Faster-Whisper 실행
        segments_generator, info = await loop.run_in_executor(
            None,
            lambda: whisper_model.transcribe(
                file_path,
                language=language if language else "ko",  # 기본 한국어 처리
                beam_size=beam_size,
                vad_filter=True,
                vad_parameters=dict(min_silence_duration_ms=500)
            )
        )

        # 세그먼트 처리
        segments_list = []
        full_text = ""

        # 세그먼트 목록을 생성하고 전체 텍스트 구성
        for segment in segments_generator:
            segment_dict = {
                "id": len(segments_list),
                "start": segment.start,
                "end": segment.end,
                "text": segment.text.strip(),
                "words": [
                    {"word": word.word, "start": word.start, "end": word.end,
                     "probability": word.probability}
                    for word in (segment.words or [])
                ]
            }

            segments_list.append(segment_dict)
            full_text += segment.text + " "

        # 결과 구성
        transcript_result = {
            "segments": segments_list,
            "language": info.language,
            "text": full_text.strip(),
            "language_probability": info.language_probability
        }

        # 결과 파일 이름 생성
        base_name = f"upload_{request_id}"
        result_file_name = f"{base_name}.json"

        # GCS가 설정된 경우 결과 업로드
        transcript_location = None
        if TRANSCRIPT_BUCKET:
            try:
                bucket = storage_client.bucket(TRANSCRIPT_BUCKET)
                blob = bucket.blob(result_file_name)

                # JSON 문자열로 변환
                transcript_json = json.dumps(transcript_result, ensure_ascii=False, indent=2)

                # 업로드
                blob.upload_from_string(transcript_json, content_type="application/json")
                transcript_location = f"gs://{TRANSCRIPT_BUCKET}/{result_file_name}"
                logger.info(f"트랜스크립션 결과 업로드 완료: {transcript_location}")
            except Exception as e:
                logger.error(f"트랜스크립션 결과 업로드 오류: {e}")
                # 업로드 실패 시에도 계속 진행

        # 처리 시간 계산
        processing_time = time.time() - start_time

        # 결과 저장
        result = {
            "status": "success",
            "message": "오디오 처리 완료",
            "request_id": request_id,
            "transcript_location": transcript_location,
            "processing_time_seconds": processing_time,
            "result": transcript_result
        }

        # 인메모리 저장소에 결과 저장 (실제 구현에서는 DB 사용 권장)
        transcription_results[request_id] = result

        logger.info(f"업로드된 오디오 처리 완료: ({processing_time:.2f}초)")
        return result

    except Exception as e:
        logger.error(f"업로드된 오디오 처리 오류: {e}")
        logger.error(traceback.format_exc())

        # 오류 정보 저장
        error_result = {
            "status": "error",
            "message": "오디오 처리 중 오류 발생",
            "request_id": request_id,
            "error_details": str(e),
            "processing_time_seconds": time.time() - start_time
        }

        # 인메모리 저장소에 오류 저장
        transcription_results[request_id] = error_result

        return error_result
    finally:
        # 임시 파일 정리
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"임시 파일 제거: {file_path}")
