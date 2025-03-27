from enum import Enum
from typing import Dict, List, Optional, Any, Union
from pydantic import BaseModel, Field


class StatusEnum(str, Enum):
    SUCCESS = "success"
    ERROR = "error"
    PENDING = "pending"
    PROCESSING = "processing"
    SKIPPED = "skipped"


class PubSubMessage(BaseModel):
    """Pub/Sub 메시지 형식"""
    data: str = Field(..., description="Base64로 인코딩된 메시지 데이터")
    attributes: Optional[Dict[str, str]] = Field(None, description="메시지 속성")
    message_id: Optional[str] = Field(None, description="Pub/Sub 메시지 ID")
    publish_time: Optional[str] = Field(None, description="메시지 발행 시간")


class PubSubEnvelope(BaseModel):
    """Pub/Sub 푸시 구독에서 받는 전체 봉투"""
    message: PubSubMessage = Field(..., description="Pub/Sub 메시지")
    subscription: str = Field(..., description="구독 이름")


class AudioProcessingRequest(BaseModel):
    """오디오 처리 요청 모델"""
    bucket: str = Field(..., description="오디오 파일이 저장된 버킷 이름")
    name: str = Field(..., description="오디오 파일 객체 이름")
    session_id: Optional[str] = Field(None, description="세션 ID (여러 파일이 하나의 강의에 속하는 경우)")


class TranscriptionSegment(BaseModel):
    """트랜스크립션 세그먼트 모델"""
    id: int = Field(..., description="세그먼트 ID")
    start: float = Field(..., description="시작 시간 (초)")
    end: float = Field(..., description="종료 시간 (초)")
    text: str = Field(..., description="트랜스크립션 텍스트")
    speaker: Optional[str] = Field(None, description="화자 ID (있는 경우)")


class TranscriptionResult(BaseModel):
    """트랜스크립션 결과 모델"""
    segments: List[TranscriptionSegment] = Field(..., description="트랜스크립션 세그먼트 목록")
    language: str = Field(..., description="감지된 언어")
    text: str = Field(..., description="전체 트랜스크립션 텍스트")


class AudioProcessingResponse(BaseModel):
    """오디오 처리 응답 모델"""
    status: StatusEnum = Field(..., description="처리 상태")
    message: str = Field(..., description="상태 메시지")
    request_id: Optional[str] = Field(None, description="요청 고유 ID")
    transcript_location: Optional[str] = Field(None, description="트랜스크립션 파일 위치")
    processing_time_seconds: Optional[float] = Field(None, description="처리 시간(초)")
    error_details: Optional[str] = Field(None, description="오류 발생 시 상세 내용")


class HealthResponse(BaseModel):
    """서비스 헬스 체크 응답"""
    status: str = Field("healthy", description="서비스 상태")
    version: str = Field(..., description="API 버전")
    environment: Optional[str] = Field(None, description="실행 환경 (dev, prod 등)")