# Google Cloud 공급자 설정
provider "google" {
  project = var.project_id
  region  = var.region
}

# Storage 버킷 - 오디오 파일 저장용
resource "google_storage_bucket" "audio_bucket" {
  name          = "${var.project_id}-audio-files"
  location      = var.region
  force_destroy = true  # 개발 환경에서만 사용하세요

  uniform_bucket_level_access = true
}

# Storage 버킷 - 트랜스크립션 결과 저장용
resource "google_storage_bucket" "transcript_bucket" {
  name          = "${var.project_id}-transcripts"
  location      = var.region
  force_destroy = true  # 개발 환경에서만 사용하세요

  uniform_bucket_level_access = true
}

# Pub/Sub 토픽 - 오디오 처리 요청
resource "google_pubsub_topic" "audio_process_topic" {
  name = "audio-process-requests"
}

# Pub/Sub 푸시 구독 - Cloud Run으로 연결
resource "google_pubsub_subscription" "audio_process_push_subscription" {
  name  = "audio-process-push-sub"
  topic = google_pubsub_topic.audio_process_topic.name

  push_config {
    push_endpoint = google_cloud_run_service.whisperx_service.status[0].url

    attributes = {
      x-goog-version = "v1"
    }

    # OIDC 토큰을 사용한 인증
    oidc_token {
      service_account_email = google_service_account.whisperx_service_account.email
    }
  }

  # 확인 마감 시간 (600초 = 10분)
  ack_deadline_seconds = 600

  # 메시지 보관 기간 (7일)
  message_retention_duration = "604800s"

  # 재시도 정책
  retry_policy {
    minimum_backoff = "10s"
    maximum_backoff = "600s"
  }

  # 만료되지 않는 구독
  expiration_policy {
    ttl = ""
  }
}

# Cloud Storage 알림 - 오디오 파일 업로드 시 Pub/Sub에 알림
resource "google_storage_notification" "audio_upload_notification" {
  bucket         = google_storage_bucket.audio_bucket.name
  payload_format = "JSON_API_V1"
  topic          = google_pubsub_topic.audio_process_topic.id
  event_types    = ["OBJECT_FINALIZE"]

  depends_on = [google_pubsub_topic_iam_binding.storage_pubsub_binding]
}

# Pub/Sub 토픽에 대한 Storage 서비스 계정 권한 부여
resource "google_pubsub_topic_iam_binding" "storage_pubsub_binding" {
  topic   = google_pubsub_topic.audio_process_topic.id
  role    = "roles/pubsub.publisher"
  members = ["serviceAccount:${data.google_storage_project_service_account.gcs_account.email_address}"]
}

# Cloud Storage 서비스 계정 정보 가져오기
data "google_storage_project_service_account" "gcs_account" {
}

# WhisperX 서비스용 서비스 계정
resource "google_service_account" "whisperx_service_account" {
  account_id   = "whisperx-processor"
  display_name = "WhisperX Processor Service Account"
  description  = "Service account for WhisperX audio processing"
}

# WhisperX 서비스 계정에 권한 부여
resource "google_project_iam_member" "storage_object_admin" {
  project = var.project_id
  role    = "roles/storage.objectAdmin"
  member  = "serviceAccount:${google_service_account.whisperx_service_account.email}"
}

resource "google_project_iam_member" "pubsub_subscriber" {
  project = var.project_id
  role    = "roles/pubsub.subscriber"
  member  = "serviceAccount:${google_service_account.whisperx_service_account.email}"
}

# Cloud Run 서비스 IAM
resource "google_cloud_run_service_iam_member" "whisperx_service_invoker" {
  location = google_cloud_run_service.whisperx_service.location
  service  = google_cloud_run_service.whisperx_service.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.whisperx_service_account.email}"
}

# WhisperX Cloud Run 서비스
resource "google_cloud_run_service" "whisperx_service" {
  name     = "whisperx-processor"
  location = var.region

  template {
    spec {
      containers {
        image = var.whisperx_image

        # 리소스 요청 및 제한
        resources {
          limits = {
            cpu    = "2000m"  # 2 vCPU
            memory = "4Gi"    # 4GB 메모리
          }
        }

        # 환경 변수
        env {
          name  = "TRANSCRIPT_BUCKET"
          value = google_storage_bucket.transcript_bucket.name
        }
      }

      # 서비스 계정 지정
      service_account_name = google_service_account.whisperx_service_account.email

      # 타임아웃 설정 (15분)
      timeout_seconds = 900
    }
  }

  # 트래픽 설정
  traffic {
    percent         = 100
    latest_revision = true
  }
}

# 공개 접근을 위한 IAM 정책 (Pub/Sub 푸시용)
resource "google_cloud_run_service_iam_member" "public_access" {
  location = google_cloud_run_service.whisperx_service.location
  service  = google_cloud_run_service.whisperx_service.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.whisperx_service_account.email}"
}