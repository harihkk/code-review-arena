import pytest

from rag.answer import build_answer


def test_rejects_unsupported_source_ids():
    retrieved = [{"id": "chunk-1", "text": "policy text"}]

    def generator(_chunks):
        return {"text": "answer", "citation_ids": ["chunk-99"]}

    with pytest.raises(ValueError, match="unsupported citation"):
        build_answer(generator, retrieved)
