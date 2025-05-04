from sklearn.feature_extraction.text import TfidfVectorizer
import numpy as np
import re
import string


def normalize_korean(text):
    """
    한국어 텍스트 정규화 (조사 제거 및 표준화)

    Args:
        text (str): 정규화할 텍스트

    Returns:
        str: 정규화된 텍스트
    """
    # 조사 패턴 정의
    josa_patterns = [
        r'(이|가|은|는|을|를|의|에|에서|로|으로|와|과|이랑|랑|하고)$',
        r'(으로부터|으로서|으로써|이라고|라고)$'
    ]

    # 문장 단위로 분리
    sentences = re.split(r'(?<=[.!?])\s+', text)
    normalized_sentences = []

    for sentence in sentences:
        # 단어 단위로 분리
        words = sentence.split()
        normalized_words = []

        for word in words:
            # 단어에서 조사 제거
            for pattern in josa_patterns:
                word = re.sub(pattern, '', word)
            normalized_words.append(word)

        normalized_sentences.append(' '.join(normalized_words))

    return ' '.join(normalized_sentences)


def extract_keywords(text, top_n=10, domain=None):
    """
    한국어 최적화 키워드 추출 알고리즘

    Args:
        text (str): 키워드를 추출할 텍스트
        top_n (int): 추출할 상위 키워드 개수
        domain (str): 도메인 정보 ('ml', 'ai', 'computer_vision' 등)

    Returns:
        list: 상위 N개 키워드 목록
    """
    # 문장 단위로 분리
    sentences = re.split(r'(?<=[.!?])\s+', text)
    sentences = [s.strip() for s in sentences if s.strip()]

    if not sentences:
        return []

    # 한국어 정규화 적용
    normalized_sentences = [normalize_korean(s) for s in sentences]

    # 도메인별 중요 용어 (가중치를 부여할 용어)
    domain_terms = {
        'ml': ['모델', '학습', '알고리즘', '파라미터', '데이터셋', '예측', '분류', '회귀',
               '정확도', '오차', '손실함수', '경사하강법', '과적합', '테스트', '훈련'],
        'computer_vision': ['컨볼루션', '필터', '특징', '검출', '이미지', '객체', '인식',
                            '패딩', '스트라이드', '채널', '풀링', '레이어', '분할', '영상처리'],
        'nlp': ['텍스트', '토큰', '임베딩', '단어', '문장', '코퍼스', '문서', '언어모델',
                '인코더', '디코더', '어텐션', '생성', '요약', '번역']
    }

    # 도메인 용어 합치기 (기본 ML 용어 + 지정 도메인)
    important_terms = set(domain_terms.get('ml', []))
    if domain and domain in domain_terms:
        important_terms.update(domain_terms[domain])

    # 확장된 불용어 리스트
    extended_stopwords = [
        # 일반 불용어
        '이', '그', '저', '것', '이것', '저것', '그것', '을', '를', '에', '의', '에서', '으로',
        '와', '과', '이다', '있다', '하다', '이런', '그런', '저런', '어떤', '무슨', '어느',

        # 강의에서 자주 나오는 일반 단어
        '여기', '우리', '얘기', '그냥', '부분', '이제', '말씀', '지금', '생각', '조금', '사람',
        '경우', '처음', '그다음', '하나', '가지', '이해', '계속', '마지막', '통해', '때문',
        '점점', '만약', '보시', '대한', '정보', '아마', '사실', '아시', '제일', '바로', '여러분',
        '부터', '시간', '다음', '예시', '자리', '정도', '마찬가지', '가면', '한번', '이유',
        '직접', '진짜', '수업', '보고', '질문', '학생', '지금', '대해', '여기서', '그래서',
        '그런데', '그리고', '그래도', '그렇게', '나중에', '요즘', '뭐가', '뭐냐', '어디',
        '언제', '이것', '저것', '그것', '왜냐하면', '그래서', '그러면', '그럼', '이런',
        '이거', '저거', '어떻게', '오늘', '내일', '어제', '다른',

        # 깨진 형태소들
        '제이', '스트', '레이', '라이', '베이', '액티', '오브', '인풋',

        # 대명사, 지시어, 강조어
        '나', '너', '우리', '저희', '당신', '그들', '제가', '제', '저희가', '저희는', '우리가', '우리는',
        '이것', '그것', '저것', '이거', '그거', '저거', '요것', '이런', '그런', '저런',
        '매우', '정말', '굉장히', '아주', '제일', '가장', '너무', '참', '되게',

        # 동사, 형용사(흔한 것들)
        '하다', '되다', '있다', '없다', '보다', '오다', '가다', '주다', '받다', '만들다', '쓰다',
        '좋다', '나쁘다', '크다', '작다', '많다', '적다', '높다', '낮다',

        # 조사와 함께 쓰이는 형태
        '하는', '된', '있는', '본', '할', '된다', '한다', '있다', '봤', '간', '준', '받은', '만든', '쓴',

        # 한국어 문법적 요소
        '때', '데', '거', '것', '수', '줄', '리', '듯', '든', '면',

        # 숫자와 단위
        '하나', '둘', '셋', '넷', '다섯', '여섯', '일곱', '여덟', '아홉', '열',
        '개', '명', '번', '차', '회', '편', '권', '장', '쪽', '초', '분', '시간', '일', '주', '달', '년',

        # 부사(흔한 것들)
        '또', '다시', '계속', '자주', '항상', '보통', '아마', '혹시', '아직', '이미', '벌써',
        '잘', '못', '많이', '조금', '약간', '거의', '완전히', '전혀', '꽤', '더', '덜',

        # 접속사
        '그리고', '또한', '그러나', '하지만', '그런데', '그래서', '따라서', '그러므로', '그래도',

        # 강의에서 자주 쓰이는 표현
        '말씀드린', '설명드린', '말씀드릴', '설명드릴', '보시면', '보시다시피', '아시다시피',
        '생각해보면', '이해하기', '이해하면', '배웠던', '배울', '했던', '할', '했습니다', '합니다'
    ]

    # TF-IDF 벡터라이저 설정
    tfidf_vectorizer = TfidfVectorizer(
        ngram_range=(1, 3),  # 1~3 단어 조합
        min_df=2,  # 최소 2개 문서에서 등장해야 함
        max_df=0.85,  # 85% 이상 문서에 등장하는 단어는 제외
        sublinear_tf=True,  # 빈도수 로그 스케일 적용
        stop_words=extended_stopwords  # 확장된 불용어 목록 적용
    )

    # TF-IDF 행렬 생성
    tfidf_matrix = tfidf_vectorizer.fit_transform(normalized_sentences)

    # 중요 단어에 가중치 부여를 위한 단어 목록
    feature_names = tfidf_vectorizer.get_feature_names_out()

    # 기본 TF-IDF 점수
    word_importance = np.sum(tfidf_matrix.toarray(), axis=0)

    # 중요 용어에 가중치 부여
    for i, word in enumerate(feature_names):
        # 단어가 중요 용어 목록에 있으면 가중치 부여
        if any(term in word for term in important_terms):
            word_importance[i] *= 2.5  # 가중치 2.5배 부여

    # 중요도 기준 정렬
    sorted_indices = np.argsort(word_importance)[::-1]

    # 필터링된 키워드 추출
    filtered_keywords = []
    seen_roots = set()  # 중복 개념 방지를 위한 집합

    for idx in sorted_indices:
        word = feature_names[idx]

        # 필터링 기준
        # 1. 2글자 이상 (한글자 단어 제외)
        # 2. 숫자만 있는 단어 제외
        # 3. 특정 용어들로 시작하거나 끝나는 단어 제외
        # 4. 중복 개념 제외
        if (len(word) > 1 and
                not word.isdigit() and
                not any(word.startswith(sw) for sw in ['그', '이', '저', '아', '어']) and
                not any(word.endswith(sw) for sw in ['요', '죠', '니다', '세요', '네요', '거든요', '잖아요'])):

            # 중복 개념 검사 (기본형 추출)
            word_root = word
            for term in important_terms:
                if term in word:
                    word_root = term
                    break

            # 이미 추출된 개념이 아니면 추가
            if word_root not in seen_roots:
                seen_roots.add(word_root)
                filtered_keywords.append(word)

                if len(filtered_keywords) >= top_n:
                    break

    return filtered_keywords


def extract_keyword_with_context(text, top_n=10, domain=None):
    """
    키워드 추출 및 각 키워드별 컨텍스트 포함

    Args:
        text (str): 키워드를 추출할 텍스트
        top_n (int): 추출할 상위 키워드 개수
        domain (str): 도메인 정보

    Returns:
        dict: 키워드 및 관련 컨텍스트
    """
    # 키워드 추출
    keywords = extract_keywords(text, top_n=top_n, domain=domain)

    # 문장 분리
    sentences = re.split(r'(?<=[.!?])\s+', text)
    sentences = [s.strip() for s in sentences if s.strip()]

    # 키워드별 컨텍스트 수집
    context = {}

    for keyword in keywords:
        # 키워드의 기본형 찾기 (조사 등 제거)
        keyword_root = keyword
        for term in ['을', '를', '이', '가', '은', '는', '의', '에', '로', '와', '과', '이라는']:
            if keyword.endswith(term):
                keyword_root = keyword[:-len(term)]
                break

        # 해당 키워드가 포함된 문장 찾기
        related_sentences = []

        for i, sentence in enumerate(sentences):
            # 키워드 또는 기본형이 문장에 포함되어 있는지 확인
            if keyword in sentence or keyword_root in sentence:
                # 현재 문장 포함
                context_snippet = sentence

                # 가능하면 이전 문장도 포함
                if i > 0:
                    context_snippet = sentences[i - 1] + " " + context_snippet

                # 가능하면 다음 문장도 포함
                if i < len(sentences) - 1:
                    context_snippet = context_snippet + " " + sentences[i + 1]

                related_sentences.append(context_snippet)

        # 최대 2개의 컨텍스트만 저장
        context[keyword] = related_sentences[:2]

    return {
        "keywords": keywords,
        "context": context
    }


# 사용 예시
if __name__ == "__main__":
    sample_text = open('/Users/rover0811/PycharmProjects/Lecture2Quiz/data/인공지능 0414.txt', 'r', encoding='utf-8').read()

    # 컴퓨터 비전 도메인 지정
    result = extract_keyword_with_context(sample_text, top_n=20, domain='computer_vision')

    print("추출된 키워드:", result["keywords"])
    print("\n키워드별 컨텍스트:")
    for keyword, contexts in result["context"].items():
        print(f"\n[{keyword}]")
        for i, ctx in enumerate(contexts):
            print(f"  컨텍스트 {i + 1}: {ctx}")