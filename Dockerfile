FROM nvidia/cuda:12.3.2-cudnn9-runtime-ubuntu22.04

# 필요한 시스템 패키지 설치
RUN apt-get update -y && \
    apt-get install -y python3-pip python3-dev git ffmpeg libsndfile1 && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# 작업 디렉터리 설정
WORKDIR /app

# 필요한 Python 패키지 설치
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# WhisperLive 설치 (Github에서 직접 설치)
RUN pip3 install git+https://github.com/collabora/WhisperLive.git

# 소스 코드 복사
COPY ./ /app/whisperlive
WORKDIR /app/whisperlive

# 환경 변수 설정
ENV MODEL_SIZE="medium"
ENV COMPUTE_TYPE="float16"
ENV LANGUAGE="ko"
ENV PORT=8080
ENV TRANSCRIPT_BUCKET=""
ENV ENVIRONMENT="production"

# transcripts 디렉토리 생성
RUN mkdir -p /app/whisperlive/transcripts && \
    chmod 777 /app/whisperlive/transcripts

# 포트 노출
EXPOSE ${PORT}

# 서버 실행
CMD ["sh", "-c", "python3 -m uvicorn main:app --host 0.0.0.0 --port ${PORT} --workers 1"]