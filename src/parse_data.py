import itertools

def txt_to_records(txt_file, category, id='rec', sentences_per_chunk=5, overlap=1):
    sentences = []
    step = sentences_per_chunk - overlap

    with open(txt_file, 'r', encoding='utf-8') as f:
        for line in f:
            if line := line.strip():
                sentences.append(line)

    modified_sentences = []
    for i in range(0, len(sentences), step):
        window = sentences[i:i + sentences_per_chunk]
        if len(window) >= 2:  # 최소 2문장 이상인 경우만 추가
            modified_sentences.append(window)
    records= []
    # itertools.batched 사용 (Python 3.12+)
    for i, chunk_sentences in enumerate(modified_sentences):
        chunk_text = ' '.join(chunk_sentences)
        record_id = f"{id}{i}"

        records.append({
            "id": record_id,
            "text": chunk_text,
            "category": category
        })

    return records


def batch_with_itertools(iterable, batch_size=96):
    """
    itertools를 사용하여 iterable을 지정된 크기의 배치로 나눕니다.

    Args:
        iterable: 나눌 iterable 객체
        batch_size: 배치 크기 (기본값: 96)

    Returns:
        배치 리스트의 제너레이터
    """
    it = iter(iterable)
    while True:
        batch = list(itertools.islice(it, batch_size))
        if not batch:
            break
        yield batch


if __name__ == '__main__':
    records = txt_to_records('../data/인공지능 0414.txt', 'ai')
