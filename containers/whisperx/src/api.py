import json
import uuid
import base64
import logging
from typing import Dict, Any
from fastapi import APIRouter, BackgroundTasks, HTTPException, Depends, Header

from ..models.models import (
    PubSubEnvelope,
    AudioProcessingRequest,
    AudioProcessingResponse,
    HealthResponse,
    StatusEnum
)
from .processor import process_audio_file

# 로깅 설정
logger = logging.getLogger("whisperx.api")

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