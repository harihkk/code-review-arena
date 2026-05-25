from app.rag.models import RetrievedDocument


def build_prompt(
    *, system_instructions: str, retrieved: list[RetrievedDocument]
) -> str:
    retrieved_text = "\n".join(document.text for document in retrieved)
    return system_instructions + "\n" + retrieved_text
