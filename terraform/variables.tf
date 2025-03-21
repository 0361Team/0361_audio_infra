variable "project_id" {
  description = "GCP 프로젝트 ID"
  type        = string
}

variable "region" {
  description = "GCP 리전"
  type        = string
  default     = "asia-northeast3"  # 서울 리전
}

variable "whisperx_image" {
  description = "WhisperX 처리 컨테이너 이미지"
  type        = string
}