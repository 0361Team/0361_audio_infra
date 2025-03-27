# cloud_services.py
import os
import json
from typing import Optional, Dict, Any
from google.cloud import storage
from google.oauth2 import service_account


class CloudStorageService:
    """GCP 스토리지 서비스 추상화 래퍼"""

    def __init__(self, use_cloud: Optional[bool] = None):
        self.use_cloud = use_cloud if use_cloud is not None else \
            os.environ.get('USE_GCP_STORAGE', '').lower() == 'true'
        self.client = self._initialize_client() if self.use_cloud else None

    def _initialize_client(self):
        """환경에 따른 스토리지 클라이언트 초기화"""
        try:
            # 1. 서비스 계정 키 파일 경로
            if os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
                return storage.Client()

            # 2. 환경 변수에 직접 저장된 JSON 문자열
            if os.environ.get("GOOGLE_CREDENTIALS"):
                credentials_info = json.loads(os.environ.get("GOOGLE_CREDENTIALS"))
                credentials = service_account.Credentials.from_service_account_info(credentials_info)
                return storage.Client(credentials=credentials)

            # 3. 기본 인증 시도
            return storage.Client()
        except Exception as e:
            raise RuntimeError(f"스토리지 클라이언트 초기화 오류: {e}")

    async def download_file(self, bucket_name: str, object_name: str, destination_path: str) -> str:
        """클라우드 또는 로컬 스토리지에서 파일 다운로드"""
        if not self.use_cloud:
            # 로컬 모드: 로컬 파일 시스템에서 처리
            return self._handle_local_download(object_name, destination_path)

        # 클라우드 모드: 실제 GCS에서 다운로드
        bucket = self.client.bucket(bucket_name)
        blob = bucket.blob(object_name)
        blob.download_to_filename(destination_path)
        return destination_path

    def _handle_local_download(self, object_name: str, destination_path: str) -> str:
        """로컬 환경에서의 파일 다운로드 모방"""
        # 로컬 테스트 디렉토리에서 파일 찾기 등의 로직 구현
        local_test_dir = os.environ.get("LOCAL_TEST_FILES_DIR", "./test_files")
        source_path = os.path.join(local_test_dir, object_name)

        # 파일이 존재하는지 확인
        if not os.path.exists(source_path):
            raise FileNotFoundError(f"로컬 테스트 파일을 찾을 수 없음: {source_path}")

        # 필요하면 파일 복사
        import shutil
        os.makedirs(os.path.dirname(destination_path), exist_ok=True)
        shutil.copy2(source_path, destination_path)

        return destination_path

    # 기타 필요한 메소드 (업로드, 리스팅 등) 구현...