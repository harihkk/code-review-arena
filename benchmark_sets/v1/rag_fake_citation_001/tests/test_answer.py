from rag.answer import build_answer


def test_generated_citations_must_exist_in_context():
    generator = lambda _chunks: {"text": "Claim", "citation_ids": ["invented"]}
    try:
        build_answer(generator, [{"id": "source-1", "text": "Evidence"}])
    except ValueError:
        return
    raise AssertionError("unsupported citation was accepted")

