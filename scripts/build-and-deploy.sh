#!/bin/bash
# build-and-deploy.sh - WhisperX 컨테이너 빌드 및 배포 스크립트

set -e  # 오류 발생 시 스크립트 중단

# 환경 변수 설정
PROJECT_ID=$(gcloud config get-value project)
REGION="asia-northeast3"  # 서울 리전
IMAGE_NAME="whisperx-processor"
IMAGE_TAG="latest"

echo "===== WhisperX 프로세서 빌드 및 배포 ====="
echo "프로젝트 ID: $PROJECT_ID"
echo "리전: $REGION"

# 필요한 API 활성화
echo "필요한 API 활성화 중..."
gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  pubsub.googleapis.com \
  storage.googleapis.com

# Artifact Registry 저장소 생성 (아직 없는 경우)
echo "Artifact Registry 저장소 설정 중..."
gcloud artifacts repositories create whisper-repo \
  --repository-format=docker \
  --location=$REGION \
  --description="WhisperX 컨테이너 이미지 저장소" \
  --quiet || true

# Docker 이미지 빌드
echo "Docker 이미지 빌드 중..."
docker build -t "$REGION-docker.pkg.dev/$PROJECT_ID/whisperx-repo/$IMAGE_NAME:$IMAGE_TAG" .

# Docker 이미지 푸시
echo "Docker 이미지 푸시 중..."
docker push "$REGION-docker.pkg.dev/$PROJECT_ID/whisperx-repo/$IMAGE_NAME:$IMAGE_TAG"

# terraform.tfvars 파일 생성
echo "Terraform 변수 파일 생성 중..."
cat > terraform.tfvars << EOF
project_id = "$PROJECT_ID"
region = "$REGION"
whisperx_image = "$REGION-docker.pkg.dev/$PROJECT_ID/whisperx-repo/$IMAGE_NAME:$IMAGE_TAG"
EOF

# Terraform 초기화 및 적용
echo "Terraform 초기화 중..."
terraform init

echo "Terraform 적용 중..."
terraform apply -auto-approve

echo "===== 배포 완료 ====="
echo "WhisperX 프로세서가 성공적으로 배포되었습니다."
echo "테스트를 위해 다음 명령어로 오디오 파일을 업로드하세요:"
echo "gsutil cp [오디오파일] gs://$(terraform output -raw audio_bucket_name)/"