def build_answer(generator, retrieved_chunks):
    answer = generator(retrieved_chunks)
    valid_ids = {chunk["id"] for chunk in retrieved_chunks}
    if any(citation not in valid_ids for citation in answer["citation_ids"]):
        raise ValueError("Answer contained an unsupported citation")
    return answer

