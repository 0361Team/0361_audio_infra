terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 4.0"
    }
  }
}

provider "google" {
  project     = var.project_id
  region      = "asia-northeast3"
  zone        = "asia-northeast3-a"
  credentials = file("lecture2quiz-672159eb71a8.json")  # 서비스 계정 키 파일 경로
}



# 방화벽 규칙 생성
resource "google_compute_firewall" "spring_app_firewall" {
  name    = "spring-app-firewall"
  network = "default"

  allow {
    protocol = "tcp"
    ports    = ["22", "8080"]
  }

  source_ranges = ["0.0.0.0/0"]
}

# Compute Engine 인스턴스 생성
resource "google_compute_instance" "spring_app_instance" {
  name         = "spring-app-instance"
  machine_type = "e2-micro"  # 프리티어 지원 인스턴스 타입

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-11"
      size  = 10  # 프리티어는 30GB까지 무료
    }
  }

  network_interface {
    network = "default"
    access_config {
      # 외부 IP 할당
    }
  }

  metadata_startup_script = <<-EOT
    #!/bin/bash
    apt-get update
    apt-get install -y openjdk-17-jdk
  EOT

  # 프리티어 요구사항을 충족하기 위한 태그
  tags = ["spring-app"]
}

# 출력 정의
output "instance_ip" {
  description = "인스턴스의 외부 IP 주소"
  value       = google_compute_instance.spring_app_instance.network_interface.0.access_config.0.nat_ip
}