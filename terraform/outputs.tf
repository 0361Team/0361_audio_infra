output "audio_bucket_name" {
  description = "오디오 파일 저장용 버킷 이름"
  value       = google_storage_bucket.audio_bucket.name
}

output "transcript_bucket_name" {
  description = "트랜스크립션 결과 저장
}