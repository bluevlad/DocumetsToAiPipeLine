"""token_counter 단위 테스트."""

from app.ingestion.token_counter import count_tokens, create_batches


class TestCountTokens:
    def test_empty_string(self):
        assert count_tokens("") == 0

    def test_simple_text(self):
        tokens = count_tokens("hello world")
        assert tokens > 0

    def test_korean_text(self):
        tokens = count_tokens("안녕하세요 세계")
        assert tokens > 0

    def test_longer_text_more_tokens(self):
        short = count_tokens("hello")
        long = count_tokens("hello world this is a longer text")
        assert long > short


class TestCreateBatches:
    def test_empty_list(self):
        batches = create_batches([])
        assert batches == []

    def test_single_item(self):
        batches = create_batches(["hello"])
        assert batches == [[0]]

    def test_respects_max_tokens(self):
        # 긴 텍스트 여러 개 → 여러 배치
        texts = ["hello world " * 500] * 5
        batches = create_batches(texts, max_tokens=1000)
        assert len(batches) > 1
        # 모든 인덱스가 포함되어야 함
        all_indices = [i for batch in batches for i in batch]
        assert sorted(all_indices) == [0, 1, 2, 3, 4]

    def test_respects_max_items(self):
        texts = ["hi"] * 10
        batches = create_batches(texts, max_tokens=100000, max_items=3)
        assert all(len(batch) <= 3 for batch in batches)
        all_indices = [i for batch in batches for i in batch]
        assert sorted(all_indices) == list(range(10))

    def test_small_texts_single_batch(self):
        texts = ["hello", "world", "test"]
        batches = create_batches(texts, max_tokens=10000)
        assert len(batches) == 1
        assert batches[0] == [0, 1, 2]
