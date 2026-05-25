from app.models import Document


class DocumentRepository:
    def __init__(self) -> None:
        self._documents: dict[str, Document] = {}

    def add(self, document: Document) -> None:
        self._documents[document.id] = document

    def fetch(self, document_id: str) -> Document | None:
        return self._documents.get(document_id)
