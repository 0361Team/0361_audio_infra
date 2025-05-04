#!/usr/bin/env python3
# Google Generative AI를 활용한 임베딩 서비스
# 필요한 라이브러리 설치:
# pip install google-generativeai

import os
from typing import List, Dict, Any
from google import genai
from google.genai.types import EmbedContentConfig


class EmbeddingService:
    def __init__(self):
        """
        임베딩 서비스 초기화
        """
        # 환경 변수 설정
        os.environ["GOOGLE_CLOUD_PROJECT"] = "lecture2quiz"
        os.environ["GOOGLE_CLOUD_LOCATION"] = "us-central1"
        os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"

        # GenAI 클라이언트 초기화
        self.client = genai.Client()

        # 기본 모델 및 차원 설정
        self.model_name = "text-multilingual-embedding-002"
        self.default_dimensions = 768

    def create_embeddings(self, texts: List[str], task_type: str = "RETRIEVAL_DOCUMENT") -> List[List[float]]:
        """
        텍스트 리스트를 임베딩 벡터로 변환합니다.

        Args:
            texts: 임베딩할 텍스트 리스트
            task_type: 임베딩 태스크 유형
                       (RETRIEVAL_DOCUMENT, RETRIEVAL_QUERY, SEMANTIC_SIMILARITY, CLASSIFICATION, CLUSTERING)

        Returns:
            임베딩 벡터 리스트
        """
        try:
            # 임베딩 요청
            response = self.client.models.embed_content(
                model=self.model_name,
                contents=texts,
                config=EmbedContentConfig(
                    task_type=task_type,
                    output_dimensionality=self.default_dimensions,
                ),
            )

            # 응답에서 임베딩 벡터 추출
            embeddings = [embedding.values for embedding in response.embeddings]
            return embeddings

        except Exception as e:
            print(f"임베딩 생성 중 오류 발생: {e}")
            raise

    def embed_document(self, document: str, chunk_size: int = 1000, overlap: int = 200) -> Dict[str, Any]:
        """
        긴 문서를 청크로 나누고 각 청크에 대한 임베딩을 생성합니다.

        Args:
            document: 임베딩할 문서
            chunk_size: 각 청크의 최대 문자 수
            overlap: 인접 청크 간의 겹치는 문자 수

        Returns:
            청크 텍스트와 해당 임베딩을 포함하는 사전
        """
        # 문서를 청크로 분할
        chunks = []
        for i in range(0, len(document), chunk_size - overlap):
            chunk = document[i:i + chunk_size]
            if len(chunk) > 200:  # 너무 짧은 청크는 건너뜀
                chunks.append(chunk)

        # 각 청크에 대한 임베딩 생성
        chunk_embeddings = self.create_embeddings(chunks)

        return {
            "chunks": chunks,
            "embeddings": chunk_embeddings
        }

    def embed_for_keyword_extraction(self, document: str) -> Dict[str, Any]:
        """
        키워드 추출을 위한 문서 임베딩을 생성합니다.

        Args:
            document: 임베딩할 문서

        Returns:
            문장 텍스트와 해당 임베딩을 포함하는 사전
        """
        # 문서를 문장으로 분할
        sentences = [s.strip() for s in document.split('.') if len(s.strip()) > 0]

        # 각 문장에 대한 임베딩 생성 (CLUSTERING 태스크 유형 사용)
        sentence_embeddings = self.create_embeddings(sentences, task_type="CLUSTERING")

        return {
            "sentences": sentences,
            "embeddings": sentence_embeddings
        }


# 테스트 코드
if __name__ == "__main__":
    # 임베딩 서비스 초기화
    embedding_service = EmbeddingService()

    # 테스트 텍스트
    test_texts = [
        "WhisperLive는 실시간 음성-텍스트 변환 기술입니다.",
        "임베딩은 텍스트를 벡터로 변환하는 과정입니다.",
        "RAG 시스템은 대규모 언어 모델의 출력을 최적화합니다."
    ]

    # 임베딩 생성 테스트
    try:
        print("텍스트 임베딩 테스트 중...")
        embeddings = embedding_service.create_embeddings(test_texts)

        # 결과 출력
        print(f"성공: {len(embeddings)}개 텍스트에 대한 임베딩 생성")
        print(f"첫 번째 임베딩 차원: {len(embeddings[0])}")
        print(f"임베딩 샘플 (처음 5개 값): {embeddings[0][:5]}")

    except Exception as e:
        print(f"오류 발생: {e}")