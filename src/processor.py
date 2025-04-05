import os
import json
import time
import tempfile
import logging
import traceback
from pathlib import Path
import asyncio
from typing import Dict, Any, Optional
import numpy as np

# WhisperLive 모듈 임포트
from whisperlive.transcriber import WhisperLiveASR
from whisperlive.audio_processing import AudioProcessor

from google.cloud import storage
from google.oauth2 import service_account

# 로깅 설정
logger = logging.getLogger("whisperlive.processor")

# 환경 변수
TRANSCRIPT_BUCKET = os.environ.get('TRANSCRIPT_BUCKET')
MODEL_SIZE = os.environ.get('MODEL_SIZE', 'medium')
COMPUTE_TYPE = os.environ.get('COMPUTE_TYPE', 'float16')
LANGUAGE = os.environ.get('LANGUAGE', 'ko')

# GCP 클라이언트 초기화 (필요시)
try:
    if os.path.exists(os.path.join(Path(__file__).parent.parent, 'lecture2quiz-3c060176783f.json')):
        credentials = service_account.Credentials.from_service_account_file(
            os.path.join(Path(__file__).parent.parent, 'lecture2quiz-3c060176783f.json')
        )
        storage_client = storage.Client(project='lecture2quiz', credentials=credentials)
    else:
        storage_client = storage.Client()
except Exception as e:
    logger.warning(f"GCP 스토리지 클라이언트 초기화 실패: {e}. 로컬 저장소만 사용됩니다.")
    storage_client = None

# 모델 인스턴스
model = None
audio_processor = None

# 트랜스크립션 결과 저장을 위한 인메모리 저장소
transcription_results = {}


def load_model():
    """WhisperLive 모델 로드 (지연 초기화)"""
    global model, audio_processor
    if model is None:
        import torch
        device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info(f"WhisperLive 모델 로드 중 (장치: {device}, 모델 크기: {MODEL_SIZE})")

        # 모델 초기화
        model = WhisperLiveASR(
            model_name=MODEL_SIZE,
            device=device,
            compute_type=COMPUTE_TYPE,
            language=LANGUAGE
        )

        # 오디오 처리기 초기화
        audio_processor = AudioProcessor(sample_rate=16000)

        logger.info("WhisperLive 모델 로드 완료")
    return model, audio_processor


# 모델 미리 로드 (선택적)
try:
    load_model()
except Exception as e:
    logger.warning(f"모델 사전 로드 실패: {e}. 첫 요청 시 로드됩니다.")


async def download_audio(bucket_name: str, object_name: str) -> str:
    """Cloud Storage에서 오디오 파일 다운로드 (비동기)"""
    try:
        if not storage_client:
            raise ValueError("스토리지 클라이언트가 초기화되지 않았습니다")

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
        if not storage_client or not TRANSCRIPT_BUCKET:
            # 로컬 저장
            output_dir = "transcripts"
            os.makedirs(output_dir, exist_ok=True)

            base_name = Path(object_name).stem
            if session_id:
                output_file = os.path.join(output_dir, f"{session_id}_{base_name}.json")
            else:
                output_file = os.path.join(output_dir, f"{base_name}.json")

            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(transcript_data, f, ensure_ascii=False, indent=2)

            logger.info(f"트랜스크립션 결과 로컬 저장 완료: {output_file}")
            return output_file

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
    """WhisperLive를 사용하여 오디오 파일 처리 (비동기 래퍼)"""
    try:
        logger.info(f"오디오 파일 처리 중: {audio_file_path}")

        # 모델 로드
        whisper_model, audio_proc = load_model()

        # 오디오 파일을 numpy 배열로 변환
        audio_data = await asyncio.to_thread(
            audio_proc.load_audio_file, audio_file_path
        )

        # WhisperLive는 스트리밍 처리를 위해 설계되었지만, 비스트리밍 방식으로도 사용 가능
        # (이 경우 전체 오디오를 처리)
        whisper_model.reset_state()  # 상태 초기화

        # 처리 로직을 스레드 풀에서 실행 (CPU/GPU 바운드 작업)
        loop = asyncio.get_event_loop()

        # 오디오 처리
        result = await loop.run_in_executor(
            None,
            lambda: whisper_model.inference(audio_data, is_final=True)
        )

        # 세그먼트 리스트 작성
        segments_list = []
        for i, segment in enumerate(result.get("segments", [])):
            segment_dict = {
                "id": i,
                "start": segment.get("start", 0),
                "end": segment.get("end", 0),
                "text": segment.get("text", "").strip(),
            }
            segments_list.append(segment_dict)

        # 결과 구성
        transcript_result = {
            "segments": segments_list,
            "language": LANGUAGE,
            "text": result.get("text", ""),
        }

        logger.info(f"트랜스크립션 완료!")
        return transcript_result
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
            "transcript_location": f"gs://{TRANSCRIPT_BUCKET}/{transcript_name}" if TRANSCRIPT_BUCKET else transcript_name,
            "processing_time_seconds": processing_time,
            "result": transcript_result
        }

        # 결과 저장
        transcription_results[request_id] = result

        logger.info(f"처리 완료: {object_name} ({processing_time:.2f}초)")
        return result

    except Exception as e:
        logger.error(f"오디오 파일 처리 오류: {e}")
        logger.error(traceback.format_exc())

        # 오류 정보 반환
        error_result = {
            "status": "error",
            "message": "오디오 처리 중 오류 발생",
            "request_id": request_id,
            "error_details": str(e),
            "processing_time_seconds": time.time() - start_time
        }

        # 오류 정보 저장
        transcription_results[request_id] = error_result

        return error_result
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

        # 오디오 처리
        transcript_result = await process_audio(file_path)

        # 결과 파일 이름 생성
        base_name = f"upload_{request_id}"
        result_file_name = f"{base_name}.json"

        # GCS가 설정된 경우 결과 업로드
        transcript_location = None
        if storage_client and TRANSCRIPT_BUCKET:
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
        else:
            # 로컬 저장
            output_dir = "transcripts"
            os.makedirs(output_dir, exist_ok=True)
            output_file = os.path.join(output_dir, result_file_name)

            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(transcript_result, f, ensure_ascii=False, indent=2)

            transcript_location = output_file
            logger.info(f"트랜스크립션 결과 로컬 저장 완료: {output_file}")

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

        # 인메모리 저장소에 결과 저장
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