# src/whisperx/processor.py
import os
import json
import time
import tempfile
import logging
from pathlib import Path
import traceback
from typing import Dict, Any, Optional, Union
import asyncio
import whisperx
import torch
from google.cloud import storage

# 로깅 설정
logger = logging.getLogger("whisperx.processor")

# 환경 변수
TRANSCRIPT_BUCKET = os.environ.get('TRANSCRIPT_BUCKET')

# GCP 클라이언트 초기화
storage_client = storage.Client()


# 모델 초기화 (애플리케이션 시작 시 한 번만 로드)
def load_model():
    """WhisperX 모델 로드 (지연 초기화)"""
    global model
    if "model" not in globals():
        device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info(f"WhisperX 모델 로드 중 (장치: {device})")
        compute_type = "float16" if device == "cuda" else "float32"
        # 한국어 처리를 위한 모델 초기화
        model = whisperx.load_model("medium", device, compute_type=compute_type, language="ko")
        logger.info("WhisperX 모델 로드 완료")
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
    """WhisperX를 사용하여 오디오 파일 처리 (비동기 래퍼)"""
    try:
        logger.info(f"오디오 파일 처리 중: {audio_file_path}")

        # 모델 로드 (필요한 경우)
        model = load_model()

        # 처리 로직을 스레드 풀에서 실행 (CPU/GPU 바운드 작업)
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: model.transcribe(audio_file_path, batch_size=16)
        )

        # 발화자 인식 및 문장 분리 (선택 사항)
        logger.info("화자 분리 실행 중...")
        try:
            diarize_model = whisperx.DiarizationPipeline(use_auth_token=None, device=model.device)

            # 화자 분리 작업을 스레드 풀에서 실행
            diarize_segments = await loop.run_in_executor(
                None,
                lambda: diarize_model(audio_file_path)
            )

            # 화자 할당 작업을 스레드 풀에서 실행
            result = await loop.run_in_executor(
                None,
                lambda: whisperx.assign_word_speakers(diarize_segments, result)
            )
        except Exception as diarize_err:
            logger.warning(f"화자 분리 생략 (오류 발생): {diarize_err}")

        # 결과 반환
        logger.info("트랜스크립션 완료!")
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