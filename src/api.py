import json
import uuid
import base64
import logging
import tempfile
from typing import Dict, Any, Optional
from fastapi import APIRouter, BackgroundTasks, HTTPException, Depends, Header, File, UploadFile, Form
from fastapi.responses import JSONResponse
from pathlib import Path

from src.models import (
    PubSubEnvelope,
    AudioProcessingRequest,
    AudioProcessingResponse,
    HealthResponse,
    StatusEnum
)
from .processor import process_audio_file, process_uploaded_file
from .websocket import WebSocketManager

# 로깅 설정
logger = logging.getLogger("whisperlive.api")

# API 버전
API_VERSION = "v1"

# API 라우터 생성
router = APIRouter(prefix=f"/api/{API_VERSION}")


# 의존성 주입을 위한 함수
async def verify_pubsub_token(x_goog_subscription: str = Header(None)):
    """Pub/Sub 토큰 검증 (필요한 경우)"""
    if x_goog_subscription is None:
        raise HTTPException(status_code=401, detail="Pub/Sub 구독 헤더가 필요합니다")
    return x_goog_subscription


@router.post("/transcribe", response_model=AudioProcessingResponse, status_code=202)
async def transcribe_audio(
        envelope: PubSubEnvelope,
        background_tasks: BackgroundTasks,
        _: str = Depends(verify_pubsub_token)
):
    """
    Pub/Sub 메시지를 수신하여 오디오 파일을 트랜스크립션합니다.

    - 비동기 처리: 요청을 수락하고 백그라운드 태스크로 처리합니다.
    - 응답: 즉시 202 Accepted 상태와 함께 요청 ID를 반환합니다.
    """
    try:
        # 메시지 데이터 디코딩
        message_data = base64.b64decode(envelope.message.data).decode("utf-8")
        data = json.loads(message_data)

        # 요청 ID 생성
        request_id = str(uuid.uuid4())

        # 오디오 처리 요청 객체 생성
        request = AudioProcessingRequest(
            bucket=data.get("bucket"),
            name=data.get("name"),
            session_id=data.get("session_id")
        )

        # 요청 검증
        if not request.bucket or not request.name:
            return AudioProcessingResponse(
                status=StatusEnum.ERROR,
                message="버킷 또는 파일명이 제공되지 않았습니다",
                request_id=request_id
            )

        # 오디오 파일 확장자 검증
        supported_formats = ['.mp3', '.wav', '.m4a', '.flac', '.ogg', '.aac']
        if not any(request.name.lower().endswith(fmt) for fmt in supported_formats):
            return AudioProcessingResponse(
                status=StatusEnum.SKIPPED,
                message=f"지원되지 않는 파일 형식: {request.name}",
                request_id=request_id
            )

        # 백그라운드 태스크로 처리 시작
        logger.info(f"오디오 처리 시작: {request.name}, 요청 ID: {request_id}")
        background_tasks.add_task(
            process_audio_file,
            request.bucket,
            request.name,
            request.session_id,
            request_id
        )

        # 즉시 응답 반환
        return AudioProcessingResponse(
            status=StatusEnum.PENDING,
            message="오디오 처리가 시작되었습니다",
            request_id=request_id
        )

    except json.JSONDecodeError:
        logger.error("잘못된 JSON 형식의 메시지")
        return AudioProcessingResponse(
            status=StatusEnum.ERROR,
            message="잘못된 메시지 형식",
            request_id=str(uuid.uuid4())
        )
    except Exception as e:
        logger.error(f"오디오 처리 요청 중 오류 발생: {e}")
        return AudioProcessingResponse(
            status=StatusEnum.ERROR,
            message="서버 내부 오류",
            request_id=str(uuid.uuid4()),
            error_details=str(e)
        )


@router.post("/upload-transcribe", response_model=AudioProcessingResponse)
async def upload_and_transcribe(
        background_tasks: BackgroundTasks,
        file: UploadFile = File(...),
        language: Optional[str] = Form(None),
        beam_size: int = Form(5)
):
    """
    오디오 파일을 직접 업로드하여 트랜스크립션 수행

    - 파일 업로드: 오디오 파일 (.mp3, .wav, .flac, .ogg 등)
    - 비동기 처리: 요청을 수락하고 백그라운드 태스크로 처리합니다.
    - 응답: 즉시 202 Accepted 상태와 함께 요청 ID를 반환합니다.
    """
    try:
        # 요청 ID 생성
        request_id = str(uuid.uuid4())

        # 오디오 파일 확장자 확인
        supported_formats = ['.mp3', '.wav', '.m4a', '.flac', '.ogg', '.aac']
        file_extension = Path(file.filename).suffix.lower()

        if not any(file_extension.endswith(fmt) for fmt in supported_formats):
            return AudioProcessingResponse(
                status=StatusEnum.SKIPPED,
                message=f"지원되지 않는 파일 형식: {file.filename}",
                request_id=request_id
            )

        # 임시 파일 생성
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=file_extension)
        temp_file_path = temp_file.name
        temp_file.close()

        # 업로드된 파일 저장
        content = await file.read()
        with open(temp_file_path, "wb") as f:
            f.write(content)

        # 백그라운드 태스크로 처리 시작
        logger.info(f"오디오 처리 시작: {file.filename}, 요청 ID: {request_id}")
        background_tasks.add_task(
            process_uploaded_file,
            temp_file_path,
            request_id,
            language,
            beam_size
        )

        # 즉시 응답 반환
        return AudioProcessingResponse(
            status=StatusEnum.PENDING,
            message="오디오 처리가 시작되었습니다",
            request_id=request_id
        )

    except Exception as e:
        logger.error(f"파일 업로드 처리 중 오류 발생: {e}")
        return AudioProcessingResponse(
            status=StatusEnum.ERROR,
            message="서버 내부 오류",
            request_id=str(uuid.uuid4()),
            error_details=str(e)
        )


@router.get("/transcription-result/{request_id}")
async def get_transcription_result(request_id: str):
    """
    트랜스크립션 결과 조회 및 반환

    - request_id: 트랜스크립션 작업 ID
    - 응답: STT 결과를 직접 JSON으로 반환
    """
    # processor.py의 인메모리 저장소에서 결과 조회
    from .processor import transcription_results

    if request_id not in transcription_results:
        raise HTTPException(
            status_code=404,
            detail=f"요청된 ID의 트랜스크립션 결과를 찾을 수 없습니다: {request_id}"
        )

    # 결과 가져오기
    result = transcription_results[request_id]

    # 에러가 있는 경우 처리
    if result.get("status") == "error":
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": result.get("message", "처리 중 오류 발생"),
                "request_id": request_id,
                "error_details": result.get("error_details")
            }
        )

    # 처리가 완료되지 않은 경우
    if result.get("status") != "success":
        return JSONResponse(
            status_code=200,
            content={
                "status": result.get("status", "unknown"),
                "message": result.get("message", "처리 중"),
                "request_id": request_id
            }
        )

    # 성공적으로 처리된 경우 STT 결과만 직접 반환
    if "result" in result and result["result"]:
        # 트랜스크립션 결과만 직접 반환
        return JSONResponse(
            status_code=200,
            content=result["result"]
        )

    # 결과는 있지만 STT 데이터가 없는 경우 (예외 상황)
    return JSONResponse(
        status_code=200,
        content={
            "status": "success",
            "message": "처리 완료되었으나 트랜스크립션 데이터를 찾을 수 없습니다",
            "request_id": request_id,
            "transcript_location": result.get("transcript_location")
        }
    )


@router.get("/session/{session_id}")
async def get_session_result(session_id: str):
    """
    WebSocket 세션의 트랜스크립션 결과 조회

    - session_id: WebSocket 세션 ID
    - 응답: 세션에서 생성된 모든 트랜스크립션 결과
    """
    # 로컬 파일에서 세션 결과 읽기
    try:
        output_dir = "transcripts"
        output_file = Path(output_dir) / f"{session_id}.json"

        if not output_file.exists():
            raise HTTPException(
                status_code=404,
                detail=f"세션 ID의 트랜스크립션 결과를 찾을 수 없습니다: {session_id}"
            )

        with open(output_file, "r", encoding="utf-8") as f:
            result = json.load(f)

        return JSONResponse(
            status_code=200,
            content=result
        )
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logger.error(f"세션 결과 조회 중 오류 발생: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"세션 결과 처리 중 오류가 발생했습니다: {str(e)}"
        )


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """
    서비스 헬스 체크 엔드포인트

    - 서비스 상태를 확인하는 간단한 엔드포인트
    - 모니터링 및 로드 밸런서 헬스 체크에 사용
    """
    import os

    return HealthResponse(
        status="healthy",
        version=API_VERSION,
        environment=os.environ.get("ENVIRONMENT", "development")
    )