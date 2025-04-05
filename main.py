import os
import logging
import asyncio
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import time

from src.api import router as api_router
from src.websocket import WebSocketManager

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("whisperlive")

# FastAPI 애플리케이션 생성
app = FastAPI(
    title="WhisperLive API",
    description="실시간 강의 오디오 스트리밍 트랜스크립션 서비스 API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS 미들웨어 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 프로덕션에서는 특정 원본만 허용하도록 수정
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API 라우터 등록
app.include_router(api_router)

# WebSocket 관리자 인스턴스 생성
websocket_manager = WebSocketManager()


# 미들웨어 - 요청 처리 시간 측정
@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    return response


# 글로벌 예외 핸들러
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"status": "error", "message": "내부 서버 오류가 발생했습니다"}
    )


# 루트 엔드포인트
@app.get("/")
async def root():
    return {"message": "WhisperLive 오디오 스트리밍 트랜스크립션 API에 오신 것을 환영합니다", "version": "1.0.0"}


# WebSocket 엔드포인트
@app.websocket("/api/v1/stream")
async def websocket_endpoint(websocket: WebSocket):
    """실시간 오디오 스트리밍을 위한 WebSocket 엔드포인트"""
    session_id = None
    try:
        # WebSocket 연결 수락
        await websocket.accept()

        # 세션 ID 생성 및 클라이언트 등록
        session_id = await websocket_manager.register(websocket)
        logger.info(f"WebSocket 클라이언트 연결됨: {session_id}")

        # 클라이언트에게 세션 ID 전송
        await websocket.send_json({"event": "connected", "session_id": session_id})

        # 오디오 스트림 처리 루프
        while True:
            # 클라이언트로부터 오디오 데이터 수신
            data = await websocket.receive_bytes()

            if not data:
                await asyncio.sleep(0.01)
                continue

            # 오디오 데이터 처리 및 결과 반환
            await websocket_manager.process_audio(session_id, data)

    except WebSocketDisconnect:
        logger.info(f"WebSocket 클라이언트 연결 해제: {session_id}")
    except Exception as e:
        logger.error(f"WebSocket 처리 중 오류 발생: {e}", exc_info=True)
    finally:
        # 연결 종료 시 정리
        if session_id:
            await websocket_manager.unregister(session_id)


# FastAPI를 직접 실행하는 경우
if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)