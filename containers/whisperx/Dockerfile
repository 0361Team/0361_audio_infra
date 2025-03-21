# PyTorch와 CUDA가 이미 설치된 NVIDIA 공식 이미지 사용
FROM pytorch/pytorch:2.0.0-cuda11.8-cudnn8-runtime

# 필요한 시스템 패키지 설치
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libsndfile1 \
    git \
    && rm -rf /var/lib/apt/lists/*

# 작업 디렉토리 설정
WORKDIR /app

# 필요한 Python 패키지 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 소스 코드 복사
COPY src/ ./src/

# 포트 설정
ENV PORT=8080
ENV TRANSCRIPT_BUCKET=""
ENV ENVIRONMENT="production"

# FastAPI 서비스 실행
CMD exec uvicorn src.whisperx.app:app --host 0.0.0.0 --port ${PORT} --workers 1